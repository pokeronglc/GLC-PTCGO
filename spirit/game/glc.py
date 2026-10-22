"""Gym Leader Challenge (GLC) card-pool rules.

This server runs a single play format: Gym Leader Challenge.  The client
still calls it "Unlimited" on the wire (the format GUID and wire name are
hashed by the client), but every card that is not playable in GLC is removed
from the catalog, so "Unlimited" and "Gym Leader Challenge" mean the same
card pool here.

GLC card pool (https://gymleaderchallenge.com):
  * Black & White onward (the Expanded card pool).  HeartGold & SoulSilver era
    sets are therefore excluded.
  * No cards with a Rule Box: Pokémon-EX, Pokémon-GX (incl. TAG TEAM),
    Pokémon V / VMAX / VSTAR / V-UNION, Pokémon ex (incl. Tera and Mega ex),
    Mega Evolution Pokémon-EX, Pokémon BREAK, Prism Star cards and Radiant
    Pokémon.
  * No ACE SPEC cards.
  * Plus the GLC ban list below.

The deck-building rules (singleton, one Pokémon type) are at the bottom of
this module; spirit/game/rules.py applies them.

To follow a future GLC ban-list update, edit BANNED_NAMES / BANNED_PRINTS
and run ``python -m spirit.tools.prune_to_glc`` again.
"""
import json
import re
from typing import Optional

# HeartGold & SoulSilver era: older than Black & White, never GLC-legal.
EXCLUDED_SETS = frozenset({
    "HGSS1", "HGSS2", "HGSS3", "HGSS4", "COL", "Promo_HGSS",
})

# Subtypes that mean a Pokémon has a Rule Box.  ("MEGA" is only checked on
# Pokémon: one Trainer script, TM Machine, carries a stray MEGA tag.)
RULE_BOX_POKEMON_SUBTYPES = frozenset({
    "EX", "GX", "TAG TEAM", "V", "VMAX", "VSTAR", "V-UNION", "ex", "Tera",
    "MEGA", "SV_Mega", "BREAK", "LEGEND", "Prism Star", "Radiant",
})

# Subtypes that exclude any card, Trainer and Energy included.
EXCLUDED_ANY_SUBTYPES = frozenset({"ACE SPEC", "Prism Star"})

# GLC ban list -- Trainer / Energy cards are banned under every printing.
BANNED_NAMES = frozenset({
    "Double Colorless Energy",
    "Dimension Valley",
    "Lysandre's Trump Card",
    "Forest of Giant Plants",
    "Hiker",
    "Chip-Chip Ice Axe",
    "Pokémon Research Lab",
    "Twin Energy",
})

# GLC ban list -- Pokémon are banned as specific cards.  Identical reprints
# (same name and attacks) are banned with them.  (set code, collector number)
BANNED_PRINTS = frozenset({
    ("SL", 45),        # Marshadow (Shining Legends 45)
    ("Promo_SM", 85),  # Marshadow (SM Black Star Promo 85, same card)
    ("SM5", 114),      # Oranguru (Ultra Prism 114)
    ("SM12", 83),      # Duskull (Cosmic Eclipse 83)
    ("SWSH4", 50),     # Raikou (Vivid Voltage 50)
    ("SWSH45", 21),    # Kyogre (Shining Fates 21)
})


def _is_pokemon(card_def) -> bool:
    from spirit.game.data_utils import PokemonCardDef
    return isinstance(card_def, PokemonCardDef)


def exclusion_reason(card_def) -> Optional[str]:
    """Why a card is not GLC-playable, or None when it is legal."""
    set_code = str(getattr(card_def, "set_code", "") or "")
    if set_code in EXCLUDED_SETS:
        return "pre-Black & White set"

    subtypes = set(getattr(card_def, "subtypes", None) or [])
    if subtypes & EXCLUDED_ANY_SUBTYPES:
        return "ACE SPEC / Prism Star"
    if _is_pokemon(card_def) and subtypes & RULE_BOX_POKEMON_SUBTYPES:
        return "Rule Box Pokémon"

    name = getattr(card_def, "display_name", None) or ""
    if name in BANNED_NAMES:
        return "GLC ban list"
    try:
        number = int(getattr(card_def, "collector_number", None))
    except (TypeError, ValueError):
        number = None
    if (set_code, number) in BANNED_PRINTS:
        return "GLC ban list"
    return None


def is_glc_legal(card_def) -> bool:
    return exclusion_reason(card_def) is None


# ---------------------------------------------------------------------------
# GLC deck-building rules (checked by spirit/game/rules.py for every format
# while config.GLC_ONLY is on).
# ---------------------------------------------------------------------------

