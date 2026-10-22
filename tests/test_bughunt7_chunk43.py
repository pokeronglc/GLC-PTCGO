"""Bug hunt round 7, chunk 43: Nickit SSH 125, Thievul EVS 105, Numel MEG 21
(ME1, chunk path BW7 was the wrong printing), Camerupt ASC 28, Chatot TEF 132,
Tyme SSP 190, Hop's Bag JTG 147, Eelektross BLK 32, Alolan Golem JTG 46,
Team Rocket's Zapdos DRI 70, Stunfisk ASC 62, Drasna SSP 173, Clemont's Quick
Wit SSP 167, Team Rocket's Archer DRI 170, Sacred Charm PFL 93."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W, D, R, L = (PokemonTypes.WATER, PokemonTypes.DARKNESS, PokemonTypes.FIRE,
              PokemonTypes.LIGHTNING)
NICKIT, THIEVUL = 'SWSH1.Nickit_125', 'SWSH7.Thievul_105'
NUMEL, CAMERUPT = 'ME1.Numel_21', 'ME2PT5.Camerupt_28'
CHATOT, TYME, HOPS_BAG = 'SV05.Chatot_132', 'SV08.Tyme_190', 'SV09.HopsBag_147'
EELEKTROSS, GOLEM = 'ZSV10PT5.Eelektross_32', 'SV09.AlolanGolem_46'
ZAPDOS, TR_ENERGY = 'SV10.TeamRocketsZapdos_70', 'SV10.TeamRocketsEnergy_182'
STUNFISK, DRASNA = 'ME2PT5.Stunfisk_62', 'SV08.Drasna_173'
CLEMONT, ARCHER = 'SV08.ClemontsQuickWit_167', 'SV10.TeamRocketsArcher_170'
SACRED_CHARM = 'ME2.SacredCharm_93'
HOP_WOOLOO, HOP_ROOKIDEE, HOP_DUBWOOL = (
    'SV09.HopsWooloo_135', 'SV09.HopsRookidee_133', 'SV09.HopsDubwool_136')
HAU = 'SM1.Hau_120'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk43Round7(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        mon._start_hp = mon.get_attribute(AttrID.HP, 0)
        return mon

    def took(self, t, mon):
        return mon._start_hp - t.hp(mon)

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    def mine(self, t, spec, kind, count, zone='active', hp=None):
        mon = self.neutral(t.put(spec, P1, zone), hp)
        if count:
            t.energy(mon, kind, count)
        return mon

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Nickit SSH 125: Instigate ------------------------------------------
    async def test_nickit_instigate_bottoms_hand_and_draws_3(self):
        t = self.table()
        nick = self.mine(t, NICKIT, D, 1)
        opp_hand = [t.put(HAU, P2, 'hand') for _ in range(5)]
        await t.attack(nick, 'Instigate')
        hand = t.zone(P2, 'hand')
        self.assertEqual(len(hand), 3)
        for c in opp_hand:
            self.assertNotIn(c, hand)
            self.assertIn(c, t.zone(P2, 'deck')[:5])     # bottom of deck
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_nickit_instigate_empty_hand_no_draw(self):
        t = self.table()
        nick = self.mine(t, NICKIT, D, 1)
        await t.attack(nick, 'Instigate')
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    # --- Thievul EVS 105: Fumbling Hands ------------------------------------
    async def test_thievul_fumbling_hands_both_draw_4(self):
        t = self.table()
        nick = t.put(NICKIT, P1, 'active')
        thv = t.put(THIEVUL, P1, 'hand')
        mine = t.put(HAU, P1, 'hand')
        theirs = [t.put(HAU, P2, 'hand') for _ in range(2)]
        await t.play(thv, targets=[nick.entity_id])
        self.assertIs(nick.parent, thv)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)
        self.assertNotIn(mine, t.zone(P1, 'hand'))
        for c in theirs:
            self.assertNotIn(c, t.zone(P2, 'hand'))

    async def test_thievul_fumbling_hands_decline(self):
        t = self.table()
        nick = t.put(NICKIT, P1, 'active')
        thv = t.put(THIEVUL, P1, 'hand')
        t.put(HAU, P1, 'hand')
        t.yes = False
        await t.play(thv, targets=[nick.entity_id])
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    async def test_thievul_fumbling_hands_only_opponent_has_cards(self):
        # "If either player put any cards ... each player draws 4 cards."
        t = self.table()
        nick = t.put(NICKIT, P1, 'active')
        thv = t.put(THIEVUL, P1, 'hand')
        t.put(HAU, P2, 'hand')
        await t.play(thv, targets=[nick.entity_id])
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)

    async def test_thievul_fumbling_hands_both_empty_no_draw(self):
        t = self.table()
        nick = t.put(NICKIT, P1, 'active')
        thv = t.put(THIEVUL, P1, 'hand')
        await t.play(thv, targets=[nick.entity_id])
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    # --- Numel MEG 21: Call for Family --------------------------------------
    async def test_numel_call_for_family_benches_up_to_2_basics(self):
        t = self.table()
        num = self.mine(t, NUMEL, R, 1)
        t.deck(P1, [CHATOT, NICKIT, STUNFISK, THIEVUL])
        await t.attack(num, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        for c in bench:
            self.assertIn(name(c), ('Chatot', 'Nickit', 'Stunfisk'))
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_numel_call_for_family_never_benches_evolution(self):
        t = self.table()
        num = self.mine(t, NUMEL, R, 1)
        t.deck(P1, [THIEVUL, CAMERUPT])
        await t.attack(num, 'Call for Family')
        self.assertEqual(t.zone(P1, 'bench'), [])

    # --- Camerupt ASC 28: Roasting Burn / Power Stomp -----------------------
    async def test_camerupt_roasting_burn_needs_burned(self):
        for burned, expected in ((True, 110), (False, 0)):
            t = self.table()
            cam = self.mine(t, CAMERUPT, R, 1)
            if burned:
                self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
            await t.attack(cam, 'Roasting Burn')
            with self.subTest(burned=burned):
                self.assertEqual(self.took(t, self.opp), expected)

    async def test_camerupt_power_stomp_discards_2_energy(self):
        t = self.table()
        cam = self.mine(t, CAMERUPT, R, 5)
        await t.attack(cam, 'Power Stomp')
        self.assertEqual(self.took(t, self.opp), 170)
        self.assertEqual(len(t.attached(cam)), 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    # --- Chatot TEF 132: A Cappella -----------------------------------------
    async def test_chatot_a_cappella_up_to_3_respects_bench_space(self):
        t = self.table()
        cha = self.mine(t, CHATOT, W, 1)
        t.deck(P1, [NICKIT, NUMEL, STUNFISK, ZAPDOS])
        await t.attack(cha, 'A Cappella')
        self.assertEqual(len(t.zone(P1, 'bench')), 3)

        t2 = self.table()
        cha2 = self.mine(t2, CHATOT, W, 1)
        for _ in range(4):
            t2.put(self.filler, P1, 'bench')
        t2.deck(P1, [NICKIT, NUMEL, STUNFISK])
        await t2.attack(cha2, 'A Cappella')
        self.assertEqual(len(t2.zone(P1, 'bench')), 5)

    # --- Tyme SSP 190 -------------------------------------------------------
    async def _tyme(self, correct):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mon = t.put(NICKIT, P1, 'hand')
        tyme = t.put(TYME, P1, 'hand')
        asked = []

        async def choice(pid, prompt, buttons, *a, **k):
            asked.append(pid)
            return 0 if correct else 1
        with patch.object(t.session, 'prompt_player_choice', choice):
            await t.play(tyme)
        return t, mon, asked

    async def test_tyme_wrong_guess_you_draw_4(self):
        t, mon, asked = await self._tyme(False)
        self.assertEqual(asked, [P2])
        hand = t.zone(P1, 'hand')
        self.assertIn(mon, hand)                     # returned to hand
        self.assertEqual(len(hand), 5)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    async def test_tyme_right_guess_opponent_draws_4(self):
        t, mon, asked = await self._tyme(True)
        self.assertEqual(t.zone(P1, 'hand'), [mon])
        self.assertEqual(len(t.zone(P2, 'hand')), 4)

    # BUG: Tyme is playable with no Pokémon in hand and then does nothing (no play condition)
    async def test_tyme_needs_a_pokemon_in_hand(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        tyme = t.put(TYME, P1, 'hand')
        t.put(HAU, P1, 'hand')
        self.assertFalse(t.can(tyme, 'UseTrainerCard'))

    # --- Hop's Bag JTG 147 --------------------------------------------------
    async def test_hops_bag_benches_basic_hops_pokemon_only(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.deck(P1, [HOP_WOOLOO, HOP_ROOKIDEE, HOP_DUBWOOL, NICKIT])
        bag = t.put(HOPS_BAG, P1, 'hand')
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(name(c) for c in cards)
            return cards[:count]
        t.picks = picks
        await t.play(bag)
        self.assertEqual(sorted(name(c) for c in t.zone(P1, 'bench')),
                         ["Hop's Rookidee", "Hop's Wooloo"])
        self.assertNotIn('Nickit', seen)
        self.assertNotIn("Hop's Dubwool", seen)

    # BUG: Hop's Bag is playable with a full Bench (missing from trainer_resource_permissions BENCH_SEARCH_NAMES/DECK_SEARCH_NAMES, unlike Nest Ball)
    async def test_hops_bag_no_bench_space_not_playable(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        for _ in range(5):
            t.put(self.filler, P1, 'bench')
        t.deck(P1, [HOP_WOOLOO])
        bag = t.put(HOPS_BAG, P1, 'hand')
        self.assertFalse(t.can(bag, 'UseTrainerCard'))

    # --- Eelektross BLK 32 --------------------------------------------------
    async def test_eelektross_thunder_fang(self):
        for heads in (True, False):
            t = self.table()
            ee = self.mine(t, EELEKTROSS, L, 1)
            t.heads = heads
            await t.attack(ee, 'Thunder Fang')
            with self.subTest(heads=heads):
                self.assertEqual(self.took(t, self.opp), 60)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    async def test_eelektross_buzz_flip(self):
        for pattern, expected in (([True, False, True, True], 300),
                                  ([False] * 4, 0)):
            t = self.table()
            ee = self.mine(t, EELEKTROSS, L, 4)
            it = iter(pattern)
            t.heads = lambda title: next(it)
            await t.attack(ee, 'Buzz Flip')
            with self.subTest(pattern=pattern):
                self.assertEqual(self.took(t, self.opp), expected)

    # --- Alolan Golem JTG 46 ------------------------------------------------
    async def test_golem_electromagnetic_catapult(self):
        for heads, expected in ((3, 210), (0, 0)):
            t = self.table()
            g = self.mine(t, GOLEM, L, 1)

            async def until_tails(ctx, title=''):
                return heads
            with patch.object(EffectContext, 'flip_until_tails', until_tails):
                await t.attack(g, 'Electromagnetic Catapult')
            with self.subTest(heads=heads):
                self.assertEqual(self.took(t, self.opp), expected)

    async def test_golem_megaton_fall_self_damage(self):
        t = self.table()
        g = self.mine(t, GOLEM, L, 2)
        await t.attack(g, 'Megaton Fall')
        self.assertEqual(self.took(t, self.opp), 160)
        self.assertEqual(self.took(t, g), 40)

    # --- Team Rocket's Zapdos DRI 70 ----------------------------------------
    async def test_zapdos_jamming_wing_moves_energy(self):
        t = self.table()
        z = self.mine(t, ZAPDOS, L, 2)
        e = t.energy(self.opp, W)
        bench = t.put(self.filler, P2, 'bench')
        await t.attack(z, 'Jamming Wing')
        self.assertEqual(self.took(t, self.opp), 30)
        self.assertIs(e.parent, bench)

    # BUG: Jamming Wing's "You may move" Energy pick is mandatory (bw_era.bw_legacy_attack defending-Pokémon move branch calls _choose_one without optional=True)
    async def test_zapdos_jamming_wing_optional(self):
        # "You may move": the Energy pick must allow 0 (the real chooser
        # enforces `minimum`), and picking nothing leaves the Energy.
        t = self.table()
        z = self.mine(t, ZAPDOS, L, 2)
        e = t.energy(self.opp, W)
        t.put(self.filler, P2, 'bench')
        minimums = []
        base = t._patches

        def patches():
            out = base()
            inner = out[0].new

            async def choose_cards(ctx, cards, count, minimum=None, *a, **k):
                minimums.append(minimum)
                return await inner(ctx, cards, count, minimum, *a, **k)
            out[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
            return out
        t._patches = patches
        t.picks = lambda cards, count, prompt, display: []
        t.yes = False
        await t.attack(z, 'Jamming Wing')
        self.assertEqual(self.took(t, self.opp), 30)
        self.assertIs(e.parent, self.opp)
        self.assertTrue(minimums)
        self.assertEqual(minimums[0], 0)

    async def test_zapdos_wicked_thunder(self):
        for with_tr, expected in ((True, 120), (False, 60)):
            t = self.table()
            z = self.mine(t, ZAPDOS, L, 3)
            if with_tr:
                t.attach(TR_ENERGY, z)
            await t.attack(z, 'Wicked Thunder')
            with self.subTest(with_tr=with_tr):
                self.assertEqual(self.took(t, self.opp), expected)

    # --- Stunfisk ASC 62: Pouncing Trap -------------------------------------
    async def test_stunfisk_pouncing_trap(self):
        t = self.table()
        s = self.mine(t, STUNFISK, L, 1)
        t.energy(self.opp, W, 4)
        t.put(self.filler, P2, 'bench')
        await t.attack(s, 'Pouncing Trap')
        self.assertEqual(self.took(t, self.opp), 30)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn()
        before = t.hp(self.opp)
        await t.attack(s, 'Pouncing Trap')
        self.assertEqual(before - t.hp(self.opp), 130)

    async def test_stunfisk_pouncing_trap_expires(self):
        t = self.table()
        s = self.mine(t, STUNFISK, L, 1)
        t.energy(self.opp, W, 4)
        t.put(self.filler, P2, 'bench')
        await t.attack(s, 'Pouncing Trap')
        for _ in range(3):
            t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn()
        before = t.hp(self.opp)
        await t.attack(s, 'Pouncing Trap')
        self.assertEqual(before - t.hp(self.opp), 30)

    # --- Drasna SSP 173 -----------------------------------------------------
    async def test_drasna_heads_8_tails_3(self):
        for heads, expected in ((True, 8), (False, 3)):
            t = self.table()
            t.put(self.filler, P1, 'active')
            old = [t.put(HAU, P1, 'hand') for _ in range(2)]
            dr = t.put(DRASNA, P1, 'hand')
            t.heads = heads
            await t.play(dr)
            with self.subTest(heads=heads):
                hand = t.zone(P1, 'hand')
                self.assertEqual(len(hand), expected)
                self.assertNotIn(dr, hand)
                self.assertIn(dr, t.zone(P1, 'discard'))

    # --- Clemont's Quick Wit SSP 167 ----------------------------------------
    async def test_clemont_heals_lightning_only(self):
        t = self.table()
        z = t.put(ZAPDOS, P1, 'active')
        s = t.put(STUNFISK, P1, 'bench')
        other = t.put(CHATOT, P1, 'bench')
        z.set_attribute(AttrID.HP, z.get_attribute(AttrID.HP) - 80)
        s.set_attribute(AttrID.HP, s.get_attribute(AttrID.HP) - 30)
        other.set_attribute(AttrID.HP, other.get_attribute(AttrID.HP) - 30)
        opp_l = t.put(STUNFISK, P2, 'bench')
        opp_l.set_attribute(AttrID.HP, 50)
        cl = t.put(CLEMONT, P1, 'hand')
        await t.play(cl)
        self.assertEqual(t.damage(z), 20)
        self.assertEqual(t.damage(s), 0)
        self.assertEqual(t.damage(other), 30)
        self.assertEqual(t.hp(opp_l), 50)

    # --- Team Rocket's Archer DRI 170 ---------------------------------------
    async def _archer_board(self, ko_spec):
        t = self.table()
        victim = self.neutral(t.put(ko_spec, P1, 'active'), 10)
        t.put(self.filler, P1, 'bench')
        title, _ = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        self.assertNotIn(victim, t.zone(P1, 'active') + t.zone(P1, 'bench'))
        t.next_turn()
        if not t.zone(P1, 'active'):
            t.board.move_card(t.zone(P1, 'bench')[0].entity_id,
                              t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        return t

    async def test_archer_after_team_rocket_ko(self):
        t = await self._archer_board(ZAPDOS)
        mine = [t.put(HAU, P1, 'hand') for _ in range(2)]
        theirs = [t.put(HAU, P2, 'hand') for _ in range(6)]
        archer = t.put(ARCHER, P1, 'hand')
        self.assertTrue(t.can(archer, 'UseTrainerCard'))
        await t.play(archer)
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        self.assertEqual(len(t.zone(P2, 'hand')), 3)

    async def test_archer_not_after_other_ko(self):
        t = await self._archer_board(STUNFISK)
        archer = t.put(ARCHER, P1, 'hand')
        self.assertFalse(t.can(archer, 'UseTrainerCard'))

    async def test_archer_not_without_ko(self):
        t = self.table()
        t.put(ZAPDOS, P1, 'active')
        archer = t.put(ARCHER, P1, 'hand')
        self.assertFalse(t.can(archer, 'UseTrainerCard'))

    # --- Sacred Charm PFL 93 ------------------------------------------------
    async def _charm(self, attacker_spec, kind=W, charm=True):
        t = Table(self)
        me = self.neutral(t.put(self.filler, P1, 'active'), 400)
        if charm:
            ch = t.put(SACRED_CHARM, P1, 'hand')
            await t.play(ch, targets=[me.entity_id])
            self.assertIs(ch.parent, me)
        att = self.neutral(t.put(attacker_spec, P2, 'active'), 300)
        t.energy(att, kind, 3)
        t.next_turn()
        return t, me, att

    async def test_sacred_charm_reduces_ability_attacker(self):
        t, me, att = await self._charm(THIEVUL)       # has Fumbling Hands
        await t.attack(att, 'Tail Smack', pid=P2)
        self.assertEqual(self.took(t, me), 30)

    async def test_sacred_charm_ignores_attacker_without_ability(self):
        t, me, att = await self._charm(STUNFISK, L)
        await t.attack(att, 'Pouncing Trap', pid=P2)
        self.assertEqual(self.took(t, me), 30)


if __name__ == '__main__':
    unittest.main()
