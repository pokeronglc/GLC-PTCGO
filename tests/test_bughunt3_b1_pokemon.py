"""Bug hunt round 3, batch 1: Pokémon, checked against their printed text
(focus on the unusual clauses; plain damage/sweep-covered text is skipped)."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W, F, G = PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.GRASS
VULPIX, FLOATZEL, BUIZEL = 'SM2.AlolanVulpix_21', 'SWSH9.Floatzel_39', 'SWSH45.Buizel_22'
HORSEA, SEADRA, KINGDRA = 'SWSH45.Horsea_20', 'SWSH11.Seadra_36', 'SWSH11.Kingdra_37'
MARILL, AZUMARILL, PHIONE = 'SM3.Marill_34', 'SWSH8.Azumarill_59', 'SM12.Phione_57'
SLOWPOKE, SLOWKING = 'PGO.Slowpoke_19', 'SM8.Slowking_55'
BONSLY, DRILBUR, EXCADRILL = 'SV3.Bonsly_110', 'ME5.Drilbur_46', 'SM11.Excadrill_119'
SUDOWOODO, HITMONTOP = 'SV10.EthansSudowoodo_93', 'SWSH4.Hitmontop_88'
MACHOP, MACHOKE = 'SV035.Machop_66', 'SM2.Machoke_64'
DEERLING, SAWSBUCK = 'XY10.Deerling_8', 'SM12.Sawsbuck_16'
GUZMA, BEA, NEST = 'SM3.Guzma_115', 'SWSH4.Bea_147', 'SV1.NestBall_181'
WASH = 'SWSH4.WashWaterEnergy_165'


class B1Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, 400)
        return p

    def table(self, opp=None):
        t = Table(self)
        self.opp = self.neutral(t.put(opp or self.filler, P2, 'active'))
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Alolan Vulpix (GRI 21): Beacon -------------------------------------
    async def test_vulpix_beacon_takes_up_to_two_pokemon_only(self):
        t = self.table()
        vulpix = t.put(VULPIX, P1, 'active')
        t.deck(P1, [HORSEA, MARILL, DEERLING, GUZMA])
        await t.attack(vulpix, 'Beacon')
        hand = self.hand_names(t)
        self.assertEqual(len(hand), 2)
        self.assertNotIn('Guzma', hand)

    # --- Floatzel (BRS 39): Floatify ----------------------------------------
    async def test_floatify_returns_up_to_two_items(self):
        t = self.table()
        fz = t.put(FLOATZEL, P1, 'active')
        t.energy(fz, W)
        items = [t.put(NEST, P1, 'discard') for _ in range(3)]
        t.put(GUZMA, P1, 'discard')
        await t.attack(fz, 'Floatify')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(c in items for c in hand))

    # --- Seadra (LOR 36): Hydro Jet / Swim Freely ----------------------------
    async def test_hydro_jet_20_per_water_energy_to_a_benched_target(self):
        t = self.table()
        seadra = t.put(SEADRA, P1, 'active')
        t.energy(seadra, W, 2)
        t.energy(seadra, F)                                  # not Water: doesn't count
        t.attach(WASH, seadra)                               # Wash Water provides Water
        bench = self.neutral(t.put(self.filler, P2, 'bench'))
        t.pokemon = lambda cands, prompt: bench
        await t.attack(seadra, 'Hydro Jet')
        self.assertEqual(t.hp(self.opp), 400)
        self.assertEqual(400 - t.hp(bench), 60)

    async def test_swim_freely_heads_prevents_damage_next_turn(self):
        t = self.table()
        seadra = t.put(SEADRA, P1, 'active')
        t.energy(seadra, W)
        t.heads = True
        await t.attack(seadra, 'Swim Freely')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.next_turn()
        attacker = t.put(BONSLY, P2, 'active')
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        await t.attack(attacker, 'Blubbering', pid=P2)
        self.assertEqual(t.damage(seadra), 0)
        self.assertNotIn(CONFUSED, t.conditions(seadra))

    async def test_swim_freely_tails_no_protection(self):
        t = self.table()
        seadra = t.put(SEADRA, P1, 'active')
        t.energy(seadra, W)
        t.heads = False
        await t.attack(seadra, 'Swim Freely')
        t.next_turn()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        attacker = t.put(BONSLY, P2, 'active')
        await t.attack(attacker, 'Blubbering', pid=P2)
        self.assertGreater(t.damage(seadra), 0)
        self.assertIn(CONFUSED, t.conditions(seadra))

    # --- Kingdra (LOR 37): Seething Currents ---------------------------------
    def _choose(self, index):
        async def choose(ctx, prompt, buttons, *a, **k):
            return index
        return patch.object(EffectContext, 'choose', choose)

    async def test_seething_currents_opponent_hand_bottom_then_draw_four(self):
        t = self.table()
        kingdra = t.put(KINGDRA, P1, 'bench')
        t.put(self.filler, P1, 'active')
        hand = [t.put(GUZMA, P2, 'hand') for _ in range(6)]
        t.yes = True
        with self._choose(1):
            await t.use(kingdra, 'Seething Currents')
        new = t.zone(P2, 'hand')
        self.assertEqual(len(new), 4)
        self.assertFalse(any(c in hand for c in new))
        deck = t.zone(P2, 'deck')
        self.assertTrue(all(c in deck[:6] for c in hand))   # on the bottom
        self.assertEqual(self.hand_names(t), [])            # my hand untouched
        self.assertIsNone(t.ability_offer(kingdra, 'Seething Currents'))

    async def test_seething_currents_empty_hand_draws_nothing(self):
        t = self.table()
        kingdra = t.put(KINGDRA, P1, 'active')
        theirs = t.put(GUZMA, P2, 'hand')
        t.yes = True
        with self._choose(0):
            await t.use(kingdra, 'Seething Currents')
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(t.zone(P2, 'hand'), [theirs])

    # --- Azumarill (FST 59): Dive and Rescue ---------------------------------
    async def test_dive_and_rescue_pokemon_and_supporters_only(self):
        t = self.table()
        az = t.put(AZUMARILL, P1, 'active')
        t.energy(az, W)
        wanted = [t.put(GUZMA, P1, 'discard'), t.put(HORSEA, P1, 'discard'),
                  t.put(MARILL, P1, 'discard')]
        nest = t.put(NEST, P1, 'discard')
        t.put(t.basic_energy(W), P1, 'discard')
        await t.attack(az, 'Dive and Rescue')
        hand = t.zone(P1, 'hand')
        self.assertEqual(sorted(map(id, hand)), sorted(map(id, wanted)))
        self.assertIn(nest, t.zone(P1, 'discard'))

    # --- Phione (CEC 57): Whirlpool Suction -----------------------------------
    async def test_whirlpool_suction_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        phione = t.put(PHIONE, P1, 'bench')
        e = t.energy(phione, W)
        opp_bench = t.put(DEERLING, P2, 'bench')
        await t.use(phione, 'Whirlpool Suction')
        self.assertIs(t.active(P2), opp_bench)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIn(e, t.zone(P1, 'discard'))
        deck = t.zone(P1, 'deck')
        self.assertIs(deck[0], phione)                      # bottom of the deck
        self.assertNotIn(phione, t.zone(P1, 'bench'))

    async def test_whirlpool_suction_not_from_active(self):
        t = self.table()
        phione = t.put(PHIONE, P1, 'active')
        t.put(DEERLING, P2, 'bench')
        self.assertIsNone(t.ability_offer(phione, 'Whirlpool Suction'))

    async def test_whirlpool_suction_needs_opponent_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        phione = t.put(PHIONE, P1, 'bench')
        self.assertIsNone(t.ability_offer(phione, 'Whirlpool Suction'))

    # --- Slowpoke (PGO 19): Ideal Fishing Day -----------------------------------
    async def test_ideal_fishing_day_takes_an_item(self):
        t = self.table()
        sp = t.put(SLOWPOKE, P1, 'active')
        t.energy(sp, W)
        nest = t.put(NEST, P1, 'discard')
        t.put(GUZMA, P1, 'discard')
        await t.attack(sp, 'Ideal Fishing Day')
        self.assertEqual(t.zone(P1, 'hand'), [nest])

    # --- Slowking (LOT 55): Memory Melt / Psychic -------------------------------
    async def test_memory_melt_lost_zones_an_opponent_hand_card(self):
        t = self.table()
        sk = t.put(SLOWKING, P1, 'active')
        t.energy(sk, W)
        cards = [t.put(GUZMA, P2, 'hand'), t.put(NEST, P2, 'hand')]
        t.picks = lambda c, n, p, d: [x for x in c if x is cards[1]] or c[:n]
        await t.attack(sk, 'Memory Melt')
        self.assertEqual(t.zone(P2, 'hand'), [cards[0]])
        self.assertIn(cards[1], t.zone(P2, 'lostZone'))

    async def test_psychic_plus_20_per_energy_on_opponent_active(self):
        t = self.table()
        sk = t.put(SLOWKING, P1, 'active')
        t.energy(sk, W, 3)
        t.energy(self.opp, W, 2)
        t.attach(WASH, self.opp)
        t.energy(t.put(self.filler, P2, 'bench'), W, 2)     # bench energy doesn't count
        await t.attack(sk, 'Psychic')
        self.assertEqual(400 - t.hp(self.opp), 60 + 3 * 20)

    # --- Excadrill (UNM 119): Rototiller ------------------------------------------
    async def test_rototiller_shuffles_four_from_discard(self):
        t = self.table()
        ex = t.put(EXCADRILL, P1, 'active')
        t.energy(ex, F)
        for _ in range(6):
            t.put(GUZMA, P1, 'discard')
        await t.attack(ex, 'Rototiller')
        self.assertEqual(len(t.zone(P1, 'discard')), 2)
        self.assertEqual(len(t.zone(P1, 'deck')), 34)

    async def test_rototiller_fewer_than_four(self):
        t = self.table()
        ex = t.put(EXCADRILL, P1, 'active')
        t.energy(ex, F)
        t.put(GUZMA, P1, 'discard')
        await t.attack(ex, 'Rototiller')
        self.assertEqual(len(t.zone(P1, 'discard')), 0)
        self.assertEqual(len(t.zone(P1, 'deck')), 31)

    # --- Drilbur (PBL 46): Call for Family -----------------------------------------
    async def test_call_for_family_benches_two_basics(self):
        t = self.table()
        dr = t.put(DRILBUR, P1, 'active')
        t.energy(dr, F)
        t.deck(P1, [HORSEA, MARILL, DEERLING, SEADRA])
        await t.attack(dr, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        self.assertNotIn('Seadra', t.names(bench))

    # --- Ethan's Sudowoodo (DRI 93): Impound / Try to Imitate ------------------------
    async def test_impound_blocks_retreat_next_turn(self):
        t = self.table()
        sw = t.put(SUDOWOODO, P1, 'active')
        t.energy(sw, F)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W, 4)
        await t.attack(sw, 'Impound')
        self.assertEqual(400 - t.hp(self.opp), 20)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', pid=P2))
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', pid=P2))

    async def test_try_to_imitate_copies_defender_attack(self):
        t = Table(self)
        opp = self.neutral(t.put(MACHOKE, P2, 'active'))     # Cross Chop 30+ coin
        sw = t.put(SUDOWOODO, P1, 'active')
        t.energy(sw, F, 2)
        t.heads = True
        await t.attack(sw, 'Try to Imitate')
        self.assertEqual(400 - t.hp(opp), 60)                # heads, then Cross Chop heads

    async def test_try_to_imitate_tails_does_nothing(self):
        t = Table(self)
        opp = self.neutral(t.put(MACHOKE, P2, 'active'))
        sw = t.put(SUDOWOODO, P1, 'active')
        t.energy(sw, F, 2)
        t.heads = False
        await t.attack(sw, 'Try to Imitate')
        self.assertEqual(t.hp(opp), 400)

    # --- Hitmontop (VIV 88): Cycle Draw / Tornado Kick ---------------------------------
    async def test_cycle_draw_discard_one_draw_three(self):
        t = self.table()
        top = t.put(HITMONTOP, P1, 'active')
        t.energy(top, F)
        junk = t.put(GUZMA, P1, 'hand')
        await t.attack(top, 'Cycle Draw')
        self.assertIn(junk, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_tornado_kick_bonus_only_after_bea(self):
        for played in (False, True):
            t = self.table()
            top = t.put(HITMONTOP, P1, 'active')
            t.energy(top, F, 3)
            if played:
                await t.play(t.put(BEA, P1, 'hand'))
            await t.attack(top, 'Tornado Kick')
            with self.subTest(bea=played):
                self.assertEqual(400 - t.hp(self.opp), 130 if played else 50)

    # --- Machop (MEW 66): Mountain Mashing ----------------------------------------------
    async def test_mountain_mashing_discards_opponent_top_card(self):
        t = self.table()
        mp = t.put(MACHOP, P1, 'active')
        t.energy(mp, F)
        top = t.deck(P2, [GUZMA])[0]
        await t.attack(mp, 'Mountain Mashing')
        self.assertIn(top, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P2, 'deck')), 30)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Machoke (GRI 64): Daunting Pose --------------------------------------------------
    async def test_daunting_pose_prevents_attack_damage_to_my_bench(self):
        t = self.table(SEADRA)
        t.energy(self.opp, W, 2)
        me = self.neutral(t.put(self.filler, P1, 'active'))
        t.put(MACHOKE, P1, 'bench')
        target = self.neutral(t.put(self.filler, P1, 'bench'))
        t.next_turn()
        t.pokemon = lambda cands, prompt: target
        await t.attack(self.opp, 'Hydro Jet', pid=P2)
        self.assertEqual(t.hp(target), 400)

    async def test_daunting_pose_does_not_protect_active(self):
        t = self.table(SEADRA)
        t.energy(self.opp, W, 2)
        me = self.neutral(t.put(self.filler, P1, 'active'))
        t.put(MACHOKE, P1, 'bench')
        t.next_turn()
        t.pokemon = lambda cands, prompt: me
        await t.attack(self.opp, 'Hydro Jet', pid=P2)
        self.assertEqual(400 - t.hp(me), 40)

    # --- Deerling (FCO 8): Find a Friend ----------------------------------------------------
    async def test_find_a_friend_any_pokemon(self):
        t = self.table()
        d = t.put(DEERLING, P1, 'active')
        t.energy(d, G)
        t.deck(P1, [SEADRA, GUZMA])
        t.picks = lambda c, n, p, disp: [x for x in c if self.name(x) == 'Seadra'][:n] or c[:n]
        await t.attack(d, 'Find a Friend')
        self.assertEqual(self.hand_names(t), ['Seadra'])

    # --- Sawsbuck (CEC 16): Seasonal Blessings / Bounce ---------------------------------------
    async def test_seasonal_blessings_draws_once_per_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        saws = t.put(SAWSBUCK, P1, 'bench')
        await t.use(saws, 'Seasonal Blessings')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertIsNone(t.ability_offer(saws, 'Seasonal Blessings'))

    async def test_bounce_switches_when_chosen(self):
        t = self.table()
        saws = t.put(SAWSBUCK, P1, 'active')
        t.energy(saws, G, 2)
        bench = t.put(self.filler, P1, 'bench')
        await t.attack(saws, 'Bounce')
        self.assertEqual(400 - t.hp(self.opp), 60)
        self.assertIs(t.active(P1), bench)

    # Was a bug (fixed Oct 10): "You may switch" is a forced pick (choose_pokemon without optional=True)
    async def test_bounce_switch_is_optional(self):
        t = self.table()
        saws = t.put(SAWSBUCK, P1, 'active')
        t.energy(saws, G, 2)
        t.put(self.filler, P1, 'bench')
        seen = []

        async def choose_pokemon(ctx, candidates, prompt='', player_id=None, optional=False):
            seen.append(optional)
            return None if optional else list(candidates)[0]    # decline whenever allowed
        base = t._patches
        t._patches = lambda: [p for p in base() if p.attribute != 'choose_pokemon'] + [
            patch.object(EffectContext, 'choose_pokemon', choose_pokemon)]
        await t.attack(saws, 'Bounce')
        self.assertEqual(seen, [True])
        self.assertIs(t.active(P1), saws)

if __name__ == '__main__':
    unittest.main()
