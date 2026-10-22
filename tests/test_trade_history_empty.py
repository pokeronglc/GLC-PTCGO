"""Owner decision (Oct 13): Trade History always shows no trades (real
entries crashed the client's TradeHistoryTabPanel)."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from spirit.packets.handlers.trade import TradeHandler


class TradeHistoryEmpty(unittest.IsolatedAsyncioTestCase):
    async def test_count_and_history_are_empty(self):
        handler = TradeHandler(MagicMock())
        handler.send = AsyncMock()
        handler._account_id = lambda: 'acct'
        with patch.object(TradeHandler, '_trade_history',
                          side_effect=AssertionError('history must not be read')):
            await handler.handle_view_trade_history_count({}, 7, 0)
            await handler.handle_view_trade_history({'offset': 0, 'limit': 50}, 8, 0)
        count_msg, history_msg = (c.args[0] for c in handler.send.await_args_list)
        self.assertEqual(count_msg['count'], 0)
        self.assertEqual(history_msg['history'], [])


if __name__ == '__main__':
    unittest.main()
