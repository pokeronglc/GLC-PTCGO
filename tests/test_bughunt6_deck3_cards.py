"""Bug hunt round 6, deck 3 (Fighting): Machop LOR 86, Machamp LOR 88,
Riolu UNM 116, Hitmonchan TEU 74, Hitmonlee TEU 73, Hitmontop UNB 101,
Erika's Hospitality TEU 140, Team Magma's Great Ball DCR 31,
Xtransceiver NVI 96, Karate Belt UNM 201 -- checked against their printed
text, including the should-NOT-work cases."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

F, W = PokemonTypes.FIGHTING, PokemonTypes.WATER
MACHOP, MACHAMP, RIOLU = 'SWSH11.Machop_86', 'SWSH11.Machamp_88', 'SM11.Riolu_116'
CHAN, LEE, TOP = 'SM9.Hitmonchan_74', 'SM9.Hitmonlee_73', 'SM10.Hitmontop_101'
ERIKA, MAGMA_BALL = 'SM9.ErikasHospitality_140', 'TATM.TeamMagmasGreatBall_31'
XTRANS, BELT = 'BW3.Xtransceiver_96', 'SM11.KarateBelt_201'
POOCHYENA, MIGHTYENA = 'TATM.TeamMagmasPoochyena_17', 'TATM.TeamMagmasMightyena_19'


class Bughunt6Deck3(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    def two_turns(self, t):
        t.next_turn()
        t.next_turn()

    async def test_set_codes(self):
        for path, code in ((MACHOP, 'SWSH11'), (MACHAMP, 'SWSH11'), (RIOLU, 'SM11'),
                           (CHAN, 'SM9'), (LEE, 'SM9'), (TOP, 'SM10'), (ERIKA, 'SM9'),
                           (MAGMA_BALL, 'TATM'), (XTRANS, 'BW3'), (BELT, 'SM11')):
            d = fixtures.definition(path)
            self.assertEqual(d.set_code, code, path)
        self.assertEqual(fixtures.definition(MAGMA_BALL).collector_number, 31)

    # --- Machamp (LOR 88): Crisis Muscles ---------------------------------
    async def test_crisis_muscles_at_three_opponent_prizes(self):
        t = self.table()
        champ = t.put(MACHAMP, P1, 'active')
        t.set_prizes(P2, 3)
        self.assertEqual(effective_max_hp(t.board, champ), 300)

    async def test_crisis_muscles_not_at_four_or_own_prizes(self):
        t = self.table()
        champ = t.put(MACHAMP, P1, 'active')
        t.set_prizes(P2, 4)
        t.set_prizes(P1, 1)          # MY prize count is irrelevant
        self.assertEqual(effective_max_hp(t.board, champ), 150)

    async def test_crisis_muscles_on_bench_too(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        champ = t.put(MACHAMP, P1, 'bench')
        t.set_prizes(P2, 2)
        self.assertEqual(effective_max_hp(t.board, champ), 300)

    # --- Machamp: Strong-Arm Lariat ----------------------------------------
    async def test_lariat_extra_damage_locks_next_turn(self):
        t = self.table()
        champ = t.put(MACHAMP, P1, 'active')
        t.energy(champ, F, 2)
        t.yes = True
        await t.attack(champ, 'Strong-Arm Lariat')
        self.assertEqual((400 - t.hp(self.opp)), 200)
        self.two_turns(t)
        self.assertIsNone(t.attack_offer(champ, 'Strong-Arm Lariat'))
        self.two_turns(t)
        self.assertIsNotNone(t.attack_offer(champ, 'Strong-Arm Lariat'))

    async def test_lariat_no_extra_no_lock(self):
        t = self.table()
        champ = t.put(MACHAMP, P1, 'active')
        t.energy(champ, F, 2)
        t.yes = False
        await t.attack(champ, 'Strong-Arm Lariat')
        self.assertEqual((400 - t.hp(self.opp)), 100)
        self.two_turns(t)
        self.assertIsNotNone(t.attack_offer(champ, 'Strong-Arm Lariat'))

    # --- Hitmonchan (TEU 74): Hit and Run ----------------------------------
    async def test_hit_and_run_may_switch(self):
        t = self.table()
        chan = t.put(CHAN, P1, 'active')
        t.energy(chan, F)
        lee = t.put(LEE, P1, 'bench')
        t.yes = True
        await t.attack(chan, 'Hit and Run')
        self.assertEqual((400 - t.hp(self.opp)), 30)
        self.assertIs(t.active(P1), lee)
        self.assertIn(chan, t.zone(P1, 'bench'))

    async def test_hit_and_run_may_decline_switch(self):
        t = self.table()
        chan = t.put(CHAN, P1, 'active')
        t.energy(chan, F)
        t.put(LEE, P1, 'bench')
        t.pokemon = lambda c, p: None     # optional chooser: decline
        await t.attack(chan, 'Hit and Run')
        self.assertEqual((400 - t.hp(self.opp)), 30)
        self.assertIs(t.active(P1), chan)

    # --- Hitmonlee (TEU 73): Special Combo ---------------------------------
    async def _hit_and_run_into_lee(self, t):
        chan = t.put(CHAN, P1, 'active')
        t.energy(chan, F)
        lee = t.put(LEE, P1, 'bench')
        t.energy(lee, F)
        t.yes = True
        await t.attack(chan, 'Hit and Run')
        self.assertIs(t.active(P1), lee)
        self.two_turns(t)
        return chan, lee

    async def test_special_combo_after_hit_and_run(self):
        t = self.table()
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(self.filler, P2, 'bench')
        for b in (b1, b2):
            self.big(b)
        chan, lee = await self._hit_and_run_into_lee(t)
        self.assertIsNotNone(t.attack_offer(lee, 'Special Combo'))
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), [b2])[1]
        await t.attack(lee, 'Special Combo')
        self.assertEqual(set(offered), {b1, b2})       # Benched only
        self.assertEqual((400 - t.hp(b2)), 90)
        self.assertEqual((400 - t.hp(b1)), 0)
        self.assertEqual((400 - t.hp(self.opp)), 30)   # only Hit and Run's 30

    async def test_special_combo_not_without_hit_and_run(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        lee = t.put(LEE, P1, 'active')
        t.energy(lee, F)
        self.assertIsNone(t.attack_offer(lee, 'Special Combo'))

    async def test_special_combo_not_after_other_attack(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        chan = t.put(CHAN, P1, 'active')
        t.energy(chan, F)
        t.energy(chan, W, 2)
        lee = t.put(LEE, P1, 'bench')
        t.energy(lee, F)
        await t.attack(chan, 'Magnum Punch')
        self.two_turns(t)
        t.board.move_card(lee.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        t.board.move_card(chan.entity_id, t.board.find_player_area(P1, 'bench').entity_id)
        self.assertIs(t.active(P1), lee)
        self.assertIsNone(t.attack_offer(lee, 'Special Combo'))

    async def test_special_combo_expires_after_one_turn(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        chan, lee = await self._hit_and_run_into_lee(t)
        self.two_turns(t)          # Hit and Run was two turns ago now
        self.assertIsNone(t.attack_offer(lee, 'Special Combo'))

    # --- Hitmontop (UNB 101): Finishing Combo ------------------------------
    async def test_finishing_combo_after_special_combo(self):
        t = self.table()
        b1 = t.put(self.filler, P2, 'bench')
        self.big(b1)
        chan, lee = await self._hit_and_run_into_lee(t)
        top = t.put(TOP, P1, 'bench')
        t.energy(top, F)
        t.yes = True
        await t.attack(lee, 'Special Combo')
        self.assertEqual((400 - t.hp(b1)), 90)
        self.two_turns(t)
        t.board.move_card(lee.entity_id, t.board.find_player_area(P1, 'bench').entity_id)
        t.board.move_card(top.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        self.assertIs(t.active(P1), top)
        self.assertIsNotNone(t.attack_offer(top, 'Finishing Combo'))
        await t.attack(top, 'Finishing Combo')
        self.assertEqual((400 - t.hp(self.opp)), 30 + 60)   # 30 from Hit and Run
        self.assertEqual((400 - t.hp(b1)), 150)
        # own side untouched
        for mon in (chan, lee):
            self.assertEqual(t.damage(mon), 0)

    async def test_finishing_combo_not_without_special_combo(self):
        t = self.table()
        top = t.put(TOP, P1, 'active')
        t.energy(top, F)
        self.assertIsNone(t.attack_offer(top, 'Finishing Combo'))

    async def test_finishing_combo_not_after_hit_and_run(self):
        t = self.table()
        chan = t.put(CHAN, P1, 'active')
        t.energy(chan, F)
        top = t.put(TOP, P1, 'bench')
        t.energy(top, F)
        t.yes = True
        await t.attack(chan, 'Hit and Run')
        self.assertIs(t.active(P1), top)
        self.two_turns(t)
        self.assertIsNone(t.attack_offer(top, 'Finishing Combo'))

    # --- Erika's Hospitality (TEU 140) -------------------------------------
    async def test_erika_draws_per_opponent_pokemon(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'bench')
        t.put(self.filler, P2, 'bench')
        for _ in range(4):
            t.put(self.item, P1, 'hand')
        erika = t.put(ERIKA, P1, 'hand')
        self.assertTrue(t.can(erika, 'UseTrainerCard'))
        await t.play(erika)
        hand = [c for c in t.zone(P1, 'hand') if c is not erika]
        self.assertEqual(len(hand), 4 + 3)

    async def test_erika_not_with_five_other_cards(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        for _ in range(5):
            t.put(self.item, P1, 'hand')
        erika = t.put(ERIKA, P1, 'hand')
        self.assertFalse(t.can(erika, 'UseTrainerCard'))

    # --- Team Magma's Great Ball (DCR 31) ----------------------------------
    async def _magma_ball(self, t, specs):
        seen = self.seen = []

        async def groups(pid, src, gspecs, prompt, **k):
            seen.append([list(s['cards']) for s in gspecs])
            return [[s['cards'][0].entity_id] if s['cards'] else [] for s in gspecs]
        ball = t.put(MAGMA_BALL, P1, 'hand')
        with patch.object(t.session, 'prompt_card_chooser_groups', groups, create=True):
            await t.play(ball)
        return seen

    # FIXED (was BUG): Team Magma's Poochyena isn't matched -- TATM cards lack a "Team Magma" subtype
    async def test_magma_ball_finds_magma_basic_and_fighting_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        pooch = t.deck(P1, [POOCHYENA])[0]
        fe = t.put(t.basic_energy(F), P1, 'deck')
        await self._magma_ball(t, None)
        hand = t.zone(P1, 'hand')
        self.assertIn(pooch, hand)
        self.assertIn(fe, hand)
        self.assertEqual(len(hand), 2)

    async def test_magma_ball_ignores_non_magma_stage1_and_other_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        others = t.deck(P1, [RIOLU, MIGHTYENA])
        we = t.put(t.basic_energy(W), P1, 'deck')
        seen = await self._magma_ball(t, None)
        for group_list in seen:
            for cards in group_list:
                for c in others + [we]:
                    self.assertNotIn(c, cards)
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Xtransceiver (NVI 96) ---------------------------------------------
    async def test_xtransceiver_heads_finds_supporter(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sup = t.deck(P1, [ERIKA])[0]
        t.heads = True
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.play(t.put(XTRANS, P1, 'hand'))
        self.assertEqual(offered, [sup])
        self.assertEqual(t.zone(P1, 'hand'), [sup])

    async def test_xtransceiver_tails_nothing(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sup = t.deck(P1, [ERIKA])[0]
        t.heads = False
        x = t.put(XTRANS, P1, 'hand')
        await t.play(x)
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertIn(sup, t.zone(P1, 'deck'))
        self.assertIn(x, t.zone(P1, 'discard'))

    # --- Karate Belt (UNM 201) ---------------------------------------------
    async def test_karate_belt_reduces_when_behind(self):
        t = self.table()
        chan = t.put(CHAN, P1, 'active')
        t.energy(chan, W, 2)
        await t.play(t.put(BELT, P1, 'hand'), targets=[chan.entity_id])
        t.set_prizes(P1, 6)
        t.set_prizes(P2, 5)
        self.assertIsNotNone(t.attack_offer(chan, 'Magnum Punch'))   # F C C -> C C
        self.assertIsNotNone(t.attack_offer(chan, 'Hit and Run'))    # F -> free

    async def test_karate_belt_no_reduction_when_equal_or_ahead(self):
        t = self.table()
        chan = t.put(CHAN, P1, 'active')
        t.energy(chan, W, 2)
        await t.play(t.put(BELT, P1, 'hand'), targets=[chan.entity_id])
        for mine, theirs in ((5, 5), (4, 5)):
            t.set_prizes(P1, mine)
            t.set_prizes(P2, theirs)
            self.assertIsNone(t.attack_offer(chan, 'Magnum Punch'), (mine, theirs))
            self.assertIsNone(t.attack_offer(chan, 'Hit and Run'), (mine, theirs))

    async def test_karate_belt_only_the_holder(self):
        t = self.table()
        chan = t.put(CHAN, P1, 'active')
        lee = t.put(LEE, P1, 'bench')
        await t.play(t.put(BELT, P1, 'hand'), targets=[lee.entity_id])
        t.set_prizes(P2, 4)
        self.assertIsNone(t.attack_offer(chan, 'Hit and Run'))


if __name__ == '__main__':
    unittest.main()
