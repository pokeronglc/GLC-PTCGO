"""Oct 14: deck stats / profile Game Stats, and the client's self-disconnect.

Decoded from the stock client (pie-src.dll / core.dll / sausage-core.dll):

* Deck manager Stats panel reads DECK attributes 201600 overall wins,
  201590 overall played, 201660 wins since edit, 201650 played since edit.
  DeckPropertiesSaved {deckID, attributes} merges new values into a deck.
* Profile Game Stats read ACCOUNT attributes 200030 cards drawn, 200040
  damage dealt, 200050 damage taken, 200060 games played, 200120 game
  points, 200080 time played (seconds), 200125 tournament rep, 200085 upsets.
* NetworkStatusIndicatorConfiguration sets MessageCenterBehaviour's
  pingErrorThreshold; the client TERMINATES its session when its Ping->Pong
  latency exceeds pingErrorThreshold x thresholdProceduralSetting (default 3).
  We sent 1000 ms, i.e. any 3-second stall disconnected the player.
"""
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.test_bughunt12_wire import FakeHandler
from spirit.game import player_stats as ps
from spirit.game.session.network_player import NetworkPlayer
from spirit.network.message_names import OutboundMsg
from spirit.network.protocol import WargFlags
from spirit.tools.effect_smoke import P1, P2


class Builders(unittest.TestCase):
    def test_deck_attributes_replace_echoed_values(self):
        attrs = [{"name": 200670, "value": "coin"},
                 {"name": ps.DECK_OVERALL_WINS, "value": 99},
                 {"name": str(ps.DECK_OVERALL_PLAYED), "value": 99}]
        out = ps.with_deck_stats(attrs, {"overall_wins": 3, "overall_played": 5,
                                         "wins_since_last_edit": 1,
                                         "played_since_last_edit": 2})
        values = {int(a["name"]): a["value"] for a in out}
        self.assertEqual(values[200670], "coin")
        self.assertEqual(values[ps.DECK_OVERALL_WINS], 3)
        self.assertEqual(values[ps.DECK_OVERALL_PLAYED], 5)
        self.assertEqual(values[ps.DECK_WINS_SINCE_EDIT], 1)
        self.assertEqual(values[ps.DECK_PLAYED_SINCE_EDIT], 2)
        self.assertEqual(len(out), 5)

    def test_cards_changed_ignores_order_case_and_cosmetics(self):
        a = {"deckName": "A", "piles": {"CakePile": ["AA", "bb"]}}
        b = {"deckName": "B", "piles": {"CakePile": ["BB", "aa"]}}
        c = {"deckName": "A", "piles": {"CakePile": ["aa", "cc"]}}
        self.assertFalse(ps.deck_cards_changed(a, b))
        self.assertTrue(ps.deck_cards_changed(a, c))

    def test_account_attributes(self):
        out = ps.account_stat_attributes(
            {"cards_drawn": 7, "damage_dealt": 120, "damage_taken": 60,
             "games_played": 2, "seconds_played": 900, "upset_wins": 1},
            game_points=40)
        values = {a["name"]: a["value"] for a in out}
        self.assertEqual(values, {200030: 7, 200040: 120, 200050: 60, 200060: 2,
                                  200080: 900, 200085: 1, 200120: 40, 200125: 0})

    def test_decks_list_carries_stats(self):
        from spirit.game.models.player import Player
        player = Player.__new__(Player)
        player.decks = [{"id": "d1", "deck_data": {"deckID": "d1", "attributes": [],
                                                   "piles": {"CakePile": []}},
                         "overall_wins": 4, "overall_played": 6,
                         "wins_since_last_edit": 1, "played_since_last_edit": 1}]
        with patch('spirit.game.rules.valid_format_names', return_value=[]):
            deck = player.get_decks_data()["decks"][0]
        values = {a["name"]: a["value"] for a in deck["attributes"]}
        self.assertEqual(values[ps.DECK_OVERALL_WINS], 4)
        self.assertEqual(values[ps.DECK_OVERALL_PLAYED], 6)


