"""Guest/mobile logins must never log in as an existing account by name."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from spirit.packets.handlers import auth


class PasswordlessLoginClosed(unittest.IsolatedAsyncioTestCase):
    def handler(self):
        client = MagicMock()
        client.addr = ("203.0.113.5", 4242)
        h = auth.AuthHandler(client)
        h._send_auth_success = AsyncMock()
        h._send_auth_failed = AsyncMock()
        return h

    async def test_mobile_login_is_refused(self):
        h = self.handler()
        lookup = MagicMock()
        with patch.object(auth, "_get_or_create_account", lookup):
            await h.handle_gas_mobile({"mobileID": "PlayerA"}, 1, 0)
        h._send_auth_success.assert_not_called()
        h._send_auth_failed.assert_awaited_once()
        lookup.assert_not_called()

    async def test_guest_login_ignores_the_client_name(self):
        h = self.handler()
        guest = {"account_id": "g", "username": "guest_x"}
        seen = []

        def fake_guest(ip, password):
            seen.append(ip)
            return guest

        lookup = MagicMock()
        with patch("spirit.database.accounts.get_or_create_guest_account", fake_guest), \
                patch.object(auth, "_get_or_create_account", lookup), \
                patch.object(auth, "run_db", AsyncMock(side_effect=lambda f, *a: f(*a))):
            await h.handle_gas_guest({"uniqueID": "PlayerA"}, 1, 0)
        lookup.assert_not_called()
        self.assertEqual(seen, ["203.0.113.5"])
        h._send_auth_success.assert_awaited_once_with(1, guest)


if __name__ == "__main__":
    unittest.main()
