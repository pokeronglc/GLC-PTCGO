"""Removing textures from a card bundle safely (shared by the slim type-file
and LZMA workers).

Card set bundles are built from a template whose own artwork stays inside
every bundle although nothing exports it (about 7 MB of dead images per set,
copied again into every slim type file).  ``orphan_texture_ids`` finds those:
textures no AssetBundle container entry points at.  Approach adapted from the
upstream Spirit-PTCGO server (bundle_variants.py, Oct 2026).

Only "texture-only" bundles are touched: one serialized file, no external
references, only Texture2D + AssetBundle objects, no streamed texture data.
Anything else is left exactly as it is.
"""
import copy


def texture_bundle(env):
    """(AssetBundle object, parsed bundle, {path_id: texture}) for a
    texture-only bundle, else None (anything unexpected: leave it alone)."""
    try:
        return _texture_bundle(env)
    except Exception:
        return None


def _texture_bundle(env):
    if len(env.assets) != 1 or env.assets[0].externals:
        return None
    objects = list(env.objects)
    if any(o.type.name not in ("Texture2D", "AssetBundle") for o in objects):
        return None
    bundles = [o for o in objects if o.type.name == "AssetBundle"]
    if len(bundles) != 1:
        return None
    textures = {o.path_id: o for o in objects if o.type.name == "Texture2D"}
    for texture in textures.values():
        stream = getattr(texture.read(), "m_StreamData", None)
        if stream and getattr(stream, "path", None):
            return None
    return bundles[0], bundles[0].read(), textures


def orphan_texture_ids(bundle, textures):
    exported = {info.asset.m_PathID for _, info in bundle.m_Container}
    return set(textures) - exported


def drop_textures(env, reader, bundle, remove):
    """Remove textures and their container entries, then save the bundle with
    a matching preload table (texture exports have no dependencies)."""
    bundle.m_Container = [(n, i) for n, i in bundle.m_Container
                          if i.asset.m_PathID not in remove]
    preload = []
    for _, info in bundle.m_Container:
        info.preloadIndex = len(preload)
        info.preloadSize = 1
        preload.append(copy.copy(info.asset))
    bundle.m_PreloadTable = preload
    main = getattr(bundle, "m_MainAsset", None)
    if main is not None and main.asset.m_PathID in remove:
        main.asset.m_PathID = 0
        main.preloadIndex = main.preloadSize = 0
    reader.save_typetree(bundle)
    for pid in remove:
        del env.assets[0].objects[pid]


def strip_orphans(env):
    """Drop unexported template textures in place; returns how many."""
    found = texture_bundle(env)
    if found is None:
        return 0
    reader, bundle, textures = found
    orphans = orphan_texture_ids(bundle, textures)
    if orphans:
        drop_textures(env, reader, bundle, orphans)
    return len(orphans)
