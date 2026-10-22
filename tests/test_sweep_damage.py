"""Sweep: damage AMOUNT / TARGET wordings.

Per-X damage (Energy, damage counters, Bench size), self-damage, attacks that
ignore Weakness/Resistance/defender effects, Bench snipes, spread damage,
"1 of your opponent's Pokémon" snipes and simple conditional bonuses.

Every per-X checker runs at two different counts so the multiplier itself is
verified (not just one data point).
"""
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.sweep_core import (SweepCase, run_sweep, std_board, do_attack, dealt,
                              neutral, BIG)
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.tools.effect_smoke import P1, P2

HARD_CHARM = 'XY1.HardCharm_119'      # opponent-side "reduce damage by 20" Tool
DONT = r" \(don't apply weakness and resistance for benched pokémon\.?\)\.?"
TYPES = {t.name.lower(): t for t in PokemonTypes}


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


def big(p, hp=BIG, damage=0):
    """Make `p` sturdy: printed (max) HP = hp, with `damage` already on it."""
    p.attribute_originals[AttrID.HP.value] = hp
    p.set_attribute(AttrID.HP, hp - damage)
    return p


def my_types(b):
    return list(b.me.get_attribute(AttrID.POKEMON_TYPES) or [])


def extra_bench(b, pid, n):
    """Add n neutral fillers to a Bench; returns them."""
    return [big(neutral(b.t.put(b.t.test.filler, pid, 'bench'))) for _ in range(n)]


def hp_loss(b, p, before):
    t = b.t
    if p not in t.board.pokemon_in_play(p.owning_player_id):
        return before
    return before - t.hp(p)


def energy_of(t, card, kind):
    """Whether an attached card is a basic Energy of type `kind` (None = any)."""
    if kind is None:
        return True
    guid = t.test.energies.get(kind.value)
    d = def_for(card.archetype_id)
    return guid is not None and getattr(d, 'guid', '').lower() == guid.lower()


async def run(test, d, attack, prep, heads=True):
    holder = {}

    def _prep(b):
        big(b.me)
        big(b.opp)
        big(b.opp_bench)
        big(b.my_bench)
        prep(b)
        holder['b'] = b
    b = std_board(test, d, attack, heads=heads, prep=_prep)
    offered = await do_attack(b)
    return b, offered


def skip_ability(d, attack):
    if has_ability(d):
        return 'card has an Ability (may change damage)'
    return None


# ----------------------------------------------------------------------
# 1. per Energy
# ----------------------------------------------------------------------
async def per_energy(test, d, attack, m):
    why = skip_ability(d, attack)
    if why:
        return None, why
    n, more, kind, where = int(m.group(1)), bool(m.group(2)), m.group(3), m.group(4)
    kind = TYPES.get(kind) if kind else None
    if m.group(3) and kind is None:
        return None, f'unknown energy type {m.group(3)}'
    if kind is not None and kind.value not in test.energies:
        return None, f'no basic {kind.name} Energy'
    base = attack.damage if more else 0
    out = []
    for extra in (0, 2):
        def prep(b, extra=extra):
            k = kind or PokemonTypes.WATER
            if where in ('this pokémon', 'both active pokémon'):
                b.t.energy(b.me, k, extra) if extra else None
            if where != 'this pokémon':
                b.t.energy(b.opp, k, extra) if extra else None
        b, ok = await run(test, d, attack, prep)
        if not ok:
            return None, 'attack not offered (printed condition?)'
        t = b.t
        mine = sum(1 for c in t.board.attached_energies(b.me) if energy_of(t, c, kind))
        theirs = sum(1 for c in t.board.attached_energies(b.opp) if energy_of(t, c, kind))
        # energy may have been moved/discarded by the attack: count before
        count = {'this pokémon': b.before['my_energy'] if kind is None else mine,
                 "your opponent's active pokémon": b.before['opp_energy'] if kind is None else theirs,
                 'the defending pokémon': b.before['opp_energy'] if kind is None else theirs,
                 'both active pokémon': (b.before['my_energy'] + b.before['opp_energy'])
                 if kind is None else mine + theirs}[where]
        want = base + n * count
        got = dealt(b)
        out.append((extra, count, got, want))
    bad = [o for o in out if o[2] != o[3]]
    return not bad, '; '.join(f"+{e} energy (count {c}): did {g}, want {w}" for e, c, g, w in out)


