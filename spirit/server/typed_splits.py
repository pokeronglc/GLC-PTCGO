"""True per-type split bundles ("SV4_water" holds only SV4's Water cards).

The client asks for card art per set *and* type (``en_US_SV4_water``).  The
server used to answer every one of those with the whole set bundle under a
new name, so a player's card cache could hold each set up to 12 times
(~5.5 GB of sets -> 60+ GB worst case).  Here each type file keeps only the
cards that can be asked for from it, so the cache tops out near the size of
the sets themselves.

Which cards go in which type file.  The client's exact rule is not readable
(obfuscated), so every card goes in each file it could plausibly be
requested from:

* Pokemon: each of their types (dual types in both files)
* Trainers: ``trainer``; Items played as Pokemon (Fossils, dolls) also
  ``colorless``
* basic Energy: its type
* Special Energy, and anything that can't be placed: every file

Only textures named after a card of the set are ever dropped; anything else
in a bundle (template objects, unknown assets) stays in every file.

Off unless ``SPIRIT_TYPED_SPLITS=1``: build the files first with
``python -m spirit.tools.build_typed_splits``, then switch it on, so players
never wait on a build.  Turning it on also changes the manifest versions of
the type files, so clients fetch the small versions instead of keeping the
big copies they already have.
"""
from __future__ import annotations

import hashlib
import json
import re
import logging
import os
import subprocess
import sys
import tempfile
import threading
import zlib
from typing import Dict, Iterable, Optional, Set

from spirit.game.attributes import AttrID, CardType, PokemonTypes

TYPE_SUFFIXES = {
    PokemonTypes.COLORLESS.value: "colorless",
    PokemonTypes.DARKNESS.value: "darkness",
    PokemonTypes.DRAGON.value: "dragon",
    PokemonTypes.FAIRY.value: "fairy",
    PokemonTypes.FIGHTING.value: "fighting",
    PokemonTypes.FIRE.value: "fire",
    PokemonTypes.GRASS.value: "grass",
    PokemonTypes.LIGHTNING.value: "lightning",
    PokemonTypes.METAL.value: "metal",
    PokemonTypes.PSYCHIC.value: "psychic",
    PokemonTypes.WATER.value: "water",
}
ALL_SUFFIXES = frozenset(list(TYPE_SUFFIXES.values()) + ["trainer"])

# Bump when the contents of the slim files change: new cache file names on the
# server and a new cache identity for clients.
#   1: per-type files
#   2: card template leftovers removed; foil / energy-icon art follows its card
REVISION = 2

WORKER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "typed_split_worker.py")


def enabled() -> bool:
    return os.environ.get("SPIRIT_TYPED_SPLITS", "0") == "1"


def manifest_version(base_version: int, virtual_name: str) -> int:
    """A different cache identity for the slim type file, so clients swap
    their big full-set copy for it instead of keeping the old one."""
    if not enabled():
        return base_version
    # The tag changes whenever the files' contents change (REVISION), so
    # clients fetch the new files instead of keeping their old copies.
    value = zlib.crc32(f"{base_version}:typed{REVISION}:{virtual_name}".encode()) & 0x7FFFFFFF
    return value or 1


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def suffixes_for(card_type, pokemon_types, special_energy=False,
                 plays_as_pokemon=False) -> frozenset:
    """Type files a card can be requested from (see module docstring)."""
    types = {TYPE_SUFFIXES[t] for t in _as_list(pokemon_types) if t in TYPE_SUFFIXES}
    if card_type == CardType.POKEMON.value:
        return frozenset(types) or ALL_SUFFIXES
    if card_type == CardType.TRAINER.value:
        return frozenset({"trainer", "colorless"} if plays_as_pokemon else {"trainer"})
    if card_type == CardType.ENERGY.value and not special_energy:
        return frozenset(types) or ALL_SUFFIXES
    return ALL_SUFFIXES


_INDEX: Optional[Dict[str, Dict[str, Set[str]]]] = None
_INDEX_LOCK = threading.Lock()


def _build_index() -> Dict[str, Dict[str, Set[str]]]:
    """{set_code: {texture_name: {suffix, ...}}} over every loaded card."""
    from spirit.game.data_utils import def_for
    from spirit.game.scripts.cards import loader
    if not loader.cards:
        loader.load_all()
    index: Dict[str, Dict[str, Set[str]]] = {}
    for model in loader.cards:
        definition = def_for(model.guid)
        if definition is None:
            continue
        name = model.get_attribute_value(AttrID.IMAGE_URL)
        if not name:
            continue
        suffixes = suffixes_for(
            model.get_attribute_value(AttrID.CARD_TYPE),
            model.get_attribute_value(AttrID.POKEMON_TYPES),
            special_energy=bool(model.get_attribute_value(AttrID.IS_SPECIAL_ENERGY)),
            plays_as_pokemon=bool(getattr(definition, "plays_as_pokemon", False)),
        )
        names = [str(name), f"{name}_energypip", f"{name}_toolpip",
                 f"{name}_energyicon", f"foil_{name}"]
        texture = getattr(definition, "vunion_texture", None)
        if texture:
            names.append(str(texture))
        bucket = index.setdefault(definition.set_code, {})
        for texture_name in names:
            bucket.setdefault(texture_name, set()).update(suffixes)
    return index


