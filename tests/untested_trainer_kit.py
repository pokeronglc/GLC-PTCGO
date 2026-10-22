"""Helpers for tests/test_untested_trainers.py (bug hunt 3, Oct 14).

find(...)   a Pokemon definition by predicate that has a plain damaging attack
named(n)    any definition by display name (first printing, deterministic)
strike(...) one real attack from P1's Active into P2's Active; returns damage
"""
import json

from spirit.game.attributes import AttrID, PokemonStage, PokemonTypes
from spirit.game.data_utils import (
    CARD_DEFS_BY_GUID, PokemonCardDef, subtypes_for, def_for)
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2
from tests.bughunt_table import Table

C, G, R, W, L, P, F, D, M, Y, N = (
    PokemonTypes.COLORLESS, PokemonTypes.GRASS, PokemonTypes.FIRE,
    PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.PSYCHIC,
    PokemonTypes.FIGHTING, PokemonTypes.DARKNESS, PokemonTypes.METAL,
    PokemonTypes.FAIRY, PokemonTypes.DRAGON)

_SORTED = None


def _defs():
    global _SORTED
    if _SORTED is None:
        _SORTED = sorted(CARD_DEFS_BY_GUID.values(),
                         key=lambda d: (str(getattr(d, 'set_code', '')),
                                        int(getattr(d, 'collector_number', 0) or 0), d.guid))
    return _SORTED


def plain_attack(d):
    for a in d.abilities or []:
        if type(a).__name__ == 'Attack' and (a.damage or 0) > 0 \
                and not (a.game_text or '').strip() and a.effect is None \
                and not getattr(a, 'damage_modifier', None):
            return a
    return None


def _quiet(d):
    """No Abilities / passives that could interfere."""
    if getattr(d, 'passive', None) is not None:
        return False
    for a in d.abilities or []:
        if type(a).__name__ != 'Attack':
            return False
    return True


def _attr(d, attr):
    spec = d.extra_attributes.get(str(attr.value))
    v = spec.get('value') if isinstance(spec, dict) else None
    if isinstance(v, str) and v[:1] in '[{':
        v = json.loads(v)
    return v


def types_of(d):
    return [PokemonTypes(x) for x in (_attr(d, AttrID.POKEMON_TYPES) or [])]


def stage_of(d):
    return PokemonStage(_attr(d, AttrID.STAGE))


def subs(d):
    return set(subtypes_for(d.guid))


def find(types=None, stage=None, sub=None, nosub=None, name=None, pred=None, quiet=True):
    """First Pokemon definition matching, with a plain damaging attack."""
    for d in _defs():
        if not isinstance(d, PokemonCardDef):
            continue
        if types is not None:
            want = types if isinstance(types, (list, tuple, set)) else [types]
            el = types_of(d)
            if len(el) != 1 or el[0] not in want:
                continue
        if stage is not None and stage_of(d) != stage:
            continue
        s = subs(d)
        if sub is not None and not (s & ({sub} if isinstance(sub, str) else set(sub))):
            continue
        if nosub is not None and s & set(nosub):
            continue
        if name is not None and not (name(d.display_name or '') if callable(name)
                                     else (d.display_name or '') == name):
            continue
        if pred is not None and not pred(d):
            continue
        if quiet and not _quiet(d):
            continue
        if plain_attack(d) is None:
            continue
        return d
    raise LookupError('no Pokemon for %r' % ((types, stage, sub, name),))


RULE_BOX = ('V', 'VSTAR', 'VMAX', 'V-UNION', 'GX', 'EX', 'ex', 'TAG TEAM', 'LEGEND',
            'SV_Mega', 'Radiant', 'MEGA', 'BREAK', 'Prism Star')


def plain(types=C, stage=PokemonStage.BASIC, **kw):
    kw.setdefault('nosub', RULE_BOX)
    return find(types=types, stage=stage, **kw)


