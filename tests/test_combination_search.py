"""'Search your deck for up to N in any combination of A and B' offers both kinds.

Regression: Heatmor's Licking Catch only offered Basic Fire Energy, never Fire
Pokémon, because the typed-Energy rule swallowed the whole descriptor.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from unittest import IsolatedAsyncioTestCase
from spirit.game.attributes import PokemonTypes as T
from spirit.game.card_effects.standard_era import _search_predicate
from spirit.tools.effect_smoke import P1


class CombinationSearchTests(IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    basic_energy = meta.GlcMetaCardTests.basic_energy

    async def asyncSetUp(self):
        self.board_rig, _ = self.rig('RSV10PT5.Heatmor_19')
        add = lambda key: self.add(self.board_rig, fixtures.definition(key), P1, 'hand')
        self.cards = {
            'Charmander': add('BW7.Charmander_18'),
            'Bulbasaur': add('BW5.Bulbasaur_1'),
            "Ethan's Cyndaquil": add('SV10.EthansCyndaquil_32'),
            'Training Court': add('SWSH2.TrainingCourt_169'),
        }
        for kind in (T.FIRE, T.GRASS, T.WATER, T.PSYCHIC):
            self.cards[kind.name.title() + ' Energy'] = self.basic_energy(self.board_rig, kind)

    def matches(self, text):
        predicate = _search_predicate(text.casefold())
        return sorted(name for name, card in self.cards.items() if predicate(card))

    def test_licking_catch_offers_fire_pokemon_and_fire_energy(self):
        self.assertEqual(self.matches(
            "Search your deck for up to 3 in any combination of Fire Pokémon and Basic Fire "
            "Energy cards, reveal them, and put them into your hand. Then, shuffle your deck."),
            ['Charmander', "Ethan's Cyndaquil", 'Fire Energy'])

    def test_grass_pokemon_and_grass_energy(self):
        self.assertEqual(self.matches(
            "Search your deck for up to 5 in any combination of Grass Pokémon and Grass Energy "
            "cards, reveal them, and put them into your hand."),
            ['Bulbasaur', 'Grass Energy'])

    def test_bare_type_borrows_energy_noun(self):
        self.assertEqual(self.matches(
            "Search your deck for up to 3 in any combination of Water and Psychic Energy cards "
            "and attach them to 1 of your Benched Pokémon."),
            ['Psychic Energy', 'Water Energy'])

    def test_grass_pokemon_and_stadium(self):
        self.assertEqual(self.matches(
            "Search your deck for up to 3 in any combination of Grass Pokémon and Stadium cards, "
            "reveal them, and put them into your hand."),
            ['Bulbasaur', 'Training Court'])

    def test_ethans_pokemon_and_fire_energy(self):
        self.assertEqual(self.matches(
            "Search your deck for up to 3 in any combination of Ethan's Pokémon and Basic Fire "
            "Energy cards, reveal them, and put them into your hand."),
            ["Ethan's Cyndaquil", 'Fire Energy'])


if __name__ == "__main__":
    unittest.main()
