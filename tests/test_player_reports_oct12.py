"""Player reports, Oct 12: Melmetal SCR 104 Reforged Axe, Floette CEC 151
Flower Picking, Metagross Meteor Mash after devolve/evolve."""
import random
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

METAL, FAIRY = PokemonTypes.METAL, PokemonTypes.FAIRY

MELMETAL = 'SV07.Melmetal_104'
UTURN = 'SM11.UTurnBoard_211'
ESCAPE = 'SM5.EscapeBoard_122'
JIRACHI = 'Promo_XY.Jirachi_67'
FLABEBE = 'SM6.Flabb_84'
FLOETTE = 'SM12.Floette_151'
FLORGES = 'SM12.Florges_152'
METANG = 'SV05.Metang_114'
METAGROSS = ('SV05.Metagross_115', 'SM7.Metagross_95', 'SWSH12.Metagross_119')


def name(card):
    return def_for(card.archetype_id).display_name


class PlayerReportsOct12(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p, hp=None):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def table(self, hp=600):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), hp)
        self.opp_full = hp
        return t

    def dealt(self, t):
        return self.opp_full - t.hp(self.opp)

    # -- Melmetal SCR 104: Reforged Axe ---------------------------------
    async def test_reforged_axe_discards_only_this_pokemons_tools(self):
        t = self.table()
        melmetal = self.neutral(t.put(MELMETAL, P1, 'active'))
        t.energy(melmetal, METAL, 3)
        uturn = t.attach(UTURN, melmetal)
        jirachi = t.put(JIRACHI, P1, 'bench')
        escape = t.attach(ESCAPE, jirachi)
        opp_tool = t.attach(ESCAPE, self.opp)
        await t.attack(melmetal, 'Reforged Axe')
        # U-Turn Board goes to the hand instead of the discard pile.
        self.assertIn(uturn, t.zone(P1, 'hand'))
        self.assertIs(escape.parent, jirachi)     # benched Jirachi keeps its Tool
        self.assertIs(opp_tool.parent, self.opp)  # opponent's Tool untouched
        self.assertEqual(self.dealt(t), 250)

    async def test_reforged_axe_does_nothing_without_own_tool(self):
        t = self.table()
        melmetal = self.neutral(t.put(MELMETAL, P1, 'active'))
        t.energy(melmetal, METAL, 3)
        jirachi = t.put(JIRACHI, P1, 'bench')
        escape = t.attach(ESCAPE, jirachi)
        await t.attack(melmetal, 'Reforged Axe')
        self.assertIs(escape.parent, jirachi)
        self.assertEqual(self.dealt(t), 0)

    # -- Floette CEC 151 / Florges CEC 152: Flower Picking --------------
    async def _flower_picking(self, evolution, base):
        t = self.table()
        target = self.neutral(t.put(base, P1, 'bench'))
        card = t.put(evolution, P1, 'hand')
        hand = [t.put(self.item, P2, 'hand') for _ in range(4)]
        sampled = []
        real = random.sample

        def sample(population, k, *a, **kw):
            out = real(population, k, *a, **kw)
            sampled.append((len(list(population)), k))
            return out

        revealed = []
        real_reveal = EffectContext.reveal_cards

        async def reveal(ctx, cards, *a, **kw):
            revealed.append(list(cards))
            return await real_reveal(ctx, cards, *a, **kw)

        # No player choice of which cards: t.picks must not be consulted.
        t.picks = lambda *a: self.fail('opponent hand cards must be random, not chosen')
        with patch.object(random, 'sample', sample), \
                patch.object(EffectContext, 'reveal_cards', reveal):
            await t.play(card, targets=[target.entity_id])
        left = [c for c in hand if c in t.zone(P2, 'hand')]
        return t, hand, left, sampled, revealed

    async def test_floette_flower_picking_shuffles_one_random_card(self):
        t, hand, left, sampled, revealed = await self._flower_picking(FLOETTE, FLABEBE)
        self.assertEqual(len(left), 3)
        self.assertIn((4, 1), sampled)
        self.assertEqual([len(r) for r in revealed], [1])
        gone = [c for c in hand if c not in left]
        self.assertIn(gone[0], t.zone(P2, 'deck'))

    async def test_floette_printed_text_is_one_card(self):
        floette = fixtures.definition(FLOETTE)
        text = next(a for a in floette.abilities if a.title == 'Flower Picking').game_text
        self.assertIn("a random card from your opponent's hand", text)
        self.assertNotIn('2 random', text)

    async def test_florges_flower_picking_still_two_cards(self):
        floette = 'SM12.Floette_151'
        t, hand, left, sampled, revealed = await self._flower_picking(FLORGES, floette)
        self.assertEqual(len(left), 2)
        self.assertEqual([len(r) for r in revealed], [2])

    # -- Metagross Meteor Mash: boost ends on devolve / re-evolve -------
    def _meteor_setup(self, spec):
        t = self.table()
        metagross = self.neutral(t.put(spec, P1, 'active'))
        metang = t.put(METANG, P1, 'hand')
        # tuck Metang underneath like a real evolution stack
        t.board.attach_card(metang.entity_id, metagross.entity_id)
        t.energy(metagross, METAL, 2)
        return t, metagross, metang

    async def _meteor_mash_after(self, spec, devolve):
        t, metagross, metang = self._meteor_setup(spec)
        base = def_for(metagross.archetype_id)
        mash = next(a for a in base.abilities if a.title == 'Meteor Mash')
        await t.attack(metagross, 'Meteor Mash')
        self.assertEqual(self.dealt(t), mash.damage)
        t.next_turn()
        t.next_turn()
        if devolve:
            ctx = EffectContext(t.session, P1, metagross, None)
            removed = await t._run(lambda: ctx.devolve_pokemon(metagross, 1, 'hand'))
            self.assertEqual(removed, [metagross])
            self.assertIn(metagross, t.zone(P1, 'hand'))
            t.state.evolved_this_turn.pop(metang.entity_id, None)
            await t._run(lambda: t.session.perform_evolution(P1, metagross, metang))
            self.assertIs(t.active(P1), metagross)
        before = self.dealt(t)
        await t.attack(metagross, 'Meteor Mash')
        return self.dealt(t) - before, mash.damage

    async def test_meteor_mash_boost_still_applies_next_turn(self):
        for spec in METAGROSS:
            with self.subTest(spec=spec):
                dealt, base = await self._meteor_mash_after(spec, devolve=False)
                self.assertEqual(dealt, base * 2)

    async def test_meteor_mash_boost_cleared_by_devolve_and_reevolve(self):
        for spec in METAGROSS:
            with self.subTest(spec=spec):
                dealt, base = await self._meteor_mash_after(spec, devolve=True)
                self.assertEqual(dealt, base)

    async def test_meteor_mash_boost_cleared_when_leaving_play(self):
        """Scooped up to the hand and replayed later: a new Pokémon, no boost."""
        t, metagross, metang = self._meteor_setup(METAGROSS[2])
        await t.attack(metagross, 'Meteor Mash')
        self.assertTrue([m for m in t.state.damage_modifiers
                         if m.source_entity_id == metagross.entity_id])
        ctx = EffectContext(t.session, P1, metagross, None)
        await t._run(lambda: ctx.put_in_hand([metagross]))
        self.assertIn(metagross, t.zone(P1, 'hand'))
        self.assertEqual([m for m in t.state.damage_modifiers
                          if m.source_entity_id == metagross.entity_id], [])

    async def test_meteor_mash_boost_expires_after_next_turn(self):
        """Control: the boost lasts only for the next turn and is gone
        afterwards."""
        t, metagross, metang = self._meteor_setup(METAGROSS[2])
        await t.attack(metagross, 'Meteor Mash')
        for _ in range(4):
            t.next_turn()
        before = self.dealt(t)
        await t.attack(metagross, 'Meteor Mash')
        self.assertEqual(self.dealt(t) - before, 100)

    async def test_meteor_mash_boost_cleared_by_retreat_and_return(self):
        """Owner ruling: the boost ends once Metagross leaves the Active Spot."""
        for spec in METAGROSS:
            with self.subTest(spec=spec):
                t, metagross, metang = self._meteor_setup(spec)
                base = def_for(metagross.archetype_id)
                mash = next(a for a in base.abilities if a.title == 'Meteor Mash')
                other = self.neutral(t.put(self.filler, P1, 'bench'))
                await t.attack(metagross, 'Meteor Mash')
                t.next_turn(); t.next_turn()
                ctx = EffectContext(t.session, P1, metagross, None)
                await t._run(lambda: ctx.switch_active(P1, other))
                await t._run(lambda: EffectContext(t.session, P1, other, None)
                             .switch_active(P1, metagross))
                self.assertIs(t.active(P1), metagross)
                before = self.dealt(t)
                await t.attack(metagross, 'Meteor Mash')
                self.assertEqual(self.dealt(t) - before, mash.damage)


if __name__ == '__main__':
    unittest.main()