# ----------------------------------------------------------------------
# 2. per damage counter
# ----------------------------------------------------------------------
async def per_counter(test, d, attack, m):
    why = skip_ability(d, attack)
    if why:
        return None, why
    n, mod, where = int(m.group(1)), (m.group(2) or '').strip(), m.group(3)
    if mod == 'minus':
        base = attack.damage
    else:
        base = attack.damage if mod in ('more', 'less') else 0
    out = []
    for counters in (0, 3):
        def prep(b, counters=counters):
            target = b.me if where == 'this pokémon' else b.opp
            big(target, BIG, 10 * counters)
        b, ok = await run(test, d, attack, prep)
        if not ok:
            return None, 'attack not offered (printed condition?)'
        if mod in ('less', 'minus'):
            want = max(0, base - n * counters)
        else:
            want = base + n * counters
        got = dealt(b)
        out.append((counters, got, want))
    bad = [o for o in out if o[1] != o[2]]
    return not bad, '; '.join(f"{c} counters: did {g}, want {w}" for c, g, w in out)


# ----------------------------------------------------------------------
# 3. per Benched / in-play Pokémon
# ----------------------------------------------------------------------
async def per_bench(test, d, attack, m):
    why = skip_ability(d, attack)
    if why:
        return None, why
    n, more, what = int(m.group(1)), bool(m.group(2)), m.group(3)
    base = attack.damage if more else 0
    out = []
    for extra in (0, 2):
        def prep(b, extra=extra):
            extra_bench(b, P1, extra)
            extra_bench(b, P2, extra)
        b, ok = await run(test, d, attack, prep)
        if not ok:
            return None, 'attack not offered (printed condition?)'
        mine, theirs = b.before['my_bench_n'], b.before['opp_bench_n']
        count = {
            'of your benched pokémon': mine,
            "of your opponent's benched pokémon": theirs,
            'of your pokémon in play': mine + 1,
            'pokémon in play (both yours and your opponent\'s)': mine + theirs + 2,
        }[what]
        want = base + n * count
        got = dealt(b)
        out.append((count, got, want))
    bad = [o for o in out if o[1] != o[2]]
    return not bad, '; '.join(f"count {c}: did {g}, want {w}" for c, g, w in out)


# ----------------------------------------------------------------------
# 4. self damage
# ----------------------------------------------------------------------
async def self_damage(test, d, attack, m):
    n = int(m.group(2))
    b, ok = await run(test, d, attack, lambda b: None)
    if not ok:
        return None, 'attack not offered (printed condition?)'
    me, opp = dealt(b, 'me'), dealt(b)
    printed = attack.damage or 0
    good_self = me == n or has_ability(d)
    good_opp = has_ability(d) or opp == printed
    return good_self and good_opp, f"self {me} (want {n}), opponent {opp} (printed {printed})"


