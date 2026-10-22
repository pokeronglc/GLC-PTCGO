"""Every prompt to a connected player is timed (live report, Oct 12).

An AFK opponent who never answered Escape Rope's "Choose your new Active
Pokémon" hung the game forever: only the main action offer had a timer.
Now every prompt expires after EFFECT_PROMPT_TIMEOUT_MS and its caller
applies a legal default instead of waiting (or re-offering) forever.
"""
import asyncio
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from tests import test_hgss_rules as fixtures
from tests.bughunt_table import Table
from spirit.game.card_effects.trainers import escape_rope
from spirit.game.session import game_session as gs_mod
from spirit.game.session.constants import GamePhase, PROMPT_NO, PROMPT_YES
from spirit.game.session.effects import EffectContext
from spirit.game.session.game_session import GameOver, GameSession
from spirit.game.session.network_player import NetworkPlayer
from spirit.network.message_names import OutboundMsg
from spirit.tools.effect_smoke import P1, P2

TINY_MS = 50


def net_player(account_id, name):
    handler = MagicMock()
    handler.player.account_id = account_id
    handler.player.username = name
    handler.player.screen_name = name
    handler.running = True
    handler.send_packet = AsyncMock()
    return NetworkPlayer(handler, {})


def sent_names(player):
    names = []
    for call in player.client_handler.send_packet.await_args_list:
        packet = call.args[0] if call.args else None
        names.append(packet.get('messageName') if isinstance(packet, dict) else packet)
    return names


