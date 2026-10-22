"""Check the slim type files and LZMA copy of a set before players get them.

    cd /opt/glc-ptcgo && venv/bin/python -m spirit.tools.check_card_files SM11 [ME2 ...]
    cd /opt/glc-ptcgo && venv/bin/python -m spirit.tools.check_card_files --all

For each set it reports:
  * template leftovers in the source bundle (unexported textures);
  * every slim type file: texture count, size, and whether its container and
    preload table point only at textures that exist;
  * ROUTING: every card picture the manifest would list under a type file is
    really inside that file (the key safety check -- a miss means that card
    would show "Loading");
  * the LZMA copy: loads, has no leftovers, and holds every card picture.
Exit code 1 if anything is wrong.
"""
from __future__ import annotations

import argparse
import os
import sys


def _load(path):
    import UnityPy
    with open(path, "rb") as handle:
        return UnityPy.load(handle.read())


def _summary(env):
    """(exported texture names, template leftover ids, problems).  Only
    exported textures matter: the client can load nothing else."""
    from spirit.server import bundle_trim
    objects = {o.path_id: o for o in env.objects}
    bundles = [o for o in objects.values() if o.type.name == "AssetBundle"]
    textures = {pid: o for pid, o in objects.items() if o.type.name == "Texture2D"}
    problems, orphans, exported_names = [], set(), set()
    if len(bundles) != 1:
        problems.append(f"{len(bundles)} AssetBundle objects")
        return exported_names, orphans, problems
    bundle = bundles[0].read()
    exported = {info.asset.m_PathID for _, info in bundle.m_Container}
    missing = {pid for pid in exported if pid and pid not in objects}
    if missing:
        problems.append(f"{len(missing)} container entries point at missing objects")
    preload = getattr(bundle, "m_PreloadTable", []) or []
    bad_preload = [p for p in preload if getattr(p, "m_PathID", 0) and p.m_PathID not in objects]
    if bad_preload:
        problems.append(f"{len(bad_preload)} preload entries point at missing objects")
    for pid in exported & set(textures):
        try:
            exported_names.add(textures[pid].read().m_Name)
        except Exception:
            problems.append(f"texture {pid} unreadable")
    if bundle_trim.texture_bundle(env) is not None:
        orphans = set(textures) - exported
    return exported_names, orphans, problems


def check_set(set_code, http, typed_splits, lzma_sets):
    from spirit.tools.build_typed_splits import _set_bundles
    sources = _set_bundles(http.ASSET_PATHS)
    src = sources.get(set_code)
    if src is None:
        print(f"{set_code}: no set bundle found")
        return False
    ok = True
    src_names, src_orphans, src_problems = _summary(_load(src))
    print(f"\n== {set_code}: source {os.path.getsize(src) / 1e6:.0f} MB, "
          f"{len(src_names)} exported pictures, {len(src_orphans)} template leftovers")

    routes = typed_splits.card_routes(set_code)
    files = {}
    for suffix in sorted(typed_splits.ALL_SUFFIXES):
        clean_base = f"{set_code}_{suffix}"
        drop = typed_splits.drop_names(set_code, suffix)
        path = typed_splits.cache_path(http.VIRTUAL_SPLIT_CACHE_DIR, clean_base, src, drop)
        if not os.path.exists(path):
            print(f"  {suffix:10s} NOT BUILT")
            ok = False
            continue
        names, orphans, problems = _summary(_load(path))
        files[suffix] = names
        flag = "" if not (orphans or problems) else "  <-- " + "; ".join(
            problems + ([f"{len(orphans)} leftovers"] if orphans else []))
        if orphans or problems:
            ok = False
        print(f"  {suffix:10s} {os.path.getsize(path) / 1e6:6.1f} MB  {len(names):4d} pictures{flag}")

    # Routing safety: the card's own picture must be in the file it is listed under.
    misses = []
    for number, kind in sorted(routes.items()):
        if kind not in files:
            continue
        candidates = {str(number), f"{number:03d}"}
        if not (candidates & src_names):
            continue                      # card has no art in this bundle at all
        if not (candidates & files[kind]):
            misses.append(f"{number:03d}->{kind}")
    print(f"  routing: {len(routes)} cards routed, {len(misses)} missing from their file"
          + (f": {', '.join(misses[:12])}" if misses else ""))
    ok = ok and not misses

    if True:   # LZMA copy (checked even before the switch is on)
        copy = lzma_sets.existing_copy(lzma_sets.cache_dir(http.VIRTUAL_SPLIT_CACHE_DIR), src)
        if copy is None:
            print("  lzma copy: NOT BUILT")
            ok = False
        else:
            names, orphans, problems = _summary(_load(copy))
            lost = src_names - names
            card_lost = {n for n in lost if n.isdigit()}
            print(f"  lzma copy: {os.path.getsize(copy) / 1e6:.0f} MB, {len(names)} pictures, "
                  f"{len(orphans)} leftovers, {len(card_lost)} card pictures missing"
                  + (f"  <-- {'; '.join(problems)}" if problems else ""))
            ok = ok and not (orphans or problems or card_lost)
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("sets", nargs="*")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    from spirit.tools.build_lzma_sets import _load_service_env
    _load_service_env()
    from spirit.server import http_server as http, typed_splits, lzma_sets
    from spirit.tools.build_typed_splits import _set_bundles
    sets = sorted(_set_bundles(http.ASSET_PATHS)) if args.all else args.sets
    if not sets:
        parser.error("name at least one set, or --all")
    results = {s: check_set(s, http, typed_splits, lzma_sets) for s in sets}
    bad = [s for s, good in results.items() if not good]
    print(f"\n{len(results) - len(bad)} of {len(results)} sets OK" + (f"; problems: {', '.join(bad)}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
