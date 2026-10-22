"""GLC's Salvatore ruling: you can't use a typed Stadium search your deck can't
contain (e.g. a Psychic deck using the opponent's Brooklet Hill).
https://gymleaderchallenge.com/faq
"""
import types
import unittest

from tests import test_hgss_rules as fixtures
from spirit.game import glc

P1 = "p1"


def entity(path, **extra):
    card_def = fixtures.definition(path)
    return types.SimpleNamespace(archetype_id=card_def.guid, children=[], **extra)


class FakeBoard:
    def __init__(self, **zones):
        self.zones = zones

    def find_player_area(self, player_id, name):
        return types.SimpleNamespace(children=self.zones.get(name, []))


BROOKLET = 'SM2.BrookletHill_120'
TURFFIELD = 'SWSH2.TurffieldStadium_170'
STORMY = 'SWSH7.StormyMountains_161'


class SalvatoreRulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HgssRulesTests.setUpClass.__func__(cls)

    def impossible(self, stadium, **zones):
        return glc.stadium_search_is_impossible(
            FakeBoard(**zones), P1, fixtures.definition(stadium))

    def test_psychic_deck_cannot_use_brooklet_hill(self):
        self.assertTrue(self.impossible(BROOKLET, activePokemonArea=[entity('BW1.Munna_48')]))

    def test_fighting_deck_can_use_brooklet_hill(self):
        self.assertFalse(self.impossible(BROOKLET, activePokemonArea=[entity('BW1.Timburr_58')]))

    def test_discarded_pokemon_reveal_the_type_too(self):
        self.assertTrue(self.impossible(BROOKLET, discard=[entity('BW1.Munna_48')]))

    def test_face_down_prizes_reveal_nothing(self):
        self.assertFalse(self.impossible(
            BROOKLET, prizePile=[entity('BW1.Munna_48', publicly_revealed=False)]))

    def test_nothing_typed_visible_allows_the_search(self):
        self.assertFalse(self.impossible(BROOKLET))

    def test_lightning_deck_can_use_stormy_mountains_not_brooklet(self):
        pikachu = [entity('BW1.Pikachu_115')]
        self.assertFalse(self.impossible(STORMY, activePokemonArea=pikachu))
        self.assertTrue(self.impossible(BROOKLET, activePokemonArea=pikachu))

    def test_fire_deck_can_use_turffield_for_a_dual_type_grass_evolution(self):
        # Steam Siege Volcarona is Grass/Fire, so a Fire deck may run it.
        self.assertFalse(self.impossible(TURFFIELD, activePokemonArea=[entity('BW7.Charmander_18')]))

    def test_psychic_deck_cannot_use_turffield(self):
        self.assertTrue(self.impossible(TURFFIELD, activePokemonArea=[entity('BW1.Munna_48')]))


if __name__ == "__main__":
    unittest.main()
