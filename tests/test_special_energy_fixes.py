"""Special Energy sweep: Triple Acceleration Energy and Draw Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import PokemonTypes
from spirit.game.session.passives import energy_provided_options
from spirit.tools.effect_smoke import P1

C = PokemonTypes.COLORLESS.value


class SpecialEnergyFixTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def attach_from_hand(self, rig, energy_path, target):
        energy = self.add(rig, fixtures.definition(energy_path), P1, 'hand')
        await rig.session._execute_attach_energy(
            P1, energy, {'targetInfoLst': [{'validTargets': [target.entity_id]}]},
            [target.entity_id])
        return energy

    async def test_triple_acceleration_provides_three_on_an_evolution(self):
        rig, e = self.rig('BW7.Charmeleon_19')
        energy = await self.attach_from_hand(rig, 'SM10.TripleAccelerationEnergy_190', e['target'])
        self.assertIs(energy.parent, e['target'])
        self.assertEqual(energy_provided_options(rig.board, energy), [[C, C, C]])
        await rig.session._fire_end_of_turn_triggers(P1)
        self.assertIs(energy.parent, rig.board.find_player_area(P1, 'discard'))

    async def test_triple_acceleration_cannot_attach_to_a_basic(self):
        definition = fixtures.definition('SM10.TripleAccelerationEnergy_190')
        rig, e = self.rig('BW7.Charmander_18')
        self.assertFalse(definition.attach_to(e['target']))

    async def test_draw_energy_draws_a_card(self):
        rig, e = self.rig('BW7.Charmander_18')
        hand = rig.board.find_player_area(P1, 'hand')
        deck = rig.board.find_player_area(P1, 'deck')
        energy = self.add(rig, fixtures.definition('SM12.DrawEnergy_209'), P1, 'hand')
        hand_before, deck_before = len(hand.children), len(deck.children)
        await rig.session._execute_attach_energy(
            P1, energy, {'targetInfoLst': [{'validTargets': [e['target'].entity_id]}]},
            [e['target'].entity_id])
        self.assertEqual(len(hand.children), hand_before)        # -1 attached, +1 drawn
        self.assertEqual(len(deck.children), deck_before - 1)


if __name__ == "__main__":
    unittest.main()
