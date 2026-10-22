"""Pre-build every slim per-type card file before switching them on.

    cd /opt/glc-ptcgo && nice -n 19 venv/bin/python -m spirit.tools.build_typed_splits

Builds ``{SET}_{type}`` for every set bundle and every type into the split
cache (the same files the server would build on first request), one at a
time.  Already-built files are skipped, so it can be stopped and re-run.
Prints a running count and a final size summary.

    --only SV4        just one set (a quick test)
    --check           only report how many files exist / are missing
    --prune           delete slim files the current rules no longer use
                      (old versions).  Run only AFTER restarting the game
                      server on the new code -- before that it still serves them.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from spirit.server import typed_splits


def _set_bundles(bundle_dirs):
    """{set_code: __data path} for every card set bundle with known cards."""
    found = {}
    for base in bundle_dirs:
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            if not entry.startswith("en_US_"):
                continue
            set_code = entry[len("en_US_"):]
            if set_code in found or typed_splits.drop_names(set_code, "trainer") is None:
                continue
            for root, _, files in os.walk(os.path.join(base, entry)):
                if "__data" in files:
                    found[set_code] = os.path.join(root, "__data")
                    break
    return found


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--only")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--prune", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    from spirit.tools.build_lzma_sets import _load_service_env
    _load_service_env()      # same cache folder as the running server
    from spirit.server import http_server as http
    sets = _set_bundles(http.ASSET_PATHS)
    if args.only:
        sets = {k: v for k, v in sets.items() if k == args.only}
    jobs = []
    for set_code, src in sorted(sets.items()):
        for suffix in sorted(typed_splits.ALL_SUFFIXES):
            clean_base = f"{set_code}_{suffix}"
            drop = typed_splits.drop_names(set_code, suffix)
            out = typed_splits.cache_path(http.VIRTUAL_SPLIT_CACHE_DIR, clean_base, src, drop)
            jobs.append((clean_base, src, drop, out))

    missing = [job for job in jobs if not os.path.exists(job[3])]
    print(f"{len(sets)} sets, {len(jobs)} type files, {len(jobs) - len(missing)} built, "
          f"{len(missing)} to build.  Cache: {http.VIRTUAL_SPLIT_CACHE_DIR}")
    if args.prune:
        keep = {os.path.basename(job[3]) for job in jobs}
        cache = http.VIRTUAL_SPLIT_CACHE_DIR
        old = [f for f in os.listdir(cache)
               if f.startswith("typed-") and f.endswith(".unity3d") and f not in keep]
        if args.only:
            old = [f for f in old if f.startswith(f"typed-{args.only}_")]
        freed = 0
        for f in old:
            path = os.path.join(cache, f)
            freed += os.path.getsize(path)
            os.remove(path)
        print(f"Pruned {len(old)} old slim files, freed {freed / 1e9:.2f} GB.")
        return 0
    if args.check:
        return 0

    started = time.time()
    failed = 0
    for done, (clean_base, src, drop, out) in enumerate(missing, 1):
        t0 = time.time()
        ok = typed_splits.build(src, out, clean_base, drop,
                                timeout=http.VIRTUAL_SPLIT_BUILD_TIMEOUT)
        failed += not ok
        elapsed = time.time() - started
        left = (elapsed / done) * (len(missing) - done)
        print(f"[{done}/{len(missing)}] {clean_base}: {'ok' if ok else 'FAILED'} "
              f"({time.time() - t0:.1f}s, ~{left / 60:.0f} min left)", flush=True)

    total = sum(os.path.getsize(job[3]) for job in jobs if os.path.exists(job[3]))
    print(f"Done. {len(jobs) - failed} type files, {total / 1e9:.2f} GB total"
          + (f", {failed} FAILED (see messages above)" if failed else "") + ".")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
