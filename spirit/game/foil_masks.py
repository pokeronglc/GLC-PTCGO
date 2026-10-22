"""Keep the client from drawing a card it has no foil mask for.

Secret Rares and Amazing Rares use the "SwSecret" foil with a second
"FlatSilver" layer.  The client renders that treatment through per-card mask
textures (the {SET}_wp_std_Foil2 / wp_secondary bundles).  This server never
synthesizes masks, so when a print's mask PNGs were never installed the client
drew the whole card transparent: a blank Card Info window and see-through
cards in play (Amazing Rayquaza/Jirachi, gold Turbo Patch).

When a print needs masks that are not on disk, send it as a normal non-foil
card instead.  Installing the masks later restores the foil automatically.
Plain illustration-window holos are unaffected: they render without a mask.
"""
import json
import os

from spirit.game.attributes import AttrID, FoilEffects, FoilMasks

CARDS_IMG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "assets", "cards")

_FOIL_ATTRS = (AttrID.FOIL_MASK, AttrID.FOIL_EFFECT,
               AttrID.FOIL_EFFECTS, AttrID.FOIL_INTENSITY)


def _value(attrs, attr_id, default=None):
    entry = attrs.get(str(attr_id.value))
    return entry.get("value", default) if isinstance(entry, dict) else default


def required_mask_suffixes(attrs):
    """Mask PNG suffixes this foil treatment cannot render without."""
    effect = _value(attrs, AttrID.FOIL_EFFECT)
    mask = _value(attrs, AttrID.FOIL_MASK)
    extra = _value(attrs, AttrID.FOIL_EFFECTS, "[]")
    if isinstance(extra, str):
        try:
            extra = json.loads(extra or "[]")
        except ValueError:
            extra = []
    needed = []
    if effect is not None and int(effect) == FoilEffects.SWSECRET.value:
        if mask is not None and int(mask) == FoilMasks.REVERSE.value:
            needed.append("_foil_ph")
        else:
            needed.append("_foil")
    if extra:
        needed.append("_foil_secondary")
    return needed


def strip_unrenderable_foil(attrs, script_path, scripts_dir, image_dir=CARDS_IMG_DIR):
    """Remove the foil attributes when a required mask is missing.

    Returns True when the foil was removed."""
    needed = required_mask_suffixes(attrs)
    if not needed or not script_path:
        return False
    rel_dir = os.path.dirname(os.path.relpath(script_path, scripts_dir))
    base = os.path.splitext(os.path.basename(script_path))[0]
    if all(os.path.exists(os.path.join(image_dir, rel_dir, base + suffix + ".png"))
           for suffix in needed):
        return False
    for attr in _FOIL_ATTRS:
        attrs.pop(str(attr.value), None)
    return True
