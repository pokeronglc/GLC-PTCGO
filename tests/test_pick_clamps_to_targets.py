"""'Choose 2 of your opponent's Benched Pokémon' with only 1 there must accept 1.

Player report: Celebrations Kyogre's Aqua Storm against a single Benched
Pokémon soft-locked -- the in-place picker demanded a second click that
could never happen."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2


class PickClampTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_aqua_storm_with_one_benched_pokemon(self):
        path = 'CEL25.Kyogre_3'
        rig, e = self.rig(path)
        bench = rig.board.find_player_area(P2, 'bench')
        discard = rig.board.find_player_area(P2, 'discard')
        if not bench.children:
            self.add(rig, fixtures.definition('BW7.Charmander_18'), P2, 'bench')
        for extra in list(bench.children)[1:]:
            rig.board.move_card(extra.entity_id, discard.entity_id)
        only = bench.children[0]
        self.assertEqual(len(bench.children), 1)

        seen = {}

        async def answer(pid, src, node, kind, valid, count, minimum, forced):
            seen.update(number=node['numberToSelect'], wire_min=node['minimumToSelect'],
                        count=count, minimum=minimum, valid=list(valid))
            return list(valid)

        attack = next(a for a in fixtures.definition(path).abilities if a.title == 'Aqua Storm')
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        with patch('spirit.game.session.game_session.AIPlayer', type('NotAI', (), {})), \
                patch.object(rig.session, '_run_pick_offer', side_effect=answer), \
                patch.object(rig.session, '_dismiss_pulled_out_picker_card', AsyncMock()):
            await attack.effect(ctx)

        self.assertEqual(seen['valid'], [only.entity_id])
        self.assertEqual(seen['number'], 1)
        self.assertEqual(seen['wire_min'], 1)
        self.assertEqual(seen['minimum'], 1)

    async def test_group_minimum_never_exceeds_its_cards(self):
        rig, e = self.rig('CEL25.Kyogre_3')
        hand = list(rig.board.find_player_area(P1, 'hand').children)[:1]
        seen = {}

        async def answer(pid, src, node, kind, valid, count, minimum, forced):
            seen['mins'] = [s['minimumToSelect'] for s in node['selections']]
            return list(valid)

        with patch('spirit.game.session.game_session.AIPlayer', type('NotAI', (), {})), \
                patch.object(rig.session, '_run_pick_offer', side_effect=answer):
            await rig.session.prompt_card_chooser_groups(
                P1, e['target'].entity_id,
                [{"cards": hand, "count": 2, "minimum": 2}])
        self.assertEqual(seen['mins'], [1])

    async def test_energy_payment_larger_than_attached_takes_all(self):
        rig, e = self.rig('CEL25.Kyogre_3')
        holder = e['target']
        energies = [c for c in holder.children
                    if type(c).__name__ == 'EnergyEntity'][:1]
        self.assertEqual(len(energies), 1)
        offer = AsyncMock()
        with patch('spirit.game.session.game_session.AIPlayer', type('NotAI', (), {})), \
                patch.object(rig.session, '_run_pick_offer', offer):
            picked = await rig.session.prompt_energy_unit_picker(
                P1, holder.entity_id, energies, 2)
        offer.assert_not_awaited()
        self.assertEqual(picked, [energies[0].entity_id])


if __name__ == "__main__":
    unittest.main()
