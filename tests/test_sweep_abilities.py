"""Sweep: search/bench/attach attacks and common Abilities.

Attacks
  bench_search     "search your deck for (up to) N basic pokémon and put them onto your bench..."
  hand_search      "search your deck for (up to) N <kind> card(s), (reveal them,) and put them into your hand..."
  discard_attach   "attach (up to) N (basic) <type> energy card(s) from your discard pile to ..."
  deck_attach      "search your deck for (up to) N (basic) <type> energy cards and attach them to ..."
Abilities
  evolve_trigger   "when you play this pokémon from your hand to evolve 1 of your pokémon (during your turn), you may ..."
  rough_skin       "if this pokémon is (your active pokémon | in the active spot) and is damaged by ... put N damage counters on the attacking pokémon."
  ko_counters      "... is knocked out by damage from ... attack, put N damage counters on the attacking pokémon."
  draw_ability     "once during your turn (before your attack), you may draw a card." (+ variants)
  damage_reduction "this pokémon takes N less damage from attacks (after applying weakness and resistance)."
"""
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import (SweepCase, run_sweep, std_board, do_attack, neutral, pay_cost,
                              unique_pokemon, norm, BIG)
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage
from spirit.game.data_utils import (Attack, CARD_DEFS_BY_GUID, PokemonCardDef, ItemCardDef,
                                    FossilItemCardDef, SupporterCardDef, StadiumCardDef,
                                    PokemonToolCardDef, EnergyCardDef, TrainerCardDef, def_for,
                                    evolves_from_chain, _string_attr)
from spirit.tools.effect_smoke import P1, P2

NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4}
TYPES = {'grass': PokemonTypes.GRASS, 'fire': PokemonTypes.FIRE, 'water': PokemonTypes.WATER,
         'lightning': PokemonTypes.LIGHTNING, 'psychic': PokemonTypes.PSYCHIC,
         'fighting': PokemonTypes.FIGHTING, 'darkness': PokemonTypes.DARKNESS,
         'metal': PokemonTypes.METAL, 'fairy': PokemonTypes.FAIRY, 'dragon': PokemonTypes.DRAGON}
TYPE_RX = '|'.join(TYPES)
COND = {'asleep': 'Asleep', 'burned': 'Burned', 'confused': 'Confused',
        'paralyzed': 'Paralyzed', 'poisoned': 'Poisoned'}


def num(s):
    return NUM[s] if s in NUM else int(s)


def other_abilities(d, ability):
    return [a for a in (d.abilities or []) if not isinstance(a, Attack) and a is not ability]


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


# ---------------------------------------------------------------- card pool --
def stage_of(d):
    spec = d.extra_attributes.get(str(AttrID.STAGE.value))
    return spec.get('value') if isinstance(spec, dict) else None


def types_of(d):
    import json
    spec = d.extra_attributes.get(str(AttrID.POKEMON_TYPES.value))
    return json.loads(spec['value']) if isinstance(spec, dict) else []


_POOL = {}


def pool(test):
    """Plain representative cards of each kind (deterministic)."""
    if _POOL:
        return _POOL
    defs = sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, d.collector_number, d.guid))
    basic_guids = {g.lower() for g in test.energies.values()}

    def plain_poke(d):
        return (isinstance(d, PokemonCardDef) and not has_ability(d) and not d.subtypes_rulebox()
                if hasattr(d, 'subtypes_rulebox') else
                isinstance(d, PokemonCardDef) and not has_ability(d)
                and not set(d.subtypes or []) & {'V', 'VMAX', 'VSTAR', 'GX', 'EX', 'ex', 'TAG TEAM',
                                                 'Radiant', 'Prism Star', 'LEGEND', 'BREAK'})

    by_type = {}
    for d in defs:
        if plain_poke(d) and stage_of(d) == PokemonStage.BASIC and len(types_of(d)) == 1 \
                and not getattr(d, 'unplayable_from_hand', False):
            by_type.setdefault(types_of(d)[0], d)
    _POOL['basic_by_type'] = by_type
    _POOL['stage1'] = next(d for d in defs if plain_poke(d) and stage_of(d) == PokemonStage.STAGE1)
    _POOL['item'] = test.item
    _POOL['supporter'] = next(d for d in defs if type(d) is SupporterCardDef
                              and 'ACE SPEC' not in (d.subtypes or []))
    _POOL['stadium'] = next(d for d in defs if type(d) is StadiumCardDef)
    _POOL['tool'] = next(d for d in defs if type(d) is PokemonToolCardDef
                         and 'ACE SPEC' not in (d.subtypes or []))
    # plain Colorless-providing special Energy (no attach restriction)
    _POOL['special_energy'] = next(d for d in defs if is_special_def(d)
                                   and getattr(d, 'energy_type', None) == PokemonTypes.COLORLESS
                                   and d.attach_to is None and d.attach_condition is None
                                   and 'ACE SPEC' not in (d.subtypes or []))
    # Vanilla attacker for "opponent attacks" scenarios: one plain attack, 60-120 damage.
    att = None
    for d in unique_pokemon():
        if not plain_poke(d) or stage_of(d) != PokemonStage.BASIC:
            continue
        atks = [a for a in d.abilities or [] if isinstance(a, Attack)]
        if len(atks) == 1 and not norm(atks[0].game_text) and 60 <= (atks[0].damage or 0) <= 120 \
                and not atks[0].damage_operator and sum((atks[0].cost or {}).values()) <= 3:
            att = (d, atks[0])
            break
    _POOL['attacker'] = att
    return _POOL


