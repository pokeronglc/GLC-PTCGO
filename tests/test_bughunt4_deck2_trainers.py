"""Bug hunt round 4, deck 2: Colress PLS 118, Eneporter FLI 106,
Multi Switch GRI 129, Pot Helmet BRS 146."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

R, W = PokemonTypes.FIRE, PokemonTypes.WATER
COLRESS, ENEPORTER = 'BW8.Colress_118', 'SM6.Eneporter_106'
MULTI, HELMET = 'SM2.MultiSwitch_129', 'SWSH9.PotHelmet_146'
QUILAVA, VULPIX = 'SWSH10.Quilava_24', 'XY5.Vulpix_20'
HIDING = 'SWSH3.HidingDarknessEnergy_175'


class Deck2Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    # --- Colress ----------------------------------------------------------
    async def test_colress_shuffles_hand_draws_per_benched(self):
        t = self.table()
        t.put(self.filler, P1, 'bench'); t.put(self.filler, P1, 'bench')
        t.put(self.filler, P2, 'bench')
        old = [t.put(VULPIX, P1, 'hand') for _ in range(4)]
        deck_before = len(t.zone(P1, 'deck'))
        card = t.put(COLRESS, P1, 'hand')
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)                         # 2 mine + 1 theirs
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before + 4 - 3)
        self.assertIn(card, t.zone(P1, 'discard'))
        self.assertTrue(all(c in t.zone(P1, 'deck') for c in old if c not in hand))

    async def test_colress_counts_benched_not_active(self):
        t = self.table()
        t.put(VULPIX, P1, 'hand')
        await t.play(t.put(COLRESS, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [])               # nobody benched: draw 0

    # --- Eneporter --------------------------------------------------------
    async def test_eneporter_moves_opponent_special_energy(self):
        t = self.table()
        bench = t.put(self.filler, P2, 'bench')
        basic = t.energy(self.opp, W)
        special = t.attach(HIDING, self.opp)
        offered = {}

        def picks(cards, count, prompt, display):
            offered['cards'] = list(cards)
            return [special]
        t.picks = picks
        t.pokemon = lambda c, p: bench
        await t.play(t.put(ENEPORTER, P1, 'hand'))
        self.assertNotIn(basic, offered['cards'])
        self.assertIn(special, bench.children)
        self.assertIn(basic, self.opp.children)

    async def test_eneporter_not_playable_without_target(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W)                # only basic Energy
        mine_b = t.put(self.filler, P1, 'bench')
        t.attach(HIDING, self.me)            # my own Special Energy doesn't count
        card = t.put(ENEPORTER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t2 = self.table()
        t2.attach(HIDING, self.opp)          # opponent has only 1 Pokémon
        self.assertFalse(t2.can(t2.put(ENEPORTER, P1, 'hand'), 'UseTrainerCard'))

    # --- Multi Switch ------------------------------------------------------
    async def test_multi_switch_bench_to_active(self):
        t = self.table()
        b = t.put(self.filler, P1, 'bench')
        e = t.energy(b, W)
        await t.play(t.put(MULTI, P1, 'hand'))
        self.assertIn(e, self.me.children)

    async def test_multi_switch_moves_only_one(self):
        t = self.table()
        b = t.put(self.filler, P1, 'bench')
        es = t.energy(b, W, 2)
        await t.play(t.put(MULTI, P1, 'hand'))
        self.assertEqual(len([e for e in es if e in self.me.children]), 1)

    async def test_multi_switch_needs_benched_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'bench')
        t.energy(self.me, W)                 # Active's Energy doesn't count
        t.energy(self.opp, W)
        t.put(self.filler, P2, 'bench')
        self.assertFalse(t.can(t.put(MULTI, P1, 'hand'), 'UseTrainerCard'))

    # --- Pot Helmet -------------------------------------------------------
    async def _helmet_hit(self, rule_box=False):
        t = self.table()
        self.me.set_attribute(AttrID.WEAKNESS_TYPES, [R.value])
        self.me.set_attribute(AttrID.RESISTANCE_TYPES, [])
        await t.play(t.put(HELMET, P1, 'hand'), targets=[self.me.entity_id])
        self.assertEqual(len(self.me.children), 1)
        t.next_turn()
        q = t.put(QUILAVA, P2, 'bench')
        t.energy(q, R, 2)
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(q.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        before = t.hp(self.me)
        if rule_box:
            with patch('spirit.game.scripts.cards.SWSH9.PotHelmet_146.has_rule_box', lambda *_: True):
                await t.attack(q, 'Flare', P2)
        else:
            await t.attack(q, 'Flare', P2)
        return before - t.hp(self.me)

    async def test_pot_helmet_30_less_after_weakness(self):
        self.assertEqual(await self._helmet_hit(), 40 * 2 - 30)

    async def test_pot_helmet_rule_box_not_protected(self):
        self.assertEqual(await self._helmet_hit(rule_box=True), 80)