# Printed name variants that count as the same card name.
_NAME_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")   # "Professor's Research (Professor Turo)"
SAME_NAME_ALIASES = {
    "Lysandre": "Boss's Orders",   # same card, reprinted under a new name
}


def singleton_name(display_name: str) -> str:
    name = _NAME_SUFFIX.sub("", display_name or "").strip()
    return SAME_NAME_ALIASES.get(name, name)


def _pokemon_types(card):
    from spirit.game.attributes import AttrID
    value = card.get_attribute_value(AttrID.POKEMON_TYPES)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = [value]
    if isinstance(value, (int, str)):
        value = [value]
    return {int(v) for v in (value or [])}


def deck_rule_failures(cards, display_name, is_basic_energy):
    """GLC deck rules -> [(failure_type, message, offending GUIDs)].

    * Singleton: one copy of each card name, except basic Energy.
    * One Pokémon type: every Pokémon must share a type (a dual-type
      Pokémon fits a deck of either of its types).
    """
    from spirit.game.attributes import AttrID, CardType, PokemonTypes

    failures = []

    by_name = {}
    for card in cards:
        if is_basic_energy(card):
            continue
        by_name.setdefault(singleton_name(display_name(card)), []).append(card.guid.lower())
    duplicates = {name: guids for name, guids in by_name.items() if len(guids) > 1}
    if duplicates:
        failures.append((
            "MaxDuplicates",
            "Gym Leader Challenge: only one copy of each card is allowed "
            "(basic Energy excepted): " + ", ".join(sorted(duplicates)) + ".",
            sorted({g for guids in duplicates.values() for g in guids}),
        ))

    pokemon = [c for c in cards
               if c.get_attribute_value(AttrID.CARD_TYPE) == CardType.POKEMON.value]
    shared = None
    for card in pokemon:
        types = _pokemon_types(card)
        shared = types if shared is None else shared & types
    if pokemon and not shared:
        counts = {}
        for card in pokemon:
            for t in _pokemon_types(card):
                counts[t] = counts.get(t, 0) + 1
        main = max(counts, key=counts.get) if counts else None
        offenders = sorted({c.guid.lower() for c in pokemon
                            if main not in _pokemon_types(c)})
        try:
            main_name = PokemonTypes(main).name.title()
        except ValueError:
            main_name = "one"
        failures.append((
            "MustNotContain",
            "Gym Leader Challenge: all Pokémon must share one type "
            f"(this deck is mostly {main_name}).",
            offenders,
        ))
    return failures


# ---------------------------------------------------------------------------
# The Salvatore ruling (GLC, August 2026): the format is public knowledge.
# Once your visible Pokémon fix your deck's type, you can't use a search that
# could only find Pokémon of a type your deck can't contain -- e.g. a Psychic
# deck can't use the opponent's Brooklet Hill.
# https://gymleaderchallenge.com/faq
# ---------------------------------------------------------------------------

def _def_types(card_def):
    from spirit.game.attributes import AttrID
    raw = (getattr(card_def, "extra_attributes", {}) or {}).get(str(AttrID.POKEMON_TYPES.value))
    value = raw.get("value") if isinstance(raw, dict) else raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return set()
    if isinstance(value, int):
        value = [value]
    return {int(v) for v in (value or [])}


def _def_is_basic(card_def):
    from spirit.game.attributes import AttrID, PokemonStage
    raw = (getattr(card_def, "extra_attributes", {}) or {}).get(str(AttrID.STAGE.value))
    value = raw.get("value") if isinstance(raw, dict) else raw
    return value == PokemonStage.BASIC.value


def _is_real_pokemon_def(card_def):
    from spirit.game.data_utils import PokemonCardDef
    return isinstance(card_def, PokemonCardDef)


def _stadium_type_search(text):
    """(types, basic_only, evolution_only) for a typed Pokémon Stadium search."""
    from spirit.game.attributes import PokemonTypes as T
    t = " ".join((text or "").casefold().split())
    if "search their deck for a basic water pokémon or basic fighting pokémon" in t:
        return {T.WATER.value, T.FIGHTING.value}, True, False      # Brooklet Hill
    if "search their deck for a basic lightning pokémon or basic dragon pokémon" in t:
        return {T.LIGHTNING.value, T.DRAGON.value}, True, False    # Stormy Mountains
    if "search their deck for an evolution grass pokémon" in t:
        return {T.GRASS.value}, False, True                        # Turffield Stadium
    return None


