"""Sweep: Abilities used / applied from the Bench vs the Active Spot.

Question: every Pokémon Ability whose text does NOT put a condition on THIS
Pokémon's own position must work from the Bench as well as from the Active
Spot; Abilities that say "if this Pokémon is in the Active Spot / your Active
Pokémon" must NOT work from the Bench, and "if this Pokémon is on your Bench"
Abilities must NOT work from the Active Spot.  "Your Active Pokémon" as a
TARGET ("heal 30 damage from your Active Pokémon") is no position condition.

Scope: every GLC-legal Pokémon printing with at least one Ability.  Identical
(title, normalised text) pairs are tested once (all printings are listed in
the report).  Abilities used from the hand / discard pile are out of scope.

Method per Ability kind (structure of the scripted Ability):
  activated   (Ability.activation set)  -- a rich, seeded board (cards of every
              kind in hand / deck / discard, damaged Pokémon with Energy on both
              sides) built twice, identical except that the card under test and
              a filler swap Active <-> Bench.  We record whether the Ability is
              offered and whether using it changes the game state (board
              fingerprint).  Up to N_VARIANTS boards (stadium / prize count /
              hand size / Special Conditions vary) until it is offered somewhere.
  passive     (Ability.passive set) -- every overridden Passive hook is probed
              with the card Active and with it Benched, over every role on the
              board (each Pokémon as target / attacker, both players, a Damage
              calculation for each attacker/target pair, cards in hand, ...).
              A hook answer that differs from the base-class default is an
              "effect".  Effects that need the card itself to attack / retreat
              (its own damage, attack cost, retreat cost) are not comparable
              from the Bench and are ignored for the Bench-vs-Active verdict.
  triggered   on_evolve (evolve a Benched vs an Active pre-evolution),
              on_energy_attached (attach from hand to the Benched vs the Active
              card), between_turns (Pokémon Checkup), end_of_turn.  The trigger
              is spied (did the engine call it?) and the state change is
              compared with a run where the effect is replaced by a no-op.
  attacked    texts about THIS Pokémon being damaged / Knocked Out by an attack
              (Rough Skin family, damage prevention/reduction, KO riders): the
              opponent's Lopunny (ME1 108) hits the card in the Active Spot (Spiral
              Kick, 60) or on the Bench (Dashing Kick, 50 to a Benched Pokémon); the
              outcome is compared with a run where the Ability is switched off.
              Passives with "whenever you attach an Energy ... from your hand" are
              run as attach triggers too (by the opponent for "your opponent attaches").
  Other triggers (on_play is Bench-only by nature; moving into / out of the
  Active Spot, being drawn / discarded / taken as a Prize are transitions, not
  positions) are listed as not tested.
  Compound texts are judged per sentence (Stoutland: evolve half unrestricted,
  Knocked Out half Active-only).

Verdicts: ok | parity (offered from both, no observable change from either) |
bug | untested (could not set up / no observable effect) | self_only (only
affects the card's own attacks/retreat) | out_of_scope.
Known bugs are pinned by BenchVsActiveScenarios (expected failures).

Run:  cd /home/claude/work && PYTHONPATH=/home/claude/stubs:. python3 -m unittest tests.test_sweep_bench_abilities
Report: /home/claude/bughunt/sweep/bench_abilities.json
"""
import asyncio
import collections
import inspect
import json
import os
import random
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import norm, REPORT_DIR
from spirit.game import glc
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage
from spirit.game.data_utils import (CARD_DEFS_BY_GUID, PokemonCardDef, Attack, def_for,
                                    SupporterCardDef, ItemCardDef, StadiumCardDef,
                                    PokemonToolCardDef, EnergyCardDef, _string_attr,
                                    Triggers)
from spirit.game.models.board import PokemonEntity
from spirit.game.session import passives as P
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import (DamageCalc, Passive, effective_max_hp,
                                          compute_damage, effective_retreat_cost)
from spirit.tools.effect_smoke import P1, P2

N_VARIANTS = 5
TYPES = [PokemonTypes.GRASS, PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.LIGHTNING,
         PokemonTypes.PSYCHIC, PokemonTypes.FIGHTING, PokemonTypes.DARKNESS, PokemonTypes.METAL]
CONDITIONS = ['Asleep', 'Burned', 'Confused', 'Paralyzed', 'Poisoned']
from spirit.game.attributes import SpecialConditions
COND_ENUMS = [SpecialConditions.ASLEEP, SpecialConditions.BURNED, SpecialConditions.CONFUSED,
              SpecialConditions.PARALYZED, SpecialConditions.POISONED]


# ------------------------------------------------------------ classification --
TP = r"(?:this pokémon|this card|it)"
ACTIVE_RX = re.compile(
    r"(?:if|as long as|while|when) " + TP + r" is (?:in the active spot|your active pokémon|active)"
    r"|" + TP + r" (?:is|was) (?:in the active spot|your active pokémon)"
    r"|if this pokémon was on the bench and became your active pokémon")
BENCH_RX = re.compile(
    r"(?:if|as long as|as along as|while|when) " + TP + r" is on (?:your|the) bench"
    r"|while on your bench|" + TP + r" is benched")
# Wordings that can only do something from the Bench although they don't say so.
IMPLICIT_BENCH_RX = re.compile(r"switch this pokémon with your active pokémon"
                               r"|from your active pokémon to this pokémon"
                               r"|move your active pokémon to your bench and play this pokémon")
SELF_ATTACK_RX = re.compile(r"^(?:this pokémon's attacks|attacks used by this pokémon)")


ACTIVE_BONUS_RX = re.compile(
    r"\. if this pokémon is (?:your active pokémon|in the active spot), [^.]*\b(?:more|instead|also)\b")


def position_class(text):
    a, b = bool(ACTIVE_RX.search(text)), bool(BENCH_RX.search(text))
    if a and not b and ACTIVE_BONUS_RX.search(text):
        return 'active_bonus'
    if a and b:
        return 'mixed'
    if a:
        return 'active'
    if b:
        return 'bench'
    if IMPLICIT_BENCH_RX.search(text):
        return 'implicit_bench'
    return 'any'


def pos_for(text, rx):
    """Position class of only the sentences a check exercises (compound texts:
    Stoutland "When you play this Pokémon ... to evolve ..., you may ... . If this
    Pokémon is your Active Pokémon and is Knocked Out ..., you may ...")."""
    sents = re.split(r"(?<=\.)\s+", text)
    rel = [x for x in sents if rx.search(x)]
    if rel and len(rel) < len(sents):
        return position_class(' '.join(rel))
    return position_class(text)


EVOLVE_SENT_RX = re.compile(r"to evolve")


def ability_kind(a):
    if a.usable_from:
        return 'out_of_play'
    if a.is_rule_action:
        return 'rule'
    trig = a.trigger
    trig = tuple(trig) if isinstance(trig, (list, tuple, set, frozenset)) else ((trig,) if trig else ())
    if a.activation:
        return 'activated'
    if trig:
        return 'trigger:' + ','.join(sorted(trig))
    if a.passive is not None:
        return 'passive'
    return 'none'


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


_GROUPS = None


def groups():
    """[(title, text, kind, [(def, ability), ...])] for GLC-legal printings."""
    global _GROUPS
    if _GROUPS is None:
        out = collections.OrderedDict()
        for d in sorted(CARD_DEFS_BY_GUID.values(),
                        key=lambda d: (d.set_code, str(d.collector_number), d.guid)):
            if not isinstance(d, PokemonCardDef) or not glc.is_glc_legal(d):
                continue
            for a in d.abilities or []:
                if isinstance(a, Attack):
                    continue
                key = (a.title, norm(a.game_text), ability_kind(a))
                out.setdefault(key, []).append((d, a))
        _GROUPS = [(k[0], k[1], k[2], v) for k, v in out.items()]
    return _GROUPS


def label(d):
    return f"{d.display_name} ({d.set_code} {d.collector_number})"


def stage_of(d):
    spec = d.extra_attributes.get(str(AttrID.STAGE.value))
    return spec.get('value') if isinstance(spec, dict) else None


def types_of(d):
    spec = d.extra_attributes.get(str(AttrID.POKEMON_TYPES.value))
    return json.loads(spec['value']) if isinstance(spec, dict) else []


# ------------------------------------------------------------------ card pool --
_POOL = {}


def pool(test):
    if _POOL:
        return _POOL
    defs = sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, str(d.collector_number), d.guid))
    legal = [d for d in defs if glc.is_glc_legal(d)]

    def plain(d):
        return isinstance(d, PokemonCardDef) and not has_ability(d) \
            and not getattr(d, 'unplayable_from_hand', False)
    by_type = {}
    for d in legal:
        if plain(d) and stage_of(d) == PokemonStage.BASIC and len(types_of(d)) == 1:
            by_type.setdefault(types_of(d)[0], d)
    _POOL['basic_by_type'] = by_type
    _POOL['stage1'] = next(d for d in legal if plain(d) and stage_of(d) == PokemonStage.STAGE1)
    _POOL['stage2'] = next(d for d in legal if plain(d) and stage_of(d) == PokemonStage.STAGE2)
    _POOL['supporter'] = next(d for d in legal if type(d) is SupporterCardDef)
    _POOL['stadium'] = next(d for d in legal if type(d) is StadiumCardDef
                            and getattr(d, 'passive', None) is None and not d.abilities)
    _POOL['tool'] = next(d for d in legal if type(d) is PokemonToolCardDef
                         and getattr(d, 'passive', None) is None
                         and not getattr(d, 'granted_abilities', None))
    _POOL['special_energy'] = next(
        d for d in legal if isinstance(d, EnergyCardDef)
        and str(AttrID.IS_SPECIAL_ENERGY.value) in d.extra_attributes
        and getattr(d, 'attach_to', None) is None and getattr(d, 'attach_condition', None) is None
        and getattr(d, 'passive', None) is None)
    _POOL['energy'] = {k: CARD_DEFS_BY_GUID[test.energies[k.value].lower()]
                       for k in TYPES if k.value in test.energies}
    return _POOL


