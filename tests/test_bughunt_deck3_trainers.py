"""Bug hunt, deck 3 (Fighting): Items, Stadiums and Supporters, through the
real play-trainer executor (so play conditions and once-per-turn rules apply)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

F, D, W = PokemonTypes.FIGHTING, PokemonTypes.DARKNESS, PokemonTypes.WATER
LUNATONE, SOLROCK, MAKUHITA = 'ME1.Lunatone_74', 'ME1.Solrock_75', 'ME1.Makuhita_72'
RIOLU, LUCARIO, TINGLU, HAWLUCHA = 'SM5.Riolu_66', 'SV1.Lucario_114', 'SV06.TingLu_110', 'SV1.Hawlucha_118'
WEEZING = 'SWSH2.GalarianWeezing_113'
STRONG, PRISM = 'XY10.StrongEnergy_115', 'BW4.PrismEnergy_93'
VIP, COLOGNE, GONG, PPP = ('SWSH8.BattleVIPPass_225', 'SWSH10.CancelingCologne_136',
                           'ME1.FightingGong_116', 'ME1.PremiumPowerPro_124')
BROOKLET, COURT, ARTAZON = 'SM2.BrookletHill_120', 'SWSH2.TrainingCourt_169', 'SV2.Artazon_171'
BOSS, CC, KORRINA, TARRAGON = ('SWSH2.BosssOrders_154', 'SM12.CynthiaCaitlin_189',
                               'XY3.Korrina_95', 'ME3.Tarragon_85')
NEST, FLOAT = 'SV1.NestBall_181', 'XY8.FloatStone_137'


class Deck3Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        for p in (self.me, self.opp):
            p.set_attribute(AttrID.WEAKNESS_TYPES, [])
            p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    def spy(self, t, take=None):
        seen = {}

        def picks(cards, count, prompt, display):
            seen.setdefault('calls', []).append((t.names(cards), count, prompt))
            if take is not None:
                return take(cards, count)
            return cards[:count]
        t.picks = picks
        return seen

    def swap_active(self, t, pid, spec):
        area = t.board.find_player_area(pid, 'activePokemonArea')
        for c in list(area.children):
            area.remove_child(c)
        p = t.put(spec, pid, 'active')
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    # --- Battle VIP Pass ----------------------------------------------------
    async def test_battle_vip_pass_first_turn_two_basics(self):
        t = self.table()
        t.state.turn_number = 1
        t.deck(P1, [MAKUHITA, RIOLU, LUCARIO, LUNATONE])
        seen = self.spy(t)
        card = t.put(VIP, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(seen['calls'][0][1], 2)
        self.assertNotIn('Lucario', seen['calls'][0][0])
        self.assertEqual(len(t.zone(P1, 'bench')), 2)

    async def test_battle_vip_pass_not_after_first_turn(self):
        t = self.table()                         # turn 3
        t.deck(P1, [MAKUHITA])
        self.assertFalse(t.can(t.put(VIP, P1, 'hand'), 'UseTrainerCard'))

    # --- Canceling Cologne --------------------------------------------------
    async def test_canceling_cologne_lifts_neutralizing_gas_this_turn(self):
        t = self.table()
        self.swap_active(t, P2, WEEZING)
        luna = t.put(LUNATONE, P1, 'bench')
        t.put(SOLROCK, P1, 'bench')
        t.put(t.basic_energy(F), P1, 'hand')
        self.assertIsNone(t.ability_offer(luna, 'Lunar Cycle'))
        await t.play(t.put(COLOGNE, P1, 'hand'))
        self.assertIsNotNone(t.ability_offer(luna, 'Lunar Cycle'))
        # Only until the end of this turn (begin_turn with the board prunes
        # expired temporary passives, as the session does)
        t.state.begin_turn(P2, t.board); t.state.begin_turn(P1, t.board)
        self.assertIsNone(t.ability_offer(luna, 'Lunar Cycle'))

    async def test_canceling_cologne_does_not_touch_benched_or_own(self):
        t = self.table()
        t.put(WEEZING, P2, 'bench')                      # benched: no lock anyway
        my_weezing = self.swap_active(t, P1, WEEZING)    # mine, Active: keeps locking P2
        opp_luna = t.put(LUNATONE, P2, 'bench')
        t.put(SOLROCK, P2, 'bench')
        t.put(t.basic_energy(F), P2, 'hand')
        await t.play(t.put(COLOGNE, P1, 'hand'))
        t.state.active_player_id = P2
        self.assertIsNone(t.ability_offer(opp_luna, 'Lunar Cycle', pid=P2))

    # --- Fighting Gong --------------------------------------------------------
    async def test_fighting_gong_basic_fighting_energy_or_pokemon(self):
        t = self.table()
        t.deck(P1, [LUCARIO, STRONG, t.basic_energy(D), self.filler, MAKUHITA, t.basic_energy(F)])
        seen = self.spy(t)
        await t.play(t.put(GONG, P1, 'hand'))
        names, count, _ = seen['calls'][0]
        self.assertEqual(count, 1)
        self.assertIn('Makuhita', names)
        self.assertEqual(len(names), 2)          # Makuhita + the basic Fighting Energy
        for bad in ('Lucario', 'Strong Energy', def_for(self.filler.guid).display_name):
            self.assertNotIn(bad, names)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    # --- Premium Power Pro ------------------------------------------------------
    async def test_premium_power_pro_plus_30_to_active_only_this_turn(self):
        t = self.table()
        ting = self.swap_active(t, P1, TINGLU)
        t.energy(ting, F, 3)
        bench = t.put(self.filler, P2, 'bench')
        t.stadium(ARTAZON, P2)
        await t.play(t.put(PPP, P1, 'hand'))
        await t.attack(ting, 'Ground Crasher')
        self.assertEqual(400 - t.hp(self.opp), 60)
        self.assertEqual(t.damage(bench), 30)
        t.next_turn(); t.next_turn()
        self.opp.set_attribute(AttrID.HP, 400)
        await t.attack(ting, 'Hammer In')
        self.assertEqual(400 - t.hp(self.opp), 110)

    # --- Brooklet Hill ------------------------------------------------------------
    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_brooklet_hill_basic_water_or_fighting_each_player(self):
        t = self.table()
        # GLC (Salvatore ruling): the searching player's visible Pokémon must
        # allow a Water/Fighting deck, so both Actives are Fighting here.
        self.swap_active(t, P1, TINGLU)
        self.swap_active(t, P2, TINGLU)
        hill = t.stadium(BROOKLET, P2)
        t.deck(P1, [LUCARIO, self.filler, MAKUHITA])
        seen = self.spy(t)
        entry = self.stadium_action(t, hill)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Makuhita'])
        self.assertEqual(seen['calls'][0][0], ['Makuhita'])
        self.assertIsNone(self.stadium_action(t, hill))
        # The opponent gets their own use on their turn
        t.next_turn()
        t.deck(P2, [RIOLU])
        entry = self.stadium_action(t, hill, P2)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertEqual(t.names(t.zone(P2, 'bench')), ['Riolu'])

    # --- Training Court ------------------------------------------------------------
    async def test_training_court_basic_energy_only(self):
        t = self.table()
        court = t.stadium(COURT, P1)
        t.put(STRONG, P1, 'discard')
        self.assertIsNone(self.stadium_action(t, court))     # no basic Energy
        t.put(t.basic_energy(F), P1, 'discard')
        entry = self.stadium_action(t, court)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(self.hand_names(t)[0] != 'Strong Energy', True)
        self.assertIsNone(self.stadium_action(t, court))

    # --- Boss's Orders ----------------------------------------------------------------
    async def test_boss_orders(self):
        t = self.table()
        card = t.put(BOSS, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        target = t.put(self.filler, P2, 'bench')
        await t.play(card)
        self.assertIs(t.active(P2), target)
        self.assertIs(t.active(P1), self.me)

    # --- Cynthia & Caitlin --------------------------------------------------------------
    async def test_cynthia_caitlin_supporter_back_no_discard(self):
        t = self.table()
        t.put(BOSS, P1, 'discard')
        t.put(CC, P1, 'discard')
        t.put(NEST, P1, 'discard')
        t.yes = False
        seen = self.spy(t)
        await t.play(t.put(CC, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ["Boss's Orders"])
        offered = [c for c in seen['calls'] if "Boss's Orders" in c[0]]
        self.assertTrue(offered)
        self.assertNotIn('Cynthia & Caitlin', offered[0][0])

    async def test_cynthia_caitlin_discard_draw_three_not_the_discarded(self):
        t = self.table()
        t.put(KORRINA, P1, 'discard')
        boss = t.put(BOSS, P1, 'hand')     # the card we choose to discard
        t.yes = True

        def take(cards, count):
            names = t.names(cards)
            boss_pick = [c for c in cards if c is boss]
            if boss_pick:
                return boss_pick
            return cards[:count]
        seen = self.spy(t, take)
        await t.play(t.put(CC, P1, 'hand'))
        hand = self.hand_names(t)
        # Korrina back, Boss discarded, 3 cards drawn
        self.assertIn('Korrina', hand)
        self.assertNotIn("Boss's Orders", hand)
        self.assertEqual(len(hand), 4)
        self.assertIn(boss, t.zone(P1, 'discard'))

    async def test_cynthia_caitlin_needs_a_supporter(self):
        t = self.table()
        t.put(CC, P1, 'discard')
        card = t.put(CC, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Korrina ------------------------------------------------------------------------
    async def test_korrina_fighting_pokemon_and_item(self):
        t = self.table()
        t.deck(P1, [self.filler, LUCARIO, NEST, BOSS, ARTAZON, FLOAT])
        seen = self.spy(t)
        await t.play(t.put(KORRINA, P1, 'hand'))
        hand = self.hand_names(t)
        self.assertEqual(len(hand), 2)
        self.assertIn('Lucario', hand)
        other = [n for n in hand if n != 'Lucario'][0]
        self.assertIn(other, {'Nest Ball', 'Float Stone', 'Pokégear 3.0'})   # an Item

    # --- Tarragon -----------------------------------------------------------------------
    async def test_tarragon_up_to_four_fighting_pokemon_and_basic_fighting(self):
        t = self.table()
        for spec in (LUCARIO, MAKUHITA, RIOLU, self.filler, STRONG, t.basic_energy(F),
                     t.basic_energy(F), t.basic_energy(D)):
            t.put(spec, P1, 'discard')
        seen = self.spy(t)
        await t.play(t.put(TARRAGON, P1, 'hand'))
        names, count, _ = seen['calls'][0]
        self.assertEqual(count, 4)
        self.assertEqual(len(names), 5)
        for bad in ('Strong Energy', def_for(self.filler.guid).display_name):
            self.assertNotIn(bad, names)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)


if __name__ == "__main__":
    unittest.main()
