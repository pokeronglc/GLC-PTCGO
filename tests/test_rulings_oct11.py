"""Server owner's rulings (Oct 11):
1. Trainers/Abilities picking from public information (discard pile) must
   take at least 1 card when one exists; attacks / deck searches may take 0.
2. Sightseer and Naveen can't be played with 5+ other cards in hand.
3. Paint Roller can't be played without a Stadium in play."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from spirit.game.session.effects import EffectContext
from spirit.game.session.game_session import GameSession
from spirit.game.session.legal_actions import trainer_condition_met
from spirit.tools.effect_smoke import P1, P2


class RulingsOct11(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig
    add = fixtures.HgssRulesTests.add

    def capture(self):
        seen = []

        async def chooser(session, pid, src, cards, count, minimum=None, *a, **k):
            seen.append(minimum)
            return [c.entity_id for c in cards][:max(minimum or 0, 0)]
        return seen, chooser

    async def test_trainer_up_to_from_discard_needs_one(self):
        rig, e = self.rig('SM11.Aegislash_95')
        card = self.add(rig, fixtures.definition('SV2.SuperRod_188'), P1, 'hand')
        self.add(rig, self.filler, P1, 'discard')
        seen, chooser = self.capture()
        ctx = EffectContext(rig.session, P1, card, None)
        ctx.is_trainer_effect = True
        with patch.object(GameSession, 'prompt_card_chooser', chooser), \
                patch.object(GameSession, 'prompt_entity_picker', chooser):
            await ctx.choose_cards(list(ctx.discard_pile()), 3, minimum=0)
        self.assertEqual(seen, [1])

    async def test_attack_up_to_from_discard_may_take_none(self):
        rig, e = self.rig('SM11.Aegislash_95')
        self.add(rig, self.filler, P1, 'discard')
        seen, chooser = self.capture()
        attack = next(a for a in fixtures.definition('SM11.Aegislash_95').abilities
                      if a.ability_type is not None and hasattr(a, 'damage'))
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        with patch.object(GameSession, 'prompt_card_chooser', chooser), \
                patch.object(GameSession, 'prompt_entity_picker', chooser):
            await ctx.choose_cards(list(ctx.discard_pile()), 3, minimum=0)
        self.assertEqual(seen, [0])

    async def test_trainer_deck_search_may_take_none(self):
        rig, e = self.rig('SM11.Aegislash_95')
        card = self.add(rig, fixtures.definition('SV2.SuperRod_188'), P1, 'hand')
        self.add(rig, self.filler, P1, 'deck')
        seen, chooser = self.capture()
        ctx = EffectContext(rig.session, P1, card, None)
        ctx.is_trainer_effect = True
        with patch.object(GameSession, 'prompt_card_chooser', chooser), \
                patch.object(GameSession, 'prompt_entity_picker', chooser):
            await ctx.choose_cards(list(ctx.deck())[:1], 1, minimum=0)
        self.assertEqual(seen, [0])

    def _playable(self, rig, path, hand_extra=0, stadium=False):
        d = fixtures.definition(path)
        card = self.add(rig, d, P1, 'hand')
        for _ in range(hand_extra):
            self.add(rig, self.filler, P1, 'hand')
        if stadium:
            st = self.add(rig, fixtures.definition('SWSH35.TurffieldStadium_68'), P1, 'hand')
            rig.board.move_card(st.entity_id, rig.board.find_global_area('activeStadium').entity_id)
        return trainer_condition_met(d.condition, rig.board, P1, card)

    def hand_size(self, rig):
        return len(rig.board.find_player_area(P1, 'hand').children)

    def test_sightseer_and_naveen_blocked_at_five_other_cards(self):
        for path in ('SM8.Sightseer_189', 'ME3.Naveen_79'):
            rig, _ = self.rig('SM11.Aegislash_95')
            for c in list(rig.board.find_player_area(P1, 'hand').children):
                rig.board.move_card(c.entity_id, rig.board.find_player_area(P1, 'discard').entity_id)
            d = fixtures.definition(path)
            card = self.add(rig, d, P1, 'hand')
            for _ in range(5):
                self.add(rig, self.filler, P1, 'hand')
            self.assertFalse(trainer_condition_met(d.condition, rig.board, P1, card), path)
            rig.board.move_card(rig.board.find_player_area(P1, 'hand').children[-1].entity_id,
                                rig.board.find_player_area(P1, 'discard').entity_id)
            self.assertTrue(trainer_condition_met(d.condition, rig.board, P1, card), path)

    def test_paint_roller_needs_a_stadium(self):
        rig, _ = self.rig('SM11.Aegislash_95')
        self.assertFalse(self._playable(rig, 'XY7.PaintRoller_79'))
        rig, _ = self.rig('SM11.Aegislash_95')
        self.assertTrue(self._playable(rig, 'XY7.PaintRoller_79', stadium=True))


if __name__ == "__main__":
    unittest.main()


class BoardPicksArePublic(unittest.IsolatedAsyncioTestCase):
    """Oct 11 ruling, part 2: 'choose up to 2 of your Benched Pokémon' on a
    Trainer must take at least 1; a single optional board pick stays optional."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig
    add = fixtures.HgssRulesTests.add

    async def pick(self, count):
        rig, e = self.rig('SM11.Aegislash_95')
        b1 = self.add(rig, self.filler, P1, 'bench')
        b2 = self.add(rig, self.filler, P1, 'bench')
        card = self.add(rig, fixtures.definition('SV2.SuperRod_188'), P1, 'hand')
        seen = []

        async def chooser(session, pid, src, cards, n, minimum=None, *a, **k):
            seen.append(minimum)
            return []
        ctx = EffectContext(rig.session, P1, card, None)
        ctx.is_trainer_effect = True
        with patch.object(GameSession, 'prompt_card_chooser', chooser), \
                patch.object(GameSession, 'prompt_entity_picker', chooser):
            await ctx.choose_cards([b1, b2], count, minimum=0)
        return seen

    async def test_up_to_two_benched_needs_one(self):
        self.assertEqual(await self.pick(2), [1])

    async def test_single_optional_board_pick_stays_optional(self):
        self.assertEqual(await self.pick(1), [0])
