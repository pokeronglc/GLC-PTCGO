"""Behind the HTTPS nginx site (X-Forwarded-Proto: https) the client must be
handed https:// links (AssetURL, CAS login address); the port-8000 site sends
no header and keeps plain http:// for existing players."""
import json
import threading
import unittest
import urllib.request


class HttpsLinks(unittest.TestCase):
    def fetch(self, headers):
        from spirit.server.http_server import MockHTTPRequestHandler
        import http.server
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), MockHTTPRequestHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(
                f'http://127.0.0.1:{srv.server_address[1]}/config.json', headers=headers)
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        finally:
            srv.shutdown()

    def test_plain_http_unchanged(self):
        cfg = self.fetch({'Host': '203.0.113.5:8000'})
        self.assertEqual(cfg['AssetURL'], 'http://203.0.113.5:8000/')
        self.assertEqual(cfg['hostName'], 'http://203.0.113.5:8000/cas')

    def test_https_behind_proxy(self):
        cfg = self.fetch({'Host': 'glc.example.org', 'X-Forwarded-Proto': 'https'})
        self.assertEqual(cfg['AssetURL'], 'https://glc.example.org/')
        self.assertEqual(cfg['hostName'], 'https://glc.example.org/cas')


if __name__ == '__main__':
    unittest.main()
