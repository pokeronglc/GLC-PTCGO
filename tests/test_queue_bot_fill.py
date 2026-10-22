"""Versus queues no longer fill with the bot; deck-builder Test still does."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from spirit.game.session import manager as mgr


def fake_client(name="p1"):
    client = MagicMock()
    client.player.username = name
    client.player.account_id = f"acct-{name}"
    client.addr = ("127.0.0.1", 1)
    client.send_packet = AsyncMock()
    return client


class QueueBotFillTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.m = mgr.GameSessionManager()
        self.m.queues.clear()

    async def test_versus_queue_has_no_bot_fill(self):
        client = fake_client()
        with patch.object(mgr, "deck_rejection", return_value=None), \
                patch.object(self.m, "_start_bot_match", AsyncMock()) as bot:
            await self.m.add_to_queue(client, "OneVsOneExpertModified", {}, {})
            entry = next(e for e in self.m.queues["OneVsOneExpertModified"] if e["client"] is client)
            self.assertIsNone(entry["fill_task"])
            bot.assert_not_called()
        await self.m.remove_from_queue(client, send_left_packet=False)

    async def test_deck_builder_test_still_uses_bot(self):
        client = fake_client("p2")
        with patch.object(self.m, "_start_bot_match", AsyncMock()) as bot:
            await self.m.add_to_queue(client, "SinglePlayerTest", {}, {})
            bot.assert_awaited_once()

    async def test_switch_turns_bot_fill_back_on(self):
        client = fake_client("p3")
        with patch.object(mgr, "QUEUE_BOT_FILL", True), \
                patch.object(mgr, "deck_rejection", return_value=None):
            await self.m.add_to_queue(client, "OneVsOneExpertModified", {}, {})
            entry = next(e for e in self.m.queues["OneVsOneExpertModified"] if e["client"] is client)
            self.assertIsNotNone(entry["fill_task"])
        await self.m.remove_from_queue(client, send_left_packet=False)


if __name__ == "__main__":
    unittest.main()
