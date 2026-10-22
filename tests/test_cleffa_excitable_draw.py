"""Cleffa (SM10 131) - Excitable Draw: heads -> shuffle your hand into your
deck, then draw 6; tails -> nothing. Either way the turn ends."""
import unittest
from unittest.mock import patch, AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1

PATH = 'SM10.Cleffa_131'


class ExcitableDrawTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def _use(self, heads):
        rig, e = self.rig(PATH, 'pokemon')
        hand = rig.board.find_player_area(P1, 'hand')
        before = list(hand.children)
        ability = next(a for a in fixtures.definition(PATH).abilities if a.title == 'Excitable Draw')
        ctx = EffectContext(rig.session, P1, e['target'], ability)
        with patch.object(EffectContext, 'flip_coins', AsyncMock(return_value=[heads])):
            await ability.effect(ctx)
        return before, list(hand.children), ctx

    async def test_heads_replaces_hand_with_six(self):
        before, after, ctx = await self._use(True)
        self.assertGreater(len(before), 6)
        self.assertEqual(len(after), 6)
        self.assertTrue(ctx.ends_turn)

    async def test_tails_keeps_hand(self):
        before, after, ctx = await self._use(False)
        self.assertEqual(after, before)
        self.assertTrue(ctx.ends_turn)


if __name__ == "__main__":
    unittest.main()
