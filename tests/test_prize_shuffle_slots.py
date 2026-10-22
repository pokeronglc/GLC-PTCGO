"""Gladion / Hisuian Heavy Ball / Beast Ball: "shuffle your face-down Prize
cards" must move the cards to new grid slots on the client, not just reorder
the server's list (the client lays Prizes out by slot)."""
import random
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1


def _slot_map(prizes):
    return {c.entity_id: (c.board_slot if c.board_slot is not None else i)
            for i, c in enumerate(prizes.children)}


class PrizeShuffleSlotTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def _play(self, path, pick_index):
        rig, e = self.rig(path, 'trainer')
        prizes = rig.board.find_player_area(P1, 'prizePile')
        for i, c in enumerate(prizes.children):
            c.board_slot = i
        picked = prizes.children[pick_index]
        vacated = picked.board_slot
        sent = []

        async def record(players, bracket, msgs):
            sent.extend(msgs)

        async def pick(*args, **kwargs):
            return picked.entity_id

        with patch.object(rig.session, 'prompt_prize_reveal_pick', pick), \
             patch.object(rig.session, 'send_game_sequence', record), \
             patch.object(EffectContext, 'reveal_cards', AsyncMock()):
            await fixtures.definition(path).effect(
                EffectContext(rig.session, P1, e['target'], None))
        return rig, prizes, e['target'], vacated, sent

    async def test_gladion_does_not_stay_in_the_vacated_slot_every_time(self):
        landed = set()
        for seed in range(20):
            random.seed(seed)
            rig, prizes, gladion, vacated, sent = await self._play('SM4.Gladion_95', 0)
            self.assertIn(gladion, prizes.children)
            slots = _slot_map(prizes)
            self.assertEqual(sorted(slots.values()), sorted(set(slots.values())))
            landed.add(slots[gladion.entity_id])
            moves = [m for m in sent if 'positionInParent' in str(m)
                     and prizes.entity_id in str(m)]
            self.assertTrue(moves)
        self.assertGreater(len(landed), 2)

    async def test_face_up_prizes_keep_their_slot(self):
        rig, e = self.rig('SM4.Gladion_95', 'trainer')
        prizes = rig.board.find_player_area(P1, 'prizePile')
        for i, c in enumerate(prizes.children):
            c.board_slot = i
        face_up = prizes.children[-1]
        face_up.publicly_revealed = True
        before = face_up.board_slot
        ctx = EffectContext(rig.session, P1, e['target'], None)
        for _ in range(10):
            msgs = ctx._redeal_face_down_prizes(prizes)
            for m in msgs:
                self.assertNotIn(face_up.entity_id, str(m))
        self.assertEqual(face_up.board_slot, before)
        self.assertEqual(sorted(_slot_map(prizes).values()), list(range(len(prizes.children))))


if __name__ == "__main__":
    unittest.main()
