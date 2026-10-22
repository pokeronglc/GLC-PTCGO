"""Player reports: Float Stone + Galar Mine, Marshadow's Shadowy Knot, Mallow."""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_retreat_cost
from spirit.tools.effect_smoke import P1, P2


class RetreatCostFixTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def stadium(self, rig, path):
        card = self.add(rig, fixtures.definition(path), P1, 'hand')
        rig.board.move_card(card.entity_id, rig.board.find_global_area('activeStadium').entity_id)

    def test_float_stone_beats_galar_mine(self):
        # Compendium: an effect that makes the Retreat Cost vanish takes
        # priority over one that increases it.
        rig, e = self.rig('BW7.Charmander_18')
        rig.attach(self.add(rig, fixtures.definition('BW9.FloatStone_99'), P1, 'hand'), e['target'])
        self.stadium(rig, 'SWSH2.GalarMine_160')
        self.assertEqual(effective_retreat_cost(rig.board, e['target']), 0)

    def test_galar_mine_still_adds_to_a_printed_cost(self):
        rig, e = self.rig('BW7.Charmander_18')
        before = effective_retreat_cost(rig.board, e['target'])
        self.stadium(rig, 'SWSH2.GalarMine_160')
        self.assertEqual(effective_retreat_cost(rig.board, e['target']), before + 2)

    async def attack_damage(self, path, title, mine=False, gemstone=False):
        definition = fixtures.definition(path)
        rig, e = self.rig(path)
        attacker = e['target']
        defender = rig.board.active_pokemon(P2)
        defender.set_attribute(AttrID.HP, 1000)
        if mine:
            self.stadium(rig, 'SWSH2.GalarMine_160')
        if gemstone:
            rig.attach(self.add(rig, fixtures.definition('SV07.GravityGemstone_137'), P1, 'hand'),
                       attacker)
        attack = next(a for a in definition.abilities if a.title == title)
        ctx = EffectContext(rig.session, P1, attacker, attack)
        await attack.effect(ctx)
        for action in list(ctx.deferred_actions):
            await action()
        return 1000 - defender.get_attribute(AttrID.HP), effective_retreat_cost(rig.board, defender)

    async def test_shadowy_knot_counts_the_current_retreat_cost(self):
        for mine, gem in ((False, False), (True, False), (True, True)):
            with self.subTest(galar_mine=mine, gravity_gemstone=gem):
                damage, retreat = await self.attack_damage(
                    'ME5.Marshadow_40', 'Shadowy Knot', mine, gem)
                self.assertGreater(retreat, 0)
                self.assertEqual(damage, 30 * retreat)

    async def test_more_damage_per_retreat_colorless(self):
        damage, retreat = await self.attack_damage('SM9.Absol_88', 'Shadow Seeker', mine=True)
        self.assertEqual(damage, 30 + 30 * retreat)

    async def test_mallow_puts_both_cards_on_top(self):
        rig, e = self.rig('SM2.Mallow_127', 'trainer')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        deck = rig.board.find_player_area(P1, 'deck')
        wanted = [c for c in deck.children[-6:-4]]

        async def search_deck(predicate=None, count=1, **kw):
            return list(wanted)
        ctx.search_deck = search_deck
        await fixtures.definition('SM2.Mallow_127').effect(ctx)
        self.assertEqual(list(ctx.deck_top(2)), wanted)      # first pick on top


if __name__ == "__main__":
    unittest.main()