def pre_evolution(d):
    from_name = _string_attr(d, AttrID.EVOLUTION_LOGIC_FROM)
    if not from_name:
        return None
    best = None
    for c in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number))):
        if isinstance(c, PokemonCardDef) and _string_attr(c, AttrID.EVOLUTION_LOGIC_NAME) == from_name:
            if not has_ability(c):
                return c
            best = best or c
    return best


def evolution_of(d):
    name = _string_attr(d, AttrID.EVOLUTION_LOGIC_NAME)
    for c in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number))):
        if isinstance(c, PokemonCardDef) and _string_attr(c, AttrID.EVOLUTION_LOGIC_FROM) == name \
                and glc.is_glc_legal(c):
            return c
    return None


_NAMES = None


_NAMED_CACHE = {}


def named_cards(d):
    if d.guid not in _NAMED_CACHE:
        _NAMED_CACHE[d.guid] = _named_cards(d)
    return _NAMED_CACHE[d.guid]


def _named_cards(d):
    """Cards named in the Ability texts ("1 of your Lunatone", "a Misty's
    Favor card", "Leftovers"): [(def, is_pokemon)], at most 4."""
    global _NAMES
    if _NAMES is None:
        _NAMES = {}
        for c in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number))):
            if not glc.is_glc_legal(c):
                continue
            n = norm(c.display_name or '')
            if len(n) < 4:
                continue
            old = _NAMES.get(n)
            if old is None or (isinstance(c, PokemonCardDef) and has_ability(old) and not has_ability(c)):
                _NAMES[n] = c
    text = ' '.join(norm(a.game_text) for a in d.abilities if not isinstance(a, Attack))
    own = norm(d.display_name or '')
    out = []
    for n, c in _NAMES.items():
        if n != own and n in text and re.search(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", text):
            out.append(c)
    # longest names first ("Wishiwashi-GX" before "Wishiwashi")
    out.sort(key=lambda c: -len(c.display_name or ''))
    return out[:4]


def named_partner(d):
    return next((c for c in named_cards(d) if isinstance(c, PokemonCardDef)), None)


def own_type(d):
    ts = types_of(d)
    for v in ts:
        try:
            k = PokemonTypes(v)
        except ValueError:
            continue
        if k in TYPES:
            return k
    return PokemonTypes.WATER


# ----------------------------------------------------------------- the table --
class BenchTable(Table):
    """Table with scripted menus (EffectContext.choose & co.)."""

    def __init__(self, test, **k):
        super().__init__(test, **k)
        self.choice = 0

    def _patches(self):
        table = self

        async def choose(ctx, prompt, buttons, player_id=None, descriptions=None, use_panel=True):
            return table.choice if table.choice < len(buttons) else 0

        async def present_card_choice(ctx, card, prompt, buttons, player_id=None):
            return 0

        async def flip_until_tails(ctx, title=''):
            return 1
        return super()._patches() + [
            patch.object(EffectContext, 'choose', choose),
            patch.object(EffectContext, 'flip_until_tails', flip_until_tails),
            patch.object(EffectContext, 'present_card_choice', present_card_choice)]


def neutral(p):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    return p


def damage(t, p, amount):
    p.set_attribute(AttrID.HP, max(10, effective_max_hp(t.board, p) - amount))


def clear(t, pid, zone):
    area = t.board.find_player_area(pid, {'deck': 'deck', 'hand': 'hand', 'discard': 'discard',
                                          'prizes': 'prizePile'}[zone])
    for c in list(area.children):
        area.remove_child(c)


class Board:
    pass


def rich_board(test, d, where, variant, *, card_zone=None, alt_a=None):
    """Seeded rich board.  where = 'active' | 'bench' : position of `d`.
    Both positions of the same variant are identical except that `d` and the
    filler A swap places.  card_zone='hand' puts `d` in hand instead (its
    pre-evolution then takes its place)."""
    rng = random.Random(1000 * variant + 7)
    pl = pool(test)
    t = BenchTable(test)
    t.choice = 0
    b = Board()
    b.t = t
    mine = own_type(d)
    other = TYPES[(TYPES.index(mine) + 3) % len(TYPES)]
    basics = pl['basic_by_type']
    e = pl['energy']
    pre, evo = pre_evolution(d), evolution_of(d)

    def mix(n_extra_filler=0):
        specs = [e[k] for k in TYPES if k in e] * 2
        specs += [basics[k] for k in sorted(basics)][:6]
        specs += [pl['stage1'], pl['stage2'], pl['supporter'], pl['tool'], pl['stadium'],
                  pl['special_energy'], test.item, test.item, d]
        if pre is not None:
            specs.append(pre)
        if evo is not None:
            specs.append(evo)
        specs += named_cards(d)
        specs += [test.item] * n_extra_filler
        return specs

    # P1 zones
    clear(t, P1, 'deck')
    deck = mix(12)
    rng.shuffle(deck)
    for s in deck:
        t.put(s, P1, 'deck')
    for s in mix():
        t.put(s, P1, 'discard')
    hand = [e[k] for k in TYPES if k in e] + [e[mine], test.item, pl['supporter'],
            pl['tool'], pl['stadium'], basics.get(mine.value, test.filler), pl['special_energy']]
    named = named_cards(d)
    hand += [c for c in named if not isinstance(c, PokemonCardDef) or stage_of(c) == PokemonStage.BASIC]
    if pre is not None:
        hand.append(pre)
    if evo is not None:
        hand.append(evo)
    hand.append(d)
    if variant == 2:
        hand = []
    elif variant == 4:
        hand = [e[mine], e[other], d]
    for s in hand:
        t.put(s, P1, 'hand')
    t.set_prizes(P1, [6, 4, 2, 1, 3][variant % 5])
    # P2 zones
    clear(t, P2, 'deck')
    deck2 = mix(12)
    rng.shuffle(deck2)
    for s in deck2:
        t.put(s, P2, 'deck')
    for s in mix():
        t.put(s, P2, 'discard')
    for s in [e[other], test.item, pl['supporter'], basics.get(other.value, test.filler), pl['tool']]:
        t.put(s, P2, 'hand')
    t.set_prizes(P2, [6, 3, 5, 2, 4][variant % 5])
    if variant == 1:
        t.stadium(pl['stadium'], P1)
    elif variant == 3:
        t.stadium(pl['stadium'], P2)

    # P1 in play.  Slot 0 = Active.
    filler_a = alt_a or test.filler
    ally_b = basics.get((types_of(d) or [mine.value])[0], basics.get(mine.value, test.filler))
    ally_c = named_partner(d) or basics.get(other.value, test.filler)
    card_spec = pre if card_zone == 'hand' else d
    if where == 'active':
        b.me = t.put(card_spec, P1, 'active')
        b.a = t.put(filler_a, P1, 'bench')
    else:
        b.a = t.put(filler_a, P1, 'active')
        b.me = t.put(card_spec, P1, 'bench')
    b.b = t.put(ally_b, P1, 'bench')
    b.c = t.put(ally_c, P1, 'bench')
    for i, (p, k) in enumerate(((b.me, mine), (b.a, mine), (b.b, mine), (b.c, other))):
        neutral(p)
        t.energy(p, k, 2)
        if variant == 0 and p is b.me:
            for kk in TYPES:
                if kk != k:
                    t.energy(p, kk, 1)
        else:
            t.energy(p, TYPES[(3 * i + variant) % len(TYPES)], 1)
            t.energy(p, TYPES[(3 * i + 1 + variant) % len(TYPES)], 1)
        damage(t, p, 30 if variant != 2 else 50)
    if variant == 3:
        for extra in [basics[k] for k in sorted(basics)][:2]:
            neutral(t.put(extra, P1, 'bench'))
    if variant == 3:
        t.energy(b.me, mine, 2)
        t.attach(pl['special_energy'], b.me)
    if variant == 1:
        t.attach(pl['tool'], b.a)
    if variant == 2:
        t.active(P1).set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned', 'Confused'])
    # P2 in play
    b.opp = neutral(t.put(test.filler, P2, 'active'))
    b.opp_b = neutral(t.put(basics.get(other.value, test.filler), P2, 'bench'))
    b.opp_c = neutral(t.put(pl['stage1'], P2, 'bench'))
    for p in (b.opp, b.opp_b, b.opp_c):
        t.energy(p, PokemonTypes.WATER, 2)
        t.energy(p, other, 1)
        damage(t, p, 40)
    t.attach(pl['special_energy'], b.opp)
    if variant in (1, 3):
        t.attach(pl['tool'], b.opp)
    if variant == 3:
        b.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])
    elif variant == 1:
        b.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned', 'Confused'])
    if card_zone == 'hand':
        b.pre = b.me
        b.me = t.put(d, P1, 'hand')
    return b


# ------------------------------------------------------------- fingerprints --
_SKIP_STATE = {'used_abilities', 'used_named_abilities'}


