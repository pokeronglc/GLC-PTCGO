"""Builds one slim per-type split bundle in a short-lived child process.

Usage: python typed_split_worker.py SRC OUT CAB_NAME DROP_JSON

Loads the full set bundle SRC, removes the card textures named in DROP_JSON
(and their container entries), gives the bundle its own CAB name so Unity
can load it beside the set's other type files, and writes OUT atomically.
Progress and a summary go to stderr (the server logs them).
"""
import json
import os
import sys

try:                                   # run as a script from spirit/server
    import bundle_trim
except ImportError:                    # imported as part of the package
    from spirit.server import bundle_trim


def _texture_name(obj):
    peek = getattr(obj, "peek_name", None)
    if peek is not None:
        try:
            return peek()
        except Exception:
            pass
    return obj.read().m_Name


def build(src, out, new_cab, drop):
    import UnityPy
    with open(src, "rb") as handle:
        env = UnityPy.load(handle.read())
    asset = env.assets[0]

    bundle_obj = next(obj for obj in asset.objects.values()
                      if obj.type.name == "AssetBundle")
    bundle = bundle_obj.read()

    textures = [(path_id, obj) for path_id, obj in asset.objects.items()
                if obj.type.name == "Texture2D"]
    dropped = {path_id for path_id, obj in textures if _texture_name(obj) in drop}

    # Texture-only bundles: also drop the card template's unexported artwork
    # and rebuild the preload table (bundle_trim).  Other bundles: old path.
    found = bundle_trim.texture_bundle(env)
    orphans = set()
    if found is not None:
        reader, parsed, texture_map = found
        orphans = bundle_trim.orphan_texture_ids(parsed, texture_map) - dropped
        bundle_trim.drop_textures(env, reader, parsed, dropped | orphans)
        preload_hits = 0
    else:
        preload_hits = sum(1 for pptr in getattr(bundle, "m_PreloadTable", []) or []
                           if getattr(pptr, "m_PathID", None) in dropped)
        for path_id in dropped:
            del asset.objects[path_id]
        bundle.m_Container = [(name, info) for name, info in bundle.m_Container
                              if info.asset.m_PathID not in dropped]
        bundle_obj.save_typetree(bundle)

    if hasattr(env, "file") and hasattr(env.file, "files"):
        for old_key in [k for k in env.file.files.keys() if k.startswith("CAB-")]:
            if "." in old_key:          # .resS / .resource streams keep their name
                continue
            env.file.files[new_cab] = env.file.files.pop(old_key)
    for serialized in env.assets:
        if getattr(serialized, "name", "").startswith("CAB-") and "." not in serialized.name:
            serialized.name = new_cab

    data = env.file.save(packer="lz4")
    tmp = f"{out}.{os.getpid()}.tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, out)
    print(f"{os.path.basename(out)}: kept {len(textures) - len(dropped) - len(orphans)} of "
          f"{len(textures)} textures ({len(orphans)} template leftovers removed), "
          f"{len(data) // 1024 // 1024} MB"
          + (f", {preload_hits} preload refs to dropped textures" if preload_hits else ""),
          file=sys.stderr)


def main(argv):
    if len(argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[4], "r", encoding="utf-8") as handle:
        drop = set(json.load(handle))
    build(argv[1], argv[2], argv[3], drop)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
