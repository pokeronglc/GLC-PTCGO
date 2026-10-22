"""Owner rule (Oct 12): 3 timeouts in a row -> AFK loss; an answer resets it."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from tests.test_grace_claim_or_wait import GraceClaimOrWait, net_player
from spirit.game.session import game_session as gs_mod
from spirit.game.session.constants import AFK_LOSS_TIMEOUTS
from spirit.tools.effect_smoke import P1, P2


class AfkLoss(GraceClaimOrWait):
    def live_session(self):
        s = self.session()
        s.players[P1] = net_player(P1, 'afk')        # connected this time
        s._disconnected.discard(P1)
        return s

    async def test_three_timeouts_in_a_row_concede(self):
        s = self.live_session()
        for _ in range(AFK_LOSS_TIMEOUTS - 1):
            self.assertFalse(await s._note_afk_timeout(s.players[P1]))
        self.assertTrue(await s._note_afk_timeout(s.players[P1]))
        s.concede.assert_awaited_once_with(P1, reason='afk was AFK')

    async def test_answer_resets_the_count(self):
        s = self.live_session()
        await s._note_afk_timeout(s.players[P1])
        await s._note_afk_timeout(s.players[P1])
        s._afk_streak.pop(P1, None)                  # what a real reply does
        self.assertFalse(await s._note_afk_timeout(s.players[P1]))
        s.concede.assert_not_called()

    async def test_real_prompt_timeouts_end_the_game(self):
        s = self.live_session()
        s.concede = AsyncMock()
        with patch.object(gs_mod, 'EFFECT_PROMPT_TIMEOUT_MS', 30), \
                patch.object(gs_mod, 'PROMPT_HIDDEN_GRACE_SECONDS', 0.01):
            for i in range(AFK_LOSS_TIMEOUTS):
                try:
                    await s.prompt_player_choice(P1, 'Pick', ['A', 'B'])
                except gs_mod.GameOver:
                    self.assertEqual(i, AFK_LOSS_TIMEOUTS - 1)
                    break
            else:
                self.fail('no AFK loss')
        s.concede.assert_awaited_once()


for _n in [n for n in vars(GraceClaimOrWait) if n.startswith('test_')]:
    setattr(AfkLoss, _n, None)
