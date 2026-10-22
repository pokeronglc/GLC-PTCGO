"""Whole-set card bundles re-packed with LZMA (about a third smaller).

The client downloads each set's whole bundle (``en_US_SM11_<ver>.unity3d``,
50-120 MB stored LZ4) and abandons a download after about 30 seconds, so on
connections slower than ~3 MB/s the big sets never finish and their cards
stay on "Loading".  Unity accepts LZMA bundles (tested live, Oct 2026: SM11
92 MB -> 59 MB, loaded fine) and re-stores them in its own cache format, so
players' cache size doesn't change -- only the download gets smaller.

LZMA packing takes ~2 minutes per set, so copies are never built on request:
build them with ``python -m spirit.tools.build_lzma_sets`` first, then set
``SPIRIT_LZMA_SETS=1``.  A set without a copy (or with a stale one, after its
source bundle changes) is served as before.

Usage as a worker: python lzma_sets.py SRC OUT
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from typing import Optional


# Bump when the copies' contents change (new file names, so stale copies are
# never served).  2: card template leftovers removed (bundle_trim).
REVISION = 2


def enabled() -> bool:
    return os.environ.get("SPIRIT_LZMA_SETS", "0") == "1"


def cache_dir(split_cache_dir: str) -> str:
    """Beside the split cache (same volume), never inside it: the split
    cache's size-based eviction must not delete these."""
    override = os.environ.get("SPIRIT_LZMA_DIR")
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(split_cache_dir)), "lzma_sets")


def set_name(source_path: str) -> str:
    """'.../en_US_SM11/0000.../__data' -> 'SM11'."""
    parts = os.path.abspath(source_path).split(os.sep)
    for part in reversed(parts):
        if part.startswith("en_US_"):
            return part[len("en_US_"):]
    return os.path.basename(os.path.dirname(source_path))


def copy_path(directory: str, source_path: str) -> str:
    st = os.stat(source_path)
    key = json.dumps([REVISION, os.path.abspath(source_path), st.st_size, st.st_mtime_ns])
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    return os.path.join(directory, f"lzma-{set_name(source_path)}-{digest}.unity3d")


def existing_copy(directory: str, source_path: str) -> Optional[str]:
    """The LZMA copy of this bundle if it has been built, else None."""
    try:
        path = copy_path(directory, source_path)
    except OSError:
        return None
    return path if os.path.exists(path) else None


def build(source_path: str, out_path: str, timeout: int = 1800) -> Optional[int]:
    """Pack one bundle in a child process (UnityPy + LZMA need several hundred
    MB; the memory goes back to the OS when the child exits).  Returns the
    new size, or None on failure.  When LZMA isn't smaller, writes nothing
    and returns the source size (the original keeps being served)."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        result = subprocess.run([sys.executable, os.path.abspath(__file__), source_path, out_path],
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"timed out: {source_path}", file=sys.stderr)
        return None
    if result.returncode != 0:
        print((result.stderr or "").strip()[-2000:], file=sys.stderr)
        return None
    if os.path.exists(out_path):
        return os.path.getsize(out_path)
    return os.path.getsize(source_path)


def _worker(src: str, out: str) -> int:
    import UnityPy
    try:                               # run as a script from spirit/server
        import bundle_trim
    except ImportError:
        from spirit.server import bundle_trim
    with open(src, "rb") as handle:
        env = UnityPy.load(handle.read())
    removed = bundle_trim.strip_orphans(env)
    if removed:
        print(f"{os.path.basename(out)}: {removed} template leftovers removed", file=sys.stderr)
    data = env.file.save(packer="lzma")
    if len(data) >= os.path.getsize(src):
        print(f"{os.path.basename(out)}: LZMA not smaller, skipped", file=sys.stderr)
        return 0
    tmp = f"{out}.{os.getpid()}.tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, out)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(_worker(sys.argv[1], sys.argv[2]))
