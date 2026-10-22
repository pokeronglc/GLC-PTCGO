"""Oct 13 report (Cicada): after a reconnect a Benched Snom showed past the
right end of the Bench, its evolution stacked onto Wailord and it couldn't be
selected. Before the reconnect snapshot both Benches are re-numbered 0..n-1
(the snapshot then has no gaps to lay out), and the player still connected
gets the same re-numbering as same-Bench moves."""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.test_grace_claim_or_wait import net_player
from spirit.game.attributes import AttrID
from spirit.tools.effect_smoke import P1, P2


class ReconnectBenchSlots(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_benches_renumbered_without_gaps(self):
        t = Table(self)
        s = t.session
        s.players[P1] = net_player(P1, 'returning')
        s.players[P2] = net_player(P2, 'waiting')
        t.put(self.filler, P1, 'active'); t.put(self.filler, P2, 'active')
        mine = [t.put(self.filler, P1, 'bench') for _ in range(3)]
        theirs = [t.put(self.filler, P2, 'bench') for _ in range(2)]
        for card, slot in zip(mine, (0, 2, 4)):      # gaps at 1 and 3
            card.board_slot = slot
        for card, slot in zip(theirs, (1, 3)):
            card.board_slot = slot
        s.send_game_sequence = AsyncMock()
        await s._compact_benches_for_resync(P1)
        self.assertEqual([c.board_slot for c in mine], [0, 1, 2])
        self.assertEqual([c.board_slot for c in theirs], [0, 1])
        bench = t.board.find_player_area(P1, 'bench')
        self.assertEqual(sorted(t.board.bench_slot_of(c) for c in bench.children), [0, 1, 2])
        # Only the player still connected is sent the re-numbering moves.
        for call in s.send_game_sequence.await_args_list:
            self.assertEqual([p.account_id for p in call.args[0]], [P2])
        sent = sum(len(call.args[2]) for call in s.send_game_sequence.await_args_list)
        self.assertEqual(sent, 2 + 2)        # mine: slots 2,4 move; theirs: 1,3 move
        # The snapshot now lists no gaps inside the occupied range.
        state = t.board.serialize(P1)
        self.assertNotIn(0, bench.get_attribute(AttrID.AREA_EMPTY_SLOTS))
        self.assertTrue(all(g >= 3 for g in bench.get_attribute(AttrID.AREA_EMPTY_SLOTS)))


if __name__ == '__main__':
    unittest.main()
