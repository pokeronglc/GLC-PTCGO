"""Pre-build LZMA copies of every whole-set card bundle (see lzma_sets.py).

    cd /opt/glc-ptcgo && nohup nice -n 19 venv/bin/python -m spirit.tools.build_lzma_sets > /root/lzma-build.log 2>&1 &

One set at a time (~2 minutes each).  Already-built sets are skipped, so it
can be stopped and re-run.  Safe while players are on: the server only serves
a copy once SPIRIT_LZMA_SETS=1 and the copy exists.

    --only SM11       just one set
    --check           only report how many copies exist / are missing
    --prune           delete copies the current version no longer uses (run
                      after restarting the server on the new code)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from spirit.server import lzma_sets


def _set_bundles(bundle_dirs):
    """{set_code: __data path} for every en_US_* bundle folder."""
    found = {}
    for base in bundle_dirs:
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            if not entry.startswith("en_US_"):
                continue
            code = entry[len("en_US_"):]
            if code in found:
                continue
            for root, _, files in os.walk(os.path.join(base, entry)):
                if "__data" in files:
                    found[code] = os.path.join(root, "__data")
                    break
    return found


def _load_service_env(path="/etc/systemd/system/glc.service.d"):
    """Pick up the game server's own Environment= settings (split cache
    location etc.) so copies land where the server looks for them, even
    when run from a plain shell."""
    if not os.path.isdir(path):
        return
    for name in sorted(os.listdir(path)):
        if not name.endswith(".conf"):
            continue
        try:
            lines = open(os.path.join(path, name), encoding="utf-8").read().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line.startswith("Environment="):
                continue
            for item in line[len("Environment="):].split():
                key, sep, value = item.strip('"').partition("=")
                if sep and key not in os.environ:
                    os.environ[key] = value


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--only")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--min-mb", type=float, default=5.0,
                        help="skip bundles smaller than this (not worth it)")
    args = parser.parse_args(argv)

    _load_service_env()
    from spirit.server import http_server as http
    out_dir = lzma_sets.cache_dir(http.VIRTUAL_SPLIT_CACHE_DIR)
    sets = _set_bundles(http.ASSET_PATHS)
    if args.only:
        sets = {k: v for k, v in sets.items() if k == args.only}
    sets = {k: v for k, v in sets.items() if os.path.getsize(v) >= args.min_mb * 1e6}
    missing = {k: v for k, v in sets.items() if lzma_sets.existing_copy(out_dir, v) is None}
    print(f"{len(sets)} set bundles, {len(sets) - len(missing)} have LZMA copies, "
          f"{len(missing)} to build.  Copies: {out_dir}", flush=True)
    if args.prune:
        keep = {os.path.basename(lzma_sets.copy_path(out_dir, v)) for v in sets.values()}
        old = [f for f in (os.listdir(out_dir) if os.path.isdir(out_dir) else [])
               if f.startswith("lzma-") and f.endswith(".unity3d") and f not in keep]
        freed = sum(os.path.getsize(os.path.join(out_dir, f)) for f in old)
        for f in old:
            os.remove(os.path.join(out_dir, f))
        print(f"Pruned {len(old)} old LZMA copies, freed {freed / 1e9:.2f} GB.")
        return 0
    if args.check:
        return 0

    started = time.time()
    before = after = 0
    failed = 0
    for done, (code, src) in enumerate(sorted(missing.items()), 1):
        t0 = time.time()
        size = lzma_sets.build(src, lzma_sets.copy_path(out_dir, src))
        src_size = os.path.getsize(src)
        if size is None:
            failed += 1
            status = "FAILED"
        else:
            before += src_size
            after += size
            status = f"{src_size / 1e6:.0f} -> {size / 1e6:.0f} MB"
        left = (time.time() - started) / done * (len(missing) - done)
        print(f"[{done}/{len(missing)}] {code}: {status} ({time.time() - t0:.0f}s, "
              f"~{left / 60:.0f} min left)", flush=True)

    print(f"Done. {before / 1e9:.2f} GB -> {after / 1e9:.2f} GB"
          + (f", {failed} FAILED" if failed else "") + ".", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
