"""Bug hunt 7 (Oct 13): what the clients are SENT during bot games.

tools: audits/results/wire/wire_check.py mirrors every packet each seat
receives into a client-side model and compares it with the server board at
every main-phase offer and after forced reconnect snapshots.

1. HP and Special Condition markers: wiping a Pokemon's damage/conditions as
   it leaves play (KO, Avery's discard, Scoop Up) was server-side only, so a
   Pokemon that came back into play showed its old damage / Poisoned to its
   owner.  NetworkPlayer.note_sent records what each client holds and
   _sync_condition_markers re-sends the real values at every main offer.
2. Mulligan hands go back to the deck still face-up on the clients; a card of
   one that is dealt as a Prize is re-hidden (AttributesReset) before the deal.
"""
import types
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, GameSequence
from spirit.game.session.constants import EMPTY_SEQUENCE_ID
from spirit.game.session.network_player import NetworkPlayer
from spirit.network.message_names import OutboundMsg
from spirit.tools.effect_smoke import P1, P2


def _names(mock):
    return [getattr(c.args[1], 'value', c.args[1]) for c in mock.call_args_list]


class FakeHandler:
    def __init__(self, pid):
        self.player = types.SimpleNamespace(account_id=pid, username=pid[:4],
                                            screen_name=pid[:4], avatar_decks=None)
        self.running = True
        self.sent = []

    async def send_packet(self, packet, request_id=0, flags=0):
        self.sent.append(packet)


def seat(session, pid):
    """Swap in a NetworkPlayer bound to a recording fake socket."""
    handler = FakeHandler(pid)
    session.players[pid] = NetworkPlayer(handler, {"piles": {"deck": []}})
    return handler


def msgs(handler, name=None):
    out = [p.get('msg') or {} for p in handler.sent]
    return [m for m in out if name is None or m.get('name') == name]


class WireSync(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def board(self):
        t = Table(self)
        self.mon = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        s = t.session
        self.h1, self.h2 = seat(s, P1), seat(s, P2)
        return t, s

    async def tell(self, s, *ms):
        for m in ms:
            await s.broadcast_packet(OutboundMsg.SEQUENCE_MESSAGE.value,
                                     s._sequence_envelope(EMPTY_SEQUENCE_ID, m))

    async def test_stale_condition_marker_cleared_on_reentry(self):
        t, s = self.board()
        mon = self.mon
        mon.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        await self.tell(s, s._condition_attr_msg(mon))   # clients see Poisoned
        s.clear_pokemon_effects(mon)                     # KO'd/scooped: server-side only
        self.h1.sent.clear(); self.h2.sent.clear()
        await s._sync_condition_markers()
        await s._sync_condition_markers()                # no repeat
        for h in (self.h1, self.h2):
            starts = [m['value']['name'] for m in msgs(h, 'StartSequence')]
            self.assertEqual(starts, [GameSequence.REMOVE_SPECIAL_CONDITION.value])
            cond = [m for m in msgs(h, 'AttributeModified')
                    if m['value']['attribute']['name'] == AttrID.SPECIAL_CONDITIONS.value]
            self.assertEqual([c['value']['attribute']['value'] for c in cond], [[]])

    async def test_stale_damage_resent_on_reentry(self):
        t, s = self.board()
        mon = self.mon
        full = mon.get_attribute(AttrID.HP)
        mon.set_attribute(AttrID.HP, full - 60)
        await self.tell(s, s._hp_attribute_msg(mon))     # clients see 60 damage
        mon.set_attribute(AttrID.HP, full)               # e.g. Avery discarded it, back via Stretcher
        self.h1.sent.clear(); self.h2.sent.clear()
        await s._sync_condition_markers()
        await s._sync_condition_markers()
        for h in (self.h1, self.h2):
            hp = [m['value']['attribute']['value'] for m in msgs(h, 'AttributeModified')
                  if m['value']['attribute']['name'] == AttrID.HP.value]
            self.assertEqual(hp, [full])

    async def test_no_traffic_when_clients_agree_or_never_told(self):
        t, s = self.board()
        t.put(self.filler, P1, 'bench')
        await self.tell(s, s._hp_attribute_msg(self.mon), s._condition_attr_msg(self.mon))
        self.h1.sent.clear(); self.h2.sent.clear()
        await s._sync_condition_markers()
        self.assertEqual(self.h1.sent + self.h2.sent, [])

    async def test_new_condition_not_yet_sent_uses_add_bracket(self):
        t, s = self.board()
        await self.tell(s, s._condition_attr_msg(self.mon))   # told: none
        self.mon.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])
        self.h1.sent.clear()
        await s._sync_condition_markers()
        starts = [m['value']['name'] for m in msgs(self.h1, 'StartSequence')]
        self.assertEqual(starts, [GameSequence.ADD_SPECIAL_CONDITION.value])

    async def test_snapshot_resets_what_the_client_holds(self):
        t, s = self.board()
        mon = self.mon
        mon.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Confused'])
        await self.tell(s, s._condition_attr_msg(mon))
        mon.set_attribute(AttrID.SPECIAL_CONDITIONS, [])
        await s.send_serialized_game_state(only_player_id=P1)  # reconnect: P1 now in step
        self.h1.sent.clear(); self.h2.sent.clear()
        await s._sync_condition_markers()
        self.assertEqual(msgs(self.h1, 'StartSequence'), [])
        self.assertEqual(len(msgs(self.h2, 'StartSequence')), 1)

    async def _deal(self, mark_mulligan):
        t = Table(self)
        s = t.session
        if mark_mulligan:
            for pid in (P1, P2):
                s._mulligan_returned_ids().update(
                    c.entity_id for c in t.zone(pid, 'deck'))
        send = AsyncMock()
        with patch.object(s, 'send_game_sequence', send):
            await s._deal_prize_cards()
        return send

    async def test_mulligan_cards_dealt_as_prizes_are_rehidden_first(self):
        send = await self._deal(True)
        self.assertEqual(_names(send), [GameSequence.GROUPED_MOVE.value,
                                        GameSequence.DEAL_INITIAL_PRIZE_CARDS.value])
        resets = send.call_args_list[0].args[2]
        self.assertEqual(len(resets), 12)
        self.assertTrue(all(m['name'] == 'AttributesReset' for m in resets))

    async def test_no_rehide_without_mulligan(self):
        send = await self._deal(False)
        self.assertEqual(_names(send), [GameSequence.DEAL_INITIAL_PRIZE_CARDS.value])


if __name__ == '__main__':
    unittest.main()