# ----------------------------------------------------------------------
# 5. ignores Weakness / Resistance / defender effects
# ----------------------------------------------------------------------
async def ignore_mods(test, d, attack, m):
    why = skip_ability(d, attack)
    if why:
        return None, why
    if not attack.damage:
        return None, 'no printed damage'
    text = m.group(1)
    aspects = []
    if text.startswith('weakness'):
        aspects.append('weakness')
    if 'resistance' in text:
        aspects.append('resistance')
    if 'effects' in text:
        aspects.append('effects')
    base = attack.damage
    out = []

    def setup(aspect):
        def prep(b):
            types = my_types(b)
            if aspect == 'weakness':
                b.opp.set_attribute(AttrID.WEAKNESS_TYPES, types[:1])
            elif aspect == 'resistance':
                b.opp.set_attribute(AttrID.RESISTANCE_TYPES, types[0] if types else 0)
                b.opp.set_attribute(AttrID.RESISTANCE_AMOUNT, 30)
            elif aspect == 'effects':
                b.t.attach(HARD_CHARM, b.opp)
        return prep

    for aspect in aspects:
        b, ok = await run(test, d, attack, setup(aspect))
        if not ok:
            return None, 'attack not offered (printed condition?)'
        out.append((aspect, dealt(b), base))
    # control: Weakness still applies when only Resistance is ignored
    if aspects == ['resistance']:
        b, ok = await run(test, d, attack, setup('weakness'))
        out.append(('weakness (control)', dealt(b), base * 2))
    bad = [o for o in out if o[1] != o[2]]
    return not bad, '; '.join(f"{a}: did {g}, want {w}" for a, g, w in out)


# ----------------------------------------------------------------------
# 6. Bench snipes / spread / "1 of your opponent's Pokémon"
# ----------------------------------------------------------------------
def weak_bench(b, mons):
    types = my_types(b)
    for p in mons:
        p.set_attribute(AttrID.WEAKNESS_TYPES, types[:1])
        p.set_attribute(AttrID.RESISTANCE_TYPES, types[0] if types else 0)
        p.set_attribute(AttrID.RESISTANCE_AMOUNT, 30)


async def bench_snipe(test, d, attack, m):
    if has_ability(d):
        return None, 'card has an Ability (may change damage)'
    n, count = int(m.group(2)), int(m.group(3))
    holder = {}

    def prep(b):
        holder['bench'] = [b.opp_bench] + extra_bench(b, P2, 1)
        weak_bench(b, holder['bench'])
        holder['hp'] = [b.t.hp(p) for p in holder['bench']]
    b, ok = await run(test, d, attack, prep)
    if not ok:
        return None, 'attack not offered (printed condition?)'
    hits = [hp_loss(b, p, h) for p, h in zip(holder['bench'], holder['hp'])]
    active = dealt(b)
    printed = attack.damage or 0
    want_hits = sorted([n] * count + [0] * (2 - count))
    ok = sorted(hits) == want_hits and active == printed
    return ok, f"bench took {hits} (want {want_hits} in some order), active {active} (printed {printed})"


async def spread(test, d, attack, m):
    if has_ability(d):
        return None, 'card has an Ability (may change damage)'
    also, n, benched = bool(m.group(1)), int(m.group(2)), bool(m.group(3))
    printed = attack.damage or 0
    if not benched and printed:
        return None, 'printed damage plus "each of your opponent\'s Pokémon" (ambiguous)'
    holder = {}

    def prep(b):
        holder['bench'] = [b.opp_bench] + extra_bench(b, P2, 1)
        weak_bench(b, holder['bench'])
        holder['hp'] = [b.t.hp(p) for p in holder['bench']]
    b, ok = await run(test, d, attack, prep)
    if not ok:
        return None, 'attack not offered (printed condition?)'
    hits = [hp_loss(b, p, h) for p, h in zip(holder['bench'], holder['hp'])]
    active = dealt(b)
    want_active = printed if benched else n
    ok = hits == [n, n] and active == want_active
    return ok, f"bench took {hits} (want [{n}, {n}]), active {active} (want {want_active})"


def chooser(t, prefer):
    """Script both choosers to prefer the entities in `prefer` (in order)."""
    def pick_pokemon(cands, prompt):
        for p in prefer:
            if p in cands:
                return p
        return cands[0]

    def pick_cards(cards, count, prompt, display):
        ids = [p.entity_id for p in prefer]
        ordered = sorted(cards, key=lambda c: ids.index(c.entity_id) if c.entity_id in ids else 99)
        return ordered[:count]
    t.pokemon = pick_pokemon
    t.picks = pick_cards


