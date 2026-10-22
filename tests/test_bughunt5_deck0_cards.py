"""Bug hunt round 5, deck 0 (Grass): Wurmple LOT 24, Cherubi BRS 12,
Wo-Chien SSP 15, Shaymin SLG 7, Bug Catching Set TWM 143."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

G, W, D, P = PokemonTypes.GRASS, PokemonTypes.WATER, PokemonTypes.DARKNESS, PokemonTypes.PSYCHIC
WURMPLE, CHERUBI = 'SM8.Wurmple_24', 'SWSH9.Cherubi_12'
WOCHIEN, SHAYMIN = 'SV08.WoChien_15', 'SL.Shaymin_7'
BUGSET = 'SV06.BugCatchingSet_143'
GROWING = 'ME3.GrowingGrassEnergy_86'     # Special Energy (provides Grass)
BAGON = 'SM7.Bagon_104'                   # non-Grass Pokémon
SABLEYE = 'SV2.Sableye_136'               # Unseen Claw 20 for [D]
HAUNTER = 'SM10.Haunter_69'               # Sinister Fog: Poison + 1 counter on each opp Benched


class Deck0Cards5(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        mon._start_hp = mon.get_attribute(AttrID.HP, 0)
        return mon

    @staticmethod
    def took(t, mon):
        return mon._start_hp - t.hp(mon)

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    def clear_deck(self, t, pid, keep):
        area = t.board.find_player_area(pid, 'deck')
        for c in list(area.children)[keep:]:
            area.remove_child(c)

    # --- Wurmple: Poison Sting ---------------------------------------------
    async def test_poison_sting_poisons(self):
        t = self.table()
        w = t.put(WURMPLE, P1, 'active')
        t.energy(w, G)
        await t.attack(w, 'Poison Sting')
        self.assertIn(POISONED, t.conditions(self.opp))
        self.assertEqual(self.took(t, self.opp), 0)

    # --- Cherubi: Lively Fruit ---------------------------------------------
    async def test_lively_fruit_blocks_poison_but_not_damage(self):
        t = Table(self)
        ch = self.neutral(t.put(CHERUBI, P1, 'active'))
        t.put(self.filler, P1, 'bench')
        opp = self.neutral(t.put(HAUNTER, P2, 'active'), 400)
        t.energy(opp, P)
        t.next_turn()
        await t.attack(opp, 'Sinister Fog', pid=P2)
        self.assertNotIn(POISONED, t.conditions(ch))

    async def test_lively_fruit_damage_still_done(self):
        t = Table(self)
        ch = self.neutral(t.put(CHERUBI, P1, 'active'))
        opp = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(opp, D)
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertEqual(self.took(t, ch), 20)

    async def test_lively_fruit_on_bench_blocks_damage_counters(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        ch = self.neutral(t.put(CHERUBI, P1, 'bench'))
        other = self.neutral(t.put(self.filler, P1, 'bench'))
        opp = self.neutral(t.put(HAUNTER, P2, 'active'), 400)
        t.energy(opp, P)
        t.next_turn()
        await t.attack(opp, 'Sinister Fog', pid=P2)
        self.assertEqual(self.took(t, ch), 0)            # counters are an effect
        self.assertEqual(self.took(t, other), 10)        # unprotected neighbour hit

    async def test_lively_fruit_does_not_protect_from_own_side(self):
        # "from your opponent's Pokémon": the opponent's Cherubi gives my
        # Wurmple no protection, and my Wurmple's poison sticks to a
        # non-Cherubi target.
        t = Table(self)
        w = t.put(WURMPLE, P1, 'active')
        t.energy(w, G)
        t.put(CHERUBI, P2, 'bench')
        opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        await t.attack(w, 'Poison Sting')
        self.assertIn(POISONED, t.conditions(opp))

    # --- Wo-Chien: Hazardous Greed / Entangling Whip -----------------------
    def wochien_board(self, deck_size):
        t = self.table()
        wc = t.put(WOCHIEN, P1, 'active')
        t.energy(wc, G, 3)
        b1 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        b2 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        self.clear_deck(t, P1, deck_size)
        return t, wc, b1, b2

    async def test_hazardous_greed_three_cards_hits_two_benched(self):
        t, wc, b1, b2 = self.wochien_board(3)
        await t.attack(wc, 'Hazardous Greed')
        self.assertEqual(self.took(t, self.opp), 20)
        self.assertEqual((self.took(t, b1), self.took(t, b2)), (120, 120))

    async def test_hazardous_greed_four_cards_no_bench_damage(self):
        t, wc, b1, b2 = self.wochien_board(4)
        await t.attack(wc, 'Hazardous Greed')
        self.assertEqual(self.took(t, self.opp), 20)
        self.assertEqual((self.took(t, b1), self.took(t, b2)), (0, 0))

    async def test_entangling_whip_discards_top_three(self):
        t = self.table()
        wc = t.put(WOCHIEN, P1, 'active')
        t.energy(wc, G, 3)
        top = t.deck(P1, [BAGON, CHERUBI, WURMPLE])
        fourth = t.zone(P1, 'deck')[-4]
        before = len(t.zone(P1, 'deck'))
        await t.attack(wc, 'Entangling Whip')
        self.assertEqual(self.took(t, self.opp), 130)
        self.assertEqual(len(t.zone(P1, 'deck')), before - 3)
        for c in top:
            self.assertIn(c, t.zone(P1, 'discard'))
        self.assertIn(fourth, t.zone(P1, 'deck'))

    # --- Shaymin: Flippity Flap / Rally Back --------------------------------
    async def test_flippity_flap_shuffles_hand_and_draws_six(self):
        t = self.table()
        s = t.put(SHAYMIN, P1, 'active')
        t.energy(s, G)
        old = [t.put(BAGON, P1, 'hand') for _ in range(3)]
        await t.attack(s, 'Flippity Flap')
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        deck = t.zone(P1, 'deck')
        self.assertEqual(sum(1 for c in old if c in deck)
                         + sum(1 for c in old if c in t.zone(P1, 'hand')), 3)

    async def test_flippity_flap_empty_hand_still_draws_six(self):
        t = self.table()
        s = t.put(SHAYMIN, P1, 'active')
        t.energy(s, G)
        await t.attack(s, 'Flippity Flap')
        self.assertEqual(len(t.zone(P1, 'hand')), 6)

    async def test_rally_back_after_attack_knockout(self):
        t = Table(self)
        opp = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(opp, D)
        victim = self.neutral(t.put(self.filler, P1, 'active', hp=10))
        s = self.neutral(t.put(SHAYMIN, P1, 'bench'))
        t.energy(s, G, 2)
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertIn(victim, t.zone(P1, 'discard'))
        self.assertIs(t.active(P1), s)
        t.next_turn()
        await t.attack(s, 'Rally Back')
        self.assertEqual(self.took(t, opp), 120)

    async def test_rally_back_no_knockout(self):
        t = self.table()
        s = t.put(SHAYMIN, P1, 'active')
        t.energy(s, G, 2)
        await t.attack(s, 'Rally Back')
        self.assertEqual(self.took(t, self.opp), 30)

    async def test_rally_back_not_for_damage_counter_knockout(self):
        # Haunter's Sinister Fog places damage counters (an effect, not
        # damage): a Benched Pokémon KO'd that way does not power Rally Back.
        t = Table(self)
        opp = self.neutral(t.put(HAUNTER, P2, 'active'), 400)
        t.energy(opp, P)
        s = self.neutral(t.put(SHAYMIN, P1, 'active'))
        t.energy(s, G, 2)
        victim = self.neutral(t.put(self.filler, P1, 'bench', hp=10))
        t.next_turn()
        await t.attack(opp, 'Sinister Fog', pid=P2)
        self.assertIn(victim, t.zone(P1, 'discard'))
        t.next_turn()
        s.set_attribute(AttrID.SPECIAL_CONDITIONS, [])
        await t.attack(s, 'Rally Back')
        self.assertEqual(self.took(t, opp), 30)

    # --- Bug Catching Set ---------------------------------------------------
    async def test_bug_catching_set_grass_pokemon_and_basic_grass_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        good = t.deck(P1, [CHERUBI, t.basic_energy(G)])
        bad = t.deck(P1, [BAGON, t.basic_energy(W), GROWING])
        deep = t.deck(P1, [WURMPLE], top=False)[0]   # bottom: outside the top 7
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'], seen['count'], seen['display'] = list(cards), count, list(display or [])
            return [c for c in cards if c in good]
        t.picks = picks
        card = t.put(BUGSET, P1, 'hand')
        await t.play(card)
        self.assertEqual(seen['count'], 2)
        self.assertEqual(len(seen['display']), 7)
        for b in bad + [deep]:
            self.assertNotIn(b, seen['cards'])
        hand = t.zone(P1, 'hand')
        for g in good:
            self.assertIn(g, hand)
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_bug_catching_set_whiff_ok(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        before = len(t.zone(P1, 'deck'))
        card = t.put(BUGSET, P1, 'hand')
        await t.play(card)
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), before)
        self.assertIn(card, t.zone(P1, 'discard'))


if __name__ == '__main__':
    unittest.main()
