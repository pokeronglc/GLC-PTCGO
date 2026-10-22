"""Bug hunt round 7, chunk 41: Zygarde EVS, Sewaddle line, Fisherman, Bill's
Transfer, Aspertia City Gym, Carracosta, Katy, Antique Sail Fossil, Horsea
line, Bruxish, Dewgong -- each checked against its printed text, including
the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

GRASS, FIGHT, WATER, FIRE = (PokemonTypes.GRASS, PokemonTypes.FIGHTING,
                             PokemonTypes.WATER, PokemonTypes.FIRE)

ZYGARDE = 'SWSH7.Zygarde_118'
SEWADDLE, SWADLOON, LEAVANNY = 'SM11.Sewaddle_7', 'RSV10PT5.Swadloon_2', 'SM11.Leavanny_9'
FISHERMAN, BILLS, KATY = 'SM7.Fisherman_130', 'SV035.BillsTransfer_156', 'SV1.Katy_177'
ASPERTIA = 'BW7.AspertiaCityGym_127'
CARRACOSTA = 'SV07.Carracosta_38'
SAIL = 'ME3.AntiqueSailFossil_69'
HORSEA, SEADRA, KINGDRA = 'SV065.Horsea_10', 'SV065.Seadra_11', 'SWSH5.Kingdra_33'
BRUXISH, DEWGONG = 'SV08.Bruxish_49', 'ME3.Dewgong_19'
BOSS = 'SWSH45.BosssOrders_58'
DCE_LIKE = 'SV2.TherapeuticEnergy_193'      # a Special Energy


class Chunk41(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def neutral(p, hp=None):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def table(self, opp=True):
        t = Table(self)
        if opp:
            self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    def mine(self, t, spec, zone='active', kind=None, count=0, hp=None):
        p = self.neutral(t.put(spec, P1, zone), hp)
        if count:
            t.energy(p, kind, count)
        return p

    async def opp_hits(self, t, attacker=None):
        """Opponent's Snorlax filler uses Heavy Impact (80) on P1's Active."""
        attacker = attacker or self.opp
        t.energy(attacker, WATER, 3)
        t.next_turn()
        await t.attack(attacker, 'Heavy Impact', pid=P2)

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def is_basic_energy(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    # --- Zygarde EVS 118: Judgment Surge -----------------------------------
    async def test_zygarde_judgment_surge_scales_and_hits_bench(self):
        t = self.table()
        bench = self.neutral(t.put(self.filler, P2, 'bench'), 400)
        t.set_prizes(P2, 4)                       # opponent has taken 2
        zyg = self.mine(t, ZYGARDE)
        t.energy(zyg, GRASS); t.energy(zyg, FIGHT); t.energy(zyg, WATER)
        t.pokemon = lambda c, p: bench
        await t.attack(zyg, 'Judgment Surge')
        self.assertEqual(400 - t.hp(bench), 80)
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_zygarde_judgment_surge_no_prizes_taken(self):
        t = self.table()
        zyg = self.mine(t, ZYGARDE)
        t.energy(zyg, GRASS); t.energy(zyg, FIGHT); t.energy(zyg, WATER)
        await t.attack(zyg, 'Judgment Surge')
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Sewaddle UNM 7 -----------------------------------------------------
    async def test_sewaddle_swaddling_leaves(self):
        t = self.table()
        sew = self.mine(t, SEWADDLE, hp=200)
        await self.opp_hits(t)
        self.assertEqual(200 - t.hp(sew), 70)

    async def test_sewaddle_surprise_attack(self):
        for heads in (True, False):
            t = self.table()
            sew = self.mine(t, SEWADDLE, kind=GRASS, count=1)
            t.heads = heads
            await t.attack(sew, 'Surprise Attack')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 20 if heads else 0)

    # --- Swadloon WHT 2: Healing Leaves ---------------------------------------
    async def test_swadloon_healing_leaves_heals_active_once(self):
        t = self.table()
        active = self.mine(t, self.filler)
        active.set_attribute(AttrID.HP, effective_max_hp(t.board, active) - 50)
        swad = self.mine(t, SWADLOON, 'bench')
        await t.use(swad, 'Healing Leaves')
        self.assertEqual(t.damage(active), 30)
        self.assertEqual(t.damage(swad), 0)
        self.assertIsNone(t.ability_offer(swad, 'Healing Leaves'))

    # --- Leavanny UNM 9: Blanket Weaver ---------------------------------------
    async def test_leavanny_blanket_weaver_grass_only_and_no_stack(self):
        for my_active, leavannies, expected in ((SWADLOON, 1, 40), (SWADLOON, 2, 40),
                                                (None, 1, 80), (SEWADDLE, 1, 30)):
            t = self.table()
            active = self.mine(t, my_active or self.filler, hp=300)
            for _ in range(leavannies):
                self.mine(t, LEAVANNY, 'bench')
            await self.opp_hits(t)
            with self.subTest(active=my_active, leavannies=leavannies):
                self.assertEqual(300 - t.hp(active), expected)

    async def test_leavanny_blanket_weaver_not_own_attacks(self):
        """Only 'your opponent's attacks' are reduced."""
        t = self.table(opp=False)
        target = self.neutral(t.put(SWADLOON, P2, 'active'), 300)
        t.put(LEAVANNY, P1, 'bench')                # P1's Leavanny: protects P1 only
        attacker = self.mine(t, self.filler, kind=WATER, count=3)
        await t.attack(attacker, 'Heavy Impact')
        self.assertEqual(300 - t.hp(target), 80)

    # --- Fisherman CES 130 -------------------------------------------------------
    async def test_fisherman_takes_four_basic_energy(self):
        t = self.table()
        self.mine(t, self.filler)
        energies = [t.put(t.basic_energy(WATER), P1, 'discard') for _ in range(5)]
        special = t.put(DCE_LIKE, P1, 'discard')
        card = t.put(FISHERMAN, P1, 'hand')
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(e in hand for e in energies), 4)
        self.assertNotIn(special, hand)

    async def test_fisherman_not_playable_without_basic_energy(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(DCE_LIKE, P1, 'discard')
        card = t.put(FISHERMAN, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Bill's Transfer MEW 156 ------------------------------------------------
    async def test_bills_transfer_only_top_eight(self):
        t = self.table()
        self.mine(t, self.filler)
        deck = t.board.find_player_area(P1, 'deck')
        deep = t.put(HORSEA, P1, 'deck')            # 9th from top
        top = [t.put(SEADRA, P1, 'deck')] + [t.put(self.item, P1, 'deck') for _ in range(5)] \
            + [t.put(t.basic_energy(WATER), P1, 'deck'), t.put(SEWADDLE, P1, 'deck')]
        seen = []
        t.picks = lambda cards, count, prompt, display: (
            seen.append(list(display or cards)),
            [c for c in cards if c in (top[0], top[-1])])[1]
        card = t.put(BILLS, P1, 'hand')
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertIn(top[0], hand)
        self.assertIn(top[-1], hand)
        self.assertNotIn(deep, hand)
        self.assertNotIn(top[6], hand)              # Energy is not a Pokémon
        self.assertEqual(len(hand), 2)
        self.assertEqual(len(deck.children), 30 + 9 - 2)

    # --- Aspertia City Gym BCR 127 ------------------------------------------------
    async def test_aspertia_city_gym_colorless_both_sides(self):
        t = self.table()
        mine = self.mine(t, self.filler)
        grass = self.mine(t, SEWADDLE, 'bench')
        base_c = effective_max_hp(t.board, mine)
        base_g = effective_max_hp(t.board, grass)
        base_o = effective_max_hp(t.board, self.opp)
        t.stadium(ASPERTIA, P2)
        self.assertEqual(effective_max_hp(t.board, mine), base_c + 20)
        self.assertEqual(effective_max_hp(t.board, self.opp), base_o + 20)
        self.assertEqual(effective_max_hp(t.board, grass), base_g)

    # --- Carracosta SCR 38: Primal Knowledge --------------------------------------
    async def test_carracosta_primal_knowledge(self):
        for target_spec, expected in ((SWADLOON, 110), (None, 80)):
            t = self.table(opp=False)
            target = self.neutral(t.put(target_spec or self.filler, P2, 'active'), 400)
            attacker = self.mine(t, self.filler, kind=WATER, count=3)
            self.mine(t, CARRACOSTA, 'bench')
            await t.attack(attacker, 'Heavy Impact')
            with self.subTest(target=target_spec):
                self.assertEqual(400 - t.hp(target), expected)

    async def test_carracosta_not_benched_evolution_nor_opponent_attacks(self):
        t = self.table(opp=False)
        self.neutral(t.put(self.filler, P2, 'active'), 400)
        # Opponent attacks P1's Active Stage 1: P1's own Carracosta must not boost it.
        opp_attacker = t.active(P2)
        swad = self.mine(t, SWADLOON, hp=300)
        self.mine(t, CARRACOSTA, 'bench')
        await self.opp_hits(t, opp_attacker)
        self.assertEqual(300 - t.hp(swad), 80)

    # --- Katy SVI 177 --------------------------------------------------------------
    async def test_katy_shuffles_draws_eight_and_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        old = [t.put(SEWADDLE, P1, 'hand') for _ in range(3)]
        card = t.put(KATY, P1, 'hand')
        ended = await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 8)
        self.assertEqual(len(t.zone(P1, 'deck')), 30 + 3 - 8)
        self.assertIn(card, t.zone(P1, 'discard'))
        self.assertTrue(ended, 'Katy ends the turn')
        self.assertTrue(all(c in t.zone(P1, 'deck') or c in hand for c in old))

    # --- Antique Sail Fossil POR 69: Protective Sail --------------------------------
    async def sail(self, t):
        t.put(self.filler, P1, 'active')
        card = t.put(SAIL, P1, 'hand')
        await t.play(card)
        return next(p for p in t.board.pokemon_in_play(P1) if self.name(p) == 'Antique Sail Fossil')

    async def test_antique_sail_blocks_bosss_orders(self):
        t = self.table()
        fossil = await self.sail(t)
        boss = t.put(BOSS, P2, 'hand')
        t.next_turn()
        t.pokemon = lambda c, p: fossil if fossil in c else c[0]
        if t.can(boss, 'UseTrainerCard', P2):
            await t.play(boss, pid=P2, targets=[fossil.entity_id])
        self.assertIsNot(t.active(P1), fossil)

    async def test_antique_sail_does_not_block_opponents_items(self):
        """Only Supporters are prevented: an opponent's Pokémon Catcher still
        brings the Fossil Active."""
        t = self.table()
        fossil = await self.sail(t)
        catcher = t.put('SWSH1.PokemonCatcher_175', P2, 'hand')
        t.heads = True
        t.pokemon = lambda c, p: fossil if fossil in c else c[0]
        t.next_turn()
        await t.play(catcher, pid=P2, targets=[fossil.entity_id])
        self.assertIs(t.active(P1), fossil)

    # --- Horsea SFA 10: Hold Still ---------------------------------------------------
    async def test_horsea_hold_still(self):
        t = self.table()
        horsea = self.mine(t, HORSEA, kind=WATER, count=1)
        horsea.set_attribute(AttrID.HP, 20)            # 40 damage
        await t.attack(horsea, 'Hold Still')
        self.assertEqual(t.damage(horsea), 10)
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Seadra SFA 11: Call for Backup ----------------------------------------------
    async def test_seadra_call_for_backup_up_to_three(self):
        t = self.table()
        seadra = self.mine(t, SEADRA, kind=WATER, count=1)
        mons = t.deck(P1, [HORSEA, SEWADDLE, KINGDRA, BRUXISH], top=False)
        t.deck(P1, [t.basic_energy(WATER)])
        await t.attack(seadra, 'Call for Backup')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertTrue(all(c in mons for c in hand))
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_seadra_call_for_backup_may_take_zero(self):
        t = self.table()
        seadra = self.mine(t, SEADRA, kind=WATER, count=1)
        t.deck(P1, [HORSEA])
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(seadra, 'Call for Backup')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Kingdra BST 33 ------------------------------------------------------------------
    async def test_kingdra_aqua_burst(self):
        t = self.table()
        king = self.mine(t, KINGDRA, kind=WATER, count=3)
        t.energy(king, FIRE)
        await t.attack(king, 'Aqua Burst')
        self.assertEqual(400 - t.hp(self.opp), 120)

    async def test_kingdra_deep_sea_king_moves_water_on_active_ko(self):
        t = self.table()
        active = self.mine(t, SEWADDLE, hp=10)
        waters = t.energy(active, WATER, 2)
        fire = t.energy(active, FIRE)
        king = self.mine(t, KINGDRA, 'bench')
        await self.opp_hits(t)
        self.assertNotIn(active, t.board.pokemon_in_play(P1))
        for w in waters:
            self.assertIn(w, king.children)
        self.assertNotIn(fire, king.children)

    async def test_kingdra_deep_sea_king_not_for_benched_ko(self):
        t = self.table(opp=False)
        self.mine(t, self.filler, hp=300)
        victim = self.mine(t, SEWADDLE, 'bench', hp=10)
        water = t.energy(victim, WATER)
        king = self.mine(t, KINGDRA, 'bench')
        zyg = self.neutral(t.put(ZYGARDE, P2, 'active'), 400)
        t.energy(zyg, GRASS); t.energy(zyg, FIGHT); t.energy(zyg, WATER)
        t.set_prizes(P1, 5)                       # P2 has taken 1 Prize
        t.pokemon = lambda c, p: victim if victim in c else c[0]
        t.next_turn()
        await t.attack(zyg, 'Judgment Surge', pid=P2)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertNotIn(water, king.children)

    # --- Bruxish SSP 49 -----------------------------------------------------------------
    async def test_bruxish_counterattack_active(self):
        t = self.table()
        self.mine(t, BRUXISH, hp=300)
        await self.opp_hits(t)
        self.assertEqual(400 - t.hp(self.opp), 30)

    async def test_bruxish_counterattack_even_if_knocked_out(self):
        t = self.table()
        brux = self.mine(t, BRUXISH, hp=50)
        self.mine(t, self.filler, 'bench')
        await self.opp_hits(t)
        self.assertNotIn(brux, t.board.pokemon_in_play(P1))
        self.assertEqual(400 - t.hp(self.opp), 30)

    async def test_bruxish_counterattack_not_on_bench(self):
        t = self.table(opp=False)
        self.mine(t, self.filler, hp=300)
        brux = self.mine(t, BRUXISH, 'bench', hp=300)
        zyg = self.neutral(t.put(ZYGARDE, P2, 'active'), 400)
        t.energy(zyg, GRASS); t.energy(zyg, FIGHT); t.energy(zyg, WATER)
        t.set_prizes(P1, 5)                       # P2 has taken 1 Prize
        t.pokemon = lambda c, p: brux if brux in c else c[0]
        t.next_turn()
        await t.attack(zyg, 'Judgment Surge', pid=P2)
        self.assertEqual(300 - t.hp(brux), 40)
        self.assertEqual(400 - t.hp(zyg), 0)

    async def test_bruxish_big_bite_no_retreat(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, WATER, 4)
        brux = self.mine(t, BRUXISH, kind=WATER, count=2)
        await t.attack(brux, 'Big Bite')
        self.assertEqual(400 - t.hp(self.opp), 50)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'RetreatPokemon', P2)
                         or any('etreat' in e['selectableAction']['description']
                                for e in t.offers(self.opp, None, P2)))

    # --- Dewgong POR 19: Wash Out ------------------------------------------------------
    # BUG: "As often as you like" is read as "move any number of Energy": one use moves every Water Energy.
    async def test_dewgong_wash_out_moves_one_energy_per_use(self):
        t = self.table()
        active = self.mine(t, self.filler)
        dew = self.mine(t, DEWGONG, 'bench')
        waters = t.energy(dew, WATER, 2)
        await t.use(dew, 'Wash Out')
        self.assertEqual(sum(w in active.children for w in waters), 1)
        await t.use(dew, 'Wash Out')                 # usable again: as often as you like
        self.assertEqual(sum(w in active.children for w in waters), 2)

    async def test_dewgong_wash_out_water_only(self):
        t = self.table()
        active = self.mine(t, self.filler)
        dew = self.mine(t, DEWGONG, 'bench')
        water = t.energy(dew, WATER)
        fire = t.energy(dew, FIRE)
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.use(dew, 'Wash Out')
        self.assertIn(water, active.children)
        self.assertIn(fire, dew.children)
        self.assertNotIn(fire, seen)
        self.assertIsNone(t.ability_offer(dew, 'Wash Out'))     # only Fire left on the Bench

    async def test_dewgong_wash_out_not_from_active(self):
        t = self.table()
        dew = self.mine(t, DEWGONG, kind=WATER, count=1)
        self.mine(t, self.filler, 'bench')
        self.assertIsNone(t.ability_offer(dew, 'Wash Out'))


if __name__ == '__main__':
    unittest.main()
