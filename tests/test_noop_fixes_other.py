"""Offered-but-does-nothing fixes outside standard_era (noop detector, Oct 12).

Cedric Juniper, Single/Rapid Strike Style Mustard, Quad Stone, Elesa's
Sparkle, Café Master, Starmie Space Beacon (ruling: may discard with nothing to retrieve), Clefable Lunar Blessing,
Appletun Delicious Aroma -- each checked against its printed text, including
the boards where it must NOT be offered."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests.bughunt_table import Table
from spirit.game.attributes import PokemonTypes
from spirit.tools.effect_smoke import P1, P2

MON = 'SM1.Chinchou_49'
STAGE1 = 'SM2.Machoke_64'
CEDRIC = 'BW11.CedricJuniper_110'
SS_MUSTARD = ['SWSH5.SingleStrikeStyleMustard_134', 'SWSH5.SingleStrikeStyleMustard_163',
              'SWSH5.SingleStrikeStyleMustard_177', 'SWSH9.SingleStrikeStyleMustard_214']
RS_MUSTARD = ['SWSH5.RapidStrikeStyleMustard_132', 'SWSH5.RapidStrikeStyleMustard_162',
              'SWSH5.RapidStrikeStyleMustard_176', 'SWSH9.RapidStrikeStyleMustard_213']
HOUNDOUR = 'SWSH5.Houndour_95'          # Basic, Single Strike
CARNIVINE = 'SWSH5.Carnivine_9'         # Basic, Rapid Strike
QUAD = 'SWSH12.QuadStone_163'
ELESA = ['SWSH8.ElesasSparkle_233', 'SWSH8.ElesasSparkle_260',
         'SWSH8.ElesasSparkle_275', 'CZ.ElesasSparkle_147']
CLAMPERL = 'SWSH8.Clamperl_65'          # Basic, Fusion Strike
CAFE = ['SWSH9.CafMaster_133', 'SWSH9.CafMaster_211']
STARMIE = 'XY12.Starmie_31'
CLEFABLE = 'SWSH4.Clefable_64'
APPLETUN = 'SWSH2.Appletun_23'


class NoopFixesOther(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig

    def board(self, my_bench=0, opp_bench=0):
        t = Table(self)
        t.put(MON, P1, 'active')
        t.put(MON, P2, 'active')
        for _ in range(my_bench):
            t.put(MON, P1, 'bench')
        for _ in range(opp_bench):
            t.put(MON, P2, 'bench')
        return t

    # --- Cedric Juniper BW11 110 ----------------------------------------------
    def test_cedric_needs_pokemon_in_own_hand(self):
        t = self.board()
        t.put(MON, P2, 'hand')                      # opponent's Pokémon don't count
        c = t.put(CEDRIC, P1, 'hand')
        self.assertFalse(t.offers(c))
        t.put(MON, P1, 'hand')
        self.assertTrue(t.offers(c))

    async def _cedric(self, actual_band):
        t = self.board()
        mine = t.put(MON, P1, 'hand')
        c = t.put(CEDRIC, P1, 'hand')
        asked = []

        async def choose(ctx, prompt, buttons, player_id=None, *a, **k):
            asked.append(player_id)
            return 0
        with patch('spirit.game.session.effects.EffectContext.choose', choose), \
                patch('spirit.game.card_effects.bw_era.random.randrange',
                      lambda n: actual_band):
            await t.play(c)
        self.assertEqual(asked, [P2])               # the opponent guesses
        self.assertIn(mine, t.zone(P1, 'hand'))     # returned to (never left) hand
        return t

    async def test_cedric_opponent_wrong_you_draw_3(self):
        t = await self._cedric(1)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    async def test_cedric_opponent_right_they_draw_3(self):
        t = await self._cedric(0)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P2, 'hand')), 3)

    # --- Single Strike Style Mustard ------------------------------------------
    async def test_ss_mustard_draws_5_even_if_search_finds_nothing(self):
        for path in SS_MUSTARD:
            with self.subTest(path):
                t = self.board()
                c = t.put(path, P1, 'hand')
                await t.play(c)
                self.assertEqual(len(t.zone(P1, 'hand')), 5)
                self.assertEqual(len(t.zone(P1, 'bench')), 0)

    async def test_ss_mustard_benches_and_draws(self):
        t = self.board()
        t.deck(P1, [HOUNDOUR])
        c = t.put(SS_MUSTARD[0], P1, 'hand')
        await t.play(c)
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Houndour'])
        self.assertEqual(len(t.zone(P1, 'hand')), 5)

    def test_ss_mustard_not_offered_full_bench_or_not_last(self):
        for path in SS_MUSTARD:
            with self.subTest(path):
                t = self.board(my_bench=5)
                c = t.put(path, P1, 'hand')
                self.assertFalse(t.offers(c))
                t = self.board()
                c = t.put(path, P1, 'hand')
                self.assertTrue(t.offers(c))
                t.put(MON, P1, 'hand')
                self.assertFalse(t.offers(c))

    # --- Rapid Strike Style Mustard -------------------------------------------
    async def test_rs_mustard_needs_rapid_strike_in_discard_and_bench_space(self):
        for path in RS_MUSTARD:
            with self.subTest(path):
                t = self.board()
                c = t.put(path, P1, 'hand')
                t.put(MON, P1, 'discard')
                self.assertFalse(t.offers(c))
                t.put(CARNIVINE, P1, 'discard')
                self.assertTrue(t.offers(c))
                t2 = self.board(my_bench=5)
                c2 = t2.put(path, P1, 'hand')
                t2.put(CARNIVINE, P1, 'discard')
                self.assertFalse(t2.offers(c2))
                await t.play(c)
                self.assertEqual(t.names(t.zone(P1, 'bench')), ['Carnivine'])
                self.assertEqual(len(t.zone(P1, 'hand')), 5)

    # --- Quad Stone SWSH12 163 -------------------------------------------------
    def test_quad_stone_not_offered_when_nothing_to_heal(self):
        t = self.board()
        q = t.put(QUAD, P1, 'hand')
        self.assertFalse(t.offers(q))
        t.put(MON, P1, 'bench', hp=10)              # damaged Bench, single stone
        self.assertFalse(t.offers(q))

    async def test_quad_stone_damaged_active_heals_10(self):
        t = Table(self)
        a = t.put(MON, P1, 'active', hp=20)
        t.put(MON, P2, 'active')
        q = t.put(QUAD, P1, 'hand')
        self.assertTrue(t.offers(q))
        before = t.hp(a)
        await t.play(q)
        self.assertEqual(t.hp(a), before + 10)

    async def test_quad_stone_four_heal_bench_when_active_undamaged(self):
        t = self.board()
        b = t.put(MON, P1, 'bench', hp=10)
        q = t.put(QUAD, P1, 'hand')
        for _ in range(3):
            t.put(QUAD, P1, 'hand')
        self.assertTrue(t.offers(q))
        await t.play(q)
        self.assertEqual(t.damage(b), 0)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Elesa's Sparkle -------------------------------------------------------
    def test_elesas_sparkle_needs_fusion_strike_in_play(self):
        for path in ELESA:
            with self.subTest(path):
                t = self.board()
                c = t.put(path, P1, 'hand')
                self.assertFalse(t.offers(c))
                t.put(CLAMPERL, P1, 'bench')
                self.assertTrue(t.offers(c))

    # --- Café Master -----------------------------------------------------------
    def test_cafe_master_needs_benched_pokemon(self):
        for path in CAFE:
            with self.subTest(path):
                t = self.board()
                c = t.put(path, P1, 'hand')
                self.assertFalse(t.offers(c))
                t.put(MON, P1, 'bench')
                self.assertTrue(t.offers(c))

    # --- Starmie XY12 31: Space Beacon ----------------------------------------
    async def test_space_beacon_may_discard_with_nothing_to_retrieve(self):
        # Owner ruling (Rulings Compendium): discard a card, period; then do
        # as much of the rest as you can.
        t = Table(self)
        st = t.put(STARMIE, P1, 'active')
        t.put(MON, P2, 'active')
        card = t.put(self.item, P1, 'hand')
        t.put(MON, P1, 'discard')
        await t.use(st, 'Space Beacon')
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_space_beacon_pays_and_retrieves(self):
        t = Table(self)
        st = t.put(STARMIE, P1, 'active')
        t.put(MON, P2, 'active')
        t.put(self.item, P1, 'hand')
        e1 = t.put(t.basic_energy(PokemonTypes.WATER), P1, 'discard')
        e2 = t.put(t.basic_energy(PokemonTypes.FIRE), P1, 'discard')
        await t.use(st, 'Space Beacon')
        self.assertEqual(set(t.zone(P1, 'hand')), {e1, e2})

    # --- Clefable SWSH4 64: Lunar Blessing ------------------------------------
    def test_lunar_blessing_needs_damage_or_condition(self):
        t = Table(self)
        m = t.put(CLEFABLE, P1, 'active')
        t.energy(m, PokemonTypes.PSYCHIC)
        t.put(MON, P2, 'active')
        self.assertIsNone(t.ability_offer(m, 'Lunar Blessing'))
        m.set_attribute(fixtures.AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        self.assertIsNotNone(t.ability_offer(m, 'Lunar Blessing'))
        m.set_attribute(fixtures.AttrID.SPECIAL_CONDITIONS, [])
        m.set_attribute(fixtures.AttrID.HP, t.hp(m) - 30)
        self.assertIsNotNone(t.ability_offer(m, 'Lunar Blessing'))

    # --- Appletun SWSH2 23: Delicious Aroma -----------------------------------
    def test_delicious_aroma_needs_opponent_benched_basic(self):
        t = Table(self)
        m = t.put(APPLETUN, P1, 'active')
        t.put(MON, P2, 'active')                    # Basic Active doesn't count
        t.put(STAGE1, P2, 'bench')
        self.assertIsNone(t.ability_offer(m, 'Delicious Aroma'))
        t.put(MON, P2, 'bench')
        self.assertIsNotNone(t.ability_offer(m, 'Delicious Aroma'))


if __name__ == '__main__':
    unittest.main()
