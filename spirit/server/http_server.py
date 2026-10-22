import http.server
import socketserver
import threading
from collections import OrderedDict
import logging
import json
import gzip
import time
import uuid
import os
import re
import hashlib
import UnityPy
from typing import Any
from spirit import config
import spirit.server.state as state

from spirit.server.state import issue_ticket
from spirit.database.accounts import get_account_by_username, verify_password, create_account
from spirit.server import metrics
from spirit.server.manifest_manager import ManifestManager
from spirit.server import fast_split
from spirit.server import typed_splits
from spirit.server import lzma_sets
from urllib.parse import parse_qs
from urllib.parse import urlparse

# Global manifest manager instance
ASSET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'assets'))
BUNDLE_CACHE_DIR = os.path.join(ASSET_DIR, 'bundleCache')

# We'll prioritize our local bundleCache
ASSET_PATHS = [BUNDLE_CACHE_DIR]

# Allow users to specify an external cache path via environment variable
# or use a local 'externalCache' directory to load original game assets without committing them
external_cache_env = os.environ.get('PTCGO_CACHE_DIR')
local_external_cache = os.path.join(ASSET_DIR, 'externalCache')

if external_cache_env:
    external_cache_env = os.path.abspath(os.path.expanduser(external_cache_env))
    nested_bundle_cache = os.path.join(external_cache_env, 'bundleCache')
    if os.path.isdir(nested_bundle_cache):
        external_cache_env = nested_bundle_cache

if external_cache_env and os.path.isdir(external_cache_env):
    logging.info(f"[HTTP] Found external cache via env: {external_cache_env}")
    ASSET_PATHS.append(external_cache_env)
elif os.path.isdir(local_external_cache):
    logging.info(f"[HTTP] Found local external cache: {local_external_cache}")
    ASSET_PATHS.append(local_external_cache)

manifest_manager = ManifestManager(ASSET_PATHS)

# Virtual type-split bundles (e.g. en_US_SM5_fighting) are rebuilt in a child
# process (spirit/server/virtual_split_worker.py) and kept on DISK, not in RAM.
# Building them inside this process and caching them in memory pushed a 4 GB VPS
# into the OOM killer a few minutes into the first game.
VIRTUAL_SPLIT_CACHE_DIR = os.environ.get(
    "SPIRIT_SPLIT_CACHE_DIR", os.path.join(ASSET_DIR, 'virtualSplitCache'))
VIRTUAL_SPLIT_CACHE_MAX_BYTES = int(os.environ.get(
    "SPIRIT_SPLIT_CACHE_BYTES", str(6 * 1024 * 1024 * 1024)))
# Serve splits by rewriting just the bundle directory (see fast_split.py).
# SPIRIT_FAST_SPLITS=0 goes back to the old build-and-cache path.
FAST_SPLITS = os.environ.get("SPIRIT_FAST_SPLITS", "1") != "0"
VIRTUAL_SPLIT_BUILD_TIMEOUT = int(os.environ.get("SPIRIT_SPLIT_BUILD_TIMEOUT", "600"))
_WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'virtual_split_worker.py')

# Per-key build locks so a stampede of first requests for one split does ONE build
# while the rest wait and then hit the disk cache.
_VIRTUAL_BUILD_LOCKS = {}
_VIRTUAL_BUILD_LOCKS_GUARD = threading.Lock()

# Global cap on concurrent builds: each child peaks at several hundred MB.
_VIRTUAL_BUILD_SEMAPHORE = threading.BoundedSemaphore(
    max(1, int(os.environ.get("SPIRIT_BUNDLE_BUILD_CONCURRENCY", "1"))))

def _bundle_build_lock(key):
    with _VIRTUAL_BUILD_LOCKS_GUARD:
        lock = _VIRTUAL_BUILD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _VIRTUAL_BUILD_LOCKS[key] = lock
        return lock

