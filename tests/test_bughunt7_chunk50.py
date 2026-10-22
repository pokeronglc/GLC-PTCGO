"""Bug hunt round 7, chunk 50: Custom Catcher LOT 171, Turtonator POR 17,
Kiawe BUS 116, Ninja Boy STS 103, Will CEC 208, Toedscruel PAR 17,
Cursed Shovel RCL 157, Elekid PAR 59, Pokedex EVO 82 -- each checked against
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

FIRE, WATER, LIGHT = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.LIGHTNING

CATCHER = 'SM8.CustomCatcher_171'
TURTONATOR = 'ME3.Turtonator_17'
KIAWE = 'SM3.Kiawe_116'
NINJA = 'XY11.NinjaBoy_103'
WILL = 'SM12.Will_208'
TOEDSCRUEL = 'SV4.Toedscruel_17'
SHOVEL = 'SWSH2.CursedShovel_157'
ELEKID = 'SV4.Elekid_59'
POKEDEX = 'XY12.Pokdex_82'
RETRIEVAL = 'SV1.EnergyRetrieval_171'


def name(card):
    return def_for(card.archetype_id).display_name or '?'


class NoCoinTable(Table):
    """Table that leaves EffectContext.flip_coins real (so Will's forced
    first coin is honoured)."""
    def _patches(self):
        return [p for p in super()._patches() if p.attribute != 'flip_coins']


class Chunk50(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, cls=Table):
        t = cls(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def clear(self, t, zone, pid=P1):
        area = t.board.find_player_area(pid, zone)
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def energies_on(self, p):
        return [c for c in p.children if self.is_energy(c)]

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Custom Catcher LOT 171 ----------------------------------------------
    async def test_custom_catcher_single_draws_until_three(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, 'hand')
        card = t.put(CATCHER, P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertIs(t.active(P2), self.opp)

    async def test_custom_catcher_pair_switches_opponent(self):
        t = self.table()
        self.mine(t, self.filler)
        target = t.put(self.filler, P2, 'bench')
        self.clear(t, 'hand')
        first = t.put(CATCHER, P1, 'hand')
        second = t.put(CATCHER, P1, 'hand')
        t.put(self.item, P1, 'hand')
        t.put(self.item, P1, 'hand')
        t.pokemon = lambda cands, prompt: target
        await t.play(first)
        self.assertIs(t.active(P2), target)
        self.assertIn(second, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2, 'pair does not also draw')

    async def test_custom_catcher_pair_declined_only_draws(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(self.filler, P2, 'bench')
        self.clear(t, 'hand')
        first = t.put(CATCHER, P1, 'hand')
        second = t.put(CATCHER, P1, 'hand')
        t.yes = False
        await t.play(first)
        self.assertIs(t.active(P2), self.opp)
        self.assertIn(second, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_custom_catcher_no_opponent_bench_cannot_pair(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, 'hand')
        first = t.put(CATCHER, P1, 'hand')
        second = t.put(CATCHER, P1, 'hand')
        await t.play(first)
        self.assertIn(second, t.zone(P1, 'hand'), 'second copy is not wasted')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    # --- Turtonator POR 17: Shell Spikes / Heat Breath ------------------------
    async def test_turtonator_shell_spikes_active_discards_attacker_energy(self):
        t = self.table()
        turt = self.mine(t, TURTONATOR)
        t.energy(self.opp, WATER, 4)
        title, _ = self.filler_attack()
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        self.assertLess(t.hp(turt), 120, 'Turtonator was damaged')
        self.assertEqual(len(self.energies_on(self.opp)), 3)

    async def test_turtonator_shell_spikes_not_on_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        turt = self.mine(t, TURTONATOR, zone='bench')
        # Opponent's Elekid snipes the Benched Turtonator.
        self.clear(t, 'activePokemonArea', P2)
        elekid = self.mine(t, ELEKID, pid=P2)
        t.energy(elekid, LIGHT, 2)
        t.picks = lambda cards, count, prompt, display: [turt]   # browser target pick
        t.next_turn()
        await t.attack(elekid, 'Crackling Shot', pid=P2)
        self.assertEqual(t.damage(turt), 30)
        self.assertEqual(len(self.energies_on(elekid)), 2)

    # --- Will CEC 208 ---------------------------------------------------------
    async def _will_heat_breath(self, choice):
        t = self.table(NoCoinTable)
        turt = self.mine(t, TURTONATOR, FIRE, 3)
        will = t.put(WILL, P1, 'hand')

        async def choose(ctx, prompt, buttons, *a, **k):
            return choice
        with patch.object(EffectContext, 'choose', choose):
            await t.play(will)
        await t.attack(turt, 'Heat Breath')
        return t

    async def test_will_choose_heads_forces_heat_breath_heads(self):
        for _ in range(4):
            await self._will_heat_breath(0)
            self.assertEqual(self.dealt(), 160)

    async def test_will_choose_tails_forces_heat_breath_tails(self):
        for _ in range(4):
            await self._will_heat_breath(1)
            self.assertEqual(self.dealt(), 80)

    async def test_will_expires_at_end_of_turn(self):
        t = self.table(NoCoinTable)
        self.mine(t, self.filler)
        will = t.put(WILL, P1, 'hand')

        async def choose(ctx, prompt, buttons, *a, **k):
            return 0
        with patch.object(EffectContext, 'choose', choose):
            await t.play(will)
        self.assertTrue(t.state.forced_coin_result)
        t.next_turn()
        self.assertIsNone(t.state.forced_coin_result, 'Will only lasts this turn')

    # --- Kiawe BUS 116 --------------------------------------------------------
    async def test_kiawe_attaches_four_fire_to_one_pokemon_and_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, TURTONATOR, zone='bench')
        fires = t.deck(P1, [t.basic_energy(FIRE)] * 5)
        card = t.put(KIAWE, P1, 'hand')
        t.pokemon = lambda cands, prompt: bench
        ended = await t.play(card)
        on = self.energies_on(bench)
        self.assertEqual(len(on), 4)
        self.assertTrue(all(c in fires for c in on))
        self.assertTrue(ended, 'Kiawe ends the turn')

    async def test_kiawe_cannot_take_non_fire_energy(self):
        t = self.table()
        me = self.mine(t, self.filler)
        water = t.deck(P1, [t.basic_energy(WATER)] * 2)
        card = t.put(KIAWE, P1, 'hand')
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return cards[:count]
        t.picks = picks
        await t.play(card)
        self.assertFalse(any(c in water for c in seen))
        self.assertEqual(self.energies_on(me), [])

    # --- Ninja Boy STS 103 ----------------------------------------------------
    async def test_ninja_boy_swaps_basic_keeping_attachments_and_damage(self):
        t = self.table()
        old = self.mine(t, self.filler, WATER, 1)
        old.set_attribute(AttrID.HP, t.hp(old) - 30)
        new = t.deck(P1, [TURTONATOR])[0]
        card = t.put(NINJA, P1, 'hand')
        t.pokemon = lambda cands, prompt: old
        t.picks = lambda cards, count, prompt, display: [new]
        await t.play(card)
        self.assertIs(t.active(P1), new)
        self.assertEqual(len(self.energies_on(new)), 1)
        self.assertEqual(t.damage(new), 30)
        self.assertIn(old, t.zone(P1, 'deck'))

    async def test_ninja_boy_cannot_switch_stage1(self):
        t = self.table()
        toed = self.mine(t, TOEDSCRUEL)
        t.deck(P1, [TURTONATOR])
        card = t.put(NINJA, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertIs(t.active(P1), toed)

    # --- Toedscruel PAR 17: Slime Mold Colony ---------------------------------
    async def test_toedscruel_blocks_opponent_trainer_recovery(self):
        t = self.table()
        self.mine(t, TOEDSCRUEL)
        e1 = t.put(t.basic_energy(WATER), P2, 'discard')
        card = t.put(RETRIEVAL, P2, 'hand')
        t.next_turn()
        if t.can(card, 'UseTrainerCard', pid=P2):
            await t.play(card, pid=P2)
        self.assertIn(e1, t.zone(P2, 'discard'))
        self.assertNotIn(e1, t.zone(P2, 'hand'))

    async def test_toedscruel_does_not_block_own_side(self):
        t = self.table()
        self.mine(t, TOEDSCRUEL)
        e1 = t.put(t.basic_energy(WATER), P1, 'discard')
        card = t.put(RETRIEVAL, P1, 'hand')
        await t.play(card)
        self.assertIn(e1, t.zone(P1, 'hand'))

    # --- Cursed Shovel RCL 157 ------------------------------------------------
    async def _shovel(self, hp):
        t = self.table()
        me = self.mine(t, self.filler)
        shovel = t.put(SHOVEL, P1, 'hand')
        await t.play(shovel, targets=[me.entity_id])
        self.assertIn(shovel, me.children)
        me.set_attribute(AttrID.HP, hp)
        t.mine_bench = self.mine(t, self.filler, zone='bench')
        t.energy(self.opp, WATER, 4)
        title, _ = self.filler_attack()
        before = len(t.zone(P2, 'deck'))
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return t, me, before

    async def test_cursed_shovel_ko_discards_two_from_opponent_deck(self):
        t, me, before = await self._shovel(10)
        self.assertNotIn(me, t.zone(P1, 'active'))
        self.assertEqual(len(t.zone(P2, 'deck')), before - 2)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    async def test_cursed_shovel_no_ko_no_discard(self):
        t, me, before = await self._shovel(300)
        self.assertIs(t.active(P1), me)
        self.assertEqual(len(t.zone(P2, 'deck')), before)

    # --- Elekid PAR 59: Crackling Shot ----------------------------------------
    async def test_elekid_bench_snipe_ignores_weakness(self):
        t = self.table()
        elekid = self.mine(t, ELEKID)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 400)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [LIGHT])
        t.picks = lambda cards, count, prompt, display: [bench]   # browser target pick
        await t.attack(elekid, 'Crackling Shot')
        self.assertEqual(400 - t.hp(bench), 30)
        self.assertEqual(self.dealt(), 0)

    async def test_elekid_active_target_applies_weakness(self):
        t = self.table()
        elekid = self.mine(t, ELEKID)
        t.put(self.filler, P2, 'bench')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [LIGHT])
        t.picks = lambda cards, count, prompt, display: [self.opp]
        await t.attack(elekid, 'Crackling Shot')
        self.assertEqual(self.dealt(), 60)

    # --- Pokedex EVO 82 -------------------------------------------------------
    async def test_pokedex_reorders_only_top_five(self):
        t = self.table()
        self.mine(t, self.filler)
        sixth = t.deck(P1, [t.basic_energy(WATER)])[0]
        top5 = t.deck(P1, [t.basic_energy(FIRE)] * 5)   # last = topmost
        card = t.put(POKEDEX, P1, 'hand')
        seen = []

        async def chooser(pid, src, cards, count, *a, **k):
            seen.append(list(cards))
            return [c.entity_id for c in cards][::-1]
        with patch.object(t.session, 'prompt_card_chooser', chooser):
            await t.play(card)
        self.assertEqual(len(seen), 1)
        self.assertEqual(set(seen[0]), set(top5))
        self.assertNotIn(sixth, seen[0])
        deck = t.zone(P1, 'deck')
        new_top_first = list(reversed(deck[-5:]))
        self.assertEqual(new_top_first, list(reversed(seen[0])))
        self.assertIs(deck[-6], sixth)
        self.assertEqual(len(deck), 36)


if __name__ == '__main__':
    unittest.main()


class SlimeMoldColonyRuling(Chunk50):
    """Owner ruling (Oct 12): discard->hand-only Trainers can't be played at
    all against Slime Mold Colony; cards with another option stay playable."""

    def _board(self):
        t = self.table()
        self.mine(t, TOEDSCRUEL)
        t.put(t.basic_energy(WATER), P2, 'discard')
        t.put(self.filler, P2, 'discard')
        t.next_turn()
        return t

    async def test_energy_retrieval_not_playable(self):
        t = self._board()
        self.assertFalse(t.can(t.put(RETRIEVAL, P2, 'hand'), 'UseTrainerCard', pid=P2))

    async def test_night_stretcher_not_playable(self):
        t = self._board()
        self.assertFalse(t.can(t.put('ME1.NightStretcher_173', P2, 'hand'),
                               'UseTrainerCard', pid=P2))

    async def test_rescue_stretcher_still_playable(self):
        t = self._board()
        for _ in range(3):
            t.put(self.filler, P2, 'discard')
        self.assertTrue(t.can(t.put('SM2.RescueStretcher_130', P2, 'hand'),
                              'UseTrainerCard', pid=P2))

    async def test_own_side_unaffected(self):
        t = self.table()
        self.mine(t, TOEDSCRUEL)
        t.put(t.basic_energy(WATER), P1, 'discard')
        self.assertTrue(t.can(t.put(RETRIEVAL, P1, 'hand'), 'UseTrainerCard'))


for _n in [n for n in vars(Chunk50) if n.startswith('test_')]:
    setattr(SlimeMoldColonyRuling, _n, None)