def _ent(t, c):
    out = [c.archetype_id]
    if isinstance(c, PokemonEntity):
        out += [c.get_attribute(AttrID.HP), tuple(sorted(c.get_attribute(AttrID.SPECIAL_CONDITIONS) or []))]
    out.append(tuple(sorted(_ent(t, ch) for ch in c.children)))
    return tuple(str(x) for x in out)


def fingerprint(t):
    fp = []
    for pid in (P1, P2):
        for zone in ('active', 'bench', 'hand', 'deck', 'discard', 'prizes', 'lostZone'):
            try:
                cards = t.zone(pid, zone)
            except Exception:
                continue
            fp.append((pid, zone, tuple(sorted(_ent(t, c) for c in cards))))
    st = t.board.find_global_area('activeStadium')
    fp.append(('stadium', tuple(sorted(_ent(t, c) for c in (st.children if st else [])))))
    fp.append(('temp', len(getattr(t.board, 'temporary_passives', None) or [])))
    state = t.state
    ids = {}

    def walk(node):
        for ch in getattr(node, 'children', []) or []:
            eid = getattr(ch, 'entity_id', None)
            if eid:
                arch = getattr(ch, 'archetype_id', None)
                dd = def_for(arch) if arch else None
                ids[str(eid)] = f"<{getattr(dd, 'display_name', '') or ch.__class__.__name__}>"
            walk(ch)
    for pid in (P1, P2):
        for zone in ('active', 'bench', 'hand', 'deck', 'discard', 'prizes', 'lostZone'):
            try:
                area = t.board.find_player_area(pid, {'active': 'activePokemonArea', 'prizes': 'prizePile'}
                                                .get(zone, zone))
            except Exception:
                area = None
            if area is not None:
                walk(area)
    rx = re.compile('|'.join(re.escape(i) for i in sorted(ids, key=len, reverse=True))) if ids else None
    for k, v in sorted(vars(state).items()):
        if k in _SKIP_STATE or k.startswith('_'):
            continue
        try:
            r = repr(v)
            if rx is not None:
                r = rx.sub(lambda m: ids[m.group(0)], r)
            r = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<?>", r)
            if isinstance(v, (set, frozenset, dict, list, tuple)):
                r = str(sorted(re.findall(r"<[^>]*>|\w+", r)))
            fp.append((k, r[:400]))
        except Exception:
            pass
    return fp


def fp_diff(a, b):
    da, db = dict((x[0] if len(x) == 2 else (x[0], x[1]), x[-1]) for x in a), \
        dict((x[0] if len(x) == 2 else (x[0], x[1]), x[-1]) for x in b)
    return sorted(str(k) for k in set(da) | set(db) if da.get(k) != db.get(k))


async def run_guarded(coro, timeout=3):
    return await asyncio.wait_for(coro, timeout)


# --------------------------------------------------------- activated sweep --
def find_ability(d, title):
    return next(a for a in d.abilities if not isinstance(a, Attack) and a.title == title)


async def activated_trial(test, d, ability, where, variant, alt_a=None):
    """-> dict(offered, called, changed, error, diff)"""
    random.seed(4242 + variant)
    b = rich_board(test, d, where, variant, alt_a=alt_a)
    t = b.t
    res = {'offered': False, 'called': False, 'changed': False, 'error': None, 'diff': []}
    entry = t.ability_offer(b.me, ability.title)
    if entry is None:
        return res, b
    res['offered'] = True
    called = []
    real = ability.effect

    async def spy(ctx, *a, **k):
        called.append(True)
        return await real(ctx, *a, **k)
    before = fingerprint(t)
    random.seed(99 + variant)
    try:
        with patch.object(ability, 'effect', spy):
            await run_guarded(t.do(entry))
    except asyncio.TimeoutError:
        res['error'] = 'timeout'
    except Exception as ex:
        res['error'] = f"{type(ex).__name__}: {ex}"[:300]
    res['called'] = bool(called)
    after = fingerprint(t)
    res['diff'] = fp_diff(before, after)[:12]
    res['changed'] = bool(res['diff'])
    return res, b


def short(r):
    return ('offered' if r['offered'] else 'not offered') + \
        ((', changed' if r['changed'] else ', no change') if r['offered'] else '') + \
        (f", error {r['error']}" if r['error'] else '')


async def check_activated(test, d, ability, pos):
    """-> (verdict, detail) verdict: ok | bug | untested."""
    log = []
    both = [False]
    for v in range(N_VARIANTS):
        ra, _ = await activated_trial(test, d, ability, 'active', v)
        rb, _ = await activated_trial(test, d, ability, 'bench', v)
        log.append(f"v{v}: Active {short(ra)} | Bench {short(rb)}")
        if pos in ('any', 'active_bonus'):
            if (ra['offered'] and not rb['offered']) or (ra['changed'] and not rb['changed']):
                # The Active partner may be what the Ability needs ("your Active
                # Grass Pokémon"): retry with a same-type partner / a 2nd copy.
                confirmed = True
                for alt in (pool(test)['basic_by_type'].get((types_of(d) or [0])[0]), d):
                    if alt is None:
                        continue
                    rb2, _ = await activated_trial(test, d, ability, 'bench', v, alt_a=alt)
                    if rb2['changed'] or (rb2['offered'] and not ra['changed']):
                        confirmed = False
                        log.append(f"  retry with Active {alt.display_name}: Bench {short(rb2)}")
                        break
                if confirmed and not rb['offered']:
                    return 'bug', f"offered from the Active Spot but not from the Bench ({log[-1]})"
                if confirmed and not rb['error']:
                    return 'bug', f"does something from the Active Spot, nothing from the Bench ({log[-1]})"
                if not confirmed:
                    return 'ok', ' '.join(log[-2:])
            if rb['error'] and not ra['error']:
                return 'bug', f"crashes from the Bench ({log[-1]})"
            if ra['changed'] and rb['changed']:
                return 'ok', log[-1]
            if rb['changed'] and not ra['offered']:
                return 'ok', log[-1]
        elif pos == 'active':
            if rb['offered']:
                return 'bug', f"Active-only Ability offered from the Bench ({log[-1]})"
            if ra['offered']:
                return 'ok', log[-1]
        elif pos in ('bench', 'implicit_bench'):
            if ra['offered'] and (pos == 'bench' or ra['changed']):
                return 'bug', f"Bench-only Ability offered from the Active Spot ({log[-1]})"
            if rb['changed']:
                return 'ok', log[-1]
        both[0] = both[0] or (pos in ('any', 'active_bonus') and ra['offered'] and rb['offered'])
    if both[0]:
        return 'parity', 'offered from both positions, no observable change from either: ' + '; '.join(log)
    return 'untested', '; '.join(log)


# ------------------------------------------------------------ passive probe --
SELF_ONLY_POKEMON_HOOKS = {
    'modify_attack_cost', 'modify_attack_cost_for_attack', 'modify_retreat_cost', 'blocks_retreat',
    'blocks_attacks', 'attacks_despite_conditions', 'attacks_on_first_turn',
    'ignores_defender_effects', 'retreats_despite_conditions', 'granted_attacks',
    'attack_keeps_turn', 'offers_attack_coin_reroll', 'retreat_cost_destination',
    'counters_on_active_to_bench',
}
CALC_HOOKS = ('modify_damage_dealt', 'modify_weakness', 'modify_resistance',
              'modify_damage_taken', 'prevents_damage')
SKIP_HOOKS = {'player_visualizations'}


def _calc_state(c):
    return (c.amount, c.weakness_applies, c.resistance_applies, c.prevented,
            c.weakness_multiplier, tuple(c.weak_types), c.resistance_reduction)


def roles(b, where):
    """name -> entity for every Pokémon in play; the card under test is 'me'."""
    t = b.t
    r = {'me': b.me}
    for pid, side in ((P1, 'ally'), (P2, 'opp')):
        for i, p in enumerate(t.board.pokemon_in_play(pid)):
            if p is b.me:
                continue
            dd = def_for(p.archetype_id)
            pos = 'active' if p is t.active(pid) else f'bench{i}'
            r[f"{side}_{pos}:{dd.display_name}"] = p
    return r


def probe_values(t, b, rmap):
    """Generic argument pools by parameter name."""
    hands = {f"{pid}:{def_for(c.archetype_id).display_name}": c
             for pid in (P1, P2) for c in t.zone(pid, 'hand')}
    energies = {}
    tools = {}
    for name, p in rmap.items():
        for ch in p.children:
            if ch.get_attribute(AttrID.IS_SPECIAL_ENERGY) or isinstance(def_for(ch.archetype_id), EnergyCardDef):
                energies.setdefault(f"{name}:energy:{def_for(ch.archetype_id).display_name}", ch)
            elif isinstance(def_for(ch.archetype_id), PokemonToolCardDef):
                tools[f"{name}:tool"] = ch
    return hands, energies, tools


POKEMON_PARAMS = {'pokemon', 'target', 'evolved', 'attacker', 'defender', 'receiver', 'ko_pokemon'}
PLAYER_PARAMS = {'player_id', 'attaching_player_id', 'mover_player_id', 'affected_player_id',
                 'acting_player_id', 'owner_id', 'benching_player_id'}


