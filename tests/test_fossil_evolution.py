"""Fossils in play are Basic Pokemon (player report: Rare Candy wasn't
offered onto a benched fossil with the Stage 2 in hand).

Also: evolution lines branch by printing -- SM6 Tyrunt evolves from
Unidentified Fossil, ME3 Tyrunt from Antique Jaw Fossil -- and Tyrantrum must
Rare Candy onto either."""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext, is_basic_pokemon
from spirit.game.session.legal_actions import compute_legal_actions, trainer_condition_met
from spirit.tools.effect_smoke import P1, P2


class FossilEvolutionTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def benched_fossil(self, path):
        rig, _ = self.rig('BW7.Charmander_18')
        fossil = self.add(rig, fixtures.definition(path), P1, 'hand')
        self.assertFalse(is_basic_pokemon(fossil))          # an Item in hand
        rig.board.move_card(fossil.entity_id, rig.board.find_player_area(P1, 'bench').entity_id)
        ts = rig.session.turn_state
        ts.begin_turn(P2); ts.begin_turn(P1)
        return rig, fossil

    async def test_rare_candy_onto_either_fossil(self):
        for path in ('SWSH10.UnidentifiedFossil_157', 'ME3.AntiqueJawFossil_68'):
            with self.subTest(fossil=path):
                rig, fossil = self.benched_fossil(path)
                self.assertTrue(is_basic_pokemon(fossil))
                candy = self.add(rig, fixtures.definition('ME1.RareCandy_125'), P1, 'hand')
                tyrantrum = self.add(rig, fixtures.definition('ME3.Tyrantrum_45'), P1, 'hand')
                definition = def_for(candy.archetype_id)
                self.assertTrue(trainer_condition_met(definition.condition, rig.board, P1, candy))
                ctx = EffectContext(rig.session, P1, candy, None)
                ctx.choose_pokemon = AsyncMock(return_value=fossil)
                await definition.effect(ctx)
                for action in list(ctx.deferred_actions):
                    await action()
                self.assertIs(fossil.parent, tyrantrum)
                self.assertEqual(tyrantrum.parent.get_attribute(AttrID.NAME), 'bench')

    def test_stage_one_offered_onto_benched_fossil(self):
        for path, evolution in (('SWSH10.UnidentifiedFossil_157', 'SM6.Tyrunt_68'),
                                ('ME3.AntiqueJawFossil_68', 'ME3.Tyrunt_44'),
                                ('SV07.AntiqueCoverFossil_129', 'ZSV10PT5.Tirtouga_22')):
            with self.subTest(fossil=path):
                rig, fossil = self.benched_fossil(path)
                card = self.add(rig, fixtures.definition(evolution), P1, 'hand')
                offers = [e for e in compute_legal_actions(rig.board, rig.session.turn_state,
                                                           P1, rig.session.game_id)
                          if e['entityID'] == card.entity_id]
                self.assertTrue(any(fossil.entity_id in (e['targetInfoLst'][0]['validTargets'])
                                    for e in offers if e['targetInfoLst']))

    async def test_fossil_evolve_button(self):
        from spirit.game.data_utils import ABILITIES_BY_ID
        from spirit.game.session.legal_actions import _ability_entries
        from spirit.game.session.effects import resolve_activated_ability
        rig, fossil = self.benched_fossil('ME5.AntiqueSkullFossil_73')
        def offered():
            return [ABILITIES_BY_ID[x['selectableAction']['actionID']].title
                    for x in _ability_entries(rig.board, rig.session.turn_state, P1,
                                              rig.session.game_id, rig.board.pokemon_in_play(P1))
                    if x['entityID'] == fossil.entity_id]
        self.assertNotIn('Evolve', offered())
        cranidos = self.add(rig, fixtures.definition('ME5.Cranidos_44'), P1, 'hand')
        self.assertIn('Evolve', offered())
        ability = next(a for a in def_for(fossil.archetype_id).abilities if a.title == 'Evolve')
        await resolve_activated_ability(rig.session, P1, fossil, ability)
        self.assertIs(fossil.parent, cranidos)


if __name__ == "__main__":
    unittest.main()


class FossilDropTargetTests(unittest.IsolatedAsyncioTestCase):
    """The client only accepts an evolution dropped on a CARD_TYPE Pokemon."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    benched_fossil = FossilEvolutionTests.benched_fossil

    async def test_in_play_fossil_is_sent_as_pokemon_then_reverted(self):
        from unittest.mock import patch
        rig, fossil = self.benched_fossil('ME3.AntiqueJawFossil_68')
        sent = []

        async def capture(name, value, flags=0):
            sent.append(value)
        with patch.object(rig.session, 'broadcast_packet', side_effect=capture):
            await rig.session._sync_fossil_card_types()
            mine = [m for m in sent if fossil.entity_id in str(m)]
            # CARD_TYPE Pokemon + TRAINER_TYPE emptied (Oct 21 drag fix).
            self.assertEqual(len(mine), 2)
            self.assertIn("'value': 0", str(mine[0]))
            self.assertIn("'value': None", str(mine[1]))
            # Server keeps the printed Trainer type.
            self.assertEqual(fossil.get_attribute(AttrID.CARD_TYPE), 2)
            sent.clear()
            await rig.session._sync_fossil_card_types()
            self.assertFalse([m for m in sent if fossil.entity_id in str(m)])
            rig.board.move_card(fossil.entity_id,
                                rig.board.find_player_area(P1, 'discard').entity_id)
            await rig.session._sync_fossil_card_types()
            back = [m for m in sent if fossil.entity_id in str(m)]
            self.assertEqual(len(back), 2)
            self.assertIn("'value': 2", str(back[0]))
            self.assertNotIn("'value': None", str(back[1]).split("'modValue'")[0])
