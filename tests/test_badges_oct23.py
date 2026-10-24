"""Badge board (owner rules, Oct 23): 4 Versus wins in a row with one deck
type earns that type's badge, permanently, one per type. A loss or a Versus
game with another type starts the count again; concede/disconnect wins count.
Only Versus matchmaking counts (not friend, tournament or bot games)."""
import os
import sqlite3
import tempfile
import unittest

from spirit.database import connection


class BadgeTests(unittest.TestCase):
    def setUp(self):
        self._old = connection.DB_PATH
        connection.DB_PATH = os.path.join(tempfile.mkdtemp(), 'badges.db')
        con = sqlite3.connect(connection.DB_PATH)
        con.executescript("""CREATE TABLE accounts (id INTEGER PRIMARY KEY, account_id TEXT UNIQUE,
            username TEXT UNIQUE, password_hash TEXT, screen_name TEXT);""")
        for acc, user, screen in (('a1', 'ann', 'Ann'), ('a2', 'bob', None),
                                  ('g1', 'guest_x', 'guest_x')):
            con.execute("INSERT INTO accounts (account_id, username, password_hash, screen_name) "
                        "VALUES (?,?,?,?)", (acc, user, 'x', screen))
        con.commit()
        con.close()
        from spirit.database import badge_data
        self.b = badge_data

    def tearDown(self):
        connection.DB_PATH = self._old

    def play(self, acc, *results):
        earned = []
        for deck_type, won in results:
            got = self.b.record_versus_result(acc, deck_type, won)
            if got:
                earned.append(got)
        return earned

    def test_four_wins_in_a_row_earns_the_badge(self):
        self.assertEqual(self.play('a1', *[('Water', True)] * 3), [])
        self.assertEqual(self.play('a1', ('Water', True)), ['Water'])

    def test_a_loss_resets(self):
        self.assertEqual(self.play('a1', ('Fire', True), ('Fire', True), ('Fire', True),
                                   ('Fire', False), ('Fire', True), ('Fire', True),
                                   ('Fire', True)), [])
        self.assertEqual(self.play('a1', ('Fire', True)), ['Fire'])

    def test_another_type_resets(self):
        self.assertEqual(self.play('a1', ('Fire', True), ('Fire', True), ('Fire', True),
                                   ('Water', True), ('Fire', True)), [])

    def test_one_badge_per_type_and_several_types(self):
        self.play('a1', *[('Water', True)] * 8)
        self.play('a1', *[('Psychic', True)] * 4)
        board = self.b.get_badge_board()
        self.assertEqual(board[0]['player'], 'Ann')
        self.assertEqual(board[0]['badges'], ['Water', 'Psychic'])

    def test_board_sorting_and_guests(self):
        self.play('a2', *[('Grass', True)] * 4)
        self.play('a1', *[('Water', True)] * 4 + [('Fire', True)] * 4)
        self.play('g1', *[('Metal', True)] * 4)
        names = [p['player'] for p in self.b.get_badge_board()]
        self.assertEqual(names, ['Ann', 'bob'])          # most badges first, guests left out

    def test_empty_board_before_any_badge(self):
        self.assertEqual(self.b.get_badge_board(), [])

    def test_only_versus_games_count(self):
        ok = self.b.is_badge_game
        self.assertTrue(ok({'queue_name': 'OneVsOneExpertModified', 'is_solo': False}))
        self.assertFalse(ok({'queue_name': 'Friend', 'is_solo': False}))
        self.assertFalse(ok({'queue_name': 'SinglePlayerModified', 'is_solo': True}))
        self.assertFalse(ok({'queue_name': 'OneVsOneExpertModified', 'tournament': {'x': 1}}))
        self.assertFalse(ok({'queue_name': 'Tournament_5'}))



class BadgeHookTests(unittest.IsolatedAsyncioTestCase):
    """GameSession._record_badge_streak reads the deck's type from the pairing."""
    def setUp(self):
        self._old = connection.DB_PATH
        connection.DB_PATH = os.path.join(tempfile.mkdtemp(), 'hook.db')
        sqlite3.connect(connection.DB_PATH).executescript(
            "CREATE TABLE accounts (account_id TEXT, username TEXT, screen_name TEXT);"
            "INSERT INTO accounts VALUES ('acc', 'ann', 'Ann');")
        from spirit.game.scripts.cards import loader
        loader.load_all()

    def tearDown(self):
        connection.DB_PATH = self._old

    async def test_versus_wins_with_a_water_deck_earn_water(self):
        import types
        from tests import test_hgss_rules as fixtures
        from spirit.game.session.game_session import GameSession, deck_type_of
        deck = {'piles': {'deck': [fixtures.definition('DM.Quagsire_26').guid] * 4
                          + [fixtures.definition('DM.Wooper_25').guid] * 4}}
        self.assertEqual(deck_type_of(deck), 'Water')
        session = GameSession.__new__(GameSession)
        session.game_id = 'g'
        session.pairing = {'queue_name': 'OneVsOneExpertModified', 'is_solo': False,
                           'players': {'p1': {'deck': deck}}}
        player = types.SimpleNamespace(account_id='acc', screen_name='Ann')
        for _ in range(4):
            await session._record_badge_streak('p1', player, True)
        from spirit.database.badge_data import get_badge_board
        self.assertEqual(get_badge_board()[0]['badges'], ['Water'])
        session.pairing['queue_name'] = 'Friend'           # friend games don't count
        for _ in range(4):
            await session._record_badge_streak('p1', player, False)
        self.assertEqual(get_badge_board()[0]['badges'], ['Water'])


if __name__ == '__main__':
    unittest.main()
