"""Bug hunt round 7, chunk 42: Luvdisc, Chien-Pao, Sordward & Shielbert, Electrike,
Manectric, Clamperl, Gorebyss, Clawitzer, Delibird, Jacq, Fresh Water Set,
Iron Bundle, Sandile, Krokorok, Krookodile -- each checked against its printed
text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

WATER, LIGHT, DARK, FIRE = (PokemonTypes.WATER, PokemonTypes.LIGHTNING,
                            PokemonTypes.DARKNESS, PokemonTypes.FIRE)

LUVDISC = 'SV2.Luvdisc_47'
CHIENPAO = 'SV4.ChienPao_57'
SORDWARD = 'SWSH5.SordwardShielbert_135'
ELECTRIKE = 'XY5.Electrike_60'
MANECTRIC = 'SWSH4.Manectric_52'
ELECTRIKE_VIV = 'SWSH4.Electrike_51'
CLAMPERL, GOREBYSS = 'SV10.Clamperl_54', 'SV10.Gorebyss_56'
CLAUNCHER, CLAWITZER = 'ME1.Clauncher_37', 'ME1.Clawitzer_38'
DELIBIRD = 'ME4.Delibird_18'
JACQ = 'SV1.Jacq_175'
FRESH = 'SWSH9.FreshWaterSet_139'
BUNDLE = 'SV4.IronBundle_56'
SANDILE, KROKOROK, KROOKODILE = ('ZSV10PT5.Sandile_57', 'ZSV10PT5.Krokorok_58',
                                 'ZSV10PT5.Krookodile_59')
BOSS = 'ME1.BosssOrders_114'
HAMMER = 'CZ.CrushingHammer_125'
SWITCH = 'SV1.Switch_194'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk42(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None, opp_hp=400):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, opp_hp)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

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

    def dealt(self, target=None):
        return 400 - (target or self.opp).get_attribute(AttrID.HP)

    async def opp_hits(self, t):
        """P2's Snorlax uses Heavy Impact (80) on P1's Active."""
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)

    # --- Luvdisc PAL 47 --------------------------------------------------------
    async def test_luvdisc_matching_finds_up_to_2_supporters(self):
        t = self.table()
        me = self.mine(t, LUVDISC, WATER, 1)
        sups = t.deck(P1, [JACQ, SORDWARD, BOSS])
        poke = t.deck(P1, [self.filler])[0]
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.attack(me, 'Matching')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(c in sups for c in hand))
        self.assertNotIn(poke, offered)
        self.assertNotIn(t.zone(P1, 'deck')[0], hand)

    async def test_luvdisc_water_pulse_sleeps(self):
        t = self.table()
        me = self.mine(t, LUVDISC, WATER, 1)
        await t.attack(me, 'Water Pulse')
        self.assertEqual(self.dealt(), 20)
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertNotIn(ASLEEP, t.conditions(me))

    # --- Chien-Pao PAR 57 ------------------------------------------------------
    async def test_chienpao_snow_bringer_attaches_2_water_to_one_pokemon(self):
        t = self.table()
        me = self.mine(t, CHIENPAO, WATER, 1)
        bench = self.mine(t, self.filler, zone='bench')
        ws = [t.put(t.basic_energy(WATER), P1, 'discard') for _ in range(3)]
        fire = t.put(t.basic_energy(FIRE), P1, 'discard')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        t.pokemon = lambda cands, prompt: bench
        await t.attack(me, 'Snow Bringer')
        attached = [c for c in bench.children if c in ws]
        self.assertEqual(len(attached), 2)
        self.assertNotIn(fire, offered)
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(self.dealt(), 0)

    async def test_chienpao_wrathful_blade_discards_2_energy(self):
        t = self.table()
        me = self.mine(t, CHIENPAO, WATER, 4)
        await t.attack(me, 'Wrathful Blade')
        self.assertEqual(self.dealt(), 130)
        self.assertEqual(len(t.board.attached_energies(me)), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    # --- Sordward & Shielbert BST 135 -----------------------------------------
    async def test_sordward_opponent_allows_card_to_hand(self):
        t = self.table()
        self.mine(t, self.filler)
        target = t.put(BOSS, P1, 'discard')
        t.yes = True
        card = t.put(SORDWARD, P1, 'hand')
        deck_before = len(t.zone(P1, 'deck'))
        await t.play(card)
        self.assertIn(target, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before)

    async def test_sordward_opponent_refuses_draw_3(self):
        t = self.table()
        self.mine(t, self.filler)
        target = t.put(BOSS, P1, 'discard')
        t.yes = False
        card = t.put(SORDWARD, P1, 'hand')
        await t.play(card)
        self.assertIn(target, t.zone(P1, 'discard'))
        self.assertEqual(len([c for c in t.zone(P1, 'hand') if c is not card]), 3)

    async def test_sordward_needs_trainer_in_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(self.filler, P1, 'discard')
        t.put(t.basic_energy(WATER), P1, 'discard')
        self.assertFalse(t.can(t.put(SORDWARD, P1, 'hand'), 'UseTrainerCard'))

    # --- Electrike PRC 60 (Omega Barrier) --------------------------------------
    async def test_electrike_omega_barrier_blocks_opponent_boss(self):
        t = self.table()
        mine_active = self.mine(t, self.filler)
        elec = self.mine(t, ELECTRIKE, zone='bench')
        other = self.mine(t, self.filler, zone='bench')
        t.next_turn()
        seen = []
        t.pokemon = lambda cands, prompt: (seen.extend(cands), elec if elec in cands else cands[0])[1]
        await t.play(t.put(BOSS, P2, 'hand'), pid=P2)
        self.assertIn(elec, t.zone(P1, 'bench'))
        self.assertNotIn(elec, seen)
        self.assertIn(other, seen)
        self.assertIs(t.active(P1), other)
        self.assertIn(mine_active, t.zone(P1, 'bench'))

    async def test_electrike_omega_barrier_blocks_crushing_hammer(self):
        t = self.table()
        elec = self.mine(t, ELECTRIKE, LIGHT, 1)
        t.next_turn()
        t.heads = True
        hammer = t.put(HAMMER, P2, 'hand')
        if t.can(hammer, 'UseTrainerCard', pid=P2):
            await t.play(hammer, pid=P2)
        self.assertEqual(len(t.board.attached_energies(elec)), 1)

    async def test_electrike_omega_barrier_not_vs_own_trainers(self):
        t = self.table()
        elec = self.mine(t, ELECTRIKE)
        bench = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(SWITCH, P1, 'hand'), targets=[bench.entity_id])
        self.assertIs(t.active(P1), bench)
        self.assertIn(elec, t.zone(P1, 'bench'))

    # --- Manectric VIV 52 ------------------------------------------------------
    async def test_manectric_high_speed_draws_3_on_evolve(self):
        t = self.table()
        self.mine(t, self.filler)
        base = self.mine(t, ELECTRIKE_VIV, zone='bench')
        t.yes = True
        evo = t.put(MANECTRIC, P1, 'hand')
        await t.play(evo, targets=[base.entity_id])
        self.assertIn(evo, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_manectric_high_speed_optional(self):
        t = self.table()
        self.mine(t, self.filler)
        base = self.mine(t, ELECTRIKE_VIV, zone='bench')
        t.yes = False
        evo = t.put(MANECTRIC, P1, 'hand')
        await t.play(evo, targets=[base.entity_id])
        self.assertIn(evo, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_manectric_high_speed_not_manual(self):
        t = self.table()
        self.mine(t, self.filler)
        m = self.mine(t, MANECTRIC, zone='bench')
        self.assertIsNone(t.ability_offer(m, 'High Speed'))

    # --- Clamperl DRI 54 -------------------------------------------------------
    async def test_clamperl_shell_press_reduces_10_next_turn(self):
        t = self.table()
        me = self.mine(t, CLAMPERL, WATER, 1, hp=200)
        await t.attack(me, 'Shell Press')
        self.assertEqual(self.dealt(), 10)
        await self.opp_hits(t)
        self.assertEqual(200 - t.hp(me), 70)

    async def test_clamperl_no_reduction_without_shell_press(self):
        t = self.table()
        me = self.mine(t, CLAMPERL, WATER, 1, hp=200)
        await self.opp_hits(t)
        self.assertEqual(200 - t.hp(me), 80)

    # --- Gorebyss DRI 56 -------------------------------------------------------
    # BUG: Crescendo Wave's "before doing damage" hand attach runs after the damage is computed
    # (and offers every one of your Pokemon as the target instead of only Gorebyss)
    async def test_gorebyss_crescendo_wave_attaches_from_hand_first(self):
        t = self.table()
        me = self.mine(t, GOREBYSS, WATER, 1)
        bench = self.mine(t, self.filler, zone='bench')
        self.clear_hand(t)
        ws = [t.put(t.basic_energy(WATER), P1, 'hand') for _ in range(2)]
        fire = t.put(t.basic_energy(FIRE), P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), list(cards))[1]
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        await t.attack(me, 'Crescendo Wave')
        self.assertNotIn(fire, offered)
        self.assertTrue(all(w in me.children for w in ws))     # "to this Pokemon"
        self.assertEqual(self.dealt(), 90)                     # 3 Water x 30

    async def test_gorebyss_crescendo_wave_attach_happens(self):
        # The optional attach itself does take place (only Gorebyss in play).
        t = self.table()
        me = self.mine(t, GOREBYSS, WATER, 1)
        self.clear_hand(t)
        ws = [t.put(t.basic_energy(WATER), P1, 'hand') for _ in range(2)]
        await t.attack(me, 'Crescendo Wave')
        self.assertTrue(all(w in me.children for w in ws))

    async def test_gorebyss_crescendo_wave_counts_only_water(self):
        t = self.table()
        me = self.mine(t, GOREBYSS, WATER, 1)
        t.energy(me, FIRE, 2)
        self.clear_hand(t)
        await t.attack(me, 'Crescendo Wave')
        self.assertEqual(self.dealt(), 30)

    # --- Clawitzer MEG 38 ------------------------------------------------------
    # BUG: "moves from the Active Spot to your Bench" is not recognised as ON_MOVE_TO_BENCH
    # (standard_trigger only matches "to the bench"), so Fall Back to Reload is a plain manual Ability
    async def test_clawitzer_fall_back_to_reload_on_retreat(self):
        t = self.table()
        claw = self.mine(t, CLAWITZER, WATER, 2)
        new = self.mine(t, self.filler, zone='bench')
        self.clear_hand(t)
        ws = [t.put(t.basic_energy(WATER), P1, 'hand') for _ in range(3)]
        t.yes = True
        retreat = next(iter(t.offers(claw, 'BaseRetreat')))
        await t.do(retreat, targets=[new.entity_id] + [e.entity_id for e in claw.children][:2])
        self.assertIn(claw, t.zone(P1, 'bench'))
        self.assertEqual(len([w for w in ws if w in claw.children]), 2)

    # BUG: "moves from the Active Spot to your Bench" is not recognised as ON_MOVE_TO_BENCH
    # (standard_trigger only matches "to the bench"), so Fall Back to Reload is a plain manual Ability
    async def test_clawitzer_fall_back_not_without_moving(self):
        t = self.table()
        self.mine(t, self.filler)
        claw = self.mine(t, CLAWITZER, zone='bench')
        self.clear_hand(t)
        t.put(t.basic_energy(WATER), P1, 'hand')
        self.assertIsNone(t.ability_offer(claw, 'Fall Back to Reload'))

    async def test_clawitzer_aqua_launcher_discards_all_energy(self):
        t = self.table()
        me = self.mine(t, CLAWITZER, WATER, 4)
        await t.attack(me, 'Aqua Launcher')
        self.assertEqual(self.dealt(), 210)
        self.assertEqual(t.board.attached_energies(me), [])

    # --- Delibird CRI 18 -------------------------------------------------------
    async def test_delibird_pleasing_present_both_players_attach(self):
        t = self.table()
        me = self.mine(t, DELIBIRD, WATER, 1)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        mine_e = [t.put(t.basic_energy(WATER), P1, 'hand') for _ in range(4)]
        opp_e = [t.put(t.basic_energy(FIRE), P2, 'hand') for _ in range(2)]
        await t.attack(me, 'Pleasing Present')
        mine_att = [e for e in mine_e if e.parent is not None and e.parent.parent is not None
                    and e in t.board.attached_energies(e.parent)]
        self.assertEqual(len([e for e in mine_e if e not in t.zone(P1, 'hand')]), 3, t.prompts)
        self.assertEqual(len([e for e in opp_e if e not in t.zone(P2, 'hand')]), 2, t.prompts)
        self.assertTrue(mine_att)
        self.assertEqual(self.dealt(), 0)

    async def test_delibird_pleasing_present_not_special_energy(self):
        t = self.table()
        me = self.mine(t, DELIBIRD, WATER, 1)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        special = t.put('SV2.TherapeuticEnergy_193', P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.attack(me, 'Pleasing Present')
        self.assertNotIn(special, offered)
        self.assertIn(special, t.zone(P1, 'hand'))

    # --- Jacq SVI 175 ----------------------------------------------------------
    async def test_jacq_finds_up_to_2_evolution_pokemon(self):
        t = self.table()
        self.mine(t, self.filler)
        evos = t.deck(P1, [GOREBYSS, KROOKODILE, CLAWITZER])
        basic = t.deck(P1, [CLAMPERL])[0]
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        card = t.put(JACQ, P1, 'hand')
        await t.play(card)
        hand = [c for c in t.zone(P1, 'hand') if c is not card]
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(c in evos for c in hand))
        self.assertNotIn(basic, offered)

    # --- Fresh Water Set BRS 139 -----------------------------------------------
    async def test_fresh_water_set_heals_20_each_own(self):
        t = self.table()
        a = self.mine(t, self.filler)
        b = self.mine(t, self.filler, zone='bench')
        full = t.hp(a)
        a.set_attribute(AttrID.HP, full - 50)
        b.set_attribute(AttrID.HP, full - 10)
        self.opp.set_attribute(AttrID.HP, 300)
        await t.play(t.put(FRESH, P1, 'hand'))
        self.assertEqual(full - t.hp(a), 30)
        self.assertEqual(t.hp(b), full)
        self.assertEqual(self.opp.get_attribute(AttrID.HP), 300)

    async def test_fresh_water_set_needs_damaged_own_pokemon(self):
        t = self.table()
        self.mine(t, self.filler)
        self.opp.set_attribute(AttrID.HP, 300)    # only opponent damaged
        self.assertFalse(t.can(t.put(FRESH, P1, 'hand'), 'UseTrainerCard'))

    # --- Iron Bundle PAR 56 ----------------------------------------------------
    async def test_iron_bundle_hyper_blower_from_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        ib = self.mine(t, BUNDLE, WATER, 1, zone='bench')
        new = t.put(self.filler, P2, 'bench')
        await t.use(ib, 'Hyper Blower')
        self.assertIs(t.active(P2), new)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIn(ib, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    async def test_iron_bundle_hyper_blower_not_from_active(self):
        t = self.table()
        ib = self.mine(t, BUNDLE)
        t.put(self.filler, P2, 'bench')
        self.assertIsNone(t.ability_offer(ib, 'Hyper Blower'))

    async def test_iron_bundle_refrigerated_stream_blocks_evolution(self):
        t = self.table(GOREBYSS)
        me = self.mine(t, BUNDLE, WATER, 3)
        await t.attack(me, 'Refrigerated Stream')
        self.assertEqual(self.dealt(), 80)
        t.energy(self.opp, WATER, 1)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, 'Crescendo Wave', pid=P2))

    async def test_iron_bundle_refrigerated_stream_basic_can_attack(self):
        t = self.table()
        me = self.mine(t, BUNDLE, WATER, 3)
        await t.attack(me, 'Refrigerated Stream')
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, 'Heavy Impact', pid=P2))

    # --- Sandile / Krokorok / Krookodile BLK 57-59 -----------------------------
    async def test_sandile_tighten_up_opponent_discards_1(self):
        t = self.table()
        me = self.mine(t, SANDILE, DARK, 1)
        self.clear_hand(t, P2)
        cards = [t.put(self.item, P2, 'hand') for _ in range(3)]
        await t.attack(me, 'Tighten Up')
        self.assertEqual(self.dealt(), 10)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)
        self.assertEqual(len([c for c in cards if c in t.zone(P2, 'discard')]), 1)

    async def test_sandile_tighten_up_empty_hand_ok(self):
        t = self.table()
        me = self.mine(t, SANDILE, DARK, 1)
        self.clear_hand(t, P2)
        await t.attack(me, 'Tighten Up')
        self.assertEqual(self.dealt(), 10)

    async def test_krokorok_tighten_up_opponent_discards_2(self):
        t = self.table()
        me = self.mine(t, KROKOROK, DARK, 2)
        self.clear_hand(t, P2)
        [t.put(self.item, P2, 'hand') for _ in range(3)]
        mine_hand = t.put(self.item, P1, 'hand')
        await t.attack(me, 'Tighten Up')
        self.assertEqual(self.dealt(), 40)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)
        self.assertIn(mine_hand, t.zone(P1, 'hand'))

    async def test_krookodile_tighten_up_one_card_hand(self):
        t = self.table()
        me = self.mine(t, KROOKODILE, DARK, 2)
        self.clear_hand(t, P2)
        c = t.put(self.item, P2, 'hand')
        await t.attack(me, 'Tighten Up')
        self.assertEqual(self.dealt(), 60)
        self.assertIn(c, t.zone(P2, 'discard'))

    async def test_krookodile_cursed_slug_3_cards_bonus(self):
        t = self.table()
        me = self.mine(t, KROOKODILE, DARK, 3)
        self.clear_hand(t, P2)
        [t.put(self.item, P2, 'hand') for _ in range(3)]
        await t.attack(me, 'Cursed Slug')
        self.assertEqual(self.dealt(), 240)

    async def test_krookodile_cursed_slug_4_cards_no_bonus(self):
        t = self.table()
        me = self.mine(t, KROOKODILE, DARK, 3)
        self.clear_hand(t, P2)
        [t.put(self.item, P2, 'hand') for _ in range(4)]
        self.clear_hand(t)          # my own hand size is irrelevant
        await t.attack(me, 'Cursed Slug')
        self.assertEqual(self.dealt(), 120)


if __name__ == '__main__':
    unittest.main()
