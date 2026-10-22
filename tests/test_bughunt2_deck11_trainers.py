"""Bug hunt round 2, deck 11 (Fairy): Supporters and Items, through the real
play-trainer executor (so play conditions apply)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

Y, D, W = PokemonTypes.FAIRY, PokemonTypes.DARKNESS, PokemonTypes.WATER
DIANTHA, CYLLENE = 'SM6.Diantha_105', 'SWSH10.Cyllene_138'
HANDIWORK, CHEER = 'XY10.TeamRocketsHandiwork_112', 'SWSH9.TeamYellsCheer_149'
HAMMER, DARK_BELL, YELL_HORN = 'SV06.EnhancedHammer_148', 'ME5.DarkBell_75', 'SWSH3.YellHorn_173'
KLEFKI, RALTS = 'SM6.Klefki_89', 'SM8.Ralts_139'
SABLEYE = 'SV2.Sableye_136'          # Darkness; P2 attacker Unseen Claw 20
GUZMA = 'SM3.Guzma_115'
NEST = 'SV1.NestBall_181'
HIDING, WONDER = 'SWSH3.HidingDarknessEnergy_175', 'XY5.WonderEnergy_144'


class Deck11Trainers2(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Diantha ----------------------------------------------------------
    async def _ko_my_active_on_opponents_turn(self, spec):
        t = Table(self)
        victim = t.put(spec, P1, 'active', hp=10)
        victim.set_attribute(AttrID.WEAKNESS_TYPES, [])
        victim.set_attribute(AttrID.RESISTANCE_TYPES, [])
        t.put(self.filler, P1, 'bench')
        opp = t.put(SABLEYE, P2, 'active')
        t.energy(opp, D)
        t.put(NEST, P1, 'discard'); t.put(GUZMA, P1, 'discard')
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        t.next_turn()
        self.assertIn(victim, t.zone(P1, 'discard'))
        return t, victim

    async def test_diantha_after_fairy_knocked_out(self):
        t, victim = await self._ko_my_active_on_opponents_turn(KLEFKI)
        card = t.put(DIANTHA, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is not victim][:count]
        await t.play(card)
        self.assertEqual(self.hand_names(t), ['Guzma', 'Nest Ball'])

    async def test_diantha_not_after_non_fairy_knocked_out(self):
        t, _ = await self._ko_my_active_on_opponents_turn(self.filler)
        self.assertFalse(t.can(t.put(DIANTHA, P1, 'hand'), 'UseTrainerCard'))

    async def test_diantha_not_without_knockout(self):
        t = self.table()
        t.put(NEST, P1, 'discard'); t.put(GUZMA, P1, 'discard')
        self.assertFalse(t.can(t.put(DIANTHA, P1, 'hand'), 'UseTrainerCard'))

    # --- Cyllene ------------------------------------------------------------
    async def test_cyllene_two_heads_two_cards_on_top(self):
        t = self.table()
        a = t.put(NEST, P1, 'discard'); b = t.put(GUZMA, P1, 'discard')
        t.put(KLEFKI, P1, 'discard')
        t.heads = True
        t.picks = lambda cards, count, prompt, display: [a, b][:count]
        await t.play(t.put(CYLLENE, P1, 'hand'))
        deck = t.zone(P1, 'deck')
        self.assertEqual(set(deck[-2:]), {a, b})
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_cyllene_one_head_one_card_tails_none(self):
        for heads, moved in ((lambda title, it=iter([True, False]): next(it), 1), (False, 0)):
            t = self.table()
            for _ in range(3):
                t.put(NEST, P1, 'discard')
            t.heads = heads
            await t.play(t.put(CYLLENE, P1, 'hand'))
            with self.subTest(moved=moved):
                self.assertEqual(len(t.zone(P1, 'deck')), 30 + moved)

    async def test_cyllene_needs_a_discard(self):
        t = self.table()
        self.assertFalse(t.can(t.put(CYLLENE, P1, 'hand'), 'UseTrainerCard'))

    # --- Team Rocket's Handiwork -------------------------------------------
    async def test_handiwork_two_per_heads(self):
        for heads, milled in ((True, 4), (False, 0)):
            t = self.table()
            t.heads = heads
            await t.play(t.put(HANDIWORK, P1, 'hand'))
            with self.subTest(heads=heads):
                self.assertEqual(len(t.zone(P2, 'discard')), milled)
                self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Team Yell's Cheer ---------------------------------------------------
    async def test_team_yells_cheer_shuffles_up_to_three(self):
        t = self.table()
        mons = [t.put(KLEFKI, P1, 'discard'), t.put(RALTS, P1, 'discard')]
        sup = t.put(GUZMA, P1, 'discard')
        other_cheer = t.put(CHEER, P1, 'discard')
        item = t.put(NEST, P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'], seen['count'] = list(cards), count
            return list(cards)[:count]
        t.picks = picks
        await t.play(t.put(CHEER, P1, 'hand'))
        self.assertEqual(seen['count'], 3)
        self.assertNotIn(other_cheer, seen['cards'])
        self.assertNotIn(item, seen['cards'])
        deck = t.zone(P1, 'deck')
        for c in mons + [sup]:
            self.assertIn(c, deck)
        self.assertIn(item, t.zone(P1, 'discard'))

    async def test_team_yells_cheer_needs_valid_target(self):
        t = self.table()
        t.put(NEST, P1, 'discard'); t.put(CHEER, P1, 'discard')
        self.assertFalse(t.can(t.put(CHEER, P1, 'hand'), 'UseTrainerCard'))

    # --- Enhanced Hammer -----------------------------------------------------
    async def test_enhanced_hammer_discards_special_from_bench(self):
        t = self.table()
        bench = t.put(SABLEYE, P2, 'bench')
        special = t.attach(HIDING, bench)
        basic = t.energy(self.opp, W)
        await t.play(t.put(HAMMER, P1, 'hand'))
        self.assertIn(special, t.zone(P2, 'discard'))
        self.assertIn(basic, self.opp.children)

    async def test_enhanced_hammer_needs_opponent_special(self):
        t = self.table()
        t.energy(self.opp, W)
        t.attach(HIDING, t.put(SABLEYE, P1, 'bench'))   # my own Special doesn't count
        self.assertFalse(t.can(t.put(HAMMER, P1, 'hand'), 'UseTrainerCard'))

    # --- Dark Bell / Yell Horn ----------------------------------------------
    async def test_dark_bell_confuses_non_darkness_actives(self):
        t = Table(self)
        me = t.put(KLEFKI, P1, 'active')
        opp = t.put(SABLEYE, P2, 'active')
        bench = t.put(KLEFKI, P1, 'bench')
        await t.play(t.put(DARK_BELL, P1, 'hand'))
        self.assertIn(CONFUSED, t.conditions(me))
        self.assertNotIn(CONFUSED, t.conditions(opp))        # Darkness: spared
        self.assertNotIn(CONFUSED, t.conditions(bench))

    async def test_dark_bell_spares_my_darkness_active(self):
        t = Table(self)
        me = t.put(SABLEYE, P1, 'active')
        opp = t.put(KLEFKI, P2, 'active')
        await t.play(t.put(DARK_BELL, P1, 'hand'))
        self.assertNotIn(CONFUSED, t.conditions(me))
        self.assertIn(CONFUSED, t.conditions(opp))

    async def test_yell_horn_confuses_both_actives_only(self):
        t = Table(self)
        me = t.put(SABLEYE, P1, 'active')
        opp = t.put(KLEFKI, P2, 'active')
        bench = t.put(KLEFKI, P2, 'bench')
        await t.play(t.put(YELL_HORN, P1, 'hand'))
        self.assertIn(CONFUSED, t.conditions(me))
        self.assertIn(CONFUSED, t.conditions(opp))
        self.assertNotIn(CONFUSED, t.conditions(bench))


if __name__ == '__main__':
    unittest.main()
