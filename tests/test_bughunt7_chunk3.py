"""Bug hunt round 7, chunk 3: Morpeko PAR 121, Risky Ruins MEG 127,
Dunsparce TEF 128, Wailmer CES 39, Electabuzz SCR 46, Binacle FCO 22,
Barbaracle FCO 23, Hisuian Basculegion LOR 45, Kyogre CEL 3, Tapu Koko DAA 61,
Kyogre MEG 34, Roselia DRX 12 / UPR 4 / TEF 8, Ditto MEW 132."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, POISONED, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W, F, D, G, L = (PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.DARKNESS,
                 PokemonTypes.GRASS, PokemonTypes.LIGHTNING)
MORPEKO = 'SV4.Morpeko_121'
RUINS = 'ME1.RiskyRuins_127'
DUNSPARCE = 'SV05.Dunsparce_128'
WAILMER = 'SM7.Wailmer_39'
ELECTABUZZ = 'SV07.Electabuzz_46'          # SCR 46 (chunk path said SWSH9)
BINACLE, BARBARACLE = 'XY10.Binacle_22', 'XY10.Barbaracle_23'
BASCULEGION = 'SWSH11.HisuianBasculegion_45'
KYOGRE_CEL, KYOGRE_MEG = 'CEL25.Kyogre_3', 'ME1.Kyogre_34'
TAPU_KOKO = 'SWSH3.TapuKoko_61'
ROSELIA_DRX, ROSELIA_UPR, ROSELIA_TEF = 'BW6.Roselia_12', 'SM5.Roselia_4', 'SV05.Roselia_8'
DITTO = 'SV035.Ditto_132'
SABLEYE = 'SV2.Sableye_136'                # Unseen Claw 20 for [D]
SPECIAL = 'SWSH9.DoubleTurboEnergy_151'
OTHER_STADIUM = 'ME1.RiskyRuins_127'


class Chunk3Round7(unittest.IsolatedAsyncioTestCase):
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

    def is_energy(self, card, kind):
        return card.archetype_id == self.energies[kind.value] or \
            str(card.archetype_id).lower() == self.energies[kind.value].lower()

    # --- Morpeko: In a Hungry Hurry / Energizer Wheel ----------------------
    async def test_morpeko_no_energy_free_retreat(self):
        t = self.table()
        m = t.put(MORPEKO, P1, 'active')
        self.assertEqual(t.retreat(m), 0)

    async def test_morpeko_with_energy_pays_retreat(self):
        t = self.table()
        m = t.put(MORPEKO, P1, 'active')
        t.energy(m, D)
        self.assertEqual(t.retreat(m), 1)

    async def test_energizer_wheel_moves_two_darkness(self):
        t = self.table()
        m = t.put(MORPEKO, P1, 'active')
        dark = t.energy(m, D, 2)
        water = t.energy(m, W)
        bench = t.put(self.filler, P1, 'bench')
        await t.attack(m, 'Energizer Wheel')
        self.assertEqual(self.took(t, self.opp), 70)
        self.assertEqual({c.entity_id for c in bench.children},
                         {c.entity_id for c in dark})
        self.assertIs(water.parent, m)

    # --- Risky Ruins ------------------------------------------------------
    async def test_risky_ruins_damages_benched_basic(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.stadium(RUINS, P2)
        mon = t.put(TAPU_KOKO, P1, 'hand')
        await t.play(mon)
        self.assertEqual(mon.parent, t.board.find_player_area(P1, 'bench'))
        self.assertEqual(t.damage(mon), 20)

    async def test_risky_ruins_spares_darkness_basic(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.stadium(RUINS, P1)
        mon = t.put(MORPEKO, P1, 'hand')
        await t.play(mon)
        self.assertEqual(mon.parent, t.board.find_player_area(P1, 'bench'))
        self.assertEqual(t.damage(mon), 0)

    # --- Dunsparce: Dig ---------------------------------------------------
    async def _dig(self, heads):
        t = Table(self)
        d = self.neutral(t.put(DUNSPARCE, P1, 'active'))
        t.energy(d, W, 2)
        opp = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(opp, D)
        t.heads = heads
        await t.attack(d, 'Dig')
        self.assertEqual(self.took(t, opp), 30)
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        return t, d

    async def test_dig_heads_prevents_damage(self):
        t, d = await self._dig(True)
        self.assertEqual(t.damage(d), 0)

    async def test_dig_tails_no_protection(self):
        t, d = await self._dig(False)
        self.assertEqual(t.damage(d), 20)

    # --- Wailmer: Wave Swallower -----------------------------------------
    @staticmethod
    async def _until_tails(t, w, heads):
        async def run(ctx, title=''):
            return heads
        with patch.object(EffectContext, 'flip_until_tails', run):
            await t.attack(w, 'Wave Swallower')

    async def test_wave_swallower_heals_50_per_heads(self):
        t = self.table()
        w = t.put(WAILMER, P1, 'active', hp=20)
        t.energy(w, W, 3)
        await self._until_tails(t, w, 1)
        self.assertEqual(self.took(t, self.opp), 50)
        self.assertEqual(t.hp(w), 70)

    async def test_wave_swallower_tails_first_no_heal(self):
        t = self.table()
        w = t.put(WAILMER, P1, 'active', hp=20)
        t.energy(w, W, 3)
        await self._until_tails(t, w, 0)
        self.assertEqual(t.hp(w), 20)

    # --- Electabuzz SCR: Collect -----------------------------------------
    async def test_collect_draws_one(self):
        t = self.table()
        e = t.put(ELECTABUZZ, P1, 'active')
        t.energy(e, L)
        before = len(t.zone(P1, 'hand'))
        deck = len(t.zone(P1, 'deck'))
        await t.attack(e, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), before + 1)
        self.assertEqual(len(t.zone(P1, 'deck')), deck - 1)
        self.assertEqual(self.took(t, self.opp), 0)

    # --- Binacle: Swing Around -------------------------------------------
    async def test_swing_around_two_heads(self):
        t = self.table()
        b = t.put(BINACLE, P1, 'active')
        t.energy(b, W, 2)
        t.heads = True
        await t.attack(b, 'Swing Around')
        self.assertEqual(self.took(t, self.opp), 50)

    async def test_swing_around_no_heads(self):
        t = self.table()
        b = t.put(BINACLE, P1, 'active')
        t.energy(b, W, 2)
        t.heads = False
        await t.attack(b, 'Swing Around')
        self.assertEqual(self.took(t, self.opp), 10)

    # --- Barbaracle: Hand Block ------------------------------------------
    def hand_block_board(self, stadium_owner):
        t = Table(self)
        t.put(BARBARACLE, P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        if stadium_owner is not None:
            t.stadium(OTHER_STADIUM, stadium_owner)
        special = t.put(SPECIAL, P2, 'hand')
        basic = t.put(t.basic_energy(W), P2, 'hand')
        t.next_turn()
        return t, opp, special, basic

    # BUG: Hand Block never applies; bw_era._BWTextPassive.blocks_energy_attachment
    # looks for the title "hand block" inside the printed text, which lacks it.

    async def test_hand_block_with_own_stadium(self):
        t, opp, special, basic = self.hand_block_board(P1)
        self.assertFalse(t.can(special, 'DefaultEnergyPlayAbility', pid=P2))
        self.assertTrue(t.can(basic, 'DefaultEnergyPlayAbility', pid=P2))

    async def test_hand_block_off_with_opponents_stadium(self):
        t, opp, special, basic = self.hand_block_board(P2)
        self.assertTrue(t.can(special, 'DefaultEnergyPlayAbility', pid=P2))

    async def test_hand_block_off_without_stadium(self):
        t, opp, special, basic = self.hand_block_board(None)
        self.assertTrue(t.can(special, 'DefaultEnergyPlayAbility', pid=P2))

    async def test_hand_block_does_not_lock_owner(self):
        t = Table(self)
        t.put(BARBARACLE, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.stadium(OTHER_STADIUM, P1)
        special = t.put(SPECIAL, P1, 'hand')
        self.assertTrue(t.can(special, 'DefaultEnergyPlayAbility'))

    # --- Hisuian Basculegion -----------------------------------------------
    async def test_upstream_spirits_counts_basic_only_and_shuffles(self):
        t = self.table()
        b = t.put(BASCULEGION, P1, 'active')
        basics = [t.put(t.basic_energy(W), P1, 'discard'),
                  t.put(t.basic_energy(F), P1, 'discard'),
                  t.put(t.basic_energy(D), P1, 'discard')]
        special = t.put(SPECIAL, P1, 'discard')
        await t.attack(b, 'Upstream Spirits')
        self.assertEqual(self.took(t, self.opp), 60)
        deck = t.zone(P1, 'deck')
        for c in basics:
            self.assertIn(c, deck)
        self.assertIn(special, t.zone(P1, 'discard'))

    async def test_upstream_spirits_empty_discard(self):
        t = self.table()
        b = t.put(BASCULEGION, P1, 'active')
        await t.attack(b, 'Upstream Spirits')
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_water_shot_discards_one_energy(self):
        t = self.table()
        b = t.put(BASCULEGION, P1, 'active')
        t.energy(b, W, 2)
        await t.attack(b, 'Water Shot')
        self.assertEqual(self.took(t, self.opp), 70)
        self.assertEqual(len(b.children), 1)

    # --- Kyogre CEL: Aqua Storm ------------------------------------------
    async def test_aqua_storm_hits_two_benched(self):
        t = self.table()
        k = t.put(KYOGRE_CEL, P1, 'active')
        t.energy(k, W, 3)
        t.deck(P1, [t.basic_energy(W), t.basic_energy(F)])
        b1 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        b2 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        b3 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        mine = self.neutral(t.put(self.filler, P1, 'bench'))
        before = len(t.zone(P1, 'discard'))
        await t.attack(k, 'Aqua Storm')
        self.assertEqual(len(t.zone(P1, 'discard')), before + 5)
        self.assertEqual((self.took(t, b1), self.took(t, b2), self.took(t, b3)), (100, 100, 0))
        self.assertEqual(self.took(t, self.opp), 0)
        self.assertEqual(self.took(t, mine), 0)

    async def test_aqua_storm_no_energy_milled(self):
        t = self.table()
        k = t.put(KYOGRE_CEL, P1, 'active')
        t.energy(k, W, 3)
        b1 = self.neutral(t.put(self.filler, P2, 'bench'), 300)
        await t.attack(k, 'Aqua Storm')
        self.assertEqual(self.took(t, b1), 0)

    # --- Tapu Koko: Allure ---------------------------------------------
    async def test_allure_draws_two(self):
        t = self.table()
        k = t.put(TAPU_KOKO, P1, 'active')
        t.energy(k, W)
        before = len(t.zone(P1, 'hand'))
        await t.attack(k, 'Allure')
        self.assertEqual(len(t.zone(P1, 'hand')), before + 2)
        self.assertEqual(self.took(t, self.opp), 0)

    # --- Kyogre MEG: Riptide / Swirling Waves ------------------------------
    async def test_riptide_counts_basic_water_only_and_shuffles(self):
        t = self.table()
        k = t.put(KYOGRE_MEG, P1, 'active')
        t.energy(k, W)
        waters = [t.put(t.basic_energy(W), P1, 'discard') for _ in range(2)]
        fire = t.put(t.basic_energy(F), P1, 'discard')
        await t.attack(k, 'Riptide')
        self.assertEqual(self.took(t, self.opp), 40)
        for c in waters:
            self.assertIn(c, t.zone(P1, 'deck'))
        self.assertIn(fire, t.zone(P1, 'discard'))

    async def test_swirling_waves_discards_two(self):
        t = self.table()
        k = t.put(KYOGRE_MEG, P1, 'active')
        t.energy(k, W, 3)
        await t.attack(k, 'Swirling Waves')
        self.assertEqual(self.took(t, self.opp), 130)
        self.assertEqual(len(k.children), 1)

    # --- Roselia DRX: Double Whip / Relaxing Fragrance ---------------------
    async def test_relaxing_fragrance_heals_and_clears(self):
        t = self.table()
        r = t.put(ROSELIA_DRX, P1, 'active', hp=20)
        t.energy(r, G)
        r.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED, BURNED])
        await t.attack(r, 'Relaxing Fragrance')
        self.assertEqual(t.hp(r), 50)
        self.assertEqual(t.conditions(r), set())
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_relaxing_fragrance_no_overheal(self):
        t = self.table()
        r = t.put(ROSELIA_DRX, P1, 'active', hp=60)
        t.energy(r, G)
        await t.attack(r, 'Relaxing Fragrance')
        self.assertEqual(t.hp(r), 70)

    async def test_double_whip_counts_heads(self):
        t = self.table()
        r = t.put(ROSELIA_DRX, P1, 'active')
        t.energy(r, G)
        seq = iter([True, False])
        t.heads = lambda title: next(seq)
        await t.attack(r, 'Double Whip')
        self.assertEqual(self.took(t, self.opp), 10)

    # --- Roselia UPR: Petal Dance ----------------------------------------
    async def test_petal_dance_three_heads_and_confused(self):
        t = self.table()
        r = t.put(ROSELIA_UPR, P1, 'active')
        t.energy(r, G, 2)
        t.heads = True
        await t.attack(r, 'Petal Dance')
        self.assertEqual(self.took(t, self.opp), 90)
        self.assertIn(CONFUSED, t.conditions(r))
        self.assertNotIn(CONFUSED, t.conditions(self.opp))

    async def test_petal_dance_tails_still_confused(self):
        t = self.table()
        r = t.put(ROSELIA_UPR, P1, 'active')
        t.energy(r, G, 2)
        t.heads = False
        await t.attack(r, 'Petal Dance')
        self.assertEqual(self.took(t, self.opp), 0)
        self.assertIn(CONFUSED, t.conditions(r))

    # --- Roselia TEF: Poison Point ---------------------------------------
    async def _poison_point(self, zone):
        t = Table(self)
        r = self.neutral(t.put(ROSELIA_TEF, P1, zone), 300)
        if zone == 'bench':
            t.put(self.filler, P1, 'active')
        opp = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(opp, D)
        return t, r, opp

    async def test_poison_point_active(self):
        t, r, opp = await self._poison_point('active')
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertIn(POISONED, t.conditions(opp))

    async def test_poison_point_benched_roselia_does_nothing(self):
        t, r, opp = await self._poison_point('bench')
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertNotIn(POISONED, t.conditions(opp))

    # --- Ditto: Transformative Start -------------------------------------
    def ditto_board(self, zone='active', turn=1, deck=(TAPU_KOKO,)):
        t = Table(self)
        t.state.turn_number = turn
        d = t.put(DITTO, P1, zone)
        if zone == 'bench':
            t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        cards = t.deck(P1, list(deck))
        return t, d, cards

    async def test_transformative_start_replaces_ditto(self):
        t, d, cards = self.ditto_board()
        energy = t.energy(d, W)
        self.assertIsNotNone(t.ability_offer(d, 'Transformative Start'))
        await t.use(d, 'Transformative Start')
        active = t.active(P1)
        self.assertIs(active, cards[0])
        self.assertIn(d, t.zone(P1, 'discard'))
        self.assertIn(energy, t.zone(P1, 'discard'))

    async def test_transformative_start_bench_not_offered(self):
        t, d, cards = self.ditto_board(zone='bench')
        self.assertIsNone(t.ability_offer(d, 'Transformative Start'))

    async def test_transformative_start_not_after_first_turn(self):
        t, d, cards = self.ditto_board(turn=3)
        self.assertIsNone(t.ability_offer(d, 'Transformative Start'))

    async def test_transformative_start_second_player_first_turn(self):
        t2 = Table(self)
        t2.state.turn_number = 2
        t2.put(self.filler, P1, 'active')
        d2 = t2.put(DITTO, P2, 'active')
        koko = t2.deck(P2, [TAPU_KOKO])[0]
        t2.state.active_player_id = P2
        self.assertIsNotNone(t2.ability_offer(d2, 'Transformative Start', pid=P2))
        await t2.use(d2, 'Transformative Start', pid=P2)
        self.assertIs(t2.active(P2), koko)

    async def test_transformative_start_excludes_ditto(self):
        t, d, cards = self.ditto_board(deck=(DITTO, TAPU_KOKO))
        seen = []

        def pick(cards_, count, prompt, display):
            seen.extend(cards_)
            return [c for c in cards_][:1]
        t.picks = pick
        await t.use(d, 'Transformative Start')
        names = {c.archetype_id for c in seen}
        self.assertNotIn(cards[0].archetype_id, names)
        self.assertIs(t.active(P1), cards[1])


if __name__ == '__main__':
    unittest.main()
