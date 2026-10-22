"""Deck-search attacks and Abilities from the GLC meta list.

Joltik's Jolting Charge only allowed 2 Energy in total, and Pelipper's
Hearsay never offered its deck-search option.
"""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import PokemonTypes
from spirit.game.card_effects.pokemon import energy_provides_type
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1


class MetaPokemonSearchTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    basic_energy = meta.GlcMetaCardTests.basic_energy

    async def test_jolting_charge_two_grass_and_two_lightning(self):
        path = 'SV07.Joltik_150'
        rig, e = self.rig(path)
        for kind in (PokemonTypes.GRASS, PokemonTypes.LIGHTNING, PokemonTypes.WATER):
            for _ in range(3):
                self.basic_energy(rig, kind, zone='deck')
        ability = next(a for a in fixtures.definition(path).abilities if a.title == 'Jolting Charge')
        ctx = EffectContext(rig.session, P1, e['target'], ability)
        seen = []

        async def groups(specs, **kw):
            out = []
            for predicate, n, *_ in specs:
                eligible = [c for c in ctx.deck() if predicate(c)]
                seen.append((n, eligible))
                out.append(eligible[:n])
            return out
        ctx.search_deck_groups = groups
        ctx.choose_pokemon = AsyncMock(return_value=e['target'])
        ctx.shuffle_deck = AsyncMock()
        await ability.effect(ctx)
        self.assertEqual([n for n, _ in seen], [2, 2])
        self.assertTrue(all(energy_provides_type(c, PokemonTypes.GRASS.value) for c in seen[0][1]))
        self.assertTrue(all(energy_provides_type(c, PokemonTypes.LIGHTNING.value) for c in seen[1][1]))

    async def hearsay(self, button, discard_supporter=True):
        path = 'SV2.Pelipper_159'
        rig, e = self.rig(path)
        if discard_supporter:
            self.add(rig, fixtures.definition('SV1.Nemona_180'), P1, 'discard')
        in_deck = self.add(rig, fixtures.definition('SV065.ColresssTenacity_57'), P1, 'deck')
        ability = next(a for a in fixtures.definition(path).abilities if a.title == 'Hearsay')
        ctx = EffectContext(rig.session, P1, e['target'], ability)
        buttons = []

        async def choose(prompt, labels, *a, **k):
            buttons.append(labels)
            return labels.index(button)
        ctx.choose = choose
        ctx.choose_cards = AsyncMock(side_effect=lambda cards, n, **kw: list(cards)[:n])
        ctx.search_deck = AsyncMock(side_effect=lambda pred, count=1, **kw:
                                    [c for c in ctx.deck() if pred(c)][:count])
        ctx.shuffle_deck = AsyncMock()
        await ability.effect(ctx)
        return {def_for(c.archetype_id).display_name for c in ctx.hand()}, buttons, in_deck

    async def test_hearsay_can_search_the_deck(self):
        hand, buttons, _ = await self.hearsay("Search your deck for a Supporter")
        self.assertIn("Search your deck for a Supporter", buttons[0])
        self.assertIn("Colress's Tenacity", hand)

    async def test_hearsay_can_take_from_the_discard_pile(self):
        hand, _, _ = await self.hearsay("Supporter from discard pile")
        self.assertIn("Nemona", hand)

    async def test_hearsay_without_discarded_supporter_still_offers_the_deck(self):
        _, buttons, _ = await self.hearsay("Search your deck for a Supporter",
                                           discard_supporter=False)
        self.assertNotIn("Supporter from discard pile", buttons[0])


if __name__ == "__main__":
    unittest.main()
