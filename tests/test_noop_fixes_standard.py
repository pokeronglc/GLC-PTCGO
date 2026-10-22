"""Offered-but-does-nothing fixes in the shared Standard-era interpreter
(standard_era.py): Trainers and Abilities that lit up although no part of
their printed effect could happen, or stayed dark although an independent
part of the effect could.

Boards follow /home/claude/bughunt/noop/repro_confirmed.py and
repro_top_findings.py.  House rules: a card is playable when any part of its
effect can be done (unless the printed text forbids it); a pick from a public
zone must take at least one card.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

WATER, FIRE, PSYCHIC = PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.PSYCHIC

MON = 'SM1.Chinchou_49'           # Basic Lightning
STAGE1 = 'SM2.Machoke_64'
FIRE_MON = 'HF.Charmander_7'
PSYDUCK = 'HF.Psyduck_11'
ULTRA_BEAST = 'SM6.Buzzwole_77'


class NoopFixesStandard(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, my_bench=0, opp_bench=0, opp_hand=0):
        t = Table(self)
        t.put(MON, P1, 'active')
        t.put(MON, P2, 'active')
        for _ in range(my_bench):
            t.put(MON, P1, 'bench')
        for _ in range(opp_bench):
            t.put(MON, P2, 'bench')
        for _ in range(opp_hand):
            t.put(self.item, P2, 'hand')
        return t

    def offered(self, t, path):
        card = t.put(path, P1, 'hand')
        return t.can(card, 'UseTrainerCard')

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, {'hand': 'hand', 'deck': 'deck'}[zone])
        for c in list(area.children):
            area.remove_child(c)

    # --- 1. Talonflame ME3 14: Sky Hunt --------------------------------------
    def _talonflame(self, opp_hand=3):
        t = self.table(opp_hand=opp_hand)
        bird = t.put('ME3.Talonflame_14', P1, 'bench')
        return t, bird

    async def test_sky_hunt_heads_discards_random_opponent_card(self):
        t, bird = self._talonflame()
        t.heads = True
        await t.use(bird, 'Sky Hunt')
        self.assertEqual(len(t.zone(P2, 'hand')), 2)
        self.assertEqual(len(t.zone(P2, 'discard')), 1)

    async def test_sky_hunt_tails_discards_nothing(self):
        t, bird = self._talonflame()
        t.heads = False
        await t.use(bird, 'Sky Hunt')
        self.assertEqual(len(t.zone(P2, 'hand')), 3)
        self.assertEqual(len(t.zone(P2, 'discard')), 0)

    def test_sky_hunt_not_offered_vs_empty_hand(self):
        t, bird = self._talonflame(opp_hand=0)
        self.assertIsNone(t.ability_offer(bird, 'Sky Hunt'))

    # --- 2. Independent first clause -----------------------------------------
    def test_giovannis_charisma_offered_without_energy_in_hand(self):
        for path in ('SV035.GiovannisCharisma_161', 'SV035.GiovannisCharisma_197',
                     'SV035.GiovannisCharisma_204'):
            t = self.table()
            t.energy(t.active(P2), WATER)
            self.assertTrue(self.offered(t, path), path)

    async def test_giovannis_charisma_resolves_first_sentence_only(self):
        t = self.table()
        t.energy(t.active(P2), WATER)
        card = t.put('SV035.GiovannisCharisma_161', P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)
        self.assertEqual(t.attached(t.active(P2)), [])

    def test_giovannis_charisma_blocked_without_opponent_energy(self):
        t = self.table()
        t.put(t.basic_energy(WATER), P1, 'hand')
        self.assertFalse(self.offered(t, 'SV035.GiovannisCharisma_161'))

    def test_roark_offered_without_basic_energy_in_discard(self):
        for path in ('SV4.Roark_173', 'SV4.Roark_242'):
            t = self.table()
            self.assertTrue(self.offered(t, path), path)

    async def test_roark_draws_two_without_discard_energy(self):
        t = self.table()
        card = t.put('SV4.Roark_173', P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    def test_roark_blocked_with_empty_deck_and_no_energy(self):
        t = self.table()
        self.clear(t, P1, 'deck')
        self.assertFalse(self.offered(t, 'SV4.Roark_173'))

    def test_gust_supporters_stay_blocked_without_opponent_bench(self):
        for path in ('ME1.BosssOrders_114', 'HF.Guzma_184'):
            t = self.table(my_bench=2)
            self.assertFalse(self.offered(t, path), path)

    # --- 3. Gengar SV045 57: Night Gate --------------------------------------
    def test_night_gate_needs_a_benched_pokemon(self):
        t = Table(self)
        gengar = t.put('SV045.Gengar_57', P1, 'active')
        t.put(MON, P2, 'active')
        self.assertIsNone(t.ability_offer(gengar, 'Night Gate'))
        t.put(MON, P1, 'bench')
        self.assertIsNotNone(t.ability_offer(gengar, 'Night Gate'))

    # --- 4. Bench-only searches with a full Bench ----------------------------
    BENCH_ONLY = ('XY3.FossilResearcher_92', 'XY3.FossilResearcher_110',
                  'XY3.JawFossil_94', 'XY3.SailFossil_98',
                  'XY11.ArmorFossilShieldon_98', 'XY11.ClawFossilAnorith_100',
                  'XY10.HelixFossilOmanyte_102', 'XY10.DomeFossilKabuto_96',
                  'ME2.GrimsleysMove_90', 'ME2.GrimsleysMove_120',
                  'XY8.Brigette_134', 'XY8.Brigette_161',
                  'SM12.ProfessorOaksSetup_201', 'SM12.ProfessorOaksSetup_233')

    def test_bench_only_searches_blocked_with_full_bench(self):
        for path in self.BENCH_ONLY:
            t = self.table(my_bench=5)
            self.assertFalse(self.offered(t, path), path)

    def test_bench_only_searches_offered_with_bench_space(self):
        for path in self.BENCH_ONLY:
            t = self.table(my_bench=4)
            if path.startswith('ME2.GrimsleysMove'):
                t.state.turn_number = 3
            self.assertTrue(self.offered(t, path), path)

    # --- 5. Opponent-Bench Trainers with the opponent's Bench full -----------
    OPP_BENCH = ('XY11.CaptivatingPokPuff_99', 'SV06.AccompanyingFlute_142',
                 'SV035.ErikasInvitation_160', 'SV035.ErikasInvitation_196',
                 'SV035.ErikasInvitation_203')

    def test_opponent_bench_trainers_blocked_when_full(self):
        for path in self.OPP_BENCH:
            t = self.table(opp_bench=5)
            t.put(MON, P2, 'hand')
            self.assertFalse(self.offered(t, path), path)

    def test_opponent_bench_trainers_offered_with_space(self):
        for path in self.OPP_BENCH:
            t = self.table(opp_bench=4)
            t.put(MON, P2, 'hand')
            self.assertTrue(self.offered(t, path), path)

    # --- 6. Stated conditions ------------------------------------------------
    def test_penny_and_ninja_boy_need_a_basic_in_play(self):
        for path in ('SV1.Penny_183', 'SV1.Penny_239', 'XY11.NinjaBoy_103'):
            t = Table(self)
            t.put(STAGE1, P1, 'active')
            t.put(MON, P2, 'active')
            self.assertFalse(self.offered(t, path), path)
            t2 = self.table()
            self.assertTrue(self.offered(t2, path), path)

    def test_jett_ogres_mask_great_potion_blocked_without_targets(self):
        # GLC has no Mega Evolution Pokémon ex, Ogerpon ex or Pokémon-GX.
        for path in ('ME5.Jett_79', 'SV06.OgresMask_159', 'SV085.OgresMask_118',
                     'SM11.GreatPotion_198'):
            t = self.table(opp_bench=2)
            t.active(P1).set_attribute(AttrID.HP, 10)
            self.assertFalse(self.offered(t, path), path)

    def test_team_star_grunt_needs_energy_on_opponent_active(self):
        for path in ('SV1.TeamStarGrunt_195', 'SV1.TeamStarGrunt_242', 'SV3.TeamStarGrunt_195'):
            t = self.table()
            self.assertFalse(self.offered(t, path), path)
            t.energy(t.active(P2), WATER)
            self.assertTrue(self.offered(t, path), path)

    def test_perrin_needs_a_pokemon_in_hand(self):
        for path in ('SV06.Perrin_160', 'SV06.Perrin_209', 'SV06.Perrin_220'):
            t = self.table()
            t.put(self.item, P1, 'hand')
            self.assertFalse(self.offered(t, path), path)
            t.put(MON, P1, 'hand')
            self.assertTrue(self.offered(t, path), path)

    def test_ultra_recon_squad_needs_an_ultra_beast_in_hand(self):
        for path in ('SM6.UltraReconSquad_114', 'SM6.UltraReconSquad_131'):
            t = self.table()
            t.put(MON, P1, 'hand')
            self.assertFalse(self.offered(t, path), path)
            t.put(ULTRA_BEAST, P1, 'hand')
            self.assertTrue(self.offered(t, path), path)

    def test_roxie_needs_a_pokemon_in_hand(self):
        t = self.table()
        t.put(self.item, P1, 'hand')
        self.assertFalse(self.offered(t, 'SM12.Roxie_205'))
        t.put(MON, P1, 'hand')
        self.assertTrue(self.offered(t, 'SM12.Roxie_205'))

    def test_mistys_water_command_needs_water_energy_and_target(self):
        t = self.table()
        t.put(PSYDUCK, P1, 'bench')
        self.assertFalse(self.offered(t, 'HF.MistysWaterCommand_63'))
        t.energy(t.active(P1), WATER)
        self.assertTrue(self.offered(t, 'HF.MistysWaterCommand_63'))

    def test_mistys_water_command_needs_a_named_destination(self):
        t = self.table(my_bench=1)
        t.energy(t.active(P1), WATER)
        self.assertFalse(self.offered(t, 'HF.MistysWaterCommand_63'))

    def test_energy_reset_needs_attached_energy(self):
        t = self.table()
        self.assertFalse(self.offered(t, 'XY10.EnergyReset_98'))
        t.energy(t.active(P1), WATER)
        self.assertTrue(self.offered(t, 'XY10.EnergyReset_98'))

    def test_blaines_last_stand_needs_a_fire_pokemon(self):
        for path in ('HF.BlainesLastStand_52', 'DM.BlainesLastStand_58'):
            t = self.table()
            self.assertFalse(self.offered(t, path), path)
            t2 = self.table()
            t2.put(FIRE_MON, P1, 'bench')
            self.assertTrue(self.offered(t2, path), path)

    def test_arvens_sandwich_needs_damaged_active(self):
        t = self.table()
        self.assertFalse(self.offered(t, 'SV10.ArvensSandwich_161'))
        t.active(P1).set_attribute(AttrID.HP, t.hp(t.active(P1)) - 10)
        self.assertTrue(self.offered(t, 'SV10.ArvensSandwich_161'))

    def test_lass_special_needs_opponent_benched_basic(self):
        t = Table(self)
        t.put(MON, P1, 'active')
        t.put(MON, P2, 'active')
        t.put(STAGE1, P2, 'bench')
        self.assertFalse(self.offered(t, 'XY10.LasssSpecial_103'))
        t.put(MON, P2, 'bench')
        self.assertTrue(self.offered(t, 'XY10.LasssSpecial_103'))

    def test_meddling_memo_needs_cards_in_opponent_hand(self):
        t = self.table()
        self.assertFalse(self.offered(t, 'SV08.MeddlingMemo_181'))
        t.put(self.item, P2, 'hand')
        self.assertTrue(self.offered(t, 'SV08.MeddlingMemo_181'))

    # --- 7. Useless Abilities -------------------------------------------------
    def test_nest_stash_needs_cards_in_hand(self):
        for path in ('SV1.Skwovet_151', 'SV1.Skwovet_222', 'SV045.Skwovet_205'):
            t = self.table()
            sk = t.put(path, P1, 'bench')
            self.assertIsNone(t.ability_offer(sk, 'Nest Stash'), path)
            t.put(self.item, P1, 'hand')
            self.assertIsNotNone(t.ability_offer(sk, 'Nest Stash'), path)


if __name__ == '__main__':
    unittest.main()
