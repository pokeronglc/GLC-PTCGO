"""Fixes from the second meta-list sweep: Lanturn's Salvage, Tate & Liza's
"Choose 1" and Ditto's Transform."""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext, is_item_card
from spirit.tools.effect_smoke import P1


def name(card):
    return def_for(card.archetype_id).display_name


class MetaSweepFixTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_salvage_only_shuffles_item_cards(self):
        path = 'SM8.Lanturn_74'
        rig, e = self.rig(path)
        for key in ('SV065.NightStretcher_61', 'BW7.Charmander_18', 'SV1.Nemona_180'):
            self.add(rig, fixtures.definition(key), P1, 'discard')
        ability = next(a for a in fixtures.definition(path).abilities if a.title == 'Salvage')
        ctx = EffectContext(rig.session, P1, e['target'], ability)
        offered = []

        async def choose(cards, count, **kw):
            offered.append(list(cards))
            return list(cards)[:count]
        ctx.choose_cards = choose
        await ability.effect(ctx)
        self.assertEqual(len(offered), 1)
        self.assertTrue(offered[0])
        self.assertTrue(all(is_item_card(c) for c in offered[0]))

    async def play_choice(self, path, pick):
        rig, e = self.rig(path, 'trainer')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        buttons = []

        async def choose(prompt, labels, *a, **k):
            buttons.append(labels)
            return pick
        ctx.choose = choose
        ctx.choose_pokemon = AsyncMock(side_effect=lambda c, *a, **k: list(c)[0] if c else None)
        hand_before = len(ctx.hand())
        active_before = ctx.my_active()
        await fixtures.definition(path).effect(ctx)
        for action in list(ctx.deferred_actions):
            await action()
        return buttons, ctx, hand_before, active_before

    async def test_tate_and_liza_offers_both_options(self):
        buttons, ctx, before, _ = await self.play_choice('SM7.TateLiza_148', 0)
        self.assertEqual(len(buttons[0]), 2)
        self.assertEqual(len(ctx.hand()), 5)

    async def test_tate_and_liza_switch_keeps_the_hand(self):
        buttons, ctx, before, active = await self.play_choice('SM7.TateLiza_148', 1)
        self.assertIsNot(ctx.my_active(), active)
        self.assertGreaterEqual(len(ctx.hand()), before - 1)

    def test_ditto_transform_stays_a_usable_ability(self):
        # Normalisation used to turn the un-"once" wording into an inert passive.
        ability = fixtures.definition('BW7.Ditto_108').abilities[0]
        self.assertIsNotNone(ability.effect)
        self.assertEqual(ability.activation, "once_per_turn")

    async def test_ditto_stays_underneath_after_transform(self):
        path = 'BW7.Ditto_108'
        rig, e = self.rig(path)
        ditto = e['target']
        basic = self.add(rig, fixtures.definition('BW7.Charmander_18'), P1, 'hand')
        ability = next(a for a in fixtures.definition(path).abilities if a.title == 'Transform')
        ctx = EffectContext(rig.session, P1, ditto, ability)
        ctx.choose_cards = AsyncMock(side_effect=lambda cards, n, **kw: [basic])
        await ability.effect(ctx)
        for action in list(ctx.deferred_actions):
            await action()
        self.assertIs(ctx.my_active(), basic)
        self.assertIn(ditto, basic.children)
        self.assertNotIn(ditto, ctx.discard_pile())


if __name__ == "__main__":
    unittest.main()
