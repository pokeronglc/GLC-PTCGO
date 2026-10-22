"""Sweep: coin-flip attack wordings (damage modifiers, conditions, protection,
self-damage, Energy discard, flip-until-tails)."""
import itertools
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.sweep_core import (SweepCase, run_sweep, std_board, do_attack, dealt,
                              neutral, pay_cost, BIG)
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

COND = {'asleep': 'Asleep', 'burned': 'Burned', 'confused': 'Confused',
        'paralyzed': 'Paralyzed', 'poisoned': 'Poisoned'}
CONDS = r"(asleep|burned|confused|paralyzed|poisoned)"
OPP = r"(?:your opponent's active pokémon|the defending pokémon)"


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


def coins(seq):
    """Table.heads callable: yields `seq` then tails forever."""
    it = itertools.chain(seq, itertools.repeat(False))
    return lambda title: next(it)


def _neutral_me(b):
    neutral(b.me, hp=None)


def chain(*fns):
    def run(b):
        for f in fns:
            if f is not None:
                f(b)
    return run


async def attack_with(test, d, attack, heads, *, prep=None, until=None):
    """Board + attack. `heads`: bool or list (per-coin sequence, tails after).
    `until`: fixed number of heads returned by flip_until_tails."""
    def set_coins(b):
        if isinstance(heads, (list, tuple)):
            b.t.heads = coins(heads)
    b = std_board(test, d, attack, heads=bool(heads) if not isinstance(heads, (list, tuple)) else True,
                  my_hp=BIG, prep=chain(_neutral_me, set_coins, prep))
    if until is not None:
        b.t.heads = coins([True] * until)     # in case a script loops flip_coins(1)

        async def fixed(self, title=''):
            return until
        with patch.object(EffectContext, 'flip_until_tails', fixed):
            offered = await do_attack(b)
    else:
        offered = await do_attack(b)
    return b, offered


def dmg_ok(d, got, want):
    return has_ability(d) or got == want


# ---------------------------------------------------------------- checkers
async def heads_more(test, d, attack, m):
    more = int(m.group(1))
    base = attack.damage or 0
    out = []
    ok = True
    for heads, want in ((True, base + more), (False, base)):
        b, offered = await attack_with(test, d, attack, heads)
        if not offered:
            return False, 'attack not offered'
        got = dealt(b)
        ok &= dmg_ok(d, got, want)
        out.append(f"{'H' if heads else 'T'}: did {got} want {want}")
    return (None, 'has ability') if has_ability(d) else (ok, '; '.join(out))


async def tails_nothing(test, d, attack, m):
    base = attack.damage or 0
    if has_ability(d):
        return None, 'has ability'
    out, ok = [], True
    for heads, want in ((True, base), (False, 0)):
        b, offered = await attack_with(test, d, attack, heads)
        if not offered:
            return False, 'attack not offered'
        got = dealt(b)
        ok &= got == want
        out.append(f"{'H' if heads else 'T'}: did {got} want {want}")
    return ok, '; '.join(out)


async def n_coins_each(test, d, attack, m):
    n, per = int(m.group(1)), int(m.group(2))
    more = len(m.groups()) >= 3 and m.group(3) is not None
    base = (attack.damage or 0) if more else 0
    if has_ability(d):
        return None, 'has ability'
    out, ok = [], True
    for seq in ([True] * n, [False] * n, [True] + [False] * (n - 1)):
        b, offered = await attack_with(test, d, attack, list(seq))
        if not offered:
            return False, 'attack not offered'
        want = base + per * sum(seq)
        got = dealt(b)
        ok &= got == want
        out.append(f"{sum(seq)}H: did {got} want {want}")
    return ok, '; '.join(out)


async def n_coins_times(test, d, attack, m):
    return await n_coins_each(test, d, attack, m)