def _visible_cards(board, player_id):
    """The player's cards in public zones: in play (whole stacks), discard,
    Lost Zone and face-up Prize cards."""
    def walk(entity):
        yield entity
        for child in getattr(entity, "children", None) or []:
            yield from walk(child)
    for area_name in ("activePokemonArea", "bench", "discard", "lostZone"):
        area = board.find_player_area(player_id, area_name)
        for child in (area.children if area else []):
            yield from walk(child)
    prizes = board.find_player_area(player_id, "prizePile")
    for prize in (prizes.children if prizes else []):
        if getattr(prize, "publicly_revealed", False):
            yield from walk(prize)


def stadium_search_is_impossible(board, player_id, stadium_def) -> bool:
    """True when the Salvatore ruling forbids this player using the Stadium."""
    from spirit.game.data_utils import CARD_DEFS_BY_GUID, def_for
    text = " ".join(filter(None, [
        getattr(getattr(stadium_def, "ability", None), "game_text", None),
        getattr(stadium_def, "game_text", None)]))
    search = _stadium_type_search(text)
    if search is None:
        return False
    wanted_types, basic_only, evolution_only = search

    deck_types, visible_names = public_deck_knowledge(board, player_id)
    if deck_types is None:
        return False           # nothing typed visible yet: anything is possible

    for card_def in CARD_DEFS_BY_GUID.values():
        if not _is_real_pokemon_def(card_def) or not is_glc_legal(card_def):
            continue
        types = _def_types(card_def)
        if not (types & wanted_types) or not (types & deck_types):
            continue
        basic = _def_is_basic(card_def)
        if (basic_only and not basic) or (evolution_only and basic):
            continue
        if singleton_name(card_def.display_name or "") in visible_names:
            continue           # singleton: its only copy is already public
        return False
    return True


def public_deck_knowledge(board, player_id):
    """(types every visible Pokémon shares or None, singleton names already public)."""
    from spirit.game.data_utils import def_for
    deck_types = None
    visible_names = set()
    for card in _visible_cards(board, player_id):
        card_def = def_for(getattr(card, "archetype_id", None))
        if card_def is None:
            continue
        visible_names.add(singleton_name(card_def.display_name or ""))
        if not _is_real_pokemon_def(card_def):
            continue           # Dolls and Fossils don't reveal a type
        types = _def_types(card_def)
        if types:
            deck_types = types if deck_types is None else deck_types & types
    return deck_types, visible_names


_EVOLVES_FROM_INDEX = {}
_EVOLVES_FROM_INDEX_SIZE = -1


def _evolutions_of(logic_name):
    """GLC-legal Pokémon card defs whose EVOLUTION_LOGIC_FROM is logic_name."""
    global _EVOLVES_FROM_INDEX_SIZE
    from spirit.game.attributes import AttrID
    from spirit.game.data_utils import CARD_DEFS_BY_GUID, _string_attr
    if _EVOLVES_FROM_INDEX_SIZE != len(CARD_DEFS_BY_GUID):
        _EVOLVES_FROM_INDEX.clear()
        for card_def in CARD_DEFS_BY_GUID.values():
            if not _is_real_pokemon_def(card_def) or not is_glc_legal(card_def):
                continue
            source = _string_attr(card_def, AttrID.EVOLUTION_LOGIC_FROM)
            if source:
                _EVOLVES_FROM_INDEX.setdefault(source, []).append(card_def)
        _EVOLVES_FROM_INDEX_SIZE = len(CARD_DEFS_BY_GUID)
    return _EVOLVES_FROM_INDEX.get(logic_name, [])


def _has_ability(card_def):
    from spirit.game.data_utils import Attack
    return any(not isinstance(a, Attack) and not getattr(a, "is_rule_action", False)
               for a in (getattr(card_def, "abilities", None) or []))


def evolution_search_allowed(board, player_id, targets, *, no_abilities=False) -> bool:
    """Salvatore ruling for Evosoda, Wally, Salvatore and TM Evolution: at least
    one of `targets` must have an evolution the deck could still contain.
    Always True outside GLC mode."""
    from spirit import config
    if not config.GLC_ONLY:
        return True
    from spirit.game.attributes import AttrID
    deck_types, visible_names = public_deck_knowledge(board, player_id)
    for pokemon in targets:
        for card_def in _evolutions_of(pokemon.get_attribute(AttrID.EVOLUTION_LOGIC_NAME)):
            if deck_types is not None and not (_def_types(card_def) & deck_types):
                continue
            if singleton_name(card_def.display_name or "") in visible_names:
                continue       # singleton: its only copy is already public
            if no_abilities and _has_ability(card_def):
                continue
            return True
    return False