def basic_energy_def(test, kind):
    return CARD_DEFS_BY_GUID[test.energies[kind.value].lower()]


def is_special_def(d):
    return isinstance(d, EnergyCardDef) and str(AttrID.IS_SPECIAL_ENERGY.value) in d.extra_attributes


def is_basic_energy_def(test, d):
    return isinstance(d, EnergyCardDef) and not is_special_def(d)


def energy_type_of(test, d):
    return getattr(getattr(d, 'energy_type', None), 'value', None)


def set_deck(t, pid, specs):
    area = t.board.find_player_area(pid, 'deck')
    for c in list(area.children):
        area.remove_child(c)
    return [t.put(s, pid, 'deck') for s in specs]


def set_discard(t, pid, specs):
    area = t.board.find_player_area(pid, 'discard')
    for c in list(area.children):
        area.remove_child(c)
    return [t.put(s, pid, 'discard') for s in specs]


class Recorder:
    """t.picks recorder: remembers every choose_cards call."""
    def __init__(self, t, chooser=None):
        self.calls = []
        self.chooser = chooser
        t.picks = self

    def __call__(self, cards, count, prompt, display):
        self.calls.append((list(cards), count, prompt))
        if self.chooser is not None:
            return self.chooser(cards, count)
        return cards[:count]


# ------------------------------------------------------- kind classification --
def kind_matcher(test, kind):
    """Return (match(def)->bool|None, deck_specs) for a search 'kind' phrase.
    None from match means 'ambiguous card, don't include'."""
    P = pool(test)
    kind = kind.strip()
    bt = P['basic_by_type']
    fire, water = PokemonTypes.FIRE.value, PokemonTypes.WATER.value
    some_basic = test.filler
    m = re.fullmatch(r"(basic )?(%s) energy( cards?)?" % TYPE_RX, kind)
    if m:
        ty = TYPES[m.group(2)]
        other = PokemonTypes.WATER if ty != PokemonTypes.WATER else PokemonTypes.FIRE
        specs = [basic_energy_def(test, other), some_basic, P['item']]
        return (lambda d: is_basic_energy_def(test, d) and energy_type_of(test, d) == ty.value,
                specs, basic_energy_def(test, ty))
    if re.fullmatch(r"basic energy cards?", kind):
        specs = [P['special_energy'], some_basic, P['item'], P['supporter']]
        return (lambda d: is_basic_energy_def(test, d), specs,
                [basic_energy_def(test, PokemonTypes.FIRE), basic_energy_def(test, PokemonTypes.WATER),
                 basic_energy_def(test, PokemonTypes.GRASS), basic_energy_def(test, PokemonTypes.LIGHTNING),
                 basic_energy_def(test, PokemonTypes.PSYCHIC)])
    if re.fullmatch(r"(an )?energy cards?", kind):
        specs = [some_basic, P['item'], P['supporter']]
        return (lambda d: isinstance(d, EnergyCardDef), specs,
                [basic_energy_def(test, PokemonTypes.FIRE), P['special_energy'],
                 basic_energy_def(test, PokemonTypes.WATER), basic_energy_def(test, PokemonTypes.GRASS),
                 basic_energy_def(test, PokemonTypes.PSYCHIC)])
    if re.fullmatch(r"(basic )?pokémon", kind):
        basic_only = kind.startswith('basic')
        specs = [P['item'], P['supporter'], basic_energy_def(test, PokemonTypes.FIRE)]
        if basic_only:
            specs.append(P['stage1'])
            return (lambda d: isinstance(d, PokemonCardDef) and stage_of(d) == PokemonStage.BASIC,
                    specs, [some_basic, bt[fire], bt[water], some_basic, bt[fire]])
        return (lambda d: isinstance(d, PokemonCardDef), specs,
                [some_basic, P['stage1'], bt[water], some_basic, P['stage1']])
    if kind == 'evolution pokémon':
        specs = [P['item'], some_basic, basic_energy_def(test, PokemonTypes.FIRE)]
        return (lambda d: isinstance(d, PokemonCardDef) and stage_of(d) not in (PokemonStage.BASIC, None),
                specs, [P['stage1']] * 5)
    m = re.fullmatch(r"(%s) pokémon" % TYPE_RX, kind)
    if m:
        ty = TYPES[m.group(1)]
        if ty.value not in bt:
            return None
        other = bt[PokemonTypes.WATER.value if ty != PokemonTypes.WATER else PokemonTypes.FIRE.value]
        specs = [other, P['item'], basic_energy_def(test, ty)]
        return (lambda d: isinstance(d, PokemonCardDef) and ty.value in types_of(d), specs, [bt[ty.value]] * 5)
    if kind in ('item card', 'item cards'):
        specs = [P['supporter'], P['stadium'], some_basic, basic_energy_def(test, PokemonTypes.FIRE)]
        return (lambda d: isinstance(d, ItemCardDef), specs, [P['item']] * 5)
    if kind in ('supporter card', 'supporter cards'):
        specs = [P['item'], P['stadium'], some_basic, basic_energy_def(test, PokemonTypes.FIRE)]
        return (lambda d: isinstance(d, SupporterCardDef), specs, [P['supporter']] * 5)
    if kind in ('stadium card', 'stadium cards'):
        specs = [P['item'], P['supporter'], some_basic, basic_energy_def(test, PokemonTypes.FIRE)]
        return (lambda d: isinstance(d, StadiumCardDef), specs, [P['stadium']] * 5)
    if kind in ('pokémon tool card', 'pokémon tool cards'):
        specs = [P['supporter'], P['stadium'], some_basic, basic_energy_def(test, PokemonTypes.FIRE)]
        return (lambda d: isinstance(d, PokemonToolCardDef), specs, [P['tool']] * 5)
    if kind in ('trainer card', 'trainer cards'):
        specs = [some_basic, basic_energy_def(test, PokemonTypes.FIRE), P['special_energy']]
        return (lambda d: isinstance(d, TrainerCardDef), specs,
                [P['item'], P['supporter'], P['stadium'], P['tool'], P['item']])
    if kind in ('card', 'cards', 'any card'):
        return (lambda d: True, [], [some_basic, P['item'], P['supporter'],
                                     basic_energy_def(test, PokemonTypes.FIRE), P['stadium']])
    return None


