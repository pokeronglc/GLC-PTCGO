"""Player reports Oct 13 (evening).

1. Mewtwo SM Promo 214 Mind Report: the Supporter put from the discard pile
   on top of the deck was never shown to the opponent (reveal_cards skipped
   cards nobody is blind to).  Same for the sibling "discard -> top of deck"
   wordings.
2. Munkidori SV06 95 Adrena-Brain onto a Pokemon shielded from Ability
   effects (Stealthy Hood): no counters land, and (owner ruling) they still
   come OFF the source -- before, the whole move fizzled and they stayed.
3. Welder: players confirmed the "up to 2" Energy picker with nothing picked,
   were then asked for a Pokemon, and nothing was attached or drawn.  A
   Trainer/Ability "up to" hand attach now needs at least 1 pick, and no
   Pokemon is asked for when nothing was picked.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.test_bughunt12_wire import seat, msgs
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

MEWTWO, MUNKIDORI, HOOD = 'Promo_SM.Mewtwo_214', 'SV06.Munkidori_95', 'SM10.StealthyHood_186'
WELDERS = ['SM10.Welder_189', 'SM10.Welder_214', 'SM10.Welder_237']


class Reports(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # --- Mewtwo -----------------------------------------------------------
    async def test_mind_report_shows_the_supporter_to_the_opponent(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        supporter = t.put('SM10.Welder_189', P1, 'discard')
        mewtwo = t.put(MEWTWO, P1, 'hand')
        h1, h2 = seat(t.session, P1), seat(t.session, P2)
        await t.play(mewtwo)
        self.assertIs(t.zone(P1, 'deck')[-1], supporter)        # on top
        reveals = [m['value']['entityID'] for m in msgs(h2, 'RevealCardToAllEffect')]
        self.assertIn(supporter.entity_id, reveals)

    # --- Munkidori ---------------------------------------------------------
    async def adrena(self, shielded):
        t = Table(self)
        munk = t.put(MUNKIDORI, P1, 'active')
        t.energy(munk, PokemonTypes.DARKNESS)
        hurt = t.put(self.filler, P1, 'bench')
        full = t.hp(hurt)
        hurt.set_attribute(AttrID.HP, full - 50)
        opp = t.put(self.filler, P2, 'active')
        if shielded:
            hood = t.put(HOOD, P2, 'hand')
            t.next_turn()
            await t.play(hood, pid=P2, targets=[opp.entity_id])
            t.next_turn()
        before = t.hp(opp)
        t.pokemon = lambda cands, prompt: hurt if hurt in cands else opp
        await t.use(munk, 'Adrena-Brain')
        return full - t.hp(hurt), before - t.hp(opp)

    async def test_adrena_brain_normal(self):
        self.assertEqual(await self.adrena(False), (40, 10))   # 1 counter moved

    async def test_adrena_brain_onto_shielded_pokemon_counters_vanish(self):
        self.assertEqual(await self.adrena(True), (40, 0))     # off the source, never placed

    # --- Welder ------------------------------------------------------------
    async def welder(self, spec, fires=2):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.put(self.filler, P2, 'active')
        energy = [t.put(t.basic_energy(PokemonTypes.FIRE), P1, 'hand') for _ in range(fires)]
        card = t.put(spec, P1, 'hand')
        seen = {}

        def picks(cards, count, prompt, shown):
            seen.setdefault(prompt, []).append(count)
            return cards[:count]
        t.picks = picks
        t.pokemon = lambda cands, prompt: me
        return t, me, energy, card, seen

    async def test_welder_attaches_and_draws(self):
        for spec in WELDERS:
            with self.subTest(spec):
                t, me, energy, card, _ = await self.welder(spec)
                hand = len(t.zone(P1, 'hand'))
                await t.play(card)
                self.assertTrue(all(e in me.children for e in energy))
                self.assertEqual(len(t.zone(P1, 'hand')), hand - 3 + 3)

    async def test_welder_energy_pick_needs_at_least_one(self):
        """All three printings (189, 214 full art, 237 secret) share one effect."""
        from unittest.mock import patch
        from spirit.game.session.effects import EffectContext as Ctx
        for spec in WELDERS:
            with self.subTest(spec):
                t, me, energy, card, seen = await self.welder(spec)
                mins = []

                async def spy(ctx, cards, count, minimum=None, prompt='', **k):
                    mins.append(minimum)
                    return []                          # player confirms with nothing
                t.prompts.clear()
                with patch.object(Ctx, 'choose_cards', spy):
                    await t.session._apply_player_action(
                        P1, next(iter(t.offers(card, 'UseTrainerCard'))), [], None)
                self.assertEqual(mins, [1])
                self.assertNotIn('Choose a Pokémon', t.prompts)

if __name__ == '__main__':
    unittest.main()
