"""Bug hunt round 7, chunk 37: Antique Armor Fossil, Startling Megaphone,
Seaking, Alolan Sandslash, Lileep, Cradily, Vulpix, Ninetales, Meltan,
Melmetal, Drilbur, Tinkatink, Tinkatuff, Tinkaton, Acerola's Premonition --
each checked against its printed text, including the cases where it should
NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, BURNED, ASLEEP, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes, SpecialConditions
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT, GRASS, PSY, METAL = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.GRASS,
    PokemonTypes.PSYCHIC, PokemonTypes.METAL)

ARMOR = 'ME5.AntiqueArmorFossil_72'
MEGAPHONE = 'XY2.StartlingMegaphone_97'
SEAKING = 'SWSH1.Seaking_47'
SANDSLASH = 'SM2.AlolanSandslash_20'
LILEEP, CRADILY = 'SV07.Lileep_5', 'SV07.Cradily_6'
VULPIX, NINETALES = 'SM9.Vulpix_15', 'XY5.Ninetales_21'
MELTAN, MELMETAL = 'SV07.Meltan_103', 'SWSH8.Melmetal_189'
DRILBUR = 'SV05.Drilbur_85'
TINKATINK, TINKATUFF, TINKATON = 'SV4.Tinkatink_83', 'SV2.Tinkatuff_104', 'SV2.Tinkaton_105'
ACEROLA = 'SWSH9.AcerolasPremonition_129'
MUSCLE_BAND = 'XY1.MuscleBand_121'
JET = 'SV2.JetEnergy_190'
ARTAZON = 'SV2.Artazon_171'
HOP = 'CZ.Hop_133'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk37(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None, base=400):
        return base - (target or self.opp).get_attribute(AttrID.HP)

    def descs(self, t, pokemon, pid):
        return {e['selectableAction']['description'] for e in t.offers(pokemon, None, pid)}

    # --- Antique Armor Fossil PBL 72 -------------------------------------------
    async def armor_board(self, armor_active):
        t = Table(self)
        lead = self.mine(t, self.filler, hp=300)
        armor = t.put(ARMOR, P1, 'hand')
        await t.play(armor)
        fossil = next(p for p in t.board.pokemon_in_play(P1) if name(p) == 'Antique Armor Fossil')
        if armor_active:
            await t._run(lambda: EffectContext(t.session, P1, fossil, None).switch_active(P1, fossil))
        attacker = t.put(self.filler, P2, 'active')
        self.big(attacker)
        t.energy(attacker, WATER, 3)
        return t, lead, fossil, attacker

    async def test_armor_fossil_active_protects_itself_10(self):
        t, lead, fossil, attacker = await self.armor_board(True)
        self.assertIs(t.active(P1), fossil)
        fossil.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.next_turn()
        hp0 = t.hp(fossil)
        # Heavy Impact (80) would KO a 60 HP fossil; give it room.
        fossil.set_attribute(AttrID.HP, 200)
        await t.attack(attacker, 'Heavy Impact', pid=P2)
        self.assertEqual(200 - t.hp(fossil), 70)
        self.assertEqual(hp0, 60)

    async def test_armor_fossil_active_protects_bench_from_spread(self):
        t, lead, fossil, attacker = await self.armor_board(True)
        fossil.set_attribute(AttrID.HP, 200)
        area = t.board.find_player_area(P2, 'activePokemonArea')
        area.remove_child(attacker)
        cetitan = t.put('SVP.Cetitan_63', P2, 'active')
        self.big(cetitan)
        t.energy(cetitan, WATER, 1)
        t.next_turn()
        await t.attack(cetitan, 'Avalanche', pid=P2)
        self.assertIn(lead, t.zone(P1, 'bench'))
        self.assertLess(t.hp(fossil), 200)            # the attack did resolve
        self.assertEqual(300 - t.hp(lead), 0)       # benched: 10 - 10

    async def test_armor_fossil_benched_gives_no_reduction(self):
        t, lead, fossil, attacker = await self.armor_board(False)
        self.assertIs(t.active(P1), lead)
        t.next_turn()
        await t.attack(attacker, 'Heavy Impact', pid=P2)
        self.assertEqual(300 - t.hp(lead), 80)

    async def test_armor_fossil_cannot_be_poisoned_or_retreat(self):
        t, lead, fossil, attacker = await self.armor_board(True)
        ctx = EffectContext(t.session, P2, attacker, None)
        await t._run(lambda: ctx.apply_special_condition(fossil, SpecialConditions.POISONED))
        self.assertEqual(t.conditions(fossil), set())
        self.assertFalse(any('Retreat' in d for d in self.descs(t, fossil, P1)))

    # --- Startling Megaphone FLF 97 --------------------------------------------
    async def test_megaphone_discards_all_opponent_tools_only(self):
        t = self.table()
        me = self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench', pid=P2)
        tool_a = t.attach(MUSCLE_BAND, self.opp)
        tool_b = t.attach(MUSCLE_BAND, bench)
        mine_tool = t.attach(MUSCLE_BAND, me)
        card = t.put(MEGAPHONE, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        discard = t.zone(P2, 'discard')
        self.assertIn(tool_a, discard)
        self.assertIn(tool_b, discard)
        self.assertIn(mine_tool, me.children)
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_megaphone_not_playable_without_opponent_tools(self):
        t = self.table()
        me = self.mine(t, self.filler)
        t.attach(MUSCLE_BAND, me)       # only my own Tool
        card = t.put(MEGAPHONE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Seaking SSH 47 --------------------------------------------------------
    async def test_seaking_ripping_horn_discards_one_per_heads(self):
        t = self.table()
        me = self.mine(t, SEAKING, WATER, 1)
        energies = t.energy(self.opp, WATER, 3)
        coins = iter([True, False, True])
        t.heads = lambda title: next(coins)
        await t.attack(me, 'Ripping Horn')
        left = [c for c in self.opp.children if c in energies]
        self.assertEqual(len(left), 1)
        self.assertEqual(self.dealt(), 0)

    async def test_seaking_ripping_horn_all_tails_discards_nothing(self):
        t = self.table()
        me = self.mine(t, SEAKING, WATER, 1)
        energies = t.energy(self.opp, WATER, 2)
        t.heads = False
        await t.attack(me, 'Ripping Horn')
        self.assertEqual(len([c for c in self.opp.children if c in energies]), 2)

    async def test_seaking_ripping_horn_heads_beyond_energy_ok(self):
        t = self.table()
        me = self.mine(t, SEAKING, WATER, 1)
        energies = t.energy(self.opp, WATER, 1)
        t.heads = True
        await t.attack(me, 'Ripping Horn')
        self.assertEqual([c for c in self.opp.children if c in energies], [])

    # --- Alolan Sandslash GRI 20 -----------------------------------------------
    async def test_sandslash_slush_rush_draws_one_once(self):
        t = self.table()
        me = self.mine(t, SANDSLASH, zone='bench')
        self.mine(t, self.filler)
        self.clear_hand(t)
        await t.use(me, 'Slush Rush')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertIsNone(t.ability_offer(me, 'Slush Rush'))

    async def test_sandslash_smash_turn_switches_with_bench(self):
        t = self.table()
        me = self.mine(t, SANDSLASH, WATER, 3)
        bench = self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Smash Turn')
        self.assertEqual(self.dealt(), 50)
        self.assertIs(t.active(P1), bench)
        self.assertIn(me, t.zone(P1, 'bench'))

    async def test_sandslash_smash_turn_no_bench_still_damages(self):
        t = self.table()
        me = self.mine(t, SANDSLASH, WATER, 3)
        await t.attack(me, 'Smash Turn')
        self.assertEqual(self.dealt(), 50)
        self.assertIs(t.active(P1), me)

    # --- Lileep SCR 5 ----------------------------------------------------------
    async def test_lileep_bind_down_blocks_retreat_next_turn(self):
        t = self.table()
        me = self.mine(t, LILEEP, GRASS, 1)
        t.energy(self.opp, WATER, 4)
        self.mine(t, self.filler, zone='bench', pid=P2)
        await t.attack(me, 'Bind Down')
        self.assertEqual(self.dealt(), 50)
        t.next_turn()
        self.assertFalse(any('Retreat' in d for d in self.descs(t, self.opp, P2)))
        t.next_turn()
        t.next_turn()
        self.assertTrue(any('Retreat' in d for d in self.descs(t, self.opp, P2)))

    async def test_lileep_bind_down_does_not_lock_own_retreat(self):
        t = self.table()
        me = self.mine(t, LILEEP, GRASS, 3)
        self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Bind Down')
        t.next_turn()
        t.next_turn()
        self.assertTrue(any('Retreat' in d for d in self.descs(t, me, P1)))

    # --- Cradily SCR 6 ---------------------------------------------------------
    def pick_choice(self, label):
        async def choose(ctx, prompt, buttons, player_id=None, descriptions=None, use_panel=True):
            self.offered_buttons = list(buttons)
            return [b.lower() for b in buttons].index(label.lower())
        return patch.object(EffectContext, 'choose', choose)

    async def test_cradily_selective_slime_heads_applies_choice(self):
        t = self.table()
        me = self.mine(t, CRADILY, zone='bench')
        self.mine(t, self.filler)
        t.heads = True
        with self.pick_choice('Burned'):
            await t.use(me, 'Selective Slime')
        self.assertEqual(sorted(b.lower() for b in self.offered_buttons),
                         ['burned', 'confused', 'poisoned'])
        self.assertEqual(t.conditions(self.opp), {BURNED})
        self.assertIsNone(t.ability_offer(me, 'Selective Slime'))

    async def test_cradily_selective_slime_tails_nothing(self):
        t = self.table()
        me = self.mine(t, CRADILY)
        t.heads = False
        with self.pick_choice('Poisoned'):
            await t.use(me, 'Selective Slime')
        self.assertEqual(t.conditions(self.opp), set())

    async def test_cradily_miasma_wind_100_per_condition(self):
        t = self.table()
        me = self.mine(t, CRADILY, GRASS, 1)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED, BURNED, CONFUSED])
        await t.attack(me, 'Miasma Wind')
        self.assertEqual(self.dealt(), 300)

    async def test_cradily_miasma_wind_no_conditions_zero(self):
        t = self.table()
        me = self.mine(t, CRADILY, GRASS, 1)
        await t.attack(me, 'Miasma Wind')
        self.assertEqual(self.dealt(), 0)

    # --- Vulpix TEU 15 ---------------------------------------------------------
    async def test_vulpix_tail_whip_heads_blocks_attack(self):
        t = self.table()
        me = self.mine(t, VULPIX, FIRE, 1, hp=300)
        t.energy(self.opp, WATER, 3)
        t.heads = True
        await t.attack(me, 'Tail Whip')
        self.assertEqual(self.dealt(), 0)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, 'Heavy Impact', P2))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, 'Heavy Impact', P2))

    async def test_vulpix_tail_whip_tails_no_effect(self):
        t = self.table()
        me = self.mine(t, VULPIX, FIRE, 1, hp=300)
        t.energy(self.opp, WATER, 3)
        t.heads = False
        await t.attack(me, 'Tail Whip')
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, 'Heavy Impact', P2))

    # --- Ninetales PRC 21 ------------------------------------------------------
    async def test_ninetales_barrier_shrine_blocks_both_players(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, NINETALES, zone='bench')
        mine_st = t.put(ARTAZON, P1, 'hand')
        opp_st = t.put(ARTAZON, P2, 'hand')
        self.assertFalse(t.can(mine_st, 'DefaultStadiumPlayAbility'))
        t.next_turn()
        self.assertFalse(t.can(opp_st, 'DefaultStadiumPlayAbility', P2))

    async def test_ninetales_absent_stadium_playable(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, VULPIX, zone='bench')
        mine_st = t.put(ARTAZON, P1, 'hand')
        self.assertTrue(t.can(mine_st, 'DefaultStadiumPlayAbility'))

    async def test_ninetales_flickering_flames_sleeps(self):
        t = self.table()
        me = self.mine(t, NINETALES, FIRE, 3)
        await t.attack(me, 'Flickering Flames')
        self.assertEqual(self.dealt(), 70)
        self.assertEqual(t.conditions(self.opp), {ASLEEP})

    # --- Meltan SCR 103 --------------------------------------------------------
    async def test_meltan_knickknack_takes_a_tool_only(self):
        t = self.table()
        me = self.mine(t, MELTAN, METAL, 1)
        t.deck(P1, [self.filler, MUSCLE_BAND])
        self.clear_hand(t)
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.attack(me, 'Knickknack Carrying')
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Muscle Band'])
        self.assertTrue(offered)
        self.assertTrue(all(name(c) == 'Muscle Band' for c in offered),
                        [name(c) for c in offered])

    async def test_meltan_knickknack_no_tool_takes_nothing(self):
        t = self.table()
        me = self.mine(t, MELTAN, METAL, 1)
        t.deck(P1, [self.filler])
        self.clear_hand(t)
        await t.attack(me, 'Knickknack Carrying')
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Melmetal FST 189 ------------------------------------------------------
    async def melmetal_after_swing(self, attacker_spec):
        t = Table(self)
        me = self.mine(t, MELMETAL, METAL, 3, hp=300)
        attacker = t.put(attacker_spec, P2, 'active')
        self.big(attacker)
        t.energy(attacker, WATER, 3)
        await t.attack(me, 'Ingot Swing')
        self.assertEqual(self.dealt(attacker), 80)
        t.next_turn()
        return t, me, attacker

    async def test_melmetal_ingot_swing_blocks_attacker_with_ability(self):
        t, me, attacker = await self.melmetal_after_swing(SANDSLASH)
        await t.attack(attacker, 'Smash Turn', pid=P2)
        self.assertEqual(300 - t.hp(me), 0)

    async def test_melmetal_ingot_swing_not_vs_attacker_without_ability(self):
        t, me, attacker = await self.melmetal_after_swing(self.filler)
        await t.attack(attacker, 'Heavy Impact', pid=P2)
        self.assertEqual(300 - t.hp(me), 80)

    async def test_melmetal_ingot_swing_expires_after_opponent_turn(self):
        t, me, attacker = await self.melmetal_after_swing(SANDSLASH)
        t.next_turn()
        t.next_turn()
        await t.attack(attacker, 'Smash Turn', pid=P2)
        self.assertEqual(300 - t.hp(me), 50)

    async def test_melmetal_blasting_hammer_discards_one_energy(self):
        t = self.table()
        me = self.mine(t, MELMETAL, METAL, 4)
        await t.attack(me, 'Blasting Hammer')
        self.assertEqual(self.dealt(), 150)
        self.assertEqual(len(me.children), 3)

    # --- Drilbur TEF 85 --------------------------------------------------------
    async def test_drilbur_dig_discards_up_to_3_fighting(self):
        t = self.table()
        self.mine(t, self.filler)
        fights = t.deck(P1, [t.basic_energy(FIGHT)] * 4)
        water = t.deck(P1, [t.basic_energy(WATER)])[0]
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        drilbur = t.put(DRILBUR, P1, 'hand')
        await t.play(drilbur)
        self.assertIn(drilbur, t.zone(P1, 'bench'))
        discarded = [c for c in t.zone(P1, 'discard') if c in fights]
        self.assertEqual(len(discarded), 3)
        self.assertNotIn(water, t.zone(P1, 'discard'))
        self.assertNotIn(water, offered)

    async def test_drilbur_dig_declined_discards_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        t.deck(P1, [t.basic_energy(FIGHT)] * 3)
        t.yes = False
        t.picks = lambda cards, count, prompt, display: []
        drilbur = t.put(DRILBUR, P1, 'hand')
        await t.play(drilbur)
        self.assertIn(drilbur, t.zone(P1, 'bench'))
        self.assertEqual(t.zone(P1, 'discard'), [])

    # --- Tinkatink PAR 83 ------------------------------------------------------
    async def test_tinkatink_boundless_power_locks_next_turn_only(self):
        t = self.table()
        me = self.mine(t, TINKATINK, PSY, 1)
        await t.attack(me, 'Boundless Power')
        self.assertEqual(self.dealt(), 40)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(me, 'Boundless Power'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(me, 'Boundless Power'))

    async def test_tinkatink_lock_does_not_affect_opponent(self):
        t = self.table()
        me = self.mine(t, TINKATINK, PSY, 1, hp=300)
        t.energy(self.opp, WATER, 3)
        await t.attack(me, 'Boundless Power')
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, 'Heavy Impact', P2))

    # --- Tinkatuff PAL 104 -----------------------------------------------------
    async def test_tinkatuff_play_rough_heads_and_tails(self):
        for heads, expected in ((True, 60), (False, 30)):
            with self.subTest(heads=heads):
                t = self.table()
                me = self.mine(t, TINKATUFF, PSY, 2)
                t.heads = heads
                await t.attack(me, 'Play Rough')
                self.assertEqual(self.dealt(), expected)

    async def armor_defender(self, t):
        """Opponent's Active is an Antique Armor Fossil (takes 10 less)."""
        area = t.board.find_player_area(P2, 'activePokemonArea')
        area.remove_child(self.opp)
        fossil = t.put(ARMOR, P2, 'hand')
        t.board.move_card(fossil.entity_id, area.entity_id)
        fossil.set_attribute(AttrID.HP, 400)
        t.state.entered_play_turn[fossil.entity_id] = 0
        return fossil

    async def test_tinkatuff_pulverizing_press_ignores_defender_effects(self):
        t = self.table()
        me = self.mine(t, TINKATUFF, PSY, 3)
        fossil = await self.armor_defender(t)
        await t.attack(me, 'Pulverizing Press')
        self.assertEqual(self.dealt(fossil), 60)

    async def test_tinkatuff_play_rough_is_reduced_by_armor(self):
        # control: a normal attack IS reduced by the defender's Ability
        t = self.table()
        me = self.mine(t, TINKATUFF, PSY, 3)
        fossil = await self.armor_defender(t)
        t.heads = True
        await t.attack(me, 'Play Rough')
        self.assertEqual(self.dealt(fossil), 50)

    # --- Tinkaton PAL 105 ------------------------------------------------------
    async def test_tinkaton_gather_materials_discard_one_draw_three(self):
        t = self.table()
        me = self.mine(t, TINKATON, zone='bench')
        self.mine(t, self.filler)
        self.clear_hand(t)
        cost = t.put(self.filler, P1, 'hand')
        await t.use(me, 'Gather Materials')
        self.assertIn(cost, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertIsNone(t.ability_offer(me, 'Gather Materials'))

    async def test_tinkaton_gather_materials_needs_a_card_in_hand(self):
        t = self.table()
        me = self.mine(t, TINKATON)
        self.clear_hand(t)
        self.assertIsNone(t.ability_offer(me, 'Gather Materials'))

    async def test_tinkaton_special_hammer_with_special_energy(self):
        t = self.table()
        me = self.mine(t, TINKATON, PSY, 1)
        t.attach(JET, me)
        await t.attack(me, 'Special Hammer')
        self.assertEqual(self.dealt(), 180)

    async def test_tinkaton_special_hammer_basic_only_90(self):
        t = self.table()
        me = self.mine(t, TINKATON, PSY, 2)
        await t.attack(me, 'Special Hammer')
        self.assertEqual(self.dealt(), 90)

    # --- Acerola's Premonition BRS 129 -----------------------------------------
    async def acerola(self, opp_hand):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        for spec in opp_hand:
            t.put(spec, P2, 'hand')
        card = t.put(ACEROLA, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        return t

    async def test_acerola_counts_items_tools_supporters_stadiums(self):
        t = await self.acerola([self.item, MUSCLE_BAND, HOP, ARTAZON, self.filler])
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len(t.zone(P2, 'hand')), 5)

    async def test_acerola_no_trainers_draws_nothing(self):
        t0 = Table(self)
        t = await self.acerola([self.filler, t0.basic_energy(WATER)])
        self.assertEqual(len(t.zone(P1, 'hand')), 0)


if __name__ == '__main__':
    unittest.main()
