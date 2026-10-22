"""Grant can be used from the discard pile: discard 2 other cards (not Grant)
from your hand to put it into your hand (player report: it couldn't be clicked)."""
import json
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.session.legal_actions import _out_of_zone_ability_entries
from spirit.tools.effect_smoke import P1


class GrantDiscardRecoveryTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def setup_grant(self, path='SWSH10.Grant_144', hand_cards=2):
        rig, _ = self.rig('BW1.Timburr_58')
        hand = rig.board.find_player_area(P1, 'hand')
        for card in list(hand.children):
            rig.to_area(card, P1, 'deck')
        for _ in range(hand_cards):
            self.add(rig, fixtures.definition('SV1.Nemona_180'), P1, 'hand')
        grant = self.add(rig, fixtures.definition(path), P1, 'discard')
        return rig, grant

    def offers(self, rig, grant):
        return [e for e in _out_of_zone_ability_entries(
            rig.board, rig.session.turn_state, P1, rig.session.game_id)
            if e.get('entityID') == grant.entity_id]

    def test_grant_carries_a_clickable_ability(self):
        for path in ('SWSH10.Grant_144', 'SWSH10.Grant_185', 'CZ.Grant_222'):
            rig, grant = self.setup_grant(path)
            rows = grant.get_attribute(AttrID.PIE_ABILITIES)
            rows = json.loads(rows) if isinstance(rows, str) else rows
            self.assertTrue(rows, path)
            self.assertTrue(self.offers(rig, grant), path)

    def test_not_offered_with_fewer_than_two_other_cards(self):
        rig, grant = self.setup_grant(hand_cards=1)
        self.add(rig, fixtures.definition('SWSH10.Grant_144'), P1, 'hand')   # Grant doesn't count
        self.assertEqual(self.offers(rig, grant), [])

    async def test_using_it_returns_grant_and_discards_two(self):
        rig, grant = self.setup_grant(hand_cards=3)
        entry = self.offers(rig, grant)[0]
        await rig.session._execute_use_ability(P1, grant, entry)
        self.assertIs(grant.parent, rig.board.find_player_area(P1, 'hand'))
        hand = rig.board.find_player_area(P1, 'hand').children
        self.assertEqual(len(hand), 2)      # 3 - 2 discarded + Grant
        self.assertFalse(rig.session.turn_state.supporter_played
                         if hasattr(rig.session.turn_state, 'supporter_played') else False)


if __name__ == "__main__":
    unittest.main()
