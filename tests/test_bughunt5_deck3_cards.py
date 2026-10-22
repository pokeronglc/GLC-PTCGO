"""Bug hunt round 5, deck 3 (Psychic): Phantump BKP 64, Trevenant XY 55,
Mismagius UNB 78, Golett CEC 89, Golurk CRE 66, Mewtwo CRZ 59,
Necrozma UNM 101, Brigette BKT 134, Gloria BRS 141, Boost Shake EVS 142,
Jubilife Village ASR 148 -- checked against their printed text, including
the should-NOT-work cases."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

P, W = PokemonTypes.PSYCHIC, PokemonTypes.WATER
PHANTUMP, TREVENANT = 'XY9.Phantump_64', 'XY1.Trevenant_55'
MISMAGIUS, GOLETT, GOLURK = 'SM10.Mismagius_78', 'SM12.Golett_89', 'SWSH6.Golurk_66'
MEWTWO, NECROZMA = 'CZ.Mewtwo_59', 'SM11.Necrozma_101'
BRIGETTE, GLORIA = 'XY8.Brigette_134', 'SWSH9.Gloria_141'
BOOST, JUBILIFE = 'SWSH7.BoostShake_142', 'SWSH10.JubilifeVillage_148'
HARD_CHARM = 'XY1.HardCharm_119'
RAINBOW = 'SM7.RainbowEnergy_151'


class Bughunt5Deck3(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def top_name(self, mon):
        return self.name(mon)

    async def test_set_codes(self):
        for path, code in ((PHANTUMP, 'XY9'), (TREVENANT, 'XY1'), (MISMAGIUS, 'SM10'),
                           (GOLETT, 'SM12'), (GOLURK, 'SWSH6'), (MEWTWO, 'CZ'),
                           (NECROZMA, 'SM11'), (BRIGETTE, 'XY8'), (GLORIA, 'SWSH9'),
                           (BOOST, 'SWSH7'), (JUBILIFE, 'SWSH10')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Phantump (BKP 64): Ascension -------------------------------------
    async def test_ascension_evolves_into_trevenant(self):
        t = self.table()
        ph = t.put(PHANTUMP, P1, 'active')
        t.energy(ph, W)
        tre = t.deck(P1, [TREVENANT])[0]
        await t.attack(ph, 'Ascension')
        self.assertIs(ph.parent, tre)
        self.assertIs(t.active(P1), tre)
        self.assertNotIn(tre, t.zone(P1, 'deck'))

    async def test_ascension_ignores_unrelated_evolutions(self):
        t = self.table()
        ph = t.put(PHANTUMP, P1, 'active')
        t.energy(ph, W)
        gol = t.deck(P1, [GOLURK])[0]
        await t.attack(ph, 'Ascension')
        self.assertIs(t.active(P1), ph)
        self.assertIn(gol, t.zone(P1, 'deck'))

    # --- Trevenant (XY 55): Forest's Curse / Tree Slam --------------------
    async def test_forests_curse_locks_opponent_items_while_active(self):
        t = self.table()
        t.put(TREVENANT, P1, 'active')
        mine = t.put(self.item, P1, 'hand')
        self.assertTrue(t.can(mine, 'UseTrainerCard'))     # my own Items are fine
        t.next_turn()
        theirs = t.put(self.item, P2, 'hand')
        self.assertFalse(t.can(theirs, 'UseTrainerCard', pid=P2))

    async def test_forests_curse_not_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(TREVENANT, P1, 'bench')
        t.next_turn()
        theirs = t.put(self.item, P2, 'hand')
        self.assertTrue(t.can(theirs, 'UseTrainerCard', pid=P2))

    async def test_tree_slam_hits_active_and_two_benched(self):
        t = self.table()
        tre = t.put(TREVENANT, P1, 'active')
        t.energy(tre, P, 3)
        b1, b2, b3 = (t.put(self.filler, P2, 'bench') for _ in range(3))
        for b in (b1, b2, b3):
            self.big(b)
        t.picks = lambda cards, n, pr, d: [c for c in cards if c in (b1, b2)][:n] or cards[:n]
        t.pokemon = lambda cands, pr: b1 if b1 in cands and t.damage(b1) == 0 else b2
        await t.attack(tre, 'Tree Slam')
        self.assertEqual((400 - t.hp(self.opp)), 60)
        self.assertEqual(sorted(400 - t.hp(b) for b in (b1, b2, b3)), [0, 20, 20])

    # --- Mismagius (UNB 78): Mysterious Message / Hypnoblast --------------
    async def test_mysterious_message_draws_to_seven_then_knocked_out(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mis = t.put(MISMAGIUS, P1, 'bench')
        for _ in range(3):
            t.put(self.item, P1, 'hand')
        await t.use(mis, 'Mysterious Message')
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        self.assertNotIn(mis, t.zone(P1, 'bench'))
        self.assertIn(mis, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)     # opponent takes a Prize

    async def test_mysterious_message_with_seven_cards_no_knockout(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mis = t.put(MISMAGIUS, P1, 'bench')
        for _ in range(7):
            t.put(self.item, P1, 'hand')
        offer = t.ability_offer(mis, 'Mysterious Message')
        if offer is not None:
            await t.do(offer)
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        self.assertIn(mis, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 6)

    async def test_hypnoblast_asleep(self):
        t = self.table()
        mis = t.put(MISMAGIUS, P1, 'active')
        t.energy(mis, P, 3)
        await t.attack(mis, 'Hypnoblast')
        self.assertEqual((400 - t.hp(self.opp)), 70)
        self.assertIn(ASLEEP, t.conditions(self.opp))

    # --- Golett (CEC 89): Return ------------------------------------------
    async def test_return_draws_up_to_five(self):
        t = self.table()
        g = t.put(GOLETT, P1, 'active')
        t.energy(g, P)
        t.put(self.item, P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.attack(g, 'Return')
        self.assertEqual((400 - t.hp(self.opp)), 10)
        self.assertEqual(len(t.zone(P1, 'hand')), 5)

    # FIXED (was BUG): Return's "You may draw" is forced; bw_legacy_attack never asks.
    async def test_return_may_decline(self):
        t = self.table()
        g = t.put(GOLETT, P1, 'active')
        t.energy(g, P)
        t.put(self.item, P1, 'hand')
        t.yes = False
        await t.attack(g, 'Return')
        self.assertEqual((400 - t.hp(self.opp)), 10)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_return_full_hand_draws_nothing(self):
        t = self.table()
        g = t.put(GOLETT, P1, 'active')
        t.energy(g, P)
        for _ in range(6):
            t.put(self.item, P1, 'hand')
        await t.attack(g, 'Return')
        self.assertEqual(len(t.zone(P1, 'hand')), 6)

    # --- Golurk (CRE 66): Reinforced Punch / Megaton Fall -----------------
    async def test_reinforced_punch_with_tool(self):
        t = self.table()
        g = t.put(GOLURK, P1, 'active')
        t.energy(g, P, 3)
        t.attach(HARD_CHARM, g)
        await t.attack(g, 'Reinforced Punch')
        self.assertEqual((400 - t.hp(self.opp)), 150)

    async def test_reinforced_punch_without_tool(self):
        t = self.table()
        g = t.put(GOLURK, P1, 'active')
        t.energy(g, P, 3)
        other = t.put(self.filler, P1, 'bench')
        t.attach(HARD_CHARM, other)           # a Tool on another Pokemon doesn't count
        await t.attack(g, 'Reinforced Punch')
        self.assertEqual((400 - t.hp(self.opp)), 60)

    async def test_megaton_fall_recoil(self):
        t = self.table()
        g = t.put(GOLURK, P1, 'active')
        t.energy(g, P, 4)
        await t.attack(g, 'Megaton Fall')
        self.assertEqual((400 - t.hp(self.opp)), 190)
        self.assertEqual(t.damage(g), 30)

    # --- Mewtwo (CRZ 59): Psypump / Limit Break ---------------------------
    async def test_psypump_attaches_two_psychic_to_benched(self):
        t = self.table()
        m = t.put(MEWTWO, P1, 'active')
        t.energy(m, W)
        bench = t.put(self.filler, P1, 'bench')
        ps = [t.put(t.basic_energy(P), P1, 'discard') for _ in range(3)]
        water = t.put(t.basic_energy(W), P1, 'discard')
        t.pokemon = lambda cands, pr: bench
        await t.attack(m, 'Psypump')
        on_bench = [c for c in t.attached(bench)]
        self.assertEqual(len(on_bench), 2)
        self.assertTrue(all(c in ps for c in on_bench))
        self.assertIn(water, t.zone(P1, 'discard'))
        self.assertEqual((400 - t.hp(self.opp)), 0)

    async def test_psypump_ignores_other_energy(self):
        t = self.table()
        m = t.put(MEWTWO, P1, 'active')
        t.energy(m, W)
        water = t.put(t.basic_energy(W), P1, 'discard')
        t.picks = lambda cards, n, pr, d: list(cards)
        await t.attack(m, 'Psypump')
        self.assertIn(water, t.zone(P1, 'discard'))
        self.assertEqual(len(t.attached(m)), 1)

    async def _limit_break(self, opp_prizes):
        t = self.table()
        m = t.put(MEWTWO, P1, 'active')
        t.energy(m, P, 3)
        t.set_prizes(P2, opp_prizes)
        t.set_prizes(P1, 6)
        await t.attack(m, 'Limit Break')
        return (400 - t.hp(self.opp))

    async def test_limit_break_three_prizes_left(self):
        self.assertEqual(await self._limit_break(3), 180)

    async def test_limit_break_four_prizes_left(self):
        self.assertEqual(await self._limit_break(4), 90)

    async def test_limit_break_uses_opponents_prizes_not_mine(self):
        t = self.table()
        m = t.put(MEWTWO, P1, 'active')
        t.energy(m, P, 3)
        t.set_prizes(P1, 2)
        t.set_prizes(P2, 6)
        await t.attack(m, 'Limit Break')
        self.assertEqual((400 - t.hp(self.opp)), 90)

    # --- Necrozma (UNM 101): Barrier Attack / Special Laser ---------------
    async def test_barrier_attack_reduces_next_turn_damage(self):
        t = self.table()
        n = t.put(NECROZMA, P1, 'active')
        self.big(n)
        t.energy(n, W, 2)
        await t.attack(n, 'Barrier Attack')
        self.assertEqual((400 - t.hp(self.opp)), 30)
        t.next_turn()
        t.energy(self.opp, W, 3)
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        self.assertEqual(400 - t.hp(n), 80 - 30)

    async def test_barrier_attack_expires_after_opponents_turn(self):
        t = self.table()
        n = t.put(NECROZMA, P1, 'active')
        self.big(n)
        t.energy(n, W, 2)
        await t.attack(n, 'Barrier Attack')
        t.next_turn()
        t.next_turn()
        t.next_turn()
        t.energy(self.opp, W, 3)
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        self.assertEqual(400 - t.hp(n), 80)

    async def test_special_laser_with_special_energy(self):
        t = self.table()
        n = t.put(NECROZMA, P1, 'active')
        t.energy(n, P, 2)
        t.attach(RAINBOW, n)
        await t.attack(n, 'Special Laser')
        self.assertEqual((400 - t.hp(self.opp)), 160)

    async def test_special_laser_basic_only(self):
        t = self.table()
        n = t.put(NECROZMA, P1, 'active')
        t.energy(n, P, 3)
        await t.attack(n, 'Special Laser')
        self.assertEqual((400 - t.hp(self.opp)), 100)

    # --- Brigette (BKT 134) -----------------------------------------------
    async def test_brigette_benches_three_basics(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        basics = t.deck(P1, [GOLETT, PHANTUMP, MEWTWO, NECROZMA])
        t.deck(P1, [GOLURK])
        card = t.put(BRIGETTE, P1, 'hand')
        await t.play(card)
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 3)
        self.assertTrue(all(b in basics for b in bench))

    async def test_brigette_respects_bench_space_and_skips_evolutions(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        for _ in range(4):
            t.put(self.filler, P1, 'bench')
        t.deck(P1, [GOLURK, TREVENANT, GOLETT, PHANTUMP])
        card = t.put(BRIGETTE, P1, 'hand')
        await t.play(card)
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 5)
        self.assertEqual(sum(self.name(b) in ('Golett', 'Phantump') for b in bench), 1)
        self.assertFalse(any(self.name(b) in ('Golurk', 'Trevenant') for b in bench))

    # --- Gloria (BRS 141) -------------------------------------------------
    async def test_gloria_benches_up_to_three_basics(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.deck(P1, [GOLETT, PHANTUMP, MEWTWO, NECROZMA, GOLURK])
        card = t.put(GLORIA, P1, 'hand')
        await t.play(card)
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 3)
        self.assertFalse(any(self.name(b) == 'Golurk' for b in bench))

    async def test_gloria_never_offers_evolutions(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.deck(P1, [GOLURK, TREVENANT])
        card = t.put(GLORIA, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertEqual(t.zone(P1, 'bench'), [])

    # --- Boost Shake (EVS 142) --------------------------------------------
    async def test_boost_shake_evolves_and_ends_turn(self):
        t = self.table()
        g = t.put(GOLETT, P1, 'active')
        gol = t.deck(P1, [GOLURK])[0]
        card = t.put(BOOST, P1, 'hand')
        ended = await t.play(card)
        self.assertIs(g.parent, gol)
        self.assertIs(t.active(P1), gol)
        self.assertTrue(ended, 'Boost Shake ends the turn')

    async def test_boost_shake_allowed_on_pokemon_put_in_play_this_turn(self):
        # Printed: "You can use this card during your first turn or on a
        # Pokemon that was put into play this turn."
        t = self.table()
        g = t.put(GOLETT, P1, 'active')
        t.state.entered_play_turn[g.entity_id] = t.state.turn_number
        gol = t.deck(P1, [GOLURK])[0]
        card = t.put(BOOST, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertIs(t.active(P1), gol)

    async def test_boost_shake_only_finds_matching_evolution(self):
        t = self.table()
        g = t.put(GOLETT, P1, 'active')
        tre = t.deck(P1, [TREVENANT])[0]
        card = t.put(BOOST, P1, 'hand')
        t.picks = lambda cards, n, pr, d: list(cards)[:n]
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertIs(t.active(P1), g)
        self.assertIn(tre, t.zone(P1, 'deck'))

    # --- Jubilife Village (ASR 148) ---------------------------------------
    def _stadium_entry(self, t, stadium, pid):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_jubilife_shuffles_hand_draws_five_ends_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        st = t.stadium(JUBILIFE, P2)          # either player's Stadium works
        for _ in range(2):
            t.put(self.item, P1, 'hand')
        mark = t.put(GOLURK, P1, 'hand')
        ended = await t.do(self._stadium_entry(t, st, P1))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 5)
        self.assertTrue(ended, 'Jubilife Village ends the turn')
        self.assertTrue(mark in hand or mark in t.zone(P1, 'deck'))

    async def test_jubilife_usable_by_opponent_too_once_per_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        st = t.stadium(JUBILIFE, P1)
        t.next_turn()
        entry = self._stadium_entry(t, st, P2)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertEqual(len(t.zone(P2, 'hand')), 5)
        self.assertIsNone(self._stadium_entry(t, st, P2))   # once per turn
        t.next_turn()
        self.assertIsNotNone(self._stadium_entry(t, st, P1))


if __name__ == '__main__':
    unittest.main()