def probe_passive(passive, carrier, b):
    """{key: value} for every hook answer that differs from the default."""
    t = b.t
    board = t.board
    rmap = roles(b, None)
    name_of = {id(v): k for k, v in rmap.items()}
    hands, energies, tools = probe_values(t, b, rmap)
    out = {}
    errors = []
    cls = type(passive)
    attack = next((a for a in (def_for(b.opp.archetype_id).abilities or []) if isinstance(a, Attack)), None)
    my_attack = next((a for a in (def_for(t.active(P1).archetype_id).abilities or [])
                      if isinstance(a, Attack)), None)
    ctx2 = EffectContext(t.session, P2, b.opp, attack)
    ctx1 = EffectContext(t.session, P1, t.active(P1), my_attack)
    for hook, base_fn in inspect.getmembers(Passive, predicate=inspect.isfunction):
        if hook.startswith('_') or hook in SKIP_HOOKS:
            continue
        fn = getattr(cls, hook, None)
        if fn is None or fn is base_fn:
            continue
        params = [p for p in inspect.signature(base_fn).parameters if p not in ('self',)]
        if hook in CALC_HOOKS:
            for an, att in rmap.items():
                for tn, tgt in rmap.items():
                    if att is tgt or att.owning_player_id == tgt.owning_player_id:
                        continue
                    saved = tgt.get_attribute(AttrID.WEAKNESS_TYPES)
                    tgt.set_attribute(AttrID.WEAKNESS_TYPES, list(att.get_attribute(AttrID.POKEMON_TYPES) or []))
                    for base in (60,):
                        c1 = DamageCalc(board, att, tgt, base, apply_modifiers=(tgt is t.active(tgt.owning_player_id)))
                        c1.weak_types = list(att.get_attribute(AttrID.POKEMON_TYPES) or [])
                        c0 = DamageCalc(board, att, tgt, base, apply_modifiers=c1.apply_modifiers)
                        c0.weak_types = list(c1.weak_types)
                        try:
                            r = getattr(passive, hook)(c1, carrier)
                        except Exception as ex:
                            errors.append(f"{hook}: {type(ex).__name__}: {ex}"[:200])
                            continue
                        if (r not in (None, False)) or _calc_state(c1) != _calc_state(c0):
                            out[(hook, an, tn)] = (repr(r), _calc_state(c1)[:4])
                    tgt.set_attribute(AttrID.WEAKNESS_TYPES, saved)
            continue
        if hook == 'blocks_trainer_effects':
            for hn, card in hands.items():
                tt = card.get_attribute(AttrID.TRAINER_TYPE)
                if tt is None:
                    continue
                for apn, ap in (('P1', P1), ('P2', P2)):
                    if card.owning_player_id == ap:
                        continue
                    for en, ent in list(rmap.items()) + [('none', None)]:
                        try:
                            r1 = passive.blocks_trainer_effects(ap, card, tt, carrier, ent, board)
                        except Exception as ex:
                            errors.append(f"{hook}: {type(ex).__name__}: {ex}"[:200])
                            continue
                        if r1:
                            out[(hook, apn, hn, en)] = repr(r1)
            continue
        if hook == 'modify_energy_provided':
            for en, energy in energies.items():
                holder = energy.parent
                opts = P.energy_provided_options(None, energy)
                try:
                    r1 = passive.modify_energy_provided(opts, energy, holder, board, carrier)
                    r0 = base_fn(passive, opts, energy, holder, board, carrier)
                except Exception as ex:
                    errors.append(f"{hook}: {type(ex).__name__}: {ex}"[:200])
                    continue
                if repr(r1) != repr(r0):
                    out[(hook, en)] = repr(r1)[:80]
            continue
        # Build argument combinations (small cartesian products).
        pools = []
        ok = True
        for p in params:
            if p == 'carrier':
                pools.append([('carrier', carrier)])
            elif p == 'board':
                pools.append([('board', board)])
            elif p in POKEMON_PARAMS:
                pools.append(list(rmap.items()))
            elif p in PLAYER_PARAMS:
                pools.append([('P1', P1), ('P2', P2)])
            elif p == 'cost' and 'retreat' in hook:
                pools.append([('2', 2)])
            elif p == 'cost':
                pools.append([("{C3}", {'Colorless': 3}), ("{W1C2}", {'Water': 1, 'Colorless': 2}),
                              ("{Y1C2}", {'Fairy': 1, 'Colorless': 2}),
                              ("{all}", {'Grass': 1, 'Fire': 1, 'Water': 1, 'Lightning': 1, 'Psychic': 1,
                                         'Fighting': 1, 'Darkness': 1, 'Metal': 1, 'Fairy': 1,
                                         'Dragon': 1, 'Colorless': 2})])
            elif p == 'condition':
                pools.append([(c.name, c) for c in COND_ENUMS])
            elif p == 'card':
                pools.append(list(hands.items()))
            elif p == 'energy':
                pools.append(list(energies.items()))
            elif p == 'tool':
                pools.append(list(tools.items()) or [('none', None)])
            elif p == 'attack':
                pools.append([('attack', attack)])
            elif p == 'ability':
                ab = next((a for a in (def_for(carrier.archetype_id).abilities or [])
                           if not isinstance(a, Attack)), None)
                pools.append([('ability', ab)])
            elif p in ('types', 'current_types', 'pokemon_types'):
                pools.append([('types', [PokemonTypes.COLORLESS.value])])
            elif p in ('counters', 'amount', 'count', 'coins'):
                pools.append([('2', 2)])
            elif p in ('provided', 'options'):
                pools.append([('prov', None)])
            elif p == 'holder':
                pools.append([('holder', None)])
            elif p == 'ctx':
                pools.append([('ctxP2', ctx2), ('ctxP1', ctx1)])
            elif p == 'trainer_type':
                pools.append([('ttype', None)])
            elif p in ('trainer_card',):
                pools.append([(k, v) for k, v in hands.items()
                              if isinstance(def_for(v.archetype_id), (ItemCardDef, SupporterCardDef))])
            elif p == 'trainer_type':
                pools.append([('ttype', None)])
            elif p == 'affected_entity':
                pools.append(list(rmap.items()) + [('none', None)])
            elif p in ('evolution_card', 'pre_evolution'):
                pools.append([('evo', None)])
            elif p == 'from_hand':
                pools.append([('fh', True)])
            else:
                ok = False
                break
        if not ok:
            continue
        combos = [[]]
        for pool_ in pools:
            combos = [c + [x] for c in combos for x in pool_][:200]
        for combo in combos:
            args = [v for _, v in combo]
            key = (hook,) + tuple(n for n, _ in combo if n not in ('carrier', 'board'))
            try:
                r1 = getattr(passive, hook)(*args)
                r0 = base_fn(passive, *args)
            except Exception as ex:
                errors.append(f"{hook}: {type(ex).__name__}: {ex}"[:200])
                continue
            if inspect.isawaitable(r1) or inspect.isawaitable(r0):
                for r in (r0, r1):
                    if inspect.isawaitable(r):
                        r.close()
                continue
            if repr(r1) != repr(r0):
                out[key] = repr(r1)[:120]
    return out, errors


def self_only(key):
    """Effects that need the card itself to attack / retreat."""
    hook = key[0]
    if hook == 'engine':
        kind = key[1]
        if kind in ('retreat', 'attack_cost') and key[2] == 'me':
            return True
        if kind == 'blocked' and key[2] == 'me':
            return False
        if kind == 'damage' and key[2] == 'me':
            return True
        return False
    if hook == 'action':
        # (action, pid, kind, who, description, title)
        return key[3] == 'me' and key[4] in ('UsePokemonAttack', 'RetreatPokemon', 'Retreat', 'BaseRetreat')
    if hook in CALC_HOOKS:
        return key[1] == 'me' and hook in ('modify_damage_dealt', 'modify_weakness', 'modify_resistance')
    if hook in SELF_ONLY_POKEMON_HOOKS:
        return 'me' in key[1:]
    return False


_BY_STAGE_TYPE = {}


def by_stage_type(stage, kind):
    if not _BY_STAGE_TYPE:
        for c in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number), x.guid)):
            if isinstance(c, PokemonCardDef) and glc.is_glc_legal(c) and not has_ability(c) \
                    and len(types_of(c)) == 1:
                _BY_STAGE_TYPE.setdefault((stage_of(c), types_of(c)[0]), c)
    return _BY_STAGE_TYPE.get((stage, kind.value if hasattr(kind, 'value') else kind))


ALL_TYPES = TYPES + [PokemonTypes.FAIRY, PokemonTypes.DRAGON, PokemonTypes.COLORLESS]


