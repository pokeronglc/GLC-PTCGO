"""Reconnect grace (Oct 11): when it runs out the connected player chooses
"Claim the win" or "Wait 60 seconds" instead of an automatic win."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests import test_hgss_rules as fixtures
from spirit.game.session import game_session as gs_mod
from spirit.game.session.network_player import NetworkPlayer
from spirit.tools.effect_smoke import P1, P2


def net_player(account_id, name):
    handler = MagicMock()
    handler.player.account_id = account_id
    handler.player.username = name
    handler.player.screen_name = name
    handler.running = True
    handler.send_packet = AsyncMock()
    return NetworkPlayer(handler, {})


class GraceClaimOrWait(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig

    def session(self):
        rig, _ = self.rig('SM11.Aegislash_95')
        s = rig.session
        s.players[P1] = net_player(P1, 'absent')
        s.players[P2] = net_player(P2, 'waiting')
        s.players[P1].client_handler = None          # detached
        s._disconnected.add(P1)
        s.concede = AsyncMock()
        s._show_connection_pause = AsyncMock()
        return s

    def sent_prompts(self, player):
        return [c for c in player.client_handler.send_packet.await_args_list
                if 'CustomChoiceRequired' in str(c)]

    async def run_grace(self, s, answer=None, reconnect_after=None):
        async def answerer():
            for _ in range(200):
                await asyncio.sleep(0.01)
                if P2 in s._grace_claim_prompts:
                    break
            if reconnect_after is not None:
                s._disconnected.discard(P1)
                return
            if answer is not None:
                counter = s._grace_claim_prompts[P2][1]
                await s.receive_player_action(P2, {'selection': answer, 'counter': counter})
        with patch.object(gs_mod, 'RECONNECT_GRACE_SECONDS', 0), \
                patch.object(gs_mod, 'CLAIM_OR_WAIT_ANSWER_SECONDS', 1), \
                patch.object(s, '_arm_reconnect_grace') as rearm:
            task = asyncio.ensure_future(answerer())
            await s._disconnect_grace(P1)
            await task
        return rearm

    async def test_claim_awards_the_win(self):
        s = self.session()
        rearm = await self.run_grace(s, answer=0)
        s.concede.assert_awaited_once_with(P1, reason='absent disconnected')
        rearm.assert_not_called()
        self.assertTrue(self.sent_prompts(s.players[P2]))

    async def test_wait_rearms_the_grace(self):
        s = self.session()
        rearm = await self.run_grace(s, answer=1)
        s.concede.assert_not_called()
        rearm.assert_called_once_with(P1)

    async def test_no_answer_counts_as_claim(self):
        s = self.session()
        await self.run_grace(s, answer=None)
        s.concede.assert_awaited_once_with(P1, reason='absent disconnected')

    async def test_reconnect_while_asking_cancels_question(self):
        s = self.session()
        rearm = await self.run_grace(s, reconnect_after=True)
        s.concede.assert_not_called()
        rearm.assert_not_called()
        self.assertIn('ForceSelectionFinished',
                      str(s.players[P2].client_handler.send_packet.await_args_list))

    async def test_answer_accepted_while_play_is_paused(self):
        s = self.session()
        s._connection_resumed.clear()                 # paused for the drop
        rearm = await self.run_grace(s, answer=1)
        rearm.assert_called_once_with(P1)


if __name__ == "__main__":
    unittest.main()
