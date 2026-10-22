"""Gladion SM4 95: take 1 Prize, shuffle Gladion into the remaining Prizes."""
import collections
import unittest
from unittest.mock import patch

from tests.test_player_reports_oct12_trainers import *  # noqa: F401,F403
from tests.test_player_reports_oct12_trainers import Oct12Trainers as Base
from spirit.tools.effect_smoke import P1

GLADION = 'SM4.Gladion_95'


class GladionPrizes(Base):
    async def play_gladion(self, t, pick):
        g = t.put(GLADION, P1, 'hand')
        sent = []
        real = t.session.send_game_sequence

        async def record(players, bracket, msgs):
            sent.append((list(players), list(msgs)))
            return await real(players, bracket, msgs)

        async def prize_pick(*a, **k):
            return pick.entity_id
        with patch.object(t.session, 'prompt_prize_reveal_pick', prize_pick), \
                patch.object(t.session, 'send_game_sequence', record):
            await t.play(g)
        return g, sent

    async def test_gladion_swaps_and_shuffles(self):
        t, prizes, basic = self.heavy_ball_table(2)
        before = len(prizes.children)
        g, sent = await self.play_gladion(t, basic)
        self.assertIn(basic, t.zone(P1, 'hand'))
        self.assertIn(g, prizes.children)
        self.assertEqual(len(prizes.children), before)
        told, moves = self.prize_shuffle_messages(sent, prizes)
        self.assertTrue(told)

    async def test_gladion_lands_in_random_slot(self):
        landed = collections.Counter()
        for n in range(24):
            t, prizes, basic = self.heavy_ball_table(n % 6)
            g, _ = await self.play_gladion(t, basic)
            landed[g.board_slot] += 1
        self.assertGreater(len(landed), 2)


for _n in [n for n in vars(Base) if n.startswith('test_')]:
    setattr(GladionPrizes, _n, None)


class HeavyBallReveal(GladionPrizes):
    async def test_opponent_gets_full_screen_reveal_of_the_basic(self):
        from tests.test_player_reports_oct12_trainers import HEAVY_BALL
        from spirit.network.message_names import OutboundMsg
        from spirit.tools.effect_smoke import P2
        t, prizes, basic = self.heavy_ball_table(1)
        ball, sent = await self.play_heavy_ball(t, basic)
        opp = t.session.players[P2]
        reveals = [m for players, msgs in sent if opp in players for m in msgs
                   if isinstance(m, dict) and m.get('name') == OutboundMsg.REVEAL_CARD_TO_ALL_EFFECT.value
                   and (m.get('value') or {}).get('entityID') == basic.entity_id]
        self.assertEqual(len(reveals), 1)

    async def test_gladion_is_not_revealed_to_opponent(self):
        from spirit.network.message_names import OutboundMsg
        from spirit.tools.effect_smoke import P2
        t, prizes, basic = self.heavy_ball_table(1)
        g, sent = await self.play_gladion(t, basic)
        opp = t.session.players[P2]
        reveals = [m for players, msgs in sent if opp in players for m in msgs
                   if isinstance(m, dict) and m.get('name') == OutboundMsg.REVEAL_CARD_TO_ALL_EFFECT.value
                   and (m.get('value') or {}).get('entityID') == basic.entity_id]
        self.assertEqual(reveals, [])


for _n in [n for n in vars(GladionPrizes) if n.startswith('test_')]:
    setattr(HeavyBallReveal, _n, None)
