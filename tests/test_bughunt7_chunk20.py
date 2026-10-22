"""Bug hunt round 7, chunk 20: Rillaboom, Gravity Mountain, Chandelure, Carmine,
Cram-o-matic, Roto-Stick, Xerneas (CRI 42 / MEG 64), Togepi, Togekiss, Axew,
Beldum, Exp. Share, Energy Recycle System, Hippopotas -- each checked against
its printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
GRASS, FIGHT, METAL = PokemonTypes.GRASS, PokemonTypes.FIGHTING, PokemonTypes.METAL
FAIRY = PokemonTypes.FAIRY

RILLABOOM, THWACKEY = 'SWSH1.Rillaboom_14', 'SWSH1.Thwackey_12'
GRAVITY = 'SV08.GravityMountain_177'
CHANDELURE, LAMPENT, LITWICK = 'SM11.Chandelure_30', 'SM11.Lampent_29', 'SM11.Litwick_27'
CARMINE = 'SV06.Carmine_145'
CRAM = 'SWSH8.Cramomatic_229'
ROTO = 'SV085.RotoStick_127'
XERNEAS_CRI, XERNEAS_MEG = 'ME4.Xerneas_42', 'ME1.Xerneas_64'
TOGEPI, TOGETIC, TOGEKISS = 'SM10.Togepi_136', 'SM10.Togetic_137', 'XY6.Togekiss_46'
AXEW = 'SM11.Axew_154'
BELDUM = 'SWSH4.Beldum_116'
EXP_SHARE = 'SV1.ExpShare_174'
ERS = 'SM7.EnergyRecycleSystem_128'
HIPPO = 'SV10.Hippopotas_105'
BOSS = 'ME1.BosssOrders_114'
POTION = 'SM1.Potion_127'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk20(unittest.IsolatedAsyncioTestCase):
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

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def energies_on(self, pokemon):
        return [c for c in pokemon.children if self.is_energy(c)]

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Rillaboom SSH 14: Voltage Beat --------------------------------------
    async def test_rillaboom_voltage_beat_attaches_two_grass_to_one(self):
        t = self.table()
        rilla = self.mine(t, RILLABOOM)
        bench = self.mine(t, self.filler, zone='bench')
        t.deck(P1, [t.basic_energy(GRASS)] * 3 + [t.basic_energy(WATER)])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.use(rilla, 'Voltage Beat')
        on = self.energies_on(bench)
        self.assertEqual(len(on), 2)
        self.assertEqual(self.energies_on(rilla), [])
        self.assertTrue(all(c.archetype_id.lower() == self.energies[GRASS.value].lower()
                            for c in on))
        self.assertIsNone(t.ability_offer(rilla, 'Voltage Beat'))   # once per turn

    async def test_rillaboom_voltage_beat_ignores_non_grass(self):
        t = self.table()
        rilla = self.mine(t, RILLABOOM)
        t.deck(P1, [t.basic_energy(WATER)] * 3)
        entry = t.ability_offer(rilla, 'Voltage Beat')
        if entry is not None:
            await t.do(entry)
        self.assertEqual(self.energies_on(rilla), [])
        self.assertEqual(sum(1 for c in t.zone(P1, 'deck') if self.is_energy(c)), 3)

    # --- Gravity Mountain SSP 177 --------------------------------------------
    async def test_gravity_mountain_minus_30_stage2_both_sides_only(self):
        t = self.table()
        rilla = self.mine(t, RILLABOOM)
        thw = self.mine(t, THWACKEY, zone='bench')
        opp_s2 = t.put(CHANDELURE, P2, 'bench')
        before = (effective_max_hp(t.board, rilla), effective_max_hp(t.board, thw),
                  effective_max_hp(t.board, opp_s2), effective_max_hp(t.board, self.opp))
        t.stadium(GRAVITY, P2)
        self.assertEqual(effective_max_hp(t.board, rilla), before[0] - 30)
        self.assertEqual(effective_max_hp(t.board, opp_s2), before[2] - 30)
        self.assertEqual(effective_max_hp(t.board, thw), before[1])       # Stage 1
        self.assertEqual(effective_max_hp(t.board, self.opp), before[3])  # Basic
        self.assertEqual(before[0], 170)

    # --- Chandelure UNM 30: Spirit Burner ------------------------------------
    # BUG: Spirit Burner never puts the discarded Fire Pokemon onto the Bench (no handler)
    async def test_chandelure_spirit_burner_counts_and_benches_fire_basics(self):
        t = self.table()
        chan = self.mine(t, CHANDELURE, FIRE, 1)
        t.deck(P1, [LITWICK, self.item, self.filler, LAMPENT, LITWICK])
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        await t.attack(chan, 'Spirit Burner')
        # 4 Pokémon discarded: 10 + 4*60
        self.assertEqual(self.dealt(), 250)
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Litwick', 'Litwick'])
        disc = t.names(t.zone(P1, 'discard'))
        self.assertIn('Lampent', disc)        # Stage 1 can't be put onto the Bench
        self.assertIn(name(t.put(self.filler, P1, 'hand')), disc)   # non-Fire stays

    async def test_chandelure_spirit_burner_no_pokemon_base_damage(self):
        t = self.table()
        chan = self.mine(t, CHANDELURE, FIRE, 1)
        t.deck(P1, [self.item] * 5)
        await t.attack(chan, 'Spirit Burner')
        self.assertEqual(self.dealt(), 10)
        self.assertEqual(t.zone(P1, 'bench'), [])
        self.assertEqual(len(t.zone(P1, 'discard')), 5)

    # --- Carmine TWM 145 ------------------------------------------------------
    async def test_carmine_discards_hand_draws_five_on_first_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        old = [t.put(self.item, P1, 'hand') for _ in range(3)]
        card = t.put(CARMINE, P1, 'hand')
        t.state.turn_number = 1
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 5)
        for c in old:
            self.assertIn(c, t.zone(P1, 'discard'))
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_carmine_with_empty_hand_still_draws_five(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        card = t.put(CARMINE, P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        self.assertEqual(t.zone(P1, 'discard'), [card])

    # --- Cram-o-matic FST 229 -------------------------------------------------
    async def test_cramomatic_heads_searches_any_card(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        fodder = t.put(self.item, P1, 'hand')
        target = t.deck(P1, [BELDUM], top=False)[0]
        card = t.put(CRAM, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        t.heads = True
        t.picks = lambda cards, count, prompt, display: (
            [target] if target in cards else list(cards)[:count])
        await t.play(card)
        self.assertIn(fodder, t.zone(P1, 'discard'))
        self.assertIn(target, t.zone(P1, 'hand'))

    async def test_cramomatic_tails_only_discards(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        fodder = t.put(self.item, P1, 'hand')
        card = t.put(CRAM, P1, 'hand')
        deck_before = len(t.zone(P1, 'deck'))
        t.heads = False
        await t.play(card)
        self.assertIn(fodder, t.zone(P1, 'discard'))
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before)

    async def test_cramomatic_needs_another_item(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.put(CARMINE, P1, 'hand')                 # not an Item
        card = t.put(CRAM, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Roto-Stick PRE 127 ---------------------------------------------------
    async def test_roto_stick_takes_supporters_from_top_four_only(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        # deck order: last added is the top card
        fifth = t.deck(P1, [CARMINE])[0]
        top = t.deck(P1, [t.basic_energy(WATER), CARMINE, self.item, CARMINE])
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        card = t.put(ROTO, P1, 'hand')
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(sorted(name(c) for c in hand), ['Carmine', 'Carmine'])
        self.assertIn(top[1], hand)
        self.assertIn(top[3], hand)
        self.assertIn(fifth, t.zone(P1, 'deck'))
        self.assertIn(top[0], t.zone(P1, 'deck'))

    async def test_roto_stick_no_supporters_takes_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.deck(P1, [BELDUM, self.item, t.basic_energy(WATER), self.item])
        before = len(t.zone(P1, 'deck'))
        await t.play(t.put(ROTO, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), before)

    # --- Xerneas CRI 42: Geo Storm --------------------------------------------
    async def test_xerneas_geo_storm_counts_psychic_on_all_your_pokemon(self):
        t = self.table()
        x = self.mine(t, XERNEAS_CRI, PSY, 3)
        b1 = self.mine(t, self.filler, PSY, 2, zone='bench')
        b2 = self.mine(t, self.filler, WATER, 2, zone='bench')
        t.energy(self.opp, PSY, 3)           # opponent's Psychic doesn't count
        await t.attack(x, 'Geo Storm')
        self.assertEqual(self.dealt(), 150)

    # --- Xerneas MEG 64: Geo Gate / Bright Horns ------------------------------
    async def test_xerneas_geo_gate_benches_up_to_three_basic_psychic(self):
        t = self.table()
        x = self.mine(t, XERNEAS_MEG, PSY, 1)
        t.deck(P1, [XERNEAS_CRI, XERNEAS_MEG, XERNEAS_CRI, XERNEAS_CRI, self.filler, TOGEPI])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.attack(x, 'Geo Gate')
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Xerneas'] * 3)
        self.assertTrue(offered)
        self.assertTrue(all(name(c) == 'Xerneas' for c in offered))

    async def test_xerneas_bright_horns_locked_next_turn(self):
        t = self.table()
        x = self.mine(t, XERNEAS_MEG, PSY, 3)
        await t.attack(x, 'Bright Horns')
        self.assertEqual(self.dealt(), 120)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(x, 'Bright Horns'))
        self.assertIsNotNone(t.attack_offer(x, 'Geo Gate'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(x, 'Bright Horns'))

    # --- Togepi UNB 136: Daunt -------------------------------------------------
    async def test_togepi_daunt_reduces_defending_attack_by_30(self):
        for daunt in (True, False):
            t = self.table()
            title, dmg = self.filler_attack()
            togepi = self.mine(t, TOGEPI, WATER, 1)
            togepi.set_attribute(AttrID.HP, 300)
            if daunt:
                await t.attack(togepi, 'Daunt')
            t.energy(self.opp, WATER, 5)
            t.next_turn()
            await t.attack(self.opp, title, pid=P2)
            with self.subTest(daunt=daunt, dmg=dmg):
                self.assertEqual(300 - t.hp(togepi), max(0, dmg - 30) if daunt else dmg)

    async def test_togepi_daunt_does_not_affect_new_active(self):
        t = self.table()
        title, dmg = self.filler_attack()
        togepi = self.mine(t, TOGEPI, WATER, 1)
        togepi.set_attribute(AttrID.HP, 300)
        other = t.put(self.filler, P2, 'bench')
        other.set_attribute(AttrID.WEAKNESS_TYPES, [])
        other.set_attribute(AttrID.RESISTANCE_TYPES, [])
        await t.attack(togepi, 'Daunt')
        t.next_turn()
        await t._run(lambda: EffectContext(t.session, P2, other, None).switch_active(P2, other))
        t.energy(other, WATER, 5)
        await t.attack(other, title, pid=P2)
        self.assertEqual(300 - t.hp(togepi), dmg)

    # --- Togekiss ROS 46: Serene Grace ----------------------------------------
    async def test_togekiss_serene_grace_attaches_basic_energy_from_top_8(self):
        t = self.table()
        togetic = self.mine(t, TOGETIC)
        bench = self.mine(t, self.filler, zone='bench')
        ninth = t.deck(P1, [t.basic_energy(WATER)])[0]
        t.deck(P1, [self.item, t.basic_energy(WATER), self.item, self.item,
                    t.basic_energy(PSY), self.item, self.item, self.item])
        kiss = t.put(TOGEKISS, P1, 'hand')
        t.yes = True
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        await t.play(kiss, targets=[togetic.entity_id])
        evolved = t.active(P1)
        self.assertEqual(name(evolved), 'Togekiss')
        total = len(self.energies_on(evolved)) + len(self.energies_on(bench))
        self.assertEqual(total, 2)
        self.assertIn(ninth, t.zone(P1, 'deck'))

    async def test_togekiss_serene_grace_optional(self):
        t = self.table()
        togetic = self.mine(t, TOGETIC)
        t.deck(P1, [t.basic_energy(WATER)] * 3)
        kiss = t.put(TOGEKISS, P1, 'hand')
        t.yes = False
        await t.play(kiss, targets=[togetic.entity_id])
        self.assertEqual(self.energies_on(t.active(P1)), [])
        self.assertEqual(sum(1 for c in t.zone(P1, 'deck') if self.is_energy(c)), 3)

    # --- Axew UNM 154: Unnerve -------------------------------------------------
    # BUG: Unnerve text matches no branch of bw_era._BWTextPassive.blocks_trainer_effects (inert)
    async def test_axew_unnerve_blocks_opponent_boss_orders(self):
        t = self.table()
        self.mine(t, self.filler)
        axew = self.mine(t, AXEW, zone='bench')
        other = self.mine(t, self.filler, zone='bench')
        t.next_turn()
        boss = t.put(BOSS, P2, 'hand')
        seen = []
        t.pokemon = lambda c, p: (seen.extend(c), c[0])[1]
        targets = t.targets(boss, 'UseTrainerCard', pid=P2)
        await t.play(boss, pid=P2, targets=[other.entity_id])
        self.assertNotIn(axew.entity_id, targets)
        self.assertNotIn(axew, seen)
        self.assertIn(axew, t.zone(P1, 'bench'))

    async def test_axew_unnerve_does_not_block_own_items(self):
        t = self.table()
        axew = self.mine(t, AXEW)
        axew.set_attribute(AttrID.HP, 30)
        potion = t.put(POTION, P1, 'hand')
        await t.play(potion, targets=[axew.entity_id])
        self.assertEqual(t.hp(axew), 60)

    # --- Beldum VIV 116: Call for Family ---------------------------------------
    async def test_beldum_call_for_family_benches_up_to_two_basics(self):
        t = self.table()
        b = self.mine(t, BELDUM, METAL, 1)
        t.deck(P1, [TOGETIC, BELDUM, AXEW, TOGEPI])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.attack(b, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 2)
        self.assertNotIn('Togetic', [name(c) for c in offered])
        self.assertNotIn('Togetic', t.names(t.zone(P1, 'bench')))

    async def test_beldum_call_for_family_respects_bench_space(self):
        t = self.table()
        b = self.mine(t, BELDUM, METAL, 1)
        for _ in range(4):
            self.mine(t, self.filler, zone='bench')
        t.deck(P1, [BELDUM, AXEW, TOGEPI])
        await t.attack(b, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Exp. Share SVI 174 ----------------------------------------------------
    async def test_exp_share_moves_energy_on_attack_ko(self):
        t = self.table()
        title, dmg = self.filler_attack()
        victim = self.mine(t, self.filler, WATER, 2)
        victim.set_attribute(AttrID.HP, 10)
        holder = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(EXP_SHARE, P1, 'hand'), targets=[holder.entity_id])
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        t.yes = True
        await t.attack(self.opp, title, pid=P2)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual(len(self.energies_on(holder)), 1)

    async def test_exp_share_not_on_benched_ko(self):
        """A Benched Pokemon Knocked Out by attack damage is not 'your Active'."""
        t = self.table()
        self.mine(t, self.filler).set_attribute(AttrID.HP, 300)
        victim = self.mine(t, self.filler, WATER, 2, zone='bench')
        holder = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(EXP_SHARE, P1, 'hand'), targets=[holder.entity_id])
        victim.set_attribute(AttrID.HP, 0)
        ctx = EffectContext(t.session, P2, self.opp, None)
        t.yes = True
        await t.knockouts(ctx)
        self.assertEqual(self.energies_on(holder), [])

    # --- Energy Recycle System CES 128 -----------------------------------------
    async def _ers(self, t, label):
        menus = []

        async def choose(ctx, prompt, buttons, *a, **k):
            menus.append(list(buttons))
            return next(i for i, b in enumerate(buttons) if label in b.lower())
        card = t.put(ERS, P1, 'hand')
        with patch.object(EffectContext, 'choose', choose):
            await t.play(card)
        return menus

    async def test_ers_put_one_basic_energy_into_hand(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        for _ in range(3):
            t.put(t.basic_energy(WATER), P1, 'discard')
        await self._ers(t, 'hand')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertTrue(self.is_energy(hand[0]))

    async def test_ers_shuffle_three_into_deck(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        for _ in range(4):
            t.put(t.basic_energy(WATER), P1, 'discard')
        before = len(t.zone(P1, 'deck'))
        await self._ers(t, 'shuffle')
        self.assertEqual(len(t.zone(P1, 'deck')), before + 3)
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_energy(c)), 1)
        self.assertEqual(t.zone(P1, 'hand'), [])

    async def test_ers_not_playable_without_basic_energy_in_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(self.item, P1, 'discard')
        card = t.put(ERS, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_ers_hand_option_with_two_energy(self):
        """With only 2 basic Energy in the discard the 'hand' option still works.
        ('Shuffle 3' with fewer than 3 shuffles what's there: EnergyRecycleRuling.)"""
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        for _ in range(2):
            t.put(t.basic_energy(WATER), P1, 'discard')
        await self._ers(t, 'hand')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_energy(c)), 1)

    # --- Hippopotas DRI 105: Push Down ------------------------------------------
    async def test_hippopotas_push_down_opponent_chooses_new_active(self):
        t = self.table()
        h = self.mine(t, HIPPO, FIGHT, 1)
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(TOGEPI, P2, 'bench')
        old = self.opp
        asked = []
        t.pokemon = lambda c, p: (asked.append(set(c)), b2)[1]
        await t.attack(h, 'Push Down')
        self.assertEqual(self.dealt(), 10)
        self.assertIs(t.active(P2), b2)
        self.assertIn(old, t.zone(P2, 'bench'))
        self.assertIn({b1, b2}, asked)

    async def test_hippopotas_push_down_no_bench(self):
        t = self.table()
        h = self.mine(t, HIPPO, FIGHT, 1)
        await t.attack(h, 'Push Down')
        self.assertEqual(self.dealt(), 10)
        self.assertIs(t.active(P2), self.opp)


if __name__ == '__main__':
    unittest.main()


class EnergyRecycleRuling(Chunk20):
    """Owner ruling: 'shuffle 3' with fewer than 3 shuffles what's there;
    with 3 or more it must be exactly 3."""

    async def test_ers_shuffle_option_with_two_shuffles_both(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        for _ in range(2):
            t.put(t.basic_energy(WATER), P1, 'discard')
        before = len(t.zone(P1, 'deck'))
        await self._ers(t, 'shuffle')
        self.assertEqual(len(t.zone(P1, 'deck')), before + 2)
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_energy(c)), 0)

    async def test_ers_shuffle_must_take_exactly_three(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        for _ in range(5):
            t.put(t.basic_energy(WATER), P1, 'discard')
        before = len(t.zone(P1, 'deck'))
        await self._ers(t, 'shuffle')
        self.assertEqual(len(t.zone(P1, 'deck')), before + 3)
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_energy(c)), 2)


for _n in [n for n in vars(Chunk20) if n.startswith('test_')]:
    setattr(EnergyRecycleRuling, _n, None)
