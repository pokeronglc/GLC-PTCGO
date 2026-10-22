"""Oct 22 reports."""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_repeatable_energy_attachment as rea
from spirit.game.attributes import PokemonTypes
from spirit.game.session.effects import resolve_activated_ability, is_energy_card
from spirit.tools.effect_smoke import P1, P2


class Oct22Reports(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(rea.RepeatableEnergyAttachmentTests.setUpClass.__func__)
    rig = rea.RepeatableEnergyAttachmentTests.rig
    add = rea.RepeatableEnergyAttachmentTests.add
    setup_case = rea.RepeatableEnergyAttachmentTests.setup_case

    async def test_draw_energy_draws_when_crazy_code_attaches_it(self):
        """Porygon-Z SM10 157 Crazy Code attaches from the hand, so Draw
        Energy's "when you attach this card from your hand" draws a card."""
        rig, source, ability, basic = self.setup_case(
            'SM10.PorygonZ_157', 'Crazy Code', PokemonTypes.WATER)
        draw = self.add(rig, fixtures.definition('SM12.DrawEnergy_209'), P1, 'hand')
        deck = rig.board.find_player_area(P1, 'deck')
        top = deck.children[-1]

        def pick(pid, sid, cards, *a, **k):
            if any(c is draw for c in cards):
                return [draw.entity_id]
            if all(is_energy_card(c) for c in cards):
                return []                       # Done
            return [cards[0].entity_id]         # the Pokémon to attach to
        rig.session.prompt_entity_picker = AsyncMock(side_effect=pick)
        ctx = await resolve_activated_ability(rig.session, P1, source, ability)
        self.assertIsNot(draw.parent, rig.board.find_player_area(P1, 'hand'))
        self.assertIn(top, ctx.hand())          # the card drawn by Draw Energy



class PeoniaNamedSpots(unittest.IsolatedAsyncioTestCase):
    """Peonia (owner report Oct 22: players can't tell where the Prizes go
    back): each card goes back into the spot a taken Prize came from, and the
    prompt names that Prize."""
    from tests import test_glc_meta_cards as _meta
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = _meta.GlcMetaCardTests.rig
    add = _meta.GlcMetaCardTests.add

    async def test_cards_go_back_where_the_taken_prizes_were(self):
        from tests.bughunt_table import Table
        from spirit.game.data_utils import def_for
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        pile = t.board.find_player_area(P1, 'prizePile')
        prizes = list(pile.children)
        chosen = [prizes[1], prizes[3], prizes[4]]          # scattered spots
        names = [def_for(c.archetype_id).display_name for c in chosen]
        # The test players take the first Prizes in the list, so record each
        # card's spot (as Peonia does) and list the chosen ones first.
        for index, card in enumerate(prizes):
            card.board_slot = index
        mine = [t.put('SM3.Guzma_115', P1, 'hand') for _ in range(3)]
        prompts, order = [], []

        def picks(cards, count, prompt, shown):
            prompts.append(prompt)
            if 'came from' in prompt:
                card = next(c for c in mine if c in cards)
                order.append(card)
                return [card]
            return list(cards)[:count]
        t.picks = picks

        async def prize_pick(player_id, ids, count, minimum=None, *a, **k):
            return [c.entity_id for c in chosen if c.entity_id in ids][:count]

        class NotAI:            # let the stub pick which Prizes are taken
            pass
        from unittest.mock import patch
        with patch('spirit.game.session.game_session.AIPlayer', NotAI), \
                patch.object(t.session, '_prompt_prize_pick', prize_pick):
            await t.play(t.put('SWSH6.Peonia_149', P1, 'hand'))
        self.assertTrue(all(c.parent is not pile for c in chosen))
        spot_prompts = [p for p in prompts if 'came from' in p]
        self.assertEqual(len(spot_prompts), 3)
        for prompt, name in zip(spot_prompts, names):
            self.assertIn(f'your {name} came from', prompt)
        self.assertEqual([c.board_slot for c in order], [1, 3, 4])
        self.assertTrue(all(c.parent is pile for c in order))


if __name__ == '__main__':
    unittest.main()