def drop_names(set_code: str, suffix: str) -> Optional[Set[str]]:
    """Card textures to leave OUT of ``{set_code}_{suffix}``; None when the
    set or suffix isn't one this module handles (callers fall back)."""
    global _INDEX
    if suffix not in ALL_SUFFIXES:
        return None
    with _INDEX_LOCK:
        if _INDEX is None:
            _INDEX = _build_index()
        cards = _INDEX.get(set_code)
    if not cards:
        return None
    return {name for name, suffixes in cards.items() if suffix not in suffixes}


def split_parts(clean_base: str):
    """'SV4_water' -> ('SV4', 'water'); None when there is no type suffix."""
    head, _, tail = clean_base.rpartition("_")
    if not head or tail.lower() not in ALL_SUFFIXES:
        return None
    return head, tail.lower()


def cache_path(cache_dir: str, clean_base: str, source_path: str,
               drop: Iterable[str]) -> str:
    st = os.stat(source_path)
    key = json.dumps([REVISION, os.path.abspath(source_path), st.st_size, st.st_mtime_ns,
                      sorted(drop)])
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    return os.path.join(cache_dir, f"typed-{clean_base}-{digest}.unity3d")


def cab_name(clean_base: str) -> str:
    return f"CAB-{hashlib.md5(clean_base.encode('utf-8')).hexdigest()}"


def build(source_path: str, out_path: str, clean_base: str, drop: Iterable[str],
          timeout: int = 600) -> bool:
    """Write the slim type file in a child process (UnityPy's peak memory is
    returned to the OS when it exits).  True on success."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     dir=os.path.dirname(out_path)) as handle:
        json.dump(sorted(drop), handle)
        drop_file = handle.name
    try:
        result = subprocess.run(
            [sys.executable, WORKER_SCRIPT, source_path, out_path,
             cab_name(clean_base), drop_file],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        logging.error(f"[TypedSplit] Build timed out for {clean_base}")
        return False
    finally:
        try:
            os.remove(drop_file)
        except OSError:
            pass
    for line in (result.stderr or "").splitlines():
        if line.strip():
            logging.info(f"[TypedSplit] [worker] {line}")
    if result.returncode != 0 or not os.path.exists(out_path):
        logging.error(f"[TypedSplit] Build failed for {clean_base} (exit {result.returncode})")
        return False
    return True


# --- Manifest routing ------------------------------------------------------
# The manifest tells the client which bundle holds each card picture.  Listing
# a card under its type file (instead of the whole set) means the client only
# ever downloads that small file for it.  Approach adapted from the upstream
# Spirit-PTCGO server (manifest asset routing, Oct 2026).

def _routing_setting() -> str:
    return os.environ.get("SPIRIT_ROUTE_CARDS", "0").strip()


def routing_enabled(set_code: Optional[str] = None) -> bool:
    """SPIRIT_ROUTE_CARDS=1 routes every set; a comma list (e.g. "SM11,ME2")
    routes only those sets (for testing); 0 / unset routes none."""
    value = _routing_setting()
    if value in ("", "0"):
        return False
    if value == "1":
        return True
    if set_code is None:
        return True
    return set_code.lower() in {v.strip().lower() for v in value.split(",") if v.strip()}


def route_kind(suffixes) -> str:
    """The one type file a card is listed under; always a file that holds it."""
    suffixes = set(suffixes)
    if "trainer" in suffixes:
        return "trainer"
    return sorted(suffixes)[0]


def card_routes(set_code: str) -> Dict[int, str]:
    """{card number: type file suffix} for a set's numbered card pictures."""
    global _INDEX
    with _INDEX_LOCK:
        if _INDEX is None:
            _INDEX = _build_index()
        cards = _INDEX.get(set_code) or {}
    return {int(name): route_kind(suffixes)
            for name, suffixes in cards.items() if name.isdigit() and suffixes}


def asset_number(name: str, set_code: str) -> Optional[int]:
    """Card number a manifest asset name refers to ('094', 'SM11/94',
    'SM11_foil_094', '094_energypip' ...), or None for anything else."""
    name = name.lower()
    for prefix in (set_code.lower() + "/", set_code.lower() + "_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    match = re.fullmatch(r"(?:foil_)?(\d+)(?:_energypip|_energyicon|_toolpip)?", name)
    return int(match.group(1)) if match else None
