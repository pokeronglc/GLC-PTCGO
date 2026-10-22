"""Banette - Puppet Offering: the Supporter goes to hand and the WHOLE Banette
(including the Shuppet under it) goes to the Lost Zone; attachments discard."""
import unittest
from unittest.mock import patch, AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.effects import EffectContext, resolve_activated_ability
from spirit.game.models.board import create_card_entity
from spirit.game.scripts.cards import loader
from spirit.tools.effect_smoke import P1


def _make(board, path, area):
    card = create_card_entity(loader.cards_by_guid[fixtures.definition(path).guid.lower()], P1)
    card.owning_player_id = P1
    board.add_card_to_area(card, board.find_player_area(P1, area))
    return card


class PuppetOfferingTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def test_shuppet_goes_to_lost_zone_with_banette(self):
        rig, e = self.rig('SWSH11.Shuppet_72', 'pokemon')
        board, session = rig.board, rig.session
        shuppet = e['target']
        energy = [c for c in shuppet.children]
        banette = _make(board, 'SWSH11.Banette_73', 'hand')
        with patch.object(session, 'send_game_sequence', AsyncMock()):
            await session.perform_evolution(P1, banette, shuppet)
        supporter = _make(board, 'CEL25.ProfessorsResearchProfessorOak_23', 'discard')
        ability = next(a for a in fixtures.definition('SWSH11.Banette_73').abilities
                       if a.title == 'Puppet Offering')

        async def choose(ctx_self, cards, n, **kwargs):
            return [c for c in cards if c is supporter]

        with patch.object(EffectContext, 'ask_yes_no', AsyncMock(return_value=True)), \
             patch.object(EffectContext, 'choose_cards', choose), \
             patch.object(session, '_promote_new_active', AsyncMock(return_value=True)):
            await resolve_activated_ability(session, P1, banette, ability)
        zone = lambda name: board.find_player_area(P1, name).children
        self.assertIn(supporter, zone('hand'))
        self.assertIn(banette, zone('lostZone'))
        self.assertIn(shuppet, zone('lostZone'))
        self.assertNotIn(shuppet, zone('discard'))
        for card in energy:
            self.assertIn(card, zone('discard'))


if __name__ == "__main__":
    unittest.main()
