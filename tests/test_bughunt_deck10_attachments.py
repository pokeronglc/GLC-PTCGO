"""Bug hunt, deck 10 (Darkness): Tools, Stadiums and Special Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

D = PokemonTypes.DARKNESS
ZUBAT, GOLBAT, CROBAT = 'ME4.Zubat_49', 'SWSH5.Golbat_90', 'SWSH12.Crobat_105'
SABLEYE, LELE, PECHARUNT = 'SV2.Sableye_136', 'Promo_SM.TapuLele_152', 'SVP.Pecharunt_149'
DARK_CLAW, FLOAT, UTURN = 'BW5.DarkClaw_92', 'XY8.FloatStone_137', 'SM11.UTurnBoard_211'
BEACH, ARTAZON, JUNGLE = 'PROMO_BW.TropicalBeach_BW50', 'SV2.Artazon_171', 'SV05.PerilousJungle_156'
HIDING, SHADOWY, IGNITION = ('SWSH3.HidingDarknessEnergy_175', 'ME5.ShadowyDarknessEnergy_83',
                             'RSV10PT5.IgnitionEnergy_86')


class Deck10Attachments(unittest.IsolatedAsyncioTestCase):
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

    # --- Dark Claw -------------------------------------------------------
    async def test_dark_claw_plus_20_for_darkness_to_active(self):
        t = self.table()
        sab = t.put(SABLEYE, P1, 'active')
        t.energy(sab, D)
        t.attach(DARK_CLAW, sab)
        await t.attack(sab, 'Unseen Claw')
        self.assertEqual(400 - t.hp(self.opp), 40)

    async def test_dark_claw_not_on_bench_damage(self):
        t = self.table()
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D, 3)
        t.attach(DARK_CLAW, crobat)
        bench = t.put(self.filler, P2, 'bench')
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        before = t.hp(bench)
        await t.attack(crobat, 'Critical Bite')
        self.assertEqual(before - t.hp(bench), 30)

    # --- Retreat Tools / Energy ------------------------------------------
    async def test_float_stone_and_u_turn_board(self):
        t = self.table()
        sab = t.put(SABLEYE, P1, 'active')
        base = t.retreat(sab)
        self.assertGreater(base, 0)
        t.attach(UTURN, sab)
        self.assertEqual(t.retreat(sab), base - 1)
        t = self.table()
        sab = t.put(SABLEYE, P1, 'active')
        t.attach(FLOAT, sab)
        self.assertEqual(t.retreat(sab), 0)

    async def test_hiding_darkness_energy_free_retreat_darkness_only(self):
        t = self.table()
        sab = t.put(SABLEYE, P1, 'active')
        t.attach(HIDING, sab)
        self.assertEqual(t.retreat(sab), 0)
        t = self.table()
        lele = t.put(LELE, P1, 'active')
        base = t.retreat(lele)
        t.attach(HIDING, lele)
        self.assertEqual(t.retreat(lele), base)

    # --- Shadowy Darkness Energy ----------------------------------------
    async def test_shadowy_darkness_protects_benched_darkness(self):
        for spec, where, protected in ((SABLEYE, 'bench', True), (LELE, 'bench', False)):
            t = self.table()
            t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
            t.put(self.filler, P2, 'active')
            target = t.put(spec, P2, where)
            t.attach(SHADOWY, target)
            crobat = t.put(CROBAT, P1, 'active')
            t.energy(crobat, D, 3)
            t.pokemon = lambda c, p: target if target in c else c[0]
            before = t.hp(target)
            await t.attack(crobat, 'Critical Bite')
            with self.subTest(card=spec):
                self.assertEqual(before - t.hp(target), 0 if protected else 30)

    async def test_shadowy_darkness_not_on_active(self):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        target = t.put(SABLEYE, P2, 'active')
        target.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.attach(SHADOWY, target)
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D)
        before = t.hp(target)
        await t.attack(crobat, 'Venomous Fang')
        self.assertEqual(before - t.hp(target), 50)

    # --- Ignition Energy ----------------------------------------------------
    async def test_ignition_energy_three_on_evolution_one_on_basic(self):
        t = self.table()
        golbat = t.put(GOLBAT, P1, 'active')       # Air Slash costs [C][C]
        t.attach(IGNITION, golbat)
        self.assertIsNotNone(t.attack_offer(golbat, 'Air Slash'))
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'active')
        t.attach(IGNITION, zubat)
        # Supersonic costs [D]: a single Colorless doesn't pay it
        self.assertIsNone(t.attack_offer(zubat, 'Supersonic'))

    async def test_ignition_energy_discarded_end_of_turn(self):
        t = self.table()
        golbat = t.put(GOLBAT, P1, 'active')
        ignition = t.put(IGNITION, P1, 'hand')
        await t.play(ignition, targets=[golbat.entity_id])     # the real attach action
        self.assertIn(ignition, golbat.children)
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        await t._run(lambda: t.session._discard_end_of_turn_attached_energies(P1))
        self.assertIn(ignition, t.zone(P1, 'discard'))

    # --- Stadiums -----------------------------------------------------------
    async def test_perilous_jungle_two_more_except_darkness(self):
        for spec, expected in ((None, 30), (SABLEYE, 10)):
            t = self.table()
            if spec:
                t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
                victim = t.put(spec, P2, 'active')
            else:
                victim = self.opp
            victim.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
            t.stadium(JUNGLE, P1)
            t.put(self.filler, P1, 'active')
            before = t.hp(victim)
            await t.checkup()
            with self.subTest(card=spec):
                self.assertEqual(before - t.hp(victim), expected)

    async def test_perilous_jungle_with_pecharunt(self):
        t = self.table()
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        t.stadium(JUNGLE, P2)
        t.put(PECHARUNT, P1, 'active')
        before = t.hp(self.opp)
        await t.checkup()
        self.assertEqual(before - t.hp(self.opp), 10 + 20 + 50)

    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_artazon_basic_without_rule_box_once(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        artazon = t.stadium(ARTAZON, P2)           # either player's Stadium
        t.deck(P1, [SABLEYE])
        entry = self.stadium_action(t, artazon)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Sableye'])
        self.assertIsNone(self.stadium_action(t, artazon))

    async def test_tropical_beach_draw_to_seven_ends_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        beach = t.stadium(BEACH, P1)
        t.put(self.filler, P1, 'hand')
        entry = self.stadium_action(t, beach)
        self.assertIsNotNone(entry)
        ended = await t.do(entry)
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        self.assertTrue(ended)


if __name__ == "__main__":
    unittest.main()
