"""Bug hunt, deck 6 (Lightning): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

L, W, F = PokemonTypes.LIGHTNING, PokemonTypes.WATER, PokemonTypes.FIRE
BLITZLE, ZEBSTRIKA = 'SV08.Blitzle_62', 'SM8.Zebstrika_82'
ELECTABUZZ, ELECTIVIRE, MAGMORTAR = 'XY12.Electabuzz_41', 'SWSH9.Electivire_47', 'SWSH9.Magmortar_20'
MAREEP, FLAAFFY = 'SM8.Mareep_76', 'SWSH7.Flaaffy_55'
TYNAMO, EELEKTRIK = 'ME2PT5.Tynamo_59', 'ME2PT5.Eelektrik_60'
MORPEKO, REGIELEKI = 'SWSH2.Morpeko_73', 'SWSH7.Regieleki_60'
KOKO, ZAPDOS = 'Promo_SM.TapuKoko_30', 'SM9.Zapdos_40'
SPEED = 'SWSH2.SpeedLightningEnergy_173'
SWITCH = 'SV1.Switch_194'


class Deck6Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, card, hp=400):
        card.set_attribute(AttrID.WEAKNESS_TYPES, [])
        card.set_attribute(AttrID.RESISTANCE_TYPES, [])
        card.set_attribute(AttrID.HP, hp)
        return card

    def table(self, opp=None):
        t = Table(self)
        self.opp = self.neutral(t.put(opp or self.filler, P2, 'active'))
        return t

    # --- Blitzle: Add On ------------------------------------------------
    async def test_blitzle_add_on_draws_one(self):
        t = self.table()
        b = t.put(BLITZLE, P1, 'active')
        t.energy(b, L)
        await t.attack(b, 'Add On')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Zebstrika: Sprint ----------------------------------------------
    async def test_zebstrika_sprint_discard_hand_draw_four_once(self):
        t = self.table()
        z = t.put(ZEBSTRIKA, P1, 'bench')
        t.put(self.filler, P1, 'active')
        old = [t.put(self.filler, P1, 'hand') for _ in range(2)]
        await t.use(z, 'Sprint')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 4)
        for c in old:
            self.assertIn(c, t.zone(P1, 'discard'))
        self.assertIsNone(t.ability_offer(z, 'Sprint'))

    async def test_zebstrika_sprint_with_empty_hand_still_draws(self):
        t = self.table()
        z = t.put(ZEBSTRIKA, P1, 'active')
        await t.use(z, 'Sprint')
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    # --- Electabuzz -------------------------------------------------------
    async def test_electabuzz_thunder_shock(self):
        for heads in (True, False):
            t = self.table()
            e = t.put(ELECTABUZZ, P1, 'active')
            t.energy(e, L)
            t.heads = heads
            await t.attack(e, 'Thunder Shock')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 10)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    async def test_electabuzz_thunder_punch(self):
        for heads, dealt, self_dmg in ((True, 40, 0), (False, 30, 10)):
            t = self.table()
            e = t.put(ELECTABUZZ, P1, 'active')
            t.energy(e, L, 2)
            t.heads = heads
            await t.attack(e, 'Thunder Punch')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dealt)
                self.assertEqual(t.damage(e), self_dmg)

    # --- Electivire -----------------------------------------------------------
    async def test_explosive_bolt_needs_damaged_benched_magmortar(self):
        for damaged, where, dealt in ((True, 'bench', 120), (False, 'bench', 30), (True, 'opp', 30)):
            t = self.table()
            e = t.put(ELECTIVIRE, P1, 'active')
            t.energy(e, L)
            mag = t.put(MAGMORTAR, P1 if where == 'bench' else P2, 'bench')
            if damaged:
                mag.set_attribute(AttrID.HP, t.hp(mag) - 10)
            await t.attack(e, 'Explosive Bolt')
            with self.subTest(damaged=damaged, where=where):
                self.assertEqual(400 - t.hp(self.opp), dealt)

    async def test_high_voltage_current_hits_all_no_bench_weakness(self):
        t = self.table()
        e = t.put(ELECTIVIRE, P1, 'active')
        t.energy(e, L, 3)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        mine = t.put(self.filler, P1, 'bench')
        before = t.hp(bench)
        await t.attack(e, 'High-Voltage Current')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(before - t.hp(bench), 50)
        self.assertEqual(t.damage(mine), 0)

    # --- Mareep -----------------------------------------------------------
    async def test_mareep_thunder_shock(self):
        t = self.table()
        m = t.put(MAREEP, P1, 'active')
        t.energy(m, L)
        t.heads = True
        await t.attack(m, 'Thunder Shock')
        self.assertIn(PARALYZED, t.conditions(self.opp))

    # --- Flaaffy / Eelektrik: Dynamotor -------------------------------
    async def test_flaaffy_dynamotor_to_bench_once(self):
        t = self.table()
        f = t.put(FLAAFFY, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        energy = t.put(t.basic_energy(L), P1, 'discard')
        t.put(t.basic_energy(L), P1, 'discard')
        seen = {}
        t.pokemon = lambda c, p: (seen.setdefault('c', list(c)), c[0])[1]
        await t.use(f, 'Dynamotor')
        self.assertNotIn(f, seen['c'])                   # Active isn't a target
        self.assertEqual(len(t.board.attached_energies(bench)), 1)
        self.assertIsNone(t.ability_offer(f, 'Dynamotor'))

    async def test_flaaffy_dynamotor_not_offered_without_bench_or_energy(self):
        t = self.table()
        f = t.put(FLAAFFY, P1, 'active')
        t.put(t.basic_energy(L), P1, 'discard')
        self.assertIsNone(t.ability_offer(f, 'Dynamotor'))     # no Bench
        t = self.table()
        f = t.put(FLAAFFY, P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.put(t.basic_energy(W), P1, 'discard')
        self.assertIsNone(t.ability_offer(f, 'Dynamotor'))     # no Lightning Energy

    async def test_flaaffy_dynamotor_special_lightning_not_in_discard(self):
        # Speed Lightning provides Lightning only while attached, so it is not
        # a Lightning Energy card in the discard pile.
        t = self.table()
        f = t.put(FLAAFFY, P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.put(SPEED, P1, 'discard')
        self.assertIsNone(t.ability_offer(f, 'Dynamotor'))

    async def test_eelektrik_dynamotor_basic_lightning_to_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        e = t.put(EELEKTRIK, P1, 'bench')
        t.put(t.basic_energy(L), P1, 'discard')
        await t.use(e, 'Dynamotor')
        self.assertEqual(len(t.board.attached_energies(e)), 1)
        self.assertIsNone(t.ability_offer(e, 'Dynamotor'))

    async def test_eelektrik_dynamotor_rejects_special_lightning(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        e = t.put(EELEKTRIK, P1, 'bench')
        t.put(SPEED, P1, 'discard')
        self.assertIsNone(t.ability_offer(e, 'Dynamotor'))

    # --- Tynamo: Hold Still ----------------------------------------------
    async def test_tynamo_hold_still_heals_10(self):
        t = self.table()
        ty = t.put(TYNAMO, P1, 'active', hp=20)
        t.energy(ty, L)
        await t.attack(ty, 'Hold Still')
        self.assertEqual(t.hp(ty), 30)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Morpeko --------------------------------------------------------
    async def test_morpeko_torment_locks_attack_next_turn_only(self):
        t = self.table(MAREEP)                 # Mareep has a single attack
        t.energy(self.opp, L)
        m = t.put(MORPEKO, P1, 'active')
        t.energy(m, L)
        await t.attack(m, 'Torment')
        self.assertEqual(400 - t.hp(self.opp), 20)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, 'Thunder Shock', P2))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, 'Thunder Shock', P2))

    async def test_morpeko_spark_bench_snipe(self):
        t = self.table()
        m = t.put(MORPEKO, P1, 'active')
        t.energy(m, L, 2)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        before = t.hp(bench)
        await t.attack(m, 'Spark')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(before - t.hp(bench), 20)

    # --- Regieleki: Teraspark -------------------------------------------
    async def test_teraspark_discards_lightning_only_and_hits_two_bench(self):
        t = self.table()
        r = t.put(REGIELEKI, P1, 'active')
        t.energy(r, L, 2)
        fire = t.energy(r, F)
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(self.filler, P2, 'bench')
        b3 = t.put(self.filler, P2, 'bench')
        order = iter([b1, b2])
        t.pokemon = lambda c, p: next(order)
        await t.attack(r, 'Teraspark')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertEqual(t.board.attached_energies(r), [fire])
        self.assertEqual((t.damage(b1), t.damage(b2), t.damage(b3)), (40, 40, 0))

    # --- Tapu Koko: Flying Flip -----------------------------------------
    async def test_flying_flip_20_each_no_bench_weakness(self):
        t = self.table()
        k = t.put(KOKO, P1, 'active')
        t.energy(k, L, 2)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        mine = t.put(self.filler, P1, 'bench')
        before = t.hp(bench)
        await t.attack(k, 'Flying Flip')
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertEqual(before - t.hp(bench), 20)
        self.assertEqual(t.damage(mine), 0)

    # --- Zapdos: Thunderous Assault -------------------------------------
    async def test_thunderous_assault_after_switch_from_bench(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        t.put(self.filler, P1, 'active')
        z = t.put(ZAPDOS, P1, 'bench')
        t.energy(z, L)
        t.pokemon = lambda c, p: z if z in c else c[0]
        await t.play(t.put(SWITCH, P1, 'hand'))
        self.assertIs(t.active(P1), z)
        await t.attack(z, 'Thunderous Assault')
        self.assertEqual(400 - t.hp(self.opp), 80)      # no Weakness doubling

    async def test_thunderous_assault_already_active(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        z = t.put(ZAPDOS, P1, 'active')
        t.energy(z, L)
        await t.attack(z, 'Thunderous Assault')
        self.assertEqual(400 - t.hp(self.opp), 10)


if __name__ == "__main__":
    unittest.main()