async def run_search_to_hand(t, test, kind, n, exact, act):
    """Builds the deck for `kind`, runs `act()` and judges the result."""
    km = kind_matcher(test, kind)
    if km is None:
        return None, f'kind {kind!r} not modelled'
    match, nonmatch, matching = km
    if not isinstance(matching, list):
        matching = [matching] * 5
    matching = (matching * (n + 2))[:n + 1]
    set_deck(t, P1, nonmatch + matching)
    deck_before = {c.entity_id for c in t.zone(P1, 'deck')}
    hand_before = {c.entity_id for c in t.zone(P1, 'hand')}
    rec = Recorder(t)
    res = await act()
    if res is False:
        return False, 'not offered/used'
    if not rec.calls:
        return False, f'no card choice offered (prompts {t.prompts})'
    cands, count, _ = rec.calls[0]
    bad = [def_for(c.archetype_id).display_name for c in cands if not match(def_for(c.archetype_id))]
    n_match_deck = len(matching)
    gained = [c for c in t.zone(P1, 'hand') if c.entity_id not in hand_before and c.entity_id in deck_before]
    gained_bad = [def_for(c.archetype_id).display_name for c in gained if not match(def_for(c.archetype_id))]
    problems = []
    if bad:
        problems.append(f'non-matching offered {bad}')
    if len(cands) < n_match_deck:
        problems.append(f'only {len(cands)} of {n_match_deck} matching cards offered')
    if count != n:
        problems.append(f'pick count {count}, text says {n}')
    if len(gained) != n:
        problems.append(f'put {len(gained)} into hand, expected {n}')
    if gained_bad:
        problems.append(f'non-matching card(s) put into hand {gained_bad}')
    return (not problems), '; '.join(problems) or f'ok ({len(gained)} cards)'


# ------------------------------------------------------------------ attacks --
BENCH_RX = (r"^search your deck for (a|up to \d+|\d+) basic pokémon and put (?:it|them) onto your bench\. "
            r"(?:then, shuffle your deck|shuffle your deck afterward)\.$")


