"""Trumbeak (Oct 11): never offer both the click panel and the drag evolve."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_player_reports_oct08 as oct08
from spirit.game.attributes import AttrID
from spirit.game.data_utils import ABILITIES_BY_ID
from spirit.game.session.legal_actions import compute_legal_actions


def kinds(offers):
    out = []
    for a in offers:
        sa = a['selectableAction']
        if sa['selectionType'] == 'AbilitySelection':
            out.append(ABILITIES_BY_ID[sa['actionID']].title)
        else:
            out.append(sa['description'])
    return sorted(out)


class TrumbeakOneEvolvePath(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig
    add = fixtures.HgssRulesTests.add
    async def board(self, with_pikipek=True):
        cls = next(v for v in vars(oct08).values()
                   if isinstance(v, type) and hasattr(v, '_trumbeak_board'))
        return await cls._trumbeak_board(self, with_pikipek)

    async def test_panel_only_when_mountain_pass_is_available(self):
        rig, trumbeak, pikipek, offers = await self.board()
        self.assertEqual(kinds(offers), ['Evolve', 'Mountain Pass'])

    async def test_plain_drag_evolve_once_mountain_pass_is_used(self):
        rig, trumbeak, pikipek, _ = await self.board()
        ids = [e.get('abilityID') for e in trumbeak.get_attribute(AttrID.PIE_ABILITIES) or []]
        mp = next(i for i in ids if ABILITIES_BY_ID[i].title == 'Mountain Pass')
        rig.session.turn_state.used_abilities.add((trumbeak.entity_id, mp))
        offers = [a for a in compute_legal_actions(rig.board, rig.session.turn_state,
                                                   trumbeak.owning_player_id, rig.session.game_id)
                  if a['entityID'] == trumbeak.entity_id]
        self.assertEqual(kinds(offers), ['EvolvePokemonPlayAbility'])

    async def test_no_pikipek_only_mountain_pass(self):
        rig, trumbeak, _, offers = await self.board(with_pikipek=False)
        self.assertEqual(kinds(offers), ['Mountain Pass'])


if __name__ == "__main__":
    unittest.main()
