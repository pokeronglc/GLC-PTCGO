"""A player who logs in again during the reconnect grace gets a longer
window: their restarted client can take over a minute to load before it asks
to rejoin (BredrockRedstone lost 3 games that way on Oct 11)."""
import unittest
from unittest.mock import patch

from tests.test_grace_claim_or_wait import GraceClaimOrWait
from spirit.game.session.constants import RETURNING_GRACE_SECONDS
from spirit.tools.effect_smoke import P1, P2


class GraceExtendOnLogin(GraceClaimOrWait):
    async def test_login_during_grace_extends_it(self):
        s = self.session()
        with patch.object(s, '_arm_reconnect_grace') as arm:
            self.assertTrue(s.note_player_logging_in(P1))
        arm.assert_called_once_with(P1, RETURNING_GRACE_SECONDS)
        self.assertGreater(RETURNING_GRACE_SECONDS, 60)

    async def test_only_once_per_drop(self):
        s = self.session()
        with patch.object(s, '_arm_reconnect_grace') as arm:
            s.note_player_logging_in(P1)
            self.assertFalse(s.note_player_logging_in(P1))
        self.assertEqual(arm.call_count, 1)

    async def test_new_drop_allows_another_extension(self):
        s = self.session()
        with patch.object(s, '_arm_reconnect_grace') as arm:
            s.note_player_logging_in(P1)
            s._resync_epoch += 1               # dropped again later
            self.assertTrue(s.note_player_logging_in(P1))
        self.assertEqual(arm.call_count, 2)

    async def test_connected_player_login_changes_nothing(self):
        s = self.session()
        with patch.object(s, '_arm_reconnect_grace') as arm:
            self.assertFalse(s.note_player_logging_in(P2))
        arm.assert_not_called()


for _n in [n for n in vars(GraceClaimOrWait) if n.startswith('test_')]:
    setattr(GraceExtendOnLogin, _n, None)

if __name__ == '__main__':
    unittest.main()
