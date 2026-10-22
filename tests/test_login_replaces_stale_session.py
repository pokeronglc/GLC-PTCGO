"""A new login for an account that the server still thinks is online
replaces the old session instead of failing with "already online"."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from spirit.packets.handlers import auth as auth_mod


def fake_client(server, addr):
    client = MagicMock()
    client.server = server
    client.addr = addr
    client.writer.transport.abort = MagicMock()
    client.disconnect = AsyncMock()
    return client


class LoginReplacesStaleSession(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = MagicMock()
        self.server.clients_by_account = {}
        self.server.logins_in_flight = set()

    def handler(self, client):
        h = auth_mod.AuthHandler.__new__(auth_mod.AuthHandler)
        h.client = client
        h._send_auth_failed = AsyncMock()
        h._complete_auth_success = AsyncMock()
        h._has_active_game = MagicMock(return_value=False)
        return h

    async def test_old_session_out_of_game_is_replaced(self):
        old = fake_client(self.server, ("1.1.1.1", 1))
        self.server.clients_by_account["acct"] = old
        new = fake_client(self.server, ("1.1.1.1", 2))
        h = self.handler(new)
        await h._send_auth_success(7, {"account_id": "acct", "username": "ben"})
        old.writer.transport.abort.assert_called_once()
        old.disconnect.assert_awaited_once()
        h._send_auth_failed.assert_not_awaited()
        h._complete_auth_success.assert_awaited_once()
        self.assertNotIn("acct", self.server.clients_by_account)   # new one registers itself
        self.assertNotIn("acct", self.server.logins_in_flight)

    async def test_hanging_old_session_does_not_block_login(self):
        old = fake_client(self.server, ("1.1.1.1", 1))

        async def hang():
            await asyncio.sleep(3600)
        old.disconnect = hang
        self.server.clients_by_account["acct"] = old
        h = self.handler(fake_client(self.server, ("1.1.1.1", 2)))
        real_wait_for = asyncio.wait_for
        with patch("asyncio.wait_for", lambda aw, timeout: real_wait_for(aw, 0.05)):
            await h._send_auth_success(7, {"account_id": "acct", "username": "ben"})
        h._complete_auth_success.assert_awaited_once()

    async def test_simultaneous_double_login_still_blocked(self):
        self.server.logins_in_flight.add("acct")
        h = self.handler(fake_client(self.server, ("1.1.1.1", 2)))
        await h._send_auth_success(7, {"account_id": "acct", "username": "ben"})
        h._send_auth_failed.assert_awaited_once()
        h._complete_auth_success.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
