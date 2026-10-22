"""Bug hunt round 7, chunk 6: Special Red Card, Zapdos (TWM/PGO), Bronzor/
Bronzong, Mudkip, Dreepy, Regieleki, Zacian (CRZ/30C), Articuno (ROS/PGO/SIT),
Torchic, Slowpoke -- each card checked against its text, including the cases
where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

PSY, WATER, LIGHT, METAL = (PokemonTypes.PSYCHIC, PokemonTypes.WATER,
                            PokemonTypes.LIGHTNING, PokemonTypes.METAL)
FIRE = PokemonTypes.FIRE

SRC = 'ME4.SpecialRedCard_82'
ZAPDOS_TWM, ZAPDOS_PGO = 'SV06.Zapdos_65', 'PGO.Zapdos_29'
BRONZOR, BRONZONG = 'SV05.Bronzor_68', 'SV05.Bronzong_69'
MUDKIP = 'SM7.Mudkip_32'
DREEPY = 'SWSH12.Dreepy_87'
REGIELEKI = 'SWSH10.Regieleki_51'
ZACIAN_CRZ, ZACIAN_30C = 'CZ.Zacian_94', 'ME55.Zacian_106'
ARTICUNO_ROS, ARTICUNO_PGO, ARTICUNO_SIT = 'XY6.Articuno_17', 'PGO.Articuno_24', 'SWSH12.Articuno_36'
TORCHIC = 'SV10.Torchic_40'
SLOWPOKE = 'TwentiethAnn.Slowpoke_32'
SHINX, LUXIO = 'SWSH5.Shinx_46', 'SWSH5.Luxio_47'
SOBBLE = 'Promo_SWSH.Sobble_3'           # Basic Water, Bind 20
WEEZING = 'SWSH2.GalarianWeezing_113'


class Chunk6(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind, count, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def dealt(self, t):
        return 400 - t.hp(self.opp)

    def is_energy_of(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    # --- Special Red Card CRI 82 ---------------------------------------------
    async def test_special_red_card_gate_boundary(self):
        for prizes, ok in ((3, True), (4, False)):
            t = self.table()
            t.put(self.filler, P1, 'active')
            src = t.put(SRC, P1, 'hand')
            t.set_prizes(P2, prizes)
            with self.subTest(prizes=prizes):
                self.assertEqual(t.can(src, 'UseTrainerCard'), ok)

    async def test_special_red_card_gate_uses_opponents_prizes(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        src = t.put(SRC, P1, 'hand')
        t.set_prizes(P1, 1)          # my prizes low, opponent at 6
        self.assertFalse(t.can(src, 'UseTrainerCard'))

    async def test_special_red_card_hand_to_bottom_draw_3(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.set_prizes(P2, 2)
        src = t.put(SRC, P1, 'hand')
        old = [t.put(self.filler, P2, 'hand') for _ in range(5)]
        top = t.deck(P2, [self.item, self.item, self.item])
        mine_before = len(t.zone(P1, 'hand'))
        await t.play(src)
        hand = t.zone(P2, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertEqual(set(c.entity_id for c in hand), set(c.entity_id for c in top))
        deck = t.zone(P2, 'deck')
        self.assertEqual(set(c.entity_id for c in deck[:5]), set(c.entity_id for c in old))
        self.assertEqual(len(t.zone(P1, 'hand')), mine_before - 1)
        self.assertIn(src, t.zone(P1, 'discard'))

    async def test_special_red_card_empty_hand_no_draw(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.set_prizes(P2, 2)
        src = t.put(SRC, P1, 'hand')
        deck_before = len(t.zone(P2, 'deck'))
        if t.can(src, 'UseTrainerCard'):
            await t.play(src)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before)

    # --- Zapdos TWM 65 -------------------------------------------------------
    async def test_zapdos_twm_thunder_wave(self):
        for heads in (True, False):
            t = self.table()
            z = self.mine(t, ZAPDOS_TWM, LIGHT, 1)
            t.heads = heads
            await t.attack(z, 'Thunder Wave')
            with self.subTest(heads=heads):
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)
                self.assertEqual(self.dealt(t), 0)

    async def test_zapdos_twm_thunderbolt_discards_all_energy(self):
        t = self.table()
        z = self.mine(t, ZAPDOS_TWM, LIGHT, 4)
        bench = t.put(self.filler, P1, 'bench')
        t.energy(bench, LIGHT, 1)
        await t.attack(z, 'Thunderbolt')
        self.assertEqual(self.dealt(t), 190)
        self.assertEqual(len(t.board.attached_energies(z)), 0)
        self.assertEqual(len(t.board.attached_energies(bench)), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 4)

    # --- Zapdos PGO 29: Lightning Symbol --------------------------------------
    async def test_zapdos_pgo_boosts_basic_lightning(self):
        t = self.table()
        t.put(ZAPDOS_PGO, P1, 'bench')
        shinx = self.mine(t, SHINX, LIGHT, 2)
        await t.attack(shinx, 'Rear Kick')
        self.assertEqual(self.dealt(t), 30)

    async def test_zapdos_pgo_not_zapdos_or_stage1(self):
        t = self.table()
        sym = self.mine(t, ZAPDOS_PGO, LIGHT, 3)
        await t.attack(sym, 'Electric Ball')
        self.assertEqual(self.dealt(t), 110)        # Zapdos itself excluded
        t2 = self.table()
        t2.put(ZAPDOS_PGO, P1, 'bench')
        luxio = self.mine(t2, LUXIO, LIGHT, 2)
        await t2.attack(luxio, 'Head Bolt')
        self.assertEqual(400 - t2.hp(self.opp), 50)  # Stage 1 excluded
        t3 = self.table()
        t3.put(ZAPDOS_PGO, P1, 'bench')
        z = self.mine(t3, ZAPDOS_TWM, LIGHT, 3)
        await t3.attack(z, 'Thunderbolt')
        self.assertEqual(400 - t3.hp(self.opp), 190)  # any Zapdos excluded

    async def test_zapdos_pgo_not_to_bench(self):
        t = self.table()
        t.put(ZAPDOS_PGO, P1, 'bench')
        reg = self.mine(t, REGIELEKI, LIGHT, 3)
        target = t.put(self.filler, P2, 'bench')
        target.set_attribute(AttrID.HP, 400)
        await t.attack(reg, 'Targeted Bolt')
        self.assertEqual(400 - t.hp(target), 120)

    async def test_zapdos_pgo_opponents_side_unaffected(self):
        t = self.table(opp=SHINX)
        t.put(ZAPDOS_PGO, P1, 'bench')
        me = self.mine(t, self.filler, WATER, 0)
        me.set_attribute(AttrID.HP, 300)
        t.energy(self.opp, LIGHT, 2)
        t.next_turn()
        await t.attack(self.opp, 'Rear Kick', pid=P2)
        self.assertEqual(300 - t.hp(me), 20)

    async def test_zapdos_pgo_ability_locked(self):
        t = self.table(opp=WEEZING)
        t.put(ZAPDOS_PGO, P1, 'bench')
        shinx = self.mine(t, SHINX, LIGHT, 2)
        await t.attack(shinx, 'Rear Kick')
        self.assertEqual(self.dealt(t), 20)

    # --- Bronzor TEF 68: Mirror Attack ----------------------------------------
    async def test_bronzor_mirror_attack(self):
        for opp, expected in ((DREEPY, 40), (None, 10)):
            t = self.table(opp=opp)
            b = self.mine(t, BRONZOR, PSY, 1)
            await t.attack(b, 'Mirror Attack')
            with self.subTest(opp=opp):
                self.assertEqual(self.dealt(t), expected)

    async def test_bronzor_mirror_attack_ignores_psychic_bench(self):
        t = self.table()
        t.put(DREEPY, P2, 'bench')
        b = self.mine(t, BRONZOR, PSY, 1)
        await t.attack(b, 'Mirror Attack')
        self.assertEqual(self.dealt(t), 10)

    # --- Bronzong TEF 69: Evolution Jammer -----------------------------------
    async def test_bronzong_evolution_jammer_blocks_next_turn(self):
        t = self.table()
        b = self.mine(t, BRONZONG, PSY, 1)
        target = t.put(BRONZOR, P2, 'bench')
        evo = t.put(BRONZONG, P2, 'hand')
        await t.attack(b, 'Evolution Jammer')
        self.assertEqual(self.dealt(t), 30)
        t.next_turn()
        self.assertFalse(t.can(evo, 'EvolvePokemonPlayAbility', pid=P2))
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.can(evo, 'EvolvePokemonPlayAbility', pid=P2))
        self.assertIsNotNone(target)

    async def test_bronzong_evolution_jammer_not_me(self):
        t = self.table()
        b = self.mine(t, BRONZONG, PSY, 1)
        mine = t.put(BRONZOR, P1, 'bench')
        evo = t.put(BRONZONG, P1, 'hand')
        t.put(BRONZOR, P2, 'bench')
        await t.attack(b, 'Evolution Jammer')
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.can(evo, 'EvolvePokemonPlayAbility', pid=P1))
        self.assertIsNotNone(mine)

    async def test_bronzong_super_psy_bolt_no_jam(self):
        t = self.table()
        b = self.mine(t, BRONZONG, PSY, 3)
        t.put(BRONZOR, P2, 'bench')
        evo = t.put(BRONZONG, P2, 'hand')
        await t.attack(b, 'Super Psy Bolt')
        self.assertEqual(self.dealt(t), 100)
        t.next_turn()
        self.assertTrue(t.can(evo, 'EvolvePokemonPlayAbility', pid=P2))

    # --- Mudkip CES 32: Water Reserve -----------------------------------------
    async def test_mudkip_water_reserve(self):
        t = self.table()
        m = self.mine(t, MUDKIP, WATER, 1)
        t.deck(P1, [t.basic_energy(WATER)] * 4 + [t.basic_energy(FIRE)])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['ok'] = all(self.is_energy_of(c, WATER) for c in cards)
            seen['count'] = count
            return cards[:count]
        t.picks = picks
        await t.attack(m, 'Water Reserve')
        self.assertTrue(seen['ok'])
        self.assertEqual(seen['count'], 3)
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(self.is_energy_of(c, WATER) for c in hand), 3)
        self.assertEqual(len(hand), 3)
        self.assertEqual(self.dealt(t), 0)

    async def test_mudkip_water_reserve_no_water(self):
        t = self.table()
        m = self.mine(t, MUDKIP, WATER, 1)
        t.deck(P1, [t.basic_energy(FIRE)])
        await t.attack(m, 'Water Reserve')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Dreepy SIT 87: Reckless Charge --------------------------------------
    async def test_dreepy_reckless_charge(self):
        t = self.table()
        d = self.mine(t, DREEPY, PSY, 1)
        await t.attack(d, 'Reckless Charge')
        self.assertEqual(self.dealt(t), 30)
        self.assertEqual(t.damage(d), 10)

    # --- Regieleki ASR 51 ----------------------------------------------------
    async def test_regieleki_sonar_takes_trainer_only(self):
        t = self.table()
        r = self.mine(t, REGIELEKI, LIGHT, 1)
        t.put(self.filler, P1, 'discard')
        t.put(self.item, P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'] = t.names(cards)
            return cards[:count]
        t.picks = picks
        await t.attack(r, 'Electromagnetic Sonar')
        self.assertEqual(seen['names'], [self.item.display_name])
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_regieleki_sonar_no_trainer(self):
        t = self.table()
        r = self.mine(t, REGIELEKI, LIGHT, 1)
        t.put(self.filler, P1, 'discard')
        await t.attack(r, 'Electromagnetic Sonar')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_regieleki_targeted_bolt(self):
        t = self.table()
        r = self.mine(t, REGIELEKI, LIGHT, 3)
        t.energy(r, WATER, 1)
        target = t.put(self.filler, P2, 'bench')
        target.set_attribute(AttrID.HP, 400)
        target.set_attribute(AttrID.WEAKNESS_TYPES, [LIGHT.value])
        await t.attack(r, 'Targeted Bolt')
        self.assertEqual(400 - t.hp(target), 120)
        self.assertEqual(self.dealt(t), 0)
        left = t.board.attached_energies(r)
        self.assertEqual(sum(self.is_energy_of(c, LIGHT) for c in left), 1)
        self.assertEqual(sum(self.is_energy_of(c, WATER) for c in left), 1)

    async def test_regieleki_targeted_bolt_no_bench(self):
        t = self.table()
        r = self.mine(t, REGIELEKI, LIGHT, 3)
        await t.attack(r, 'Targeted Bolt')
        self.assertEqual(self.dealt(t), 0)
        self.assertEqual(len(t.board.attached_energies(r)), 1)   # still discards 2

    # --- Zacian CRZ 94: Battle Legion ------------------------------------------
    async def test_zacian_crz_battle_legion_counts_bench(self):
        for n in (0, 3):
            t = self.table()
            z = self.mine(t, ZACIAN_CRZ, METAL, 1)
            for _ in range(n):
                t.put(self.filler, P1, 'bench')
            t.put(self.filler, P2, 'bench')           # opponent's bench ignored
            await t.attack(z, 'Battle Legion')
            with self.subTest(n=n):
                self.assertEqual(self.dealt(t), 20 + 10 * n)

    async def test_zacian_crz_battle_legion_ignores_weakness_not_resistance(self):
        t = self.table()
        z = self.mine(t, ZACIAN_CRZ, METAL, 1)
        t.put(self.filler, P1, 'bench')
        t.put(self.filler, P1, 'bench')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [METAL.value])
        await t.attack(z, 'Battle Legion')
        self.assertEqual(self.dealt(t), 40)
        t2 = self.table()
        z2 = self.mine(t2, ZACIAN_CRZ, METAL, 1)
        for _ in range(3):
            t2.put(self.filler, P1, 'bench')
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, METAL.value)
        await t2.attack(z2, 'Battle Legion')
        self.assertEqual(400 - t2.hp(self.opp), 20)    # 50 - 30 resistance

    # --- Zacian 30C 106 --------------------------------------------------------
    async def test_zacian_30c_hardened_blade(self):
        def_for_tool = fixtures.definition('SV1.DefianceBand_169')   # inert: prizes equal
        for with_tool, expected in ((False, 20), (True, 60)):
            t = self.table()
            z = self.mine(t, ZACIAN_30C, METAL, 1)
            if with_tool:
                t.attach(def_for_tool, z)
            await t.attack(z, 'Hardened Blade')
            with self.subTest(tool=with_tool):
                self.assertEqual(self.dealt(t), expected)

    async def test_zacian_30c_slashing_strike_locked_next_turn(self):
        t = self.table()
        z = self.mine(t, ZACIAN_30C, METAL, 3)
        await t.attack(z, 'Slashing Strike')
        self.assertEqual(self.dealt(t), 120)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(z, 'Slashing Strike'))
        self.assertIsNotNone(t.attack_offer(z, 'Hardened Blade'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(z, 'Slashing Strike'))

    # --- Articuno ROS 17 --------------------------------------------------------
    async def test_articuno_ros_chilling_sigh(self):
        t = self.table()
        a = self.mine(t, ARTICUNO_ROS, WATER, 1)
        await t.attack(a, 'Chilling Sigh')
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertEqual(self.dealt(t), 0)

    async def test_articuno_ros_tri_edge(self):
        for pattern, expected in (([True] * 3, 140), ([True, False, False], 60), ([False] * 3, 20)):
            t = self.table()
            a = self.mine(t, ARTICUNO_ROS, WATER, 3)
            flips = iter(pattern)
            t.heads = lambda title: next(flips)
            await t.attack(a, 'Tri Edge')
            with self.subTest(pattern=pattern):
                self.assertEqual(self.dealt(t), expected)

    async def test_articuno_ros_extra_prize_on_ko(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        a = self.mine(t, ARTICUNO_ROS, WATER, 3)
        self.opp.set_attribute(AttrID.HP, 20)
        t.heads = False
        await t.attack(a, 'Tri Edge')
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 4)

    async def test_articuno_ros_opponent_ko_of_articuno_normal(self):
        t = self.table(opp=SHINX)
        a = self.mine(t, ARTICUNO_ROS, WATER, 0)
        a.set_attribute(AttrID.HP, 10)
        t.put(self.filler, P1, 'bench')
        t.energy(self.opp, LIGHT, 2)
        t.next_turn()
        await t.attack(self.opp, 'Rear Kick', pid=P2)
        self.assertIn(a, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)

    # --- Articuno PGO 24: Ice Symbol ------------------------------------------
    async def test_articuno_pgo_boosts_basic_water(self):
        t = self.table()
        t.put(ARTICUNO_PGO, P1, 'bench')
        s = self.mine(t, SOBBLE, WATER, 2)
        t.heads = False
        await t.attack(s, 'Bind')
        self.assertEqual(self.dealt(t), 30)

    async def test_articuno_pgo_not_articuno_or_other_types(self):
        t = self.table()
        t.put(ARTICUNO_PGO, P1, 'bench')
        a = self.mine(t, ARTICUNO_SIT, WATER, 1)
        await t.attack(a, 'Ice Wing')
        self.assertEqual(self.dealt(t), 20)
        t2 = self.table()
        t2.put(ARTICUNO_PGO, P1, 'bench')
        sh = self.mine(t2, SHINX, LIGHT, 2)
        await t2.attack(sh, 'Rear Kick')
        self.assertEqual(400 - t2.hp(self.opp), 20)
        t3 = self.table()
        a3 = self.mine(t3, ARTICUNO_PGO, WATER, 3)
        await t3.attack(a3, 'Freezing Wind')
        self.assertEqual(400 - t3.hp(self.opp), 110)

    # --- Articuno SIT 36: Wild Freeze -----------------------------------------
    async def test_articuno_sit_wild_freeze(self):
        t = self.table()
        a = self.mine(t, ARTICUNO_SIT, WATER, 2)
        await t.attack(a, 'Wild Freeze')
        self.assertEqual(self.dealt(t), 70)
        self.assertEqual(t.damage(a), 50)
        self.assertIn(PARALYZED, t.conditions(self.opp))
        self.assertNotIn(PARALYZED, t.conditions(a))

    # --- Torchic DRI 40: Collect -----------------------------------------------
    async def test_torchic_collect(self):
        t = self.table()
        tc = self.mine(t, TORCHIC, FIRE, 1)
        await t.attack(tc, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(self.dealt(t), 0)

    # --- Slowpoke GEN 32 ---------------------------------------------------------
    async def test_slowpoke_spacing_out(self):
        for heads, dmg in ((True, 0), (False, 20)):
            t = self.table()
            s = self.mine(t, SLOWPOKE, PSY, 1)
            s.set_attribute(AttrID.HP, 30)              # 20 damage
            t.heads = heads
            await t.attack(s, 'Spacing Out')
            with self.subTest(heads=heads):
                self.assertEqual(t.damage(s), 10 if heads else 20)
                self.assertEqual(self.dealt(t), 0)

    async def test_slowpoke_scavenge(self):
        t = self.table()
        s = self.mine(t, SLOWPOKE, PSY, 2)
        t.put(self.item, P1, 'discard')
        t.put(self.filler, P1, 'discard')
        await t.attack(s, 'Scavenge')
        self.assertEqual(len(t.board.attached_energies(s)), 1)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertEqual(t.names(hand), [self.item.display_name])
        self.assertEqual(self.dealt(t), 0)

    async def test_slowpoke_scavenge_requires_psychic_energy(self):
        t = self.table()
        s = self.mine(t, SLOWPOKE, PSY, 0)
        t.energy(s, WATER, 2)
        t.put(self.item, P1, 'discard')
        offered = t.attack_offer(s, 'Scavenge')
        if offered is not None:      # [P][P] cost should not be payable with Water
            await t.attack(s, 'Scavenge')
        self.assertIsNone(offered)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)


if __name__ == '__main__':
    unittest.main()
