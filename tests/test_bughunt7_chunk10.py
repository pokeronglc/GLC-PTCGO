"""Bug hunt round 7, chunk 10: Sneasel, Ponyta/Rapidash, Martial Arts Dojo,
Emboar, Tirtouga, Antique Cover Fossil, Snorunt, Dusk Ball, Therapeutic
Energy, Mystery Garden, Oddish, Kyurem, Combusken, Bicycle -- each card
checked against its text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED, ASLEEP, PARALYZED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT, PSY, GRASS, DARK = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.FIGHTING,
    PokemonTypes.PSYCHIC, PokemonTypes.GRASS, PokemonTypes.DARKNESS)

SNEASEL = 'SM3.Sneasel_85'
PONYTA, RAPIDASH = 'XY2.Ponyta_14', 'SM9.Rapidash_18'
DOJO = 'SM10.MartialArtsDojo_179'
EMBOAR = 'RSV10PT5.Emboar_13'
TIRTOUGA, COVER = 'ZSV10PT5.Tirtouga_22', 'SV07.AntiqueCoverFossil_129'
SNORUNT = 'SWSH12.Snorunt_41'
DUSK_BALL = 'SV08.DuskBall_175'
THERAPEUTIC = 'SV2.TherapeuticEnergy_193'
GARDEN = 'ME1.MysteryGarden_122'
ODDISH = 'SVP.Oddish_102'
KYUREM = 'BW11.Kyurem_43'
COMBUSKEN = 'SV10.Combusken_41'
BICYCLE = 'BW8.Bicycle_117'
RALTS = 'SWSH10.Ralts_60'                    # a Psychic Basic
GUZMA = 'SM3.Guzma_115'                      # a Supporter
FLOAT_STONE = 'BW9.FloatStone_99'            # a Pokémon Tool
DURALUDON = 'ME2.Duraludon_74'               # Hyper Beam discards an Energy


class Chunk10(unittest.IsolatedAsyncioTestCase):
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

    def dealt(self, t):
        return 400 - t.hp(self.opp)

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

    # --- Sneasel BUS 85: Hone Claws -> Slash 80 next turn ------------------
    async def test_sneasel_hone_claws_boosts_next_turn_slash(self):
        t = self.table()
        sneasel = self.mine(t, SNEASEL, DARK, 2)
        await t.attack(sneasel, 'Hone Claws')
        self.assertEqual(self.dealt(t), 0)
        t.next_turn()
        t.next_turn()
        await t.attack(sneasel, 'Slash')
        self.assertEqual(self.dealt(t), 80)

    async def test_sneasel_slash_plain_and_boost_expires(self):
        t = self.table()
        sneasel = self.mine(t, SNEASEL, DARK, 2)
        await t.attack(sneasel, 'Slash')
        self.assertEqual(self.dealt(t), 20)
        # Hone Claws, then skip a whole turn of ours: the boost is gone.
        t = self.table()
        sneasel = self.mine(t, SNEASEL, DARK, 2)
        await t.attack(sneasel, 'Hone Claws')
        for _ in range(4):
            t.next_turn()
        await t.attack(sneasel, 'Slash')
        self.assertEqual(self.dealt(t), 20)

    # --- Ponyta FLF 14 / Rapidash TEU 18: Agility --------------------------
    async def test_agility_heads_prevents_damage_and_effects(self):
        for spec, cost, dmg in ((PONYTA, 1, 10), (RAPIDASH, 2, 60)):
            for heads in (True, False):
                t = self.table()
                me = self.mine(t, spec, FIRE, cost)
                me.set_attribute(AttrID.HP, 300)
                t.heads = heads
                await t.attack(me, 'Agility')
                with self.subTest(card=spec, heads=heads):
                    self.assertEqual(self.dealt(t), dmg)
                    hit = await self.opp_hits(t)
                    self.assertEqual(300 - t.hp(me), 0 if heads else hit)

    async def test_agility_prevention_ends_after_opponents_turn(self):
        t = self.table()
        me = self.mine(t, PONYTA, FIRE, 1)
        me.set_attribute(AttrID.HP, 300)
        t.heads = True
        await t.attack(me, 'Agility')
        await self.opp_hits(t)                       # prevented
        t.next_turn()                                # our turn
        t.next_turn()                                # opponent again
        title, dmg = self.filler_attack()
        await t.attack(self.opp, title, pid=P2)
        self.assertEqual(300 - t.hp(me), dmg)

    async def test_rapidash_searing_flame_burns(self):
        t = self.table()
        me = self.mine(t, RAPIDASH, FIRE, 1)
        await t.attack(me, 'Searing Flame')
        self.assertEqual(self.dealt(t), 20)
        self.assertIn(BURNED, t.conditions(self.opp))
        self.assertNotIn(BURNED, t.conditions(me))

    # --- Martial Arts Dojo UNB 179 (end to end through a real attack) ------
    async def test_dojo_real_attack_bonus(self):
        for kind, ours, theirs, expected in ((FIGHT, 6, 6, 30), (FIGHT, 6, 5, 60),
                                             (FIGHT, 5, 6, 30), (FIRE, 6, 5, 20)):
            t = self.table()
            t.stadium(DOJO, P2)
            me = self.mine(t, COMBUSKEN, kind, 1)
            t.set_prizes(P1, ours)
            t.set_prizes(P2, theirs)
            await t.attack(me, 'Combustion')
            with self.subTest(kind=kind, prizes=(ours, theirs)):
                self.assertEqual(self.dealt(t), expected)

    # --- Emboar WHT 13: Inferno Fandango -----------------------------------
    async def test_emboar_inferno_fandango_repeatable(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        emboar = self.mine(t, EMBOAR, zone='bench')
        target = t.active(P1)
        f1 = t.put(t.basic_energy(FIRE), P1, 'hand')
        f2 = t.put(t.basic_energy(FIRE), P1, 'hand')
        t.pokemon = lambda c, p: target if target in c else c[0]
        # One activation loops ("attach, or Done") until Done / no Fire left.
        await t.use(emboar, 'Inferno Fandango')
        self.assertIn(f1, target.children)
        self.assertIn(f2, target.children)
        self.assertIsNone(t.ability_offer(emboar, 'Inferno Fandango'))  # no Fire left

    async def test_emboar_inferno_fandango_done_then_again(self):
        t = self.table()
        emboar = self.mine(t, EMBOAR)
        f1 = t.put(t.basic_energy(FIRE), P1, 'hand')
        f2 = t.put(t.basic_energy(FIRE), P1, 'hand')
        calls = []

        def picks(cards, count, prompt, display):
            calls.append(prompt)
            return cards[:1] if len(calls) == 1 else []        # attach one, then Done
        t.picks = picks
        await t.use(emboar, 'Inferno Fandango')
        self.assertEqual(sum(c in emboar.children for c in (f1, f2)), 1)
        t.picks = None
        await t.use(emboar, 'Inferno Fandango')                # usable again
        self.assertIn(f1, emboar.children)
        self.assertIn(f2, emboar.children)

    async def test_emboar_inferno_fandango_not_for_other_energy(self):
        t = self.table()
        emboar = self.mine(t, EMBOAR)
        water = t.put(t.basic_energy(WATER), P1, 'hand')
        offer = t.ability_offer(emboar, 'Inferno Fandango')
        if offer is not None:
            await t.do(offer)
        self.assertIn(water, t.zone(P1, 'hand'))
        self.assertEqual([c for c in emboar.children if not self.is_fire(c)], [])

    async def test_emboar_inferno_fandango_ignores_energy_attach_limit(self):
        t = self.table()
        emboar = self.mine(t, EMBOAR)
        manual = t.put(t.basic_energy(FIRE), P1, 'hand')
        await t.play(manual, targets=[emboar.entity_id])   # normal once-per-turn attach
        self.assertIn(manual, emboar.children)
        extra = t.put(t.basic_energy(FIRE), P1, 'hand')
        await t.use(emboar, 'Inferno Fandango')
        self.assertIn(extra, emboar.children)

    # --- Tirtouga BLK 22: Ancient Seaweed ----------------------------------
    async def test_tirtouga_ancient_seaweed_counts_opponent_items(self):
        t = self.table()
        me = self.mine(t, TIRTOUGA, WATER, 1)
        for _ in range(3):
            t.put(self.item, P2, 'discard')
        t.put(GUZMA, P2, 'discard')                  # Supporter: not an Item
        t.put(self.filler, P2, 'discard')            # Pokémon
        t.put(t.basic_energy(WATER), P2, 'discard')  # Energy
        for _ in range(4):
            t.put(self.item, P1, 'discard')          # my own Items don't count
        await t.attack(me, 'Ancient Seaweed')
        self.assertEqual(self.dealt(t), 90)

    async def test_tirtouga_ancient_seaweed_tools_are_not_items(self):
        # Current rules (SWSH onward): Pokémon Tools are their own Trainer
        # category, not Item cards.
        t = self.table()
        me = self.mine(t, TIRTOUGA, WATER, 1)
        t.put(FLOAT_STONE, P2, 'discard')
        t.put(self.item, P2, 'discard')
        await t.attack(me, 'Ancient Seaweed')
        self.assertEqual(self.dealt(t), 30)

    async def test_tirtouga_ancient_seaweed_zero_items(self):
        t = self.table()
        me = self.mine(t, TIRTOUGA, WATER, 1)
        t.put(GUZMA, P2, 'discard')
        await t.attack(me, 'Ancient Seaweed')
        self.assertEqual(self.dealt(t), 0)

    # --- Antique Cover Fossil SCR 129 --------------------------------------
    async def test_cover_fossil_does_not_block_own_side_or_damage(self):
        # Protective Cover vs an opponent's attack effect is covered in
        # test_antique_fossil_abilities; here: special conditions blocked by the
        # Fossil body, damage still lands, and it can't retreat.
        t = Table(self)
        t.put(self.filler, P1, 'active')
        card = t.put(COVER, P1, 'hand')
        await t.play(card)
        fossil = next(p for p in t.zone(P1, 'bench'))
        fossil.set_attribute(AttrID.HP, 60)
        await t._run(lambda: EffectContext(t.session, P1, fossil, None).switch_active(P1, fossil))
        dura = t.put(DURALUDON, P2, 'active')
        t.energy(dura, PokemonTypes.METAL, 3)
        energy = t.energy(fossil, DARK)
        fossil.set_attribute(AttrID.HP, 200)
        t.next_turn()
        await t.attack(dura, 'Hyper Beam', pid=P2)
        self.assertIn(energy, fossil.children)
        self.assertGreater(200 - t.hp(fossil), 0)

    # --- Snorunt SIT 41: Collect -------------------------------------------
    async def test_snorunt_collect_draws_one(self):
        t = self.table()
        me = self.mine(t, SNORUNT, WATER, 1)
        top = t.deck(P1, [self.filler])[0]
        deck_before = len(t.zone(P1, 'deck'))
        await t.attack(me, 'Collect')
        self.assertEqual(t.zone(P1, 'hand'), [top])
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before - 1)
        self.assertEqual(self.dealt(t), 0)

    # --- Therapeutic Energy PAL 193 ----------------------------------------
    async def test_therapeutic_provides_colorless_only(self):
        t = self.table()
        snorunt = self.mine(t, SNORUNT)
        energy = t.put(THERAPEUTIC, P1, 'hand')
        await t.play(energy, targets=[snorunt.entity_id])
        self.assertIsNotNone(t.attack_offer(snorunt, 'Collect'))     # [C]
        self.assertIsNone(t.attack_offer(snorunt, 'Icy Snow'))       # [W][C]
        t2 = self.table()
        ponyta = self.mine(t2, PONYTA)
        e2 = t2.put(THERAPEUTIC, P1, 'hand')
        await t2.play(e2, targets=[ponyta.entity_id])
        self.assertIsNone(t2.attack_offer(ponyta, 'Agility'))        # [R]

    async def test_therapeutic_recovers_asleep_but_not_poisoned_burned(self):
        t = self.table()
        me = self.mine(t, SNORUNT)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [ASLEEP, POISONED, BURNED])
        energy = t.put(THERAPEUTIC, P1, 'hand')
        await t.play(energy, targets=[me.entity_id])
        self.assertEqual(t.conditions(me), {POISONED, BURNED})

    # --- Dusk Ball SSP 175 -------------------------------------------------
    async def test_dusk_ball_finds_pokemon_in_bottom_seven(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        target = t.deck(P1, [RALTS], top=False)[0]            # the very bottom
        ball = t.put(DUSK_BALL, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is target][:count]
        await t.play(ball)
        self.assertIn(target, t.zone(P1, 'hand'))
        self.assertIn(7, t.shown)

    async def test_dusk_ball_does_not_see_eighth_card(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        deck = t.board.find_player_area(P1, 'deck')
        target = t.put(RALTS, P1, 'deck')
        deck.children.remove(target)
        deck.children.insert(7, target)                        # 8th from the bottom
        ball = t.put(DUSK_BALL, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is target][:count]
        await t.play(ball)
        self.assertNotIn(target, t.zone(P1, 'hand'))
        self.assertIn(target, t.zone(P1, 'deck'))
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Mystery Garden MEG 122 --------------------------------------------
    async def test_mystery_garden_discard_energy_draw_to_psychic_count(self):
        t = self.table()
        t.put(RALTS, P1, 'active')
        t.put(RALTS, P1, 'bench')
        t.put(RALTS, P1, 'bench')
        t.put(self.filler, P1, 'bench')                        # not Psychic
        stadium = t.stadium(GARDEN, P2)                        # opponent's Stadium works too
        energy = t.put(t.basic_energy(PSY), P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.do(next(iter(t.offers(stadium, None, P1))))
        self.assertIn(energy, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(t.offers(stadium, None, P1), [])      # once per turn

    async def test_mystery_garden_needs_energy_in_hand(self):
        t = self.table()
        t.put(RALTS, P1, 'active')
        stadium = t.stadium(GARDEN, P1)
        t.put(self.item, P1, 'hand')
        self.assertEqual(t.offers(stadium, None, P1), [])

    async def test_mystery_garden_usable_by_opponent_on_their_turn(self):
        t = self.table()
        t.put(RALTS, P1, 'active')
        stadium = t.stadium(GARDEN, P1)
        t.put(RALTS, P2, 'bench')
        t.put(t.basic_energy(PSY), P2, 'hand')
        t.next_turn()
        await t.do(next(iter(t.offers(stadium, None, P2))), pid=P2)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)            # 1 Psychic Pokémon (filler isn't)

    # --- Oddish SVP 102: Grass Knot ----------------------------------------
    async def test_oddish_grass_knot_uses_retreat_cost(self):
        for retreat in (0, 1, 3):
            t = self.table()
            self.opp.set_attribute(AttrID.RETREAT_COST, retreat)
            me = self.mine(t, ODDISH, GRASS, 2)
            await t.attack(me, 'Grass Knot')
            with self.subTest(retreat=retreat):
                self.assertEqual(self.dealt(t), 20 * retreat)

    async def test_oddish_grass_knot_uses_modified_retreat_cost(self):
        t = self.table()
        self.opp.set_attribute(AttrID.RETREAT_COST, 3)
        t.attach(FLOAT_STONE, self.opp)                        # Retreat Cost 0
        self.assertEqual(t.retreat(self.opp), 0)
        me = self.mine(t, ODDISH, GRASS, 2)
        await t.attack(me, 'Grass Knot')
        self.assertEqual(self.dealt(t), 0)

    # --- Kyurem LTR 43 ------------------------------------------------------
    async def test_kyurem_outrage(self):
        for counters in (0, 5):
            t = self.table()
            me = self.mine(t, KYUREM, WATER, 2)
            me.set_attribute(AttrID.HP, 130 - 10 * counters)
            await t.attack(me, 'Outrage')
            with self.subTest(counters=counters):
                self.assertEqual(self.dealt(t), 20 + 10 * counters)

    async def test_kyurem_glaciate_hits_all_opponents_only(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [WATER.value])
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [WATER.value])
        me = self.mine(t, KYUREM, WATER, 3)
        mine_bench = t.put(self.filler, P1, 'bench')
        await t.attack(me, 'Glaciate')
        self.assertEqual(self.dealt(t), 60)                    # Weakness applies to the Active
        self.assertEqual(t.damage(bench), 30)                  # not to the Bench
        self.assertEqual(t.damage(mine_bench), 0)
        self.assertEqual(t.damage(me), 0)

    # --- Combusken DRI 41: Double Kick -------------------------------------
    async def test_combusken_double_kick(self):
        for pattern, expected in (([True, True], 80), ([True, False], 40), ([False, False], 0)):
            t = self.table()
            me = self.mine(t, COMBUSKEN, FIRE, 2)
            flips = iter(pattern)
            t.heads = lambda title: next(flips)
            await t.attack(me, 'Double Kick')
            with self.subTest(pattern=pattern):
                self.assertEqual(self.dealt(t), expected)

    # --- Bicycle PLS 117 ----------------------------------------------------
    async def test_bicycle_draws_until_four(self):
        for others, expected_draw in ((0, 4), (2, 2), (5, 0)):
            t = self.table()
            t.put(self.filler, P1, 'active')
            for _ in range(others):
                t.put(self.item, P1, 'hand')
            bike = t.put(BICYCLE, P1, 'hand')
            deck_before = len(t.zone(P1, 'deck'))
            if expected_draw == 0 and not t.can(bike, 'UseTrainerCard'):
                continue                                       # not playable with 5 in hand: fine
            await t.play(bike)
            with self.subTest(others=others):
                self.assertIn(bike, t.zone(P1, 'discard'))
                self.assertEqual(deck_before - len(t.zone(P1, 'deck')), expected_draw)
                self.assertEqual(len(t.zone(P1, 'hand')), max(4, others))

    async def test_bicycle_not_playable_with_empty_deck(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        deck = t.board.find_player_area(P1, 'deck')
        for c in list(deck.children):
            deck.remove_child(c)
        bike = t.put(BICYCLE, P1, 'hand')
        self.assertFalse(t.can(bike, 'UseTrainerCard'))


if __name__ == '__main__':
    unittest.main()