async def bench_search(test, d, attack, m):
    want = m.group(1)
    n = num(want.split()[-1])
    P = pool(test)
    bt = P['basic_by_type']
    basics = [test.filler, bt[PokemonTypes.FIRE.value], bt[PokemonTypes.WATER.value], test.filler, test.filler]

    def prep(b):
        set_deck(b.t, P1, [P['stage1'], P['item'], basic_energy_def(test, PokemonTypes.FIRE)] + basics[:n + 1])

    b = std_board(test, d, attack, prep=prep)
    rec = Recorder(b.t)
    if not await do_attack(b):
        return False, 'attack not offered'
    t = b.t
    added = len(t.zone(P1, 'bench')) - b.before['my_bench_n']
    problems = []
    if not rec.calls:
        problems.append('no choice offered')
    else:
        cands, count, _ = rec.calls[0]
        bad = [def_for(c.archetype_id).display_name for c in cands
               if stage_of(def_for(c.archetype_id)) != PokemonStage.BASIC
               or not isinstance(def_for(c.archetype_id), PokemonCardDef)]
        if bad:
            problems.append(f'non-Basic offered {bad}')
        if len(cands) != n + 1:
            problems.append(f'{len(cands)} candidates offered, deck has {n + 1} Basics')
        if count != n:
            problems.append(f'pick count {count}, expected {n}')
    if added != n:
        problems.append(f'benched {added}, expected {n}')
    if len(t.zone(P1, 'deck')) != b.before['my_deck'] - n:
        problems.append(f"deck {b.before['my_deck']} -> {len(t.zone(P1, 'deck'))}")
    # bench-space cap: 4 already on bench -> only 1 more fits
    if n >= 2:
        def prep2(b2):
            prep(b2)
            for _ in range(3):
                neutral(b2.t.put(test.filler, P1, 'bench'))
        b2 = std_board(test, d, attack, prep=prep2)
        Recorder(b2.t)
        if await do_attack(b2):
            n2 = len(b2.t.zone(P1, 'bench'))
            if n2 != 5:
                problems.append(f'with 4 benched, bench ended at {n2} (should be 5)')
        else:
            problems.append('not offered with 4 benched')
    return (not problems), '; '.join(problems) or f'benched {added}'


HAND_RX = (r"^search your deck for (a|an|up to \d+|\d+) ((?:basic )?(?:(?:%s) )?(?:pokémon|energy|item|supporter|"
           r"stadium|pokémon tool|trainer|evolution pokémon)(?: cards?)?|cards?)(?:, reveal (?:it|them),)? and put "
           r"(?:it|them) into your hand\. (?:then, shuffle your deck|shuffle your deck afterward)\.$") % TYPE_RX


async def hand_search(test, d, attack, m):
    cnt, kind = m.group(1), m.group(2)
    n = num(cnt.split()[-1])
    if kind == 'card' or kind == 'cards':
        kind = 'card'
    b = std_board(test, d, attack)

    async def act():
        return await do_attack(b)
    ok, detail = await run_search_to_hand(b.t, test, kind, n, not cnt.startswith('up to'), act)
    if ok and not has_ability(d) and attack.damage and not attack.damage_operator:
        got = b.before['opp_hp'] - b.t.hp(b.opp)
        if got != attack.damage:
            return False, f'{detail}; damage {got} vs printed {attack.damage}'
    return ok, detail


DISCARD_RX = (r"^attach (a|an|up to \d+|\d+) (basic )?(?:(%s) )?energy(?: cards?)? from your discard pile to "
              r"(this pokémon|1 of your benched pokémon|1 of your pokémon)\.$") % TYPE_RX


def _energy_setup(test, basic, tname):
    """(matching specs, non-matching specs, match(def))"""
    P = pool(test)
    if tname:
        ty = TYPES[tname]
        other = PokemonTypes.WATER if ty != PokemonTypes.WATER else PokemonTypes.FIRE
        return ([basic_energy_def(test, ty)] * 4, [basic_energy_def(test, other), P['item'], test.filler],
                lambda dd: is_basic_energy_def(test, dd) and energy_type_of(test, dd) == ty.value)
    if basic:
        return ([basic_energy_def(test, k) for k in (PokemonTypes.FIRE, PokemonTypes.WATER,
                                                      PokemonTypes.GRASS, PokemonTypes.PSYCHIC)],
                [P['special_energy'], P['item'], test.filler],
                lambda dd: is_basic_energy_def(test, dd))
    return ([basic_energy_def(test, PokemonTypes.FIRE), P['special_energy'],
             basic_energy_def(test, PokemonTypes.WATER), P['special_energy']],
            [P['item'], test.filler], lambda dd: isinstance(dd, EnergyCardDef))


def _attached_energy_counts(t, pokes):
    return {p.entity_id: len(t.board.attached_energies(p)) for p in pokes}


