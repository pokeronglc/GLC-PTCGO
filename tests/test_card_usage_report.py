"""DECK lines at game start + the card usage / wins-by-type report."""
import io
import logging
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from spirit.game.session.game_session import GameSession
from spirit.game.starter_content import BOT_DECKS, build_deck_data
from spirit.tools import card_usage_report as cr


class CardUsageReport(unittest.TestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)

    def test_deck_line_and_wins_by_type(self):
        deck = build_deck_data(*BOT_DECKS[0])
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s,000 - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
        root = logging.getLogger()
        root.addHandler(handler)
        old = root.level
        root.setLevel(logging.INFO)
        try:
            gs = GameSession.__new__(GameSession)
            gs.game_id = '11111111-1111-1111-1111-111111111111'
            gs._log_deck('alice', deck)
            gs._log_deck('bob', {"deckName": "x", "piles": {"deck": []}})
        finally:
            root.removeHandler(handler)
            root.setLevel(old)
        text = buf.getvalue()
        self.assertIn('DECK alice <Psychic> "Psychic" (60): ', text)
        lines = text.splitlines() + [
            "2026-10-11 09:00:00,000 - INFO - [Session 11111111-1111-1111-1111-111111111111] "
            "Game over: alice wins (Took all Prize cards)."]
        out = io.StringIO()

        def fake(_hours):
            for line in lines:
                m = cr.TS.search(line)
                if m:
                    yield m.group(1)

        with patch.object(cr, 'read_log', fake), patch('sys.stdout', out):
            cr.main([])
        report = out.getvalue()
        self.assertIn('Decks taken into games: 2', report)
        self.assertRegex(report, r'Psychic\s+1 wins /\s+1 games')
        self.assertRegex(report, r'Unknown\s+0 wins /\s+1 games')


if __name__ == "__main__":
    unittest.main()