class EndOfGame(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_records_both_players_and_pushes_deck_stats(self):
        t = Table(self)
        s = t.session
        handlers = {}
        for pid in (P1, P2):
            h = FakeHandler(pid)
            h.player.update_deck_stats = lambda deck_id, stats, pid=pid: \
                handlers[pid].__dict__.setdefault('updated', (deck_id, stats))
            handlers[pid] = h
            s.players[pid] = NetworkPlayer(h, {"piles": {"deck": []}})
        s.is_solo = False
        s.pairing.setdefault("players", {})
        for pid in (P1, P2):
            s.pairing["players"].setdefault(pid, {})["deck"] = {"deckID": f"deck-{pid}"}
        s.game_stats = {P1: {"cardsdrawn": 9, "damagedealt": 230},
                        P2: {"cardsdrawn": 7, "damagedealt": 110}}
        added, decks = {}, {}

        def fake_add(account_id, **amounts):
            added[account_id] = amounts
            return amounts

        def fake_deck(account_id, deck_id, won):
            decks[account_id] = (deck_id, won)
            return {"overall_wins": int(won), "overall_played": 1,
                    "wins_since_last_edit": int(won), "played_since_last_edit": 1}

        async def run_db(fn, *a, **k):
            return fn(*a, **k)
        with patch('spirit.database.stats_data.add_player_stats', fake_add), \
                patch('spirit.database.stats_data.record_deck_result', fake_deck), \
                patch('spirit.game.session.game_session.run_db', run_db):
            await s._record_player_stats(P1, {P1: 10, P2: 50})
        self.assertEqual(added[P1]["cards_drawn"], 9)
        self.assertEqual(added[P1]["damage_dealt"], 230)
        self.assertEqual(added[P1]["damage_taken"], 110)
        self.assertEqual(added[P1]["upset_wins"], 1)          # beat a higher-ranked player
        self.assertEqual(added[P2]["upset_wins"], 0)
        self.assertEqual(added[P2]["games_played"], 1)
        self.assertEqual(decks[P1], (f"deck-{P1}", True))
        self.assertEqual(decks[P2], (f"deck-{P2}", False))
        pushed = [p for p in handlers[P1].sent
                  if p.get("messageName") == OutboundMsg.DECK_PROPERTIES_SAVED.value]
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0]["deckID"], f"deck-{P1}")
        values = {a["name"]: a["value"] for a in pushed[0]["attributes"]}
        self.assertEqual(values[ps.DECK_OVERALL_WINS], 1)
        self.assertEqual(handlers[P1].updated[0], f"deck-{P1}")

    async def test_solo_games_are_not_counted(self):
        t = Table(self)
        t.session.is_solo = True
        with patch('spirit.database.stats_data.add_player_stats') as add:
            await t.session._record_player_stats(P1, {})
        add.assert_not_called()


class Ping(unittest.IsolatedAsyncioTestCase):
    def test_thresholds_leave_room_for_stalls(self):
        from spirit.packets.handlers import auth
        disconnect_after = auth.NETWORK_PING_ERROR_MS * auth.NETWORK_PING_ERROR_COUNT
        self.assertGreaterEqual(disconnect_after, 30000)

    def test_ping_is_recognised_and_never_rate_limited(self):
        from spirit.server.client_handler import _is_ping
        self.assertTrue(_is_ping({"name": "Ping", "value": {}}, 0))
        self.assertTrue(_is_ping({}, WargFlags.PING_PONG))
        self.assertFalse(_is_ping({"name": "GetDeckList"}, 0))


if __name__ == '__main__':
    unittest.main()


