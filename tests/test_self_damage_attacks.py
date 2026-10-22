"""Attacks that also hurt your own Pokémon (Shadow Impact, Raging Thunder,
Earthquake, Superpower)."""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2


class SelfDamageAttackTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def run_attack(self, path, title, yes=True):
        rig, e = self.rig(path)
        board = rig.board
        attack = next(a for a in fixtures.definition(path).abilities if a.title == title)
        before = {p.entity_id: p.get_attribute(AttrID.HP)
                  for pid in (P1, P2) for p in board.pokemon_in_play(pid)}
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        ctx.ask_yes_no = AsyncMock(return_value=yes)
        await attack.effect(ctx)
        lost = {pid: [before[p.entity_id] - p.get_attribute(AttrID.HP)
                      for p in board.pokemon_in_play(pid)
                      if before[p.entity_id] != p.get_attribute(AttrID.HP)]
                for pid in (P1, P2)}
        return lost

    async def test_shadow_impact_puts_counters_on_own_pokemon(self):
        for path in ('SM8.Giratina_97', 'SM12.Trevenant_94', 'SM11.Yveltal_139'):
            with self.subTest(path=path):
                lost = await self.run_attack(path, 'Shadow Impact')
                self.assertEqual(len(lost[P1]), 1)
                self.assertIn(lost[P1][0], (30, 40))
                self.assertTrue(lost[P2])

    async def test_raging_thunder_hits_own_bench(self):
        lost = await self.run_attack('SV4.Zekrom_66', 'Raging Thunder')
        self.assertEqual(lost[P1], [40])

    async def test_bw_earthquake_hits_own_bench_once(self):
        lost = await self.run_attack('BW2.Excadrill_57', 'Earthquake')
        self.assertTrue(lost[P1])
        self.assertTrue(all(amount == 10 for amount in lost[P1]))

    async def test_optional_recoil_only_when_chosen(self):
        lost = await self.run_attack('SV06.Gurdurr_104', 'Superpower', yes=True)
        self.assertEqual(lost[P1], [30])
        lost = await self.run_attack('SV06.Gurdurr_104', 'Superpower', yes=False)
        self.assertEqual(lost[P1], [])


if __name__ == "__main__":
    unittest.main()