async def any_snipe(test, d, attack, m):
    if has_ability(d):
        return None, 'card has an Ability (may change damage)'
    n = int(m.group(1))
    printed = attack.damage or 0
    if printed:
        return None, 'printed damage plus a snipe (ambiguous)'
    out = []
    for target in ('bench', 'active'):
        holder = {}

        def prep(b, target=target):
            weak_bench(b, [b.opp_bench])
            chooser(b.t, [b.opp_bench] if target == 'bench' else [b.opp])
        b, ok = await run(test, d, attack, prep)
        if not ok:
            return None, 'attack not offered (printed condition?)'
        got = (dealt(b, 'opp_bench'), dealt(b))
        want = (n, 0) if target == 'bench' else (0, n)
        out.append((target, got, want))
    bad = [o for o in out if o[1] != o[2]]
    return not bad, '; '.join(f"chose {tg}: (bench, active) took {g}, want {w}" for tg, g, w in out)


# ----------------------------------------------------------------------
# 7. simple conditional bonuses
# ----------------------------------------------------------------------
CONDS = {
    'asleep': 'Asleep', 'burned': 'Burned', 'confused': 'Confused',
    'paralyzed': 'Paralyzed', 'poisoned': 'Poisoned',
}


def cond_setter(cond):
    """Returns prep(b, on) for a supported condition text, else None."""
    if cond == 'this pokémon has any damage counters on it':
        return lambda b, on: big(b.me, BIG, 20 if on else 0)
    if cond in ("your opponent's active pokémon already has any damage counters on it",
                "your opponent's active pokémon has any damage counters on it",
                'the defending pokémon already has any damage counters on it',
                'the defending pokémon has any damage counters on it'):
        return lambda b, on: big(b.opp, BIG, 20 if on else 0)
    if cond == 'your benched pokémon have any damage counters on them':
        return lambda b, on: big(b.my_bench, BIG, 20 if on else 0)
    for who in ("your opponent's active pokémon", 'the defending pokémon'):
        for word, value in CONDS.items():
            if cond == f'{who} is {word}':
                return lambda b, on, value=value: b.opp.set_attribute(
                    AttrID.SPECIAL_CONDITIONS, [value] if on else [])
        if cond == f'{who} is affected by a special condition':
            return lambda b, on: b.opp.set_attribute(
                AttrID.SPECIAL_CONDITIONS, ['Confused'] if on else [])
    hands = {
        'you have the same number of cards in your hand as your opponent': ((2, 2), (2, 3)),
        'you have more cards in your hand than your opponent': ((3, 1), (1, 1)),
        'you have no cards in your hand': ((0, 1), (1, 1)),
    }
    if cond in hands:
        def set_hands(b, on, sizes=hands[cond]):
            mine, theirs = sizes[0] if on else sizes[1]
            for pid, n in ((P1, mine), (P2, theirs)):
                for _ in range(n):
                    b.t.put(b.t.test.item, pid, 'hand')
        return set_hands
    m = re.fullmatch(r'(you have|your opponent has) (exactly|) ?(\d+)(?: or (fewer))? prize cards? remaining', cond)
    if m and (m.group(2) or m.group(4)):
        pid, n = (P1 if m.group(1) == 'you have' else P2), int(m.group(3))
        off = n + 1 if n < 6 else n - 1
        return lambda b, on: b.t.set_prizes(pid, n if on else off)
    if cond == 'you have more prize cards remaining than your opponent':
        def set_prizes(b, on):
            b.t.set_prizes(P1, 4 if on else 3)
            b.t.set_prizes(P2, 2 if on else 3)
        return set_prizes
    if cond in ('this pokémon is poisoned', 'this pokémon is burned or poisoned',
                'this pokémon is affected by a special condition'):
        return lambda b, on: b.me.set_attribute(
            AttrID.SPECIAL_CONDITIONS, ['Poisoned'] if on else [])
    return None


