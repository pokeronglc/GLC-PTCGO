"""grant_all_cards runs on every login: it must be fast and exact."""
import os
import tempfile
import time
import unittest

from spirit.database import connection


class GrantAllCardsBulkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_path = connection.DB_PATH
        connection.DB_PATH = os.path.join(tempfile.mkdtemp(), 'grant.db')
        connection.engine.dispose()
        from spirit.database.base import Base
        import spirit.database  # noqa: F401  (registers the models)
        Base.metadata.create_all(connection.engine)
        from spirit.game.scripts.cards import loader
        cls.cards = loader.load_all()

    @classmethod
    def tearDownClass(cls):
        connection.engine.dispose()
        connection.DB_PATH = cls._old_path

    def rows(self, account):
        from spirit.database import Collection, db_session
        with db_session() as session:
            return {c.archetype_id: (c.tradable_count, c.nontradable_count)
                    for c in session.query(Collection).filter_by(account_id=account)}

    def test_new_account_gets_every_card_quickly(self):
        from spirit.database.player_data import grant_all_cards, _all_cards_grant_count
        started = time.perf_counter()
        self.assertEqual(grant_all_cards('new-acc', count=1, exact=True), len(self.cards))
        self.assertLess(time.perf_counter() - started, 3.0)
        rows = self.rows('new-acc')
        self.assertEqual(len(rows), len(self.cards))
        for card in self.cards[:200]:
            self.assertEqual(rows[card.guid], (_all_cards_grant_count(card, 1), 0))

    def test_exact_mode_lowers_extras_and_repeat_is_a_no_op(self):
        from spirit.database import Collection, db_session
        from spirit.database.player_data import grant_all_cards
        card = self.cards[0]
        grant_all_cards('extra-acc', count=1, exact=True)
        with db_session() as session:
            row = session.query(Collection).filter_by(
                account_id='extra-acc', archetype_id=card.guid).one()
            expected = row.tradable_count
            row.tradable_count, row.nontradable_count = 7, 2
        grant_all_cards('extra-acc', count=1, exact=True)
        self.assertEqual(self.rows('extra-acc')[card.guid], (expected, 0))
        before = self.rows('extra-acc')
        grant_all_cards('extra-acc', count=1, exact=True)
        self.assertEqual(self.rows('extra-acc'), before)


if __name__ == "__main__":
    unittest.main()
