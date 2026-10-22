"""Bug hunt round 2, deck 1 (Colorless): Supporters, Items and the Stadium,
through the real play-trainer executor (so play conditions apply)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W = PokemonTypes.WATER
TEDDIURSA, URSARING = 'SWSH3.Teddiursa_138', 'SWSH7.Ursaring_127'
SABLEYE = 'SV2.Sableye_136'
GUZMA, N, ARTAZON, NEST = 'SM3.Guzma_115', 'XY10.N_105', 'SV2.Artazon_171', 'SV1.NestBall_181'
CHERYL, DELINQUENT, BB = 'SWSH5.Cheryl_123', 'XY9.Delinquent_98', 'SM12.BellelbaBrycenMan_186'
PEONIA, SURGE, MALLOW = 'SWSH6.Peonia_149', 'SM10.LtSurgesStrategy_178', 'SM2.Mallow_127'
HAPU, TURO, SYCAMORE = 'SM11.Hapu_200', 'SV4.ProfessorTurosScenario_171', 'XY9.ProfessorSycamore_107'
XEROSIC, GRUNT = 'SV065.XerosicsMachinations_64', 'XY1.TeamFlareGrunt_129'
MAX_POTION, PICNIC, GALAR_MINE = 'SM2.MaxPotion_128', 'SV1.PicnicBasket_184', 'SWSH2.GalarMine_160'
COMPRESSOR = 'XY4.BattleCompressorTeamFlareGear_92'


def c_in(cards, wanted):
    return any(c in wanted for c in cards)


def name(card):
    return def_for(card.archetype_id).display_name


class Deck1Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Cheryl ------------------------------------------------------------
    async def test_cheryl_heals_damaged_evolutions_and_discards_their_energy(self):
        t = self.table()
        ring = t.put(URSARING, P1, 'bench', hp=60)          # damaged Evolution
        e1 = t.energy(ring, W)
        full = t.put(URSARING, P1, 'bench')                 # undamaged Evolution
        e2 = t.energy(full, W)
        basic = t.put(TEDDIURSA, P1, 'bench', hp=30)        # damaged Basic
        await t.play(t.put(CHERYL, P1, 'hand'))
        self.assertEqual(t.damage(ring), 0)
        self.assertIn(e1, t.zone(P1, 'discard'))
        self.assertIn(e2, t.board.attached_energies(full))
        self.assertEqual(t.damage(basic), 40)

    async def test_cheryl_needs_a_damaged_evolution(self):
        t = self.table()
        t.put(URSARING, P1, 'bench')
        t.put(TEDDIURSA, P1, 'bench', hp=30)
        self.assertFalse(t.can(t.put(CHERYL, P1, 'hand'), 'UseTrainerCard'))

    # --- Delinquent -----------------------------------------------------------
    async def test_delinquent_any_stadium_then_opponent_discards_three(self):
        for owner in (P1, P2):
            t = self.table()
            t.stadium(ARTAZON, owner)
            for _ in range(5):
                t.put(self.item, P2, 'hand')
            await t.play(t.put(DELINQUENT, P1, 'hand'))
            with self.subTest(owner=owner):
                self.assertFalse(t.board.find_global_area('activeStadium').children)
                self.assertEqual(len(t.zone(P2, 'hand')), 2)

    async def test_delinquent_needs_a_stadium(self):
        t = self.table()
        t.put(self.item, P2, 'hand')
        self.assertFalse(t.can(t.put(DELINQUENT, P1, 'hand'), 'UseTrainerCard'))

    # --- Bellelba & Brycen-Man -------------------------------------------------
    async def test_bb_man_mills_three_each(self):
        t = self.table()
        for _ in range(4):
            t.put(self.filler, P1, 'bench'); t.put(self.filler, P2, 'bench')
        t.yes = False
        await t.play(t.put(BB, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'deck')), 27)
        self.assertEqual(len(t.zone(P2, 'deck')), 27)
        self.assertEqual(len(t.zone(P1, 'bench')), 4)      # no extra cost paid: Benches untouched
        self.assertEqual(len(t.zone(P2, 'bench')), 4)

    async def test_bb_man_extra_trims_benches_to_three(self):
        t = self.table()
        for _ in range(5):
            t.put(self.filler, P1, 'bench'); t.put(self.filler, P2, 'bench')
        for _ in range(3):
            t.put(self.item, P1, 'hand')
        t.yes = True
        await t.play(t.put(BB, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'bench')), 3)
        self.assertEqual(len(t.zone(P2, 'bench')), 3)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Peonia ------------------------------------------------------------------
    async def test_peonia_swaps_up_to_three_prizes(self):
        t = self.table()
        prizes = list(t.zone(P1, 'prizes'))
        hand = [t.put(GUZMA, P1, 'hand') for _ in range(3)]
        t.picks = lambda cards, count, prompt, display: (
            [c for c in cards if c in hand][:count] if 'Prize' in prompt and c_in(cards, hand) else cards[:count])
        await t.play(t.put(PEONIA, P1, 'hand'))
        now = t.zone(P1, 'prizes')
        self.assertEqual(len(now), 6)
        for g in hand:
            self.assertIn(g, now)
        self.assertEqual(len([c for c in t.zone(P1, 'hand') if c in prizes]), 3)

    async def test_peonia_needs_prizes(self):
        t = self.table()
        t.set_prizes(P1, 0)
        self.assertFalse(t.can(t.put(PEONIA, P1, 'hand'), 'UseTrainerCard'))

    # --- Lt. Surge's Strategy ------------------------------------------------------
    async def test_lt_surge_only_when_behind(self):
        for mine, theirs, ok in ((6, 6, False), (5, 6, False), (6, 5, True)):
            t = self.table()
            t.set_prizes(P1, mine); t.set_prizes(P2, theirs)
            with self.subTest(mine=mine, theirs=theirs):
                self.assertEqual(t.can(t.put(SURGE, P1, 'hand'), 'UseTrainerCard'), ok)

    async def test_lt_surge_three_supporters_including_itself(self):
        t = self.table()
        t.set_prizes(P2, 5)
        t.stadium(ARTAZON, P2)
        await t.play(t.put(SURGE, P1, 'hand'))
        await t.play(t.put(HAPU, P1, 'hand'))
        third = t.put(DELINQUENT, P1, 'hand')
        self.assertTrue(t.can(third, 'UseTrainerCard'))
        await t.play(third)
        self.assertFalse(t.can(t.put(HAPU, P1, 'hand'), 'UseTrainerCard'))

    async def test_lt_surge_does_not_carry_to_next_turn(self):
        t = self.table()
        t.set_prizes(P2, 5)
        await t.play(t.put(SURGE, P1, 'hand'))
        t.next_turn(); t.next_turn()
        await t.play(t.put(HAPU, P1, 'hand'))
        self.assertFalse(t.can(t.put(HAPU, P1, 'hand'), 'UseTrainerCard'))

    # --- Mallow ---------------------------------------------------------------------
    async def test_mallow_two_cards_on_top(self):
        t = self.table()
        g, n = t.deck(P1, [GUZMA, N], top=False)    # buried at the bottom
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in (g, n)] or cards[:count]
        await t.play(t.put(MALLOW, P1, 'hand'))
        deck = t.zone(P1, 'deck')
        self.assertEqual({id(c) for c in deck[-2:]}, {id(g), id(n)})
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Hapu --------------------------------------------------------------------------
    async def test_hapu_two_of_top_six_rest_discarded(self):
        t = self.table()
        t.deck(P1, [GUZMA, N, NEST, ARTAZON, SABLEYE, TEDDIURSA])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', (len(cards), count)), cards[:count])[1]
        await t.play(t.put(HAPU, P1, 'hand'))
        self.assertEqual(seen['c'], (6, 2))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 4 + 1)   # 4 + Hapu itself
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Professor Turo's Scenario ----------------------------------------------------
    async def test_turo_returns_pokemon_discards_attachments(self):
        t = self.table()
        bench = t.put(SABLEYE, P1, 'bench', hp=20)
        energy = t.energy(bench, W)
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.play(t.put(TURO, P1, 'hand'))
        self.assertIn(bench, t.zone(P1, 'hand'))
        self.assertIn(energy, t.zone(P1, 'discard'))
        self.assertNotIn(energy, t.zone(P1, 'hand'))

    async def test_turo_evolved_pokemon_whole_stack_to_hand(self):
        t = self.table()
        ted = t.put(TEDDIURSA, P1, 'bench')
        ring = t.put(URSARING, P1, 'hand')
        await t._run(lambda: t.session.perform_evolution(P1, ring, ted))
        top = next(p for p in t.board.pokemon_in_play(P1) if name(p) == 'Ursaring')
        energy = t.energy(top, W)
        t.pokemon = lambda c, p: top if top in c else c[0]
        await t.play(t.put(TURO, P1, 'hand'))
        self.assertEqual(sorted(self.hand_names(t)), ['Teddiursa', 'Ursaring'])
        self.assertIn(energy, t.zone(P1, 'discard'))

    async def test_turo_active_pokemon_is_replaced(self):
        t = self.table()
        bench = t.put(SABLEYE, P1, 'bench')
        t.pokemon = lambda c, p: self.me if self.me in c else c[0]
        await t.play(t.put(TURO, P1, 'hand'))
        self.assertIn(self.me, t.zone(P1, 'hand'))
        self.assertIs(t.active(P1), bench)

    # --- Professor Sycamore -------------------------------------------------------------
    async def test_sycamore_discard_hand_draw_seven(self):
        t = self.table()
        old = [t.put(GUZMA, P1, 'hand') for _ in range(3)]
        await t.play(t.put(SYCAMORE, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        for c in old:
            self.assertIn(c, t.zone(P1, 'discard'))

    # --- Xerosic's Machinations -------------------------------------------------------
    async def test_xerosic_opponent_down_to_three(self):
        t = self.table()
        for _ in range(6):
            t.put(self.item, P2, 'hand')
        t.put(self.item, P1, 'hand')
        await t.play(t.put(XEROSIC, P1, 'hand'))
        self.assertEqual(len(t.zone(P2, 'hand')), 3)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_xerosic_three_or_fewer_not_playable(self):
        t = self.table()
        for _ in range(3):
            t.put(self.item, P2, 'hand')
        self.assertFalse(t.can(t.put(XEROSIC, P1, 'hand'), 'UseTrainerCard'))

    # --- Team Flare Grunt ------------------------------------------------------------
    async def test_grunt_discards_energy_from_opponent_active(self):
        t = self.table()
        e = t.energy(self.opp, W)
        mine = t.energy(self.me, W)
        await t.play(t.put(GRUNT, P1, 'hand'))
        self.assertIn(e, t.zone(P2, 'discard'))
        self.assertIn(mine, t.board.attached_energies(self.me))

    async def test_grunt_ignores_benched_energy(self):
        t = self.table()
        bench = t.put(self.filler, P2, 'bench')
        t.energy(bench, W)
        card = t.put(GRUNT, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Max Potion --------------------------------------------------------------------
    async def test_max_potion_heals_all_and_discards_energy(self):
        t = self.table()
        hurt = t.put(SABLEYE, P1, 'bench', hp=10)
        energies = t.energy(hurt, W, 2)
        t.pokemon = lambda c, p: hurt if hurt in c else c[0]
        await t.play(t.put(MAX_POTION, P1, 'hand'))
        self.assertEqual(t.damage(hurt), 0)
        self.assertEqual(t.board.attached_energies(hurt), [])
        for e in energies:
            self.assertIn(e, t.zone(P1, 'discard'))

    async def test_max_potion_needs_damaged_pokemon(self):
        t = self.table()
        t.put(self.filler, P2, 'bench', hp=10)       # the opponent's damage doesn't count
        self.assertFalse(t.can(t.put(MAX_POTION, P1, 'hand'), 'UseTrainerCard'))

    # --- Picnic Basket -------------------------------------------------------------------
    async def test_picnic_basket_heals_30_from_each_pokemon_both_sides(self):
        t = self.table()
        mine = t.put(SABLEYE, P1, 'bench', hp=10)      # 60 damage
        theirs = t.put(SABLEYE, P2, 'bench', hp=50)    # 20 damage
        self.me.set_attribute(AttrID.HP, t.hp(self.me) - 40)
        await t.play(t.put(PICNIC, P1, 'hand'))
        self.assertEqual(t.damage(mine), 30)
        self.assertEqual(t.damage(theirs), 0)
        self.assertEqual(t.damage(self.me), 10)

    # --- Galar Mine ------------------------------------------------------------------------
    async def test_galar_mine_active_plus_two_both_sides_bench_unchanged(self):
        t = self.table()
        bench = t.put(SABLEYE, P1, 'bench')
        before = (t.retreat(self.me), t.retreat(self.opp), t.retreat(bench))
        t.stadium(GALAR_MINE, P2)
        self.assertEqual(t.retreat(self.me), before[0] + 2)
        self.assertEqual(t.retreat(self.opp), before[1] + 2)
        self.assertEqual(t.retreat(bench), before[2])

    # --- Battle Compressor -------------------------------------------------------------------
    async def test_battle_compressor_discards_up_to_three_from_deck(self):
        t = self.table()
        t.deck(P1, [GUZMA, N, NEST, ARTAZON])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['c'] = count
            return [c for c in cards if name(c) in ('Guzma', 'N', 'Artazon')]
        t.picks = picks
        await t.play(t.put(COMPRESSOR, P1, 'hand'))
        self.assertEqual(seen['c'], 3)
        self.assertEqual(sorted(t.names(t.zone(P1, 'discard'))),
                         ['Artazon', 'Battle Compressor Team Flare Gear', 'Guzma', 'N'])
        self.assertEqual(len(t.zone(P1, 'deck')), 31)

    async def test_battle_compressor_may_discard_nothing(self):
        t = self.table()
        t.picks = lambda cards, count, prompt, display: []
        await t.play(t.put(COMPRESSOR, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'deck')), 30)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_battle_compressor_empty_deck_not_playable(self):
        t = Table(self, filler_deck=0)
        t.put(self.filler, P1, 'active'); t.put(self.filler, P2, 'active')
        self.assertFalse(t.can(t.put(COMPRESSOR, P1, 'hand'), 'UseTrainerCard'))


if __name__ == "__main__":
    unittest.main()
