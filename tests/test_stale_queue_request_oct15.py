"""Oct 15 (game d3b1cc7b, PlayerA vs PlayerB): a client pressed Cancel
and re-queued while its match was being created. The queue request arrived
25 ms after the game started and deleted it, leaving both players on an
empty board. A game that has only just started must survive a stale queue
request; an abandoned game in progress is conceded instead of vanishing."""
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from spirit.game.session import manager as mgr
from spirit.game.session.constants import GamePhase


def fake_client(name):
    client = MagicMock()
    client.player.username = name
    client.player.account_id = f"acct-{name}"
    client.addr = ("127.0.0.1", 1)
    client.send_packet = AsyncMock()
    return client


def fake_session(game_id, account_id, age, phase=GamePhase.INIT):
    session = MagicMock()
    session.game_id = game_id
    session.players = {account_id: MagicMock()}
    session.game_phase = phase
    session.created_at = time.monotonic() - age
    session.concede = AsyncMock()
    return session


class StaleQueueRequest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.m = mgr.GameSessionManager()
        self.m.queues.clear()
        self.m.active_sessions.clear()
        self.m.session_ids_by_player.clear()

    async def queue(self, client):
        with patch.object(mgr, "deck_rejection", return_value=None):
            await self.m.add_to_queue(client, "OneVsOneExpertModified", {}, {})

    def register(self, session, account_id):
        self.m.active_sessions[session.game_id] = session
        self.m.session_ids_by_player[account_id] = session.game_id

    async def test_new_game_survives_a_requeue(self):
        client = fake_client("snorlax")
        session = fake_session("g-new", client.player.account_id, age=0.05)
        self.register(session, client.player.account_id)
        await self.queue(client)
        self.assertIn("g-new", self.m.active_sessions)
        session.concede.assert_not_awaited()
        self.assertFalse(any(e["client"] is client
                             for e in self.m.queues.get("OneVsOneExpertModified", [])))

    async def test_abandoned_game_is_conceded_then_queued(self):
        client = fake_client("leaver")
        session = fake_session("g-old", client.player.account_id, age=600,
                               phase=GamePhase.TURN_LOOP)
        self.register(session, client.player.account_id)
        await self.queue(client)
        session.concede.assert_awaited_once_with(client.player.account_id)
        self.assertNotIn("g-old", self.m.active_sessions)
        self.assertTrue(any(e["client"] is client
                            for e in self.m.queues["OneVsOneExpertModified"]))
        await self.m.remove_from_queue(client, send_left_packet=False)

    async def test_finished_game_is_just_cleared(self):
        client = fake_client("done")
        session = fake_session("g-done", client.player.account_id, age=1,
                               phase=GamePhase.GAME_OVER)
        self.register(session, client.player.account_id)
        await self.queue(client)
        session.concede.assert_not_awaited()
        self.assertNotIn("g-done", self.m.active_sessions)
        await self.m.remove_from_queue(client, send_left_packet=False)


if __name__ == "__main__":
    unittest.main()
