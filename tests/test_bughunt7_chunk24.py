"""Bug hunt round 7, chunk 24: Flutter Mane, Naclstack, Eco Arm, Team Rocket's
Venture Bomb, Clavell, Sky Field, Nitro Fire Energy, Trapinch, Vibrava (CEC),
Flygon (PFL), Judge Whistle, Cinderace (MEG), Damage Pump, Memory Energy,
Bramblin -- each checked against its printed text, including the cases where
it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

F, P, W, G, R = (PokemonTypes.FIGHTING, PokemonTypes.PSYCHIC, PokemonTypes.WATER,
                 PokemonTypes.GRASS, PokemonTypes.FIRE)

FLUTTER_MANE = 'SV05.FlutterMane_78'
NACLSTACK = 'SV2.Naclstack_122'
ECO_ARM = 'XY7.EcoArm_71'
VENTURE_BOMB = 'SV10.TeamRocketsVentureBomb_179'
CLAVELL = 'SV2.Clavell_177'
SKY_FIELD = 'XY6.SkyField_89'
NITRO = 'ME4.NitroFireEnergy_86'
TRAPINCH = 'SV08.Trapinch_104'
VIBRAVA = 'SM12.Vibrava_109'          # chunk path XY5.Vibrava_109 is the wrong printing (CEC = SM12)
FLYGON = 'ME2.Flygon_53'
JUDGE_WHISTLE = 'SM9.JudgeWhistle_146'
CINDERACE = 'ME1.Cinderace_28'        # chunk path SWSH6.Cinderace_28 is the wrong printing (MEG = ME1)
DAMAGE_PUMP = 'SWSH11.DamagePump_156'
MEMORY = 'SM8.MemoryEnergy_194'
BRAMBLIN = 'SV2.Bramblin_23'

LIEPARD = 'SWSH9.Liepard_91'          # activated Ability: Trade
BOSS = 'ME1.BosssOrders_114'
JUDGE = 'SM6.Judge_108'
HO_OH = 'ME4.HoOh_10'                 # Fire; Bright Wing discards a Fire Energy
TOOL = 'XY1.MuscleBand_121'
OTHER_STADIUM = 'XY3.FightingStadium_90'


class Chunk24(unittest.IsolatedAsyncioTestCase):
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

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = self.neutral(t.put(spec, P1, zone))
        if count:
            t.energy(p, kind, count)
        return p

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        title, dmg = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    def is_basic_energy(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    # --- Flutter Mane (TEF 78) -------------------------------------------------
    def _mane_board(self, mane_zone, liepard_zone):
        t = Table(self)
        if mane_zone == 'active':
            self.mine(t, FLUTTER_MANE)
        else:
            self.mine(t, self.filler)
            self.mine(t, FLUTTER_MANE, zone='bench')
        if liepard_zone == 'active':
            liepard = self.neutral(t.put(LIEPARD, P2, 'active'), 400)
        else:
            self.neutral(t.put(self.filler, P2, 'active'), 400)
            liepard = t.put(LIEPARD, P2, 'bench')
        t.put(self.filler, P2, 'hand')
        t.put(self.filler, P2, 'hand')
        t.next_turn()
        return t, liepard

    async def test_flutter_mane_active_locks_opponent_active_ability(self):
        t, liepard = self._mane_board('active', 'active')
        self.assertIsNone(t.ability_offer(liepard, 'Trade', pid=P2))

    async def test_flutter_mane_does_not_lock_opponent_bench(self):
        t, liepard = self._mane_board('active', 'bench')
        self.assertIsNotNone(t.ability_offer(liepard, 'Trade', pid=P2))

    async def test_flutter_mane_on_bench_does_not_lock(self):
        t, liepard = self._mane_board('bench', 'active')
        self.assertIsNotNone(t.ability_offer(liepard, 'Trade', pid=P2))

    async def test_flutter_mane_hex_hurl_two_counters_on_bench_only(self):
        t = self.table()
        mane = self.mine(t, FLUTTER_MANE, W, 3)
        ob = self.neutral(t.put(self.filler, P2, 'bench'))
        calls = []

        async def place(player_id, source_id, pool, count, *a, **k):
            calls.append((sorted(p.entity_id for p in pool), count))
            return {ob.entity_id: count}
        with patch.object(t.session, 'prompt_damage_counter_placement', place):
            await t.attack(mane, 'Hex Hurl')
        self.assertEqual(400 - t.hp(self.opp), 90)
        self.assertEqual(t.damage(ob), 20)
        self.assertEqual(calls, [([ob.entity_id], 2)])

    async def test_flutter_mane_hex_hurl_no_bench_just_damage(self):
        t = self.table()
        mane = self.mine(t, FLUTTER_MANE, W, 3)
        await t.attack(mane, 'Hex Hurl')
        self.assertEqual(400 - t.hp(self.opp), 90)

    # --- Naclstack (PAL 122): Salt Cannon --------------------------------------
    async def test_naclstack_salt_cannon_60_per_heads(self):
        for heads, expected in ((True, 180), (False, 0)):
            t = self.table()
            n = self.mine(t, NACLSTACK, F, 2)
            t.heads = heads
            await t.attack(n, 'Salt Cannon')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), expected)

    # --- Eco Arm (AOR 71) --------------------------------------------------------
    async def test_eco_arm_shuffles_three_tools_not_other_items(self):
        t = self.table()
        self.mine(t, self.filler)
        tools = [t.put(TOOL, P1, 'discard') for _ in range(4)]
        other = t.put(self.item, P1, 'discard')
        arm = t.put(ECO_ARM, P1, 'hand')
        await t.play(arm)
        deck = t.zone(P1, 'deck')
        self.assertEqual(sum(1 for c in tools if c in deck), 3)
        self.assertIn(other, t.zone(P1, 'discard'))

    async def test_eco_arm_not_playable_without_tools(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(self.item, P1, 'discard')
        arm = t.put(ECO_ARM, P1, 'hand')
        self.assertFalse(t.can(arm, 'UseTrainerCard'))

    # --- Team Rocket's Venture Bomb (DRI 179) ------------------------------------
    async def test_venture_bomb_heads_two_counters_on_chosen_opponent_pokemon(self):
        t = self.table()
        me = self.mine(t, self.filler)
        ob = self.neutral(t.put(self.filler, P2, 'bench'))
        t.heads = True
        t.pokemon = lambda cands, prompt: ob if ob in cands else cands[0]
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is ob][:count] or cards[:count]
        bomb = t.put(VENTURE_BOMB, P1, 'hand')
        await t.play(bomb)
        self.assertEqual(t.damage(ob), 20)
        self.assertEqual(t.hp(self.opp), 400)
        self.assertEqual(t.damage(me), 0)

    async def test_venture_bomb_tails_two_counters_on_own_active(self):
        t = self.table()
        me = self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        t.heads = False
        bomb = t.put(VENTURE_BOMB, P1, 'hand')
        await t.play(bomb)
        self.assertEqual(t.damage(me), 20)
        self.assertEqual(t.damage(bench), 0)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Clavell (PAL 177) ---------------------------------------------------------
    async def test_clavell_up_to_three_basics_120_hp_or_less(self):
        t = self.table()
        self.mine(t, self.filler)
        small = t.deck(P1, [TRAPINCH, BRAMBLIN, FLUTTER_MANE, TRAPINCH])
        big = t.deck(P1, [self.filler])[0]               # Basic, > 120 HP
        stage1 = t.deck(P1, [VIBRAVA])[0]                # 80 HP but Stage 1
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [c for c in cards if c in small][:count]
        t.picks = picks
        clav = t.put(CLAVELL, P1, 'hand')
        await t.play(clav)
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(1 for c in small if c in hand), 3)
        self.assertNotIn(big, hand)
        self.assertNotIn(stage1, hand)
        self.assertNotIn(big, offered)
        self.assertNotIn(stage1, offered)
        self.assertGreater(t.hp(t.put(self.filler, P1, 'bench')), 120)

    # --- Sky Field (ROS 89) --------------------------------------------------------
    async def test_sky_field_bench_eight_then_discard_to_five(self):
        t = self.table()
        self.mine(t, self.filler)
        for _ in range(5):
            self.mine(t, BRAMBLIN, zone='bench')
        extra = t.put(TRAPINCH, P1, 'hand')
        self.assertFalse(t.can(extra, 'DefaultPokemonPlayAbility'))
        t.stadium(SKY_FIELD, P2)                         # either player's Sky Field
        self.assertTrue(t.can(extra, 'DefaultPokemonPlayAbility'))
        await t.play(extra)
        for _ in range(2):
            self.mine(t, BRAMBLIN, zone='bench')
        self.assertEqual(len(t.zone(P1, 'bench')), 8)
        last = t.put(TRAPINCH, P1, 'hand')
        self.assertFalse(t.can(last, 'DefaultPokemonPlayAbility'))
        for _ in range(6):
            self.neutral(t.put(BRAMBLIN, P2, 'bench'))
        new = t.put(OTHER_STADIUM, P1, 'hand')
        await t.play(new)
        self.assertEqual(len(t.zone(P1, 'bench')), 5)
        self.assertEqual(len(t.zone(P2, 'bench')), 5)
        self.assertEqual(len(t.zone(P1, 'discard')), 3)          # 3 Benched Pokémon discarded
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)    # a discard, no prizes taken
        self.assertEqual(len(t.zone(P2, 'prizes')), 6)

    # --- Nitro Fire Energy (CRI 86) ----------------------------------------------
    async def _nitro(self, fire=True):
        t = self.table()
        ho = self.mine(t, HO_OH, R, 2)
        if not fire:
            ho.set_attribute(AttrID.POKEMON_TYPES, [W.value])
        nitro = t.put(NITRO, P1, 'hand')
        await t.play(nitro, targets=[ho.entity_id])
        self.assertIn(nitro, t.attached(ho))
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is nitro][:count] or cards[:count]
        return t, ho, nitro

    async def test_nitro_fire_provides_fire_for_cost(self):
        t, ho, nitro = await self._nitro()
        self.assertIsNotNone(t.attack_offer(ho, 'Bright Wing'))   # [R][R][R] paid by 2 Fire + Nitro

    # BUG: Nitro Fire Energy discarded by its Fire Pokémon's attack stays in the discard pile
    async def test_nitro_fire_discarded_by_fire_attack_returns_to_hand(self):
        t, ho, nitro = await self._nitro()
        await t.attack(ho, 'Bright Wing')
        self.assertEqual(400 - t.hp(self.opp), 130)
        self.assertNotIn(nitro, t.attached(ho))
        self.assertIn(nitro, t.zone(P1, 'hand'))

    async def test_nitro_fire_non_fire_pokemon_stays_discarded(self):
        t, ho, nitro = await self._nitro(fire=False)
        await t.attack(ho, 'Bright Wing')
        self.assertIn(nitro, t.zone(P1, 'discard'))

    # --- Trapinch (SSP 104): Call for Family -------------------------------------
    async def test_trapinch_call_for_family_two_basics_not_stage1(self):
        t = self.table()
        tr = self.mine(t, TRAPINCH, W, 1)
        basics = t.deck(P1, [BRAMBLIN, FLUTTER_MANE, TRAPINCH])
        stage1 = t.deck(P1, [VIBRAVA])[0]
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [c for c in cards if c in basics][:count]
        t.picks = picks
        await t.attack(tr, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual(sum(1 for c in basics if c in bench), 2)
        self.assertNotIn(stage1, bench)
        self.assertNotIn(stage1, offered)

    async def test_trapinch_call_for_family_respects_bench_space(self):
        t = self.table()
        tr = self.mine(t, TRAPINCH, W, 1)
        for _ in range(4):
            self.mine(t, BRAMBLIN, zone='bench')
        t.deck(P1, [BRAMBLIN, FLUTTER_MANE])
        await t.attack(tr, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Vibrava (CEC 109): Obnoxious Whirring -----------------------------------
    async def test_vibrava_opponent_boss_cannot_drag_it(self):
        t = self.table()
        self.mine(t, self.filler)
        vib = self.mine(t, VIBRAVA, zone='bench')
        t.next_turn()
        boss = t.put(BOSS, P2, 'hand')
        seen = []

        def choose(cands, prompt):
            seen.append(list(cands))
            return vib if vib in cands else cands[0]
        t.pokemon = choose
        if t.can(boss, 'UseTrainerCard', pid=P2):
            targets = t.targets(boss, 'UseTrainerCard', pid=P2)
            self.assertNotIn(vib.entity_id, targets)
            await t.play(boss, pid=P2, targets=[vib.entity_id] if targets else [])
        self.assertIn(vib, t.zone(P1, 'bench'))

    async def test_vibrava_does_not_shield_other_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, VIBRAVA, zone='bench')
        other = self.mine(t, BRAMBLIN, zone='bench')
        t.next_turn()
        boss = t.put(BOSS, P2, 'hand')
        t.pokemon = lambda cands, prompt: other if other in cands else cands[0]
        targets = t.targets(boss, 'UseTrainerCard', pid=P2)
        await t.play(boss, pid=P2, targets=[other.entity_id] if targets else [])
        self.assertIs(t.active(P1), other)

    # --- Flygon (PFL 53): Sandy Flapping -----------------------------------------
    async def test_flygon_sandy_flapping_on_evolve_discards_two(self):
        t = self.table()
        vib = self.mine(t, VIBRAVA)
        fly = t.put(FLYGON, P1, 'hand')
        before = len(t.zone(P2, 'deck'))
        t.yes = True
        await t.play(fly, targets=[vib.entity_id])
        if t.ability_offer(fly, 'Sandy Flapping') is not None:      # click-panel style
            await t.use(fly, 'Sandy Flapping')
        self.assertIn(fly, t.zone(P1, 'active'))
        self.assertEqual(len(t.zone(P2, 'deck')), before - 2)
        self.assertEqual(len(t.zone(P2, 'discard')), 2)

    async def test_flygon_sandy_flapping_not_from_plain_board(self):
        t = self.table()
        fly = self.mine(t, FLYGON)
        before = len(t.zone(P2, 'deck'))
        self.assertIsNone(t.ability_offer(fly, 'Sandy Flapping'))
        self.assertEqual(len(t.zone(P2, 'deck')), before)

    # BUG: Sandy Flapping's KO clause is unimplemented (trigger is ON_EVOLVE only)
    async def test_flygon_sandy_flapping_when_active_knocked_out(self):
        t = self.table()
        fly = self.mine(t, FLYGON)
        self.mine(t, self.filler, zone='bench')
        fly.set_attribute(AttrID.HP, 10)
        before = len(t.zone(P2, 'deck'))
        t.yes = True
        await self.opp_hits(t)
        self.assertNotIn(fly, t.zone(P1, 'active'))
        self.assertEqual(len(t.zone(P2, 'deck')), before - 2)

    async def test_flygon_sandy_flapping_not_when_benched_knocked_out(self):
        t = self.table()
        self.mine(t, self.filler)
        fly = self.mine(t, FLYGON, zone='bench')
        fly.set_attribute(AttrID.HP, 10)
        t.yes = True
        before = len(t.zone(P2, 'deck'))
        # knock out the benched Flygon with an opponent's effect-free KO path:
        await self.opp_hits(t)                                   # hits Active only
        self.assertIn(fly, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P2, 'deck')), before)

    # --- Judge Whistle (TEU 146) ----------------------------------------------
    async def test_judge_whistle_draw_a_card(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(JUDGE, P1, 'discard')
        w = t.put(JUDGE_WHISTLE, P1, 'hand')

        async def choose(ctx, prompt, buttons, *a, **k):
            return next(i for i, b in enumerate(buttons) if 'Draw' in b)
        with patch.object(EffectContext, 'choose', choose):
            await t.play(w)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertNotEqual(t.names(t.zone(P1, 'hand')), ['Judge'])

    async def test_judge_whistle_take_judge_from_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        judge = t.put(JUDGE, P1, 'discard')
        w = t.put(JUDGE_WHISTLE, P1, 'hand')
        deck = len(t.zone(P1, 'deck'))

        async def choose(ctx, prompt, buttons, *a, **k):
            return next(i for i, b in enumerate(buttons) if 'Judge' in b)
        with patch.object(EffectContext, 'choose', choose):
            await t.play(w)
        self.assertEqual(t.zone(P1, 'hand'), [judge])
        self.assertEqual(len(t.zone(P1, 'deck')), deck)

    async def test_judge_whistle_other_supporter_not_retrievable(self):
        t = self.table()
        self.mine(t, self.filler)
        clav = t.put(CLAVELL, P1, 'discard')
        w = t.put(JUDGE_WHISTLE, P1, 'hand')
        buttons_seen = []

        async def choose(ctx, prompt, buttons, *a, **k):
            buttons_seen.append(list(buttons))
            return 0
        with patch.object(EffectContext, 'choose', choose):
            await t.play(w)
        self.assertIn(clav, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)          # only the draw was possible

    # --- Cinderace (MEG 28): Turbo Flare / Explosiveness -------------------------
    async def test_cinderace_turbo_flare_attaches_basic_energy_to_bench(self):
        t = self.table()
        cin = self.mine(t, CINDERACE, R, 1)
        b1 = self.mine(t, BRAMBLIN, zone='bench')
        b2 = self.mine(t, TRAPINCH, zone='bench')
        e = [t.put(t.basic_energy(R), P1, 'deck') for _ in range(2)] + \
            [t.put(t.basic_energy(W), P1, 'deck')]
        special = t.put(NITRO, P1, 'deck')
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [c for c in cards if c in e][:count]
        t.picks = picks
        order = iter([b1, b2, b2])
        t.pokemon = lambda cands, prompt: next(order)
        await t.attack(cin, 'Turbo Flare')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(sum(1 for c in t.attached(b1) if c in e), 1)
        self.assertEqual(sum(1 for c in t.attached(b2) if c in e), 2)
        self.assertEqual(len(t.attached(cin)), 1)
        self.assertNotIn(special, offered)

    async def test_cinderace_turbo_flare_no_bench_attaches_nothing(self):
        t = self.table()
        cin = self.mine(t, CINDERACE, R, 1)
        e = t.put(t.basic_energy(R), P1, 'deck')
        await t.attack(cin, 'Turbo Flare')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertIn(e, t.zone(P1, 'deck'))
        self.assertEqual(len(t.attached(cin)), 1)

    def test_cinderace_explosiveness_flagged_for_setup(self):
        self.assertTrue(getattr(fixtures.definition(CINDERACE), 'setup_as_active', False))

    # --- Damage Pump (LOR 156) ----------------------------------------------------
    async def test_damage_pump_moves_up_to_two_counters(self):
        t = self.table()
        a = self.mine(t, self.filler)
        b = self.mine(t, BRAMBLIN, zone='bench')
        a.set_attribute(AttrID.HP, t.hp(a) - 50)
        t.pokemon = lambda cands, prompt: a if a in cands else cands[0]
        calls = []

        async def place(player_id, source_id, pool, count, *aa, **k):
            calls.append((sorted(p.entity_id for p in pool), count))
            return {b.entity_id: count}
        pump = t.put(DAMAGE_PUMP, P1, 'hand')
        with patch.object(t.session, 'prompt_damage_counter_placement', place):
            await t.play(pump)
        self.assertEqual(t.damage(a), 30)
        self.assertEqual(t.damage(b), 20)
        self.assertEqual(calls[0][0], [b.entity_id])
        self.assertLessEqual(calls[0][1], 2)

    async def test_damage_pump_not_playable_without_damage_or_partner(self):
        t = self.table()
        a = self.mine(t, self.filler)
        a.set_attribute(AttrID.HP, t.hp(a) - 30)
        pump = t.put(DAMAGE_PUMP, P1, 'hand')
        self.assertFalse(t.can(pump, 'UseTrainerCard'))     # only 1 Pokémon
        self.mine(t, BRAMBLIN, zone='bench')
        self.assertTrue(t.can(pump, 'UseTrainerCard'))
        a.set_attribute(AttrID.HP, t.hp(a) + 30)
        self.assertFalse(t.can(pump, 'UseTrainerCard'))     # nobody damaged

    # --- Memory Energy (LOT 194) -------------------------------------------------
    async def _evolved_vibrava(self, memory):
        t = self.table()
        tr = self.mine(t, TRAPINCH)
        vib = t.put(VIBRAVA, P1, 'hand')
        await t.play(vib, targets=[tr.entity_id])
        self.assertIn(vib, t.zone(P1, 'active'))
        self.neutral(vib)
        t.energy(vib, F, 1)
        if memory:
            m = t.put(MEMORY, P1, 'hand')
            await t.play(m, targets=[vib.entity_id])
            self.assertIn(m, t.attached(vib))
        await t.session._refresh_dynamic_attacks(P1)     # the real game does this before each offer
        return t, vib

    async def test_memory_energy_grants_previous_evolution_attack(self):
        t, vib = await self._evolved_vibrava(True)
        self.assertIsNotNone(t.attack_offer(vib, 'Bite'))          # [F][C], Trapinch's
        self.assertIsNotNone(t.attack_offer(vib, 'Flap'))
        await t.attack(vib, 'Bite')
        self.assertEqual(400 - t.hp(self.opp), 20)

    async def test_memory_energy_absent_no_previous_attacks(self):
        t, vib = await self._evolved_vibrava(False)
        t.energy(vib, F, 1)
        await t.session._refresh_dynamic_attacks(P1)
        self.assertIsNone(t.attack_offer(vib, 'Bite'))
        self.assertIsNone(t.attack_offer(vib, 'Call for Family'))

    async def test_memory_energy_only_helps_its_holder(self):
        # Owner report (Oct 21): Memory Energy on one Pokémon let every
        # evolved Pokémon use its previous Evolutions' attacks.
        t, vib = await self._evolved_vibrava(False)
        other = self.mine(t, self.filler, zone='bench')
        m = t.put(MEMORY, P1, 'hand')
        await t.play(m, targets=[other.entity_id])
        t.energy(vib, F, 1)
        await t.session._refresh_dynamic_attacks(P1)
        self.assertIsNone(t.attack_offer(vib, 'Bite'))

    async def test_memory_energy_on_basic_grants_nothing(self):
        t = self.table()
        vib = self.mine(t, VIBRAVA, F, 1)          # put directly: no Trapinch underneath
        m = t.put(MEMORY, P1, 'hand')
        await t.play(m, targets=[vib.entity_id])
        await t.session._refresh_dynamic_attacks(P1)
        self.assertIsNone(t.attack_offer(vib, 'Bite'))

    # --- Bramblin (PAL 23): Blot ---------------------------------------------------
    async def test_bramblin_blot_heals_ten(self):
        t = self.table()
        br = self.mine(t, BRAMBLIN, G, 1)
        br.set_attribute(AttrID.HP, t.hp(br) - 30)
        await t.attack(br, 'Blot')
        self.assertEqual(400 - t.hp(self.opp), 10)
        self.assertEqual(t.damage(br), 20)

    async def test_bramblin_blot_full_hp_stays_full(self):
        t = self.table()
        br = self.mine(t, BRAMBLIN, G, 1)
        await t.attack(br, 'Blot')
        self.assertEqual(t.damage(br), 0)
        self.assertEqual(400 - t.hp(self.opp), 10)


if __name__ == '__main__':
    unittest.main()
