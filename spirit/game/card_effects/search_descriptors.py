"""Narrow search descriptors shared by SM Trainer and Ability searches."""
import re
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for, subtypes_for
from spirit.game.session.effects import is_pokemon_card, is_basic_pokemon, is_energy_card, is_stadium_card, is_supporter_card, is_pokemon_tool
from spirit.game.card_effects.pokemon import energy_provides_type

TYPES = "grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy|dragon|colorless"


def specific_search_predicate(text):
    text = text.casefold()
    descriptor = text.split("search your deck for ", 1)[-1].split(", reveal", 1)[0].split(".", 1)[0]
    subtypes = lambda c: {s.casefold() for s in (subtypes_for(c.archetype_id) or [])}
    name_contains = re.search(r'pokémon that (?:has|have) "([^"]+)" in (?:its|their) names?', descriptor)
    if name_contains:
        fragment = name_contains.group(1)
        return lambda c: is_pokemon_card(c) and fragment in (
            getattr(def_for(c.archetype_id), "display_name", "") or "").casefold()
    if "in any combination of supporter and stadium cards" in descriptor:
        return lambda c: is_supporter_card(c) or is_stadium_card(c)
    if "pokémon and a pokémon tool card" in descriptor:
        return lambda c: is_pokemon_card(c) or is_pokemon_tool(c)
    if "tag team cards" in descriptor:
        return lambda c: "tag team" in subtypes(c)
    if "ultra beast card" in descriptor:
        return lambda c: "ultra beast" in subtypes(c)
    if "future pokémon" in descriptor:
        return lambda c: is_pokemon_card(c) and "future" in subtypes(c)
    if "ancient pokémon" in descriptor:
        return lambda c: is_pokemon_card(c) and "ancient" in subtypes(c)
    if "cards named looker" in descriptor:
        return lambda c: (getattr(def_for(c.archetype_id), "display_name", "") or "").casefold() == "looker"
    if "unidentified fossil card" in descriptor:
        return lambda c: (getattr(def_for(c.archetype_id), "display_name", "") or "").casefold() == "unidentified fossil"
    # Both subtypes and elemental restrictions apply (Electromagnetic Radar).
    requested = set(re.findall(r"pokémon-(gx|ex)\b", descriptor))
    if requested and "including" not in descriptor and "isn't" not in descriptor and "except" not in descriptor:
        types = {getattr(PokemonTypes, t.upper()).value
                 for t in re.findall(rf"({TYPES}) pokémon-", descriptor)}
        # Uppercase EX and lowercase ex are distinct card classes.
        requested = {s.upper() for s in requested}
        return lambda c: is_pokemon_card(c) and bool(requested.intersection(subtypes_for(c.archetype_id) or [])) and (
            not types or bool(types.intersection(c.get_attribute(AttrID.POKEMON_TYPES) or [])))
    combination = _combination_predicate(descriptor)
    if combination is not None:
        return combination
    extra = _extra_descriptor_predicate(descriptor)
    if extra is not None:
        return extra
    mixed = re.search(rf"basic ({TYPES}) pokémon or an? ({TYPES}) energy", descriptor)
    if mixed:
        pokemon_type, energy_type = (getattr(PokemonTypes, t.upper()).value for t in mixed.groups())
        return lambda c: (is_basic_pokemon(c) and pokemon_type in
                          (c.get_attribute(AttrID.POKEMON_TYPES) or [])) or (
                          is_energy_card(c) and energy_provides_type(c, energy_type))
    if "basic water pokémon or basic fighting pokémon" in descriptor:
        return lambda c: is_basic_pokemon(c) and bool(
            {PokemonTypes.WATER.value, PokemonTypes.FIGHTING.value}.intersection(
                c.get_attribute(AttrID.POKEMON_TYPES) or []))
    if "stadium card" in descriptor and "search your deck for" in text:
        return is_stadium_card
    return None


_NOUN = re.compile(r"\b(pokémon|energy|cards?)\b")


