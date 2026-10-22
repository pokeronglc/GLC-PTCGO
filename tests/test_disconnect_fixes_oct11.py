"""Client-crash fixes found while auditing mid-game disconnects (Oct 11)."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_sm_knockout_timing as kot
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.game_session import GameSession
from spirit.tools.effect_smoke import P1, P2


def _walk(msgs):
    for m in msgs:
        inner = getattr(m, 'messages', None) or getattr(m, 'inner', None)
        if inner is not None:
            yield from _walk(inner)
        elif isinstance(m, dict):
            yield m


class SpellTagCountersBeforeKnockout(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig
    add = fixtures.HgssRulesTests.add
    attack_context = kot.SmKnockoutTimingTests.attack_context

    async def test_counter_fx_is_sent_before_the_target_is_knocked_out(self):
        rig, e = self.rig('SM11.Aegislash_95')
        victim = e['target']
        victim.set_attribute(AttrID.POKEMON_TYPES, [PokemonTypes.PSYCHIC.value])
        tool = self.add(rig, fixtures.definition('SM8.SpellTag_190'), P1, 'hand')
        rig.attach(tool, victim)
        ctx = self.attack_context(rig, victim)
        attacker = ctx.attacker
        attacker.set_attribute(AttrID.HP, 30)        # 4 counters KO it
        log = []
        real = GameSession.send_game_sequence

        async def record(session, players, name, inner):
            for m in _walk(inner):
                log.append((str(name), m.get('name') or m.get('messageName') or str(m)[:80],
                            str(m)))
            return await real(session, players, name, inner)

        async def place(session, player_id, source_id, pool, count, prompt=''):
            return {attacker.entity_id: count}

        with patch.object(GameSession, 'send_game_sequence', record), \
                patch.object(GameSession, 'prompt_damage_counter_placement', place):
            await ctx.deal_damage(1000, target=victim)
            await rig.session.resolve_knockouts(ctx)

        self.assertNotIn(attacker, rig.board.pokemon_in_play(P2))
        aid = attacker.entity_id
        place_at = [i for i, (_, _, raw) in enumerate(log)
                    if 'PlaceDamageEffect' in raw and aid in raw]
        move_at = [i for i, (_, _, raw) in enumerate(log)
                   if 'EntityMoved' in raw and aid in raw]
        self.assertTrue(place_at, log)
        self.assertTrue(move_at, log)
        self.assertLess(max(place_at), min(move_at))


if __name__ == "__main__":
    unittest.main()


from unittest.mock import AsyncMock, MagicMock
from spirit.game.session import manager as mgr

Q = "OneVsOneExpertModified"


def _client(name):
    c = MagicMock()
    c.player.username = name
    c.player.account_id = f"acct-{name}"
    c.addr = ("127.0.0.1", 1)
    c.running = True
    c.send_packet = AsyncMock()
    return c


class NoSecondGameWhileInAGame(unittest.IsolatedAsyncioTestCase):
    """Kikabo (Oct 11 09:06-09:12): queued, accepted a friend challenge, was
    left in the queue and got paired into a second game mid-match."""

    async def asyncSetUp(self):
        self.m = mgr.GameSessionManager()
        self.m.queues.clear()
        self.m.pending_pairings.clear()
        self.m.pending_challenges.clear()

    async def asyncTearDown(self):
        self.m.queues.clear()
        self.m.pending_pairings.clear()
        self.m.pending_challenges.clear()

    async def test_accepting_a_challenge_leaves_the_queue(self):
        kik, tv = _client("kik"), _client("tv")
        tv.server.clients = [tv, kik]
        with patch.object(mgr, "deck_rejection", return_value=None), \
                patch.object(self.m, "_dispatch_ready_check"):
            await self.m.add_to_queue(kik, Q, {}, {})
            self.m.pending_challenges["challenge_x"] = {
                "challenger": tv, "opponent": kik, "deck": {}, "options": {}}
            kik.server.clients = [tv, kik]
            await self.m.accept_challenge(kik, "challenge_x", {})
        self.assertFalse(any(e["client"] is kik for e in self.m.queues.get(Q, [])))

    async def test_queue_skips_a_player_already_in_a_game(self):
        kik, silver = _client("kik"), _client("silver")
        self.m.queues[Q] = [{"client": kik, "deck": {}, "options": {},
                             "tournament_context": None, "fill_task": None}]
        busy = lambda aid: object() if aid == "acct-kik" else None
        with patch.object(mgr, "deck_rejection", return_value=None), \
                patch.object(self.m, "get_session_by_player_id", side_effect=busy), \
                patch.object(self.m, "remove_session_by_player_id"), \
                patch.object(self.m, "_dispatch_ready_check") as ready:
            await self.m.add_to_queue(silver, Q, {}, {})
        ready.assert_not_called()
        self.assertEqual([e["client"] for e in self.m.queues[Q]], [silver])
        self.assertEqual(self.m.pending_pairings, {})

    async def test_free_players_still_pair(self):
        a, b = _client("a"), _client("b")
        with patch.object(mgr, "deck_rejection", return_value=None), \
                patch.object(self.m, "_dispatch_ready_check") as ready:
            await self.m.add_to_queue(a, Q, {}, {})
            await self.m.add_to_queue(b, Q, {}, {})
        ready.assert_called_once()


from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral


class PeoniaNeverHidesACardStillInHand(unittest.IsolatedAsyncioTestCase):
    """PlayerA's HandSort.Compare crash came 1 s after Peonia: the hand cards
    were re-hidden (AttributesReset) while still in his hand."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_reset_only_after_the_card_left_the_hand(self):
        t = Table(self)
        for pid in (P1, P2):
            neutral(t.put(self.filler, pid, 'active'))
        log = []
        real = GameSession.send_game_sequence

        async def record(session, players, name, inner):
            for m in _walk(inner):
                log.append(str(m))
            return await real(session, players, name, inner)

        with patch.object(GameSession, 'send_game_sequence', record):
            await t.play(t.put('SWSH6.Peonia_149', P1, 'hand'))
        pile = t.board.find_player_area(P1, 'prizePile')
        moved_in = [c.entity_id for c in pile.children]
        hand_id = t.board.find_player_area(P1, 'hand').entity_id
        checked = 0
        for eid in moved_in:
            events = [(m, i) for i, m in enumerate(log) if eid in m
                      and ('EntityMoved' in m or 'AttributesReset' in m)]
            in_hand = False
            for m, i in events:
                if 'EntityMoved' in m:
                    in_hand = hand_id in m
                elif in_hand:
                    self.fail(f"AttributesReset sent while {eid} was in hand (msg {i})")
                else:
                    checked += 1
        self.assertGreater(checked, 0)
