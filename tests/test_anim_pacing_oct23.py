"""SPIRIT_ANIM_PACING scales the server's wait for client animations
(owner request Oct 23: actions felt slow; waits averaged ~3 s)."""
import unittest
from unittest.mock import patch


class AnimPacing(unittest.TestCase):
    def wait_for(self, pacing):
        from spirit import config
        from spirit.game.session.game_session import GameSession
        s = GameSession.__new__(GameSession)
        s._client_caught_up_at = {}
        s.choreography_pauses = True
        with patch.object(config, 'ANIM_PACING', pacing):
            s._note_client_animation('Attack', ['p1'])
        return s._client_catchup_remaining('p1')

    def test_full_pacing_matches_the_estimate(self):
        self.assertAlmostEqual(self.wait_for(1.0), 3.4, delta=0.1)

    def test_lower_pacing_waits_less(self):
        self.assertAlmostEqual(self.wait_for(0.5), 1.7, delta=0.1)

    def test_zero_never_waits(self):
        self.assertEqual(self.wait_for(0.0), 0.0)


if __name__ == '__main__':
    unittest.main()
