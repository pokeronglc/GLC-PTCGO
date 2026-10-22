"""Bug hunt round 7, chunk 34: Pokemon Center Lady, Boxed Order, Roxanne, Damage Mover,
Chinchou, Lanturn, Shining Genesect, Gardenia's Vigor, Suicune, Harlequin, Kofu, Audino,
Emolga, N's Plan, Friends in Paldea -- each checked against its printed text, including
the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, CONFUSED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, GRASS, LIGHT = (PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS,
                             PokemonTypes.LIGHTNING)

CENTER_LADY = 'ME1.PokemonCenterLady_123'
BOXED = 'SV05.BoxedOrder_143'
ROXANNE = 'SWSH10.Roxanne_150'
DMOVER = 'SL.DamageMover_58'
CHINCHOU, LANTURN = 'SM8.Chinchou_73', 'SM8.Lanturn_74'
GENESECT = 'SL.ShiningGenesect_9'
GARDENIA = 'SWSH10.GardeniasVigor_143'
SUICUNE = 'ME2.Suicune_26'
HARLEQUIN = 'RSV10PT5.Harlequin_83'
KOFU = 'SV07.Kofu_138'
AUDINO = 'ZSV10PT5.Audino_74'
EMOLGA = 'ZSV10PT5.Emolga_29'
NS_PLAN = 'ZSV10PT5.NsPlan_83'
FRIENDS = 'SV085.FriendsinPaldea_109'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk34(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
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

    def grass_card(self, t, pid=P1):
        return t.put(t.basic_energy(GRASS), pid, 'hand')

    # --- Pokemon Center Lady MEG 123 -----------------------------------------
    async def test_center_lady_heals_60_and_cures(self):
        t = self.table()
        me = self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        maxhp = t.hp(bench)
        bench.set_attribute(AttrID.HP, maxhp - 100)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED, CONFUSED])
        me.set_attribute(AttrID.HP, t.hp(me) - 30)
        card = t.put(CENTER_LADY, P1, 'hand')
        t.pokemon = lambda cands, prompt: me
        await t.play(card)
        self.assertEqual(t.damage(me), 0)
        self.assertEqual(t.conditions(me), set())
        self.assertEqual(t.damage(bench), 100)

    async def test_center_lady_heals_bench_only_60(self):
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        bench.set_attribute(AttrID.HP, t.hp(bench) - 100)
        card = t.put(CENTER_LADY, P1, 'hand')
        t.pokemon = lambda cands, prompt: bench
        await t.play(card)
        self.assertEqual(t.damage(bench), 40)

    async def test_center_lady_not_playable_with_nothing_to_heal(self):
        t = self.table()
        self.mine(t, self.filler)
        self.opp.set_attribute(AttrID.HP, 100)          # opponent's damage doesn't count
        card = t.put(CENTER_LADY, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Boxed Order TEF 143 --------------------------------------------------
    async def test_boxed_order_takes_two_items_and_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        wanted = t.deck(P1, [DMOVER, DMOVER, CHINCHOU])
        self.clear_hand(t)
        card = t.put(BOXED, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in wanted][:count]
        ended = await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(sorted(name(c) for c in hand), ['Damage Mover', 'Damage Mover'])
        self.assertTrue(ended, 'Boxed Order ends the turn')

    async def test_boxed_order_cannot_take_pokemon(self):
        t = self.table()
        self.mine(t, self.filler)
        chin = t.deck(P1, [CHINCHOU])[0]
        self.clear_hand(t)
        card = t.put(BOXED, P1, 'hand')
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return []
        t.picks = picks
        await t.play(card)
        self.assertNotIn(chin, seen)
        self.assertIn(chin, t.zone(P1, 'deck'))

    # --- Roxanne ASR 150 ------------------------------------------------------
    async def test_roxanne_playable_at_three_prizes_draws_six_and_two(self):
        t = self.table()
        self.mine(t, self.filler)
        t.set_prizes(P2, 3)
        for _ in range(3):
            t.put(self.item, P1, 'hand')
        for _ in range(5):
            t.put(self.item, P2, 'hand')
        card = t.put(ROXANNE, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)

    async def test_roxanne_not_playable_at_four_prizes(self):
        t = self.table()
        self.mine(t, self.filler)
        t.set_prizes(P2, 4)
        t.set_prizes(P1, 1)                         # my own prize count is irrelevant
        card = t.put(ROXANNE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Damage Mover SLG 58 --------------------------------------------------
    def _mover_picker(self, src, dst):
        calls = []

        def pick(cands, prompt):
            calls.append(prompt)
            return src if len(calls) == 1 else dst
        return pick

    async def test_damage_mover_moves_three_counters(self):
        t = self.table()
        me = self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        me.set_attribute(AttrID.HP, t.hp(me) - 50)
        card = t.put(DMOVER, P1, 'hand')
        t.pokemon = self._mover_picker(me, bench)
        await t.play(card)
        self.assertEqual(t.damage(me), 20)
        self.assertEqual(t.damage(bench), 30)

    # BUG: Damage Mover is offered with no damaged Pokemon / no second Pokemon (does nothing)
    async def test_damage_mover_not_playable_without_damage(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, self.filler, zone='bench')
        self.opp.set_attribute(AttrID.HP, 100)          # opponent's damage doesn't count
        card = t.put(DMOVER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # BUG: Damage Mover is offered with no damaged Pokemon / no second Pokemon (does nothing)
    async def test_damage_mover_not_playable_with_single_pokemon(self):
        t = self.table()
        me = self.mine(t, self.filler)
        me.set_attribute(AttrID.HP, t.hp(me) - 50)
        card = t.put(DMOVER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Chinchou LOT 73 ------------------------------------------------------
    async def test_chinchou_thunder_wave_heads_paralyzes(self):
        t = self.table()
        me = self.mine(t, CHINCHOU, WATER, 1)
        t.heads = True
        await t.attack(me, 'Thunder Wave')
        self.assertIn(PARALYZED, t.conditions(self.opp))
        self.assertEqual(self.dealt(), 0)

    async def test_chinchou_thunder_wave_tails_nothing(self):
        t = self.table()
        me = self.mine(t, CHINCHOU, WATER, 1)
        t.heads = False
        await t.attack(me, 'Thunder Wave')
        self.assertEqual(t.conditions(self.opp), set())

    # --- Lanturn LOT 74 -------------------------------------------------------
    async def test_lanturn_salvage_shuffles_four_items(self):
        t = self.table()
        me = self.mine(t, LANTURN, WATER, 1)
        items = [t.put(DMOVER, P1, 'discard') for _ in range(5)]
        poke = t.put(CHINCHOU, P1, 'discard')
        energy = t.put(t.basic_energy(WATER), P1, 'discard')
        deck_before = len(t.zone(P1, 'deck'))
        await t.attack(me, 'Salvage')
        discard = t.zone(P1, 'discard')
        self.assertEqual(sum(1 for c in items if c in discard), 1)
        self.assertIn(poke, discard)
        self.assertIn(energy, discard)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before + 4)

    async def test_lanturn_salvage_ignores_non_items(self):
        t = self.table()
        me = self.mine(t, LANTURN, WATER, 1)
        sup = t.put(ROXANNE, P1, 'discard')
        item = t.put(DMOVER, P1, 'discard')
        await t.attack(me, 'Salvage')
        self.assertIn(sup, t.zone(P1, 'discard'))
        self.assertIn(item, t.zone(P1, 'deck'))

    async def test_lanturn_signal_beam_confuses(self):
        t = self.table()
        me = self.mine(t, LANTURN, LIGHT, 2)
        await t.attack(me, 'Signal Beam')
        self.assertEqual(self.dealt(), 50)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    # --- Shining Genesect SLG 9 -----------------------------------------------
    async def test_genesect_energy_reload_moves_grass(self):
        t = self.table()
        me = self.mine(t, GENESECT)
        bench = self.mine(t, self.filler, zone='bench')
        g = t.energy(bench, GRASS, 1)
        await t.use(me, 'Energy Reload')
        self.assertIn(g, me.children)
        self.assertIsNone(t.ability_offer(me, 'Energy Reload'), 'once per turn')

    async def test_genesect_energy_reload_works_from_bench(self):
        t = self.table()
        act = self.mine(t, self.filler)
        me = self.mine(t, GENESECT, zone='bench')
        g = t.energy(act, GRASS, 1)
        await t.use(me, 'Energy Reload')
        self.assertIn(g, me.children)

    async def test_genesect_energy_reload_not_for_non_grass(self):
        t = self.table()
        me = self.mine(t, GENESECT)
        bench = self.mine(t, self.filler, zone='bench')
        t.energy(bench, WATER, 2)
        t.energy(me, GRASS, 1)                         # its own Grass doesn't count
        self.assertIsNone(t.ability_offer(me, 'Energy Reload'))

    async def test_genesect_gaia_blaster_counts_grass(self):
        t = self.table()
        me = self.mine(t, GENESECT)
        t.energy(me, GRASS, 2)
        t.energy(me, WATER, 1)
        await t.attack(me, 'Gaia Blaster')
        self.assertEqual(self.dealt(), 90)

    # --- Gardenia's Vigor ASR 143 ---------------------------------------------
    async def test_gardenia_draws_two_and_attaches_two_grass_to_bench(self):
        t = self.table()
        act = self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        self.clear_hand(t)
        gs = [self.grass_card(t) for _ in range(3)]
        card = t.put(GARDENIA, P1, 'hand')
        t.pokemon = lambda cands, prompt: bench
        await t.play(card)
        self.assertEqual(sum(1 for g in gs if g in bench.children), 2)
        self.assertEqual(len(t.zone(P1, 'hand')), 1 + 2)    # 1 Grass left + 2 drawn
        self.assertEqual(act.children, [])

    async def test_gardenia_cannot_attach_to_active_or_non_grass(self):
        t = self.table()
        act = self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        self.clear_hand(t)
        water = t.put(t.basic_energy(WATER), P1, 'hand')
        self.grass_card(t)
        card = t.put(GARDENIA, P1, 'hand')
        offered = []

        def pick(cands, prompt):
            offered.extend(cands)
            return bench
        t.pokemon = pick
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return cards[:count]
        t.picks = picks
        await t.play(card)
        self.assertNotIn(act, offered)
        self.assertNotIn(water, seen)
        self.assertNotIn(water, bench.children)

    # --- Suicune PFL 26 -------------------------------------------------------
    async def test_suicune_crystal_fall_four_water_in_play(self):
        t = self.table()
        me = self.mine(t, SUICUNE, WATER, 2)
        bench = self.mine(t, self.filler, zone='bench')
        t.energy(bench, WATER, 2)
        await t.attack(me, 'Crystal Fall')
        self.assertEqual(self.dealt(), 120)

    async def test_suicune_crystal_fall_three_water_no_bonus(self):
        t = self.table()
        me = self.mine(t, SUICUNE, WATER, 2)
        bench = self.mine(t, self.filler, zone='bench')
        t.energy(bench, WATER, 1)
        t.energy(bench, FIRE, 1)
        t.energy(self.opp, WATER, 3)                 # opponent's Water doesn't count
        await t.attack(me, 'Crystal Fall')
        self.assertEqual(self.dealt(), 30)

    # --- Harlequin WHT 83 -----------------------------------------------------
    async def _harlequin(self, heads):
        t = self.table()
        self.mine(t, self.filler)
        for _ in range(2):
            t.put(self.item, P1, 'hand')
        for _ in range(7):
            t.put(self.item, P2, 'hand')
        card = t.put(HARLEQUIN, P1, 'hand')
        t.heads = heads
        await t.play(card)
        return len(t.zone(P1, 'hand')), len(t.zone(P2, 'hand'))

    async def test_harlequin_heads_five_three(self):
        self.assertEqual(await self._harlequin(True), (5, 3))

    async def test_harlequin_tails_three_five(self):
        self.assertEqual(await self._harlequin(False), (3, 5))

    # --- Kofu SCR 138 ---------------------------------------------------------
    async def test_kofu_bottoms_two_and_draws_four(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        a = t.put(CHINCHOU, P1, 'hand')
        b = t.put(EMOLGA, P1, 'hand')
        c = t.put(DMOVER, P1, 'hand')
        card = t.put(KOFU, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [x for x in cards if x in (a, b)][:count]
        await t.play(card)
        deck = t.zone(P1, 'deck')
        self.assertEqual({deck[0], deck[1]}, {a, b})
        hand = t.zone(P1, 'hand')
        self.assertIn(c, hand)
        self.assertEqual(len(hand), 1 + 4)

    async def test_kofu_not_playable_with_one_other_card(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.put(DMOVER, P1, 'hand')
        card = t.put(KOFU, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Audino BLK 74 --------------------------------------------------------
    async def test_audino_return_draws_to_six(self):
        t = self.table()
        me = self.mine(t, AUDINO, WATER, 1)
        self.clear_hand(t)
        t.put(self.item, P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.attack(me, 'Return')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(len(t.zone(P1, 'hand')), 6)

    async def test_audino_return_may_decline(self):
        t = self.table()
        me = self.mine(t, AUDINO, WATER, 1)
        self.clear_hand(t)
        t.yes = False
        await t.attack(me, 'Return')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_audino_return_full_hand_draws_nothing(self):
        t = self.table()
        me = self.mine(t, AUDINO, WATER, 1)
        self.clear_hand(t)
        for _ in range(7):
            t.put(self.item, P1, 'hand')
        await t.attack(me, 'Return')
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    # --- Emolga BLK 29 --------------------------------------------------------
    async def test_emolga_call_for_family_benches_two_basics(self):
        t = self.table()
        me = self.mine(t, EMOLGA, WATER, 1)
        basics = t.deck(P1, [CHINCHOU, AUDINO, SUICUNE])
        lant = t.deck(P1, [LANTURN])[0]
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return [c for c in cards if c in basics][:count]
        t.picks = picks
        await t.attack(me, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        self.assertTrue(all(c in basics for c in bench))
        self.assertNotIn(lant, seen)

    async def test_emolga_call_for_family_respects_bench_space(self):
        t = self.table()
        me = self.mine(t, EMOLGA, WATER, 1)
        for _ in range(4):
            self.mine(t, self.filler, zone='bench')
        t.deck(P1, [CHINCHOU, AUDINO])
        await t.attack(me, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- N's Plan BLK 83 ------------------------------------------------------
    async def test_ns_plan_moves_two_bench_energy_to_active(self):
        t = self.table()
        act = self.mine(t, self.filler)
        b1 = self.mine(t, self.filler, zone='bench')
        b2 = self.mine(t, self.filler, zone='bench')
        e1 = t.energy(b1, WATER, 1)
        e2, e3 = t.energy(b2, FIRE, 2)
        card = t.put(NS_PLAN, P1, 'hand')
        await t.play(card)
        moved = [e for e in (e1, e2, e3) if e in act.children]
        self.assertEqual(len(moved), 2)

    async def test_ns_plan_not_playable_without_bench_energy(self):
        t = self.table()
        act = self.mine(t, self.filler)
        t.energy(act, WATER, 2)                       # Active's Energy doesn't count
        self.mine(t, self.filler, zone='bench')
        card = t.put(NS_PLAN, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Friends in Paldea PRE 109 --------------------------------------------
    async def test_friends_in_paldea_draws_three(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        card = t.put(FRIENDS, P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)


if __name__ == '__main__':
    unittest.main()
