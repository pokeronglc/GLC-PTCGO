"""Owner request (Oct 16): the card-art server logs any request slower than
SLOW_REQUEST_SECONDS (path, size, time, player address); fast ones stay
silent. Also: the listen backlog is 256 (was 5)."""
import time
import unittest
import urllib.request
from unittest.mock import patch

from spirit.server import http_server as h


class SlowRequestLog(unittest.TestCase):
    def setUp(self):
        self.srv = h.AssetHTTPServer(host='127.0.0.1', port=0)
        self.port = self.srv.server.server_address[1]
        self.srv.start()
        self.addCleanup(self.srv.stop)

    def get(self, path='/health'):
        return urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}', timeout=10).read()

    def test_backlog(self):
        self.assertEqual(self.srv.server.request_queue_size, 256)

    def test_fast_request_is_not_logged(self):
        self.get()          # first /health warms the card data (slow once)
        with self.assertNoLogs(level='INFO'):
            self.get()

    def test_slow_request_is_logged(self):
        real = h.MockHTTPRequestHandler._do_get

        def slow(handler):
            time.sleep(0.2)
            return real(handler)
        with patch.object(h.MockHTTPRequestHandler, 'SLOW_REQUEST_SECONDS', 0.1), \
                patch.object(h.MockHTTPRequestHandler, '_do_get', slow), \
                self.assertLogs(level='INFO') as logs:
            self.get('/health')
        line = next(l for l in logs.output if 'Slow request' in l)
        self.assertIn('GET /health', line)
        self.assertIn('127.0.0.1', line)


if __name__ == '__main__':
    unittest.main()
