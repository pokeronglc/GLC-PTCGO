"""Town Map turns Prizes face up; "look at your face-down Prize cards"
Trainers (Hisuian Heavy Ball, Beast Ball, Gladion) only see face-down ones."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.effects import EffectContext
from spirit.game.session.legal_actions import trainer_condition_met
from spirit.tools.effect_smoke import P1

PATHS = ('SWSH10.HisuianHeavyBall_146', 'SM7.BeastBall_125', 'SM4.Gladion_95')


class FaceUpPrizeTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    def test_not_playable_when_every_prize_is_face_up(self):
        for path in PATHS:
            with self.subTest(path=path):
                rig, e = self.rig(path, 'trainer')
                definition = fixtures.definition(path)
                prizes = rig.board.find_player_area(P1, 'prizePile').children
                self.assertTrue(trainer_condition_met(definition.condition, rig.board, P1, e['target']))
                for prize in prizes:
                    prize.publicly_revealed = True
                self.assertFalse(trainer_condition_met(definition.condition, rig.board, P1, e['target']))
                prizes[0].publicly_revealed = False
                self.assertTrue(trainer_condition_met(definition.condition, rig.board, P1, e['target']))

    async def test_heavy_ball_only_looks_at_face_down_prizes(self):
        rig, e = self.rig('SWSH10.HisuianHeavyBall_146', 'trainer')
        prizes = list(rig.board.find_player_area(P1, 'prizePile').children)
        for prize in prizes[1:]:
            prize.publicly_revealed = True
        picker = AsyncMock(return_value=None)
        with patch.object(rig.session, 'prompt_prize_reveal_pick', picker):
            await fixtures.definition('SWSH10.HisuianHeavyBall_146').effect(
                EffectContext(rig.session, P1, e['target'], None))
        shown = picker.call_args.args[2]
        self.assertEqual(shown, [prizes[0].entity_id])


if __name__ == "__main__":
    unittest.main()
