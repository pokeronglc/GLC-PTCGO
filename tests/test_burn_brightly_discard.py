"""Energy discarded by an attack counts provided Energy, not cards.

Charizard (Pokémon GO 10) "Burn Brightly": each basic Fire Energy attached to
your Pokémon provides Fire Fire.  "Discard 2 Energy" is then paid by a single
basic Fire Energy card.
"""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from spirit.game.attributes import PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1


class BurnBrightlyDiscardTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig
    add = fixtures.HgssRulesTests.add

    async def discarded_cards(self, path, title, charizard=True):
        rig, e = self.rig(path)
        blaziken = e['target']
        for energy in list(rig.board.attached_energies(blaziken)):
            rig.to_area(energy, P1, 'hand')
        fire = CARD_DEFS_BY_GUID[self.energies[PokemonTypes.FIRE.value].lower()]
        attached = [self.add(rig, fire, P1, 'hand') for _ in range(3)]
        for card in attached:
            rig.attach(card, blaziken)
        if charizard:
            self.add(rig, fixtures.definition('PGO.Charizard_10'), P1, 'bench')
        ability = next(a for a in fixtures.definition(path).abilities if a.title == title)
        ctx = EffectContext(rig.session, P1, blaziken, ability)
        ctx.choose_pokemon = AsyncMock(return_value=ctx.opponent_active())
        ctx.choose_cards = AsyncMock(side_effect=lambda cards, n, **kw: list(cards)[:n])
        await ability.effect(ctx)
        for action in list(ctx.deferred_actions):
            await action()
        return [card for card in attached if card in ctx.discard_pile()]

    async def test_one_card_pays_two_energy_with_burn_brightly(self):
        for path, title in (('XY3.Blaziken_14', 'Burning Shot'),
                            ('SV10.Blaziken_42', 'Inferno Kick Flurry')):
            with self.subTest(path=path):
                self.assertEqual(len(await self.discarded_cards(path, title)), 1)

    async def test_two_cards_without_burn_brightly(self):
        for path, title in (('XY3.Blaziken_14', 'Burning Shot'),
                            ('SV10.Blaziken_42', 'Inferno Kick Flurry')):
            with self.subTest(path=path):
                self.assertEqual(
                    len(await self.discarded_cards(path, title, charizard=False)), 2)

    async def test_client_picking_two_cards_only_discards_one(self):
        # The client's pip tray counts printed Energy (1 per basic), so a
        # human is made to tick two basic Fire Energy.  Only one is needed.
        from spirit.game.session.ai_player import AIPlayer
        rig, e = self.rig('SV10.Blaziken_42')
        blaziken = e['target']
        for energy in list(rig.board.attached_energies(blaziken)):
            rig.to_area(energy, P1, 'hand')
        fire = CARD_DEFS_BY_GUID[self.energies[PokemonTypes.FIRE.value].lower()]
        attached = [self.add(rig, fire, P1, 'hand') for _ in range(3)]
        for card in attached:
            rig.attach(card, blaziken)
        self.add(rig, fixtures.definition('PGO.Charizard_10'), P1, 'bench')
        picked = [attached[0].entity_id, attached[1].entity_id]
        session = rig.session
        with patch.object(type(session), '_run_pick_offer', AsyncMock(return_value=picked)), \
                patch.object(type(session), '_dismiss_pulled_out_picker_card', AsyncMock()), \
                patch.dict(session.players, {P1: object()}):
            self.assertNotIsInstance(session.players[P1], AIPlayer)
            ids = await session.prompt_energy_unit_picker(
                P1, blaziken.entity_id, attached, 2)
        self.assertEqual(ids, [attached[0].entity_id])

    def test_trim_keeps_needed_cards(self):
        from spirit.game.session.legal_actions import trim_energy_overpayment
        class E:
            def __init__(self, n): self.n = n
        with patch('spirit.game.session.legal_actions.energy_provided_count',
                   lambda e, board=None: e.n):
            a, b, c = E(1), E(2), E(1)
            self.assertEqual(trim_energy_overpayment([a, b], 2), [b])
            self.assertEqual(trim_energy_overpayment([a, c], 2), [a, c])
            self.assertEqual(trim_energy_overpayment([b, a], 2), [b])


if __name__ == "__main__":
    unittest.main()
