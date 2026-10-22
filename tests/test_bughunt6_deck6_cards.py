"""Bug hunt round 6, deck 6 (Fire): Fuecoco PAL 35, Crocalor PAR 24,
Skeledirge SSP 31, Ponyta MEW 77, Rapidash DRI 30, Vulpix SSP 16,
Ninetales OBF 29."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

F, W, D, P = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.DARKNESS, PokemonTypes.PSYCHIC
FUECOCO, CROCALOR, SKELEDIRGE = 'SV2.Fuecoco_35', 'SV4.Crocalor_24', 'SV08.Skeledirge_31'
PONYTA, RAPIDASH = 'SV035.Ponyta_77', 'SV10.Rapidash_30'
VULPIX, NINETALES = 'SV08.Vulpix_16', 'SV3.Ninetales_29'
SABLEYE = 'SV2.Sableye_136'                # Unseen Claw 20 (+70 if opp Active has a condition)
HAUNTER = 'SM10.Haunter_69'                # Sinister Fog: Poison + 1 counter on each opp Benched


class Deck6Cards6(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        mon._start_hp = mon.get_attribute(AttrID.HP, 0)
        return mon

    @staticmethod
    def took(t, mon):
        return mon._start_hp - t.hp(mon)

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    # --- Fuecoco: Spacing Out ----------------------------------------------
    async def test_spacing_out_heads_heals_30(self):
        t = self.table()
        f = t.put(FUECOCO, P1, 'active', hp=40)
        t.energy(f, F)
        t.heads = True
        await t.attack(f, 'Spacing Out')
        self.assertEqual(t.hp(f), 70)
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_spacing_out_tails_no_heal(self):
        t = self.table()
        f = t.put(FUECOCO, P1, 'active', hp=40)
        t.energy(f, F)
        t.heads = False
        await t.attack(f, 'Spacing Out')
        self.assertEqual(t.hp(f), 40)

    # --- Crocalor: Rolling Fireball -----------------------------------------
    async def test_rolling_fireball_returns_one_energy_to_hand(self):
        t = self.table()
        c = t.put(CROCALOR, P1, 'active')
        e1, e2 = t.energy(c, F, 2)
        await t.attack(c, 'Rolling Fireball')
        self.assertEqual(self.took(t, self.opp), 90)
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(1 for e in (e1, e2) if e in hand), 1)
        self.assertEqual(len(c.children), 1)

    # --- Skeledirge: Unaware / Torcherto -------------------------------------
    async def test_unaware_blocks_poison_damage_still_done(self):
        t = Table(self)
        s = self.neutral(t.put(SKELEDIRGE, P1, 'active'))
        opp = self.neutral(t.put(HAUNTER, P2, 'active'), 400)
        t.energy(opp, P)
        t.next_turn()
        await t.attack(opp, 'Sinister Fog', pid=P2)
        self.assertNotIn(POISONED, t.conditions(s))

    async def test_unaware_damage_is_not_prevented(self):
        t = Table(self)
        s = self.neutral(t.put(SKELEDIRGE, P1, 'active'))
        opp = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(opp, D)
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertEqual(self.took(t, s), 20)

    async def test_unaware_on_bench_blocks_counters_neighbour_hit(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        s = self.neutral(t.put(SKELEDIRGE, P1, 'bench'))
        other = self.neutral(t.put(self.filler, P1, 'bench'))
        opp = self.neutral(t.put(HAUNTER, P2, 'active'), 400)
        t.energy(opp, P)
        t.next_turn()
        await t.attack(opp, 'Sinister Fog', pid=P2)
        self.assertEqual(self.took(t, s), 0)
        self.assertEqual(self.took(t, other), 10)

    async def test_unaware_blocks_damage_counters_from_attack(self):
        # Damage counters placed by an attack are an effect, not damage.
        t = Table(self)
        n = t.put(NINETALES, P1, 'active')
        t.energy(n, F, 2)
        s = self.neutral(t.put(SKELEDIRGE, P2, 'active'))
        await t.attack(n, 'Nine-Tailed Dance')
        self.assertEqual(self.took(t, s), 0)

    # FIXED (was BUG): Torcherto counts only the attacker's own Bench (bw_era._formula_damage_core generic 'benched pokémon' branch)
    async def test_torcherto_counts_both_benches(self):
        t = self.table()
        s = t.put(SKELEDIRGE, P1, 'active')
        t.energy(s, F, 2)
        for _ in range(2):
            t.put(self.filler, P1, 'bench')
        for _ in range(3):
            self.neutral(t.put(self.filler, P2, 'bench'))
        await t.attack(s, 'Torcherto')
        self.assertEqual(self.took(t, self.opp), 60 + 20 * 5)

    async def test_torcherto_no_bench_base_damage(self):
        t = self.table()
        s = t.put(SKELEDIRGE, P1, 'active')
        t.energy(s, F, 2)
        await t.attack(s, 'Torcherto')
        self.assertEqual(self.took(t, self.opp), 60)

    # --- Ponyta: Collect -----------------------------------------------------
    async def test_collect_draws_one(self):
        t = self.table()
        p = t.put(PONYTA, P1, 'active')
        t.energy(p, F)
        deck = len(t.zone(P1, 'deck'))
        hand = len(t.zone(P1, 'hand'))
        await t.attack(p, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 1)
        self.assertEqual(len(t.zone(P1, 'deck')), deck - 1)
        self.assertEqual(self.took(t, self.opp), 0)

    # --- Rapidash: Hurried Gait ----------------------------------------------
    async def test_hurried_gait_draws_once_per_turn(self):
        t = self.table()
        r = t.put(RAPIDASH, P1, 'bench')
        t.put(self.filler, P1, 'active')
        hand = len(t.zone(P1, 'hand'))
        self.assertIsNotNone(t.ability_offer(r, 'Hurried Gait'))
        await t.use(r, 'Hurried Gait')
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 1)
        self.assertIsNone(t.ability_offer(r, 'Hurried Gait'))

    async def test_hurried_gait_two_rapidash_each_once(self):
        t = self.table()
        r1 = t.put(RAPIDASH, P1, 'active')
        r2 = t.put(RAPIDASH, P1, 'bench')
        hand = len(t.zone(P1, 'hand'))
        await t.use(r1, 'Hurried Gait')
        await t.use(r2, 'Hurried Gait')
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 2)

    async def test_hurried_gait_available_again_next_turn(self):
        t = self.table()
        r = t.put(RAPIDASH, P1, 'active')
        await t.use(r, 'Hurried Gait')
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.ability_offer(r, 'Hurried Gait'))

    async def test_hurried_gait_empty_deck_not_usable_or_harmless(self):
        t = self.table()
        r = t.put(RAPIDASH, P1, 'active')
        area = t.board.find_player_area(P1, 'deck')
        for c in list(area.children):
            area.remove_child(c)
        offer = t.ability_offer(r, 'Hurried Gait')
        if offer is not None:
            await t.do(offer)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Vulpix: Take Down ---------------------------------------------------
    async def test_take_down_self_damage(self):
        t = self.table()
        v = self.neutral(t.put(VULPIX, P1, 'active'))
        t.energy(v, F)
        await t.attack(v, 'Take Down')
        self.assertEqual(self.took(t, self.opp), 30)
        self.assertEqual(self.took(t, v), 10)

    # --- Ninetales: Nine-Tailed Dance ----------------------------------------
    async def test_nine_tailed_dance_benched_target_and_lock(self):
        t = self.table()
        n = t.put(NINETALES, P1, 'active')
        t.energy(n, F, 2)
        b = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        t.pokemon = lambda cands, prompt: b
        await t.attack(n, 'Nine-Tailed Dance')
        self.assertEqual(self.took(t, b), 90)
        self.assertEqual(self.took(t, self.opp), 0)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(n, 'Nine-Tailed Dance'))
        self.assertIsNone(t.attack_offer(n, 'Will-O-Wisp'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(n, 'Will-O-Wisp'))

    async def test_nine_tailed_dance_counters_ignore_weakness(self):
        t = Table(self)
        n = t.put(NINETALES, P1, 'active')
        t.energy(n, F, 2)
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        opp.set_attribute(AttrID.HP, 400)
        opp._start_hp = 400
        await t.attack(n, 'Nine-Tailed Dance')
        self.assertEqual(self.took(t, opp), 90)


if __name__ == '__main__':
    unittest.main()