class PromptTimeouts(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig

    def setUp(self):
        patcher = patch.object(gs_mod, 'EFFECT_PROMPT_TIMEOUT_MS', TINY_MS)
        patcher.start()
        self.addCleanup(patcher.stop)
        grace = patch.object(gs_mod, 'PROMPT_HIDDEN_GRACE_SECONDS', 0.01)
        grace.start()
        self.addCleanup(grace.stop)

    def table(self, networked=(P2,)):
        t = Table(self)
        s = t.session
        # SmokeSession narrows prompt_selection_message's signature; use the
        # real one (the main action offer passes idle_timeout_ms).
        s.prompt_selection_message = types.MethodType(
            GameSession.prompt_selection_message, s)
        for pid in networked:
            s.players[pid] = net_player(pid, f'net-{pid}')
        s.game_phase = GamePhase.TURN_LOOP
        t.state.active_player_id = P1
        return t

    async def bounded(self, coro, seconds=5.0):
        return await asyncio.wait_for(coro, seconds)

    # (a) ------------------------------------------------------------------
    async def test_afk_opponent_escape_rope_auto_picks_a_legal_new_active(self):
        t = self.table()
        t.put(self.filler_spec(), P1, 'active')
        old_active = t.put(self.filler_spec(), P2, 'active')
        bench = [t.put(self.filler_spec(), P2, 'bench') for _ in range(3)]
        rope = t.put('SWSH5.EscapeRope_125', P1, 'hand')
        ctx = EffectContext(t.session, P1, rope, None)
        with self.assertLogs(level='INFO') as logs:
            await self.bounded(escape_rope(ctx))
        new_active = t.active(P2)
        self.assertIn(new_active, bench)
        self.assertIn(old_active, t.zone(P2, 'bench'))
        names = sent_names(t.session.players[P2])
        self.assertIn(OutboundMsg.SET_IDLE_TIMER.value, names)
        self.assertIn(OutboundMsg.FORCE_SELECTION_FINISHED.value, names)
        self.assertTrue(any("didn't answer" in line and 'auto-picked' in line
                            for line in logs.output), logs.output)

    async def test_promotion_after_knock_out_auto_picks_a_benched_pokemon(self):
        t = self.table()
        t.put(self.filler_spec(), P1, 'active')
        bench = [t.put(self.filler_spec(), P2, 'bench') for _ in range(2)]
        promoted = await self.bounded(t.session._promote_new_active(P2))
        self.assertTrue(promoted)
        self.assertIn(t.active(P2), bench)

    # (b) ------------------------------------------------------------------
    async def test_optional_pick_times_out_to_nothing(self):
        t = self.table()
        t.put(self.filler_spec(), P1, 'active')
        t.put(self.filler_spec(), P2, 'active')
        bench = [t.put(self.filler_spec(), P2, 'bench') for _ in range(2)]
        picked = await self.bounded(t.session.prompt_entity_picker(
            P2, bench[0].entity_id, bench, 1, minimum=0, prompt='You may choose'))
        self.assertEqual(picked, [])

    # (c) ------------------------------------------------------------------
    async def test_yes_no_times_out_to_no(self):
        t = self.table()
        t.put(self.filler_spec(), P2, 'active')
        ctx = EffectContext(t.session, P1, None, None)
        self.assertFalse(await self.bounded(ctx.ask_yes_no('You may draw', player_id=P2)))
        idx = await self.bounded(t.session.prompt_player_choice(
            P2, 'Play First Ticket?', [PROMPT_YES, PROMPT_NO]))
        self.assertEqual(idx, 1)

    async def test_button_menu_times_out_to_first_option_and_rps_is_random(self):
        t = self.table()
        idx = await self.bounded(t.session.prompt_player_choice(P2, 'Pick', ['A', 'B', 'C']))
        self.assertEqual(idx, 0)
        with patch.object(gs_mod.random, 'randrange', return_value=2) as rr:
            idx = await self.bounded(t.session.prompt_player_choice(
                P2, 'Rock-Paper-Scissors', ['Rock', 'Paper', 'Scissors']))
        self.assertEqual(idx, 2)
        rr.assert_called_once_with(3)

    # (d) ------------------------------------------------------------------
    async def test_forced_multi_card_pick_returns_exactly_minimum_valid_cards(self):
        t = self.table()
        cards = [t.put(self.item, P2, 'discard') for _ in range(5)]
        valid_ids = {c.entity_id for c in cards}
        picked = await self.bounded(t.session.prompt_card_chooser(
            P2, cards[0].entity_id, cards, 3, minimum=2, prompt='Choose 2-3'))
        self.assertEqual(len(picked), 2)
        self.assertEqual(len(set(picked)), 2)
        self.assertTrue(set(picked) <= valid_ids)
        # One offer, not MAX_SELECTION_RETRIES re-offers.
        offers = [c for c in t.session.players[P2].client_handler.send_packet.await_args_list
                  if 'SelectionWithTargetsRequired' in str(c)]
        self.assertEqual(len(offers), 1)

    async def test_damage_counter_placement_times_out_to_a_legal_spread(self):
        t = self.table()
        t.put(self.filler_spec(), P1, 'active')
        targets = [t.put(self.filler_spec(), P1, 'bench') for _ in range(2)]
        spread = await self.bounded(t.session.prompt_damage_counter_placement(
            P2, targets[0].entity_id, targets, 4))
        self.assertEqual(sum(spread.values()), 4)
        self.assertTrue(set(spread) <= {p.entity_id for p in targets})

    async def test_prize_pick_times_out_to_random_prizes(self):
        t = self.table()
        prizes = [c.entity_id for c in t.zone(P2, 'prizes')]
        picked = await self.bounded(t.session._prompt_prize_pick(P2, prizes, 2))
        self.assertEqual(len(picked), 2)
        self.assertTrue(set(picked) <= set(prizes))

    async def test_setup_active_placement_times_out_to_a_random_basic(self):
        t = self.table()
        t.session.game_phase = GamePhase.PLACEMENT_PHASE
        basics = [t.put(self.filler_spec(), P2, 'hand') for _ in range(2)]
        done = set()
        await self.bounded(t.session._run_active_placement(P2, done))
        self.assertIn(t.active(P2), basics)
        # Before the turn loop the deadline is server-side only.
        self.assertNotIn(OutboundMsg.SET_IDLE_TIMER.value, sent_names(t.session.players[P2]))

    # (e) ------------------------------------------------------------------
    async def test_concede_during_opponents_pending_prompt_ends_the_game(self):
        t = self.table()
        t.put(self.filler_spec(), P1, 'active')
        t.put(self.filler_spec(), P2, 'active')
        bench = [t.put(self.filler_spec(), P2, 'bench') for _ in range(2)]
        with patch.object(gs_mod, 'EFFECT_PROMPT_TIMEOUT_MS', 60_000):
            task = asyncio.ensure_future(t.session.prompt_entity_picker(
                P2, bench[0].entity_id, bench, 1, prompt='Choose your new Active'))
            for _ in range(100):
                await asyncio.sleep(0.01)
                fut = t.session.players[P2].pending_choice_future
                if fut is not None and not fut.done():
                    break
            self.assertFalse(task.done())
            await t.session.concede(P1)
            with self.assertRaises(GameOver):
                await self.bounded(task)
        self.assertEqual(t.session.game_phase, GamePhase.GAME_OVER)

    # (f) ------------------------------------------------------------------
    async def test_main_action_offer_still_auto_ends_the_turn(self):
        t = self.table(networked=(P1,))
        t.put(self.filler_spec(), P1, 'active')
        t.put(self.filler_spec(), P2, 'active')
        with patch.object(gs_mod, 'ACTION_TIMEOUT_MS', TINY_MS), \
                self.assertLogs(level='INFO') as logs:
            await self.bounded(t.session._run_player_turn(P1))
        self.assertTrue(any('was skipped after' in line for line in logs.output),
                        logs.output)
        names = sent_names(t.session.players[P1])
        self.assertIn(OutboundMsg.SET_IDLE_TIMER.value, names)
        self.assertIn(OutboundMsg.FORCE_SELECTION_FINISHED.value, names)

    async def test_answer_before_deadline_is_used(self):
        t = self.table()
        with patch.object(gs_mod, 'EFFECT_PROMPT_TIMEOUT_MS', 60_000):
            task = asyncio.ensure_future(t.session.prompt_player_choice(
                P2, 'Pick', ['A', 'B', 'C']))
            for _ in range(100):
                await asyncio.sleep(0.01)
                if t.session.players[P2].pending_choice_future is not None:
                    break
            await t.session.receive_player_action(P2, {'selection': 2})
            self.assertEqual(await self.bounded(task), 2)

    # helpers --------------------------------------------------------------
    # (late) --------------------------------------------------------------
    async def test_answer_arriving_as_the_timer_runs_out_is_used(self):
        """Player report, Oct 14: Teammates picks reached the server 1.4s before the
        'timed out' log -- during the settle pause after the expiry -- and were
        thrown away (auto-picked nothing)."""
        t = self.table()
        s = t.session
        player = s.players[P2]
        late = {'gameID': s.game_id, 'counter': 7,
                'selection': {'entityID': 'x', 'targetResponses': [
                    {'entityList': ['a', 'b'], 'name': 'EntityListTargetResponse'}]}}
        real_pause = s.choreo_pause

        async def pause_then_reply(seconds):
            fut = player.pending_choice_future
            if fut is not None and not fut.done():
                await s.receive_player_action(P2, late)
            return await real_pause(0)
        s.choreo_pause = pause_then_reply
        reply = await self.bounded(s.prompt_selection_message(
            player, OutboundMsg.SELECTION_WITH_TARGETS_REQUIRED.value,
            {'counter': 7, 'targetMap': {}}, expected_counter=7))
        self.assertEqual(reply, late)
        self.assertNotIn('_timed_out', reply)

    async def test_no_answer_still_times_out(self):
        t = self.table()
        s = t.session
        reply = await self.bounded(s.prompt_selection_message(
            s.players[P2], OutboundMsg.SELECTION_WITH_TARGETS_REQUIRED.value,
            {'counter': 3, 'targetMap': {}}, expected_counter=3))
        self.assertTrue(reply.get('_timed_out'))

    def filler_spec(self):
        return type(self).filler


if __name__ == '__main__':
    unittest.main()


class HiddenGrace(PromptTimeouts):
    """Owner, Oct 15: a Confirm pressed up to 2 seconds after the shown clock
    reaches 0 still counts (the client keeps the picker open until
    ForceSelectionFinished)."""

    async def test_answer_inside_the_grace_is_used_without_closing_the_picker(self):
        t = self.table()
        s = t.session
        with patch.object(gs_mod, 'PROMPT_HIDDEN_GRACE_SECONDS', 1.0):
            task = asyncio.ensure_future(s.prompt_player_choice(P2, 'Pick', ['A', 'B', 'C']))
            await asyncio.sleep(TINY_MS / 1000 + 0.3)        # shown clock is at 0
            self.assertFalse(task.done(), 'still answerable during the grace')
            await s.receive_player_action(P2, {'selection': 1})
            self.assertEqual(await self.bounded(task), 1)
        self.assertNotIn(OutboundMsg.FORCE_SELECTION_FINISHED.value, sent_names(s.players[P2]))

    async def test_shown_timer_excludes_the_grace(self):
        t = self.table()
        s = t.session
        payloads = []
        real = s._idle_timer_payload
        s._idle_timer_payload = lambda acct, ms: (payloads.append(ms), real(acct, ms))[1]
        with patch.object(gs_mod, 'PROMPT_HIDDEN_GRACE_SECONDS', 0.2):
            await self.bounded(s.prompt_player_choice(P2, 'Pick', ['A', 'B']))
        self.assertTrue(payloads)
        self.assertLessEqual(max(payloads), TINY_MS + 1000)
        self.assertNotIn(TINY_MS + 200, payloads)


# The subclass would re-run every inherited test; keep only its own.
for _name in [n for n in dir(PromptTimeouts) if n.startswith('test_')]:
    setattr(HiddenGrace, _name, None)


class DeckCheckTimer(PromptTimeouts):
    """Owner, Oct 16 (player poll): 45 s per action, 60 s for deck checks --
    a card browser over the player's own deck gets the longer timer."""

    async def shown_ms(self, zone):
        t = self.table()
        s = t.session
        t.put(self.filler_spec(), P2, 'active')
        cards = [t.put(self.filler_spec(), P2, zone) for _ in range(3)]
        payloads = []
        real = s._idle_timer_payload
        s._idle_timer_payload = lambda acct, ms: (payloads.append(ms), real(acct, ms))[1]
        with patch.object(gs_mod, 'DECK_SEARCH_PROMPT_TIMEOUT_MS', 3 * TINY_MS):
            await self.bounded(s.prompt_card_chooser(
                P2, cards[0].entity_id, cards, 1, minimum=0, display_cards=cards))
        return max(payloads)

    async def test_deck_search_gets_the_longer_timer(self):
        self.assertGreaterEqual(await self.shown_ms('deck'), 3 * TINY_MS)

    async def test_other_card_choices_keep_the_normal_timer(self):
        self.assertLess(await self.shown_ms('discard'), 3 * TINY_MS)


for _name in [n for n in dir(PromptTimeouts) if n.startswith('test_')]:
    setattr(DeckCheckTimer, _name, None)
