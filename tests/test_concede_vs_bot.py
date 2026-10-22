"""Conceding during the bot's turn ends the game at once (Oct 13): the bot's
turn is stopped before the result goes out, instead of playing on."""
import asyncio
import unittest
from unittest.mock import AsyncMock

from tests.test_grace_claim_or_wait import GraceClaimOrWait, net_player
from spirit.game.session.ai_player import AIPlayer
from spirit.game.session.game_session import GameOver
from spirit.tools.effect_smoke import P1, P2


class ConcedeVsBot(GraceClaimOrWait):
    def bot_session(self):
        rig, _ = self.rig('SM11.Aegislash_95')
        s = rig.session
        s.players[P1] = net_player(P1, 'human')
        s.players[P2] = AIPlayer(P2, 'Bot', {}, s)
        s.end_game = AsyncMock(side_effect=GameOver())
        return s

    async def test_concede_on_bot_turn_stops_the_bot_first(self):
        s = self.bot_session()
        sends = []

        async def bot_turn():                 # a bot turn: no human prompt pending
            while True:
                sends.append(1)
                await asyncio.sleep(0.01)
        s.gameplay_task = asyncio.create_task(bot_turn())
        await asyncio.sleep(0.05)
        await s.concede(P1)
        self.assertTrue(s.gameplay_task.done())
        count = len(sends)
        await asyncio.sleep(0.05)
        self.assertEqual(len(sends), count)   # nothing more from the bot
        s.end_game.assert_awaited_once_with(P2, 'human conceded')

    async def test_human_game_keeps_the_old_path(self):
        rig, _ = self.rig('SM11.Aegislash_95')
        s = rig.session
        s.players[P1] = net_player(P1, 'a')
        s.players[P2] = net_player(P2, 'b')
        s.end_game = AsyncMock(side_effect=GameOver())
        s.gameplay_task = asyncio.create_task(asyncio.sleep(10))
        await s.concede(P1)
        self.assertFalse(s.gameplay_task.done())
        s.gameplay_task.cancel()


if __name__ == '__main__':
    unittest.main()