async def until_tails(test, d, attack, m):
    per = int(m.group(1))
    more = bool(m.group(2))
    base = (attack.damage or 0) if more else 0
    if has_ability(d):
        return None, 'has ability'
    out, ok = [], True
    for h in (0, 3):
        b, offered = await attack_with(test, d, attack, True, until=h)
        if not offered:
            return False, 'attack not offered'
        want = base + per * h
        got = dealt(b)
        ok &= got == want
        out.append(f"{h}H: did {got} want {want}")
    return ok, '; '.join(out)


async def heads_condition(test, d, attack, m):
    want = {COND[w] for w in m.groups() if w}
    base = attack.damage or 0
    out, ok = [], True
    for heads in (True, False):
        b, offered = await attack_with(test, d, attack, heads)
        if not offered:
            return False, 'attack not offered'
        got = b.t.conditions(b.opp)
        exp = want if heads else set()
        ok &= got == exp and dmg_ok(d, dealt(b), base)
        out.append(f"{'H' if heads else 'T'}: conds {sorted(got)} want {sorted(exp)}, did {dealt(b)} want {base}")
    return ok, '; '.join(out)


async def opp_hits_back(b):
    """P2's Active (vanilla filler, Heavy Impact 80) attacks next turn.
    Returns damage taken by P1's tested Pokémon, or None if not possible."""
    t = b.t
    atk = next(a for a in t.test.filler.abilities if isinstance(a, Attack))
    pay_cost(t, b.opp, atk)
    t.next_turn()
    hp0 = t.hp(b.me)
    entry = t.attack_offer(b.opp, atk.title, P2)
    if entry is None:
        return None, atk
    await t.do(entry, pid=P2)
    if b.me not in t.board.pokemon_in_play(P1):
        return 'KO', atk
    return hp0 - t.hp(b.me), atk


async def heads_protect(test, d, attack, m):
    tails_nothing_too = bool(m.group(1))
    base = attack.damage or 0
    out, ok = [], True
    for heads in (True, False):
        b, offered = await attack_with(test, d, attack, heads)
        if not offered:
            return False, 'attack not offered'
        did = dealt(b)
        want_did = 0 if (tails_nothing_too and not heads) else base
        ok &= dmg_ok(d, did, want_did)
        taken, atk = await opp_hits_back(b)
        if taken is None:
            return False, 'setup: opponent attack not offered next turn'
        want_taken = 0 if heads else atk.damage
        if heads:
            ok &= taken == 0
        else:
            ok &= has_ability(d) or taken == want_taken
        out.append(f"{'H' if heads else 'T'}: did {did} want {want_did}; took {taken} next turn want {want_taken}")
    return ok, '; '.join(out)


async def tails_self(test, d, attack, m):
    self_dmg = int(m.group(1))
    base = attack.damage or 0
    out, ok = [], True
    for heads in (True, False):
        b, offered = await attack_with(test, d, attack, heads)
        if not offered:
            return False, 'attack not offered'
        me, did = dealt(b, 'me'), dealt(b)
        want_me = 0 if heads else self_dmg
        ok &= me == want_me and dmg_ok(d, did, base)
        out.append(f"{'H' if heads else 'T'}: self {me} want {want_me}; did {did} want {base}")
    return ok, '; '.join(out)


async def more_or_self(test, d, attack, m):
    g = m.groupdict()
    more = int(g['more1'] or g['more2'])
    self_dmg = int(g['self1'] or g['self2'])
    base = attack.damage or 0
    out, ok = [], True
    for heads in (True, False):
        b, offered = await attack_with(test, d, attack, heads)
        if not offered:
            return False, 'attack not offered'
        me, did = dealt(b, 'me'), dealt(b)
        want_me = 0 if heads else self_dmg
        want_did = base + more if heads else base
        ok &= me == want_me and dmg_ok(d, did, want_did)
        out.append(f"{'H' if heads else 'T'}: self {me} want {want_me}; did {did} want {want_did}")
    return ok, '; '.join(out)


def _opp_two_energy(b):
    b.t.energy(b.opp, PokemonTypes.WATER, 2)


