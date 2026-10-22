"""Re-evolving and re-using Abilities after Devolution Spray / Spray Z /
Scoop Up Net:

* a devolved Pokemon can't evolve again that turn (Spray, Spray Z)
* a Basic scooped up and replayed is new: can't evolve that turn
* Forest of Vitality lifts both for Grass Pokemon
* a Pokemon that evolved this turn can't evolve again
* once-per-turn Abilities are fresh on a Pokemon that left play / evolved
"""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.effects import EffectContext
from spirit.game.session.legal_actions import compute_legal_actions
from spirit.tools.effect_smoke import P1, P2


class DevolveReevolveTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def can_evolve(self, rig, card, target):
        board, session = rig.board, rig.session
        return any(target.entity_id in info.get('validTargets', [])
                   for entry in compute_legal_actions(board, session.turn_state, P1, session.game_id)
                   if entry['entityID'] == card.entity_id
                   and entry['selectableAction']['description'] == 'EvolvePokemonPlayAbility'
                   for info in entry['targetInfoLst'])

    def stadium(self, rig, path):
        card = self.add(rig, fixtures.definition(path), P2, 'hand')
        rig.board.move_card(card.entity_id, rig.board.find_global_area('activeStadium').entity_id)

    async def evolved_last_turn(self, rig):
        """Roselia benched two turns ago, evolved into Roserade last turn."""
        session, ts = rig.session, rig.session.turn_state
        roselia = self.add(rig, fixtures.definition('SV05.Roselia_8'), P1, 'bench')
        ts.begin_turn(P2); ts.begin_turn(P1)
        roserade = self.add(rig, fixtures.definition('SV05.Roserade_9'), P1, 'hand')
        with patch.object(session, 'send_game_sequence', AsyncMock()):
            await session.perform_evolution(P1, roserade, roselia)
        ts.begin_turn(P2); ts.begin_turn(P1)
        return roselia, roserade

    async def spray(self, rig, path, target):
        card = self.add(rig, fixtures.definition(path), P1, 'hand')
        ctx = EffectContext(rig.session, P1, card, None)
        ctx.choose_pokemon = AsyncMock(return_value=target)
        ctx.choose = AsyncMock(return_value=0)
        with patch.object(rig.session, 'send_game_sequence', AsyncMock()):
            await fixtures.definition(path).effect(ctx)

    async def test_spray_blocks_reevolve_unless_forest(self):
        for spray in ('BW6.DevolutionSpray_113', 'XY10.DevolutionSpray_95', 'SM10.DevolutionSprayZ_166'):
            for forest in (False, True):
                with self.subTest(spray=spray, forest=forest):
                    rig, _ = self.rig('SM9.Moltres_19')
                    if forest:
                        self.stadium(rig, 'ME1.ForestofVitality_117')
                    roselia, roserade = await self.evolved_last_turn(rig)
                    await self.spray(rig, spray, roserade)
                    self.assertIn(roselia, rig.board.find_player_area(P1, 'bench').children)
                    again = self.add(rig, fixtures.definition('SV05.Roserade_9'), P1, 'hand')
                    self.assertEqual(self.can_evolve(rig, again, roselia), forest)

    async def test_scoop_up_net_replay_cant_evolve_unless_forest(self):
        for forest in (False, True):
            with self.subTest(forest=forest):
                rig, e = self.rig('SWSH2.ScoopUpNet_165', 'trainer')
                if forest:
                    self.stadium(rig, 'ME1.ForestofVitality_117')
                roselia, roserade = await self.evolved_last_turn(rig)
                ctx = EffectContext(rig.session, P1, e['target'], None)
                ctx.choose_pokemon = AsyncMock(return_value=roserade)
                with patch.object(rig.session, 'send_game_sequence', AsyncMock()):
                    await fixtures.definition('SWSH2.ScoopUpNet_165').effect(ctx)
                hand = rig.board.find_player_area(P1, 'hand')
                self.assertIn(roselia, hand.children)
                entry = next(a for a in compute_legal_actions(rig.board, rig.session.turn_state, P1,
                                                              rig.session.game_id)
                             if a['entityID'] == roselia.entity_id)
                with patch.object(rig.session, 'send_game_sequence', AsyncMock()), \
                     patch.object(rig.session, 'broadcast_packet', AsyncMock()):
                    await rig.session._apply_player_action(P1, entry, [])
                self.assertIn(roselia, rig.board.find_player_area(P1, 'bench').children)
                self.assertEqual(self.can_evolve(rig, roserade, roselia), forest)

    async def test_no_second_evolution_same_turn(self):
        rig, _ = self.rig('SM9.Moltres_19')
        session, ts = rig.session, rig.session.turn_state
        roselia = self.add(rig, fixtures.definition('SV05.Roselia_8'), P1, 'bench')
        ts.begin_turn(P2); ts.begin_turn(P1)
        roserade = self.add(rig, fixtures.definition('SV05.Roserade_9'), P1, 'hand')
        self.assertTrue(self.can_evolve(rig, roserade, roselia))
        with patch.object(session, 'send_game_sequence', AsyncMock()):
            await session.perform_evolution(P1, roserade, roselia)
        self.assertFalse(ts.may_evolve_target(roserade.entity_id))

    async def test_ability_fresh_after_leaving_play_and_after_evolving(self):
        rig, _ = self.rig('SM9.Moltres_19')
        session, ts = rig.session, rig.session.turn_state
        minccino = self.add(rig, fixtures.definition('SWSH1.Minccino_146'), P1, 'bench')
        ts.begin_turn(P2); ts.begin_turn(P1)
        cinccino = self.add(rig, fixtures.definition('SWSH1.Cinccino_147'), P1, 'hand')
        with patch.object(session, 'send_game_sequence', AsyncMock()):
            await session.perform_evolution(P1, cinccino, minccino)
        ability = next(a for a in fixtures.definition('SWSH1.Cinccino_147').abilities if a.title == 'Make Do')
        ts.used_abilities.add((cinccino.entity_id, ability.ability_id))
        # Devolution Spray returns Cinccino to hand: a fresh card again.
        await self.spray(rig, 'BW6.DevolutionSpray_113', cinccino)
        self.assertIn(cinccino, rig.board.find_player_area(P1, 'hand').children)
        self.assertNotIn((cinccino.entity_id, ability.ability_id), ts.used_abilities)
        # Evolving gives the Pokemon underneath fresh Abilities too.
        ts.used_abilities.add((minccino.entity_id, 'x'))
        ts.begin_turn(P2); ts.begin_turn(P1)
        with patch.object(session, 'send_game_sequence', AsyncMock()):
            await session.perform_evolution(P1, cinccino, minccino)
        self.assertNotIn((minccino.entity_id, 'x'), ts.used_abilities)


if __name__ == "__main__":
    unittest.main()