async def discard_attach(test, d, attack, m):
    cnt, basic, tname, target = m.groups()
    n = num(cnt.split()[-1])
    if tname in ('dragon', 'fairy') or (tname and TYPES[tname].value not in test.energies):
        return None, 'no basic energy of that type'
    matching, nonmatch, match = _energy_setup(test, basic, tname)
    matching = (matching * (n + 2))[:n + 1]

    def prep(b):
        set_discard(b.t, P1, nonmatch + matching)
    b = std_board(test, d, attack, prep=prep)
    t = b.t
    rec = Recorder(t)
    mine = [b.me, b.my_bench]
    before = _attached_energy_counts(t, mine)
    pre_ids = {e.entity_id for p in mine for e in t.board.attached_energies(p)}
    if not await do_attack(b):
        return False, 'attack not offered'
    after = _attached_energy_counts(t, mine)
    problems = []
    if rec.calls:
        bad = [def_for(c.archetype_id).display_name for c in rec.calls[0][0] if not match(def_for(c.archetype_id))]
        if bad:
            problems.append(f'non-matching offered {bad}')
    want_target = {'this pokémon': b.me, '1 of your benched pokémon': b.my_bench,
                   '1 of your pokémon': None}[target]
    gained = {k: after[k] - before[k] for k in after}
    total = sum(gained.values())
    if total != n:
        problems.append(f'attached {total}, expected {n}')
    if want_target is not None and gained[want_target.entity_id] != total:
        problems.append(f'energy went to wrong Pokémon: {gained}')
    new = [e for p in mine for e in t.board.attached_energies(p) if e.entity_id not in pre_ids]
    badnew = [def_for(e.archetype_id).display_name for e in new if not match(def_for(e.archetype_id))]
    if badnew:
        problems.append(f'non-matching attached {badnew}')
    lost = b.before['my_discard'] - len(t.zone(P1, 'discard'))
    if lost != n:
        problems.append(f'discard shrank by {lost}, expected {n}')
    return (not problems), '; '.join(problems) or f'attached {total}'


DECK_ATTACH_RX = (r"^search your deck for (a|an|up to \d+|\d+) (basic )?(?:(%s) )?energy(?: cards?)? and attach "
                  r"(?:it|them) to (this pokémon|your pokémon in any way you like|your benched pokémon in any way "
                  r"you like|1 of your benched pokémon|1 of your pokémon)\. "
                  r"(?:then, shuffle your deck|shuffle your deck afterward)\.$") % TYPE_RX


async def deck_attach(test, d, attack, m):
    cnt, basic, tname, target = m.groups()
    n = num(cnt.split()[-1])
    if tname and TYPES[tname].value not in test.energies:
        return None, 'no basic energy of that type'
    matching, nonmatch, match = _energy_setup(test, basic, tname)
    matching = (matching * (n + 2))[:n + 1]

    def prep(b):
        set_deck(b.t, P1, nonmatch + matching)
    b = std_board(test, d, attack, prep=prep)
    t = b.t
    rec = Recorder(t)
    mine = [b.me, b.my_bench]
    before = _attached_energy_counts(t, mine)
    pre_ids = {e.entity_id for p in mine for e in t.board.attached_energies(p)}
    if target in ('your pokémon in any way you like',):
        t.pokemon = lambda cands, prompt: cands[-1]     # send them to the bench filler
    if not await do_attack(b):
        return False, 'attack not offered'
    after = _attached_energy_counts(t, mine)
    problems = []
    if rec.calls:
        cands = rec.calls[0][0]
        bad = [def_for(c.archetype_id).display_name for c in cands if not match(def_for(c.archetype_id))]
        if bad:
            problems.append(f'non-matching offered {bad}')
        if len(cands) != len(matching):
            problems.append(f'{len(cands)} candidates, deck has {len(matching)} matching')
    else:
        problems.append('no choice offered')
    gained = {k: after[k] - before[k] for k in after}
    total = sum(gained.values())
    if total != n:
        problems.append(f'attached {total}, expected {n}')
    if target == 'this pokémon' and gained[b.me.entity_id] != total:
        problems.append(f'energy not all on this Pokémon: {gained}')
    if 'benched' in target and gained[b.me.entity_id]:
        problems.append(f'energy attached to the Active: {gained}')
    if target == 'your pokémon in any way you like' and gained[b.my_bench.entity_id] != total:
        problems.append(f'chosen target (bench) ignored: {gained}')
    new = [e for p in mine for e in t.board.attached_energies(p) if e.entity_id not in pre_ids]
    badnew = [def_for(e.archetype_id).display_name for e in new if not match(def_for(e.archetype_id))]
    if badnew:
        problems.append(f'non-matching attached {badnew}')
    if len(t.zone(P1, 'deck')) != b.before['my_deck'] - n:
        problems.append(f"deck {b.before['my_deck']} -> {len(t.zone(P1, 'deck'))}")
    return (not problems), '; '.join(problems) or f'attached {total}'


