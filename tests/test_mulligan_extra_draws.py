"""Owner rule (Oct 12): extra cards for an opponent's mulligans are chosen
in ONE prompt -- any number up to the total, decided before drawing -- and
after drawing the player may bench Basic Pokémon again before the game
starts."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.session.game_session import GameSession
from spirit.tools.effect_smoke import P1, P2


class MulliganExtraDraws(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    def setup(self, answer):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.deck(P1, [self.filler] * 3)          # top cards are Basics
        prompts, benches = [], []

        async def choice(session, pid, prompt, buttons, sort_type='', timeout_default=None):
            prompts.append((pid, prompt, list(buttons), timeout_default))
            return answer(buttons) if callable(answer) else answer

        async def bench(session, pid, done):
            benches.append(pid)
            area = session.board_state.find_player_area(pid, 'bench')
            for card in session.board_state.setup_bench_candidates(pid):
                await session._place_setup_card(pid, card.entity_id, area)
            done.add(pid)
        return t, prompts, benches, choice, bench

    async def run_offer(self, t, choice, bench, counts):
        with patch.object(GameSession, 'prompt_player_choice', choice), \
                patch.object(GameSession, '_run_bench_placement', bench):
            await t.session._offer_extra_draws(counts)

    async def test_one_question_for_all_cards_then_bench_again(self):
        t, prompts, benches, choice, bench = self.setup(answer=0)
        hand0 = len(t.zone(P1, 'hand'))
        await self.run_offer(t, choice, bench, {P1: 0, P2: 3})
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0][0], P1)
        self.assertIn('up to 3', prompts[0][1])
        self.assertEqual(prompts[0][2], ['Draw 3', 'Draw 2', 'Draw 1', "Don't draw"])
        self.assertEqual(prompts[0][3], 3)          # timeout = don't draw
        self.assertEqual(benches, [P1])
        self.assertEqual(len(t.zone(P1, 'bench')), 3)      # the 3 drawn Basics
        self.assertEqual(len(t.zone(P1, 'hand')), hand0)

    async def test_can_choose_fewer(self):
        t, prompts, benches, choice, bench = self.setup(
            answer=lambda buttons: list(buttons).index('Draw 1'))
        await self.run_offer(t, choice, bench, {P1: 0, P2: 3})
        self.assertEqual(len(prompts), 1)
        self.assertEqual(benches, [P1])
        self.assertEqual(len(t.zone(P1, 'bench')), 1)

    async def test_declining_draws_nothing_and_skips_bench_round(self):
        t, prompts, benches, choice, bench = self.setup(answer=2)
        hand0 = len(t.zone(P1, 'hand'))
        await self.run_offer(t, choice, bench, {P1: 0, P2: 2})
        self.assertEqual(len(prompts), 1)
        self.assertEqual(benches, [])
        self.assertEqual(len(t.zone(P1, 'hand')), hand0)

    async def test_single_mulligan_keeps_original_wording(self):
        t, prompts, benches, choice, bench = self.setup(answer=0)
        await self.run_offer(t, choice, bench, {P1: 1, P2: 2})
        self.assertEqual(len(prompts), 1)
        self.assertIn('an extra card', prompts[0][1])
        self.assertEqual(len(t.zone(P1, 'bench')), 1)


if __name__ == '__main__':
    unittest.main()