async def heads_discard_energy(test, d, attack, m):
    base = attack.damage or 0
    out, ok = [], True
    for heads in (True, False):
        b, offered = await attack_with(test, d, attack, heads, prep=_opp_two_energy)
        if not offered:
            return False, 'attack not offered'
        lost = b.before['opp_energy'] - len(b.t.board.attached_energies(b.opp))
        disc = len(b.t.zone(P2, 'discard')) - b.before['opp_discard']
        want = 1 if heads else 0
        ok &= lost == want and disc == want and dmg_ok(d, dealt(b), base)
        out.append(f"{'H' if heads else 'T'}: opp lost {lost} energy ({disc} to discard) want {want}; "
                   f"did {dealt(b)} want {base}")
    return ok, '; '.join(out)


async def coins_nothing(test, d, attack, m):
    n = int(m.group(1))
    mode = m.group(2)        # 'either of them is tails' | 'both of them are tails'
    base = attack.damage or 0
    if has_ability(d):
        return None, 'has ability'
    out, ok = [], True
    for seq in ([True] * n, [False] * n, [True] + [False] * (n - 1)):
        b, offered = await attack_with(test, d, attack, list(seq))
        if not offered:
            return False, 'attack not offered'
        if mode.startswith('either'):
            want = base if all(seq) else 0
        else:
            want = 0 if not any(seq) else base
        got = dealt(b)
        ok &= got == want
        out.append(f"{sum(seq)}H: did {got} want {want}")
    return ok, '; '.join(out)


PROTECT = (r"(?:prevent all effects of attacks, including damage, done to this pokémon during your opponent's next turn"
           r"|during your opponent's next turn, prevent all damage from and effects of attacks done to this pokémon"
           r"|during your opponent's next turn, prevent all effects of attacks, including damage, done to this pokémon"
           r"|prevent all damage done to this pokémon by attacks during your opponent's next turn"
           r"|during your opponent's next turn, prevent all damage done to this pokémon by attacks)")

CASES = [
    SweepCase('coin_heads_more', r"^flip a coin\. if heads, this attack does (\d+) more damage\.$", heads_more),
    SweepCase('coin_tails_nothing', r"^flip a coin\. if tails, this attack does nothing\.$", tails_nothing),
    SweepCase('coins_damage_each',
              r"^flip (\d+) coins\. this attack does (\d+) damage (?:for each heads|times the number of heads)\.$",
              n_coins_each),
    SweepCase('coins_more_each',
              r"^flip (\d+) coins\. this attack does (\d+) (more) damage for each heads\.$", n_coins_each),
    SweepCase('until_tails',
              r"^flip a coin until you get tails\. this attack does (\d+) (more )?damage "
              r"(?:for each heads|times the number (?:of )?heads)\.$", until_tails),
    SweepCase('coin_condition',
              rf"^flip a coin\. if heads, {OPP} is now {CONDS}(?: and {CONDS})?\.$", heads_condition),
    SweepCase('coin_protect',
              rf"^flip a coin\. (if tails, this attack does nothing\. )?if heads, {PROTECT}\.$", heads_protect),
    SweepCase('coin_tails_self',
              r"^flip a coin\. if tails, this pokémon (?:also )?does (\d+) damage to itself\.$", tails_self),
    SweepCase('coin_more_or_self',
              r"^flip a coin\. (?:if heads, this attack does (?P<more1>\d+) more damage\. "
              r"if tails, this pokémon (?:also )?does (?P<self1>\d+) damage to itself"
              r"|if tails, this pokémon (?:also )?does (?P<self2>\d+) damage to itself\. "
              r"if heads, this attack does (?P<more2>\d+) more damage)\.$", more_or_self),
    SweepCase('coin_discard_energy',
              rf"^flip a coin\. if heads, discard an energy (?:from|attached to) {OPP}\.$", heads_discard_energy),
    SweepCase('coins_nothing',
              r"^flip (\d+) coins\. if (either of them is tails|both of them are tails), this attack does nothing\.$",
              coins_nothing),
]


class SweepCoins(unittest.IsolatedAsyncioTestCase):
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
