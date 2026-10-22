"""Bug hunt, deck 1 (Colorless): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

C, D = PokemonTypes.WATER, PokemonTypes.DARKNESS   # C: any basic pays [C]
PIKIPEK, TRUMBEAK, TOUCANNON = 'ME5.Pikipek_66', 'ME5.Trumbeak_67', 'ME5.Toucannon_68'
MINCCINO, CINCCINO = 'SWSH9.Minccino_124', 'SWSH1.Cinccino_147'
BIDOOF, BIBAREL = 'CZ.Bidoof_111', 'SWSH9.Bibarel_121'
SKWOVET, GREEDENT = 'SV1.Skwovet_151', 'SWSH11.Greedent_151'
WOOLOO, DUBWOOL = 'SV09.HopsWooloo_135', 'SV09.HopsDubwool_136'
HOP_SNORLAX, CRAMORANT = 'SV09.HopsSnorlax_117', 'SV09.HopsCramorant_138'
ORANGURU, FAN_ROTOM = 'SM1.Oranguru_113', 'SV07.FanRotom_118'
SABLEYE, CROBAT = 'SV2.Sableye_136', 'SWSH12.Crobat_105'
ARTAZON = 'SV2.Artazon_171'


class Deck1Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def hand(self, t, n, pid=P1):
        return [t.put(self.filler, pid, 'hand') for _ in range(n)]

    # --- Pikipek: Double Stab ------------------------------------------------
    async def test_pikipek_double_stab(self):
        for heads, dmg in ((True, 20), (False, 0)):
            t = self.table()
            p = t.put(PIKIPEK, P1, 'active')
            t.energy(p, C)
            t.heads = heads
            await t.attack(p, 'Double Stab')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Trumbeak: Fly --------------------------------------------------------
    async def _fly_then_hit(self, heads):
        t = self.table(WOOLOO)
        trum = t.put(TRUMBEAK, P1, 'active')
        t.energy(trum, C)
        t.energy(self.opp, C, 3)
        t.heads = heads
        await t.attack(trum, 'Fly')
        dealt = 400 - t.hp(self.opp)
        t.next_turn()
        before = t.hp(trum)
        await t.attack(self.opp, 'Smash Kick', pid=P2)
        return dealt, before - t.hp(trum)

    async def test_trumbeak_fly_heads_protects(self):
        dealt, taken = await self._fly_then_hit(True)
        self.assertEqual(dealt, 30)
        self.assertEqual(taken, 0)

    async def test_trumbeak_fly_tails_does_nothing(self):
        dealt, taken = await self._fly_then_hit(False)
        self.assertEqual(dealt, 0)
        self.assertEqual(taken, 50)

    async def test_trumbeak_fly_heads_prevents_effects(self):
        t = self.table(SABLEYE)
        trum = t.put(TRUMBEAK, P1, 'active')
        t.energy(trum, C)
        t.energy(self.opp, C)
        t.heads = True
        await t.attack(trum, 'Fly')
        t.next_turn()
        await t.attack(self.opp, 'Night Eyes', pid=P2)       # puts the Defending Pokémon to sleep
        self.assertEqual(t.conditions(trum), set())

    # --- Toucannon --------------------------------------------------------------
    async def test_toucannon_aerial_draw_once(self):
        t = self.table()
        tou = t.put(TOUCANNON, P1, 'bench')
        t.put(self.filler, P1, 'active')
        await t.use(tou, 'Aerial Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertIsNone(t.ability_offer(tou, 'Aerial Draw'))

    async def test_toucannon_feather_rondo_counts_both_benches(self):
        for mine, theirs in ((0, 0), (2, 1)):
            t = self.table()
            tou = t.put(TOUCANNON, P1, 'active')
            t.energy(tou, C)
            for _ in range(mine):
                t.put(self.filler, P1, 'bench')
            for _ in range(theirs):
                t.put(self.filler, P2, 'bench')
            await t.attack(tou, 'Feather Rondo')
            with self.subTest(mine=mine, theirs=theirs):
                self.assertEqual(400 - t.hp(self.opp), 60 + 20 * (mine + theirs))

    # --- Minccino: Call for Family -----------------------------------------
    async def test_minccino_call_for_family_two_basics_only(self):
        t = self.table()
        m = t.put(MINCCINO, P1, 'active')
        t.energy(m, C)
        t.deck(P1, [PIKIPEK, BIDOOF, SKWOVET, TRUMBEAK])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (
            seen.setdefault('n', (t.names(cards), count)), cards[:count])[1]
        await t.attack(m, 'Call for Family')
        names, count = seen['n']
        self.assertEqual(count, 2)
        self.assertNotIn('Trumbeak', names)
        self.assertEqual(len(t.zone(P1, 'bench')), 2)

    # --- Cinccino -------------------------------------------------------------
    async def test_cinccino_make_do(self):
        t = self.table()
        cin = t.put(CINCCINO, P1, 'bench')
        t.put(self.filler, P1, 'active')
        self.assertIsNone(t.ability_offer(cin, 'Make Do'))      # nothing to discard
        self.hand(t, 2)
        await t.use(cin, 'Make Do')
        self.assertEqual(len(t.zone(P1, 'discard')), 1)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertIsNone(t.ability_offer(cin, 'Make Do'))

    async def test_cinccino_energy_assist(self):
        t = self.table()
        cin = t.put(CINCCINO, P1, 'active')
        t.energy(cin, C)
        bench = t.put(self.filler, P1, 'bench')
        energy = t.put(t.basic_energy(PokemonTypes.FIRE), P1, 'discard')
        await t.attack(cin, 'Energy Assist')
        self.assertEqual(400 - t.hp(self.opp), 40)
        self.assertIn(energy, bench.children)

    async def test_cinccino_energy_assist_ignores_special_energy(self):
        t = self.table()
        cin = t.put(CINCCINO, P1, 'active')
        t.energy(cin, C)
        bench = t.put(self.filler, P1, 'bench')
        t.put('SM12.DrawEnergy_209', P1, 'discard')
        await t.attack(cin, 'Energy Assist')
        self.assertEqual(400 - t.hp(self.opp), 40)
        self.assertEqual(list(bench.children), [])

    # --- Bidoof: Carefree Countenance --------------------------------------
    async def test_bidoof_bench_prevents_attack_damage(self):
        t = self.table(CROBAT)
        t.energy(self.opp, D, 3)
        t.put(self.filler, P1, 'active')
        bidoof = t.put(BIDOOF, P1, 'bench')
        t.next_turn()
        t.pokemon = lambda c, p: bidoof if bidoof in c else c[0]
        await t.attack(self.opp, 'Critical Bite', pid=P2)
        self.assertEqual(t.damage(bidoof), 0)

    async def test_bidoof_active_takes_damage(self):
        t = self.table(WOOLOO)
        t.energy(self.opp, C, 3)
        bidoof = t.put(BIDOOF, P1, 'active')
        bidoof.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.next_turn()
        await t.attack(self.opp, 'Smash Kick', pid=P2)
        self.assertEqual(t.damage(bidoof), 50)

    # --- Bibarel: Industrious Incisors ------------------------------------
    async def test_bibarel_draw_until_five_once(self):
        t = self.table()
        bib = t.put(BIBAREL, P1, 'bench')
        t.put(self.filler, P1, 'active')
        self.hand(t, 2)
        await t.use(bib, 'Industrious Incisors')
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        self.assertIsNone(t.ability_offer(bib, 'Industrious Incisors'))

    async def test_bibarel_not_with_five_in_hand(self):
        t = self.table()
        bib = t.put(BIBAREL, P1, 'bench')
        self.hand(t, 5)
        self.assertIsNone(t.ability_offer(bib, 'Industrious Incisors'))

    # --- Skwovet: Nest Stash -------------------------------------------------
    async def test_skwovet_nest_stash(self):
        t = self.table()
        sk = t.put(SKWOVET, P1, 'bench')
        t.put(self.filler, P1, 'active')
        old = [t.put(PIKIPEK, P1, 'hand'), t.put(BIDOOF, P1, 'hand'), t.put(MINCCINO, P1, 'hand')]
        await t.use(sk, 'Nest Stash')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertFalse(set(old) & set(hand))
        deck = t.zone(P1, 'deck')
        bottom3 = set(deck[:3])
        self.assertEqual(bottom3, set(old))
        self.assertIsNone(t.ability_offer(sk, 'Nest Stash'))

    async def test_skwovet_nest_stash_empty_hand_draws_nothing(self):
        t = self.table()
        sk = t.put(SKWOVET, P1, 'bench')
        t.put(self.filler, P1, 'active')
        if t.ability_offer(sk, 'Nest Stash') is not None:
            await t.use(sk, 'Nest Stash')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Greedent -------------------------------------------------------------
    async def test_greedent_collect(self):
        t = self.table()
        g = t.put(GREEDENT, P1, 'active')
        t.energy(g, C)
        await t.attack(g, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    async def test_greedent_spill_out_threshold(self):
        for n, dmg in ((5, 210), (4, 60)):
            t = self.table()
            g = t.put(GREEDENT, P1, 'active')
            t.energy(g, C, 2)
            self.hand(t, n)
            await t.attack(g, 'Spill Out')
            with self.subTest(hand=n):
                self.assertEqual(400 - t.hp(self.opp), dmg)
                self.assertEqual(len(t.zone(P1, 'hand')), 0)
                self.assertEqual(len(t.zone(P1, 'discard')), n)

    # --- Hop's Dubwool: Defiant Horn ---------------------------------------
    async def test_dubwool_defiant_horn_on_evolve(self):
        t = self.table()
        target = t.put(SABLEYE, P2, 'bench')
        t.put(self.filler, P1, 'active')
        wooloo = t.put(WOOLOO, P1, 'bench')
        dub = t.put(DUBWOOL, P1, 'hand')
        t.yes = True
        t.pokemon = lambda c, p: target if target in c else c[0]
        await t.play(dub, targets=[wooloo.entity_id])
        self.assertIs(t.active(P2), target)

    async def test_dubwool_defiant_horn_is_optional(self):
        t = self.table()
        t.put(SABLEYE, P2, 'bench')
        t.put(self.filler, P1, 'active')
        wooloo = t.put(WOOLOO, P1, 'bench')
        dub = t.put(DUBWOOL, P1, 'hand')
        t.yes = False
        await t.play(dub, targets=[wooloo.entity_id])
        self.assertIs(t.active(P2), self.opp)

    # --- Hop's Snorlax ----------------------------------------------------------
    async def test_extra_helpings_boosts_hops_only_no_stack(self):
        for snorlaxes, attacker, title, base in ((1, WOOLOO, 'Smash Kick', 50),
                                                 (2, WOOLOO, 'Smash Kick', 50),
                                                 (1, PIKIPEK, 'Double Stab', 20),
                                                 (0, WOOLOO, 'Smash Kick', 50)):
            t = self.table()
            a = t.put(attacker, P1, 'active')
            t.energy(a, C, 3)
            for _ in range(snorlaxes):
                t.put(HOP_SNORLAX, P1, 'bench')
            t.heads = True
            await t.attack(a, title)
            bonus = 30 if snorlaxes and attacker == WOOLOO else 0
            with self.subTest(snorlaxes=snorlaxes, attacker=attacker):
                self.assertEqual(400 - t.hp(self.opp), base + bonus)

    async def test_extra_helpings_stacks_with_hops_choice_band(self):
        t = self.table()
        w = t.put(WOOLOO, P1, 'active')
        t.energy(w, C, 3)
        t.attach('SV09.HopsChoiceBand_148', w)
        t.put(HOP_SNORLAX, P1, 'bench')
        await t.attack(w, 'Smash Kick')
        self.assertEqual(400 - t.hp(self.opp), 50 + 30 + 30)

    async def test_extra_helpings_not_for_opponents_hops(self):
        t = self.table(WOOLOO)
        t.energy(self.opp, C, 3)
        mine = t.put(self.filler, P1, 'active', hp=300)
        mine.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.put(HOP_SNORLAX, P1, 'bench')
        t.next_turn()
        before = t.hp(mine)
        await t.attack(self.opp, 'Smash Kick', pid=P2)
        self.assertEqual(before - t.hp(mine), 50)

    async def test_hops_snorlax_dynamic_press(self):
        t = self.table()
        s = t.put(HOP_SNORLAX, P1, 'active')
        t.energy(s, C, 3)
        await t.attack(s, 'Dynamic Press')
        self.assertEqual(400 - t.hp(self.opp), 140 + 30)   # it is a Hop's Pokémon itself
        self.assertEqual(t.damage(s), 80)

    # --- Hop's Cramorant: Fickle Spitting -----------------------------------
    async def test_cramorant_fickle_spitting_prize_window(self):
        for prizes, dmg in ((2, 0), (3, 120), (4, 120), (5, 0)):
            t = self.table()
            c = t.put(CRAMORANT, P1, 'active')
            t.energy(c, C)
            t.set_prizes(P2, prizes)
            await t.attack(c, 'Fickle Spitting')
            with self.subTest(prizes=prizes):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    async def test_cramorant_counts_opponents_prizes_not_mine(self):
        t = self.table()
        c = t.put(CRAMORANT, P1, 'active')
        t.energy(c, C)
        t.set_prizes(P1, 3)
        t.set_prizes(P2, 6)
        await t.attack(c, 'Fickle Spitting')
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Oranguru -------------------------------------------------------------
    async def test_oranguru_instruct(self):
        t = self.table()
        o = t.put(ORANGURU, P1, 'bench')
        t.put(self.filler, P1, 'active')
        self.hand(t, 1)
        await t.use(o, 'Instruct')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertIsNone(t.ability_offer(o, 'Instruct'))

    async def test_oranguru_instruct_with_full_hand_draws_nothing(self):
        t = self.table()
        o = t.put(ORANGURU, P1, 'bench')
        t.put(self.filler, P1, 'active')
        self.hand(t, 4)
        if t.ability_offer(o, 'Instruct') is not None:
            await t.use(o, 'Instruct')
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    async def test_oranguru_psychic(self):
        for n in (0, 2):
            t = self.table()
            o = t.put(ORANGURU, P1, 'active')
            t.energy(o, C, 3)
            if n:
                t.energy(self.opp, PokemonTypes.WATER, n)
            await t.attack(o, 'Psychic')
            with self.subTest(opp_energy=n):
                self.assertEqual(400 - t.hp(self.opp), 60 + 20 * n)

    async def test_oranguru_psychic_ignores_own_energy_and_bench(self):
        t = self.table()
        o = t.put(ORANGURU, P1, 'active')
        t.energy(o, C, 4)
        bench = t.put(self.filler, P2, 'bench')
        t.energy(bench, PokemonTypes.WATER, 3)
        await t.attack(o, 'Psychic')
        self.assertEqual(400 - t.hp(self.opp), 60)

    # --- Fan Rotom ------------------------------------------------------------
    async def test_fan_call_first_turn_colorless_100_or_less(self):
        t = self.table()
        t.state.turn_number = 2
        rotom = t.put(FAN_ROTOM, P1, 'active')
        t.deck(P1, [PIKIPEK, MINCCINO, HOP_SNORLAX, ORANGURU, SABLEYE, CRAMORANT, TRUMBEAK])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (
            seen.setdefault('n', (t.names(cards), count)), cards[:count])[1]
        await t.use(rotom, 'Fan Call')
        names, count = seen['n']
        self.assertEqual(count, 3)
        self.assertEqual(sorted(set(names)), ['Minccino', 'Pikipek', 'Trumbeak'])
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_fan_call_not_after_first_turn(self):
        t = self.table()
        t.state.turn_number = 3
        rotom = t.put(FAN_ROTOM, P1, 'active')
        self.assertIsNone(t.ability_offer(rotom, 'Fan Call'))

    async def test_fan_call_only_one_per_turn(self):
        t = self.table()
        t.state.turn_number = 2
        r1 = t.put(FAN_ROTOM, P1, 'active')
        r2 = t.put(FAN_ROTOM, P1, 'bench')
        await t.use(r1, 'Fan Call')
        self.assertIsNone(t.ability_offer(r2, 'Fan Call'))

    async def test_assault_landing_needs_stadium(self):
        for stadium, dmg in ((None, 0), (P2, 70), (P1, 70)):
            t = self.table()
            r = t.put(FAN_ROTOM, P1, 'active')
            t.energy(r, C)
            if stadium:
                t.stadium(ARTAZON, stadium)
            await t.attack(r, 'Assault Landing')
            with self.subTest(stadium=stadium):
                self.assertEqual(400 - t.hp(self.opp), dmg)


if __name__ == "__main__":
    unittest.main()
