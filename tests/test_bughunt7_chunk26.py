"""Bug hunt round 7, chunk 26: Garganacl MEG 84, Fossil Quarry PBL 76, Rotom Dex
SUM 131, Floette CEC 151, Florges BKT 103, Tympole OBF 50, Palpitoad DRX 35 /
RCL 45, Metagross CRI 61, Lapras TEU 31 (SM9, chunk path SWSH9 was the wrong
printing), Poison Barb SUM 124, Relicanth TEF 84, Amaura FLI 27, Aurorus POR 24,
Candice SIT 152 -- each checked against its printed text, including the cases
where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, CONFUSED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.card_effects.trainers import candice_predicate
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.FIGHTING
METAL, FAIRY = PokemonTypes.METAL, PokemonTypes.FAIRY

GARGANACL = 'ME1.Garganacl_84'
QUARRY = 'ME5.FossilQuarry_76'
ROTOM_DEX = 'SM1.RotomDex_131'
FLABEBE, FLOETTE = 'SM12.Flabb_149', 'SM12.Floette_151'
FLORGES = 'XY8.Florges_103'
TYMPOLE = 'SV3.Tympole_50'
PALPI_DRX, PALPI_RCL = 'BW6.Palpitoad_35', 'SWSH2.Palpitoad_45'
METAGROSS = 'ME4.Metagross_61'
LAPRAS = 'SM9.Lapras_31'
BARB = 'SM1.PoisonBarb_124'
RELICANTH = 'SV05.Relicanth_84'
AMAURA, FOSSIL = 'SM6.Amaura_27', 'SM6.UnidentifiedFossil_116'
AURORUS = 'ME3.Aurorus_24'
CANDICE = 'SWSH12.Candice_152'
ANTIQUE_A, ANTIQUE_B = 'ME5.AntiqueArmorFossil_72', 'ME3.AntiqueJawFossil_68'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk26(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.big(self.opp)
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=300):
        p = t.put(spec, P1, zone)
        self.big(p, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def energies_on(self, pokemon):
        return [c for c in pokemon.children if self.is_energy(c)]

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    def bench_fossil(self, t, pid=P1):
        f = t.put(FOSSIL, pid, 'hand')
        t.board.move_card(f.entity_id, t.board.find_player_area(pid, 'bench').entity_id)
        t.state.entered_play_turn[f.entity_id] = 0
        return f

    async def test_set_codes(self):
        for path, code in ((GARGANACL, 'ME1'), (QUARRY, 'ME5'), (ROTOM_DEX, 'SM1'),
                           (FLOETTE, 'SM12'), (FLORGES, 'XY8'), (TYMPOLE, 'SV3'),
                           (PALPI_DRX, 'BW6'), (METAGROSS, 'ME4'), (PALPI_RCL, 'SWSH2'),
                           (LAPRAS, 'SM9'), (BARB, 'SM1'), (RELICANTH, 'SV05'),
                           (AMAURA, 'SM6'), (AURORUS, 'ME3'), (CANDICE, 'SWSH12')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Garganacl MEG 84: Powerful a-Salt -----------------------------------
    async def test_garganacl_boosts_your_fighting_attacks_by_30(self):
        t = self.table()
        rel = self.mine(t, RELICANTH, FIGHT, 2)
        self.mine(t, GARGANACL, zone='bench')
        await t.attack(rel, 'Razor Fin')
        self.assertEqual(self.dealt(), 60)

    async def test_garganacl_no_boost_for_non_fighting_or_opponent(self):
        t = self.table()
        title, dmg = self.filler_attack()
        me = self.mine(t, self.filler, WATER, 5)
        self.mine(t, GARGANACL, zone='bench')
        await t.attack(me, title)
        self.assertEqual(self.dealt(), dmg)          # Colorless attacker: no bonus
        # Opponent's Fighting Pokémon do not benefit from MY Garganacl.
        t2 = self.table()
        target = self.mine(t2, self.filler, hp=300)
        self.mine(t2, GARGANACL, zone='bench')
        orel = t2.put(RELICANTH, P2, 'bench')
        self.big(orel)
        t2.board.move_card(self.opp.entity_id, t2.board.find_player_area(P2, 'bench').entity_id)
        t2.board.move_card(orel.entity_id,
                           t2.board.find_player_area(P2, 'activePokemonArea').entity_id)
        t2.energy(orel, FIGHT, 2)
        t2.next_turn()
        await t2.attack(orel, 'Razor Fin', pid=P2)
        self.assertEqual(300 - t2.hp(target), 30)

    # --- Fossil Quarry PBL 76 ---------------------------------------------------
    async def test_fossil_quarry_benches_two_antique_trainers(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(QUARRY, P2)
        t.deck(P1, [ANTIQUE_A, FOSSIL, ANTIQUE_B, ANTIQUE_A])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        entry = next(iter(t.offers(stadium, None, P1)), None)
        self.assertIsNotNone(entry)
        await t.do(entry)
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        self.assertTrue(all('Antique' in name(c) for c in bench))
        self.assertNotIn('Unidentified Fossil', [name(c) for c in offered])
        self.assertFalse(t.offers(stadium, None, P1))       # once per turn
        # Opponent can use it during their own turn too.
        t.deck(P2, [ANTIQUE_B])
        t.next_turn()
        entry = next(iter(t.offers(stadium, None, P2)), None)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertEqual([name(c) for c in t.zone(P2, 'bench')], ['Antique Jaw Fossil'])

    async def test_fossil_quarry_not_with_full_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        for _ in range(5):
            self.mine(t, self.filler, zone='bench')
        stadium = t.stadium(QUARRY, P1)
        t.deck(P1, [ANTIQUE_A])
        entry = next(iter(t.offers(stadium, None, P1)), None)
        if entry is not None:
            await t.do(entry)
        self.assertEqual(len(t.zone(P1, 'bench')), 5)
        self.assertIsNone(entry)

    # --- Rotom Dex SUM 131 -----------------------------------------------------
    async def test_rotom_dex_reshuffles_same_number_of_prizes(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        prize_area = t.board.find_player_area(P1, 'prizePile')
        for c in list(prize_area.children):
            prize_area.remove_child(c)
        markers = [t.put(TYMPOLE, P1, 'prizes') for _ in range(3)]
        deck_before = len(t.zone(P1, 'deck'))
        dex = t.put(ROTOM_DEX, P1, 'hand')
        self.assertTrue(t.can(dex, 'UseTrainerCard'))
        await t.play(dex)
        self.assertEqual(len(t.zone(P1, 'prizes')), 3)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before)
        pool = t.zone(P1, 'prizes') + t.zone(P1, 'deck')
        for m in markers:
            self.assertIn(m, pool)
        self.assertIn(dex, t.zone(P1, 'discard'))
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Floette CEC 151: Flower Picking ---------------------------------------
    async def test_floette_flower_picking_shuffles_one_from_opponent_hand(self):
        # Printed CEC 151 text: "choose a random card" (the script used to
        # carry Florges CEC 152's "2 random cards"; fixed Oct 12).
        t = self.table()
        flab = self.mine(t, FLABEBE)
        self.clear_hand(t, P2)
        for _ in range(3):
            t.put(self.item, P2, 'hand')
        deck_before = len(t.zone(P2, 'deck'))
        t.yes = True
        await t.play(t.put(FLOETTE, P1, 'hand'), targets=[flab.entity_id])
        self.assertEqual(name(t.active(P1)), 'Floette')
        self.assertEqual(len(t.zone(P2, 'hand')), 2)
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before + 1)

    async def test_floette_flower_picking_is_optional(self):
        t = self.table()
        flab = self.mine(t, FLABEBE)
        self.clear_hand(t, P2)
        for _ in range(3):
            t.put(self.item, P2, 'hand')
        t.yes = False
        await t.play(t.put(FLOETTE, P1, 'hand'), targets=[flab.entity_id])
        self.assertEqual(name(t.active(P1)), 'Floette')
        self.assertEqual(len(t.zone(P2, 'hand')), 3)

    # --- Florges BKT 103: Calming Aroma / Wonder Shine --------------------------
    async def test_florges_calming_aroma_and_wonder_shine(self):
        t = self.table()
        flo = self.mine(t, FLORGES, FAIRY, 2)
        self.assertIsNotNone(t.attack_offer(flo, 'Wonder Shine'))   # FFF -> FF
        await t.attack(flo, 'Wonder Shine')
        self.assertEqual(self.dealt(), 70)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    async def test_florges_reduces_only_fairy_and_only_yours(self):
        t = self.table()
        flo = self.mine(t, FLORGES, FAIRY, 1)
        self.assertIsNone(t.attack_offer(flo, 'Wonder Shine'))      # FFF -> FF, only 1
        # Magical Shot (F C) with Florges benched: costs just C.
        t2 = self.table()
        floette = self.mine(t2, FLOETTE, WATER, 1)
        self.mine(t2, FLORGES, zone='bench')
        self.assertIsNotNone(t2.attack_offer(floette, 'Magical Shot'))
        # Opponent's Florges does not help my attacks.
        t3 = self.table()
        floette = self.mine(t3, FLOETTE, WATER, 1)
        t3.put(FLORGES, P2, 'bench')
        self.assertIsNone(t3.attack_offer(floette, 'Magical Shot'))

    # --- Tympole OBF 50: Screw Tail ---------------------------------------------
    async def test_tympole_screw_tail_heads_discards_energy(self):
        t = self.table()
        ty = self.mine(t, TYMPOLE, WATER, 1)
        t.energy(self.opp, FIRE, 2)
        t.heads = True
        await t.attack(ty, 'Screw Tail')
        self.assertEqual(self.dealt(), 10)
        self.assertEqual(len(self.energies_on(self.opp)), 1)

    async def test_tympole_screw_tail_tails_keeps_energy(self):
        t = self.table()
        ty = self.mine(t, TYMPOLE, WATER, 1)
        t.energy(self.opp, FIRE, 2)
        t.heads = False
        await t.attack(ty, 'Screw Tail')
        self.assertEqual(self.dealt(), 10)
        self.assertEqual(len(self.energies_on(self.opp)), 2)

    # --- Palpitoad DRX 35: Supersonic --------------------------------------------
    async def test_palpitoad_drx_supersonic_confuses_no_damage(self):
        t = self.table()
        p = self.mine(t, PALPI_DRX, WATER, 1)
        await t.attack(p, 'Supersonic')
        self.assertEqual(self.dealt(), 0)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    # --- Palpitoad RCL 45: Twirling Sign -----------------------------------------
    async def test_palpitoad_rcl_twirling_sign(self):
        t = self.table()
        p = self.mine(t, PALPI_RCL, WATER, 2)
        await t.attack(p, 'Twirling Sign')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.conditions(self.opp), {CONFUSED})
        self.assertEqual(t.conditions(p), set())

    # --- Metagross CRI 61 ----------------------------------------------------------
    async def test_metagross_bounce_back_opponent_chooses(self):
        t = self.table()
        m = self.mine(t, METAGROSS, METAL, 1)
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(self.filler, P2, 'bench')
        chooser = []
        t.pokemon = lambda c, p: (chooser.append(p), b2 if b2 in c else c[0])[1]
        await t.attack(m, 'Bounce Back')
        self.assertEqual(self.dealt(), 60)
        self.assertIs(t.active(P2), b2)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIn(b1, t.zone(P2, 'bench'))

    async def test_metagross_metallic_hammer_optional_discard(self):
        for yes in (True, False):
            t = self.table()
            m = self.mine(t, METAGROSS, METAL, 4)
            t.yes = yes
            await t.attack(m, 'Metallic Hammer')
            with self.subTest(discard=yes):
                self.assertEqual(self.dealt(), 300 if yes else 150)
                self.assertEqual(len(self.energies_on(m)), 1 if yes else 4)

    # --- Lapras TEU 31 -------------------------------------------------------------
    async def test_lapras_confuse_ray_and_hydro_pump(self):
        t = self.table()
        lap = self.mine(t, LAPRAS, WATER, 3)
        t.energy(lap, FIRE, 1)            # non-Water Energy doesn't count
        await t.attack(lap, 'Hydro Pump')
        self.assertEqual(self.dealt(), 100)
        t2 = self.table()
        lap = self.mine(t2, LAPRAS, WATER, 1)
        await t2.attack(lap, 'Confuse Ray')
        self.assertEqual(self.dealt(), 0)
        self.assertIn(CONFUSED, t2.conditions(self.opp))

    # --- Poison Barb SUM 124 --------------------------------------------------------
    async def test_poison_barb_poisons_attacker_when_active_damaged(self):
        t = self.table()
        title, dmg = self.filler_attack()
        me = self.mine(t, self.filler)
        await t.play(t.put(BARB, P1, 'hand'), targets=[me.entity_id])
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        self.assertEqual(300 - t.hp(me), dmg)
        self.assertIn(POISONED, t.conditions(self.opp))

    async def test_poison_barb_on_bench_does_nothing(self):
        t = self.table()
        title, dmg = self.filler_attack()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(BARB, P1, 'hand'), targets=[bench.entity_id])
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        self.assertNotIn(POISONED, t.conditions(self.opp))

    # --- Relicanth TEF 84: Memory Dive ------------------------------------------------
    async def test_relicanth_memory_dive_evolved_uses_previous_attack(self):
        t = self.table()
        ty = self.mine(t, TYMPOLE)
        self.mine(t, RELICANTH, zone='bench')
        await t.play(t.put(PALPI_RCL, P1, 'hand'), targets=[ty.entity_id])
        palp = t.active(P1)
        self.assertEqual(name(palp), 'Palpitoad')
        t.energy(palp, WATER, 1)
        self.assertIsNotNone(t.attack_offer(palp, 'Screw Tail'))
        t.energy(self.opp, FIRE, 1)
        t.heads = True
        await t.attack(palp, 'Screw Tail')
        self.assertEqual(self.dealt(), 10)
        self.assertEqual(self.energies_on(self.opp), [])

    async def test_relicanth_memory_dive_needs_your_relicanth(self):
        t = self.table()
        ty = self.mine(t, TYMPOLE)
        orel = t.put(RELICANTH, P2, 'bench')          # opponent's Relicanth
        await t.play(t.put(PALPI_RCL, P1, 'hand'), targets=[ty.entity_id])
        palp = t.active(P1)
        t.energy(palp, WATER, 2)
        self.assertIsNone(t.attack_offer(palp, 'Screw Tail'))
        self.assertIsNotNone(t.attack_offer(palp, 'Twirling Sign'))
        self.assertIn(orel, t.zone(P2, 'bench'))

    # --- Amaura FLI 27 -----------------------------------------------------------------
    async def test_amaura_evolves_from_fossil_and_powder_snow(self):
        t = self.table()
        self.mine(t, self.filler)
        f = self.bench_fossil(t)
        amaura = t.put(AMAURA, P1, 'hand')
        entry = t.ability_offer(f, 'Evolve')
        if entry is not None:
            await t.do(entry)
        else:
            await t.play(amaura, targets=[f.entity_id])
        self.assertIn(amaura, t.zone(P1, 'bench'))
        t2 = self.table()
        a = self.mine(t2, AMAURA, WATER, 2)
        await t2.attack(a, 'Powder Snow')
        self.assertEqual(self.dealt(), 30)
        self.assertIn(ASLEEP, t2.conditions(self.opp))

    async def test_amaura_not_onto_non_fossil(self):
        t = self.table()
        me = self.mine(t, self.filler)
        amaura = t.put(AMAURA, P1, 'hand')
        self.assertNotIn(me.entity_id, t.targets(amaura, 'EvolvePokemonPlayAbility'))

    # --- Aurorus POR 24: Tundra Wall (also covered in test_damage_reduction_abilities) --
    async def test_aurorus_tundra_wall_only_with_water_energy(self):
        for water in (True, False):
            t = self.table()
            title, dmg = self.filler_attack()
            me = self.mine(t, self.filler, WATER if water else FIRE, 1)
            self.mine(t, AURORUS, zone='bench')
            t.energy(self.opp, WATER, 5)
            t.next_turn()
            await t.attack(self.opp, title, pid=P2)
            with self.subTest(water=water):
                self.assertEqual(300 - t.hp(me), max(0, dmg - 50) if water else dmg)

    # --- Candice SIT 152 ----------------------------------------------------------------
    async def test_candice_takes_water_pokemon_and_energy_from_top_seven(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        eighth = t.deck(P1, [t.basic_energy(WATER)])[0]
        top = t.deck(P1, [LAPRAS, TYMPOLE, t.basic_energy(WATER), t.basic_energy(FIRE),
                          RELICANTH, self.item, self.filler])
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [c for c in cards if candice_predicate(c)]
        t.picks = picks
        await t.play(t.put(CANDICE, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        for c in top[:3]:
            self.assertIn(c, hand)
        for c in top[3:]:
            self.assertIn(c, t.zone(P1, 'deck'))
        self.assertIn(eighth, t.zone(P1, 'deck'))
        self.assertTrue(all(candice_predicate(c) for c in offered),
                        [name(c) for c in offered])

    async def test_candice_may_take_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.deck(P1, [LAPRAS, t.basic_energy(WATER)])
        before = len(t.zone(P1, 'deck'))
        t.picks = lambda cards, count, prompt, display: []
        await t.play(t.put(CANDICE, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), before)


if __name__ == '__main__':
    unittest.main()
