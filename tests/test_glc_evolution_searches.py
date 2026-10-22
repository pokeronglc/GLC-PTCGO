"""Evolution searches: Salvatore's effect, and GLC's Salvatore ruling for
Evosoda, Wally, Salvatore and TM Evolution (no use without a possible target).
https://gymleaderchallenge.com/faq
"""
import types
import unittest
from unittest import mock
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit import config
from spirit.game import glc
from spirit.game.attributes import AttrID
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1


class FakePokemon(types.SimpleNamespace):
    def get_attribute(self, attr_id, default=None):
        return self.attrs.get(attr_id, default)


def pokemon(path):
    card_def = fixtures.definition(path)
    from spirit.game.data_utils import _string_attr
    return FakePokemon(archetype_id=card_def.guid, children=[], attrs={
        AttrID.EVOLUTION_LOGIC_NAME: _string_attr(card_def, AttrID.EVOLUTION_LOGIC_NAME)})


class FakeBoard:
    def __init__(self, **zones):
        self.zones = zones

    def find_player_area(self, player_id, name):
        return types.SimpleNamespace(children=self.zones.get(name, []))


class SalvatoreRulingEvolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HgssRulesTests.setUpClass.__func__(cls)

    def allowed(self, targets, no_abilities=False, **zones):
        with mock.patch.object(config, "GLC_ONLY", True):
            return glc.evolution_search_allowed(
                FakeBoard(**zones), P1, targets, no_abilities=no_abilities)

    def test_ordinary_evolution_is_allowed(self):
        munna = pokemon('BW1.Munna_48')
        self.assertTrue(self.allowed([munna], activePokemonArea=[munna]))

    def test_evolution_already_public_blocks_it(self):
        munna = pokemon('BW1.Munna_48')
        self.assertFalse(self.allowed([munna], activePokemonArea=[munna],
                                      discard=[pokemon('BW1.Musharna_49')]))

    def test_no_evolution_of_the_deck_type_blocks_it(self):
        # Every Eeveelution has a type a Colorless deck can't contain.
        eevee = pokemon('BW5.Eevee_83')
        self.assertFalse(self.allowed([eevee], activePokemonArea=[eevee]))

    def test_salvatore_needs_an_evolution_without_abilities(self):
        charmander = pokemon('BW7.Charmander_18')
        self.assertTrue(self.allowed([charmander], no_abilities=True,
                                     activePokemonArea=[charmander]))

    def test_outside_glc_mode_nothing_is_blocked(self):
        eevee = pokemon('BW5.Eevee_83')
        with mock.patch.object(config, "GLC_ONLY", False):
            self.assertTrue(glc.evolution_search_allowed(
                FakeBoard(activePokemonArea=[eevee]), P1, [eevee]))


class SalvatoreEffectTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def play_salvatore(self, basic, evolution):
        rig, e = self.rig('SV05.Salvatore_160', 'trainer')
        target = self.add(rig, fixtures.definition(basic), P1, 'bench')
        card = self.add(rig, fixtures.definition(evolution), P1, 'deck')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        offered = []

        async def search_deck(predicate=None, count=1, **kw):
            offered.extend(c for c in ctx.deck() if predicate(c))
            return [card] if card in offered else []
        ctx.search_deck = search_deck
        ctx.choose_pokemon = AsyncMock(return_value=target)
        ctx.shuffle_deck = AsyncMock()
        # The rig's other Pokemon are of another type, which the GLC deck-type
        # filter (Oct 15: Evosoda/Salvatore only offer Pokemon that could still
        # evolve) would rightly reject; this test is about the Ability filter.
        with mock.patch.object(config, "GLC_ONLY", False):
            await fixtures.definition('SV05.Salvatore_160').effect(ctx)
        names = [def_for(p.archetype_id).display_name for p in rig.board.pokemon_in_play(P1)]
        return offered, names, ctx

    async def test_salvatore_evolves_into_a_card_without_abilities(self):
        offered, names, ctx = await self.play_salvatore('BW7.Charmander_18', 'BW7.Charmeleon_19')
        self.assertEqual({def_for(c.archetype_id).display_name for c in offered}, {'Charmeleon'})
        self.assertIn('Charmeleon', names)
        ctx.shuffle_deck.assert_awaited()

    async def test_salvatore_skips_evolutions_with_abilities(self):
        # Gardevoir NXD has the Psychic Mirage Ability.
        offered, names, _ = await self.play_salvatore('BW4.Kirlia_56', 'BW4.Gardevoir_57')
        self.assertEqual(offered, [])
        self.assertIn('Kirlia', names)


if __name__ == "__main__":
    unittest.main()
