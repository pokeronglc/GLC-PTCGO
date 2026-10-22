"""Bug hunt round 6, deck 0 (Water): Cetoddle PAL 53, Cetitan PAL 55,
Snom SSH 63, Wailmer CRZ 31, Wailord SIT 38, Articuno TEU 32."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

W, F, D = PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.DARKNESS
CETODDLE, CETITAN = 'SV2.Cetoddle_53', 'SV2.Cetitan_55'
SNOM, WAILMER, WAILORD = 'SWSH1.Snom_63', 'CZ.Wailmer_31', 'SWSH12.Wailord_38'
ARTICUNO = 'SM9.Articuno_32'
SPECIAL = 'ME3.GrowingGrassEnergy_86'      # a Special Energy
SABLEYE = 'SV2.Sableye_136'                # Unseen Claw 20 for [D]
BOSS = 'SWSH2.BosssOrders_154'


class Deck0Cards6(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        mon._start_hp = mon.get_attribute(AttrID.HP, 0)
        return mon

    @staticmethod
    def took(t, mon):
        return mon._start_hp - t.hp(mon)

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    # --- Cetoddle: Avalanche ------------------------------------------------
    async def test_avalanche_hits_each_opponent_bench_not_own(self):
        t = self.table()
        c = t.put(CETODDLE, P1, 'active')
        t.energy(c, W, 2)
        b1 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        b2 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        mine = self.neutral(t.put(self.filler, P1, 'bench'))
        await t.attack(c, 'Avalanche')
        self.assertEqual(self.took(t, self.opp), 30)
        self.assertEqual((self.took(t, b1), self.took(t, b2)), (10, 10))
        self.assertEqual(self.took(t, mine), 0)

    async def test_avalanche_no_weakness_on_bench(self):
        t = self.table()
        c = t.put(CETODDLE, P1, 'active')
        t.energy(c, W, 2)
        b = t.put(self.filler, P2, 'bench')
        b.set_attribute(AttrID.WEAKNESS_TYPES, [W.value])
        b.set_attribute(AttrID.HP, 300)
        b._start_hp = 300
        await t.attack(c, 'Avalanche')
        self.assertEqual(self.took(t, b), 10)

    # --- Cetitan: Special Horn ---------------------------------------------
    async def test_special_horn_with_special_energy(self):
        t = self.table()
        c = t.put(CETITAN, P1, 'active')
        t.energy(c, W, 3)
        t.attach(SPECIAL, c)
        await t.attack(c, 'Special Horn')
        self.assertEqual(self.took(t, self.opp), 220)

    async def test_special_horn_without_special_energy(self):
        t = self.table()
        c = t.put(CETITAN, P1, 'active')
        t.energy(c, W, 4)
        await t.attack(c, 'Special Horn')
        self.assertEqual(self.took(t, self.opp), 80)

    # --- Wailmer: Nap --------------------------------------------------------
    async def test_nap_heals_30(self):
        t = self.table()
        w = t.put(WAILMER, P1, 'active', hp=60)
        t.energy(w, W)
        await t.attack(w, 'Nap')
        self.assertEqual(t.hp(w), 90)
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_nap_does_not_overheal(self):
        t = self.table()
        w = t.put(WAILMER, P1, 'active', hp=110)
        t.energy(w, W)
        await t.attack(w, 'Nap')
        self.assertEqual(t.hp(w), 120)

    # --- Wailord: Jumbo-Sized / Special Wave --------------------------------
    async def test_jumbo_sized_after_weakness(self):
        t = Table(self)
        w = t.put(WAILORD, P1, 'active')
        w.set_attribute(AttrID.RESISTANCE_TYPES, [])
        w.set_attribute(AttrID.WEAKNESS_TYPES, [D.value])
        opp = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(opp, D)
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        # 20 x2 weakness = 40, then -30 = 10
        self.assertEqual(t.damage(w), 10)

    async def test_jumbo_sized_floors_at_zero(self):
        t = Table(self)
        w = self.neutral(t.put(WAILORD, P1, 'active'))
        opp = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(opp, D)
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertEqual(t.damage(w), 0)

    async def test_special_wave_with_and_without_special(self):
        t = self.table()
        w = t.put(WAILORD, P1, 'active')
        t.energy(w, W, 4)
        await t.attack(w, 'Special Wave')
        self.assertEqual(self.took(t, self.opp), 120)
        t2 = self.table()
        w2 = t2.put(WAILORD, P1, 'active')
        t2.energy(w2, W, 3)
        t2.attach(SPECIAL, w2)
        await t2.attack(w2, 'Special Wave')
        self.assertEqual(self.took(t2, self.opp), 240)

    # --- Articuno: Blizzard Veil / Cold Cyclone -----------------------------
    def veil_board(self, articuno_zone='active'):
        t = Table(self)
        art = t.put(ARTICUNO, P1, articuno_zone)
        if articuno_zone == 'bench':
            t.put(self.filler, P1, 'active')
        snom = t.put(SNOM, P1, 'bench')
        t.put(self.filler, P2, 'active')
        t.next_turn()
        boss = t.put(BOSS, P2, 'hand')
        return t, art, snom, boss

    # FIXED (was BUG): Blizzard Veil text is not handled by _BWTextPassive.blocks_trainer_effects (no effect)
    async def test_blizzard_veil_blocks_boss_on_benched_water(self):
        t, art, snom, boss = self.veil_board()
        other = t.put(self.filler, P1, 'bench')
        seen = []
        t.pokemon = lambda cands, prompt: (seen.extend(cands), snom if snom in cands else cands[0])[1]
        if t.can(boss, 'UseTrainerCard', pid=P2):
            await t.play(boss, pid=P2)
        self.assertNotIn(snom, seen)
        self.assertIn(snom, t.zone(P1, 'bench'))
        self.assertIs(t.active(P1), other)

    # FIXED (was BUG): Blizzard Veil text is not handled by _BWTextPassive.blocks_trainer_effects (no effect)
    async def test_blizzard_veil_only_benched_water_boss_does_nothing(self):
        t, art, snom, boss = self.veil_board()
        if t.can(boss, 'UseTrainerCard', pid=P2):
            await t.play(boss, pid=P2)
        self.assertIs(t.active(P1), art)
        self.assertIn(snom, t.zone(P1, 'bench'))

    async def test_blizzard_veil_not_from_bench(self):
        t, art, snom, boss = self.veil_board('bench')
        t.pokemon = lambda cands, prompt: snom if snom in cands else cands[0]
        await t.play(boss, pid=P2)
        self.assertIs(t.active(P1), snom)

    async def test_blizzard_veil_does_not_protect_non_water(self):
        t = Table(self)
        art = t.put(ARTICUNO, P1, 'active')
        other = t.put(self.filler, P1, 'bench')
        t.put(self.filler, P2, 'active')
        t.next_turn()
        boss = t.put(BOSS, P2, 'hand')
        await t.play(boss, pid=P2)
        self.assertIs(t.active(P1), other)

    async def test_cold_cyclone_moves_two_water(self):
        t = self.table()
        art = t.put(ARTICUNO, P1, 'active')
        t.energy(art, W, 3)
        b = t.put(self.filler, P1, 'bench')
        t.picks = lambda cards, count, prompt, display: cards[:count]
        await t.attack(art, 'Cold Cyclone')
        self.assertEqual(self.took(t, self.opp), 70)
        self.assertEqual(len(b.children), 2)
        self.assertEqual(len(art.children), 1)

    async def test_cold_cyclone_only_water_moved(self):
        t = self.table()
        art = t.put(ARTICUNO, P1, 'active')
        t.energy(art, W, 2)
        fire = t.energy(art, F)
        b = t.put(self.filler, P1, 'bench')
        await t.attack(art, 'Cold Cyclone')
        self.assertIn(fire, art.children)
        self.assertEqual(len(b.children), 2)

    async def test_cold_cyclone_no_bench_keeps_energy(self):
        t = self.table()
        art = t.put(ARTICUNO, P1, 'active')
        t.energy(art, W, 2)
        await t.attack(art, 'Cold Cyclone')
        self.assertEqual(self.took(t, self.opp), 70)
        self.assertEqual(len(art.children), 2)


if __name__ == '__main__':
    unittest.main()