def probe_board(test, d, where, variant):
    """Board for hook probes: 6 Pokémon a side, many types / stages / states.
    Identical for both positions except the card and P1's first Pokémon swap."""
    pl = pool(test)
    e = pl['energy']
    t = BenchTable(test)
    b = Board()
    b.t = t
    mine = own_type(d)
    rot = (variant * 3) % len(ALL_TYPES)
    kinds = ALL_TYPES[rot:] + ALL_TYPES[:rot]
    stages = [PokemonStage.BASIC, PokemonStage.STAGE1, PokemonStage.BASIC, PokemonStage.STAGE2,
              PokemonStage.BASIC, PokemonStage.STAGE1]

    def make(i, side):
        kind = kinds[(i + (0 if side == P1 else 6)) % len(kinds)]
        st = stages[(i + variant) % len(stages)]
        return by_stage_type(st, kind) or by_stage_type(PokemonStage.BASIC, kind) or test.filler
    named = named_cards(d)
    named_poke = [c for c in named if isinstance(c, PokemonCardDef)]
    named_other = [c for c in named if not isinstance(c, PokemonCardDef)]
    p1 = [make(i, P1) for i in range(5)]
    if named_poke:
        p1[1] = named_poke[0]
        if len(named_poke) > 1:
            p1[2] = named_poke[1]
        if len(named_poke) > 2:
            p1[3] = named_poke[2]
    if variant == 4:
        p1[2] = d               # a 2nd copy (e.g. "at least 1 other Bouffalant")
    if where == 'active':
        b.me = t.put(d, P1, 'active')
        others = [t.put(s_, P1, 'bench') for s_ in p1]
    else:
        others = [t.put(p1[0], P1, 'active'), None] + []
        b.me = t.put(d, P1, 'bench')
        others = [others[0]] + [t.put(s_, P1, 'bench') for s_ in p1[1:]]
    opp = [t.put(make(i, P2), P2, 'active' if i == 0 else 'bench') for i in range(6)]
    if named_poke:
        pass
    for i, p in enumerate(others + opp):
        neutral(p)
        kt = types_of(def_for(p.archetype_id))
        kk = PokemonTypes(kt[0]) if kt and PokemonTypes(kt[0]) in e else TYPES[i % len(TYPES)]
        t.energy(p, kk, 1)
        t.energy(p, TYPES[(i + variant) % len(TYPES)], 1)
        if (i + variant) % 3 == 0:
            damage(t, p, 30)
    neutral(b.me)
    # the card's own state per variant
    if variant == 0:
        for kk in TYPES:
            t.energy(b.me, kk, 1)
    elif variant == 1:
        pass                                     # no Energy, full HP
    elif variant == 2:
        t.energy(b.me, mine, 6)
        b.me.set_attribute(AttrID.HP, 50)
    elif variant == 3:
        t.energy(b.me, mine, 2)
        t.attach(pl['special_energy'], b.me)
        damage(t, b.me, 30)
    else:
        t.energy(b.me, mine, 1)
    for c in named_other:
        if isinstance(c, PokemonToolCardDef) or isinstance(c, EnergyCardDef):
            try:
                t.attach(c, b.me)
            except Exception:
                pass
    if variant == 3 and not any(isinstance(c, PokemonToolCardDef) for c in named_other):
        t.attach(pl['tool'], b.me)
    conds = {1: ['Poisoned', 'Confused'], 2: ['Asleep', 'Burned'], 3: ['Paralyzed']}.get(variant)
    if conds:
        for pid in (P1, P2):
            for p in t.board.pokemon_in_play(pid):
                p.set_attribute(AttrID.SPECIAL_CONDITIONS, list(conds))
    hand = [e[k] for k in TYPES if k in e] + [test.item, pl['supporter'], pl['tool'], pl['stadium'],
                                              pl['special_energy'], test.filler] + named
    if variant == 1:
        hand = hand[:4]
    elif variant == 2:
        hand = []
    for s_ in hand:
        t.put(s_, P1, 'hand')
    hand2 = [e[k] for k in TYPES[:4] if k in e] + [test.item, pl['supporter'], pl['tool'],
                                                     pl['stadium'], test.filler]
    if variant == 1:
        hand2 = hand2[:4]
    for s_ in hand2:
        t.put(s_, P2, 'hand')
    for s_ in [pl['supporter'], pl['tool'], pl['stadium'], test.item] + [e[k] for k in TYPES[:3]]:
        t.put(s_, P1, 'discard')
        t.put(s_, P2, 'discard')
    t.set_prizes(P1, [6, 2, 3, 1, 4][variant % 5])
    t.set_prizes(P2, [6, 2, 3, 1, 4][(variant + 2) % 5])
    if variant == 1:
        t.stadium(pl['stadium'], P1)
    elif variant == 3:
        t.stadium(pl['stadium'], P2)
    b.opp = t.active(P2)
    return b


def _action_summary(t, rmap, pid):
    from spirit.game.data_utils import ABILITIES_BY_ID
    name_of = {v.entity_id: k for k, v in rmap.items()}
    out = set()
    for e in t.actions(pid):
        eid = e['entityID']
        ent = t.board.get_entity(eid)
        who = name_of.get(eid) or (f"{pid}:{ent._containing_area_name()}:"
                                    f"{def_for(ent.archetype_id).display_name}" if ent is not None else eid)
        ab = ABILITIES_BY_ID.get(e['selectableAction'].get('actionID'))
        out.add((who, e['selectableAction']['description'], getattr(ab, 'title', '')))
    return out


def engine_metrics(t, b, rmap, pid):
    """Engine-level observations (pure reads) from player `pid`'s turn."""
    from spirit.game.data_utils import ABILITIES_BY_ID
    from spirit.game.attributes import CLIENT_POKEMON_TYPE_NAMES
    board = t.board
    m = {}
    for rn, p in rmap.items():
        m[('hp', rn)] = effective_max_hp(board, p)
        m[('retreat', rn)] = effective_retreat_cost(board, p)
        m[('types', rn)] = tuple(P.effective_pokemon_types(board, p))
        m[('cond_blocked', rn)] = tuple(P.conditions_blocked(board, p, c) for c in COND_ENUMS)
        m[('blocked', rn)] = (P.attack_effects_blocked(board, p), P.healing_blocked(board, p),
                              P.damage_counters_blocked(board, p), P.retreat_blocked(board, p),
                              P.attacks_blocked(board, p), P.ability_locked(board, p))
        atk = next((a for a in (def_for(p.archetype_id).abilities or []) if isinstance(a, Attack)), None)
        if atk is not None:
            cost = {CLIENT_POKEMON_TYPE_NAMES[k]: v for k, v in (atk.cost or {}).items()}
            m[('attack_cost', rn)] = tuple(sorted(P.effective_attack_cost(board, p, cost, atk).items()))
        for tn, q in rmap.items():
            if q.owning_player_id == p.owning_player_id:
                continue
            act = q is t.active(q.owning_player_id)
            m[('damage', rn, tn)] = compute_damage(board, p, q, 60, apply_modifiers=act).amount
    for player in (P1, P2):
        m[('bench_cap', player)] = P.effective_bench_capacity(board, player)
    m[('actions', pid)] = _action_summary(t, rmap, pid)
    return m


def _strip(entity, ability):
    old = entity.get_attribute(AttrID.PIE_ABILITIES) or []
    entity.set_attribute(AttrID.PIE_ABILITIES,
                         [e for e in old if not (isinstance(e, dict) and e.get('abilityID') == ability.ability_id)])
    return old


def _metric_diff(on, off):
    out = {}
    for k in set(on) | set(off):
        a, b_ = on.get(k), off.get(k)
        if a == b_:
            continue
        if k[0] == 'actions':
            for x in sorted(a ^ b_):
                kind = 'only_with' if x in a else 'only_without'
                out[('action', k[1], kind) + x] = True
        else:
            out[('engine',) + k] = f"{b_} -> {a}"
    return out


def _off(ability, b):
    """Switch the tested Ability off for the card under test only: strip it
    from the card's PIE_ABILITIES, and also null the shared passive object
    when no other copy of the card is in play."""
    from contextlib import nullcontext
    copies = [p for pid in (P1, P2) for p in b.t.board.pokemon_in_play(pid)
              if p is not b.me and p.archetype_id == b.me.archetype_id]
    return nullcontext() if copies else patch.object(ability, 'passive', None)


def engine_effects(t, b, ability):
    rmap = roles(b, None)
    out = {}
    on = engine_metrics(t, b, rmap, P1)
    old = _strip(b.me, ability)
    with _off(ability, b):
        off = engine_metrics(t, b, rmap, P1)
    b.me.set_attribute(AttrID.PIE_ABILITIES, old)
    out.update(_metric_diff(on, off))
    t.next_turn()
    on = {('actions', P2): _action_summary(t, rmap, P2)}
    old = _strip(b.me, ability)
    with _off(ability, b):
        off = {('actions', P2): _action_summary(t, rmap, P2)}
    b.me.set_attribute(AttrID.PIE_ABILITIES, old)
    out.update(_metric_diff(on, off))
    return out


def passive_effects(test, d, ability, where, variant):
    b = probe_board(test, d, where, variant)
    out, errors = probe_passive(ability.passive, b.me, b)
    try:
        out.update(engine_effects(b.t, b, ability))
    except Exception as ex:
        errors.append(f"engine: {type(ex).__name__}: {ex}"[:200])
    return out, errors


def check_passive(test, d, ability, pos):
    eff = {'active': {}, 'bench': {}}
    errs = []
    for v in range(N_VARIANTS):
        for where in ('active', 'bench'):
            o, e = passive_effects(test, d, ability, where, v)
            for k, val in o.items():
                eff[where].setdefault(k, val)
            errs += e
    act_cmp = {k: v for k, v in eff['active'].items() if not self_only(k)}
    ben_cmp = {k: v for k, v in eff['bench'].items() if not self_only(k)}
    ben_all = eff['bench']
    act_all = eff['active']
    det = (f"Active effects {len(act_all)} (comparable {len(act_cmp)}) e.g. {list(act_cmp)[:3] or list(act_all)[:2]}; "
           f"Bench effects {len(ben_all)} (comparable {len(ben_cmp)}) e.g. {list(ben_cmp)[:3]}")
    if pos == 'any':
        if act_cmp and not ben_cmp:
            return 'bug', 'effect present from the Active Spot, missing from the Bench: ' + det
        if act_cmp and ben_cmp:
            # Same effect family?  Compare hooks.
            ha = {k[0] for k in act_cmp}
            hb = {k[0] for k in ben_cmp}
            if ha - hb:
                return 'partial', f"hooks only from Active: {sorted(ha - hb)}; " + det
            return 'ok', det
        if ben_cmp:
            return 'ok', det
        if act_all and not act_cmp:
            return 'self_only', det
        return 'untested', 'no observable hook effect in either position' + (f" (errors {errs[:2]})" if errs else '')
    if pos == 'active':
        if ben_cmp:
            return 'bug', 'Active-only Ability has an effect from the Bench: ' + det
        if act_all:
            return 'ok', det
        return 'untested', 'no observable hook effect in either position'
    if pos in ('bench', 'implicit_bench'):
        if act_all:
            return 'bug', 'Bench-only Ability has an effect from the Active Spot: ' + det
        if ben_all:
            return 'ok', det
        return 'untested', 'no observable hook effect in either position'
    return 'untested', 'position wording mixed: ' + det


