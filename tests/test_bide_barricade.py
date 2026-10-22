"""Wobbuffet - Bide Barricade (XY4 and 20th Anniversary prints): while it is
Active, non-Psychic Pokémon (e.g. Darkness Spiritomb) have no Abilities."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.legal_actions import compute_legal_actions
from spirit.game.session.passives import ability_locked
from spirit.tools.effect_smoke import P1, P2


class BideBarricadeTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_spiritomb_building_spite_blocked(self):
        for wob in ('XY4.Wobbuffet_36', 'TwentiethAnn.Wobbuffet_111'):
            for side in (P1, P2):
                with self.subTest(wobbuffet=wob, side=side):
                    rig, e = self.rig('SM10.Spiritomb_112', 'pokemon')
                    board, session = rig.board, rig.session
                    spiritomb = e['target']
                    wobbuffet = self.add(rig, fixtures.definition(wob), side, 'bench')
                    active = board.find_player_area(side, 'activePokemonArea')
                    previous = active.children[0]
                    active.remove_child(previous)
                    board.find_player_area(side, 'bench').remove_child(wobbuffet)
                    board.add_card_to_area(wobbuffet, active)
                    board.add_card_to_area(previous, board.find_player_area(side, 'bench'))
                    self.assertTrue(ability_locked(board, spiritomb))
                    offered = [a for a in compute_legal_actions(board, session.turn_state, P1, session.game_id)
                               if a['entityID'] == spiritomb.entity_id
                               and a['selectableAction']['description'] == 'UsePokemonAbility']
                    self.assertEqual(offered, [])


    async def test_psychic_pokemon_keep_their_abilities(self):
        for wob in ('XY4.Wobbuffet_36', 'TwentiethAnn.Wobbuffet_111'):
            for side in (P1, P2):
                with self.subTest(wobbuffet=wob, side=side):
                    rig, e = self.rig('SM10.Mismagius_78', 'pokemon')   # Psychic
                    board = rig.board
                    mismagius = e['target']
                    wobbuffet = self.add(rig, fixtures.definition(wob), side, 'bench')
                    active = board.find_player_area(side, 'activePokemonArea')
                    previous = active.children[0]
                    active.remove_child(previous)
                    board.find_player_area(side, 'bench').remove_child(wobbuffet)
                    board.add_card_to_area(wobbuffet, active)
                    board.add_card_to_area(previous, board.find_player_area(side, 'bench'))
                    self.assertFalse(ability_locked(board, mismagius))
                    self.assertFalse(ability_locked(board, wobbuffet))


if __name__ == "__main__":
    unittest.main()
