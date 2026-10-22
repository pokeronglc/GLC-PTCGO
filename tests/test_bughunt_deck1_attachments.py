"""Bug hunt, deck 1 (Colorless): Tools, Stadiums and Special Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, D = PokemonTypes.WATER, PokemonTypes.DARKNESS
PIKIPEK, TRUMBEAK = 'ME5.Pikipek_66', 'ME5.Trumbeak_67'
CINCCINO, WOOLOO, DUBWOOL = 'SWSH1.Cinccino_147', 'SV09.HopsWooloo_135', 'SV09.HopsDubwool_136'
HOP_SNORLAX, SABLEYE, CROBAT = 'SV09.HopsSnorlax_117', 'SV2.Sableye_136', 'SWSH12.Crobat_105'
AIR_BALLOON, MUSCLE_BAND, CHOICE_BAND = ('SWSH1.AirBalloon_156', 'XY1.MuscleBand_121',
                                         'SV09.HopsChoiceBand_148')
LOST_CITY, PARALLEL = 'SWSH11.LostCity_161', 'XY8.ParallelCity_145'
RECYCLE, CAPTURE, GIFT = 'SM11.RecycleEnergy_212', 'SWSH2.CaptureEnergy_171', 'SWSH11.GiftEnergy_171'
DRAW, JET, PCE = 'SM12.DrawEnergy_209', 'SV2.JetEnergy_190', 'SWSH3.PowerfulColorlessEnergy_176'
DTE, COUNTER, TAE = 'SWSH9.DoubleTurboEnergy_151', 'SM4.CounterEnergy_100', 'SM10.TripleAccelerationEnergy_190'


class Deck1Attachments(unittest.IsolatedAsyncioTestCase):
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

    def swap_opp(self, t, spec, hp=None):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = t.put(spec, P2, 'active', hp=hp)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return self.opp

    # --- Air Balloon ---------------------------------------------------------
    async def test_air_balloon_two_less(self):
        t = self.table()
        s = t.put(HOP_SNORLAX, P1, 'active')
        self.assertEqual(t.retreat(s), 4)
        t.attach(AIR_BALLOON, s)
        self.assertEqual(t.retreat(s), 2)
        p = t.put(PIKIPEK, P1, 'bench')
        t.attach(AIR_BALLOON, p)
        self.assertEqual(t.retreat(p), 0)          # never below zero

    # --- Muscle Band -----------------------------------------------------------
    async def test_muscle_band_plus_20_active_only(self):
        t = self.table()
        p = t.put(PIKIPEK, P1, 'active')
        t.energy(p, W)
        t.attach(MUSCLE_BAND, p)
        t.heads = True
        await t.attack(p, 'Double Stab')
        self.assertEqual(400 - t.hp(self.opp), 40)
        t = self.table()
        c = t.put(CROBAT, P1, 'active')
        t.energy(c, D, 3)
        t.attach(MUSCLE_BAND, c)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.pokemon = lambda cands, p: bench if bench in cands else cands[0]
        before = t.hp(bench)
        await t.attack(c, 'Critical Bite')
        self.assertEqual(before - t.hp(bench), 30)

    # --- Hop's Choice Band ---------------------------------------------------
    async def test_hops_choice_band_cost_and_damage_hops_only(self):
        t = self.table()
        w = t.put(WOOLOO, P1, 'active')
        t.energy(w, W, 2)
        self.assertIsNone(t.attack_offer(w, 'Smash Kick'))
        t.attach(CHOICE_BAND, w)
        self.assertIsNotNone(t.attack_offer(w, 'Smash Kick'))
        await t.attack(w, 'Smash Kick')
        self.assertEqual(400 - t.hp(self.opp), 80)

    async def test_hops_choice_band_does_nothing_for_others(self):
        t = self.table()
        p = t.put(PIKIPEK, P1, 'active')
        t.attach(CHOICE_BAND, p)
        self.assertIsNone(t.attack_offer(p, 'Double Stab'))
        t.energy(p, W)
        t.heads = True
        await t.attack(p, 'Double Stab')
        self.assertEqual(400 - t.hp(self.opp), 20)

    # --- Lost City -------------------------------------------------------------
    async def test_lost_city_ko_goes_to_lost_zone_attachments_discarded(self):
        for stadium in (True, False):
            t = self.table()
            victim = self.swap_opp(t, self.filler, hp=10)
            energy = t.energy(victim, W)
            t.put(self.filler, P2, 'bench')
            if stadium:
                t.stadium(LOST_CITY, P2)
            p = t.put(PIKIPEK, P1, 'active')
            t.energy(p, W)
            t.heads = True
            await t.attack(p, 'Double Stab')
            with self.subTest(lost_city=stadium):
                self.assertEqual(victim in t.zone(P2, 'lostZone'), stadium)
                self.assertEqual(victim in t.zone(P2, 'discard'), not stadium)
                self.assertIn(energy, t.zone(P2, 'discard'))

    async def test_lost_city_applies_to_own_pokemon_too(self):
        t = self.table()
        t.stadium(LOST_CITY, P2)
        mine = t.put(self.filler, P1, 'active', hp=10)
        mine.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        t.put(self.filler, P1, 'bench')
        await t.checkup()
        self.assertIn(mine, t.zone(P1, 'lostZone'))

    # --- Parallel City ---------------------------------------------------------
    async def _play_parallel(self, t, orientation):
        card = t.put(PARALLEL, P1, 'hand')
        entry = next(iter(t.offers(card, None, P1)))
        await t.do(entry, amounts=[orientation])
        return card

    async def test_parallel_city_normal_caps_opponent_bench(self):
        t = self.table()
        for _ in range(5):
            t.put(self.filler, P2, 'bench')
            t.put(self.filler, P1, 'bench')
        await self._play_parallel(t, 0)
        self.assertEqual(len(t.zone(P2, 'bench')), 3)
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    async def test_parallel_city_inverted_caps_own_bench(self):
        t = self.table()
        for _ in range(5):
            t.put(self.filler, P2, 'bench')
            t.put(self.filler, P1, 'bench')
        await self._play_parallel(t, 1)
        self.assertEqual(len(t.zone(P1, 'bench')), 3)
        self.assertEqual(len(t.zone(P2, 'bench')), 5)

    async def test_parallel_city_minus_20_water_fire_grass_only(self):
        for orientation, kind, expected in ((0, W, 30), (1, W, 50), (0, PokemonTypes.COLORLESS, 50)):
            t = self.table()
            w = t.put(WOOLOO, P1, 'active')
            w.set_attribute(AttrID.POKEMON_TYPES, [kind.value])
            t.energy(w, W, 3)
            await self._play_parallel(t, orientation)
            await t.attack(w, 'Smash Kick')
            with self.subTest(orientation=orientation, kind=kind):
                self.assertEqual(400 - t.hp(self.opp), expected)

    # --- Recycle Energy -----------------------------------------------------
    async def test_recycle_energy_returns_to_hand_when_ko(self):
        t = self.table()
        victim = self.swap_opp(t, self.filler, hp=10)
        rec = t.attach(RECYCLE, victim)
        t.put(self.filler, P2, 'bench')
        p = t.put(PIKIPEK, P1, 'active')
        t.energy(p, W)
        t.heads = True
        await t.attack(p, 'Double Stab')
        self.assertIn(victim, t.zone(P2, 'discard'))
        self.assertIn(rec, t.zone(P2, 'hand'))

    async def test_recycle_energy_discarded_from_hand_stays(self):
        t = self.table()
        cin = t.put(CINCCINO, P1, 'active')
        rec = t.put(RECYCLE, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [rec]
        await t.use(cin, 'Make Do')
        self.assertIn(rec, t.zone(P1, 'discard'))

    async def test_recycle_energy_returns_when_discarded_by_attack(self):
        t = self.table()
        golbat = t.put('SWSH5.Golbat_90', P1, 'active')      # Air Slash: discard an Energy
        recs = [t.attach(RECYCLE, golbat), t.attach(RECYCLE, golbat)]   # whichever goes, it's Recycle
        await t.attack(golbat, 'Air Slash')
        gone = [r for r in recs if r not in golbat.children]
        self.assertEqual(len(gone), 1)
        self.assertIn(gone[0], t.zone(P1, 'hand'))
        self.assertNotIn(gone[0], t.zone(P1, 'discard'))

    async def test_recycle_energy_to_hand_under_lost_city(self):
        t = self.table()
        t.stadium(LOST_CITY, P1)
        victim = self.swap_opp(t, self.filler, hp=10)
        rec = t.attach(RECYCLE, victim)
        t.put(self.filler, P2, 'bench')
        p = t.put(PIKIPEK, P1, 'active')
        t.energy(p, W)
        t.heads = True
        await t.attack(p, 'Double Stab')
        self.assertIn(victim, t.zone(P2, 'lostZone'))
        self.assertIn(rec, t.zone(P2, 'hand'))

    async def test_parallel_city_blocks_fourth_bench(self):
        t = self.table()
        for _ in range(3):
            t.put(self.filler, P2, 'bench')
            t.put(self.filler, P1, 'bench')
        await self._play_parallel(t, 0)
        mine = t.put(PIKIPEK, P1, 'hand')
        self.assertTrue(t.can(mine, 'DefaultPokemonPlayAbility'))
        theirs = t.put(PIKIPEK, P2, 'hand')
        t.next_turn()
        self.assertFalse(t.can(theirs, 'DefaultPokemonPlayAbility', P2))

    # --- Capture Energy -----------------------------------------------------
    async def test_capture_energy_benches_a_basic(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        t.deck(P1, [TRUMBEAK, PIKIPEK])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (
            seen.setdefault('n', t.names(cards)), cards[:count])[1]
        cap = t.put(CAPTURE, P1, 'hand')
        await t.play(cap, targets=[me.entity_id])
        self.assertIn(cap, me.children)
        self.assertNotIn('Trumbeak', seen['n'])
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Pikipek'])

    async def test_capture_energy_provides_one_colorless(self):
        t = self.table()
        w = t.put(PIKIPEK, P1, 'active')
        t.attach(CAPTURE, w)
        self.assertIsNotNone(t.attack_offer(w, 'Double Stab'))

    # --- Gift Energy ---------------------------------------------------------
    async def test_gift_energy_draw_to_seven_on_attack_ko(self):
        t = self.table()
        victim = self.swap_opp(t, self.filler, hp=10)
        t.attach(GIFT, victim)
        t.put(self.filler, P2, 'bench')
        for _ in range(2):
            t.put(self.filler, P2, 'hand')
        p = t.put(PIKIPEK, P1, 'active')
        t.energy(p, W)
        t.heads = True
        await t.attack(p, 'Double Stab')
        self.assertIn(victim, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P2, 'hand')), 7)

    async def test_gift_energy_not_on_poison_ko(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        victim = self.swap_opp(t, self.filler, hp=10)
        t.attach(GIFT, victim)
        victim.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        t.put(self.filler, P2, 'bench')
        for _ in range(2):
            t.put(self.filler, P2, 'hand')
        await t.checkup()
        self.assertIn(victim, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P2, 'hand')), 2)

    # --- Draw Energy ---------------------------------------------------------
    async def test_draw_energy_draws_on_attach_from_hand(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        de = t.put(DRAW, P1, 'hand')
        await t.play(de, targets=[me.entity_id])
        self.assertIn(de, me.children)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    # --- Jet Energy ------------------------------------------------------------
    async def test_jet_energy_switches_when_attached_to_bench(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        bench = t.put(PIKIPEK, P1, 'bench')
        jet = t.put(JET, P1, 'hand')
        await t.play(jet, targets=[bench.entity_id])
        self.assertIs(t.active(P1), bench)
        self.assertIn(jet, bench.children)

    async def test_jet_energy_no_switch_on_active(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        t.put(PIKIPEK, P1, 'bench')
        jet = t.put(JET, P1, 'hand')
        await t.play(jet, targets=[me.entity_id])
        self.assertIs(t.active(P1), me)

    # --- Powerful Colorless Energy -------------------------------------------
    async def test_powerful_colorless_plus_20_colorless_only(self):
        t = self.table()
        p = t.put(PIKIPEK, P1, 'active')
        t.attach(PCE, p)
        t.heads = True
        await t.attack(p, 'Double Stab')
        self.assertEqual(400 - t.hp(self.opp), 40)
        t = self.table()
        s = t.put(SABLEYE, P1, 'active')
        t.energy(s, D)
        t.attach(PCE, s)
        await t.attack(s, 'Unseen Claw')
        self.assertEqual(400 - t.hp(self.opp), 20)

    # --- Double Turbo Energy --------------------------------------------------
    async def test_double_turbo_two_energy_minus_20(self):
        t = self.table()
        w = t.put(WOOLOO, P1, 'active')
        t.energy(w, W)
        self.assertIsNone(t.attack_offer(w, 'Smash Kick'))
        t.attach(DTE, w)
        self.assertIsNotNone(t.attack_offer(w, 'Smash Kick'))
        await t.attack(w, 'Smash Kick')
        self.assertEqual(400 - t.hp(self.opp), 30)

    # --- Counter Energy -------------------------------------------------------
    async def test_counter_energy_every_type_two_when_behind(self):
        for mine, theirs, ok in ((6, 4, True), (4, 4, False), (3, 5, False)):
            t = self.table()
            t.set_prizes(P1, mine)
            t.set_prizes(P2, theirs)
            s = t.put(SABLEYE, P1, 'active')
            t.attach(COUNTER, s)
            w = t.put(WOOLOO, P1, 'bench')
            t.attach(COUNTER, w)
            t.energy(w, W)
            with self.subTest(mine=mine, theirs=theirs):
                self.assertEqual(t.attack_offer(s, 'Unseen Claw') is not None, ok)   # [D]
                t.board.find_player_area(P1, 'activePokemonArea').remove_child(s)
                t.board.find_player_area(P1, 'bench').remove_child(w)
                t.board.add_card_to_area(w, t.board.find_player_area(P1, 'activePokemonArea'))
                self.assertEqual(t.attack_offer(w, 'Smash Kick') is not None, ok)    # [C][C][C]

    # --- Triple Acceleration Energy ------------------------------------------
    async def test_triple_acceleration_evolution_only(self):
        t = self.table()
        basic = t.put(WOOLOO, P1, 'active')
        evo = t.put(DUBWOOL, P1, 'bench')
        tae = t.put(TAE, P1, 'hand')
        targets = t.targets(tae, None)
        self.assertIn(evo.entity_id, targets)
        self.assertNotIn(basic.entity_id, targets)

    async def test_triple_acceleration_ccc_and_discarded_end_of_turn(self):
        t = self.table()
        dub = t.put(DUBWOOL, P1, 'active')
        tae = t.put(TAE, P1, 'hand')
        await t.play(tae, targets=[dub.entity_id])
        self.assertIsNotNone(t.attack_offer(dub, 'Headbutt'))
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        await t._run(lambda: t.session._discard_end_of_turn_attached_energies(P1))
        self.assertIn(tae, t.zone(P1, 'discard'))


if __name__ == "__main__":
    unittest.main()