# ---------------------------------------------------------------- abilities --
def pre_evolution(d):
    from_name = _string_attr(d, AttrID.EVOLUTION_LOGIC_FROM)
    if not from_name:
        return None
    want = stage_of(d) - 1 if stage_of(d) in (PokemonStage.STAGE1, PokemonStage.STAGE2) else None
    for c in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, x.collector_number)):
        if isinstance(c, PokemonCardDef) and _string_attr(c, AttrID.EVOLUTION_LOGIC_NAME) == from_name \
                and stage_of(c) == want and not has_ability(c):
            return c
    for c in CARD_DEFS_BY_GUID.values():
        if isinstance(c, PokemonCardDef) and _string_attr(c, AttrID.EVOLUTION_LOGIC_NAME) == from_name:
            return c
    return None


EVOLVE_RX = (r"^when you play this pokémon from your hand to evolve 1 of your pokémon(?: during your turn)?, "
             r"you may (.*)$")


def evolve_board(test, d):
    t = Table(test)
    pre = pre_evolution(d)
    if pre is None:
        return None
    base = t.put(pre, P1, 'active')
    neutral(base, hp=None)          # keep real HP: damage must carry through evolution
    bench = neutral(t.put(test.filler, P1, 'bench'))
    opp = neutral(t.put(test.filler, P2, 'active'))
    opp_bench = neutral(t.put(test.filler, P2, 'bench'))
    card = t.put(d, P1, 'hand')
    return t, base, card, bench, opp, opp_bench


async def evolve_trigger(test, d, ability, m):
    effect = m.group(1)
    built = evolve_board(test, d)
    if built is None:
        return None, 'no pre-evolution found'
    t, base, card, bench, opp, opp_bench = built
    judge = None
    mm = re.fullmatch(r"draw (\d+|a) cards?\.", effect)
    if mm:
        n = num(mm.group(1))
        hand0 = len(t.zone(P1, 'hand')) - 1
        def judge():
            got = len(t.zone(P1, 'hand')) - hand0
            return got == n, f'drew {got}, expected {n}'
    mm = mm or None
    if judge is None:
        mm = re.fullmatch(r"(?:leave|make) your opponent's active pokémon (asleep|burned|confused|paralyzed|poisoned)"
                          r"(?: and (asleep|burned|confused|paralyzed|poisoned))?\.", effect) \
             or re.fullmatch(r"use this ability\. if you do, your opponent's active pokémon is now "
                             r"(asleep|burned|confused|paralyzed|poisoned)(?: and (asleep|burned|confused|paralyzed|"
                             r"poisoned))?\.", effect)
        if mm:
            want = {COND[w] for w in mm.groups() if w}
            def judge():
                got = t.conditions(opp)
                return want <= got and not t.conditions(base), f'opp conditions {sorted(got)}, want {sorted(want)}'
    if judge is None:
        mm = re.fullmatch(r"heal (\d+) damage from your active pokémon\.", effect)
        if mm:
            h = int(mm.group(1))
            pre_max = t.hp(base)
            D = min(h + 20, pre_max - 10)
            base.set_attribute(AttrID.HP, pre_max - D)
            def judge():
                dmg = t.damage(t.active(P1))
                return dmg == max(0, D - h), f'active has {dmg} damage after heal {h} of {D} (expected {max(0, D - h)})'
    if judge is None:
        mm = re.fullmatch(r"heal all damage from 1 of your pokémon\.", effect)
        if mm:
            base.set_attribute(AttrID.HP, t.hp(base) - min(50, t.hp(base) - 10))
            def judge():
                dmg = t.damage(t.active(P1))
                return dmg == 0, f'active has {dmg} damage left'
    if judge is None:
        mm = re.fullmatch(r"put (\d+) damage counters on 1 of your opponent's pokémon\.", effect)
        if mm:
            n = int(mm.group(1)) * 10
            def judge():
                got = (BIG - t.hp(opp)) + (BIG - t.hp(opp_bench))
                return got == n, f'opponent took {got}, expected {n}'
    if judge is None:
        mm = re.fullmatch(r"discard the top (\d+) cards of your opponent's deck\.", effect)
        if mm:
            n = int(mm.group(1))
            d0, x0 = len(t.zone(P2, 'deck')), len(t.zone(P2, 'discard'))
            def judge():
                dd, xx = d0 - len(t.zone(P2, 'deck')), len(t.zone(P2, 'discard')) - x0
                return dd == n and xx == n, f'opp deck -{dd}, discard +{xx}, expected {n}'
    search = None
    if judge is None:
        mm = re.fullmatch(r"search your deck for (a|an|any|up to \d+|\d+) ((?:\w+ )*?(?:card|cards|trainer cards?|"
                          r"pokémon tool cards?|item cards?|supporter cards?))(?:, reveal (?:it|them),)? and put "
                          r"(?:it|them) into your hand\. (?:then, shuffle your deck|shuffle your deck afterward)\.",
                          effect)
        if mm:
            n = 1 if mm.group(1) in ('a', 'an', 'any') else num(mm.group(1).split()[-1])
            search = (mm.group(2), n)
    if judge is None and search is None:
        return None, f'effect not modelled: {effect}'

    if other_abilities(d, ability) and False:
        pass
    # Negative check first: declining ("you may") does nothing.
    if search is not None:
        kind, n = search

        async def act():
            await t.play(card, targets=[base.entity_id])
        t.yes = True
        ok, detail = await run_search_to_hand(t, test, kind, n, False, act)
    else:
        t.yes = True
        await t.play(card, targets=[base.entity_id])
        ok, detail = judge()
    top = t.active(P1)
    if def_for(top.archetype_id) is not d:
        return False, f'evolution did not happen (active is {def_for(top.archetype_id).display_name}); {detail}'
    if ok and search is None:
        # "you may": declining leaves the board alone
        built = evolve_board(test, d)
        t2, base2, card2, *_ = built
        t2.yes = False
        h0, dk0 = len(t2.zone(P1, 'hand')), len(t2.zone(P1, 'deck'))
        c0 = t2.conditions(t2.active(P2))
        await t2.play(card2, targets=[base2.entity_id])
        if len(t2.zone(P1, 'hand')) != h0 - 1 or t2.conditions(t2.active(P2)) != c0 \
                or len(t2.zone(P2, 'deck')) != 30 or len(t2.zone(P1, 'deck')) != dk0:
            return False, f'{detail}; but declining the "you may" still had an effect'
    return ok, detail


