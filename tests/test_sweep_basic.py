"""Sweep: plain-damage attacks, Special Conditions, draw N."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.sweep_core import SweepCase, run_sweep, std_board, do_attack, dealt
from spirit.game.data_utils import Attack
from spirit.tools.effect_smoke import P1, P2

COND = {'asleep': 'Asleep', 'burned': 'Burned', 'confused': 'Confused',
        'paralyzed': 'Paralyzed', 'poisoned': 'Poisoned'}


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


async def vanilla(test, d, attack, m):
    if not attack.damage or has_ability(d) or (attack.damage_operator or '') not in ('', None):
        return None, 'has text/ability or no damage'
    b = std_board(test, d, attack)
    if not await do_attack(b):
        return False, 'attack not offered with its cost paid'
    got = dealt(b)
    return got == attack.damage, f"did {got}, printed {attack.damage}"


async def condition(test, d, attack, m):
    b = std_board(test, d, attack)
    if not await do_attack(b):
        return False, 'attack not offered'
    want = {COND[w] for w in m.groups() if w}
    got = b.t.conditions(b.opp)
    expect_damage = attack.damage or 0
    ok = want <= got and (has_ability(d) or dealt(b) == expect_damage)
    return ok, f"conditions {sorted(got)} (want {sorted(want)}), damage {dealt(b)} (printed {expect_damage})"


async def draw(test, d, attack, m):
    n = 1 if m.group(1) == 'a' else int(m.group(1))
    b = std_board(test, d, attack)
    if not await do_attack(b):
        return False, 'attack not offered'
    got = len(b.t.zone(P1, 'hand')) - b.before['my_hand']
    return got == n, f"drew {got}, should draw {n}"


CASES = [
    SweepCase('vanilla_damage', r'^$', vanilla),
    SweepCase('special_condition',
              r"^your opponent's active pokémon is now (asleep|burned|confused|paralyzed|poisoned)"
              r"(?: and (asleep|burned|confused|paralyzed|poisoned))?\.$", condition),
    SweepCase('defending_condition',
              r"^the defending pokémon is now (asleep|burned|confused|paralyzed|poisoned)"
              r"(?: and (asleep|burned|confused|paralyzed|poisoned))?\.$", condition),
    SweepCase('draw_n', r"^draw (\d+|a) cards?\.$", draw),
]


class SweepBasic(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_sweep(self):
        for case in CASES:
            checked, failures, skipped = await run_sweep(self, case)
            print(f"{case.name}: checked {checked}, failures {len(failures)}, skipped {len(skipped)}")


if __name__ == "__main__":
    unittest.main()