# --------------------------------------------------------------- triggers --
def _energy_for(test, d, ability):
    m = re.search(r"attach (?:a |an )?(?:basic )?(grass|fire|water|lightning|psychic|fighting|darkness|metal) energy",
                  norm(ability.game_text))
    e = pool(test)['energy']
    if m:
        return e[getattr(PokemonTypes, m.group(1).upper())]
    return e[own_type(d)]


def _disable_ctx(stack, ability, entity, spy):
    """Real run: spy on the effect.  noop run: spy returns at once and the
    passive (if any) is switched off for this card."""
    if ability.effect is not None and callable(ability.effect):
        stack.enter_context(patch.object(ability, 'effect', spy))


async def trigger_trial(test, d, ability, where, variant, kind, noop, alt_a=None):
    from contextlib import ExitStack
    random.seed(555 + variant)
    card_zone = 'hand' if kind == 'on_evolve' else None
    b = rich_board(test, d, where, variant, card_zone=card_zone, alt_a=alt_a)
    t = b.t
    called = []
    real = ability.effect

    async def spy(ctx, *a, **k):
        called.append(True)
        if noop:
            return None
        return await real(ctx, *a, **k)
    res = {'called': False, 'error': None, 'fp': None, 'skip': None}
    try:
        with ExitStack() as stack:
            _disable_ctx(stack, ability, b.me, spy)
            if noop and ability.passive is not None:
                stack.enter_context(patch.object(ability, 'passive', None))
                _strip(b.me, ability)
            if kind == 'on_evolve':
                entry = next((e for e in t.offers(b.me, None, P1)
                              if e['selectableAction']['description'] == 'EvolvePokemonPlayAbility'), None)
                if entry is None:
                    res['skip'] = 'evolve not offered'
                    return res
                await run_guarded(t.do(entry, [b.pre.entity_id]))
            elif kind == 'on_energy_attached' and re.search(r"your opponent attaches", norm(ability.game_text)):
                t.next_turn()
                en = t.put(pool(test)['energy'][PokemonTypes.WATER], P2, 'hand')
                entry = next((e for e in t.offers(en, None, P2)
                              if e['selectableAction']['description'] == 'DefaultEnergyPlayAbility'), None)
                if entry is None:
                    res['skip'] = 'opponent attach not offered'
                    return res
                await run_guarded(t.do(entry, [t.active(P2).entity_id], pid=P2))
            elif kind == 'on_energy_attached':
                en = t.put(_energy_for(test, d, ability), P1, 'hand')
                entry = next((e for e in t.offers(en, None, P1)
                              if e['selectableAction']['description'] == 'DefaultEnergyPlayAbility'), None)
                if entry is None:
                    res['skip'] = 'attach not offered'
                    return res
                await run_guarded(t.do(entry, [b.me.entity_id]))
            elif kind == 'between_turns':
                await run_guarded(t.checkup())
            elif kind == 'end_of_turn':
                await run_guarded(t._run(lambda: t.session._fire_end_of_turn_triggers(P1)))
    except asyncio.TimeoutError:
        res['error'] = 'timeout'
    except Exception as ex:
        res['error'] = f"{type(ex).__name__}: {ex}"[:300]
    res['called'] = bool(called)
    res['fp'] = fingerprint(t)
    return res


# ------------------------------------------------- attacked / knocked out --
SNIPER = 'ME1.Lopunny_108'          # Dashing Kick: 50 to a Benched Pokémon; Spiral Kick: 60
ATTACKED_RX = re.compile(
    r"this pokémon (?:is|would be) (?:your active pokémon and is |in the active spot and is |asleep and is |"
    r"confused and is )?(?:damaged by|knocked out by damage from|knocked out)"
    r"|(?:any )?damage (?:is )?done to this pokémon by (?:an opponent's |your opponent's )?attacks?"
    r"|if this pokémon is knocked out|if this pokémon has full hp and would be knocked out")


async def attacked_trial(test, d, ability, where, ko, noop):
    from contextlib import ExitStack
    random.seed(777)
    pl = pool(test)
    t = BenchTable(test)
    t.heads = True
    mine = own_type(d)
    if where == 'active':
        me = t.put(d, P1, 'active')
        t.put(test.filler, P1, 'bench')
    else:
        t.put(test.filler, P1, 'active')
        me = t.put(d, P1, 'bench')
    t.put(pl['basic_by_type'].get(mine.value, test.filler), P1, 'bench')
    for p in t.board.pokemon_in_play(P1):
        neutral(p)
        t.energy(p, mine, 2)
    t.energy(me, PokemonTypes.WATER, 1)
    if ko:
        me.set_attribute(AttrID.HP, 10)
    for s_ in [pl['energy'][k] for k in TYPES] + [pl['basic_by_type'].get(mine.value, test.filler)] * 2 \
            + named_cards(d) * 2:
        t.put(s_, P1, 'deck')
    sniper = neutral(t.put(fixtures.definition(SNIPER), P2, 'active'))
    sniper.set_attribute(AttrID.HP, 400)
    t.energy(sniper, PokemonTypes.WATER, 2)
    neutral(t.put(test.filler, P2, 'bench'))
    for s_ in [test.item, pl['supporter'], pl['energy'][PokemonTypes.WATER], test.filler]:
        t.put(s_, P2, 'hand')
    t.next_turn()
    t.pokemon = lambda cands, prompt: me if me in cands else cands[0]
    called = []
    real = ability.effect

    async def spy(ctx, *a, **k):
        called.append(True)
        if noop:
            return None
        return await real(ctx, *a, **k)
    res = {'called': False, 'error': None, 'fp': None}
    try:
        with ExitStack() as stack:
            _disable_ctx(stack, ability, me, spy)
            if noop and ability.passive is not None:
                stack.enter_context(patch.object(ability, 'passive', None))
                _strip(me, ability)
            title = 'Spiral Kick' if where == 'active' else 'Dashing Kick'
            entry = t.attack_offer(sniper, title, pid=P2)
            if entry is None:
                res['error'] = 'attack not offered'
            else:
                await run_guarded(t.do(entry, pid=P2))
    except asyncio.TimeoutError:
        res['error'] = 'timeout'
    except Exception as ex:
        res['error'] = f"{type(ex).__name__}: {ex}"[:300]
    res['called'] = bool(called)
    res['fp'] = fingerprint(t)
    return res


async def check_attacked(test, d, ability, pos):
    text = norm(ability.game_text)
    ko = 'knocked out' in text and 'full hp' not in text
    out = {}
    for where in ('active', 'bench'):
        real = await attacked_trial(test, d, ability, where, ko, False)
        base = await attacked_trial(test, d, ability, where, ko, True)
        diff = fp_diff(base['fp'], real['fp'])
        out[where] = {'changed': bool(diff), 'called': real['called'], 'error': real['error'] or base['error'],
                      'diff': diff[:6]}
    a, bb = out['active'], out['bench']
    det = (f"Active: changed={a['changed']} called={a['called']} err={a['error']} {a['diff'][:3]} | "
           f"Bench: changed={bb['changed']} called={bb['called']} err={bb['error']} {bb['diff'][:3]}")
    if pos == 'active':
        if bb['changed']:
            return 'bug', 'Active-only Ability works when the Benched card is attacked: ' + det
        if a['changed']:
            return 'ok', det
        return 'untested', 'no observable effect either way: ' + det
    if pos == 'any':
        if a['changed'] and not bb['changed']:
            return 'bug', 'works when attacked in the Active Spot but not on the Bench: ' + det
        if bb['changed']:
            return 'ok', det
        return 'untested', 'no observable effect either way: ' + det
    if pos == 'bench':
        if a['changed']:
            return 'bug', 'Bench-only Ability works when the card is attacked in the Active Spot: ' + det
        if bb['changed']:
            return 'ok', det
        return 'untested', 'no observable effect either way: ' + det
    return 'untested', f'position {pos}: ' + det


TRIGGER_KINDS = ('on_evolve', 'on_energy_attached', 'between_turns', 'end_of_turn')