def named(display_name, kind=None):
    for d in _defs():
        if (d.display_name or '') == display_name and (kind is None or isinstance(d, kind)):
            return d
    raise LookupError(display_name)


def neutral(p, hp=None):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.attribute_originals[AttrID.HP.value] = hp
        p.set_attribute(AttrID.HP, hp)
    return p


def pay(t, pokemon, attack):
    for k, v in attack.cost.items():
        t.energy(pokemon, D if k == C else k, v)


def board(test, attacker=None, defender=None, *, hp=400, neutral_def=True, neutral_atk=True,
          pay_attack=True):
    """P1 Active `attacker` (energy paid for its plain attack), P2 Active `defender`."""
    t = Table(test)
    atk_def = attacker or test.filler
    a = t.put(atk_def, P1, 'active')
    if neutral_atk:
        neutral(a)
    att = plain_attack(atk_def) if not isinstance(atk_def, str) else None
    if pay_attack and att is not None:
        pay(t, a, att)
    d = t.put(defender or test.filler, P2, 'active')
    if neutral_def:
        neutral(d, hp)
    elif hp is not None:
        d.attribute_originals[AttrID.HP.value] = hp
        d.set_attribute(AttrID.HP, hp)
    t.atk = att
    return t, a, d


async def strike(t, a, d):
    """P1's Active uses its plain attack; returns damage taken by d."""
    before = t.hp(d)
    await t.attack(a, t.atk.title)
    return before - t.hp(d)


def name_of(card):
    return def_for(card.archetype_id).display_name


def max_hp(t, p):
    return effective_max_hp(t.board, p)


def big(types=C, at_least=100, **kw):
    """A non-rule-box Pokemon (any stage) whose plain attack does >= at_least."""
    kw.setdefault('nosub', RULE_BOX)
    return find(types=types, pred=lambda d: (plain_attack(d) is not None
                                             and plain_attack(d).damage >= at_least), **kw)


def weak_to(kind, **kw):
    """Plain Pokemon whose Weakness is `kind` (no Resistance)."""
    kw.setdefault('nosub', RULE_BOX)

    def ok(d):
        w = _attr(d, AttrID.WEAKNESS_TYPES) or []
        r = _attr(d, AttrID.RESISTANCE_TYPES)
        return w == [kind.value] and r in (None, 0, PokemonTypes.UNSET.value)
    return find(pred=ok, **kw)


def ultra_beast(**kw):
    return find(pred=lambda d: 'Ultra Beast' in subs(d), **kw)


async def end_turn(t):
    """End the current player's turn like run_turn_loop does, then pass it."""
    s = t.session
    pid = t.state.active_player_id
    await t._run(lambda: s._fire_end_of_turn_triggers(pid))
    await t._run(lambda: s._discard_end_of_turn_attached_energies(pid))
    await t._run(lambda: s._run_pokemon_checkup(pid))
    t.next_turn()


def with_attack(rx, types=None, nosub=RULE_BOX, stage=None, cost_max=4, skip=0):
    """(definition, attack) whose attack text matches regex rx (lower-case)."""
    import re
    n = 0
    for d in _defs():
        if not isinstance(d, PokemonCardDef) or not _quiet(d):
            continue
        if subs(d) & set(nosub or ()):
            continue
        if types is not None and types_of(d) != [types]:
            continue
        if stage is not None and stage_of(d) != stage:
            continue
        for a in d.abilities:
            if type(a).__name__ == 'Attack' and re.search(rx, (a.game_text or '').lower()) \
                    and sum(a.cost.values()) <= cost_max:
                if n == skip:
                    return d, a
                n += 1
    raise LookupError(rx)


async def equip(t, tool, pokemon):
    """Attach a Tool and register its granted abilities (as a real play does)."""
    card = t.attach(tool, pokemon)
    await t._run(lambda: t.session.refresh_granted_abilities(pokemon))
    return card
