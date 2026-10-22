"""Bug hunt round 7, chunk 35: Dedenne, Rescue Board, Lacey, Energy Swatter, Cottonee (WHT),
Whimsicott (TEF), Clefairy (POR), Clefable (TWM), Jacinthe, Beartic, Salvatore,
Flyinium Z: Air Slash, Cottonee (UNM), Whimsicott (UNM), Infernape (UPR) -- each checked
against its printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, GRASS, PSY, DARK = (PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS,
                                 PokemonTypes.PSYCHIC, PokemonTypes.DARKNESS)

DEDENNE = 'SV08.Dedenne_87'
RESCUE_BOARD = 'SV05.RescueBoard_159'
LACEY = 'SV07.Lacey_139'
SWATTER = 'ME3.EnergySwatter_73'
COTTONEE_WHT = 'RSV10PT5.Cottonee_4'
WHIMSI_TEF = 'SV05.Whimsicott_15'
CLEFAIRY = 'ME3.Clefairy_30'
CLEFABLE = 'SV06.Clefable_79'
JACINTHE = 'ME3.Jacinthe_75'
BEARTIC = 'ZSV10PT5.Beartic_26'
SALVATORE = 'SV05.Salvatore_160'
FLYINIUM = 'SM11.FlyiniumZAirSlash_195'
NOIBAT = 'SM11.Noibat_158'            # has Air Slash [P][D]
COTTONEE_UNM = 'SM11.Cottonee_143'
WHIMSI_UNM = 'SM11.Whimsicott_144'
INFERNAPE = 'SM5.Infernape_23'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk35(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p, hp=None):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = self.neutral(t.put(spec, pid, zone))
        if count:
            t.energy(p, kind, count)
        return p

    def hurt(self, t, p, dmg):
        p.set_attribute(AttrID.HP, effective_max_hp(t.board, p) - dmg)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Dedenne SSP 87: Electromagnetic Sonar ----------------------------------
    async def test_dedenne_sonar_takes_trainer_only(self):
        t = self.table()
        d = self.mine(t, DEDENNE, WATER, 1)
        poke = t.put(self.filler, P1, 'discard')
        item = t.put(self.item, P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'] = list(cards)
            return cards[:count]
        t.picks = picks
        await t.attack(d, 'Electromagnetic Sonar')
        self.assertEqual(seen['cards'], [item])
        self.assertIn(item, t.zone(P1, 'hand'))
        self.assertIn(poke, t.zone(P1, 'discard'))

    # --- Rescue Board TEF 159 ----------------------------------------------------
    # BUG: Rescue Board's "Colorless less" is never applied while HP > 30 (HP gate returns cost)
    async def test_rescue_board_reduces_by_one(self):
        t = self.table()
        c = self.mine(t, CLEFABLE)                      # retreat 2
        rb = t.put(RESCUE_BOARD, P1, 'hand')
        await t.play(rb, targets=[c.entity_id])
        self.assertIn(rb, t.attached(c))
        self.assertEqual(t.retreat(c), 1)
        self.hurt(t, c, 120 - 40)                       # 40 HP left: still 1
        self.assertEqual(t.retreat(c), 1)

    async def test_rescue_board_no_retreat_at_30_hp(self):
        t = self.table()
        b = self.mine(t, BEARTIC)                       # retreat 3
        rb = t.put(RESCUE_BOARD, P1, 'hand')
        await t.play(rb, targets=[b.entity_id])
        b.set_attribute(AttrID.HP, 30)
        self.assertEqual(t.retreat(b), 0)
        b.set_attribute(AttrID.HP, 31)
        self.assertGreater(t.retreat(b), 0)

    # BUG: same root cause, on a Retreat Cost 3 Pokemon (should be 2 at full HP)
    async def test_rescue_board_reduces_three_to_two(self):
        t = self.table()
        b = self.mine(t, BEARTIC)
        rb = t.put(RESCUE_BOARD, P1, 'hand')
        await t.play(rb, targets=[b.entity_id])
        self.assertEqual(t.retreat(b), 2)

    # --- Lacey SCR 139 -----------------------------------------------------------
    async def _lacey(self, opp_prizes):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.set_prizes(P2, opp_prizes)
        t.set_prizes(P1, 2)                             # my own prizes must not matter
        old = [t.put(self.filler, P1, 'hand') for _ in range(3)]
        lacey = t.put(LACEY, P1, 'hand')
        deck_before = len(t.zone(P1, 'deck'))
        await t.play(lacey)
        return t, old, deck_before

    async def test_lacey_draws_8_at_3_prizes(self):
        t, old, deck_before = await self._lacey(3)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 8)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before + 3 - 8)

    async def test_lacey_draws_4_at_4_prizes(self):
        t, old, deck_before = await self._lacey(4)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 4)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before + 3 - 4)

    # --- Energy Swatter POR 73 ---------------------------------------------------
    async def test_energy_swatter_bottoms_chosen_energy(self):
        t = self.table()
        self.mine(t, self.filler)
        e1 = t.put(t.basic_energy(WATER), P2, 'hand')
        other = t.put(self.filler, P2, 'hand')
        e2 = t.put(t.basic_energy(FIRE), P2, 'hand')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'] = list(cards)
            return [e2]
        t.picks = picks
        sw = t.put(SWATTER, P1, 'hand')
        await t.play(sw)
        self.assertNotIn(other, seen['cards'])
        hand = t.zone(P2, 'hand')
        self.assertIn(e1, hand)
        self.assertIn(other, hand)
        self.assertNotIn(e2, hand)
        deck = t.zone(P2, 'deck')
        self.assertIs(deck[0], e2, 'chosen Energy should be at the bottom (index 0) of the deck')

    async def test_energy_swatter_no_energy_moves_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        other = t.put(self.filler, P2, 'hand')
        mine_e = t.put(t.basic_energy(WATER), P1, 'hand')
        sw = t.put(SWATTER, P1, 'hand')
        deck_before = len(t.zone(P2, 'deck'))
        if t.can(sw, 'UseTrainerCard'):
            await t.play(sw)
        self.assertIn(other, t.zone(P2, 'hand'))
        self.assertIn(mine_e, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before)

    # --- Cottonee WHT 4: Absorb --------------------------------------------------
    async def test_cottonee_wht_absorb_heals_10(self):
        t = self.table()
        c = self.mine(t, COTTONEE_WHT, GRASS, 1)
        self.hurt(t, c, 30)
        await t.attack(c, 'Absorb')
        self.assertEqual(400 - t.hp(self.opp), 10)
        self.assertEqual(t.damage(c), 20)

    async def test_cottonee_wht_absorb_undamaged_stays_full(self):
        t = self.table()
        c = self.mine(t, COTTONEE_WHT, GRASS, 1)
        await t.attack(c, 'Absorb')
        self.assertEqual(t.damage(c), 0)
        self.assertEqual(t.hp(c), 60)

    # --- Whimsicott TEF 15: Wafting Heal -----------------------------------------
    async def _evolve(self, t, base, spec, yes=True):
        evo = t.put(spec, P1, 'hand')
        t.yes = yes
        await t.play(evo, targets=[base.entity_id])
        return evo

    async def test_whimsicott_tef_heals_active_grass_and_discards_energy(self):
        t = self.table()
        active = self.mine(t, COTTONEE_WHT)            # Grass Active
        self.hurt(t, active, 40)
        t.energy(active, GRASS, 2)
        bench_c = self.mine(t, COTTONEE_WHT, zone='bench')
        evo = await self._evolve(t, bench_c, WHIMSI_TEF)
        if t.ability_offer(evo, 'Wafting Heal') is not None:
            await t.use(evo, 'Wafting Heal')
        self.assertIn(evo, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(active), 0)
        self.assertEqual(len(t.board.attached_energies(active)), 0)

    # BUG: Wafting Heal discards all Energy from the Active Grass Pokemon even when it had no damage
    async def test_whimsicott_tef_undamaged_active_keeps_energy(self):
        t = self.table()
        active = self.mine(t, COTTONEE_WHT)
        t.energy(active, GRASS, 2)
        bench_c = self.mine(t, COTTONEE_WHT, zone='bench')
        evo = await self._evolve(t, bench_c, WHIMSI_TEF)
        if t.ability_offer(evo, 'Wafting Heal') is not None:
            await t.use(evo, 'Wafting Heal')
        self.assertEqual(len(t.board.attached_energies(active)), 2)

    async def test_whimsicott_tef_non_grass_active_not_healed(self):
        t = self.table()
        active = self.mine(t, self.filler)              # Colorless Active
        self.hurt(t, active, 40)
        t.energy(active, WATER, 2)
        bench_c = self.mine(t, COTTONEE_WHT, zone='bench')
        evo = await self._evolve(t, bench_c, WHIMSI_TEF)
        if t.ability_offer(evo, 'Wafting Heal') is not None:
            await t.use(evo, 'Wafting Heal')
        self.assertEqual(t.damage(active), 40)
        self.assertEqual(len(t.board.attached_energies(active)), 2)

    # --- Clefairy POR 30: Follow Me ----------------------------------------------
    async def test_clefairy_follow_me_switches_in_opponent_bench(self):
        t = self.table()
        c = self.mine(t, CLEFAIRY, PSY, 1)
        ob = self.neutral(t.put(self.filler, P2, 'bench'))
        mb = self.neutral(t.put(self.filler, P1, 'bench'))
        await t.attack(c, 'Follow Me')
        self.assertIs(t.active(P2), ob)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIs(t.active(P1), c)
        self.assertIn(mb, t.zone(P1, 'bench'))

    async def test_clefairy_follow_me_no_bench_nothing(self):
        t = self.table()
        c = self.mine(t, CLEFAIRY, PSY, 1)
        await t.attack(c, 'Follow Me')
        self.assertIs(t.active(P2), self.opp)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Clefable TWM 79: Metronome ----------------------------------------------
    async def test_clefable_metronome_copies_active_attack_only(self):
        t = self.table()
        c = self.mine(t, CLEFABLE, PSY, 2)
        ob = self.neutral(t.put(BEARTIC, P2, 'bench'))
        title, dmg = self.filler_attack()
        seen = {}

        async def prompt_attack_selection(player_id, source, candidates, prompt):
            seen['c'] = list(candidates)
            return next(i for i, (_, a) in enumerate(candidates) if a.title == title)
        with patch.object(t.session, 'prompt_attack_selection', prompt_attack_selection):
            await t.attack(c, 'Metronome')
        self.assertTrue(seen['c'])
        self.assertTrue(all(p is self.opp for p, _ in seen['c']),
                        'only the opponent Active Pokemon attacks should be offered')
        self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Jacinthe POR 75 ---------------------------------------------------------
    async def test_jacinthe_heals_150_from_psychic(self):
        t = self.table()
        fill = self.hurt(t, self.mine(t, self.filler), 50)
        c = self.mine(t, CLEFABLE, zone='bench')
        self.hurt(t, c, 110)
        j = t.put(JACINTHE, P1, 'hand')
        self.assertTrue(t.can(j, 'UseTrainerCard'))
        await t.play(j)
        self.assertEqual(t.damage(c), 0)
        self.assertEqual(t.damage(fill), 50)

    async def test_jacinthe_not_playable_without_damaged_psychic(self):
        t = self.table()
        self.hurt(t, self.mine(t, self.filler), 50)    # damaged, but Colorless
        self.mine(t, CLEFABLE, zone='bench')            # Psychic, undamaged
        j = t.put(JACINTHE, P1, 'hand')
        self.assertFalse(t.can(j, 'UseTrainerCard'))

    # --- Beartic BLK 26 ----------------------------------------------------------
    async def test_beartic_continuous_headbutt(self):
        t = self.table()
        b = self.mine(t, BEARTIC, WATER, 1)

        async def until_tails(ctx, title=''):
            return 3
        with patch.object(EffectContext, 'flip_until_tails', until_tails):
            await t.attack(b, 'Continuous Headbutt')
        self.assertEqual(400 - t.hp(self.opp), 150)

    async def test_beartic_continuous_headbutt_first_tails(self):
        t = self.table()
        b = self.mine(t, BEARTIC, WATER, 1)

        async def until_tails(ctx, title=''):
            return 0
        with patch.object(EffectContext, 'flip_until_tails', until_tails):
            await t.attack(b, 'Continuous Headbutt')
        self.assertEqual(t.hp(self.opp), 400)

    async def test_beartic_sheer_cold_locks_next_turn_only(self):
        t = self.table()
        b = self.mine(t, BEARTIC, WATER, 4)
        b.set_attribute(AttrID.HP, 400)
        title, _ = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        await t.attack(b, 'Sheer Cold')
        self.assertEqual(400 - t.hp(self.opp), 150)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, title, pid=P2))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, title, pid=P2))

    # --- Salvatore TEF 160 -------------------------------------------------------
    async def test_salvatore_evolves_fresh_pokemon_with_abilityless_card(self):
        t = self.table()
        c = self.mine(t, CLEFAIRY)
        t.state.entered_play_turn[c.entity_id] = t.state.turn_number   # put in play this turn
        clefable, = t.deck(P1, [CLEFABLE])
        s = t.put(SALVATORE, P1, 'hand')
        self.assertTrue(t.can(s, 'UseTrainerCard'))
        await t.play(s)
        self.assertIn(clefable, t.zone(P1, 'active'))

    async def test_salvatore_skips_evolution_with_ability(self):
        t = self.table()
        c = self.mine(t, COTTONEE_WHT)
        whim, = t.deck(P1, [WHIMSI_TEF])                 # has Wafting Heal
        s = t.put(SALVATORE, P1, 'hand')
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [x for x in cards if x is whim][:count]
        t.picks = picks
        if t.can(s, 'UseTrainerCard'):
            await t.play(s)
        self.assertIn(whim, t.zone(P1, 'deck'))
        self.assertIs(t.active(P1), c)

    # --- Flyinium Z: Air Slash UNM 195 -------------------------------------------
    async def _noibat_z(self, t, spec=NOIBAT):
        n = self.mine(t, spec)
        t.energy(n, PSY, 2)
        t.energy(n, DARK, 2)
        z = t.put(FLYINIUM, P1, 'hand')
        await t.play(z, targets=[n.entity_id])
        await t.session._refresh_dynamic_attacks(P1)
        return n

    async def test_flyinium_grants_gx_and_protects(self):
        t = self.table()
        n = await self._noibat_z(t)
        n.set_attribute(AttrID.HP, 200)
        self.assertIsNotNone(t.attack_offer(n, 'Speeding Skystrike-GX'))
        await t.attack(n, 'Speeding Skystrike-GX')
        self.assertEqual(400 - t.hp(self.opp), 180)
        title, _ = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        self.assertEqual(t.hp(n), 200)

    async def test_flyinium_needs_air_slash(self):
        t = self.table()
        s = await self._noibat_z(t, self.filler)
        self.assertIsNone(t.attack_offer(s, 'Speeding Skystrike-GX'))

    # --- Cottonee UNM 143: Dust Gathering ----------------------------------------
    async def test_cottonee_unm_draws_one(self):
        t = self.table()
        c = self.mine(t, COTTONEE_UNM, WATER, 1)
        self.clear_hand(t)
        top = t.zone(P1, 'deck')[-1]
        await t.attack(c, 'Dust Gathering')
        self.assertEqual(t.zone(P1, 'hand'), [top])
        self.assertEqual(t.hp(self.opp), 400)

    # --- Whimsicott UNM 144: Prowl -----------------------------------------------
    async def test_whimsicott_unm_prowl_searches_any_card(self):
        t = self.table()
        c = self.mine(t, COTTONEE_UNM)
        self.clear_hand(t)
        target, = t.deck(P1, [self.filler], top=False)

        def picks(cards, count, prompt, display):
            return [x for x in cards if x is target][:count]
        t.picks = picks
        evo = await self._evolve(t, c, WHIMSI_UNM)
        if t.ability_offer(evo, 'Prowl') is not None:
            await t.use(evo, 'Prowl')
        self.assertIn(evo, t.zone(P1, 'active'))
        self.assertIn(target, t.zone(P1, 'hand'))

    async def test_whimsicott_unm_prowl_not_from_board(self):
        t = self.table()
        w = self.mine(t, WHIMSI_UNM)
        self.assertIsNone(t.ability_offer(w, 'Prowl'))

    # --- Infernape UPR 23 --------------------------------------------------------
    async def test_infernape_flaming_fighter_six_counters(self):
        t = self.table()
        self.mine(t, INFERNAPE, zone='bench')
        self.mine(t, self.filler)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        t.heads = False
        await t.checkup()
        self.assertEqual(400 - t.hp(self.opp), 60)

    async def test_infernape_does_not_boost_own_burn(self):
        t = self.table()
        self.mine(t, INFERNAPE, zone='bench')
        me = self.neutral(self.mine(t, self.filler), 300)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        t.heads = False
        await t.checkup()
        self.assertEqual(300 - t.hp(me), 20)

    async def test_infernape_burst_punch_burns(self):
        t = self.table()
        i = self.mine(t, INFERNAPE, FIRE, 2)
        await t.attack(i, 'Burst Punch')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertIn(BURNED, t.conditions(self.opp))


if __name__ == '__main__':
    unittest.main()