async def check_trigger(test, d, ability, pos, kind):
    log = []
    for v in range(N_VARIANTS):
        out = {}
        for where in ('active', 'bench'):
            real = await trigger_trial(test, d, ability, where, v, kind, False)
            base = await trigger_trial(test, d, ability, where, v, kind, True)
            if real['skip']:
                return 'untested', real['skip']
            diff = fp_diff(base['fp'], real['fp'])
            out[where] = {'called': real['called'], 'changed': bool(diff), 'error': real['error'],
                          'diff': diff[:6]}
        a, bb = out['active'], out['bench']
        log.append(f"v{v}: Active called={a['called']} changed={a['changed']} err={a['error']} | "
                   f"Bench called={bb['called']} changed={bb['changed']} err={bb['error']}")
        if pos == 'any':
            if a['changed'] and not bb['changed']:
                if re.search(r"remove all special conditions from it", norm(ability.game_text)):
                    return 'untested', ('only removes Special Conditions from itself; a Benched '
                                        'Pokémon cannot have any ({})'.format(log[-1]))
                # The Active partner may be what the effect needs ("your Active
                # Grass Pokémon"): retry with a same-type Active partner.
                alt = pool(test)['basic_by_type'].get((types_of(d) or [0])[0])
                if alt is not None:
                    r2 = await trigger_trial(test, d, ability, 'bench', v, kind, False, alt_a=alt)
                    b2 = await trigger_trial(test, d, ability, 'bench', v, kind, True, alt_a=alt)
                    if fp_diff(b2['fp'], r2['fp']):
                        return 'ok', log[-1] + f"; Bench works with an Active {alt.display_name}"
                return 'bug', ('not triggered from the Bench' if not bb['called'] else
                               'triggered from the Bench but does nothing') + f" ({log[-1]})"
            if a['changed'] and bb['changed']:
                return 'ok', log[-1]
            if bb['changed']:
                return 'ok', log[-1]
        elif pos == 'active':
            if bb['changed']:
                return 'bug', f"Active-only trigger works from the Bench ({log[-1]})"
            if a['changed']:
                return 'ok', log[-1]
        elif pos in ('bench', 'implicit_bench'):
            if a['changed']:
                return 'bug', f"Bench-only trigger works from the Active Spot ({log[-1]})"
            if bb['changed']:
                return 'ok', log[-1]
    return 'untested', '; '.join(log)


# ------------------------------------------------------------------- sweep --
async def sweep(test, kinds=('activated', 'passive', 'trigger'), limit=None, only=None):
    report = {'groups': 0, 'printings': 0, 'by_kind': collections.Counter(),
              'by_position': collections.Counter(), 'results': [], 'not_tested': []}
    seen_printings = set()
    for title, text, kind, members in groups():
        d, a = members[0]
        for dd, _ in members:
            seen_printings.add(dd.guid)
        report['groups'] += 1
        report['by_kind'][kind] += 1
        pos = position_class(text)
        report['by_position'][pos] += 1
        if only and not re.search(only, f"{title} {label(d)}"):
            continue
        entry = {'title': title, 'text': text, 'kind': kind, 'position': pos,
                 'card': label(d), 'module': d.__module__ if hasattr(d, '__module__') else '',
                 'printings': [label(x) for x, _ in members]}
        try:
            if ATTACKED_RX.search(text) and kind != 'activated' and 'attacked' in kinds and (
                    not kind.startswith('trigger:') or 'on_knocked_out' in kind or 'on_damaged' in kind):
                entry['kind'] = kind = 'attacked:' + kind
                entry['position'] = pos = pos_for(text, ATTACKED_RX)
                verdict, detail = await check_attacked(test, d, a, pos)
            elif kind == 'passive' and 'trigger' in kinds and re.search(
                    r"when(?:ever)? you attach (?:a |an )?(?:basic )?(?:\w+ )?energy (?:card )?from your hand to "
                    r"(?:this pokémon|it|1 of your pokémon)", text):
                entry['kind'] = kind = 'trigger:passive_on_energy_attached'
                verdict, detail = await check_trigger(test, d, a, pos, 'on_energy_attached')
                # the same passive may also carry continuous hooks: probe them too
                pv, pd = check_passive(test, d, a, pos)
                if pv == 'bug' or (verdict != 'bug' and verdict == 'untested' and pv in ('ok', 'partial')):
                    verdict, detail = pv, 'continuous hooks: ' + pd + ' || attach trigger: ' + detail
                else:
                    detail += ' || continuous hooks: ' + pv
            elif kind == 'activated' and 'activated' in kinds:
                verdict, detail = await check_activated(test, d, a, pos)
            elif kind == 'passive' and 'passive' in kinds:
                verdict, detail = check_passive(test, d, a, pos)
            elif kind.startswith('trigger:') and 'trigger' in kinds:
                trig = kind.split(':', 1)[1].split(',')
                tk = next((k for k in TRIGGER_KINDS if k in trig), None)
                if tk is None:
                    verdict, detail = 'untested', f"trigger {kind} not checked (inherent position / transition)"
                elif tk == 'on_evolve' and not re.search(r"evolve", text):
                    verdict, detail = 'untested', 'on_evolve without evolve wording'
                else:
                    if tk == 'on_evolve':
                        entry['position'] = pos = pos_for(text, EVOLVE_SENT_RX)
                    verdict, detail = await check_trigger(test, d, a, pos, tk)
            elif kind in ('out_of_play', 'rule', 'none'):
                verdict, detail = 'out_of_scope', kind
            else:
                continue
        except Exception as ex:
            verdict, detail = 'error', f"{type(ex).__name__}: {ex}"[:300]
        entry['verdict'] = verdict
        entry['detail'] = detail
        if os.environ.get('SWEEP_PROGRESS'):
            print(f"[{report['groups']}] {verdict} {label(d)} {title}", flush=True)
        report['results'].append(entry)
        if limit is not None and len(report['results']) >= limit:
            break
    report['printings'] = len(seen_printings)
    return report


KNOWN_BUGS = {
    'Arf Arf Bark': {
        'root_cause': 'side finding (not a position bug): spirit/game/scripts/cards/SM12/Stoutland_176.py '
                      'only declares Triggers.ON_EVOLVE, so the Active-only Knocked Out half never runs',
        'test': 'BenchVsActiveScenarios.test_stoutland_ko_in_active_spot_discards_attacker_energy'},
    'Comatose': {
        'root_cause': 'spirit/game/card_effects/bw_era.py:_BWTextPassive.on_energy_attached: the '
                      '"whenever you attach an energy from your hand to it ... it is now asleep" branch has no '
                      '_is_active(holder) check (the text starts "As long as this Pokémon is your Active '
                      'Pokémon"); EffectContext.apply_special_condition also accepts a Benched target, so the '
                      'Benched Komala becomes Asleep and stays Asleep when it later moves into the Active Spot',
        'test': 'BenchVsActiveScenarios.test_komala_comatose_does_not_fire_on_bench'},
    'Bully of the Sands': {
        'root_cause': 'spirit/game/scripts/cards/SWSH12/Krookodile_113.py:bully_of_the_sands ignores '
                      'ctx.was_active_at_ko, so the "if this Pokémon is your Active Pokémon and is Knocked '
                      'Out" half also fires when Krookodile is Knocked Out on the Bench',
        'test': 'BenchVsActiveScenarios.test_krookodile_ko_on_bench_does_not_discard'},
    'Energy Evolution': {
        'root_cause': 'spirit/game/card_effects/bw_era.py:_BWTextPassive.modify_pokemon_types: the bare '
                      '"same type as" match (Kecleon BW9 94) also hits Eevee\'s "...the same type as that '
                      'Energy card", so an Active Eevee takes the type of the opponent\'s Active Pokémon',
        'test': 'BenchVsActiveScenarios.test_eevee_in_active_spot_stays_colorless'},
}


def write_report(report, name='bench_abilities'):
    os.makedirs(REPORT_DIR, exist_ok=True)
    out = dict(report)
    for r in report['results']:
        if r['verdict'] == 'bug' and r['title'] in KNOWN_BUGS:
            r.update(KNOWN_BUGS[r['title']])
    not_tested = collections.Counter()
    for r in report['results']:
        if r['verdict'] in ('untested', 'self_only', 'out_of_scope'):
            why = r['detail'] if r['verdict'] != 'untested' else re.sub(r"v\d.*", "", r['detail'])[:90]
            not_tested[f"{r['kind'].split(':')[0]}:{r['verdict']}:{why[:90]}"] += 1
    out['not_tested_reasons'] = dict(not_tested.most_common())
    out['by_kind'] = dict(report['by_kind'])
    out['by_position'] = dict(report['by_position'])
    out['summary'] = collections.Counter(f"{r['kind'].split(':')[0]}:{r['verdict']}" for r in report['results'])
    out['bugs'] = [r for r in report['results'] if r['verdict'] in ('bug', 'error')]
    with open(os.path.join(REPORT_DIR, name + '.json'), 'w') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, default=str)
    return out


