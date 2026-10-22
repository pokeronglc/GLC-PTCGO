"""Ranked queue / friend challenges refuse decks that break GLC rules."""
import copy
import unittest
from unittest.mock import patch

from spirit import config
from spirit.game.data_utils import CARD_DEFS_BY_GUID, TrainerCardDef
from spirit.game.scripts.cards import loader
from spirit.game.session.manager import deck_rejection
from spirit.game.starter_content import BOT_DECKS, build_deck_data


class MatchDeckGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not loader.cards:
            loader.load_all()

    def test_legal_glc_deck_is_accepted_and_duplicates_refused(self):
        name, decklist = BOT_DECKS[0]
        deck = build_deck_data(name, decklist)
        with patch.object(config, "GLC_ONLY", True):
            self.assertIsNone(deck_rejection(deck))
            bad = copy.deepcopy(deck)
            pile = bad["piles"]["deck"]
            trainer = next(g for g in pile
                           if isinstance(CARD_DEFS_BY_GUID.get(g.lower()), TrainerCardDef))
            other = next(g for g in pile
                         if g != trainer
                         and not isinstance(CARD_DEFS_BY_GUID.get(g.lower()), TrainerCardDef))
            pile[pile.index(other)] = trainer
            self.assertIn("one copy", deck_rejection(bad))
            self.assertIsNotNone(deck_rejection({}))

    def test_gate_is_off_outside_glc_mode(self):
        with patch.object(config, "GLC_ONLY", False):
            self.assertIsNone(deck_rejection({}))


if __name__ == "__main__":
    unittest.main()


class FriendChallengeLookupTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, server, account_id):
        from types import SimpleNamespace
        client = SimpleNamespace(server=server, running=True, sent=[],
                                 player=SimpleNamespace(account_id=account_id,
                                                        username=account_id))

        async def send_packet(packet, request_id=0, **kwargs):
            client.sent.append(packet)
        client.send_packet = send_packet
        return client

    async def test_offline_friend_challenge_corrects_presence(self):
        from types import SimpleNamespace
        from spirit.game.session.manager import GameSessionManager
        server = SimpleNamespace(clients_by_account={}, clients=[])
        me = self._client(server, "me")
        server.clients_by_account["me"] = me
        with patch.object(config, "GLC_ONLY", False):
            await GameSessionManager().create_challenge(me, "ghost", {}, {})
        names = [p.get("messageName") for p in me.sent]
        self.assertIn("FriendPresence", names)
        presence = next(p for p in me.sent if p.get("messageName") == "FriendPresence")
        self.assertEqual((presence["accountID"], presence["presence"]), ("ghost", "Offline"))

    def test_lookup_tolerates_case_and_skips_dead_sockets(self):
        from types import SimpleNamespace
        from spirit.game.session.manager import GameSessionManager
        server = SimpleNamespace(clients_by_account={}, clients=[])
        me = self._client(server, "me")
        friend = self._client(server, "AbC-1")
        server.clients_by_account.update({"me": me, "AbC-1": friend})
        manager = GameSessionManager()
        self.assertIs(manager._find_online_client(me, "abc-1"), friend)
        friend.running = False
        self.assertIsNone(manager._find_online_client(me, "AbC-1"))
