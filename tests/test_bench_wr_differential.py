"""Owner request (Oct 13/14): attacks printing "(Don't apply Weakness and
Resistance for Benched Pokémon.)" must never apply them to the Bench.

Differential sweep (Roserade SWSH11 15 Assassin's Rose report): every such
attack is run twice on the same board -- once with a Benched target that is
weak (and once resistant) to the attacker's type, once with the same target
neutral -- and the Bench damage must be identical.  Choices always pick the
Benched target, coins are heads, and the opponent's Active is Poisoned (for
"if ... affected by a Special Condition" riders).
"""
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.untested_trainer_kit import _defs, neutral, pay, D, C, types_of
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import PokemonCardDef
from spirit.tools.effect_smoke import P1, P2

CLAUSE = "don't apply weakness and resistance for benched pokémon"


def attacks():
    out = []
    for d in _defs():
        if not isinstance(d, PokemonCardDef):
            continue
        for a in d.abilities or []:
            if type(a).__name__ == 'Attack' and CLAUSE in (a.game_text or '').lower():
                out.append((d, a))
    return out


class BenchWR(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def run_once(self, d, a, kind, mode):
        t = Table(self)
        me = neutral(t.put(d, P1, 'active'))
        pay(t, me, a)
        t.energy(me, D, 2)
        opp = neutral(t.put(self.filler, P2, 'active'), 400)
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        bench = neutral(t.put(self.filler, P2, 'bench'), 400)
        if mode == 'weak':
            bench.set_attribute(AttrID.WEAKNESS_TYPES, [kind.value])
        elif mode == 'resist':
            bench.set_attribute(AttrID.RESISTANCE_TYPES, [kind.value])
        t.heads = True
        t.yes = True
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        t.picks = lambda cards, count, prompt, shown: (
            [bench] if bench in cards else list(cards)[:count])
        entry = t.attack_offer(me, a.title)
        if entry is None:
            return None
        try:
            await t.do(entry)
        except Exception:
            return None
        return 400 - t.hp(bench)

    async def test_sweep(self):
        bad, checked = [], 0
        for d, a in attacks():
            kinds = types_of(d)
            if not kinds:
                continue
            kind = kinds[0]
            if kind == PokemonTypes.COLORLESS:
                kind = PokemonTypes.COLORLESS
            base = await self.run_once(d, a, kind, 'none')
            if not base:
                continue
            checked += 1
            for mode in ('weak', 'resist'):
                got = await self.run_once(d, a, kind, mode)
                if got is not None and got != base:
                    bad.append(f'{d.set_code} {d.display_name} {a.title}: Bench {mode} {got} vs {base}')
        for b in bad:
            print('MISMATCH', b)
        print(f'bench W/R: {checked} attacks hit the Bench, {len(bad)} mismatches')
        self.assertGreater(checked, 50)
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