def attacker_board(test, d, *, where='active', my_hp=BIG):
    """d in play for P1 (Active or Bench); P2 has the vanilla attacker Active, P2 to act."""
    P = pool(test)
    ad, aa = P['attacker']
    t = Table(test)
    if where == 'active':
        me = neutral(t.put(d, P1, 'active'), hp=my_hp)
        front = me
        neutral(t.put(test.filler, P1, 'bench'))
    else:
        front = neutral(t.put(test.filler, P1, 'active'))
        me = neutral(t.put(d, P1, 'bench'), hp=my_hp)
    att = neutral(t.put(ad, P2, 'active'))
    neutral(t.put(test.filler, P2, 'bench'))
    pay_cost(t, att, aa)
    neutral(t.put(test.filler, P2, 'bench'))
    t.next_turn()
    return t, me, front, att, aa


ROUGH_RX = (r"^if this pokémon is (?:your active pokémon|in the active spot) and is damaged by an "
            r"(?:opponent's attack|attack from your opponent's pokémon) \(even if this pokémon is knocked out\), "
            r"put (\d+) damage counters on the attacking pokémon\.$")


async def rough_skin(test, d, ability, m):
    n = int(m.group(1)) * 10
    if len(other_abilities(d, ability)):
        return None, 'other abilities'
    t, me, front, att, aa = attacker_board(test, d)
    entry = t.attack_offer(att, aa.title, pid=P2)
    if entry is None:
        return None, 'attacker attack not offered'
    await t.do(entry, pid=P2)
    took = BIG - t.hp(me)
    got = BIG - t.hp(att)
    problems = []
    if took <= 0:
        return None, 'ability holder took no damage'
    if got != n:
        problems.append(f'Active: attacker got {got} damage, expected {n}')
    # KO case
    t, me, front, att, aa = attacker_board(test, d, my_hp=10)
    await t.do(t.attack_offer(att, aa.title, pid=P2), pid=P2)
    got = BIG - t.hp(att)
    if got != n:
        problems.append(f'when KO\'d: attacker got {got}, expected {n}')
    # Bench: the filler Active is attacked -> no counters
    t, me, front, att, aa = attacker_board(test, d, where='bench')
    await t.do(t.attack_offer(att, aa.title, pid=P2), pid=P2)
    got = BIG - t.hp(att)
    if got != 0:
        problems.append(f'on Bench: attacker got {got} damage (expected 0)')
    return (not problems), '; '.join(problems) or f'attacker took {n}'


KO_RX = (r"^if this pokémon is (?:your active pokémon|in the active spot) and is knocked out by damage from an "
         r"(?:opponent's attack|attack from your opponent's pokémon), put (\d+) damage counters on the attacking "
         r"pokémon\.$")


async def ko_counters(test, d, ability, m):
    n = int(m.group(1)) * 10
    problems = []
    t, me, front, att, aa = attacker_board(test, d)
    entry = t.attack_offer(att, aa.title, pid=P2)
    if entry is None:
        return None, 'attacker attack not offered'
    await t.do(entry, pid=P2)
    if BIG - t.hp(att) != 0:
        problems.append(f'not KO\'d but attacker got {BIG - t.hp(att)}')
    t, me, front, att, aa = attacker_board(test, d, my_hp=10)
    await t.do(t.attack_offer(att, aa.title, pid=P2), pid=P2)
    if BIG - t.hp(att) != n:
        problems.append(f'KO\'d: attacker got {BIG - t.hp(att)}, expected {n}')
    return (not problems), '; '.join(problems) or 'ok'