def _combination_predicate(descriptor):
    """"up to 3 in any combination of Fire Pokémon and Basic Fire Energy cards"
    (Heatmor's Licking Catch): a card may match EITHER part.  Without this the
    typed-Energy rule caught the whole phrase and only Energy was offered.

    Returns None when any part isn't understood, so name lists such as
    "Silcoon and Cascoon" keep their existing handling."""
    match = re.search(r"in any combination of (.+?)(?: and (?:put|attach)|$)", descriptor)
    if not match:
        return None
    parts = [p.strip() for p in re.split(r"\s+and\s+|\s+or\s+|,\s*", match.group(1)) if p.strip()]
    if len(parts) < 2:
        return None
    # "Water and Psychic Energy cards": a bare type borrows the last part's noun.
    tail = _NOUN.search(parts[-1])
    if tail:
        tail_text = parts[-1][tail.start():]
        parts = [p if _NOUN.search(p) or p not in TYPES.split("|") else f"{p} {tail_text}"
                 for p in parts]
    if not any(_NOUN.search(p) for p in parts):
        names = {p for p in parts}          # "Amaura or Tyrunt": card names
        return lambda c: is_pokemon_card(c) and _display_name(c) in names
    from spirit.game.card_effects.standard_era import _search_predicate
    predicates = []
    for part in parts:
        owner = re.fullmatch(r"([a-z.]+)'s pokémon", part)
        if owner:
            prefix = f"{owner.group(1)}'s "
            predicates.append(lambda c, prefix=prefix: is_pokemon_card(c) and (
                getattr(def_for(c.archetype_id), "display_name", "") or "").casefold().startswith(prefix))
            continue
        if not _NOUN.search(part):
            return None
        predicate = _search_predicate("search your deck for " + part)
        if predicate is None:
            return None
        predicates.append(predicate)
    return lambda c: any(p(c) for p in predicates)



def _display_name(card):
    return (getattr(def_for(card.archetype_id), "display_name", "") or "").casefold()


def _extra_descriptor_predicate(descriptor):
    """Narrow descriptors the broad type/kind rules used to swallow."""
    from spirit.game.session.effects import is_item_card
    lead = r"^(?:up to \d+ |an? |\d+ |any number of )?"
    # Hop's Bag: "up to 2 basic hop's pokémon" (owner prefix in the card name).
    owner = re.search(lead + r"(basic |evolution )?([a-z.]+(?: [a-z.]+)?)'s pokémon\b", descriptor)
    if owner and owner.group(2) not in {"your opponent", "opponent"}:
        stage, prefix = owner.group(1), owner.group(2) + "'s "
        return lambda c: is_pokemon_card(c) and _display_name(c).startswith(prefix) and (
            stage is None or (is_basic_pokemon(c) == (stage == "basic ")))
    # Apricorn Maker.
    word = re.search(r'item cards? that (?:has|have) the word "([^"]+)" in (?:its|their) names?', descriptor)
    if word:
        fragment = word.group(1)
        return lambda c: is_item_card(c) and fragment in _display_name(c)
    # Lisia: Prism Star cards (none are GLC-legal).
    if "prism star" in descriptor:
        return lambda c: any("prism" in s.casefold() for s in (subtypes_for(c.archetype_id) or []))
    # Tera Orb (Tera Pokémon are all Pokémon ex, so none are GLC-legal).
    if re.search(r"\btera pokémon\b", descriptor):
        return lambda c: is_pokemon_card(c) and any(
            s.casefold() == "tera" for s in (subtypes_for(c.archetype_id) or []))
    # Poké Maniac.
    retreat = re.search(r"pokémon that (?:has|have) a retreat cost of exactly (\d+)", descriptor)
    if retreat:
        wanted = int(retreat.group(1))
        return lambda c: is_pokemon_card(c) and int(c.get_attribute(AttrID.RETREAT_COST) or 0) == wanted
    # Professor Elm's Lecture / Clavell.
    hp = re.search(r"(basic )?pokémon with (\d+) hp or less", descriptor)
    if hp:
        basic, limit = bool(hp.group(1)), int(hp.group(2))
        return lambda c: is_pokemon_card(c) and (not basic or is_basic_pokemon(c)) and \
            0 < int(c.get_attribute(AttrID.HP) or 0) <= limit
    return None
