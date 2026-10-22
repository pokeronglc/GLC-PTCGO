"""Bug hunt round 2, deck 9 (Grass): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

G, R, W = PokemonTypes.GRASS, PokemonTypes.FIRE, PokemonTypes.WATER
APPLIN, FLAPPLE = 'SWSH2.Applin_21', 'SWSH2.Flapple_22'
HOPPIP, SKIPLOOM, JUMPLUFF = 'SWSH7.Hoppip_2', 'SWSH7.Skiploom_3', 'SWSH7.Jumpluff_4'
ROWLET, DARTRIX, DECIDUEYE = 'SV065.Rowlet_3', 'SV3.Dartrix_14', 'SM12.Decidueye_20'
CELEBI, MARACTUS = 'Promo_XY.Celebi_93', 'SV09.Maractus_8'
CHARMANDER = 'SWSH4.Charmander_23'
ENERGY_SWITCH = 'ME1.EnergySwitch_115'


class Deck9Pokemon(unittest.IsolatedAsyncioTestCase):
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

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def swap_opp_active(self, t, spec, hp=None):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = self.neutral(t.put(spec, P2, 'active'), hp)
        return self.opp

    # --- Applin: Withdraw ---------------------------------------------------
    async def test_withdraw_heads_prevents_damage_next_turn(self):
        for heads, taken in ((True, 0), (False, 30)):
            t = self.table()
            applin = self.neutral(t.put(APPLIN, P1, 'active'), 40)
            t.energy(applin, W)
            attacker = self.swap_opp_active(t, CHARMANDER)
            t.energy(attacker, R, 2)
            t.heads = heads
            await t.attack(applin, 'Withdraw')
            t.next_turn()
            await t.attack(attacker, 'Flare', pid=P2)
            with self.subTest(heads=heads):
                self.assertEqual(40 - t.hp(applin), taken)

    # --- Flapple: Apple Drop / Acid Spray ---------------------------------
    async def test_apple_drop_two_counters_then_shuffle_flapple_in(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        flapple = t.put(FLAPPLE, P1, 'bench')
        energy = t.energy(flapple, G)
        target = t.put(self.filler, P2, 'bench')
        t.pokemon = lambda c, p: target if target in c else c[0]
        await t.use(flapple, 'Apple Drop')
        self.assertEqual(t.damage(target), 20)
        self.assertIn(flapple, t.zone(P1, 'deck'))
        self.assertIn(energy, t.zone(P1, 'deck'))

    async def test_apple_drop_prevented_keeps_flapple(self):
        # Celebi's θ Stop prevents effects of opposing Abilities on it.
        t = self.table()
        t.put(self.filler, P1, 'active')
        flapple = t.put(FLAPPLE, P1, 'bench')
        celebi = t.put(CELEBI, P2, 'bench')
        t.pokemon = lambda c, p: celebi if celebi in c else c[0]
        await t.use(flapple, 'Apple Drop')
        self.assertEqual(t.damage(celebi), 0)
        self.assertIn(flapple, t.zone(P1, 'bench'))

    async def test_acid_spray_heads_discards_energy(self):
        for heads, left in ((True, 0), (False, 1)):
            t = self.table()
            f = t.put(FLAPPLE, P1, 'active')
            t.energy(f, G, 2)
            t.energy(self.opp, W)
            t.heads = heads
            await t.attack(f, 'Acid Spray')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 60)
                self.assertEqual(len(t.board.attached_energies(self.opp)), left)

    # --- Hoppip: Continuous Spin -------------------------------------------
    async def test_continuous_spin_until_tails(self):
        t = self.table()
        h = t.put(HOPPIP, P1, 'active')
        t.energy(h, G)
        # flip_until_tails is its own coin screen (not Table.heads): 3 heads
        with patch.object(EffectContext, 'flip_until_tails', AsyncMock(return_value=3)):
            await t.attack(h, 'Continuous Spin')
        self.assertEqual(400 - t.hp(self.opp), 60)

    # --- Skiploom: Solar Evolution -----------------------------------------
    async def test_solar_evolution_on_energy_from_hand(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sk = t.put(SKIPLOOM, P1, 'bench')
        t.deck(P1, [JUMPLUFF])
        energy = t.put(t.basic_energy(G), P1, 'hand')
        await t.play(energy, targets=[sk.entity_id])
        self.assertIn('Jumpluff', t.names(t.board.pokemon_in_play(P1)))

    async def test_solar_evolution_not_on_effect_attach(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        sk = t.put(SKIPLOOM, P1, 'bench')
        t.deck(P1, [JUMPLUFF])
        fire = t.energy(me, G)
        t.pokemon = lambda c, p: sk if sk in c and 'from' not in p.lower() else (me if me in c else c[0])
        t.picks = lambda cards, count, prompt, display: [fire] if fire in cards else cards[:count]
        await t.play(t.put(ENERGY_SWITCH, P1, 'hand'))
        self.assertIn(fire, sk.children)
        self.assertNotIn('Jumpluff', t.names(t.board.pokemon_in_play(P1)))

    # --- Jumpluff: Fluffy Barrage ------------------------------------------
    async def test_fluffy_barrage_attacks_twice(self):
        t = self.table()
        j = t.put(JUMPLUFF, P1, 'active')
        t.energy(j, G)
        with patch.object(t.session, 'prompt_player_choice', AsyncMock(return_value=0)):
            ended = await t.attack(j, 'Spinning Attack')
            self.assertFalse(ended)
            self.assertIsNotNone(t.attack_offer(j, 'Spinning Attack'))
            ended = await t.attack(j, 'Spinning Attack')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertTrue(ended)                    # no third attack

    async def test_skiploom_attacks_once(self):
        t = self.table()
        s = t.put(SKIPLOOM, P1, 'active')
        t.energy(s, G)
        ended = await t.attack(s, 'Spinning Attack')
        self.assertTrue(ended)

    # --- Rowlet / Dartrix / Decidueye --------------------------------------
    async def test_rowlet_add_on_draws(self):
        t = self.table()
        r = t.put(ROWLET, P1, 'active')
        t.energy(r, W)
        await t.attack(r, 'Add On')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_shoot_through_bench_no_weakness(self):
        t = self.table()
        d = t.put(DARTRIX, P1, 'active')
        t.energy(d, G, 2)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [G.value])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        before = t.hp(bench)
        await t.attack(d, 'Shoot Through')
        self.assertEqual(400 - t.hp(self.opp), 40)
        self.assertEqual(before - t.hp(bench), 20)

    async def test_skill_dive_any_pokemon(self):
        t = self.table()
        d = t.put(DECIDUEYE, P1, 'active')
        t.energy(d, G)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [G.value])
        t.picks = lambda cards, count, prompt, display: [bench] if bench in cards else cards[:count]
        before = t.hp(bench)
        await t.attack(d, 'Skill Dive')
        self.assertEqual(before - t.hp(bench), 40)
        self.assertEqual(t.hp(self.opp), 400)

    async def test_tracking_shot_only_damaged_benched(self):
        t = self.table()
        d = t.put(DECIDUEYE, P1, 'active')
        t.energy(d, G, 2)
        clean = t.put(self.filler, P2, 'bench')
        hurt = t.put(self.filler, P2, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 10)
        hurt_before, clean_before = t.hp(hurt), t.hp(clean)
        seen = {}

        def pick(cands, prompt):
            seen['c'] = list(cands)
            return hurt
        t.pokemon = pick
        await t.attack(d, 'Tracking Shot')
        self.assertEqual(seen['c'], [hurt])
        self.assertEqual(hurt_before - t.hp(hurt), 80)
        self.assertEqual(t.hp(clean), clean_before)

    # RULING (owner, Oct 14) -- reverses the Oct 10 change: Tracking Shot does
    # its printed 80 to the Active AND 80 to a damaged Benched Pokemon.
    async def test_tracking_shot_hits_active_and_damaged_bench(self):
        t = self.table()
        d = t.put(DECIDUEYE, P1, 'active')
        t.energy(d, G, 2)
        hurt = t.put(self.filler, P2, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 10)
        before = t.hp(hurt)
        t.pokemon = lambda c, p: hurt if hurt in c else c[0]
        await t.attack(d, 'Tracking Shot')
        self.assertEqual(400 - t.hp(self.opp), 80)
        self.assertEqual(before - t.hp(hurt), 80)

    async def test_tracking_shot_no_damaged_bench_only_active(self):
        t = self.table()
        d = t.put(DECIDUEYE, P1, 'active')
        t.energy(d, G, 2)
        clean = t.put(self.filler, P2, 'bench')
        before = t.hp(clean)
        await t.attack(d, 'Tracking Shot')
        self.assertEqual(t.hp(clean), before)
        self.assertEqual(400 - t.hp(self.opp), 80)

    # --- Celebi ---------------------------------------------------------------
    async def test_sparkle_motion_one_counter_each(self):
        t = self.table()
        c = t.put(CELEBI, P1, 'active')
        t.energy(c, G)
        bench = t.put(self.filler, P2, 'bench')
        mine = t.put(self.filler, P1, 'bench')
        await t.attack(c, 'Sparkle Motion')
        self.assertEqual(400 - t.hp(self.opp), 10)
        self.assertEqual(t.damage(bench), 10)
        self.assertEqual(t.damage(mine), 0)

    async def _celebi_ko(self, heads):
        t = self.table()
        celebi = self.neutral(t.put(CELEBI, P1, 'active', hp=10))
        t.put(self.filler, P1, 'bench')
        attacker = self.swap_opp_active(t, CHARMANDER)
        t.energy(attacker, R, 2)
        t.heads = heads
        t.next_turn()
        await t.attack(attacker, 'Flare', pid=P2)
        self.assertNotIn(celebi, t.board.pokemon_in_play(P1))
        return t, celebi

    # Was a bug (fixed Oct 10): Leap Through Time shuffles Celebi in but the opponent still takes a Prize
    async def test_leap_through_time_heads_no_prize(self):
        t, celebi = await self._celebi_ko(True)
        self.assertIn(celebi, t.zone(P1, 'deck'))
        self.assertEqual(t.board.prizes_taken(P2), 0)

    # Was a bug (fixed Oct 10): Leap Through Time ignores the coin: on tails Celebi is still shuffled into the deck
    async def test_leap_through_time_tails_normal_ko(self):
        t, celebi = await self._celebi_ko(False)
        self.assertIn(celebi, t.zone(P1, 'discard'))
        self.assertEqual(t.board.prizes_taken(P2), 1)

    # --- Maractus: Exploding Needles / Corner ----------------------------
    async def _needles(self, where, both=False):
        t = self.table()
        m = self.neutral(t.put(MARACTUS, P1, where, hp=10))
        if where == 'bench':
            t.put(self.filler, P1, 'active', hp=10 if both else None)
            t.put(self.filler, P1, 'bench')       # so P1 still has a Pokémon
        else:
            t.put(self.filler, P1, 'bench')
        attacker = self.swap_opp_active(t, DARTRIX, 400)
        t.energy(attacker, G, 2)
        t.pokemon = lambda c, p: m if m in c else c[0]
        t.next_turn()
        await t.attack(attacker, 'Shoot Through', pid=P2)
        self.assertNotIn(m, t.board.pokemon_in_play(P1))
        return t, attacker

    # Was a bug (fixed Oct 10): Exploding Needles is declared with no trigger, so it never fires
    async def test_exploding_needles_active_ko(self):
        t, attacker = await self._needles('active')
        self.assertEqual(400 - t.hp(attacker), 60)

    async def test_exploding_needles_not_on_bench(self):
        t, attacker = await self._needles('bench')
        self.assertEqual(t.hp(attacker), 400)

    async def test_exploding_needles_not_on_bench_when_active_also_ko(self):
        # Passes today only because the Ability never fires; with the trigger
        # added, the script's "Active Spot is empty" check misfires here.
        t, attacker = await self._needles('bench', both=True)
        self.assertEqual(t.hp(attacker), 400)

    async def test_corner_blocks_retreat_next_turn(self):
        t = self.table()
        m = t.put(MARACTUS, P1, 'active')
        t.energy(m, G)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W, 4)
        await t.attack(m, 'Corner')
        self.assertEqual(400 - t.hp(self.opp), 20)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))


if __name__ == "__main__":
    unittest.main()