DRAW_RX = (r"^once during your turn(?: \(before your attack\))?, (?:(if this pokémon is your active pokémon), )?"
           r"you may (?:use this ability\. )?draw (a|\d+) cards?\.( if this pokémon is your active pokémon, draw 1 "
           r"more card\.)?$")
DRAW_RX2 = r"^once during your turn, you may use this ability\. draw (a|\d+) cards?\.$"


async def draw_ability(test, d, ability, m):
    active_only, cnt, bonus = m.group(1), m.group(2), m.group(3)
    n = num(cnt)
    problems = []
    for where in ('active', 'bench'):
        t = Table(test)
        if where == 'active':
            me = neutral(t.put(d, P1, 'active'))
            neutral(t.put(test.filler, P1, 'bench'))
        else:
            neutral(t.put(test.filler, P1, 'active'))
            me = neutral(t.put(d, P1, 'bench'))
        neutral(t.put(test.filler, P2, 'active'))
        entry = t.ability_offer(me, ability.title)
        if where == 'bench' and active_only:
            if entry is not None:
                problems.append('offered on the Bench (Active only)')
            continue
        if entry is None:
            problems.append(f'not offered ({where})')
            continue
        h0 = len(t.zone(P1, 'hand'))
        await t.do(entry)
        want = n + (1 if bonus and where == 'active' else 0)
        got = len(t.zone(P1, 'hand')) - h0
        if got != want:
            problems.append(f'{where}: drew {got}, expected {want}')
        if t.ability_offer(me, ability.title) is not None:
            problems.append(f'{where}: offered again the same turn')
        # next own turn: available again
        t.next_turn()
        t.next_turn()
        if t.ability_offer(me, ability.title) is None:
            problems.append(f'{where}: not offered on the next turn')
    return (not problems), '; '.join(problems) or 'ok'


REDUCE_RX = r"^this pokémon takes (\d+) less damage from attacks \(after applying weakness and resistance\)\.$"


async def damage_reduction(test, d, ability, m):
    n = int(m.group(1))
    if other_abilities(d, ability):
        return None, 'other abilities'
    P = pool(test)
    ad, aa = P['attacker']
    problems = []
    t, me, front, att, aa = attacker_board(test, d)
    entry = t.attack_offer(att, aa.title, pid=P2)
    if entry is None:
        return None, 'attacker attack not offered'
    await t.do(entry, pid=P2)
    took = BIG - t.hp(me)
    want = max(0, aa.damage - n)
    if took != want:
        problems.append(f'Active took {took}, expected {aa.damage}-{n}={want}')
    # with Weakness: (damage x2) - n
    t, me, front, att, aa = attacker_board(test, d)
    atype = types_of(ad)[0]
    me.set_attribute(AttrID.WEAKNESS_TYPES, [atype])
    await t.do(t.attack_offer(att, aa.title, pid=P2), pid=P2)
    took = BIG - t.hp(me)
    want = max(0, aa.damage * 2 - n)
    if took != want:
        problems.append(f'with Weakness took {took}, expected {aa.damage}x2-{n}={want}')
    return (not problems), '; '.join(problems) or 'ok'


CASES = [
    SweepCase('bench_search', BENCH_RX, bench_search),
    SweepCase('hand_search', HAND_RX, hand_search),
    SweepCase('discard_attach', DISCARD_RX, discard_attach),
    SweepCase('deck_attach', DECK_ATTACH_RX, deck_attach),
    SweepCase('evolve_trigger', EVOLVE_RX, evolve_trigger, attack_only=False),
    SweepCase('rough_skin', ROUGH_RX, rough_skin, attack_only=False),
    SweepCase('ko_counters', KO_RX, ko_counters, attack_only=False),
    SweepCase('draw_ability', DRAW_RX, draw_ability, attack_only=False),
    SweepCase('draw_ability2', DRAW_RX2, lambda test, d, a, m: draw_ability(
        test, d, a, type('M', (), {'group': lambda self, i: {1: None, 2: m.group(1), 3: None}[i]})()),
        attack_only=False),
    SweepCase('damage_reduction', REDUCE_RX, damage_reduction, attack_only=False),
]


class SweepAbilities(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    LIMIT = None
    ONLY = None

    async def test_sweep(self):
        import os
        only = os.environ.get('SWEEP_ONLY')
        limit = os.environ.get('SWEEP_LIMIT')
        for case in CASES:
            if only and case.name not in only.split(','):
                continue
            checked, failures, skipped = await run_sweep(self, case, limit=int(limit) if limit else None)
            print(f"{case.name}: checked {checked}, failures {len(failures)}, skipped {len(skipped)}")


if __name__ == "__main__":
    unittest.main()
