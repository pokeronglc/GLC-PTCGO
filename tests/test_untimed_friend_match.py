"""Owner rule (Oct 12): Friend match with "Timed match" unchecked = no clock
(no action timer, no prompt deadline, no AFK loss); checked = Versus clock."""
import asyncio
import types
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests.bughunt_table import Table
from tests.test_prompt_timeouts import net_player, sent_names, TINY_MS
from spirit.game.session import game_session as gs_mod
from spirit.game.session.constants import GamePhase, PROMPT_NO, PROMPT_YES
from spirit.game.session.game_session import GameSession, match_is_untimed
from spirit.network.message_names import OutboundMsg
from spirit.tools.effect_smoke import P1, P2


class MatchIsUntimed(unittest.TestCase):
    def test_flag_detection(self):
        f = lambda q, o: match_is_untimed({'queue_name': q, 'options': o})
        self.assertTrue(f('Friend', {'timedMatch': False}))
        self.assertTrue(f('Friend', {'isTimed': 'false'}))
        self.assertTrue(f('Friend', {'useTimer': 0}))
        self.assertFalse(f('Friend', {'timedMatch': True}))
        self.assertFalse(f('Friend', {'timed': 'True'}))
        self.assertFalse(f('Friend', {}))                    # unknown -> timed
        self.assertFalse(f('Versus', {'timedMatch': False}))  # ladder always timed


class UntimedPrompts(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig

    def setUp(self):
        for name, value in (('EFFECT_PROMPT_TIMEOUT_MS', TINY_MS), ('ACTION_TIMEOUT_MS', TINY_MS),
                            ('PROMPT_HIDDEN_GRACE_SECONDS', 0.01)):
            p = patch.object(gs_mod, name, value)
            p.start()
            self.addCleanup(p.stop)

    def table(self, untimed):
        t = Table(self)
        s = t.session
        s.prompt_selection_message = types.MethodType(GameSession.prompt_selection_message, s)
        s.players[P2] = net_player(P2, 'net-P2')
        s.game_phase = GamePhase.TURN_LOOP
        s.untimed = untimed
        t.state.active_player_id = P1
        return t

    async def test_untimed_prompt_waits_for_the_answer(self):
        t = self.table(untimed=True)
        player = t.session.players[P2]
        task = asyncio.create_task(t.session.prompt_player_choice(
            P2, 'Pick', [PROMPT_YES, PROMPT_NO]))
        await asyncio.sleep(0.3)                 # far past the tiny timeout
        self.assertFalse(task.done())
        player.pending_choice_future.set_result({'selection': 0, 'counter': None})
        self.assertEqual(await asyncio.wait_for(task, 2), 0)
        self.assertNotIn(OutboundMsg.SET_IDLE_TIMER.value, sent_names(player))

    async def test_untimed_main_action_offer_has_no_timer(self):
        t = self.table(untimed=True)
        player = t.session.players[P2]
        task = asyncio.create_task(t.session.prompt_selection_message(
            player, 'X', {'counter': 1}, expected_counter=1,
            idle_timeout_ms=TINY_MS))
        await asyncio.sleep(0.3)
        self.assertFalse(task.done())
        self.assertNotIn(OutboundMsg.SET_IDLE_TIMER.value, sent_names(player))
        task.cancel()

    async def test_timed_friend_match_still_times_out(self):
        t = self.table(untimed=False)
        picked = await asyncio.wait_for(t.session.prompt_player_choice(
            P2, 'Pick', [PROMPT_YES, PROMPT_NO]), 5)
        self.assertEqual(picked, 1)


if __name__ == '__main__':
    unittest.main()
