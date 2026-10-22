"""Bug hunt round 5, deck 2 (Psychic): Dreepy RCL 89, Drakloak RCL 90,
Dragapult RCL 91, Munna BCR 68, Musharna NXD 59, Ralts SIT 67,
Galarian Articuno EVS 63, Mew UNB 76, Wobbuffet GEN-RC 11 (= PHF 36),
Sonia CPA 65, Wally GEN-RC 27 (= ROS 94)."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

P, W = PokemonTypes.PSYCHIC, PokemonTypes.WATER
DREEPY, DRAKLOAK, DRAGAPULT = 'SWSH2.Dreepy_89', 'SWSH2.Drakloak_90', 'SWSH2.Dragapult_91'
MUNNA, MUSHARNA = 'BW7.Munna_68', 'BW4.Musharna_59'
RALTS = 'SWSH12.Ralts_67'
ARTICUNO = 'SWSH7.GalarianArticuno_63'
MEW = 'SM10.Mew_76'
WOBBUFFET = 'XY4.Wobbuffet_36'
SONIA = 'SWSH35.Sonia_65'
WALLY = 'XY6.Wally_94'
PIDGEOTTO = 'SM9.Pidgeotto_123'     # Colorless, Air Mail Ability
GUZMA, N = 'SM3.Guzma_115', 'BW3.N_92'


def name(card):
    return def_for(card.archetype_id).display_name


class Deck2Cards(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    @staticmethod
    def neutral(pokemon, hp=400):
        pokemon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        pokemon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        pokemon.set_attribute(AttrID.HP, hp)

    @staticmethod
    def choosing(index, seen=None):
        async def choose(ctx, prompt, buttons, *a, **k):
            if seen is not None:
                seen.append(list(buttons))
            return index(buttons) if callable(index) else index
        return patch.object(EffectContext, 'choose', choose)

    @staticmethod
    def choosing_attack(index, seen=None):
        """Memory Skip & co pick from attack rows (prompt_attack_selection)."""
        from spirit.game.session.game_session import GameSession

        async def pick(session, pid, source, candidates, prompt=''):
            titles = [attack.title for _, attack in candidates]
            if seen is not None:
                seen.append(titles)
            return index(titles) if callable(index) else index
        return patch.object(GameSession, 'prompt_attack_selection', pick)

    # --- Dreepy: Quick Attack ----------------------------------------------
    async def test_dreepy_quick_attack_heads_and_tails(self):
        for heads, dealt in ((True, 20), (False, 10)):
            with self.subTest(heads=heads):
                t = self.table()
                d = t.put(DREEPY, P1, 'active')
                t.energy(d, P)
                t.heads = heads
                await t.attack(d, 'Quick Attack')
                self.assertEqual(400 - t.hp(self.opp), dealt)

    # --- Drakloak: Summon --------------------------------------------------
    async def test_drakloak_summon_only_dreepy(self):
        t = self.table()
        dk = t.put(DRAKLOAK, P1, 'active')
        t.energy(dk, W)
        cards = t.deck(P1, [MUNNA, DREEPY, RALTS])
        seen = {}

        def picks(c, count, prompt, display):
            seen['names'] = t.names(c)
            return list(c)[:count]
        t.picks = picks
        await t.attack(dk, 'Summon')
        self.assertEqual(seen['names'], ['Dreepy'])
        self.assertEqual(t.zone(P1, 'bench'), [cards[1]])

    async def test_drakloak_summon_no_dreepy_benches_nothing(self):
        t = self.table()
        dk = t.put(DRAKLOAK, P1, 'active')
        t.energy(dk, W)
        t.deck(P1, [MUNNA, RALTS])
        await t.attack(dk, 'Summon')
        self.assertEqual(t.zone(P1, 'bench'), [])

    # --- Dragapult: Infiltrator / Phantom Force ----------------------------
    async def test_infiltrator_heads_prevents_tails_does_not(self):
        for heads in (True, False):
            with self.subTest(heads=heads):
                t = Table(self)
                drag = t.put(DRAGAPULT, P1, 'active')
                self.neutral(drag, 150)
                t.put(self.filler, P1, 'bench')
                d = t.put(DREEPY, P2, 'active')
                t.energy(d, P)
                t.next_turn()
                # heads everywhere: Quick Attack 20, prevented -> 0
                # tails everywhere: Quick Attack 10, taken -> 10
                t.heads = heads
                taken = 0 if heads else 10
                await t.attack(d, 'Quick Attack', pid=P2)
                self.assertEqual(150 - t.hp(drag), taken)

    async def test_phantom_force_counters_bench_only(self):
        t = self.table()
        drag = t.put(DRAGAPULT, P1, 'active')
        t.energy(drag, P, 2)
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(self.filler, P2, 'bench')
        seen = {}

        async def place(pid, source_id, candidates, count, **kwargs):
            seen['cands'], seen['count'] = list(candidates), count
            return {b1.entity_id: 2, b2.entity_id: 1}
        with patch.object(t.session, 'prompt_damage_counter_placement', AsyncMock(side_effect=place)):
            await t.attack(drag, 'Phantom Force')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertEqual(seen['count'], 3)
        self.assertNotIn(self.opp, seen['cands'])
        self.assertEqual((t.damage(b1), t.damage(b2)), (20, 10))

    async def test_phantom_force_no_bench_just_damage(self):
        t = self.table()
        drag = t.put(DRAGAPULT, P1, 'active')
        t.energy(drag, P, 2)
        await t.attack(drag, 'Phantom Force')
        self.assertEqual(400 - t.hp(self.opp), 120)

    # --- Munna: Long-Distance Hypnosis -------------------------------------
    async def test_hypnosis_heads_sleeps_opponent_from_bench(self):
        t = self.table()
        mine = t.put(self.filler, P1, 'active')
        munna = t.put(MUNNA, P1, 'bench')
        t.heads = True
        await t.use(munna, 'Long-Distance Hypnosis')
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertNotIn(ASLEEP, t.conditions(mine))
        self.assertIsNone(t.ability_offer(munna, 'Long-Distance Hypnosis'))

    async def test_hypnosis_tails_sleeps_your_active(self):
        t = self.table()
        mine = t.put(self.filler, P1, 'active')
        munna = t.put(MUNNA, P1, 'bench')
        t.heads = False
        await t.use(munna, 'Long-Distance Hypnosis')
        self.assertIn(ASLEEP, t.conditions(mine))
        self.assertNotIn(ASLEEP, t.conditions(self.opp))
        self.assertNotIn(ASLEEP, t.conditions(munna))

    # --- Musharna: Forewarn / Fluffy Dream ---------------------------------
    async def test_forewarn_top_two_one_to_hand_other_back_on_top(self):
        t = self.table()
        m = t.put(MUSHARNA, P1, 'bench')
        a, b = t.deck(P1, [GUZMA, N])       # N on top
        seen = {}

        def picks(cards, count, prompt, display):
            seen['c'] = (sorted(t.names(cards)), count)
            return [c for c in cards if c is a]
        t.picks = picks
        await t.use(m, 'Forewarn')
        self.assertEqual(seen['c'], (['Guzma', 'N'], 1))
        self.assertEqual(t.zone(P1, 'hand'), [a])
        self.assertIs(t.zone(P1, 'deck')[-1], b, 'the other card goes back on top')
        self.assertIsNone(t.ability_offer(m, 'Forewarn'))

    async def test_fluffy_dream_self_asleep(self):
        t = self.table()
        m = t.put(MUSHARNA, P1, 'active')
        t.energy(m, P, 2)
        await t.attack(m, 'Fluffy Dream')
        self.assertEqual(400 - t.hp(self.opp), 40)
        self.assertIn(ASLEEP, t.conditions(m))
        self.assertNotIn(ASLEEP, t.conditions(self.opp))

    # --- Ralts: Memory Skip ------------------------------------------------
    async def test_memory_skip_locks_chosen_attack_next_turn_only(self):
        t = Table(self)
        ralts = t.put(RALTS, P1, 'active')
        self.neutral(ralts)
        dk = t.put(DRAKLOAK, P2, 'active')
        self.neutral(dk)
        t.energy(dk, P, 2)
        t.energy(ralts, P)
        seen = []
        with self.choosing_attack(lambda buttons: buttons.index('Bite'), seen):
            await t.attack(ralts, 'Memory Skip')
        self.assertEqual(sorted(seen[0]), ['Bite', 'Summon'])
        t.next_turn()
        self.assertIsNone(t.attack_offer(dk, 'Bite', pid=P2))
        self.assertIsNotNone(t.attack_offer(dk, 'Summon', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(dk, 'Bite', pid=P2))

    async def test_memory_skip_lock_leaves_with_switch(self):
        """The lock is on 'that Pokémon'; a different Drakloak isn't locked."""
        t = Table(self)
        ralts = t.put(RALTS, P1, 'active')
        self.neutral(ralts)
        dk = t.put(DRAKLOAK, P2, 'active')
        self.neutral(dk)
        other = t.put(DRAKLOAK, P2, 'bench')
        t.energy(dk, P, 2)
        t.energy(other, P, 2)
        t.energy(ralts, P)
        with self.choosing_attack(lambda buttons: buttons.index('Bite')):
            await t.attack(ralts, 'Memory Skip')
        t.next_turn()
        self.assertIsNone(t.attack_offer(dk, 'Bite', pid=P2))
        # swap actives manually (as if switched)
        active = t.board.find_player_area(P2, 'activePokemonArea')
        bench = t.board.find_player_area(P2, 'bench')
        t.board.move_card(dk.entity_id, bench.entity_id)
        t.board.move_card(other.entity_id, active.entity_id)
        self.assertIsNotNone(t.attack_offer(other, 'Bite', pid=P2))

    # --- Galarian Articuno: Cruel Charge / Psylaser ------------------------
    async def test_cruel_charge_attaches_up_to_two_psychic(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        art = t.put(ARTICUNO, P1, 'hand')
        ps = [t.put(t.basic_energy(P), P1, 'hand') for _ in range(3)]
        water = t.put(t.basic_energy(W), P1, 'hand')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['c'], seen['n'] = list(cards), count
            return list(cards)[:count]
        t.picks = picks
        await t.play(art)
        self.assertIn(art, t.zone(P1, 'bench'))
        self.assertEqual(seen['n'], 2)
        self.assertNotIn(water, seen['c'])
        self.assertEqual(sum(1 for c in art.children if c in ps), 2)

    async def test_cruel_charge_may_attach_none(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        art = t.put(ARTICUNO, P1, 'hand')
        t.put(t.basic_energy(P), P1, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        await t.play(art)
        self.assertEqual(list(art.children), [])

    async def test_cruel_charge_not_on_other_bench_entry(self):
        """Only 'when you play this Pokémon from your hand onto your Bench':
        a Summon-style deck-to-bench put does not trigger."""
        t = self.table()
        dk = t.put(DRAKLOAK, P1, 'active')
        t.energy(dk, W)
        t.put(t.basic_energy(P), P1, 'hand')
        prompts_before = len(t.prompts)
        # Drakloak's Summon only takes Dreepy, so use effect helper directly
        from spirit.game.card_effects.support_common import search_to_bench
        t.deck(P1, [ARTICUNO])
        ctx = EffectContext(t.session, P1, dk, None)
        await t._run(lambda: search_to_bench(predicate=lambda c: name(c) == 'Galarian Articuno')(ctx))
        art = next(c for c in t.zone(P1, 'bench') if name(c) == 'Galarian Articuno')
        self.assertEqual(list(art.children), [])
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_psylaser_discards_only_psychic_hits_bench_no_wr(self):
        t = self.table()
        art = t.put(ARTICUNO, P1, 'active')
        ps = t.energy(art, P, 2)
        water = t.energy(art, W)
        bench = t.put(self.filler, P2, 'bench')
        self.neutral(bench)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [P.value])
        t.pokemon = lambda candidates, prompt: bench
        await t.attack(art, 'Psylaser')
        self.assertEqual(400 - t.hp(bench), 120)
        self.assertEqual(t.hp(self.opp), 400)
        self.assertEqual(list(art.children), [water])
        for e in ps:
            self.assertIn(e, t.zone(P1, 'discard'))

    async def test_psylaser_active_gets_weakness(self):
        t = self.table()
        art = t.put(ARTICUNO, P1, 'active')
        t.energy(art, P, 3)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [P.value])
        t.pokemon = lambda candidates, prompt: self.opp
        await t.attack(art, 'Psylaser')
        self.assertEqual(400 - t.hp(self.opp), 240)

    # --- Mew: Bench Barrier / Psypower --------------------------------------
    async def test_bench_barrier_prevents_attack_damage_to_bench(self):
        t = Table(self)
        mine = t.put(self.filler, P1, 'active')
        self.neutral(mine)
        mew = t.put(MEW, P1, 'bench')
        ben = t.put(self.filler, P1, 'bench')
        self.neutral(ben)
        art = t.put(ARTICUNO, P2, 'active')
        self.neutral(art)
        t.energy(art, P, 3)
        t.next_turn()
        t.pokemon = lambda candidates, prompt: ben
        await t.attack(art, 'Psylaser', pid=P2)
        self.assertEqual(t.hp(ben), 400)
        self.assertIn(mew, t.zone(P1, 'bench'))

    async def test_bench_barrier_does_not_protect_active(self):
        t = Table(self)
        mine = t.put(self.filler, P1, 'active')
        self.neutral(mine)
        t.put(MEW, P1, 'bench')
        art = t.put(ARTICUNO, P2, 'active')
        self.neutral(art)
        t.energy(art, P, 3)
        t.next_turn()
        t.pokemon = lambda candidates, prompt: mine
        await t.attack(art, 'Psylaser', pid=P2)
        self.assertEqual(400 - t.hp(mine), 120)

    async def test_bench_barrier_does_not_stop_damage_counters(self):
        t = Table(self)
        mine = t.put(self.filler, P1, 'active')
        self.neutral(mine)
        t.put(MEW, P1, 'bench')
        ben = t.put(self.filler, P1, 'bench')
        self.neutral(ben)
        drag = t.put(DRAGAPULT, P2, 'active')
        t.energy(drag, P, 2)
        t.next_turn()
        with patch.object(t.session, 'prompt_damage_counter_placement',
                          AsyncMock(return_value={ben.entity_id: 3})):
            await t.attack(drag, 'Phantom Force', pid=P2)
        self.assertEqual(400 - t.hp(ben), 30)

    async def test_psypower_three_counters_any_way(self):
        t = self.table()
        mew = t.put(MEW, P1, 'active')
        t.energy(mew, W)
        b = t.put(self.filler, P2, 'bench')
        self.neutral(b)
        seen = {}

        async def place(pid, source_id, candidates, count, **kwargs):
            seen['cands'], seen['count'] = set(candidates), count
            return {self.opp.entity_id: 1, b.entity_id: 2}
        with patch.object(t.session, 'prompt_damage_counter_placement', AsyncMock(side_effect=place)):
            await t.attack(mew, 'Psypower')
        self.assertEqual(seen['count'], 3)
        self.assertEqual(seen['cands'], {self.opp, b})
        self.assertEqual((400 - t.hp(self.opp), 400 - t.hp(b)), (10, 20))

    # --- Wobbuffet: Bide Barricade / Psychic Assault -----------------------
    async def test_bide_barricade_blocks_non_psychic_spares_psychic(self):
        t = self.table()
        t.put(WOBBUFFET, P1, 'active')
        pid = t.put(PIDGEOTTO, P1, 'bench')
        m = t.put(MUSHARNA, P1, 'bench')
        t.deck(P1, [GUZMA, N])
        self.assertIsNone(t.ability_offer(pid, 'Air Mail'))
        self.assertIsNotNone(t.ability_offer(m, 'Forewarn'))

    async def test_bide_barricade_off_when_benched(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(WOBBUFFET, P1, 'bench')
        pid = t.put(PIDGEOTTO, P1, 'bench')
        t.deck(P1, [GUZMA, N])
        self.assertIsNotNone(t.ability_offer(pid, 'Air Mail'))

    async def test_bide_barricade_blocks_opponents_too(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        pid = t.put(PIDGEOTTO, P1, 'bench')
        t.deck(P1, [GUZMA, N])
        t.put(WOBBUFFET, P2, 'active')
        self.assertIsNone(t.ability_offer(pid, 'Air Mail'))

    async def test_psychic_assault_scales_with_counters(self):
        t = self.table()
        w = t.put(WOBBUFFET, P1, 'active')
        t.energy(w, P, 2)
        from spirit.game.session.passives import effective_max_hp
        self.opp.set_attribute(AttrID.HP, effective_max_hp(t.board, self.opp) - 40)  # 4 counters
        self.assertEqual(t.damage(self.opp), 40)
        await t.attack(w, 'Psychic Assault')
        self.assertEqual(t.damage(self.opp), 40 + 50)

    # --- Sonia --------------------------------------------------------------
    async def test_sonia_two_basic_pokemon(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sonia = t.put(SONIA, P1, 'hand')
        cards = t.deck(P1, [DREEPY, DRAKLOAK, MUNNA, t.basic_energy(P)])
        seen = {}

        def picks(c, count, prompt, display):
            seen['names'], seen['n'] = t.names(c), count
            return list(c)[:count]
        t.picks = picks
        with self.choosing(0):
            await t.play(sonia)
        self.assertEqual(seen['n'], 2)
        self.assertEqual(sorted(seen['names']), ['Dreepy', 'Munna'])
        self.assertEqual(set(t.zone(P1, 'hand')), {cards[0], cards[2]})

    async def test_sonia_two_basic_energy_not_special(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sonia = t.put(SONIA, P1, 'hand')
        cards = t.deck(P1, [t.basic_energy(P), t.basic_energy(W), t.basic_energy(P),
                            'SWSH3.HidingDarknessEnergy_175', DREEPY])
        seen = {}

        def picks(c, count, prompt, display):
            seen['c'] = list(c)
            return list(c)[:2]
        t.picks = picks
        with self.choosing(1):
            await t.play(sonia)
        self.assertNotIn(cards[3], seen['c'])
        self.assertNotIn(cards[4], seen['c'])
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertTrue(all(c in cards[:3] for c in t.zone(P1, 'hand')))

    # --- Wally ---------------------------------------------------------------
    async def test_wally_evolves_pokemon_played_this_turn(self):
        t = self.table()
        dreepy = t.put(DREEPY, P1, 'active')
        # Dreepy was put into play this very turn
        t.state.entered_play_turn[dreepy.entity_id] = t.state.turn_number
        wally = t.put(WALLY, P1, 'hand')
        dk = t.deck(P1, [DRAKLOAK, DRAGAPULT])[0]
        seen = {}

        def picks(c, count, prompt, display):
            seen['names'] = t.names(c)
            return [x for x in c if x is dk]
        t.picks = picks
        self.assertTrue(t.can(wally, 'UseTrainerCard'))
        await t.play(wally)
        self.assertEqual(seen['names'], ['Drakloak'])          # no Stage 2 skip
        self.assertIs(t.active(P1), dk)
        self.assertIn(dreepy, list(dk.children))

    async def test_wally_on_going_second_players_first_turn(self):
        """'You can use this card during your first turn': P2 on turn 2,
        evolving a Dreepy benched that same turn."""
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(MUNNA, P2, 'active')         # keep P2 single-type (GLC search rule)
        dreepy = t.put(DREEPY, P2, 'bench')
        t.state.turn_number = 1
        t.next_turn()                      # turn 2, P2's first turn
        self.assertEqual(t.state.active_player_id, P2)
        t.state.entered_play_turn[dreepy.entity_id] = t.state.turn_number
        wally = t.put(WALLY, P2, 'hand')
        dk = t.deck(P2, [DRAKLOAK])[0]
        self.assertTrue(t.can(wally, 'UseTrainerCard', pid=P2))
        t.pokemon = lambda candidates, prompt: dreepy
        await t.play(wally, pid=P2)
        self.assertIn(dk, t.zone(P2, 'bench'))
        self.assertIn(dreepy, list(dk.children))

    async def test_wally_cannot_skip_to_stage_two(self):
        t = self.table()
        t.put(DREEPY, P1, 'active')
        wally = t.put(WALLY, P1, 'hand')
        t.deck(P1, [DRAGAPULT])
        await t.play(wally)
        self.assertEqual(name(t.active(P1)), 'Dreepy')
        self.assertIn('Dragapult', t.names(t.zone(P1, 'deck')))


if __name__ == '__main__':
    unittest.main()
