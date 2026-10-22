"""Bug hunt round 8, gap group A: card text that no test had exercised yet
(Teammates, Bibarel Tail Smash, Bidoof Hyper Fang, Electivire Unleash
Lightning, Chaotic Swell, Lucky Helmet, Beautifly, Luxray evolve, Froakie
Flock, Heatmor Hot Lick, Rescue Scarf, Handheld Fan) -- each checked against
its printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

L, W, G, R = (PokemonTypes.LIGHTNING, PokemonTypes.WATER, PokemonTypes.GRASS,
              PokemonTypes.FIRE)

TEAMMATES, TEAMMATES_FA = 'XY5.Teammates_141', 'XY5.Teammates_160'
BIBAREL, BIBAREL_CZ, BIBAREL_PR = 'SWSH9.Bibarel_121', 'CZ.Bibarel_185', 'Promo_SWSH.Bibarel_188'
BIDOOF, BIDOOF_189 = 'CZ.Bidoof_111', 'CZ.Bidoof_189'
ELECTIVIRE = 'SV07.Electivire_47'
SWELL, ARTAZON, PARALLEL = 'SM12.ChaoticSwell_187', 'SV2.Artazon_171', 'XY8.ParallelCity_145'
HELMET, HELMET_XY7 = 'SV06.LuckyHelmet_158', 'XY7.LuckyHelmet_77'
BEAUTIFLY = 'BW6.Beautifly_8'
SHINX, LUXIO, LUXRAY = 'SV2.Shinx_68', 'SV2.Luxio_70', 'SV2.Luxray_71'
FROAKIE, FROGADIER = 'SV06.Froakie_56', 'SV06.Frogadier_57'
HEATMOR, DURANT = 'BW5.Heatmor_19', 'BW6.Durant_83'
SCARF = 'BW6.RescueScarf_115'
FAN = 'SV06.HandheldFan_150'
SWITCH = 'BW1.Switch_104'
GUZMA, NEST = 'SM3.Guzma_115', 'SM1.NestBall_123'


def name(card):
    return def_for(card.archetype_id).display_name


class ChooserTable(Table):
    """Table that also records which player each choice was asked of."""

    def __init__(self, test):
        super().__init__(test)
        self.askers = []

    def _patches(self):
        base = super()._patches()
        table = self
        inner_cards = base[0].new
        inner_pokemon = base[1].new

        async def choose_cards(ctx, cards, count, minimum=None, prompt='', player_id=None, **k):
            table.askers.append(('cards', player_id or ctx.player_id))
            return await inner_cards(ctx, cards, count, minimum, prompt, player_id, **k)

        async def choose_pokemon(ctx, candidates, prompt='', *a, **k):
            table.askers.append(('pokemon', k.get('player_id') or ctx.player_id))
            return await inner_pokemon(ctx, candidates, prompt, *a, **k)

        return [patch.object(EffectContext, 'choose_cards', choose_cards),
                patch.object(EffectContext, 'choose_pokemon', choose_pokemon)] + base[2:]


class GapA(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, cls=Table, opp=None):
        t = cls(self)
        self.opp = self.neutral(t.put(opp or self.filler, P2, 'active'), 400)
        return t

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        return mon

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None):
        p = self.neutral(t.put(spec, P1, zone), hp)
        if count:
            t.energy(p, kind, count)
        return p

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        """Opponent's Active (filler) attacks P1's Active on P2's turn."""
        title, dmg = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    def energies_on(self, mon):
        return [c for c in mon.children if 'Energy' in (def_for(c.archetype_id).subtypes or [])
                or def_for(c.archetype_id).display_name is None]

    def is_energy(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    def stadium_cards(self, t):
        return list(t.board.find_global_area('activeStadium').children)

    # === Teammates (PRC 141) ================================================
    async def _ko_on_opponents_turn(self, t):
        victim = self.mine(t, self.filler, hp=10)
        t.put(self.filler, P1, 'bench')
        await self.opp_hits(t)
        t.next_turn()
        self.assertIn(victim, t.zone(P1, 'discard'))

    async def test_teammates_after_ko_searches_any_two_cards(self):
        t = self.table()
        guzma, nest = t.deck(P1, [GUZMA, NEST])
        await self._ko_on_opponents_turn(t)
        card = t.put(TEAMMATES, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        seen = []

        def picks(cards, count, prompt, display):
            seen.append((len(cards), count))
            return [guzma, nest]
        t.picks = picks
        deck_before = len(t.zone(P1, 'deck'))
        await t.play(card)
        self.assertEqual(seen[0][1], 2)                       # up to 2
        self.assertEqual(seen[0][0], deck_before)             # ANY card in the deck
        self.assertIn(guzma, t.zone(P1, 'hand'))
        self.assertIn(nest, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before - 2)

    async def test_teammates_may_take_zero(self):
        t = self.table()
        await self._ko_on_opponents_turn(t)
        card = t.put(TEAMMATES, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        deck_before = len(t.zone(P1, 'deck'))
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before)
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_teammates_not_when_ko_was_two_turns_ago(self):
        t = self.table()
        await self._ko_on_opponents_turn(t)
        t.next_turn()                     # P2's turn, no KO
        t.next_turn()                     # P1 again
        self.assertFalse(t.can(t.put(TEAMMATES, P1, 'hand'), 'UseTrainerCard'))

    async def test_teammates_not_when_opponents_pokemon_was_knocked_out(self):
        t = self.table()
        self.mine(t, self.filler)
        self.opp.set_attribute(AttrID.HP, 10)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W, 5)
        t.next_turn(); t.next_turn()          # P1 KOs P2's Active on P1's turn
        title, _ = self.filler_attack()
        t.energy(t.active(P1), W, 5)
        await t.attack(t.active(P1), title)
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        t.next_turn(); t.next_turn()
        self.assertFalse(t.can(t.put(TEAMMATES, P1, 'hand'), 'UseTrainerCard'))

    async def test_teammates_full_art_reprint_same_condition(self):
        t = self.table()
        self.assertFalse(t.can(t.put(TEAMMATES_FA, P1, 'hand'), 'UseTrainerCard'))
        await self._ko_on_opponents_turn(t)
        self.assertTrue(t.can(t.put(TEAMMATES_FA, P1, 'hand'), 'UseTrainerCard'))

    # === Bibarel (BRS 121): Tail Smash ======================================
    async def test_bibarel_tail_smash_heads_100_tails_nothing(self):
        for spec in (BIBAREL, BIBAREL_CZ, BIBAREL_PR):
            for heads in (True, False):
                t = self.table()
                b = self.mine(t, spec, W, 3)
                t.heads = heads
                await t.attack(b, 'Tail Smash')
                with self.subTest(spec=spec, heads=heads):
                    self.assertEqual(400 - t.hp(self.opp), 100 if heads else 0)

    async def test_bibarel_tail_smash_needs_three_energy(self):
        t = self.table()
        b = self.mine(t, BIBAREL, W, 2)
        self.assertIsNone(t.attack_offer(b, 'Tail Smash'))

    # === Bidoof (CRZ 111): Hyper Fang =======================================
    async def test_bidoof_hyper_fang_heads_30_tails_nothing(self):
        for spec in (BIDOOF, BIDOOF_189):
            for heads in (True, False):
                t = self.table()
                b = self.mine(t, spec, W, 2)
                t.heads = heads
                await t.attack(b, 'Hyper Fang')
                with self.subTest(spec=spec, heads=heads):
                    self.assertEqual(400 - t.hp(self.opp), 30 if heads else 0)

    # === Electivire (SCR 47): Unleash Lightning ==============================
    async def test_electivire_unleash_lightning_220_then_no_attacks_next_turn(self):
        t = self.table()
        ev = self.mine(t, ELECTIVIRE, L, 2)
        bench = self.mine(t, self.filler, W, 5, zone='bench')
        await t.attack(ev, 'Unleash Lightning')
        self.assertEqual(400 - t.hp(self.opp), 220)
        # Opponent's turn: their Pokémon are not affected.
        t.energy(self.opp, W, 5)
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, self.filler_attack()[0], pid=P2))
        t.next_turn()
        self.assertIsNone(t.attack_offer(ev, 'Electroslug'))
        self.assertIsNone(t.attack_offer(ev, 'Unleash Lightning'))
        # A different Pokémon moved into the Active Spot can't attack either.
        await t.play(t.put(SWITCH, P1, 'hand'), targets=[bench.entity_id])
        self.assertIs(t.active(P1), bench)
        self.assertIsNone(t.attack_offer(bench, self.filler_attack()[0]))

    async def test_electivire_lock_covers_new_pokemon_put_into_play(self):
        t = self.table()
        ev = self.mine(t, ELECTIVIRE, L, 2)
        await t.attack(ev, 'Unleash Lightning')
        t.next_turn(); t.next_turn()
        fresh = self.mine(t, self.filler, W, 5, zone='bench')
        await t.play(t.put(SWITCH, P1, 'hand'), targets=[fresh.entity_id])
        self.assertIsNone(t.attack_offer(fresh, self.filler_attack()[0]))

    async def test_electivire_lock_ends_after_that_turn(self):
        t = self.table()
        ev = self.mine(t, ELECTIVIRE, L, 2)
        await t.attack(ev, 'Unleash Lightning')
        t.next_turn(); t.next_turn(); t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(ev, 'Electroslug'))

    async def test_electivire_electroslug_has_no_lock(self):
        t = self.table()
        ev = self.mine(t, ELECTIVIRE, L, 2)
        await t.attack(ev, 'Electroslug')
        self.assertEqual(400 - t.hp(self.opp), 40)
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(ev, 'Electroslug'))

    # === Chaotic Swell (CEC 187) ============================================
    async def test_chaotic_swell_replaces_another_stadium_and_stays(self):
        t = self.table()
        self.mine(t, self.filler)
        art = t.stadium(ARTAZON, P2)
        swell = t.put(SWELL, P1, 'hand')
        await t.play(swell)
        self.assertEqual(self.stadium_cards(t), [swell])
        self.assertIn(art, t.zone(P2, 'discard'))

    async def test_chaotic_swell_cannot_be_played_onto_chaotic_swell(self):
        t = self.table()
        self.mine(t, self.filler)
        t.stadium(SWELL, P2)
        self.assertFalse(t.can(t.put(SWELL, P1, 'hand'), None))

    async def test_chaotic_swell_new_stadium_has_no_effect(self):
        # Parallel City played into Chaotic Swell: its "discard Benched Pokémon
        # until 3" never happens and both Stadiums are discarded.
        t = self.table()
        self.mine(t, self.filler)
        bench = [t.put(self.filler, P1, 'bench') for _ in range(5)]
        swell = t.stadium(SWELL, P2)
        city = t.put(PARALLEL, P1, 'hand')
        await t.play(city)
        self.assertEqual(self.stadium_cards(t), [])
        self.assertIn(swell, t.zone(P2, 'discard'))
        self.assertIn(city, t.zone(P1, 'discard'))
        self.assertEqual(t.zone(P1, 'bench'), bench)

    # === Lucky Helmet (TWM 158 / ROS 77) =====================================
    async def test_lucky_helmet_no_draw_from_own_attack_self_damage(self):
        for spec in (HELMET, HELMET_XY7):
            t = self.table()
            lux = self.mine(t, LUXRAY, L, 3)
            await t.play(t.put(spec, P1, 'hand'), targets=[lux.entity_id])
            before = len(t.zone(P1, 'hand'))
            await t.attack(lux, 'Wild Charge')
            with self.subTest(spec=spec):
                self.assertEqual(t.damage(lux), 20)
                self.assertEqual(len(t.zone(P1, 'hand')), before)

    async def test_lucky_helmet_reprint_draws_two_when_active_hit(self):
        t = self.table()
        mine = self.mine(t, self.filler)
        await t.play(t.put(HELMET_XY7, P1, 'hand'), targets=[mine.entity_id])
        before = len(t.zone(P1, 'hand'))
        await self.opp_hits(t)
        self.assertGreater(t.damage(mine), 0)
        self.assertEqual(len(t.zone(P1, 'hand')), before + 2)

    async def test_lucky_helmet_no_draw_when_attack_does_no_damage(self):
        # Opponent's Bidoof Hyper Fang tails: "this attack does nothing".
        t = self.table(opp=BIDOOF)
        mine = self.mine(t, self.filler)
        await t.play(t.put(HELMET, P1, 'hand'), targets=[mine.entity_id])
        t.energy(self.opp, W, 2)
        t.next_turn()
        t.heads = False
        before = len(t.zone(P1, 'hand'))
        await t.attack(self.opp, 'Hyper Fang', pid=P2)
        self.assertEqual(t.damage(mine), 0)
        self.assertEqual(len(t.zone(P1, 'hand')), before)

    # === Beautifly (DRX 8): Triple Energy / Drainpour =========================
    async def test_beautifly_triple_energy_three_types_any_way(self):
        t = self.table()
        bf = self.mine(t, BEAUTIFLY, G, 1)
        bench = self.mine(t, self.filler, zone='bench')
        f1, f2, w1, g1 = t.deck(P1, [t.basic_energy(R), t.basic_energy(R),
                                     t.basic_energy(W), t.basic_energy(G)])
        offered = []

        def picks(cards, count, prompt, display):
            offered.append(list(cards))
            self.assertEqual(count, 3)
            return list(cards)
        t.picks = picks
        targets = iter([bf, bench, bench])
        t.pokemon = lambda cands, prompt: next(targets)
        await t.attack(bf, 'Triple Energy')
        kinds = sorted(k.name for c in offered[0] for k in (R, W, G) if self.is_energy(c, k))
        self.assertEqual(kinds, ['FIRE', 'GRASS', 'WATER'])          # one per type
        on_bf = [c for c in bf.children if c in (f1, f2, w1, g1)]
        on_bench = [c for c in bench.children if c in (f1, f2, w1, g1)]
        self.assertEqual(len(on_bf), 1)
        self.assertEqual(len(on_bench), 2)
        self.assertEqual(sum(1 for c in on_bf + on_bench if self.is_energy(c, R)), 1)
        self.assertEqual(sum(1 for c in t.zone(P1, 'deck') if c in (f1, f2)), 1)
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_beautifly_triple_energy_cannot_take_two_of_one_type(self):
        t = self.table()
        bf = self.mine(t, BEAUTIFLY, G, 1)
        t.deck(P1, [t.basic_energy(R), t.basic_energy(R), t.basic_energy(R)])
        sizes = []
        t.picks = lambda cards, count, prompt, display: (sizes.append(len(cards)) or list(cards))
        before = len(bf.children)
        await t.attack(bf, 'Triple Energy')
        self.assertEqual(sizes, [1])
        self.assertEqual(len(bf.children), before + 1)

    async def _drainpour(self):
        t = self.table()
        bf = self.mine(t, BEAUTIFLY, G, 3)
        b1 = self.mine(t, self.filler, zone='bench')
        b2 = self.mine(t, self.filler, zone='bench')
        ob = self.neutral(t.put(self.filler, P2, 'bench'))
        for mon, dmg in ((bf, 50), (b1, 60), (b2, 20), (ob, 50)):
            mon.set_attribute(AttrID.HP, t.hp(mon) - dmg)
        await t.attack(bf, 'Drainpour')
        return t, bf, b1, b2, ob

    async def test_beautifly_drainpour_heals_40_from_each_bench(self):
        t, bf, b1, b2, ob = await self._drainpour()
        self.assertEqual(400 - t.hp(self.opp), 40)
        self.assertEqual(t.damage(b1), 20)
        self.assertEqual(t.damage(b2), 0)
        self.assertEqual(t.damage(ob), 50)          # opponent's Bench not healed

    # FIXED Oct 13 (was: Drainpour also heals the Active (attacking) Beautifly; text says Benched Pokémon only
    async def test_beautifly_drainpour_does_not_heal_active(self):
        t, bf, b1, b2, ob = await self._drainpour()
        self.assertEqual(t.damage(bf), 50)

    # === Luxray (PAL 71): evolving =========================================
    async def test_luxray_evolves_from_luxio(self):
        t = self.table()
        luxio = self.mine(t, LUXIO)
        lux = t.put(LUXRAY, P1, 'hand')
        await t.play(lux, targets=[luxio.entity_id])
        self.assertIs(t.active(P1), lux)
        self.assertIn(luxio, lux.children)

    async def test_luxray_cannot_evolve_from_shinx_or_new_luxio(self):
        t = self.table()
        shinx = self.mine(t, SHINX)
        lux = t.put(LUXRAY, P1, 'hand')
        self.assertNotIn(shinx.entity_id, t.targets(lux, None))
        luxio = self.mine(t, LUXIO, zone='bench')
        t.state.entered_play_turn[luxio.entity_id] = t.state.turn_number
        self.assertNotIn(luxio.entity_id, t.targets(lux, None))

    # === Froakie (TWM 56): Flock ============================================
    async def test_froakie_flock_benches_up_to_two_froakie_only(self):
        t = self.table()
        fr = self.mine(t, FROAKIE, W, 1)
        a, b, c = t.deck(P1, [FROAKIE, FROAKIE, FROAKIE])
        t.deck(P1, [FROGADIER, self.filler])
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.append((list(cards), count))
                                                          or list(cards)[:count])
        await t.attack(fr, 'Flock')
        self.assertEqual(offered[0][1], 2)
        self.assertEqual({name(x) for x in offered[0][0]}, {'Froakie'})
        self.assertEqual(len(offered[0][0]), 3)
        self.assertEqual([name(x) for x in t.zone(P1, 'bench')], ['Froakie', 'Froakie'])
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_froakie_flock_capped_by_bench_space_and_may_take_zero(self):
        t = self.table()
        fr = self.mine(t, FROAKIE, W, 1)
        for _ in range(4):
            t.put(self.filler, P1, 'bench')
        t.deck(P1, [FROAKIE, FROAKIE])
        counts = []
        t.picks = lambda cards, count, prompt, display: (counts.append(count) or list(cards)[:count])
        await t.attack(fr, 'Flock')
        self.assertEqual(counts, [1])
        self.assertEqual(len(t.zone(P1, 'bench')), 5)
        t2 = self.table()
        fr2 = self.mine(t2, FROAKIE, W, 1)
        t2.deck(P1, [FROAKIE])
        t2.picks = lambda cards, count, prompt, display: []
        await t2.attack(fr2, 'Flock')
        self.assertEqual(t2.zone(P1, 'bench'), [])

    # === Heatmor (DEX 19): Hot Lick ==========================================
    # FIXED Oct 13 (was: Hot Lick never adds +50 against Durant (no named-defender bonus in bw_legacy_attack)
    async def test_heatmor_hot_lick_plus_50_vs_durant(self):
        t = self.table(opp=DURANT)
        h = self.mine(t, HEATMOR, W, 1)
        await t.attack(h, 'Hot Lick')
        self.assertEqual(400 - t.hp(self.opp), 60)

    async def test_heatmor_hot_lick_10_vs_other(self):
        t = self.table()
        t.put(DURANT, P2, 'bench')            # benched Durant doesn't count
        h = self.mine(t, HEATMOR, W, 1)
        await t.attack(h, 'Hot Lick')
        self.assertEqual(400 - t.hp(self.opp), 10)

    # === Rescue Scarf (DRX 115) =============================================
    async def test_rescue_scarf_returns_whole_evolution_line(self):
        t = self.table()
        luxio = self.mine(t, LUXIO, hp=10)
        shinx_under = t.put(SHINX, P1, 'hand')
        t.board.attach_card(shinx_under.entity_id, luxio.entity_id)
        t.put(self.filler, P1, 'bench')
        e = t.energy(luxio, L)
        await t.play(t.put(SCARF, P1, 'hand'), targets=[luxio.entity_id])
        scarf = next(c for c in luxio.children if name(c) == 'Rescue Scarf')
        await self.opp_hits(t)
        hand = t.zone(P1, 'hand')
        self.assertIn(luxio, hand)
        self.assertIn(shinx_under, hand)
        self.assertIn(scarf, t.zone(P1, 'discard'))
        self.assertIn(e, t.zone(P1, 'discard'))

    async def test_rescue_scarf_not_for_own_attack_self_knockout(self):
        t = self.table()
        lux = self.mine(t, LUXRAY, L, 3, hp=20)
        t.put(self.filler, P1, 'bench')
        await t.play(t.put(SCARF, P1, 'hand'), targets=[lux.entity_id])
        await t.attack(lux, 'Wild Charge')
        self.assertNotIn(lux, t.zone(P1, 'active'))
        self.assertNotIn(lux, t.zone(P1, 'hand'))
        self.assertIn(lux, t.zone(P1, 'discard'))

    # === Handheld Fan (TWM 150) ==============================================
    async def test_handheld_fan_owner_chooses_energy_and_bench(self):
        t = self.table(cls=ChooserTable)
        holder = self.mine(t, self.filler)
        await t.play(t.put(FAN, P1, 'hand'), targets=[holder.entity_id])
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(self.filler, P2, 'bench')
        t.pokemon = lambda cands, prompt: b2 if b2 in cands else cands[0]
        t.askers.clear()
        await self.opp_hits(t)
        fan_asks = [a for a in t.askers]
        self.assertTrue(fan_asks)
        self.assertTrue(all(pid == P1 for _, pid in fan_asks), fan_asks)
        self.assertEqual(len(self.energies_on(b2)), 1)
        self.assertEqual(self.energies_on(b1), [])
        self.assertEqual(len(self.energies_on(self.opp)), 4)

    async def test_handheld_fan_no_move_from_own_attack_self_damage(self):
        t = self.table()
        lux = self.mine(t, LUXRAY, L, 3)
        mybench = t.put(self.filler, P1, 'bench')
        t.put(self.filler, P2, 'bench')
        await t.play(t.put(FAN, P1, 'hand'), targets=[lux.entity_id])
        await t.attack(lux, 'Wild Charge')
        self.assertEqual(t.damage(lux), 20)
        self.assertEqual(len(self.energies_on(lux)), 3)
        self.assertEqual(self.energies_on(mybench), [])


if __name__ == '__main__':
    unittest.main()
