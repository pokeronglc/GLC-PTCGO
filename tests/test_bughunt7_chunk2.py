"""Bug hunt round 7, chunk 2: Gardevoir/Cresselia family, Bunnelby, Snorlax,
Town Store, Postwick, Chi-Yu, Blitzle/Zebstrika, checked against their
printed text, including the cases where they should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

PSY, FIRE, L, D, FAIRY, W = (PokemonTypes.PSYCHIC, PokemonTypes.FIRE, PokemonTypes.LIGHTNING,
                             PokemonTypes.DARKNESS, PokemonTypes.FAIRY, PokemonTypes.WATER)
GARDEVOIR_CRE, GARDEVOIR_LOT = 'SWSH6.Gardevoir_61', 'SM8.Gardevoir_141'
CRESS_LOR, CRESS_CRE = 'SWSH11.Cresselia_74', 'SWSH6.Cresselia_64'
CRESS_SFA, CRESS_PFL = 'SV065.Cresselia_21', 'ME2.Cresselia_39'
BUNNELBY, SNORLAX = 'SWSH2.Bunnelby_146', 'PGO.Snorlax_55'
TOWN_STORE, POSTWICK = 'SV3.TownStore_196', 'SV09.Postwick_154'
CHIYU_TWM, CHIYU_PBL = 'SV06.ChiYu_39', 'ME5.ChiYu_59'
BLITZLE_NVI, ZEBSTRIKA, BLITZLE_CRE = 'BW3.Blitzle_35', 'RSV10PT5.Zebstrika_32', 'SWSH6.Blitzle_50'
HOPS_WOOLOO = 'SV09.HopsWooloo_135'
HOP = 'SWSH1.Hop_165'
TOOL = 'SWSH1.BigCharm_158'
TOOL2 = 'SWSH4.RockyHelmet_159'


class Chunk2(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, 400)

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def taken(self, p):
        return 400 - p.get_attribute(AttrID.HP, 0)

    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    # --- Gardevoir (CRE): Shining Arcana / Brainwave ------------------------
    async def test_shining_arcana_attaches_energy_rest_to_hand(self):
        t = self.table()
        g = t.put(GARDEVOIR_CRE, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        energy, item = t.deck(P1, [t.basic_energy(PSY), self.item])
        # deck() puts each on top in turn: item is top, energy second
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.use(g, 'Shining Arcana')
        self.assertIn(energy, bench.children)
        self.assertIn(item, t.zone(P1, 'hand'))
        self.assertIsNone(t.ability_offer(g, 'Shining Arcana'))   # once per turn

    async def test_shining_arcana_no_energy_all_to_hand(self):
        t = self.table()
        g = t.put(GARDEVOIR_CRE, P1, 'active')
        a, b = t.deck(P1, [self.item, self.item])
        await t.use(g, 'Shining Arcana')
        hand = t.zone(P1, 'hand')
        self.assertIn(a, hand)
        self.assertIn(b, hand)
        self.assertEqual(len(g.children), 0)

    async def test_brainwave_counts_psychic_only(self):
        t = self.table()
        g = t.put(GARDEVOIR_CRE, P1, 'active')
        t.energy(g, PSY, 2)
        t.energy(g, FIRE, 1)
        await t.attack(g, 'Brainwave')
        self.assertEqual(self.taken(self.opp), 60 + 2 * 30)

    # --- Cresselia (LOR): Moonglow Reverse --------------------------------
    async def test_moonglow_reverse_moves_two_from_each(self):
        t = self.table()
        c = t.put(CRESS_LOR, P1, 'active')
        t.energy(c, PSY)
        b1 = t.put(self.filler, P1, 'bench')
        b2 = t.put(self.filler, P1, 'bench')
        c.set_attribute(AttrID.HP, t.hp(c) - 50)
        b1.set_attribute(AttrID.HP, t.hp(b1) - 10)
        await t.attack(c, 'Moonglow Reverse')
        self.assertEqual(t.damage(c), 30)          # 2 counters moved
        self.assertEqual(t.damage(b1), 0)          # only had 1
        self.assertEqual(t.damage(b2), 0)
        self.assertEqual(self.taken(self.opp), 30)

    async def test_moonglow_reverse_nothing_to_move(self):
        t = self.table()
        c = t.put(CRESS_LOR, P1, 'active')
        t.energy(c, PSY)
        await t.attack(c, 'Moonglow Reverse')
        self.assertEqual(self.taken(self.opp), 0)

    # --- Cresselia (CRE): Crescent Glow / Photon Laser --------------------
    async def test_crescent_glow_one_energy_normally(self):
        t = self.table()
        t.session.first_player_id = P1
        c = t.put(CRESS_CRE, P1, 'active')
        t.energy(c, PSY)
        bench = t.put(self.filler, P1, 'bench')
        t.deck(P1, [t.basic_energy(PSY)] * 3)
        t.pokemon = lambda cs, p: bench if bench in cs else cs[0]
        await t.attack(c, 'Crescent Glow')
        self.assertEqual(len(bench.children), 1)

    async def test_crescent_glow_three_when_going_second_first_turn(self):
        t = self.table()
        t.session.first_player_id = P2
        t.state.turn_number = 2
        c = t.put(CRESS_CRE, P1, 'active')
        t.energy(c, PSY)
        bench = t.put(self.filler, P1, 'bench')
        t.deck(P1, [t.basic_energy(PSY)] * 3 + [t.basic_energy(FIRE)])
        t.pokemon = lambda cs, p: bench if bench in cs else cs[0]
        await t.attack(c, 'Crescent Glow')
        self.assertEqual(len(bench.children), 3)
        self.assertTrue(all(self.name(e) != 'Fire Energy' for e in bench.children))

    async def test_photon_laser_five_energy_boundary(self):
        t = self.table()
        c = t.put(CRESS_CRE, P1, 'active')
        t.energy(c, PSY, 2)
        b = t.put(self.filler, P1, 'bench')
        t.energy(b, PSY, 2)                         # 4 in play
        await t.attack(c, 'Photon Laser')
        self.assertEqual(self.taken(self.opp), 30)
        t2 = self.table()
        c2 = t2.put(CRESS_CRE, P1, 'active')
        t2.energy(c2, PSY, 2)
        b2 = t2.put(self.filler, P1, 'bench')
        t2.energy(b2, PSY, 3)                       # 5 in play
        t2.energy(self.opp, PSY, 3)                 # opponent's Energy don't count anyway
        await t2.attack(c2, 'Photon Laser')
        self.assertEqual(self.taken(self.opp), 120)

    async def test_photon_laser_ignores_opponent_energy(self):
        t = self.table()
        c = t.put(CRESS_CRE, P1, 'active')
        t.energy(c, PSY, 2)
        t.energy(self.opp, PSY, 5)
        await t.attack(c, 'Photon Laser')
        self.assertEqual(self.taken(self.opp), 30)

    # --- Cresselia (SFA): Healing Pirouette / Crescent Purge --------------
    async def test_healing_pirouette_heals_mine_only(self):
        t = self.table()
        c = t.put(CRESS_SFA, P1, 'active')
        t.energy(c, PSY)
        b = t.put(self.filler, P1, 'bench')
        c.set_attribute(AttrID.HP, t.hp(c) - 30)
        b.set_attribute(AttrID.HP, t.hp(b) - 10)
        opp_bench = t.put(self.filler, P2, 'bench')
        opp_bench.set_attribute(AttrID.HP, t.hp(opp_bench) - 30)
        await t.attack(c, 'Healing Pirouette')
        self.assertEqual(t.damage(c), 10)
        self.assertEqual(t.damage(b), 0)
        self.assertEqual(t.damage(opp_bench), 30)

    async def test_crescent_purge_turns_prize_up_for_80_more(self):
        t = self.table()
        c = t.put(CRESS_SFA, P1, 'active')
        t.energy(c, PSY, 3)
        t.yes = True
        await t.attack(c, 'Crescent Purge')
        self.assertEqual(self.taken(self.opp), 160)
        up = [p for p in t.zone(P1, 'prizes') if getattr(p, 'publicly_revealed', False)]
        self.assertEqual(len(up), 1)

    async def test_crescent_purge_declined_or_no_face_down(self):
        t = self.table()
        c = t.put(CRESS_SFA, P1, 'active')
        t.energy(c, PSY, 3)
        t.yes = False
        await t.attack(c, 'Crescent Purge')
        self.assertEqual(self.taken(self.opp), 80)
        # every Prize already face up: no bonus possible
        t2 = self.table()
        c2 = t2.put(CRESS_SFA, P1, 'active')
        t2.energy(c2, PSY, 3)
        for p in t2.zone(P1, 'prizes'):
            p.publicly_revealed = True
        t2.yes = True
        await t2.attack(c2, 'Crescent Purge')
        self.assertEqual(self.taken(self.opp), 80)

    # --- Cresselia (PFL): Swelling Light ----------------------------------
    async def test_swelling_light_two_basic_psychic_to_self(self):
        t = self.table()
        c = t.put(CRESS_PFL, P1, 'active')
        t.energy(c, PSY)
        bench = t.put(self.filler, P1, 'bench')
        t.deck(P1, [t.basic_energy(PSY)] * 3 + [t.basic_energy(FIRE)])
        t.pokemon = lambda cs, p: bench if bench in cs else cs[0]
        await t.attack(c, 'Swelling Light')
        self.assertEqual(len(c.children), 3)        # 1 + 2 found
        self.assertEqual(len(bench.children), 0)
        self.assertEqual(sum(1 for x in t.zone(P1, 'deck')
                             if def_for(x.archetype_id).guid == t.basic_energy(PSY).guid), 1)

    async def test_swelling_light_ignores_non_psychic(self):
        t = self.table()
        c = t.put(CRESS_PFL, P1, 'active')
        t.energy(c, PSY)
        t.deck(P1, [t.basic_energy(FIRE)] * 2)
        await t.attack(c, 'Swelling Light')
        self.assertEqual(len(c.children), 1)

    # --- Gardevoir (LOT): Brilliant Search / Sensitive Ray ----------------
    async def test_brilliant_search_three_cards(self):
        t = self.table()
        g = t.put(GARDEVOIR_LOT, P1, 'active')
        t.energy(g, FAIRY)
        before_hand, before_deck = len(t.zone(P1, 'hand')), len(t.zone(P1, 'deck'))
        await t.attack(g, 'Brilliant Search')
        self.assertEqual(len(t.zone(P1, 'hand')) - before_hand, 3)
        self.assertEqual(before_deck - len(t.zone(P1, 'deck')), 3)

    async def test_sensitive_ray_needs_supporter_this_turn(self):
        t = self.table()
        g = t.put(GARDEVOIR_LOT, P1, 'active')
        t.energy(g, FAIRY, 3)
        await t.attack(g, 'Sensitive Ray')
        self.assertEqual(self.taken(self.opp), 70)
        t2 = self.table()
        g2 = t2.put(GARDEVOIR_LOT, P1, 'active')
        t2.energy(g2, FAIRY, 3)
        hop = t2.put(HOP, P1, 'hand')
        await t2.play(hop)
        self.assertIn(hop, t2.zone(P1, 'discard'))
        await t2.attack(g2, 'Sensitive Ray')
        self.assertEqual(self.taken(self.opp), 160)

    # --- Bunnelby (RCL): Burrow -------------------------------------------
    async def test_burrow_discards_opponent_top_card(self):
        t = self.table()
        b = t.put(BUNNELBY, P1, 'active')
        t.energy(b, W)
        top = t.deck(P2, [self.filler])[0]
        mine = len(t.zone(P1, 'deck'))
        await t.attack(b, 'Burrow')
        self.assertIn(top, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'deck')), mine)
        self.assertEqual(self.taken(self.opp), 0)

    # --- Snorlax (PGO): Block / Collapse ----------------------------------
    async def test_block_active_only(self):
        t = self.table()
        t.put(SNORLAX, P1, 'active')
        t.energy(self.opp, W, 5)
        t.put(self.filler, P2, 'bench')
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', pid=P2))
        # Snorlax on the Bench: no block
        t2 = self.table()
        t2.put(self.filler, P1, 'active')
        t2.put(SNORLAX, P1, 'bench')
        t2.energy(self.opp, W, 5)
        t2.put(self.filler, P2, 'bench')
        t2.next_turn()
        self.assertTrue(t2.can(self.opp, 'BaseRetreat', pid=P2))

    async def test_block_does_not_affect_owner(self):
        t = self.table()
        s = t.put(SNORLAX, P1, 'active')
        t.energy(s, W, 4)
        t.put(self.filler, P1, 'bench')
        self.assertTrue(t.can(s, 'BaseRetreat'))

    async def test_collapse_puts_self_asleep(self):
        t = self.table()
        s = t.put(SNORLAX, P1, 'active')
        t.energy(s, W, 4)
        await t.attack(s, 'Collapse')
        self.assertEqual(self.taken(self.opp), 150)
        self.assertIn(ASLEEP, t.conditions(s))
        self.assertNotIn(ASLEEP, t.conditions(self.opp))

    # --- Town Store (OBF) -------------------------------------------------
    async def test_town_store_finds_tool_once_per_turn_each_player(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        t.attach(TOOL2, me)                          # a Tool visible in play (GLC search rule)
        tool = t.deck(P1, [TOOL, t.basic_energy(W)])[0]
        store = t.stadium(TOWN_STORE, P2)
        entry = self.stadium_action(t, store)
        self.assertIsNotNone(entry)
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is tool][:1] or cards[:0]
        await t.do(entry)
        self.assertIn(tool, t.zone(P1, 'hand'))
        self.assertEqual(self.name(tool), def_for(t.zone(P1, 'hand')[0].archetype_id).display_name)
        self.assertIsNone(self.stadium_action(t, store))
        # opponent may use it on their own turn
        opp_tool = t.deck(P2, [TOOL])[0]
        t.next_turn()
        entry2 = self.stadium_action(t, store, P2)
        self.assertIsNotNone(entry2)
        t.picks = None
        await t.do(entry2, pid=P2)
        self.assertIn(opp_tool, t.zone(P2, 'hand'))

    async def test_town_store_only_tools(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        t.attach(TOOL2, me)
        energy = t.deck(P1, [t.basic_energy(W), self.filler])
        store = t.stadium(TOWN_STORE, P1)
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), [])[1]
        entry = self.stadium_action(t, store)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(offered, [])
        for c in energy:
            self.assertNotIn(c, t.zone(P1, 'hand'))

    # --- Postwick (JTG) ---------------------------------------------------
    async def test_postwick_boosts_hops_pokemon_both_sides(self):
        t = self.table()
        w = t.put(HOPS_WOOLOO, P1, 'active')
        t.energy(w, W, 3)
        t.stadium(POSTWICK, P2)
        await t.attack(w, 'Smash Kick')
        self.assertEqual(self.taken(self.opp), 80)
        # opponent's Hop's Pokémon is boosted too
        t2 = Table(self)
        mine = t2.put(self.filler, P1, 'active')
        self.big(mine)
        ow = t2.put(HOPS_WOOLOO, P2, 'active')
        t2.energy(ow, W, 3)
        t2.stadium(POSTWICK, P1)
        t2.next_turn()
        await t2.attack(ow, 'Smash Kick', pid=P2)
        self.assertEqual(self.taken(mine), 80)

    async def test_postwick_not_for_other_pokemon(self):
        t = self.table()
        b = t.put(BUNNELBY, P1, 'active')
        t.energy(b, W, 3)
        t.stadium(POSTWICK, P1)
        await t.attack(b, 'Headbutt Bounce')
        self.assertEqual(self.taken(self.opp), 50)

    # --- Chi-Yu (TWM): Allure / Ground Melter -----------------------------
    async def test_allure_draws_two(self):
        t = self.table()
        c = t.put(CHIYU_TWM, P1, 'active')
        t.energy(c, FIRE)
        before = len(t.zone(P1, 'hand'))
        await t.attack(c, 'Allure')
        self.assertEqual(len(t.zone(P1, 'hand')) - before, 2)

    async def test_ground_melter_with_and_without_stadium(self):
        t = self.table()
        c = t.put(CHIYU_TWM, P1, 'active')
        t.energy(c, FIRE, 2)
        st = t.stadium(POSTWICK, P2)
        await t.attack(c, 'Ground Melter')
        self.assertEqual(self.taken(self.opp), 120)
        self.assertEqual(list(t.board.find_global_area('activeStadium').children), [])
        self.assertIn(st, t.zone(P2, 'discard'))
        t2 = self.table()
        c2 = t2.put(CHIYU_TWM, P1, 'active')
        t2.energy(c2, FIRE, 2)
        await t2.attack(c2, 'Ground Melter')
        self.assertEqual(self.taken(self.opp), 60)

    # --- Chi-Yu (PBL): Whirling Envy --------------------------------------
    async def test_whirling_envy_threshold_and_no_weakness(self):
        t = self.table()
        c = t.put(CHIYU_PBL, P1, 'active')
        t.energy(c, D)
        c.set_attribute(AttrID.HP, t.hp(c) - 10)    # 1 counter
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [D.value])
        await t.attack(c, 'Whirling Envy')
        self.assertEqual(self.taken(self.opp), 20)
        t2 = self.table()
        c2 = t2.put(CHIYU_PBL, P1, 'active')
        t2.energy(c2, D)
        c2.set_attribute(AttrID.HP, t2.hp(c2) - 20)  # 2 counters
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [D.value])
        await t2.attack(c2, 'Whirling Envy')
        self.assertEqual(self.taken(self.opp), 110)

    # --- Blitzle (NVI): Agility -------------------------------------------
    async def _agility(self, heads):
        t = self.table()
        b = t.put(BLITZLE_NVI, P1, 'active')
        t.energy(b, L)
        opp = t.put(BUNNELBY, P2, 'active')
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = opp
        self.big(opp)
        t.put(self.filler, P2, 'bench')
        t.energy(opp, W, 3)
        t.heads = heads
        await t.attack(b, 'Agility')
        self.assertEqual(self.taken(opp), 10)
        t.next_turn()
        hp = t.hp(b)
        await t.attack(opp, 'Headbutt Bounce', pid=P2)
        return t, b, hp

    async def test_agility_heads_prevents_damage(self):
        t, b, hp = await self._agility(True)
        self.assertEqual(t.hp(b), hp)
        self.assertIn(b, t.zone(P1, 'active'))

    async def test_agility_tails_no_protection(self):
        t, b, hp = await self._agility(False)
        self.assertEqual(hp - t.hp(b), 50)

    # --- Zebstrika (WHT): Electrobullet -----------------------------------
    async def test_electrobullet_hits_active_and_chosen_bench(self):
        t = self.table()
        z = t.put(ZEBSTRIKA, P1, 'active')
        t.energy(z, L, 3)
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(self.filler, P2, 'bench')
        b1.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        t.pokemon = lambda cs, p: b1 if b1 in cs else cs[0]
        await t.attack(z, 'Electrobullet')
        self.assertEqual(self.taken(self.opp), 100)
        self.assertEqual(t.damage(b1), 30)          # no Weakness on the Bench
        self.assertEqual(t.damage(b2), 0)

    async def test_electrobullet_no_bench(self):
        t = self.table()
        z = t.put(ZEBSTRIKA, P1, 'active')
        t.energy(z, L, 3)
        mine = t.put(self.filler, P1, 'bench')
        await t.attack(z, 'Electrobullet')
        self.assertEqual(self.taken(self.opp), 100)
        self.assertEqual(t.damage(mine), 0)

    # --- Blitzle (CRE): Thunder Spear -------------------------------------
    async def test_thunder_spear_any_one_pokemon(self):
        t = self.table()
        b = t.put(BLITZLE_CRE, P1, 'active')
        t.energy(b, L)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), [bench])[1]
        await t.attack(b, 'Thunder Spear')
        self.assertEqual(t.damage(bench), 10)
        self.assertEqual(self.taken(self.opp), 0)
        self.assertIn(self.opp, seen)               # Active is a legal choice too

    async def test_thunder_spear_active_applies_weakness(self):
        t = self.table()
        b = t.put(BLITZLE_CRE, P1, 'active')
        t.energy(b, L)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        t.picks = lambda cards, count, prompt, display: [self.opp]
        await t.attack(b, 'Thunder Spear')
        self.assertEqual(self.taken(self.opp), 20)


if __name__ == '__main__':
    unittest.main()
