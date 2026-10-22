"""Fixes: optional / conditional self-shuffle attacks, Order a Raid, "draw a
card for each ..." attacks, Iono's Kilowattrel / Cycling Road discard costs
and Magcargo's Lava Zone."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED
from tests.sweep_core import pay_cost, neutral
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack
from spirit.tools.effect_smoke import P1, P2

POLITOED, LOPUNNY, GHOLDENGO = 'SM2.Politoed_25', 'SM5.Lopunny_107', 'SV08.Gholdengo_131'
POLIWRATH, BUTTERFREE = 'SV06.Poliwrath_43', 'SV035.Butterfree_12'
VESPIQUEN, COMBEE = 'SV2.Vespiquen_9', 'SV2.Combee_8'
KIRLIA, PLUSLE, ORICORIO = 'BW11.Kirlia_RC9', 'SM7.Plusle_53', 'SV4.Oricorio_67'
KILOWATTREL, KILOWATTREL_ME = 'SV09.IonosKilowattrel_55', 'ME2PT5.IonosKilowattrel_72'
CYCLING_ROAD = 'SV035.CyclingRoad_157'
MAGCARGO = 'SV05.Magcargo_29'
SWITCH, ROPE, BOSS = 'SV1.Switch_194', 'BW8.EscapeRope_120', 'SWSH2.BosssOrders_154'
COPPERAJAH, WEEZING = 'SWSH3.Copperajah_132', 'SWSH2.GalarianWeezing_113'

PSY, L, W, F = (PokemonTypes.PSYCHIC, PokemonTypes.LIGHTNING, PokemonTypes.WATER,
                PokemonTypes.FIRE)


def attack_def(spec, title):
    return next(a for a in fixtures.definition(spec).abilities
                if isinstance(a, Attack) and a.title == title)


class FixAttackDrawsShuffles(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, spec, title, *, opp_bench=1, my_bench=1):
        t = Table(self)
        self.me = t.put(spec, P1, 'active')
        pay_cost(t, self.me, attack_def(spec, title))
        self.my_bench = [neutral(t.put(self.filler, P1, 'bench')) for _ in range(my_bench)]
        self.opp = neutral(t.put(self.filler, P2, 'active'), hp=400)
        self.opp_bench = [neutral(t.put(self.filler, P2, 'bench')) for _ in range(opp_bench)]
        return t

    def in_play(self, t, p):
        return p in t.board.pokemon_in_play(p.owning_player_id)

    # --- 1. "You may shuffle this Pokémon ..." ----------------------------
    async def _optional_self_shuffle(self, spec, title):
        for yes in (True, False):
            t = self.table(spec, title)
            t.yes = yes
            deck = len(t.zone(P1, 'deck'))
            stack = 1 + len(self.me.children)
            await t.attack(self.me, title)
            if yes:
                self.assertFalse(self.in_play(t, self.me), spec)
                self.assertEqual(len(t.zone(P1, 'deck')), deck + stack, spec)
            else:
                self.assertIs(t.active(P1), self.me, spec)
                self.assertEqual(len(t.zone(P1, 'deck')), deck, spec)

    async def test_politoed_hyper_jump_optional(self):
        await self._optional_self_shuffle(POLITOED, 'Hyper Jump')

    async def test_lopunny_happy_turn_optional(self):
        await self._optional_self_shuffle(LOPUNNY, 'Happy Turn')

    async def test_gholdengo_surf_back_optional(self):
        await self._optional_self_shuffle(GHOLDENGO, 'Surf Back')

    async def test_poliwrath_jumping_uppercut_yes(self):
        t = self.table(POLIWRATH, 'Jumping Uppercut')
        t.yes = True
        hp, deck = t.hp(self.opp), len(t.zone(P1, 'deck'))
        stack = 1 + len(self.me.children)
        await t.attack(self.me, 'Jumping Uppercut')
        self.assertEqual(hp - t.hp(self.opp), 240)
        self.assertFalse(self.in_play(t, self.me))
        self.assertEqual(len(t.zone(P1, 'deck')), deck + stack)

    async def test_poliwrath_jumping_uppercut_no(self):
        t = self.table(POLIWRATH, 'Jumping Uppercut')
        t.yes = False
        hp, deck = t.hp(self.opp), len(t.zone(P1, 'deck'))
        await t.attack(self.me, 'Jumping Uppercut')
        self.assertEqual(hp - t.hp(self.opp), 120)
        self.assertIs(t.active(P1), self.me)
        self.assertEqual(len(t.zone(P1, 'deck')), deck)

    async def test_butterfree_bye_bye_flight_with_bench(self):
        t = self.table(BUTTERFREE, 'Bye-Bye Flight')
        target = self.opp_bench[0]
        opp_deck, deck = len(t.zone(P2, 'deck')), len(t.zone(P1, 'deck'))
        stack = 1 + len(self.me.children)
        await t.attack(self.me, 'Bye-Bye Flight')
        self.assertFalse(self.in_play(t, target))
        self.assertEqual(len(t.zone(P2, 'deck')), opp_deck + 1)
        self.assertFalse(self.in_play(t, self.me))
        self.assertEqual(len(t.zone(P1, 'deck')), deck + stack)

    async def test_butterfree_bye_bye_flight_no_bench_does_nothing(self):
        t = self.table(BUTTERFREE, 'Bye-Bye Flight', opp_bench=0)
        deck = len(t.zone(P1, 'deck'))
        await t.attack(self.me, 'Bye-Bye Flight')
        self.assertIs(t.active(P1), self.me)
        self.assertEqual(len(t.zone(P1, 'deck')), deck)

    # --- 2. Vespiquen: Order a Raid -------------------------------------
    async def test_vespiquen_order_a_raid_shuffles_combee(self):
        t = self.table(VESPIQUEN, 'Order a Raid')
        combee = t.put(COMBEE, P1, 'bench')
        t.energy(combee, PokemonTypes.GRASS)
        deck, hp = len(t.zone(P1, 'deck')), t.hp(self.opp)
        await t.attack(self.me, 'Order a Raid')
        self.assertFalse(self.in_play(t, combee))
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 2)
        self.assertTrue(self.in_play(t, self.my_bench[0]))
        self.assertEqual(hp - t.hp(self.opp), 120)

    async def test_vespiquen_order_a_raid_without_combee_does_nothing(self):
        t = self.table(VESPIQUEN, 'Order a Raid')
        deck, hp = len(t.zone(P1, 'deck')), t.hp(self.opp)
        await t.attack(self.me, 'Order a Raid')
        self.assertEqual(hp, t.hp(self.opp))
        self.assertEqual(len(t.zone(P1, 'deck')), deck)
        self.assertTrue(self.in_play(t, self.my_bench[0]))

    # --- 3. "Draw a card for each ..." -----------------------------------
    async def test_kirlia_tiptoe_step_draws_per_psychic(self):
        t = self.table(KIRLIA, 'Tiptoe Step')    # cost: 1 Psychic
        t.energy(self.me, PSY, 2)
        hand = len(t.zone(P1, 'hand'))
        await t.attack(self.me, 'Tiptoe Step')
        self.assertEqual(len(t.zone(P1, 'hand')) - hand, 3)

    async def test_kirlia_tiptoe_step_ignores_other_energy(self):
        t = self.table(KIRLIA, 'Tiptoe Step')
        t.energy(self.me, W, 2)
        hand = len(t.zone(P1, 'hand'))
        await t.attack(self.me, 'Tiptoe Step')
        self.assertEqual(len(t.zone(P1, 'hand')) - hand, 1)

    async def _shuffle_draw_per_bench(self, spec, title):
        t = self.table(spec, title, my_bench=2, opp_bench=3)
        for _ in range(2):
            t.put(self.item, P1, 'hand')
        await t.attack(self.me, title)
        self.assertEqual(len(t.zone(P1, 'hand')), 5, spec)
        self.assertEqual(len(t.zone(P1, 'deck')), 30 + 2 - 5, spec)

    async def test_plusle_draw_for_everybody(self):
        await self._shuffle_draw_per_bench(PLUSLE, 'Draw for Everybody')

    async def test_oricorio_pep_up(self):
        await self._shuffle_draw_per_bench(ORICORIO, 'Pep Up')

    async def test_oricorio_pep_up_no_bench_draws_nothing(self):
        t = self.table(ORICORIO, 'Pep Up', my_bench=0, opp_bench=0)
        t.put(self.item, P1, 'hand')
        await t.attack(self.me, 'Pep Up')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- 4. Iono's Kilowattrel: Flashing Draw ----------------------------
    async def test_kilowattrel_pays_lightning_energy(self):
        for spec in (KILOWATTREL, KILOWATTREL_ME):
            t = Table(self)
            neutral(t.put(self.filler, P2, 'active'))
            t.put(self.filler, P1, 'active')
            bird = t.put(spec, P1, 'bench')
            energy = t.energy(bird, L)
            await t.use(bird, 'Flashing Draw')
            self.assertEqual(t.board.attached_energies(bird), [], spec)
            self.assertIn(energy, t.zone(P1, 'discard'), spec)
            self.assertEqual(len(t.zone(P1, 'hand')), 6, spec)

    async def test_kilowattrel_not_offered_without_lightning(self):
        t = Table(self)
        neutral(t.put(self.filler, P2, 'active'))
        t.put(self.filler, P1, 'active')
        bird = t.put(KILOWATTREL, P1, 'bench')
        self.assertIsNone(t.ability_offer(bird, 'Flashing Draw'))
        t.energy(bird, W)
        self.assertIsNone(t.ability_offer(bird, 'Flashing Draw'))

    # --- 5. Cycling Road --------------------------------------------------
    async def test_cycling_road_discards_basic_energy_to_draw(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        neutral(t.put(self.filler, P2, 'active'))
        road = t.stadium(CYCLING_ROAD, P1)
        t.put(self.item, P1, 'hand')
        energy = t.put(t.basic_energy(F), P1, 'hand')
        entry = next(iter(t.offers(road, None, P1)), None)
        await t.do(entry)
        self.assertIn(energy, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)       # item + drawn card
        self.assertEqual(len(t.zone(P1, 'deck')), 29)

    async def test_cycling_road_needs_basic_energy(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        neutral(t.put(self.filler, P2, 'active'))
        road = t.stadium(CYCLING_ROAD, P1)
        t.put(self.item, P1, 'hand')
        self.assertFalse(t.offers(road, None, P1))

    # --- 6. Magcargo: Lava Zone -------------------------------------------
    def lava(self, magcargo_zone='active'):
        """P1 owns Magcargo; it is P2's turn."""
        t = Table(self)
        if magcargo_zone == 'active':
            self.mag = t.put(MAGCARGO, P1, 'active')
        else:
            t.put(self.filler, P1, 'active')
            self.mag = t.put(MAGCARGO, P1, 'bench')
        self.opp = t.put(self.filler, P2, 'active')
        self.opp_new = t.put(self.filler, P2, 'bench')
        t.next_turn()
        self.assertEqual(t.state.active_player_id, P2)
        return t

    async def retreat(self, t, pokemon, to):
        t.energy(pokemon, W, max(1, t.retreat(pokemon)))
        entry = next(e for e in t.offers(pokemon, None, P2)
                     if e['selectableAction']['description'] == 'BaseRetreat')
        energies = [e.entity_id for e in pokemon.children][:t.retreat(pokemon)]
        await t.do(entry, targets=[to.entity_id] + energies, pid=P2)
        self.assertIs(t.active(P2), to)

    async def test_lava_zone_burns_after_retreat_magcargo_active(self):
        t = self.lava('active')
        await self.retreat(t, self.opp, self.opp_new)
        self.assertIn(BURNED, t.conditions(self.opp_new))

    async def test_lava_zone_burns_after_retreat_magcargo_benched(self):
        t = self.lava('bench')
        await self.retreat(t, self.opp, self.opp_new)
        self.assertIn(BURNED, t.conditions(self.opp_new))

    async def test_lava_zone_burns_after_switch(self):
        t = self.lava('bench')
        t.pokemon = lambda cands, prompt: self.opp_new if self.opp_new in cands else cands[0]
        await t.play(t.put(SWITCH, P2, 'hand'), pid=P2)
        self.assertIs(t.active(P2), self.opp_new)
        self.assertIn(BURNED, t.conditions(self.opp_new))

    async def test_lava_zone_burns_after_escape_rope(self):
        t = self.lava('active')
        t.put(self.filler, P1, 'bench')
        await t.play(t.put(ROPE, P2, 'hand'), pid=P2)
        self.assertIs(t.active(P2), self.opp_new)
        self.assertIn(BURNED, t.conditions(self.opp_new))

    async def test_lava_zone_not_on_magcargo_owners_turn(self):
        t = Table(self)
        self.mag = t.put(MAGCARGO, P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        new = t.put(self.filler, P2, 'bench')
        t.pokemon = lambda cands, prompt: new if new in cands else cands[0]
        await t.play(t.put(BOSS, P1, 'hand'), pid=P1)
        self.assertIs(t.active(P2), new)
        self.assertNotIn(BURNED, t.conditions(new))
        self.assertTrue(opp in t.zone(P2, 'bench'))

    async def test_lava_zone_ignores_own_side_switch(self):
        """Magcargo's owner switching during the opponent's turn is not covered."""
        t = Table(self)
        self.mag = t.put(MAGCARGO, P1, 'bench')
        mine = t.put(self.filler, P1, 'active')
        neutral(t.put(self.filler, P2, 'active'))
        t.put(self.filler, P2, 'bench')
        t.state.active_player_id = P1
        t.pokemon = lambda cands, prompt: self.mag if self.mag in cands else cands[0]
        await t.play(t.put(SWITCH, P1, 'hand'), pid=P1)
        self.assertIs(t.active(P1), self.mag)
        self.assertNotIn(BURNED, t.conditions(self.mag))
        self.assertNotIn(BURNED, t.conditions(mine))

    async def test_lava_zone_not_on_knock_out_promotion(self):
        t = self.lava('bench')
        await t.session.fire_move_to_active_triggers(
            self.opp_new, previous_active=None, switch_reason="effect")
        self.assertNotIn(BURNED, t.conditions(self.opp_new))

    async def test_lava_zone_respects_condition_immunity(self):
        t = Table(self)
        self.mag = t.put(MAGCARGO, P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        immune = t.put(COPPERAJAH, P2, 'bench')
        t.next_turn()
        await self.retreat(t, opp, immune)
        self.assertNotIn(BURNED, t.conditions(immune))

    async def test_lava_zone_respects_ability_lock(self):
        t = Table(self)
        self.mag = t.put(MAGCARGO, P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        weezing = t.put(WEEZING, P2, 'bench')     # Neutralizing Gas once Active
        t.next_turn()
        await self.retreat(t, opp, weezing)
        self.assertNotIn(BURNED, t.conditions(weezing))


if __name__ == '__main__':
    unittest.main()
