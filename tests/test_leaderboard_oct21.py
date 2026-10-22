"""Public live leaderboard (owner request Oct 21): /leaderboard + /leaderboard.json."""
import json
import os
import tempfile
import threading
import unittest
import urllib.request

from spirit.database import connection


class LeaderboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_path = connection.DB_PATH
        connection.DB_PATH = os.path.join(tempfile.mkdtemp(), 'lb.db')
        import sqlite3
        con = sqlite3.connect(connection.DB_PATH)
        # Same columns as models.account.Account / models.inventory.Deck.
        con.executescript("""
            CREATE TABLE accounts (id INTEGER PRIMARY KEY, account_id TEXT UNIQUE,
                username TEXT UNIQUE, password_hash TEXT, screen_name TEXT);
            CREATE TABLE decks (id TEXT PRIMARY KEY, account_id TEXT, name TEXT,
                deck_data TEXT, is_avatar INT DEFAULT 0, overall_wins INT, overall_played INT,
                wins_since_last_edit INT DEFAULT 0, played_since_last_edit INT DEFAULT 0);""")
        people = [  # account, username, screen name, [(wins, played) per deck]
            ('a1', 'ann', 'Ann', [(30, 50), (5, 10)]),     # 35/60
            ('a2', 'bob', None, [(40, 100)]),               # 40/100
            ('a3', 'cat', 'Cat', [(9, 10)]),                # 9/10: too few for win %
            ('a4', 'guest_x1', 'guest_x1', [(99, 99)]),     # guest: left out
            ('a5', 'dan', 'Dan', [(0, 0)]),                 # never played
            ('a6', 'eve', 'Ev<b>e', [(15, 20)]),            # 75% over 20 games
        ]
        for acc, user, screen, decks in people:
            con.execute("INSERT INTO accounts (account_id, username, password_hash, screen_name) "
                        "VALUES (?,?,?,?)", (acc, user, 'x', screen))
            for i, (w, p) in enumerate(decks):
                con.execute("INSERT INTO decks (id, account_id, name, deck_data, overall_wins, "
                            "overall_played) VALUES (?,?,?,?,?,?)",
                            (f'{acc}-{i}', acc, 'd', '{}', w, p))
        con.commit()
        con.close()

    @classmethod
    def tearDownClass(cls):
        connection.DB_PATH = cls._old_path

    def board(self):
        from spirit.database import leaderboard_data
        leaderboard_data._cache['data'] = None
        return leaderboard_data.get_leaderboard()

    def test_rankings(self):
        d = self.board()
        self.assertEqual([p['player'] for p in d['top_wins']], ['bob', 'Ann', 'Ev<b>e', 'Cat'])
        self.assertEqual(d['top_wins'][1]['played'], 60)
        self.assertEqual([p['player'] for p in d['best_win_rate']], ['Ev<b>e', 'Ann', 'bob'])
        self.assertEqual([p['player'] for p in d['most_active']], ['bob', 'Ann', 'Ev<b>e', 'Cat'])
        self.assertEqual(d['total_players'], 4)

    def test_deck_stats_by_type_and_card(self):
        import sqlite3
        from tests import test_hgss_rules as fixtures
        from spirit.game.scripts.cards import loader
        loader.load_all()
        g = lambda spec: fixtures.definition(spec).guid
        water = [g('ZSV10PT5.Tirtouga_106')] * 4 + [g('SWSH4.WashWaterEnergy_165')] * 2 \
            + [g('SM3.Guzma_115')] * 2 + [g('MEE.BasicWaterEnergy_11')] * 10
        psychic = [g('SWSH11.Gengar_66')] * 3 + [g('SM3.Guzma_115')] * 1
        con = sqlite3.connect(connection.DB_PATH)
        for deck_id, acc, cards, wins, played in (('w1', 'a1', water, 6, 10),
                                                  ('w2', 'a2', water, 1, 2),
                                                  ('p1', 'a6', psychic, 3, 8),
                                                  ('g1', 'a4', psychic, 50, 50)):   # guest
            con.execute("INSERT INTO decks (id, account_id, name, deck_data, overall_wins, "
                        "overall_played, wins_since_last_edit, played_since_last_edit) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (deck_id, acc, 'x', json.dumps({'piles': {'deck': cards}}), 0, 0, wins, played))
        con.commit()
        con.close()
        try:
            d = self.board()
            types = {r['type']: r for r in d['by_type']}
            self.assertEqual(types['Water']['games'], 12)
            self.assertEqual(types['Water']['wins'], 7)
            self.assertEqual(types['Psychic']['games'], 8)
            self.assertEqual(d['top_pokemon'][0]['card'], 'Tirtouga')
            self.assertEqual(d['top_pokemon'][0]['avg_copies'], 4.0)
            guzma = d['top_trainers'][0]
            self.assertEqual((guzma['card'], guzma['games'], guzma['decks']), ('Guzma', 20, 3))
            self.assertEqual(d['top_special_energy'][0]['card'], 'Wash Water Energy')
            self.assertNotIn('Basic Water Energy', [c['card'] for c in d['top_special_energy']])
        finally:
            con = sqlite3.connect(connection.DB_PATH)
            con.execute("DELETE FROM decks WHERE id IN ('w1','w2','p1','g1')")
            con.commit()
            con.close()

    def test_http_routes(self):
        from spirit.server.http_server import MockHTTPRequestHandler
        import http.server
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), MockHTTPRequestHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            base = f'http://127.0.0.1:{srv.server_address[1]}'
            for path in ('/leaderboard.json', '/api/leaderboard'):
                with urllib.request.urlopen(base + path) as r:
                    self.assertEqual(r.headers['Access-Control-Allow-Origin'], '*')
                    self.assertEqual(json.loads(r.read())['top_wins'][0]['player'], 'bob')
            with urllib.request.urlopen(base + '/leaderboard') as r:
                html = r.read().decode()
                self.assertIn('GLC Leaderboard', html)
                self.assertIn('textContent', html)     # names never go in as HTML
        finally:
            srv.shutdown()


if __name__ == '__main__':
    unittest.main()