def _virtual_split_cache_path(filename, source_path):
    """Disk-cache path for a split, keyed on the source bundle's identity so a
    rebuilt set bundle never serves a stale split."""
    st = os.stat(source_path)
    key = f"{os.path.abspath(source_path)}|{st.st_size}|{st.st_mtime_ns}"
    digest = hashlib.md5(key.encode('utf-8')).hexdigest()[:12]
    stem = filename[:-len(".unity3d")] if filename.endswith(".unity3d") else filename
    return os.path.join(VIRTUAL_SPLIT_CACHE_DIR, f"{stem}-{digest}.unity3d")

def _evict_virtual_split_cache():
    """Delete least-recently-used splits until the cache fits its byte budget."""
    try:
        entries = []
        for name in os.listdir(VIRTUAL_SPLIT_CACHE_DIR):
            if not name.endswith(".unity3d"):
                continue
            path = os.path.join(VIRTUAL_SPLIT_CACHE_DIR, name)
            st = os.stat(path)
            entries.append((st.st_mtime, st.st_size, path))
    except OSError:
        return
    total = sum(size for _, size, _ in entries)
    for _, size, path in sorted(entries):
        if total <= VIRTUAL_SPLIT_CACHE_MAX_BYTES:
            break
        try:
            os.remove(path)
            total -= size
        except OSError:
            pass

# LRU cache of filename -> resolved on-disk path (skips the os.walk probing per request)
ASSET_PATH_CACHE = OrderedDict()
ASSET_PATH_CACHE_MAX = 1024
_ASSET_PATH_LOCK = threading.Lock()

def _asset_path_cache_get(filename):
    with _ASSET_PATH_LOCK:
        path = ASSET_PATH_CACHE.get(filename)
        if path is not None:
            ASSET_PATH_CACHE.move_to_end(filename)
    if path is not None and not os.path.exists(path):
        with _ASSET_PATH_LOCK:
            ASSET_PATH_CACHE.pop(filename, None)
        return None
    return path

def _asset_path_cache_put(filename, path):
    with _ASSET_PATH_LOCK:
        ASSET_PATH_CACHE[filename] = path
        ASSET_PATH_CACHE.move_to_end(filename)
        while len(ASSET_PATH_CACHE) > ASSET_PATH_CACHE_MAX:
            ASSET_PATH_CACHE.popitem(last=False)


def register_asset_path(path):
    """Adds a newly-created bundle cache to serving and refreshes the manifest.

    Admin-managed landing artwork can create ``externalCache`` after server
    startup, so the one-time module initialization above cannot be relied on to
    discover it.  ``ManifestManager`` intentionally shares the ASSET_PATHS list.
    """
    asset_path = os.path.abspath(os.fspath(path))
    if not os.path.isdir(asset_path):
        raise FileNotFoundError(f"Asset cache does not exist: {asset_path}")
    normalized = os.path.normcase(asset_path)
    if not any(os.path.normcase(os.path.abspath(p)) == normalized for p in ASSET_PATHS):
        ASSET_PATHS.append(asset_path)
    with _ASSET_PATH_LOCK:
        ASSET_PATH_CACHE.clear()
    manifest_manager.refresh()


class MockHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    # HTTP/1.1 keep-alive reuses one TCP connection for many asset bundles
    # (remote clients otherwise pay a handshake per card set). Requires an
    # accurate Content-Length on EVERY response; timeout reaps idle sockets.
    protocol_version = "HTTP/1.1"
    timeout = 60

    def handle(self):
        # Idle keep-alive sockets get RST by the remote client/NAT; swallow the
        # benign disconnect instead of letting socketserver dump a traceback.
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError):
            self.close_connection = True

    # Slow-download log (owner, Oct 16): a request taking longer than this
    # is logged at INFO with path, size, time and the player's address, so a
    # stuck loading bar leaves a trace.  Fast requests stay silent.
    SLOW_REQUEST_SECONDS = 3.0

    def send_header(self, keyword, value):
        if keyword.lower() == 'content-length':
            self._sent_length = value
        return super().send_header(keyword, value)

    def _timed(self, handler):
        start = time.monotonic()
        self._sent_length = None
        try:
            return handler()
        finally:
            took = time.monotonic() - start
            if took >= self.SLOW_REQUEST_SECONDS:
                who = (self.headers.get('X-Forwarded-For') or self.headers.get('X-Real-IP')
                       or self.client_address[0]) if self.headers else self.client_address[0]
                size = self._sent_length
                size_txt = f"{int(size) / 1_048_576:.1f} MB" if str(size or '').isdigit() else "? MB"
                logging.info(f"[HTTP] Slow request: {self.command} {urlparse(self.path).path} "
                             f"({size_txt}) took {took:.1f}s for {str(who).split(',')[0].strip()}")

    def log_message(self, format, *args):
        logging.debug(f"[HTTP] {self.client_address[0]} - - [{self.log_date_time_string()}] {format%args}")

    def log_error(self, format, *args):
        # Routine keep-alive reaping (idle timeout / reset) surfaces here — keep it out of INFO.
        logging.debug(f"[HTTP] {self.client_address[0]} - {format % args}")

    def serve_admin(self, method, parsed_path, body=None):
        """Delegates /admin requests to the Admin Dashboard API."""
        from spirit.server.admin_api import route_admin
        result = route_admin(method, parsed_path, body, headers=self.headers)
        extra_headers = []
        if len(result) == 4:
            status, payload, content_type, extra_headers = result
        else:
            status, payload, content_type = result
        self.send_response(status)
        self.send_header('Content-type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        for name, value in extra_headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        return self._timed(self._do_get)

    def do_POST(self):
        return self._timed(self._do_post)

    def _do_get(self):
        logging.debug(f"[HTTP] GET Request received for path: {self.path}")
        metrics.inc("http_requests")

        # Clean the path to ignore query parameters
        parsed_path = urlparse(self.path).path

        if parsed_path == '/health':
            return self._serve_health()
        if parsed_path in ('/leaderboard', '/leaderboard/'):
            return self._serve_leaderboard_page()
        if parsed_path in ('/leaderboard.json', '/api/leaderboard'):
            return self._serve_leaderboard_json()
        if parsed_path == '/admin/api/metrics':
            return self.serve_admin('GET', parsed_path)

        if parsed_path == '/admin' or parsed_path.startswith('/admin/'):
            return self.serve_admin('GET', parsed_path)

        # The client adds dynamic GUIDs to the path, so we catch anything ending in .unity3d
        if parsed_path.endswith(".unity3d"):
            return self.handle_cdn_asset(parsed_path)

        # Routing dictionary
        routes = {
            "messaging/manifest.json": self.handle_messaging_manifest,
            "manifest.json": self.handle_patch_manifest,
            "manifest.version": self.handle_manifest_version,
            ".manifest": self.handle_asset_manifest,
            "config.json": self.handle_config,
            "dynamic_config.json": self.handle_config,
            "motd.json": self.handle_motd,
            "sso/login": self.handle_cas_login,
            "placeholder.png": self.handle_placeholder_image,
            "eula/en_us_agreement_pc.txt": self.handle_eula_us_agreement,
            "privacypolicy/en_us_privacy_policy_pc.txt": self.handle_privacy_policy,
        }

        # Check for product images
        # Intercept both explicit /products/ requests and logical asset name requests to prevent Shop 404s
        if "/products/" in parsed_path or not any(parsed_path.endswith(ext) for ext in [".unity3d", ".json", ".txt"]):
            filename = os.path.basename(parsed_path).lower()
            
            custom_dirs = [
                os.path.join(ASSET_DIR, "products", "custom_packs"),
                os.path.join(ASSET_DIR, "products", "custom_pcds"),
                os.path.join(ASSET_DIR, "products", "custom_sleeves"),
                os.path.join(ASSET_DIR, "products", "custom_coins"),
                os.path.join(ASSET_DIR, "products", "custom_deckboxes"),
                os.path.join(ASSET_DIR, "products"),
            ]
            
            base_name = filename.replace(".png", "")
            candidates = [filename, f"{filename}.png", base_name, f"{base_name}.png"]
            
            for d in custom_dirs:
                if not os.path.exists(d):
                    continue
                for cand in candidates:
                    product_path = os.path.join(d, cand)
                    if os.path.exists(product_path) and os.path.isfile(product_path):
                        logging.debug(f"[HTTP] Product Image Match Found: {parsed_path} -> {product_path}")
                        return self.serve_static_file(product_path, 'image/png')

        for route_key, handler in routes.items():
            if parsed_path.endswith(route_key):
                return handler()

        return self.handle_default()

    def handle_eula_us_agreement(self):
        eula_path = os.path.join(ASSET_DIR, "eula", "en_us_agreement_pc.txt")
        return self.serve_static_file(eula_path, 'text/plain; charset=utf-8')

    def handle_privacy_policy(self):
        privacy_path = os.path.join(ASSET_DIR, "eula", "en_us_privacy_policy_pc.txt")
        return self.serve_static_file(privacy_path, 'text/plain; charset=utf-8')

    def _send_bytes(self, payload: bytes, content_type: str, cache: str = 'no-store',
                    cors: bool = False):
        self.send_response(200)
        if cors:
            self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', cache)
        self.end_headers()
        self.wfile.write(payload)

    def _serve_leaderboard_page(self):
        """Public live leaderboard (owner request Oct 21)."""
        page = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'leaderboard_page.html')
        try:
            with open(page, 'rb') as f:
                payload = f.read()
        except OSError:
            self.send_response(404)
            self.end_headers()
            return
        return self._send_bytes(payload, 'text/html; charset=utf-8', 'max-age=60')

    def _serve_leaderboard_json(self):
        """Public read-only API: other sites (e.g. a community page) may
        fetch it from the browser, so it allows any origin."""
        from spirit.database.leaderboard_data import get_leaderboard
        payload = json.dumps(get_leaderboard()).encode('utf-8')
        return self._send_bytes(payload, 'application/json', cors=True)

    def _serve_health(self):
        """Liveness/readiness probe: 200 once content is loaded, else 503."""
        try:
            from spirit.packets.handlers import data_sync
            ready = bool(getattr(data_sync, "CARDS_DB", None))
        except Exception:
            ready = False
        payload = json.dumps({"status": "ok" if ready else "loading", "ready": ready}).encode('utf-8')
        self.send_response(200 if ready else 503)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_static_file(self, file_path, content_type):
        if os.path.exists(file_path):
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-Length', str(os.path.getsize(file_path)))
            self.end_headers()
            # Stream in chunks: a full f.read() of a large asset holds the whole file
            # in RAM per handler thread (up to ~84 MB for a set bundle).
            import shutil
            with open(file_path, 'rb') as f:
                shutil.copyfileobj(f, self.wfile, 256 * 1024)
        else:
            logging.warning(f"[HTTP] File Not Found: {file_path}")
            return self.handle_default()

    def handle_placeholder_image(self):
        """Serves a 1x1 transparent PNG to satisfy DuiTexture.LoadFromURL"""
        # 1x1 Transparent PNG
        png_data = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b4944415478da6360000000020001737501180000000049454e44ae426082")
        self.send_response(200)
        self.send_header('Content-type', 'image/png')
        self.send_header('Content-length', str(len(png_data)))
        self.end_headers()
        self.wfile.write(png_data)

    def _do_post(self):
        # Junk from internet scanners (bad Content-Length, non-UTF-8 bodies)
        # must not dump a traceback: reject it quietly.
        try:
            content_length = max(0, int(self.headers.get('Content-Length', 0)))
        except ValueError:
            self.send_error(400)
            return
        post_data = self.rfile.read(content_length).decode('utf-8', errors='replace')
        # NEVER log the body: CAS login and /admin POST carry passwords/tickets.
        logging.debug(f"[HTTP] POST path={self.path} ({content_length} bytes)")
        parsed_path = urlparse(self.path).path

        if parsed_path == '/admin' or parsed_path.startswith('/admin/'):
            return self.serve_admin('POST', parsed_path, post_data)

        # Routing dictionary
        routes = {
            "sso/login": self.handle_cas_login
        }

        for route_key, handler in routes.items():
            if parsed_path.endswith(route_key):
                return handler(post_data)

        return self.handle_default()

    def send_json_response(self, data):
        """Helper to send standard JSON responses"""
        payload = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def handle_patch_manifest(self):
        """Source Logic: client_source/pie/pie-src/CheckForPatchBehavior.cs"""
        host = self.headers.get("Host", state.SERVER_HOST)
        response = {
            "LatestWindowsPatcherVersion": 240,
            "LatestMacPatcherVersion": 240,
            "LatestWindowsClientVersion": 5815,
            "LatestMacClientVersion": 5815,
            "WindowsPatcherDownloadLink": f"http://{host}/refresher.zip",
            "MacPatcherDownloadLink": f"http://{host}/refresher.zip"
        }
        self.send_json_response(response)

    def handle_messaging_manifest(self):
        """Source Logic: ServerManifestDataRetriever.cs — null 'messaging' array NREs the Tournament scene."""
        host = self.headers.get("Host", state.SERVER_HOST)
        self.send_json_response({"cdn_url": f"http://{host}/", "messaging": []})

    def handle_manifest_version(self):
        """Source Logic: LoadManifestVersion.cs"""
        logging.info(f"[HTTP] Sending Manifest Version: {manifest_manager.manifest_version}")
        payload = str(manifest_manager.manifest_version).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def handle_asset_manifest(self):
        """Source Logic: LoadManifest.cs (Requires GZip compression)"""
        logging.info("[HTTP] Sending Full Asset Manifest (GZipped)...")
        payload = manifest_manager.generate_manifest()
        self.send_response(200)
        self.send_header('Content-type', 'application/x-gzip')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def handle_cdn_asset(self, path):
        """Serves .unity3d files using a Robust Matcher to handle client path mangling."""
        filename = os.path.basename(path)
        asset_full_path = None

        # 1. Generate candidates for matching
        # Candidate 1: Full name without extension (e.g. en_US_Free_Energy_1)
        full_no_ext = filename.replace(".unity3d", "")

        # Candidate 2: Normalized (stripped redundant prefixes and version suffixes)
        # e.g. en_US_en_US_Free_Energy_1 -> en_US_Free_Energy
        normalized = re.sub(r'_\d+(\.unity3d)?$', '', filename)
        normalized = re.sub(r'^(en_US_)+', 'en_US_', normalized).replace(".unity3d", "")

        # Candidate 3: Clean base (no locale)
        clean_base = normalized.replace("en_US_", "")

        # Handle virtual type-split suffixes by stripping them (e.g. SWSH12_water -> SWSH12)
        split_suffixes = [
            "_grass", "_fire", "_water", "_lightning", "_psychic", "_fighting",
            "_darkness", "_metal", "_fairy", "_dragon", "_colorless", "_trainer"
        ]
        
        clean_base_stripped = clean_base
        for suffix in split_suffixes:
            if clean_base.lower().endswith(suffix):
                clean_base_stripped = clean_base[:-len(suffix)]
                break

        candidates = [full_no_ext, normalized, clean_base]

        # Candidate 4: Clean base without version suffix
        clean_no_suffix = re.sub(r'_\d+$', '', clean_base)
        if clean_no_suffix not in candidates:
            candidates.append(f"en_US_{clean_no_suffix}")
            candidates.append(clean_no_suffix)

        # Candidate 5: Stripped split-suffix variants (allows SWSH12_water -> en_US_SWSH12)
        if clean_base_stripped != clean_base:
            clean_stripped_no_suffix = re.sub(r'_\d+$', '', clean_base_stripped)
            for variant in [clean_base_stripped, clean_stripped_no_suffix]:
                if variant not in candidates:
                    candidates.append(f"en_US_{variant}")
                    candidates.append(variant)

        cached_path = _asset_path_cache_get(filename)
        if cached_path is not None:
            asset_full_path = cached_path

        # Search across all registered asset paths
        for base_dir in ASSET_PATHS if asset_full_path is None else []:
            if not os.path.exists(base_dir):
                continue

            # Priority 1: Exact directory match for candidates
            for candidate in candidates:
                potential_folder = os.path.join(base_dir, candidate)
                if os.path.exists(potential_folder) and os.path.isdir(potential_folder):
                    for root, _, files in os.walk(potential_folder):
                        if "__data" in files:
                            asset_full_path = os.path.join(root, "__data")
                            logging.debug(f"[HTTP] Match Found: {filename} -> {asset_full_path} (via {candidate})")
                            break
                if asset_full_path: break
            if asset_full_path: break
            # Priority 2: Direct file match
            test_path = os.path.join(base_dir, filename)
            if os.path.exists(test_path) and os.path.isfile(test_path):
                asset_full_path = test_path
                break
            
            # Priority 3: Fuzzy fallback (only if desperate)
            for entry in os.listdir(base_dir):
                entry_path = os.path.join(base_dir, entry)
                if clean_base_stripped.lower() in entry.lower():
                    if os.path.isdir(entry_path):
                        for root, _, files in os.walk(entry_path):
                            if "__data" in files:
                                asset_full_path = os.path.join(root, "__data")
                                logging.info(f"[HTTP] Fuzzy Match: {filename} -> {asset_full_path}")
                                break
                if asset_full_path: break
            if asset_full_path: break

        logging.debug(f"[HTTP] Asset Requested: {filename} (Path: {path})")

        if asset_full_path and cached_path is None:
            _asset_path_cache_put(filename, asset_full_path)

        if asset_full_path and os.path.exists(asset_full_path):
            is_virtual_split = (clean_base_stripped != clean_base)

            # Slim per-type file (only that type's cards): keeps players'
            # card caches near the size of the sets instead of up to 12x.
            typed_path = self._typed_split_path(filename, asset_full_path, clean_base) \
                if is_virtual_split and typed_splits.enabled() else None

            if is_virtual_split and FAST_SPLITS and typed_path is None:
                # Rewrite only the bundle directory and stream the set bundle's
                # data as-is: instant, and nothing to cache on disk.
                new_cab_name = f"CAB-{hashlib.md5(clean_base.encode('utf-8')).hexdigest()}"
                try:
                    split_plan = fast_split.plan(asset_full_path, new_cab_name)
                except Exception as e:
                    logging.warning(f"[HTTP] Fast split failed for {filename}: {e}")
                    split_plan = None
                if split_plan is not None:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/vnd.unity')
                    self.send_header('Content-Length', str(split_plan.length))
                    self.send_header('Cache-Control', 'no-cache, must-revalidate')
                    self.send_header('Pragma', 'no-cache')
                    self.end_headers()
                    split_plan.stream(self.wfile)
                    metrics.inc("fast_splits")
                    return

            if typed_path is not None:
                serve_path = typed_path
            elif is_virtual_split:
                serve_path = self._virtual_split_path(filename, asset_full_path, clean_base)
                if serve_path is None:
                    self.send_response(503)
                    self.send_header('Retry-After', '5')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
            else:
                serve_path = asset_full_path
                # Whole set: the smaller LZMA copy when one has been built
                # (downloads finish inside the client's ~30 s limit).
                if lzma_sets.enabled():
                    serve_path = lzma_sets.existing_copy(
                        lzma_sets.cache_dir(VIRTUAL_SPLIT_CACHE_DIR), asset_full_path) or asset_full_path

            self.send_response(200)
            self.send_header('Content-type', 'application/vnd.unity')
            self.send_header('Content-Length', str(os.path.getsize(serve_path)))
            # Unity maintains its own versioned AssetBundle cache.  A one-year
            # HTTP freshness lifetime here can serve old bytes after the
            # manifest version changes, making regenerated card/foil textures
            # appear unchanged.  Revalidate the URL and let Unity retain the
            # bundle under the content-derived manifest version.
            self.send_header('Cache-Control', 'no-cache, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.end_headers()
            # Stream from disk: never hold a whole ~84 MB bundle in RAM per request.
            import shutil
            with open(serve_path, 'rb') as f:
                shutil.copyfileobj(f, self.wfile, 256 * 1024)
            logging.debug(f"[HTTP] Asset Sent Successfully: {filename} from {asset_full_path}")
            return
        else:
            logging.warning(f"[HTTP] Asset Not Found on Disk: {filename}")
            self.send_response(404)
            self.send_header('Content-Length', '0')
            self.end_headers()

    def _typed_split_path(self, filename, asset_full_path, clean_base):
        """The slim per-type bundle for ``filename`` (built on first request
        and kept on disk), or None to fall back to the full-set split."""
        parts = typed_splits.split_parts(clean_base)
        if parts is None:
            return None
        try:
            drop = typed_splits.drop_names(*parts)
            if drop is None:
                return None
            path = typed_splits.cache_path(VIRTUAL_SPLIT_CACHE_DIR, clean_base,
                                           asset_full_path, drop)
        except Exception as e:
            logging.warning(f"[TypedSplit] {filename}: {e}")
            return None
        if os.path.exists(path):
            try:
                os.utime(path)   # LRU touch
            except OSError:
                pass
            return path
        with _bundle_build_lock(path):
            if os.path.exists(path):
                return path
            with _VIRTUAL_BUILD_SEMAPHORE:
                started = time.time()
                if not typed_splits.build(asset_full_path, path, clean_base, drop,
                                          timeout=VIRTUAL_SPLIT_BUILD_TIMEOUT):
                    return None
                logging.info(f"[TypedSplit] Built {clean_base} in {time.time() - started:.1f}s.")
                _evict_virtual_split_cache()
                return path

    def _virtual_split_path(self, filename, asset_full_path, clean_base):
        """Return the on-disk split bundle for ``filename``, building it in a
        child process on first request.  None if the build failed."""
        cache_path = _virtual_split_cache_path(filename, asset_full_path)
        if os.path.exists(cache_path):
            try:
                os.utime(cache_path)   # LRU touch
            except OSError:
                pass
            return cache_path
        with _bundle_build_lock(filename):
            if os.path.exists(cache_path):
                return cache_path
            with _VIRTUAL_BUILD_SEMAPHORE:
                return self._build_virtual_split(filename, asset_full_path, clean_base, cache_path)

    def _build_virtual_split(self, filename, asset_full_path, clean_base, cache_path):
        import subprocess
        import sys
        # Stable, unique CAB name for this virtual split bundle (deterministic).
        new_cab_name = f"CAB-{hashlib.md5(clean_base.encode('utf-8')).hexdigest()}"
        os.makedirs(VIRTUAL_SPLIT_CACHE_DIR, exist_ok=True)
        started = time.time()
        try:
            result = subprocess.run(
                [sys.executable, _WORKER_SCRIPT, asset_full_path, cache_path, new_cab_name],
                capture_output=True, text=True, timeout=VIRTUAL_SPLIT_BUILD_TIMEOUT)
        except subprocess.TimeoutExpired:
            logging.error(f"[HTTP] Split build timed out for {filename}")
            return None
        for line in (result.stderr or "").splitlines():
            if line.strip():
                logging.info(f"[HTTP] [split-worker] {line}")
        if result.returncode != 0 or not os.path.exists(cache_path):
            logging.error(f"[HTTP] Split build failed for {filename} (exit {result.returncode})")
            return None
        logging.info(f"[HTTP] Built split {filename} -> {new_cab_name} "
                     f"in {time.time() - started:.1f}s (disk-cached).")
        _evict_virtual_split_cache()
        return cache_path

    def handle_config(self):
        """Source Logic: PieDynamicConfig.cs"""
        # Dynamically record the host being used by the client
        host = self.headers.get("Host", state.SERVER_HOST)
        state.SERVER_HOST = host

        # The AssetURL is the base for all .unity3d downloads.
        cdn_base = f"http://{host}/"

        self.send_json_response({
            "hostName": f"http://{host}/cas",
            "AssetURL": cdn_base,
            "collectorURL": f"http://{host}/collector/",
            "helpButtonDestination": f"http://{host}/help/",
            "localizedSignup": f"http://{host}/signup/",
            "serviceID": "pokemon_tcgo",
            # ``BackgroundImageBehaviour`` builds the asset key as
            # ``Background{resolution}/Background{release}``.  The spelling
            # of this JSON field is intentionally kept as the archived client
            # expects it.  ``_cr112`` therefore resolves to the original
            # ``Background/background_cr112`` asset in the cache manifest.
            "bacgroundRelease": "_cr112",
        })

    def handle_motd(self):
        """Source Logic: ShowSystemMessageBehaviour.cs"""
        current_time_ms = int(time.time() * 1000)
        response = {
            "message": {
                "en": "Welcome to Gym Leader Challenge!",
                "en_US": "Welcome to Gym Leader Challenge!",
                "en_UK": "Welcome to Gym Leader Challenge!"
            },
            "urgency": "High",
            "date": current_time_ms
        }
        self.send_json_response(response)

    def handle_cas_login(self, post_data=None):
        """Source Logic: O.X.cs (CasAuthCommand)"""

        if self.command == 'GET':
            # The client's regex expects name="lt" value="..." and name="execution" value="..."
            # Based on PrivateImplementationDetails decryption, regexes are approx 45-52 chars.
            html = """
            <!DOCTYPE html>
            <html>
            <body>
                <form action="" method="post">
                    <input type="hidden" name="lt" value="LT-MOCK-TOKEN-12345" />
                    <input type="hidden" value="LT-MOCK-TOKEN-12345" name="lt" />
                    <input name="lt" type="hidden" value="LT-MOCK-TOKEN-12345" />

                    <input type="hidden" name="execution" value="e1s1" />
                    <input type="hidden" value="e1s1" name="execution" />
                    <input name="execution" type="hidden" value="e1s1" />

                    <input type="text" name="username" />
                    <input type="password" name="password" />
                    <input type="submit" name="submit" value="Login" />
                </form>
            </body>
            </html>
            """
            payload = html.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.command == 'POST':
            # 1. Parse Credentials
            if post_data is None:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')

            params = parse_qs(post_data)

            username = params.get('username', [''])[0]
            password = params.get('password', [''])[0]

            logging.info(f"[HTTP] Login attempt for user: {username}")

            # 2. Validate Password
            account = get_account_by_username(username)
            if not account:
                # Auto-register for this private server
                logging.info(f"[HTTP] User '{username}' not found. Auto-registering...")
                account = create_account(username, password)

            if account and verify_password(account['password_hash'], password):
                # 3. Success! Generate a Ticket (never log the ticket — it is a live
                # bearer credential valid for the CAS TTL).
                ticket = f"ST-{uuid.uuid4()}"
                state.sweep_expired_tickets()
                issue_ticket(ticket, username)
                logging.info(f"[HTTP] Password verified for '{username}'. Ticket issued.")
                metrics.inc("cas_tickets_issued")

                # 4. Redirect with Ticket
                host = self.headers.get("Host", state.SERVER_HOST)
                body = f"ticket={ticket}\n?ticket={ticket}\n&ticket={ticket}".encode('utf-8')
                self.send_response(302)
                self.send_header('Location', f'http://{host}/cas/sso/login?ticket={ticket}')
                self.send_header('Content-type', 'text/html')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                # 5. Failure
                logging.warning(f"[HTTP] Invalid password for user: {username}")
                body = b"Authentication Failed. Check your credentials."
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)


    def handle_default(self):
        """Fallback for unhandled assets or telemetry to prevent freezing"""
        payload = b"{}"
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

class _AssetTCPServer(socketserver.ThreadingTCPServer):
    """Thread per connection. The stock listen backlog is 5: when many
    clients load card art at once (each opens several downloads), extra
    connection attempts were dropped and retried by the client, which
    shows as a loading bar crawling (owner report Oct 16, "takes forever
    to get to 80%")."""
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 256


class AssetHTTPServer:
    def __init__(self, host='0.0.0.0', port=config.HTTP_PORT):
        self.host = host
        self.port = port
        self.server = _AssetTCPServer((self.host, self.port), MockHTTPRequestHandler)
        self.thread = None

    def start(self):
        logging.info(f"Asset HTTP Server listening on http://{self.host}:{self.port}")
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        if self.thread:
            self.thread.join()
        logging.info("Asset HTTP Server stopped.")