class FriendInviteByAccount(unittest.IsolatedAsyncioTestCase):
    """Client audit (Oct 14): the client's CreateFriendInvitationWithAccountID
    had no handler, and FriendError's text is read from "msg"."""

    def setUp(self):
        from types import SimpleNamespace
        from spirit.packets.handlers.social import SocialHandler
        self.server = SimpleNamespace(clients=[], clients_by_account={})
        self.user = SimpleNamespace(server=self.server, running=True, addr=("h", 1),
                                    player=SimpleNamespace(account_id="me", screen_name="Me",
                                                           friends_list=Mock()),
                                    chat_rooms=set(), send_packet=AsyncMock())
        self.handler = SocialHandler(self.user)

    async def run_db(self, fn, *a, **k):
        return fn(*a, **k)

    async def test_invite_by_account_id_is_handled(self):
        from spirit.network.message_names import InboundMsg
        handlers = self.handler.get_handlers()
        self.assertIn(InboundMsg.CREATE_FRIEND_INVITATION_WITH_ACCOUNT_ID.value, handlers)
        added = []
        with patch('spirit.packets.handlers.social.run_db', self.run_db), \
                patch('spirit.packets.handlers.social.get_account_by_id',
                      return_value={"account_id": "them", "username": "Them"}), \
                patch('spirit.packets.handlers.social.get_friends_by_account_id', return_value=[]), \
                patch('spirit.packets.handlers.social.add_friend_relationship',
                      side_effect=lambda *a: added.append(a)):
            await self.handler.handle_create_friend_invitation_with_account_id(
                {"accountID": "them"}, 5, 0)
        self.assertEqual(added[0][:2], ("me", "them"))
        self.assertTrue(self.user.send_packet.await_count >= 1)

    async def test_unknown_account_error_text_reaches_the_client(self):
        with patch('spirit.packets.handlers.social.run_db', self.run_db), \
                patch('spirit.packets.handlers.social.get_account_by_id', return_value=None):
            await self.handler.handle_create_friend_invitation_with_account_id(
                {"accountID": "ghost"}, 5, 0)
        sent = self.user.send_packet.call_args.args[0]
        self.assertEqual(sent["messageName"], OutboundMsg.FRIEND_ERROR.value)
        self.assertTrue(sent["msg"])


class LogMiningOct14(unittest.IsolatedAsyncioTestCase):
    """Live-log mining (Oct 14): GetMotd was the most common unhandled
    request; the client's login command waits for Motd or NoMotdSet."""

    async def test_get_motd_answers_no_motd(self):
        from spirit.packets.handlers.data_sync import DataSyncHandler
        from spirit.network.message_names import InboundMsg
        client = Mock()
        client.send_packet = AsyncMock()
        handler = DataSyncHandler(client)
        self.assertIn(InboundMsg.GET_MOTD.value, handler.get_handlers())
        await handler.handle_get_motd({}, 7, 0)
        sent = client.send_packet.await_args.args[0]
        self.assertEqual(sent, {"messageName": "NoMotdSet"})
        self.assertEqual(client.send_packet.await_args.args[1], 7)


class LoadTimeout(unittest.IsolatedAsyncioTestCase):
    """Oct 14 (PlayerA vs a guest): the guest's client never sent
    PlayerReady, so the game never started and PlayerA sat on an empty board.
    After the load timeout the player who loaded wins (owner ruling)."""

    def make(self, ready):
        from tests.test_connection_notices import ConnectionNoticeTests, RecordingNetworkPlayer
        session = ConnectionNoticeTests.make_session(self)
        session._state_dispatched = False
        a, b = RecordingNetworkPlayer("loaded"), RecordingNetworkPlayer("stuck")
        a.username, b.username = "Loaded", "Stuck"
        session.players = {"loaded": a, "stuck": b}
        session.ready_players = set(ready)
        conceded = []

        async def concede(account_id, reason=None):
            conceded.append((account_id, reason))
        session.concede = concede
        return session, conceded

    async def test_stuck_player_loses(self):
        session, conceded = self.make({"loaded"})
        await session._watch_initial_load(timeout=0)
        self.assertEqual(conceded, [("stuck", "Stuck never finished loading")])

    async def test_nothing_happens_once_game_started(self):
        session, conceded = self.make({"loaded", "stuck"})
        session._state_dispatched = True
        await session._watch_initial_load(timeout=0)
        self.assertEqual(conceded, [])

    async def test_nobody_loaded_no_result(self):
        session, conceded = self.make(set())
        await session._watch_initial_load(timeout=0)
        self.assertEqual(conceded, [])

    def test_timeout_is_a_minute(self):
        from spirit.game.session.constants import LOAD_TIMEOUT_SECONDS
        self.assertEqual(LOAD_TIMEOUT_SECONDS, 60)
