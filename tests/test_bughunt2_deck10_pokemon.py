"""Bug hunt round 2, deck 10 (Darkness): Pokémon, checked against their
printed text, including the cases where they should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

D, W = PokemonTypes.DARKNESS, PokemonTypes.WATER
ZUBAT, CROBAT = 'SV065.Zubat_27', 'ME4.Crobat_51'
YVELTAL, MOLTRES = 'SM9.Yveltal_95', 'SWSH7.GalarianMoltres_93'
TYRANITAR, MURKROW, SABLEYE = 'SV09.Tyranitar_95', 'SV10.TeamRocketsMurkrow_127', 'BW5.Sableye_62'
SV_SABLEYE = 'SV2.Sableye_136'        # two attacks: Night Eyes, Unseen Claw
GUZMA = 'SM3.Guzma_115'
HIDING = 'SWSH3.HidingDarknessEnergy_175'
NEST = 'SV1.NestBall_181'
FLOAT = 'XY8.FloatStone_137'


class Deck10Pokemon2(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Zubat (SFA): Lead ------------------------------------------------
    async def test_zubat_lead_finds_a_supporter(self):
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'active')
        t.energy(zubat, D)
        t.deck(P1, [GUZMA, NEST])
        await t.attack(zubat, 'Lead')
        self.assertEqual(self.hand_names(t), ['Guzma'])

    async def test_zubat_lead_takes_no_item(self):
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'active')
        t.energy(zubat, D)
        t.deck(P1, [NEST])
        await t.attack(zubat, 'Lead')
        self.assertEqual(self.hand_names(t), [])

    # --- Crobat (CRI): Nighttime Maneuvers / Poison Sound Wave -------------
    async def test_nighttime_maneuvers_puts_chosen_card_on_top(self):
        t = self.table()
        crobat = t.put(CROBAT, P1, 'active')
        target = t.deck(P1, [GUZMA], top=False)[0]          # bottom of the deck
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is target] or cards[:count]
        await t.use(crobat, 'Nighttime Maneuvers')
        deck = t.zone(P1, 'deck')
        self.assertEqual(len(deck), 31)
        self.assertIs(deck[-1], target)                     # top = last child
        self.assertIsNone(t.ability_offer(crobat, 'Nighttime Maneuvers'))

    async def test_nighttime_maneuvers_not_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        crobat = t.put(CROBAT, P1, 'bench')
        self.assertIsNone(t.ability_offer(crobat, 'Nighttime Maneuvers'))

    async def test_poison_sound_wave(self):
        t = self.table()
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D)
        await t.attack(crobat, 'Poison Sound Wave')
        self.assertEqual(400 - t.hp(self.opp), 80)
        self.assertTrue({POISONED, CONFUSED} <= t.conditions(self.opp))

    # --- Yveltal (TEU): Derail / Clutch ------------------------------------
    async def test_derail_discards_special_energy_not_basic(self):
        t = self.table()
        yv = t.put(YVELTAL, P1, 'active')
        t.energy(yv, D)
        special = t.attach(HIDING, self.opp)
        basic = t.energy(self.opp, W)
        await t.attack(yv, 'Derail')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertNotIn(special, self.opp.children)
        self.assertIn(special, t.zone(P2, 'discard'))
        self.assertIn(basic, self.opp.children)

    async def test_derail_leaves_basic_energy_alone(self):
        t = self.table()
        yv = t.put(YVELTAL, P1, 'active')
        t.energy(yv, D)
        basic = t.energy(self.opp, W)
        await t.attack(yv, 'Derail')
        self.assertIn(basic, self.opp.children)

    async def test_clutch_blocks_retreat_for_one_turn(self):
        t = self.table()
        yv = t.put(YVELTAL, P1, 'active')
        t.energy(yv, D, 2)
        t.energy(self.opp, W, 5)
        t.put(self.filler, P2, 'bench')
        await t.attack(yv, 'Clutch')
        self.assertEqual(400 - t.hp(self.opp), 60)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', pid=P2))

    # --- Galarian Moltres (EVS): Malevolent Charge / Fiery Wrath ----------
    async def test_malevolent_charge_attaches_two_darkness_from_hand(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        moltres = t.put(MOLTRES, P1, 'hand')
        e1 = t.put(t.basic_energy(D), P1, 'hand')
        e2 = t.put(t.basic_energy(D), P1, 'hand')
        water = t.put(t.basic_energy(W), P1, 'hand')
        await t.play(moltres)
        self.assertIn(moltres, t.zone(P1, 'bench'))
        self.assertIn(e1, moltres.children)
        self.assertIn(e2, moltres.children)
        self.assertNotIn(water, moltres.children)

    async def test_malevolent_charge_is_optional(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        moltres = t.put(MOLTRES, P1, 'hand')
        e1 = t.put(t.basic_energy(D), P1, 'hand')
        t.yes = False
        await t.play(moltres)
        self.assertIn(moltres, t.zone(P1, 'bench'))
        self.assertNotIn(e1, moltres.children)

    async def test_fiery_wrath_scales_with_opponent_prizes_taken(self):
        for p2_prizes, dmg in ((6, 20), (4, 120)):
            t = self.table()
            moltres = t.put(MOLTRES, P1, 'active')
            t.energy(moltres, D, 3)
            t.set_prizes(P2, p2_prizes)
            await t.attack(moltres, 'Fiery Wrath')
            with self.subTest(p2_prizes=p2_prizes):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    async def test_fiery_wrath_ignores_my_own_prizes_taken(self):
        t = self.table()
        moltres = t.put(MOLTRES, P1, 'active')
        t.energy(moltres, D, 3)
        t.set_prizes(P1, 2)                    # I've taken 4, opponent none
        await t.attack(moltres, 'Fiery Wrath')
        self.assertEqual(400 - t.hp(self.opp), 20)

    # --- Tyranitar (JTG): Daunting Gaze / Cracking Stomp -------------------
    async def test_daunting_gaze_active_blocks_opponent_items(self):
        t = self.table()
        t.put(TYRANITAR, P1, 'active')
        opp_item = t.put(NEST, P2, 'hand')
        my_item = t.put(NEST, P1, 'hand')
        self.assertTrue(t.can(my_item, 'UseTrainerCard'))        # mine still work
        t.next_turn()
        self.assertFalse(t.can(opp_item, 'UseTrainerCard', pid=P2))
        opp_sup = t.put(GUZMA, P2, 'hand')
        t.put(self.filler, P1, 'bench')
        self.assertTrue(t.can(opp_sup, 'UseTrainerCard', pid=P2))  # Supporters fine

    async def test_daunting_gaze_not_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(TYRANITAR, P1, 'bench')
        opp_item = t.put(NEST, P2, 'hand')
        t.next_turn()
        self.assertTrue(t.can(opp_item, 'UseTrainerCard', pid=P2))

    async def test_cracking_stomp_mills_two_from_opponent(self):
        t = self.table()
        ttar = t.put(TYRANITAR, P1, 'active')
        t.energy(ttar, D, 2)
        await t.attack(ttar, 'Cracking Stomp')
        self.assertEqual(400 - t.hp(self.opp), 150)
        self.assertEqual(len(t.zone(P2, 'discard')), 2)
        self.assertEqual(len(t.zone(P2, 'deck')), 28)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Team Rocket's Murkrow (DRI): Deceit / Torment ----------------------
    async def test_deceit_finds_a_supporter_only(self):
        t = self.table()
        murkrow = t.put(MURKROW, P1, 'active')
        t.energy(murkrow, D)
        t.deck(P1, [GUZMA, NEST])
        await t.attack(murkrow, 'Deceit')
        self.assertEqual(self.hand_names(t), ['Guzma'])

    async def test_torment_locks_chosen_attack_only(self):
        t = self.table(SV_SABLEYE)
        t.energy(self.opp, D, 2)
        murkrow = t.put(MURKROW, P1, 'active')
        t.energy(murkrow, D, 2)

        async def choose_attack(ctx, options, prompt='', *a, **k):
            return next(o for o in options if o[1].title == 'Unseen Claw')
        with patch.object(EffectContext, 'choose_attack_to_copy', choose_attack, create=True):
            await t.attack(murkrow, 'Torment')
        self.assertEqual(400 - t.hp(self.opp), 30)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, 'Unseen Claw', pid=P2))
        self.assertIsNotNone(t.attack_offer(self.opp, 'Night Eyes', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, 'Unseen Claw', pid=P2))

    # --- Sableye (DEX): Confuse Ray / Junk Hunt -----------------------------
    async def test_confuse_ray_heads_and_tails(self):
        for heads in (True, False):
            t = self.table()
            sab = t.put(SABLEYE, P1, 'active')
            t.energy(sab, D)
            t.heads = heads
            await t.attack(sab, 'Confuse Ray')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 10)
                self.assertEqual(CONFUSED in t.conditions(self.opp), heads)

    async def test_junk_hunt_two_items_not_other_cards(self):
        t = self.table()
        sab = t.put(SABLEYE, P1, 'active')
        t.energy(sab, D)
        i1 = t.put(NEST, P1, 'discard')
        i2 = t.put('SWSH8.QuickBall_237', P1, 'discard')
        sup = t.put(GUZMA, P1, 'discard')
        i3 = t.put(NEST, P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'], seen['count'] = list(cards), count
            return [c for c in cards if c in (i1, i2)][:count]
        t.picks = picks
        await t.attack(sab, 'Junk Hunt')
        self.assertEqual(seen['count'], 2)
        self.assertNotIn(sup, seen['cards'])
        hand = t.zone(P1, 'hand')
        self.assertIn(i1, hand)
        self.assertIn(i2, hand)
        self.assertNotIn(sup, hand)
        self.assertIn(i3, t.zone(P1, 'discard'))


if __name__ == '__main__':
    unittest.main()
