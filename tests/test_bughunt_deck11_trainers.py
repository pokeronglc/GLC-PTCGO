"""Bug hunt, deck 11 (Grass): Items and Stadiums, through the real executor."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

G = PokemonTypes.GRASS
TURTWIG, GROTLE, TORTERRA = 'SM5.Turtwig_6', 'SWSH9.Grotle_7', 'SWSH9.Torterra_8'
CHIMCHAR, MONFERNO, INFERNAPE = 'SWSH9.Chimchar_24', 'SWSH9.Monferno_25', 'SWSH9.Infernape_26'
REVITALIZER, NET_BALL = 'TwentiethAnn.Revitalizer_70', 'SM8.NetBall_187'
TURFFIELD, FOREST = 'SWSH2.TurffieldStadium_170', 'ME1.ForestofVitality_117'


class Deck11Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def hand(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Revitalizer ------------------------------------------------------
    async def test_revitalizer_two_grass_pokemon_from_discard(self):
        t = self.table()
        for spec in (TURTWIG, CHIMCHAR, GROTLE, TORTERRA):
            t.put(spec, P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        await t.play(t.put(REVITALIZER, P1, 'hand'))
        self.assertEqual(seen['count'], 2)
        self.assertNotIn('Chimchar', seen['names'])
        hand = self.hand(t)
        self.assertEqual(len(hand), 2)
        self.assertNotIn('Chimchar', hand)

    async def test_revitalizer_needs_grass_pokemon_in_discard(self):
        t = self.table()
        t.put(CHIMCHAR, P1, 'discard')
        t.put(t.basic_energy(G), P1, 'discard')
        card = t.put(REVITALIZER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.put(TURTWIG, P1, 'discard')   # one is enough to play it
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(self.hand(t), ['Turtwig'])

    # --- Net Ball ---------------------------------------------------------
    async def test_net_ball_basic_grass_pokemon_or_grass_energy(self):
        t = self.table()
        energy, = t.deck(P1, [t.basic_energy(G)])
        fire, = t.deck(P1, [t.basic_energy(PokemonTypes.FIRE)])
        t.deck(P1, [TURTWIG, GROTLE, CHIMCHAR])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'], seen['count'] = list(cards), count
            return cards[:count]
        t.picks = picks
        await t.play(t.put(NET_BALL, P1, 'hand'))
        names = t.names(seen['cards'])
        self.assertEqual(seen['count'], 1)
        self.assertIn('Turtwig', names)
        self.assertIn(energy, seen['cards'])
        self.assertNotIn(fire, seen['cards'])
        self.assertNotIn('Grotle', names)      # Stage 1
        self.assertNotIn('Chimchar', names)    # not Grass
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    # --- Turffield Stadium -------------------------------------------------
    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    def grass_table(self):
        # GLC is single-type: the Salvatore ruling hides a typed Stadium search
        # when the player's visible Pokemon (here the Colorless filler) can't
        # share its type, so put Grass Pokemon in play.
        t = Table(self)
        self.me = t.put(TURTWIG, P1, 'active')
        self.opp = t.put(TURTWIG, P2, 'active')
        return t

    async def test_turffield_hidden_for_a_visibly_non_grass_deck(self):
        t = self.table()                      # Colorless filler Actives
        stadium = t.stadium(TURFFIELD, P1)
        self.assertIsNone(self.stadium_action(t, stadium))

    async def test_turffield_evolution_grass_only_once_per_turn(self):
        t = self.grass_table()
        stadium = t.stadium(TURFFIELD, P1)
        t.deck(P1, [TURTWIG, INFERNAPE, GROTLE])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'] = t.names(cards)
            return cards[:count]
        t.picks = picks
        await t.do(self.stadium_action(t, stadium))
        self.assertEqual(seen['names'], ['Grotle'])
        self.assertEqual(self.hand(t), ['Grotle'])
        self.assertIsNone(self.stadium_action(t, stadium))

    async def test_turffield_usable_by_opponent_on_their_turn(self):
        t = self.grass_table()
        stadium = t.stadium(TURFFIELD, P1)
        t.deck(P2, [TORTERRA])
        t.next_turn()
        entry = self.stadium_action(t, stadium, P2)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertEqual(self.hand(t, P2), ['Torterra'])

    # --- Forest of Vitality -----------------------------------------------
    async def test_forest_grass_evolves_the_turn_it_is_played(self):
        t = self.table()
        t.stadium(FOREST, P2)                  # either player's Stadium
        turtwig = t.put(TURTWIG, P1, 'bench')
        t.state.entered_play_turn[turtwig.entity_id] = t.state.turn_number
        grotle = t.put(GROTLE, P1, 'hand')
        self.assertIn(turtwig.entity_id, t.targets(grotle, 'EvolvePokemonPlayAbility'))
        await t.play(grotle, targets=[turtwig.entity_id])
        self.assertIn(grotle, t.board.pokemon_in_play(P1))

    async def test_forest_needed_and_grass_only(self):
        t = self.table()
        turtwig = t.put(TURTWIG, P1, 'bench')
        chimchar = t.put(CHIMCHAR, P1, 'bench')
        for p in (turtwig, chimchar):
            t.state.entered_play_turn[p.entity_id] = t.state.turn_number
        grotle = t.put(GROTLE, P1, 'hand')
        monferno = t.put(MONFERNO, P1, 'hand')
        self.assertNotIn(turtwig.entity_id, t.targets(grotle, 'EvolvePokemonPlayAbility'))
        t.stadium(FOREST, P1)
        self.assertIn(turtwig.entity_id, t.targets(grotle, 'EvolvePokemonPlayAbility'))
        self.assertNotIn(chimchar.entity_id, t.targets(monferno, 'EvolvePokemonPlayAbility'))

    async def test_forest_not_on_first_turn(self):
        t = self.table()
        t.state.turn_number = 2
        t.stadium(FOREST, P1)
        turtwig = t.put(TURTWIG, P1, 'bench')
        t.state.entered_play_turn[turtwig.entity_id] = 2
        grotle = t.put(GROTLE, P1, 'hand')
        self.assertNotIn(turtwig.entity_id, t.targets(grotle, 'EvolvePokemonPlayAbility'))

    async def test_forest_chain_turtwig_grotle_torterra(self):
        # Grotle was also played (evolved onto Turtwig) this turn, so the
        # Stadium lets it evolve again into Torterra.
        t = self.table()
        t.stadium(FOREST, P1)
        turtwig = t.put(TURTWIG, P1, 'bench')
        t.state.entered_play_turn[turtwig.entity_id] = t.state.turn_number
        grotle = t.put(GROTLE, P1, 'hand')
        await t.play(grotle, targets=[turtwig.entity_id])
        torterra = t.put(TORTERRA, P1, 'hand')
        self.assertIn(grotle.entity_id, t.targets(torterra, 'EvolvePokemonPlayAbility'))


if __name__ == "__main__":
    unittest.main()