class SweepBenchAbilities(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_sweep(self):
        if os.environ.get('SWEEP_SKIP'):
            self.skipTest('SWEEP_SKIP')
        kinds = tuple((os.environ.get('SWEEP_KINDS') or 'activated,passive,trigger,attacked').split(','))
        limit = int(os.environ['SWEEP_LIMIT']) if os.environ.get('SWEEP_LIMIT') else None
        report = await sweep(self, kinds, limit, os.environ.get('SWEEP_ONLY'))
        out = write_report(report, os.environ.get('SWEEP_NAME', 'bench_abilities'))
        print('\nbench_abilities:', dict(out['summary']))
        for r in out['bugs']:
            print('  BUG?', r['card'], '|', r['title'], '|', r['position'], '|', r['detail'][:300])



# ------------------------------------------------------- targeted scenarios --
KROOKODILE = 'SWSH12.Krookodile_113'
EEVEE_XY3 = 'XY3.Eevee_80'
EEVEE_HIF = 'HF.Eevee_141'
SQUIRTLE = 'BW7.Squirtle_29'            # Shell Shield: Bench-only damage prevention
DRUDDIGON = 'BW11.Druddigon_106'        # Rough Skin: Active-only
BEWEAR = 'SM12.Bewear_182'              # Carry and Run: Bench-only retreat discount
SHAYMIN = 'SM8.Shaymin_33'
KOMALA = 'Promo_SM.Komala_41'
STOUTLAND = 'SM12.Stoutland_176'              # Floral Heal: "your Active Grass Pokémon" (target, not position)


class BenchVsActiveScenarios(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def sniper_board(self, spec, where, hp=None):
        """P1: `spec` Active or Benched (+ fillers); P2: Lopunny (Dashing Kick =
        50 to a Benched Pokémon, Spiral Kick = 60) ready to attack, 4 cards in hand."""
        t = BenchTable(self)
        if where == 'active':
            me = neutral(t.put(spec, P1, 'active'))
            neutral(t.put(self.filler, P1, 'bench'))
        else:
            neutral(t.put(self.filler, P1, 'active'))
            me = neutral(t.put(spec, P1, 'bench'))
        neutral(t.put(self.filler, P1, 'bench'))
        if hp is not None:
            me.set_attribute(AttrID.HP, hp)
        sniper = neutral(t.put(fixtures.definition(SNIPER), P2, 'active'))
        sniper.set_attribute(AttrID.HP, 400)
        t.energy(sniper, PokemonTypes.WATER, 2)
        neutral(t.put(self.filler, P2, 'bench'))
        for _ in range(4):
            t.put(self.item, P2, 'hand')
        t.next_turn()
        t.pokemon = lambda cands, prompt: me if me in cands else cands[0]
        return t, me, sniper

    # --- Krookodile: "If this Pokémon is your Active Pokémon and is Knocked Out ..."
    async def test_krookodile_ko_in_active_spot_discards_from_opponents_hand(self):
        t, me, sniper = self.sniper_board(KROOKODILE, 'active', hp=10)
        before = len(t.zone(P2, 'discard'))
        await t.attack(sniper, 'Spiral Kick', pid=P2)
        self.assertNotIn(me, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'discard')), before + 1)

    # BUG: Krookodile (SWSH12 113) Bully of the Sands also discards a random card from the
    # opponent's hand when it is Knocked Out on the BENCH (e.g. by a bench-snipe attack).
    # Root cause: spirit/game/scripts/cards/SWSH12/Krookodile_113.py:bully_of_the_sands only
    # checks ctx.ko_from_attack, never ctx.was_active_at_ko (which the KO dispatcher in
    # game_session.resolve_knockouts sets for exactly this gate).
    async def test_krookodile_ko_on_bench_does_not_discard(self):
        t, me, sniper = self.sniper_board(KROOKODILE, 'bench', hp=10)
        before = len(t.zone(P2, 'discard'))
        await t.attack(sniper, 'Dashing Kick', pid=P2)
        self.assertNotIn(me, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'discard')), before)

    # --- Eevee Energy Evolution: no type-changing text at all
    def eevee_board(self, spec, where):
        t = BenchTable(self)
        fire = pool(self)['basic_by_type'][PokemonTypes.FIRE.value]
        if where == 'active':
            eevee = neutral(t.put(spec, P1, 'active'))
        else:
            neutral(t.put(self.filler, P1, 'active'))
            eevee = neutral(t.put(spec, P1, 'bench'))
        neutral(t.put(fire, P2, 'active'))
        return t, eevee

    async def test_eevee_on_bench_stays_colorless(self):
        for spec in (EEVEE_XY3, EEVEE_HIF):
            with self.subTest(spec=spec):
                t, eevee = self.eevee_board(spec, 'bench')
                self.assertEqual(P.effective_pokemon_types(t.board, eevee), [PokemonTypes.COLORLESS.value])

    # BUG: Eevee (XY3 80 / HIF 141) Energy Evolution turns Eevee into the type of the opponent's
    # Active Pokémon while Eevee is Active (Kecleon's rule), although its text has no such clause.
    # Root cause: spirit/game/card_effects/bw_era.py:_BWTextPassive.modify_pokemon_types matches
    # the bare phrase "same type as" (meant for Kecleon BW9 94 "this Pokémon is the same type as
    # the your opponent's Active Pokémon"); Eevee's "...that is the same type as that Energy card"
    # matches it.  Anchor the pattern on "same type as (the )?(your )?opponent's active pokémon".
    async def test_eevee_in_active_spot_stays_colorless(self):
        for spec in (EEVEE_XY3, EEVEE_HIF):
            with self.subTest(spec=spec):
                t, eevee = self.eevee_board(spec, 'active')
                self.assertEqual(P.effective_pokemon_types(t.board, eevee), [PokemonTypes.COLORLESS.value])

    # --- Komala Comatose: "As long as this Pokémon is your Active Pokémon, whenever you
    # attach an Energy from your hand to it, it is now Asleep."
    async def komala_attach(self, where):
        t = BenchTable(self)
        if where == 'active':
            k = neutral(t.put(KOMALA, P1, 'active'))
            neutral(t.put(self.filler, P1, 'bench'))
        else:
            neutral(t.put(self.filler, P1, 'active'))
            k = neutral(t.put(KOMALA, P1, 'bench'))
        neutral(t.put(self.filler, P2, 'active'))
        energy = t.put(pool(self)['energy'][PokemonTypes.WATER], P1, 'hand')
        await t.play(energy, targets=[k.entity_id])
        self.assertIs(energy.parent, k)
        return t, k

    async def test_komala_comatose_in_active_spot(self):
        t, k = await self.komala_attach('active')
        self.assertEqual(t.conditions(k), {'Asleep'})

    # BUG: Komala (SM Promo 41) Comatose makes the BENCHED Komala Asleep when an Energy is
    # attached to it from hand (and it is still Asleep once it moves into the Active Spot).
    # Root cause: spirit/game/card_effects/bw_era.py:_BWTextPassive.on_energy_attached, Comatose
    # branch lacks an _is_active(holder) check; EffectContext.apply_special_condition
    # (spirit/game/session/effects.py) does not refuse Benched targets either.
    async def test_komala_comatose_does_not_fire_on_bench(self):
        t, k = await self.komala_attach('bench')
        self.assertEqual(t.conditions(k), set())

    # --- Stoutland Arf Arf Bark (side finding): the Active-only KO half is not implemented.
    # BUG: Stoutland (SM12 176 / SM12 248) "If this Pokémon is your Active Pokémon and is Knocked
    # Out by damage from an opponent's attack, you may discard an Energy from your opponent's
    # Active Pokémon" never happens, from the Active Spot either.  Root cause:
    # spirit/game/scripts/cards/SM12/Stoutland_176.py declares trigger=Triggers.ON_EVOLVE only
    # (no ON_KNOCKED_OUT, no was_active_at_ko-gated handler), so only the evolve half runs.
    async def test_stoutland_ko_in_active_spot_discards_attacker_energy(self):
        t, me, sniper = self.sniper_board(STOUTLAND, 'active', hp=10)
        before = len(t.board.attached_energies(sniper))
        await t.attack(sniper, 'Spiral Kick', pid=P2)
        self.assertNotIn(me, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.board.attached_energies(sniper)), before - 1)

    async def test_stoutland_evolve_half_works_from_bench(self):
        t = BenchTable(self)
        neutral(t.put(self.filler, P1, 'active'))
        herdier = neutral(t.put(pre_evolution(fixtures.definition(STOUTLAND)), P1, 'bench'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        t.energy(opp, PokemonTypes.WATER, 2)
        card = t.put(STOUTLAND, P1, 'hand')
        await t.play(card, targets=[herdier.entity_id])
        self.assertEqual(len(t.board.attached_energies(opp)), 1)

    # --- reverse checks that hold (regression guards)
    async def test_bench_only_shell_shield_is_off_in_active_spot(self):
        t, me, sniper = self.sniper_board(SQUIRTLE, 'active')
        hp = t.hp(me)
        await t.attack(sniper, 'Spiral Kick', pid=P2)
        self.assertTrue(me not in t.board.pokemon_in_play(P1) or t.hp(me) < hp)   # 60 HP: KO'd
        t, me, sniper = self.sniper_board(SQUIRTLE, 'bench')
        hp = t.hp(me)
        await t.attack(sniper, 'Dashing Kick', pid=P2)
        self.assertEqual(t.hp(me), hp)

    async def test_active_only_rough_skin_is_off_on_bench(self):
        t, me, sniper = self.sniper_board(DRUDDIGON, 'bench')
        await t.attack(sniper, 'Dashing Kick', pid=P2)
        self.assertEqual(t.hp(sniper), 400)
        t, me, sniper = self.sniper_board(DRUDDIGON, 'active')
        await t.attack(sniper, 'Spiral Kick', pid=P2)
        self.assertEqual(t.hp(sniper), 380)

    async def test_bench_only_retreat_discount(self):
        t = BenchTable(self)
        active = neutral(t.put(self.filler, P1, 'active'))
        base = t.retreat(active)
        bewear = neutral(t.put(BEWEAR, P1, 'bench'))
        self.assertEqual(t.retreat(active), max(0, base - 2))
        t = BenchTable(self)
        bewear = neutral(t.put(BEWEAR, P1, 'active'))
        other = neutral(t.put(self.filler, P1, 'bench'))
        self.assertEqual(t.retreat(bewear), int(bewear.get_attribute(AttrID.RETREAT_COST) or 0))

    async def test_target_wording_your_active_works_from_bench(self):
        """Floral Heal heals "your Active Grass Pokémon": usable from the Bench."""
        t = BenchTable(self)
        grass = neutral(t.put(pool(self)['basic_by_type'][PokemonTypes.GRASS.value], P1, 'active'))
        damage(t, grass, 30)
        shaymin = neutral(t.put(SHAYMIN, P1, 'bench'))
        neutral(t.put(self.filler, P2, 'active'))
        hp = t.hp(grass)
        await t.use(shaymin, 'Floral Heal')
        self.assertEqual(t.hp(grass), hp + 20)


if __name__ == "__main__":
    unittest.main()
