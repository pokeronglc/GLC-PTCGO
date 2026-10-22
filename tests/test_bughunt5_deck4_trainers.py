"""Bug hunt round 5, deck 4 (Colorless): Trainers and Special Energy checked
against their printed text, including the cases where they should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, F = PokemonTypes.WATER, PokemonTypes.FIGHTING
KUKUI = 'SM1.ProfessorKukui_128'
WARP, LUCKY, WGUARD = 'SL.WarpEnergy_70', 'SWSH6.LuckyEnergy_158', 'SM11.WeaknessGuardEnergy_213'
PIDGEY = 'SM9.Pidgey_122'          # Quick Attack [C] 10+
SLAKOTH = 'SM11.Slakoth_168'       # Scratch [CC] 30, Weakness Fighting x2
TIMBURR = 'BW1.Timburr_58'         # Pound [FF] 30, Fighting
MARSHTOMP = 'SM7.Marshtomp_34'     # Muddy Water: 20 to a Benched Pokémon


class Bughunt5Deck4Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    @staticmethod
    def lost(p, hp=400):
        return hp - p.get_attribute(AttrID.HP, 0)

    async def test_set_codes(self):
        for path, code in ((KUKUI, 'SM1'), (WARP, 'SL'), (LUCKY, 'SWSH6'),
                           (WGUARD, 'SM11'), (TIMBURR, 'BW1')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Professor Kukui (SUM 128) ------------------------------------------
    async def test_kukui_draws_two_and_adds_20_this_turn(self):
        t = self.table()
        s = t.put(SLAKOTH, P1, 'active')
        t.energy(s, W, 2)
        kukui = t.put(KUKUI, P1, 'hand')
        await t.play(kukui)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertIn(kukui, t.zone(P1, 'discard'))
        await t.attack(s, 'Scratch')
        self.assertEqual(self.lost(self.opp), 50)

    async def test_kukui_bonus_before_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [PokemonTypes.COLORLESS.value])
        s = t.put(SLAKOTH, P1, 'active')
        t.energy(s, W, 2)
        await t.play(t.put(KUKUI, P1, 'hand'))
        await t.attack(s, 'Scratch')
        self.assertEqual(self.lost(self.opp), (30 + 20) * 2)

    async def test_kukui_bonus_expires_next_turn(self):
        t = self.table()
        s = t.put(SLAKOTH, P1, 'active')
        t.energy(s, W, 2)
        await t.play(t.put(KUKUI, P1, 'hand'))
        t.next_turn(); t.next_turn()
        await t.attack(s, 'Scratch')
        self.assertEqual(self.lost(self.opp), 30)

    async def test_kukui_bonus_not_on_bench_damage(self):
        t = self.table()
        m = t.put(MARSHTOMP, P1, 'active')
        t.energy(m, W, 2)
        bench = t.put(self.filler, P2, 'bench')
        self.big(bench)
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.play(t.put(KUKUI, P1, 'hand'))
        await t.attack(m, 'Muddy Water')
        self.assertEqual(self.lost(bench), 20)

    async def test_kukui_bonus_does_not_help_opponent(self):
        t = self.table(TIMBURR)
        mine = t.put(self.filler, P1, 'active')
        self.big(mine)
        await t.play(t.put(KUKUI, P1, 'hand'))
        t.next_turn()
        t.energy(self.opp, F, 2)
        await t.attack(self.opp, 'Pound', pid=P2)
        self.assertEqual(self.lost(mine), 30)

    # --- Warp Energy (SLG 70) ------------------------------------------------
    async def test_warp_energy_to_active_switches(self):
        t = self.table()
        a = t.put(self.filler, P1, 'active')
        b = t.put(SLAKOTH, P1, 'bench')
        warp = t.put(WARP, P1, 'hand')
        t.pokemon = lambda c, p: b if b in c else c[0]
        await t.play(warp, targets=[a.entity_id])
        self.assertIn(warp, a.children)
        self.assertIs(t.active(P1), b)
        self.assertIn(a, t.zone(P1, 'bench'))

    async def test_warp_energy_to_bench_no_switch(self):
        t = self.table()
        a = t.put(self.filler, P1, 'active')
        b = t.put(SLAKOTH, P1, 'bench')
        warp = t.put(WARP, P1, 'hand')
        await t.play(warp, targets=[b.entity_id])
        self.assertIn(warp, b.children)
        self.assertIs(t.active(P1), a)

    async def test_warp_energy_no_bench_still_attaches(self):
        t = self.table()
        a = t.put(self.filler, P1, 'active')
        warp = t.put(WARP, P1, 'hand')
        await t.play(warp, targets=[a.entity_id])
        self.assertIn(warp, a.children)
        self.assertIs(t.active(P1), a)

    async def test_warp_energy_provides_colorless(self):
        t = self.table()
        p = t.put(PIDGEY, P1, 'active')
        t.attach(WARP, p)
        self.assertIsNotNone(t.attack_offer(p, 'Quick Attack'))

    # --- Lucky Energy (CRE 158) ----------------------------------------------
    async def _opp_attacks(self, t, attack='Pound'):
        t.next_turn()
        t.energy(self.opp, F, 2)
        await t.attack(self.opp, attack, pid=P2)

    async def test_lucky_energy_draws_when_active_damaged(self):
        t = self.table(TIMBURR)
        mine = t.put(self.filler, P1, 'active')
        self.big(mine)
        t.attach(LUCKY, mine)
        hand = len(t.zone(P1, 'hand'))
        await self._opp_attacks(t)
        self.assertEqual(self.lost(mine), 30)
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 1)

    async def test_lucky_energy_draws_even_if_knocked_out(self):
        t = self.table(TIMBURR)
        mine = t.put(self.filler, P1, 'active', hp=30)
        mine.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mine.set_attribute(AttrID.RESISTANCE_TYPES, [])
        t.put(self.filler, P1, 'bench')
        t.attach(LUCKY, mine)
        hand = len(t.zone(P1, 'hand'))
        await self._opp_attacks(t)
        self.assertNotIn(mine, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 1)

    async def test_lucky_energy_no_draw_on_bench(self):
        t = Table(self)
        self.opp = t.put(MARSHTOMP, P2, 'active')
        self.big(self.opp)
        mine = t.put(self.filler, P1, 'active')
        self.big(mine)
        benched = t.put(self.filler, P1, 'bench')
        self.big(benched)
        t.attach(LUCKY, benched)
        t.pokemon = lambda c, p: benched if benched in c else c[0]
        hand = len(t.zone(P1, 'hand'))
        t.next_turn()
        t.energy(self.opp, W, 2)
        await t.attack(self.opp, 'Muddy Water', pid=P2)
        self.assertEqual(self.lost(benched), 20)
        self.assertEqual(len(t.zone(P1, 'hand')), hand)

    async def test_lucky_energy_no_draw_on_own_attack_or_undamaged(self):
        t = self.table()
        p = t.put(PIDGEY, P1, 'active')
        self.big(p)
        t.attach(LUCKY, p)
        hand = len(t.zone(P1, 'hand'))
        await t.attack(p, 'Quick Attack')       # Lucky provides [C]
        self.assertEqual(self.lost(self.opp), 20)
        self.assertEqual(len(t.zone(P1, 'hand')), hand)

    # --- Weakness Guard Energy (UNM 213) -------------------------------------
    async def test_weakness_guard_removes_weakness(self):
        t = self.table(TIMBURR)
        s = t.put(SLAKOTH, P1, 'active')
        s.set_attribute(AttrID.HP, 400)
        t.attach(WGUARD, s)
        await self._opp_attacks(t)
        self.assertEqual(self.lost(s), 30)

    async def test_without_weakness_guard_weakness_applies(self):
        t = self.table(TIMBURR)
        s = t.put(SLAKOTH, P1, 'active')
        s.set_attribute(AttrID.HP, 400)
        await self._opp_attacks(t)
        self.assertEqual(self.lost(s), 60)

    async def test_weakness_guard_provides_colorless(self):
        t = self.table()
        p = t.put(PIDGEY, P1, 'active')
        t.attach(WGUARD, p)
        self.assertIsNotNone(t.attack_offer(p, 'Quick Attack'))


if __name__ == '__main__':
    unittest.main()
