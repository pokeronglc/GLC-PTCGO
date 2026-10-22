"""Bug hunt round 2, deck 5 (Water): the Pokémon."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, D = PokemonTypes.WATER, PokemonTypes.DARKNESS
TOTODILE, CROCONAW, FERALIGATR = 'SV05.Totodile_39', 'SL.Croconaw_19', 'SV05.Feraligatr_41'
STARYU, STARMIE = 'SV10.MistysStaryu_46', 'SV10.MistysStarmie_47'
FINIZEN, PALAFIN = 'SV06.Finizen_59', 'SV05.Palafin_49'
CASTFORM, MANAPHY = 'SWSH6.CastformSnowyForm_34', 'SWSH9.Manaphy_41'
ARTAZON = 'SV2.Artazon_171'
CROBAT = 'SWSH12.Crobat_105'      # Critical Bite: 30 to a Benched Pokémon
SABLEYE = 'SV2.Sableye_136'       # Unseen Claw: 20 to the Active


class Deck5Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    # --- Totodile: Big Bite --------------------------------------------------
    async def test_big_bite_blocks_retreat_one_turn(self):
        t = self.table()
        toto = t.put(TOTODILE, P1, 'active')
        t.energy(toto, W)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W, 4)
        await t.attack(toto, 'Big Bite')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))

    # --- Croconaw: Plunge ---------------------------------------------------
    # Was a bug (fixed Oct 10): Plunge only switches; generic 'switch it with your active' branch in bw_legacy_ability never moves the Energy
    async def test_plunge_moves_all_energy_and_switches(self):
        t = self.table()
        active = t.put(self.filler, P1, 'active')
        energies = t.energy(active, W, 2) + [t.energy(active, D, 1)]
        croc = t.put(CROCONAW, P1, 'bench')
        await t.use(croc, 'Plunge')
        self.assertIs(t.active(P1), croc)
        self.assertEqual(set(t.board.attached_energies(croc)), set(energies))
        self.assertEqual(list(t.board.attached_energies(active)), [])
        self.assertIn(active, t.zone(P1, 'bench'))

    async def test_plunge_not_from_active(self):
        t = self.table()
        croc = t.put(CROCONAW, P1, 'active')
        t.energy(croc, W)
        t.put(self.filler, P1, 'bench')
        self.assertIsNone(t.ability_offer(croc, 'Plunge'))

    # --- Feraligatr: Torrential Heart / Giant Wave --------------------------
    # Was a bug (fixed Oct 10): Torrential Heart places 5 counters but never adds the +120 (self-counter fallback returns early)
    async def test_torrential_heart_50_self_and_120_more(self):
        t = self.table()
        fera = t.put(FERALIGATR, P1, 'active')
        t.energy(fera, W, 2)
        await t.use(fera, 'Torrential Heart')
        self.assertEqual(t.damage(fera), 50)
        self.assertIsNone(t.ability_offer(fera, 'Torrential Heart'))
        await t.attack(fera, 'Giant Wave')
        self.assertEqual(400 - t.hp(self.opp), 280)

    async def test_torrential_heart_expires_and_giant_wave_lock(self):
        t = self.table()
        fera = t.put(FERALIGATR, P1, 'active')
        t.energy(fera, W, 2)
        await t.use(fera, 'Torrential Heart')
        t.next_turn(); t.next_turn()
        # boost was "during this turn" only; Giant Wave was not used, so no lock
        await t.attack(fera, 'Giant Wave')
        self.assertEqual(400 - t.hp(self.opp), 160)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(fera, 'Giant Wave'))

    async def test_torrential_heart_no_boost_to_bench_damage(self):
        # Boost is for the Active only: a benched Feraligatr's use boosts
        # nobody else either (ability text: "attacks used by this Pokémon").
        t = self.table()
        fera = t.put(FERALIGATR, P1, 'bench')
        sab = t.put(SABLEYE, P1, 'active')
        t.energy(sab, D)
        await t.use(fera, 'Torrential Heart')
        await t.attack(sab, 'Unseen Claw')
        self.assertEqual(400 - t.hp(self.opp), 20)

    # --- Misty's Staryu / Starmie --------------------------------------------
    async def test_bubble_beam(self):
        for heads in (True, False):
            t = self.table()
            staryu = t.put(STARYU, P1, 'active')
            t.energy(staryu, W)
            t.heads = heads
            await t.attack(staryu, 'Bubble Beam')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 20)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    async def test_abrupt_flash_evolved_this_turn(self):
        t = self.table()
        staryu = t.put(STARYU, P1, 'active')
        t.energy(staryu, W)
        starmie = t.put(STARMIE, P1, 'hand')
        await t.play(starmie, targets=[staryu.entity_id])
        self.assertIs(t.active(P1), starmie)
        await t.attack(starmie, 'Abrupt Flash')
        self.assertEqual(400 - t.hp(self.opp), 140)

    async def test_abrupt_flash_not_evolved_this_turn(self):
        t = self.table()
        staryu = t.put(STARYU, P1, 'active')
        t.energy(staryu, W)
        starmie = t.put(STARMIE, P1, 'hand')
        await t.play(starmie, targets=[staryu.entity_id])
        t.next_turn(); t.next_turn()
        await t.attack(starmie, 'Abrupt Flash')
        self.assertEqual(400 - t.hp(self.opp), 60)

    async def test_abrupt_flash_put_into_play_not_evolved(self):
        t = self.table()
        starmie = t.put(STARMIE, P1, 'active')
        t.energy(starmie, W)
        await t.attack(starmie, 'Abrupt Flash')
        self.assertEqual(400 - t.hp(self.opp), 60)

    # --- Finizen: Aqua Slash --------------------------------------------------
    async def test_aqua_slash_cant_attack_next_turn(self):
        t = self.table()
        fin = t.put(FINIZEN, P1, 'active')
        t.energy(fin, W)
        await t.attack(fin, 'Aqua Slash')
        self.assertEqual(400 - t.hp(self.opp), 30)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(fin, 'Aqua Slash'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(fin, 'Aqua Slash'))

    # --- Palafin ------------------------------------------------------------
    async def test_vanguard_punch_self_damage(self):
        for counters in (0, 3):
            t = self.table()
            pal = t.put(PALAFIN, P1, 'active')
            t.energy(pal, W)
            pal.set_attribute(AttrID.HP, t.hp(pal) - 10 * counters)
            await t.attack(pal, 'Vanguard Punch')
            with self.subTest(counters=counters):
                self.assertEqual(400 - t.hp(self.opp), 130)
                self.assertEqual(t.damage(pal), 10 * counters * 2)

    async def test_double_hit(self):
        for heads, dmg in ((True, 180), (False, 0)):
            t = self.table()
            pal = t.put(PALAFIN, P1, 'active')
            t.energy(pal, W, 3)
            t.heads = heads
            await t.attack(pal, 'Double Hit')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)
        t = self.table()
        pal = t.put(PALAFIN, P1, 'active')
        t.energy(pal, W, 3)
        flips = iter([True, False])
        t.heads = lambda title: next(flips)
        await t.attack(pal, 'Double Hit')
        self.assertEqual(400 - t.hp(self.opp), 90)

    # --- Castform Snowy Form: Weather Reading ---------------------------
    async def test_weather_reading_eight_stadiums(self):
        for count, offered in ((8, True), (7, False)):
            t = self.table()
            cast = t.put(CASTFORM, P1, 'active')
            for _ in range(count):
                t.put(ARTAZON, P1, 'discard')
            with self.subTest(count=count):
                self.assertEqual(t.attack_offer(cast, 'Frosty Typhoon') is not None, offered)

    async def test_weather_reading_opponent_discard_doesnt_count(self):
        t = self.table()
        cast = t.put(CASTFORM, P1, 'active')
        for _ in range(8):
            t.put(ARTAZON, P2, 'discard')
        self.assertIsNone(t.attack_offer(cast, 'Frosty Typhoon'))

    async def test_frosty_typhoon_locked_next_turn(self):
        t = self.table()
        cast = t.put(CASTFORM, P1, 'active')
        for _ in range(8):
            t.put(ARTAZON, P1, 'discard')
        await t.attack(cast, 'Frosty Typhoon')
        self.assertEqual(400 - t.hp(self.opp), 120)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(cast, 'Frosty Typhoon'))

    # --- Manaphy: Wave Veil ------------------------------------------------
    async def _opp_critical_bite(self, with_manaphy, manaphy_side=P1):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        crobat = t.put(CROBAT, P2, 'active')
        t.energy(crobat, D, 3)
        t.put(self.filler, P1, 'active')
        target = t.put(self.filler, P1, 'bench')
        target.set_attribute(AttrID.WEAKNESS_TYPES, [])
        if with_manaphy:
            t.put(MANAPHY, manaphy_side, 'bench')
        t.pokemon = lambda c, p: target if target in c else c[0]
        t.next_turn()
        before = t.hp(target)
        await t.attack(crobat, 'Critical Bite', pid=P2)
        return before - t.hp(target)

    async def test_wave_veil_protects_bench(self):
        self.assertEqual(await self._opp_critical_bite(True), 0)
        self.assertEqual(await self._opp_critical_bite(False), 30)
        # The opponent's Manaphy doesn't protect my Bench
        self.assertEqual(await self._opp_critical_bite(True, manaphy_side=P2), 30)

    async def test_wave_veil_not_active(self):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        sab = t.put(SABLEYE, P2, 'active')
        t.energy(sab, D)
        mine = t.put(self.filler, P1, 'active')
        mine.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.put(MANAPHY, P1, 'bench')
        t.next_turn()
        before = t.hp(mine)
        await t.attack(sab, 'Unseen Claw', pid=P2)
        self.assertEqual(before - t.hp(mine), 20)


if __name__ == "__main__":
    unittest.main()