async def cond_bonus(test, d, attack, m):
    why = skip_ability(d, attack)
    if why:
        return None, why
    cond, n = m.group(1), int(m.group(2))
    setter = cond_setter(cond)
    if setter is None:
        return None, f'condition not modelled: {cond}'
    base = attack.damage or 0
    out = []
    for on in (False, True):
        b, ok = await run(test, d, attack, lambda b, on=on: setter(b, on))
        if not ok:
            return None, f'attack not offered (condition {on})'
        want = base + (n if on else 0)
        out.append((on, dealt(b), want))
    bad = [o for o in out if o[1] != o[2]]
    return not bad, '; '.join(f"cond={c}: did {g}, want {w}" for c, g, w in out)


TGT = r"(this pokémon|your opponent's active pokémon|the defending pokémon)"
CASES = [
    SweepCase('dmg_per_energy',
              r"^(?:this attack )?does (\d+) (more )?damage (?:for each|times the (?:number|amount) of) "
              r"(?:(\w+) )?energy attached to (this pokémon|your opponent's active pokémon|"
              r"the defending pokémon|both active pokémon)\.$", per_energy),
    SweepCase('dmg_per_counter',
              r"^(?:this attack )?does (\d+) (more |less )?damage (?:for each|times the number of) "
              rf"damage counters? on {TGT}\.$", per_counter),
    SweepCase('dmg_minus_per_counter',
              r"^(?:this attack )?does \d+ damage (minus) (\d+) damage for each damage counter on "
              rf"{TGT}\.$",
              lambda test, d, a, m: per_counter(test, d, a, _Shift(m))),
    SweepCase('dmg_per_bench',
              r"^(?:this attack )?does (\d+) (more )?damage (?:for each|times the number of) "
              r"(of your benched pokémon|of your opponent's benched pokémon|of your pokémon in play|"
              r"pokémon in play \(both yours and your opponent's\))\.$", per_bench),
    SweepCase('self_damage', r"^this pokémon (also )?does (\d+) damage to itself\.$", self_damage),
    SweepCase('ignore_wr_effects',
              r"^this attack's damage isn't affected by (weakness|resistance|weakness or resistance|"
              r"weakness, resistance, or any other effects on (?:your opponent's active pokémon|"
              r"the defending pokémon)|any effects on (?:your opponent's active pokémon|"
              r"the defending pokémon)|weakness or resistance, or by any effects on your "
              r"opponent's active pokémon)\.$", ignore_mods),
    SweepCase('bench_snipe',
              r"^(?:this attack )?(also )?does (\d+) damage to (1|2) of your opponent's benched pokémon\."
              + DONT + "$", bench_snipe),
    SweepCase('spread_damage',
              r"^(?:this attack )?(also )?does (\d+) damage to each of your opponent's (benched )?pokémon\."
              + DONT + "$", spread),
    SweepCase('any_snipe',
              r"^(?:this attack )?does (\d+) damage to 1 of your opponent's pokémon\." + DONT + "$",
              any_snipe),
    SweepCase('conditional_bonus',
              r"^if ([^,]+), this attack does (\d+) more damage\.$", cond_bonus),
]


class _Shift:
    """Adapts 'N damage minus M for each counter' to per_counter's groups."""
    def __init__(self, m):
        self.m = m

    def group(self, i):
        return {1: self.m.group(2), 2: 'minus', 3: self.m.group(3)}[i]


class SweepDamage(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    LIMIT = None

    async def test_sweep(self):
        import os
        only = os.environ.get('SWEEP_ONLY')
        limit = int(os.environ['SWEEP_LIMIT']) if os.environ.get('SWEEP_LIMIT') else self.LIMIT
        for case in CASES:
            if only and case.name not in only.split(','):
                continue
            checked, failures, skipped = await run_sweep(self, case, limit=limit)
            print(f"{case.name}: checked {checked}, failures {len(failures)}, skipped {len(skipped)}")


if __name__ == "__main__":
    unittest.main()
