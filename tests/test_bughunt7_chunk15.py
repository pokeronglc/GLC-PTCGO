"""Bug hunt round 7, chunk 15: Gladion's Final Battle, Pikachu x3, Sizzlipede,
Cubchoo, Fiery Flint, Galarian Perrserker, N's Darmanitan, Rocky Fighting
Energy, Galarian Meowth, Uxie, Girafarig, Flapple, Delphox -- each card
checked against its text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT, PSY, METAL, LIGHT = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.FIGHTING,
    PokemonTypes.PSYCHIC, PokemonTypes.METAL, PokemonTypes.LIGHTNING)

GLADION = 'ME5.GladionsFinalBattle_77'
PIKA_PAL, PIKA_TEF, PIKA_LOR = 'SV2.Pikachu_62', 'SV05.Pikachu_51', 'SWSH11.Pikachu_52'
SIZZLIPEDE = 'SWSH1.Sizzlipede_38'
CUBCHOO = 'ZSV10PT5.Cubchoo_25'
FLINT = 'DM.FieryFlint_60'
PERRSERKER = 'SWSH1.GalarianPerrserker_128'
DARMANITAN = 'SV09.NsDarmanitan_27'
ROCKY = 'ME3.RockyFightingEnergy_87'
G_MEOWTH = 'ME55.GalarianMeowth_101'
UXIE = 'SV08.Uxie_78'
GIRAFARIG = 'SM8.Girafarig_94'
FLAPPLE = 'SWSH7.Flapple_120'
DELPHOX = 'XY1.Delphox_26'
TIMBURR = 'BW1.Timburr_58'                    # a Fighting Basic
SWITCH = 'SV1.Switch_194'
DOUBLE_TURBO = 'SWSH9.DoubleTurboEnergy_151'    # a Special Energy


class Chunk15(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def theirs(self, t, spec, zone='bench'):
        p = t.put(spec, P2, zone)
        p.set_attribute(AttrID.HP, 400)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def dealt(self, t, p=None):
        return 400 - t.hp(p or self.opp)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        title, dmg = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    def is_fire(self, card):
        return card.archetype_id.lower() == self.energies[FIRE.value].lower()

    def is_basic_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    # --- Gladion's Final Battle PBL 77 ----------------------------------
    async def test_gladion_only_as_last_card(self):
        t = self.table()
        self.mine(t, G_MEOWTH, METAL, 1)
        g = t.put(GLADION, P1, 'hand')
        self.assertTrue(t.can(g, 'UseTrainerCard'))
        t.put(self.item, P1, 'hand')
        self.assertFalse(t.can(g, 'UseTrainerCard'))

    async def test_gladion_plus_80_to_active_this_turn_only(self):
        t = self.table()
        meowth = self.mine(t, G_MEOWTH, METAL, 1)
        g = t.put(GLADION, P1, 'hand')
        await t.play(g)
        self.assertIn(g, t.zone(P1, 'discard'))
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 90)
        # next own turn: gone
        self.opp.set_attribute(AttrID.HP, 400)
        t.next_turn()
        t.next_turn()
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 10)

    async def test_gladion_does_not_boost_bench_damage(self):
        t = self.table()
        pika = self.mine(t, PIKA_TEF, LIGHT, 1)
        bench = self.theirs(t, self.filler)
        g = t.put(GLADION, P1, 'hand')
        await t.play(g)
        t.picks = lambda c, n, p, d: [bench] if bench in c else c[:n]
        await t.attack(pika, 'Random Spark')
        self.assertEqual(self.dealt(t, bench), 10)
        self.assertEqual(self.dealt(t), 0)

    async def test_gladion_benched_before_play_then_switched_in(self):
        # control for the next test: same Switch line, Meowth already benched
        t = self.table()
        self.mine(t, self.filler)
        meowth = self.mine(t, G_MEOWTH, METAL, 1, zone='bench')
        g = t.put(GLADION, P1, 'hand')
        await t.play(g)
        sw = t.put(SWITCH, P1, 'hand')
        t.pokemon = lambda c, p: meowth if meowth in c else c[0]
        await t.play(sw)
        self.assertIs(t.active(P1), meowth)
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 90)


    # BUG: Gladion's +80 is attached only to Pokemon already in play when it is played
    async def test_gladion_boosts_pokemon_put_in_play_after_it(self):
        # "During this turn, attacks used by your Pokemon ..." -- a Basic
        # benched after Gladion and switched in is still one of your Pokemon.
        t = self.table()
        self.mine(t, self.filler)
        g = t.put(GLADION, P1, 'hand')
        await t.play(g)
        meowth = t.put(G_MEOWTH, P1, 'hand')
        await t.play(meowth)
        self.assertIn(meowth, t.zone(P1, 'bench'))
        t.energy(meowth, METAL, 1)
        sw = t.put(SWITCH, P1, 'hand')
        t.pokemon = lambda c, p: meowth if meowth in c else c[0]
        await t.play(sw)
        self.assertIs(t.active(P1), meowth)
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 90)

    # --- Pikachu PAL 62: Growl ------------------------------------------
    async def test_pikachu_growl_reduces_next_turn_attack(self):
        t = self.table()
        pika = self.mine(t, PIKA_PAL, LIGHT, 1)
        pika.set_attribute(AttrID.HP, 300)
        await t.attack(pika, 'Growl')
        self.assertEqual(self.dealt(t), 0)
        dmg = await self.opp_hits(t)
        self.assertEqual(300 - t.hp(pika), max(0, dmg - 20))

    async def test_pikachu_growl_expires(self):
        t = self.table()
        pika = self.mine(t, PIKA_PAL, LIGHT, 1)
        pika.set_attribute(AttrID.HP, 300)
        await t.attack(pika, 'Growl')
        await self.opp_hits(t)
        before = t.hp(pika)
        t.next_turn()
        t.next_turn()
        title, dmg = self.filler_attack()
        await t.attack(self.opp, title, pid=P2)
        self.assertEqual(before - t.hp(pika), dmg)

    # --- Pikachu TEF 51: Random Spark -------------------------------------
    async def test_pikachu_random_spark_any_target_no_wr_on_bench(self):
        t = self.table()
        pika = self.mine(t, PIKA_TEF, LIGHT, 1)
        bench = self.theirs(t, self.filler)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [LIGHT.value])
        t.picks = lambda c, n, p, d: [bench] if bench in c else c[:n]
        await t.attack(pika, 'Random Spark')
        self.assertEqual(self.dealt(t, bench), 10)
        self.assertEqual(self.dealt(t), 0)

    async def test_pikachu_random_spark_active_applies_weakness(self):
        t = self.table()
        pika = self.mine(t, PIKA_TEF, LIGHT, 1)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [LIGHT.value])
        t.picks = lambda c, n, p, d: [self.opp] if self.opp in c else c[:n]
        await t.attack(pika, 'Random Spark')
        self.assertEqual(self.dealt(t), 20)

    # --- Pikachu LOR 52: Pika Dash / Whimsy Tackle --------------------------
    async def test_pikachu_pika_dash_free_retreat_only_with_energy(self):
        t = self.table()
        pika = self.mine(t, PIKA_LOR)
        self.assertEqual(t.retreat(pika), 1)
        t.energy(pika, LIGHT, 1)
        self.assertEqual(t.retreat(pika), 0)
        # another Pokemon with energy is not affected
        other = self.mine(t, self.filler, LIGHT, 1, zone='bench')
        self.assertGreater(t.retreat(other), 0)

    async def test_pikachu_whimsy_tackle_flip(self):
        for heads, expected in ((True, 50), (False, 0)):
            t = self.table()
            pika = self.mine(t, PIKA_LOR, LIGHT, 3)
            t.heads = heads
            await t.attack(pika, 'Whimsy Tackle')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(t), expected)

    # --- Sizzlipede SSH 38: Relentless Flames ---------------------------
    async def test_sizzlipede_flip_until_tails(self):
        for heads, expected in ((3, 120), (0, 0)):
            t = self.table()
            me = self.mine(t, SIZZLIPEDE, FIRE, 2)

            async def until_tails(ctx, title=''):
                return heads
            with patch.object(EffectContext, 'flip_until_tails', until_tails):
                await t.attack(me, 'Relentless Flames')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(t), expected)

    # --- Cubchoo BLK 25: Snotted Up ---------------------------------------
    async def test_cubchoo_snotted_up_locks_next_turn_only(self):
        t = self.table()
        cub = self.mine(t, CUBCHOO, WATER, 1)
        title, _ = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        await t.attack(cub, 'Snotted Up')
        self.assertEqual(self.dealt(t), 10)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, title, pid=P2))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, title, pid=P2))

    async def test_cubchoo_lock_ends_when_defender_leaves_active(self):
        t = self.table()
        cub = self.mine(t, CUBCHOO, WATER, 1)
        title, _ = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        other = self.theirs(t, self.filler)
        t.energy(other, WATER, 5)
        await t.attack(cub, 'Snotted Up')
        t.next_turn()
        # swap Active and Bench manually: new Active is not the Defending Pokemon
        sw = t.put(SWITCH, P2, 'hand')
        t.pokemon = lambda c, p: other if other in c else c[0]
        await t.play(sw, pid=P2)
        self.assertIs(t.active(P2), other)
        self.assertIsNotNone(t.attack_offer(other, title, pid=P2))

    # --- Fiery Flint DRM 60 ------------------------------------------------
    async def test_fiery_flint_discard_two_search_four_fire(self):
        t = self.table()
        self.mine(t, self.filler)
        flint = t.put(FLINT, P1, 'hand')
        a = t.put(self.item, P1, 'hand')
        b = t.put(self.item, P1, 'hand')
        fires = t.deck(P1, [t.basic_energy(FIRE)] * 5)
        water = t.deck(P1, [t.basic_energy(WATER)])[0]
        self.assertTrue(t.can(flint, 'UseTrainerCard'))
        await t.play(flint)
        hand = t.zone(P1, 'hand')
        self.assertIn(a, t.zone(P1, 'discard'))
        self.assertIn(b, t.zone(P1, 'discard'))
        self.assertEqual(sum(1 for c in hand if self.is_fire(c)), 4)
        self.assertNotIn(water, hand)
        self.assertIn(flint, t.zone(P1, 'discard'))

    async def test_fiery_flint_needs_two_other_cards(self):
        t = self.table()
        self.mine(t, self.filler)
        flint = t.put(FLINT, P1, 'hand')
        t.put(self.item, P1, 'hand')
        t.deck(P1, [t.basic_energy(FIRE)])
        self.assertFalse(t.can(flint, 'UseTrainerCard'))

    # --- Galarian Perrserker SSH 128: Steely Spirit -----------------------
    async def test_perrserker_boosts_metal_active_from_bench_and_stacks(self):
        t = self.table()
        meowth = self.mine(t, G_MEOWTH, METAL, 1)
        self.mine(t, PERRSERKER, zone='bench')
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 30)
        t = self.table()
        meowth = self.mine(t, G_MEOWTH, METAL, 1)
        self.mine(t, PERRSERKER, zone='bench')
        self.mine(t, PERRSERKER, zone='bench')
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 50)

    async def test_perrserker_not_for_non_metal_or_bench_or_opponent(self):
        t = self.table()
        pika = self.mine(t, PIKA_TEF, LIGHT, 1)
        self.mine(t, PERRSERKER, zone='bench')
        bench = self.theirs(t, self.filler)
        t.picks = lambda c, n, p, d: [self.opp] if self.opp in c else c[:n]
        await t.attack(pika, 'Random Spark')          # Lightning: no boost
        self.assertEqual(self.dealt(t), 10)
        # the opponent's Perrserker does not boost my Metal attacker
        t = self.table()
        meowth = self.mine(t, G_MEOWTH, METAL, 1)
        self.theirs(t, PERRSERKER)
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 10)

    # --- N's Darmanitan JTG 27 ---------------------------------------------
    async def test_darmanitan_back_draft_counts_opp_basic_energy_only(self):
        t = self.table()
        me = self.mine(t, DARMANITAN, FIRE, 2)
        for _ in range(3):
            t.put(t.basic_energy(WATER), P2, 'discard')
        t.put(DOUBLE_TURBO, P2, 'discard')             # Special: not counted
        t.put(t.basic_energy(FIRE), P1, 'discard')     # mine: not counted
        await t.attack(me, 'Back Draft')
        self.assertEqual(self.dealt(t), 90)

    async def test_darmanitan_back_draft_zero(self):
        t = self.table()
        me = self.mine(t, DARMANITAN, FIRE, 2)
        t.put(t.basic_energy(FIRE), P1, 'discard')
        await t.attack(me, 'Back Draft')
        self.assertEqual(self.dealt(t), 0)

    async def test_darmanitan_flamebody_cannon(self):
        t = self.table()
        me = self.mine(t, DARMANITAN, FIRE, 3)
        bench = self.theirs(t, self.filler)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [FIRE.value])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(me, 'Flamebody Cannon')
        self.assertEqual(self.dealt(t), 90)
        self.assertEqual(self.dealt(t, bench), 90)
        self.assertEqual([c for c in me.children if self.is_basic_energy(c)], [])
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_fire(c)), 3)

    async def test_darmanitan_flamebody_cannon_no_bench(self):
        t = self.table()
        me = self.mine(t, DARMANITAN, FIRE, 3)
        await t.attack(me, 'Flamebody Cannon')
        self.assertEqual(self.dealt(t), 90)
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_fire(c)), 3)

    # --- Rocky Fighting Energy POR 87 ------------------------------------
    async def _rocky_vs_snotted_up(self, spec):
        t = Table(self)
        me = self.mine(t, spec)
        me.set_attribute(AttrID.HP, 300)
        rocky = t.put(ROCKY, P1, 'hand')
        await t.play(rocky, targets=[me.entity_id])
        self.assertIn(rocky, me.children)
        t.energy(me, FIGHT, 3)
        cub = t.put(CUBCHOO, P2, 'active')
        cub.set_attribute(AttrID.HP, 300)
        t.energy(cub, WATER, 1)
        t.next_turn()
        await t.attack(cub, 'Snotted Up', pid=P2)
        damaged = 300 - t.hp(me)
        t.next_turn()
        title = next(a.title for a in def_for(me.archetype_id).abilities
                     if isinstance(a, Attack))
        return t, me, damaged, t.attack_offer(me, title)

    async def test_rocky_shields_fighting_pokemon_from_effects_not_damage(self):
        t, me, damaged, offer = await self._rocky_vs_snotted_up(TIMBURR)
        self.assertEqual(damaged, 10)
        self.assertIsNotNone(offer)

    async def test_rocky_does_not_shield_non_fighting(self):
        t, me, damaged, offer = await self._rocky_vs_snotted_up(self.filler)
        self.assertEqual(damaged, 10)
        self.assertIsNone(offer)

    async def test_rocky_provides_fighting(self):
        t = self.table()
        me = self.mine(t, TIMBURR)
        rocky = t.put(ROCKY, P1, 'hand')
        await t.play(rocky, targets=[me.entity_id])
        self.assertIsNone(t.attack_offer(me, 'Pound'))      # [F][F], only 1 so far
        t.energy(me, FIGHT, 1)
        self.assertIsNotNone(t.attack_offer(me, 'Pound'))   # Rocky pays one [F]

    # --- Galarian Meowth 30C 101 -----------------------------------------
    async def test_galarian_meowth_pay_day_draws(self):
        t = self.table()
        meowth = self.mine(t, G_MEOWTH, METAL, 1)
        top = t.deck(P1, [self.filler])[0]
        await t.attack(meowth, 'Pay Day')
        self.assertEqual(self.dealt(t), 10)
        self.assertEqual(t.zone(P1, 'hand'), [top])

    async def test_galarian_meowth_treasure_rush_counts_hand(self):
        for n in (4, 0):
            t = self.table()
            meowth = self.mine(t, G_MEOWTH, METAL, 1)
            for _ in range(n):
                t.put(self.item, P1, 'hand')
            t.put(self.item, P2, 'hand')               # opponent's hand: not counted
            await t.attack(meowth, 'Treasure Rush')
            with self.subTest(n=n):
                self.assertEqual(self.dealt(t), 10 * n)

    # --- Uxie SSP 78: Painful Memories ------------------------------------
    async def test_uxie_painful_memories(self):
        t = self.table()
        uxie = self.mine(t, UXIE, PSY, 1)
        b1 = self.theirs(t, self.filler)
        b2 = self.theirs(t, self.filler)
        mine_bench = self.mine(t, self.filler, zone='bench')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [PSY.value])
        await t.attack(uxie, 'Painful Memories')
        for p in (self.opp, b1, b2):
            self.assertEqual(self.dealt(t, p), 20)     # counters ignore Weakness
        self.assertEqual(t.damage(mine_bench), 0)
        self.assertEqual(t.damage(uxie), 0)

    # --- Girafarig LOT 94 --------------------------------------------------
    async def test_girafarig_get_lost_two_cards(self):
        t = self.table()
        me = self.mine(t, GIRAFARIG, PSY, 1)
        cards = [t.put(self.item, P2, 'discard') for _ in range(3)]
        mine_card = t.put(self.item, P1, 'discard')
        await t.attack(me, 'Get Lost')
        self.assertEqual(len(t.zone(P2, 'lostZone')), 2)
        self.assertEqual(len(t.zone(P2, 'discard')), 1)
        self.assertIn(mine_card, t.zone(P1, 'discard'))

    async def test_girafarig_get_lost_fewer_cards(self):
        t = self.table()
        me = self.mine(t, GIRAFARIG, PSY, 1)
        t.put(self.item, P2, 'discard')
        await t.attack(me, 'Get Lost')
        self.assertEqual(len(t.zone(P2, 'lostZone')), 1)
        self.assertEqual(t.zone(P2, 'discard'), [])

    async def test_girafarig_mind_shock_ignores_wr(self):
        t = self.table()
        me = self.mine(t, GIRAFARIG, PSY, 3)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [PSY.value])
        await t.attack(me, 'Mind Shock')
        self.assertEqual(self.dealt(t), 70)
        t = self.table()
        me = self.mine(t, GIRAFARIG, PSY, 3)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, PSY.value)
        await t.attack(me, 'Mind Shock')
        self.assertEqual(self.dealt(t), 70)

    # --- Flapple EVS 120 --------------------------------------------------
    async def test_flapple_acidic_mucus_counts_opp_ability_pokemon(self):
        t = self.table()
        me = self.mine(t, FLAPPLE, FIRE, 1)
        self.theirs(t, DELPHOX)                        # activated Ability
        self.theirs(t, PERRSERKER)                     # passive Ability
        self.theirs(t, self.filler)                    # no Ability
        self.mine(t, DELPHOX, zone='bench')            # mine: not counted
        await t.attack(me, 'Acidic Mucus')
        self.assertEqual(self.dealt(t), 100)

    async def test_flapple_acidic_mucus_none(self):
        t = self.table()
        me = self.mine(t, FLAPPLE, FIRE, 1)
        self.mine(t, DELPHOX, zone='bench')
        await t.attack(me, 'Acidic Mucus')
        self.assertEqual(self.dealt(t), 0)

    async def test_flapple_fighting_tackle_non_v(self):
        t = self.table()
        me = self.mine(t, FLAPPLE)
        t.energy(me, PokemonTypes.GRASS, 1)
        t.energy(me, FIRE, 1)
        await t.attack(me, 'Fighting Tackle')
        self.assertEqual(self.dealt(t), 80)

    # --- Delphox XY 26 ------------------------------------------------------
    async def test_delphox_mystical_fire_draws_to_six_once(self):
        t = self.table()
        dx = self.mine(t, DELPHOX, zone='bench')
        self.mine(t, self.filler)
        for _ in range(2):
            t.put(self.item, P1, 'hand')
        await t.use(dx, 'Mystical Fire')
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        discard = t.board.find_player_area(P1, 'discard')
        for c in t.zone(P1, 'hand')[:3]:
            t.board.move_card(c.entity_id, discard.entity_id)
        self.assertIsNone(t.ability_offer(dx, 'Mystical Fire'))

    async def test_delphox_mystical_fire_full_hand(self):
        t = self.table()
        dx = self.mine(t, DELPHOX)
        for _ in range(7):
            t.put(self.item, P1, 'hand')
        offer = t.ability_offer(dx, 'Mystical Fire')
        if offer is not None:
            await t.do(offer)
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_delphox_blaze_ball(self):
        t = self.table()
        dx = self.mine(t, DELPHOX, FIRE, 2)
        t.energy(dx, WATER, 1)
        await t.attack(dx, 'Blaze Ball')
        self.assertEqual(self.dealt(t), 90)


if __name__ == '__main__':
    unittest.main()
