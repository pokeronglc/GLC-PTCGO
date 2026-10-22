"""Bug hunt, deck 8 (Metal): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

M, C, F = PokemonTypes.METAL, PokemonTypes.COLORLESS, PokemonTypes.FIRE
DURALUDON, ARCHALUDON = 'SWSH2.Duraludon_138', 'SV07.Archaludon_107'
VAROOM, REVAVROOM = 'SV065.Varoom_43', 'SV1.Revavroom_142'
BRONZOR, BRONZONG = 'SV3.Bronzor_144', 'XY4.Bronzong_61'
ZAMAZENTA, IRON_CROWN = 'CZ.Zamazenta_97', 'SV08.IronCrown_132'
COBALION, JIRACHI, MAGEARNA = 'XY11.Cobalion_74', 'SM9.Jirachi_99', 'SWSH4.Magearna_128'
MAGNETIC = 'ME4.MagneticMetalEnergy_85'
NEST = 'SV1.NestBall_181'


def name(card):
    return def_for(card.archetype_id).display_name


class Deck8Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    def neutral(self, pokemon, hp=400):
        pokemon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        pokemon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            pokemon.set_attribute(AttrID.HP, hp)

    def swap_opp(self, t, spec):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = t.put(spec, P2, 'active')
        self.neutral(self.opp)
        return self.opp

    async def opponent_hits(self, t, defender, spec=DURALUDON, title='Power Beam', cost=((M, 3),)):
        """P2 attacks P1's Active `defender` with `spec`; returns damage dealt."""
        attacker = self.swap_opp(t, spec)
        for kind, n in cost:
            t.energy(attacker, kind, n)
        t.next_turn()
        before = t.hp(defender)
        await t.attack(attacker, title, pid=P2)
        return before - t.hp(defender)

    async def ko_my_active_on_their_turn(self, t):
        """P2 Knocks Out P1's Active with an attack during P2's turn, then it's P1's turn."""
        victim = t.put(self.filler, P1, 'active', hp=10)
        attacker = self.swap_opp(t, BRONZOR)
        t.energy(attacker, M, 2)
        t.next_turn()
        await t.attack(attacker, 'Speed Dive', pid=P2)
        assert victim not in t.board.pokemon_in_play(P1), 'setup: victim not KOd'
        t.next_turn()

    # --- Duraludon: Metal Sharpener ----------------------------------------
    async def test_metal_sharpener_attaches_metal_from_discard(self):
        t = self.table()
        dura = t.put(DURALUDON, P1, 'active')
        t.energy(dura, M)
        bench = t.put(self.filler, P1, 'bench')
        metal = t.put(t.basic_energy(M), P1, 'discard')
        t.put(t.basic_energy(F), P1, 'discard')
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:count])[1]
        await t.attack(dura, 'Metal Sharpener')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertIn(metal, bench.children)
        self.assertNotIn('Fire Energy', seen.get('n', []))

    async def test_metal_sharpener_ignores_non_metal_energy(self):
        t = self.table()
        dura = t.put(DURALUDON, P1, 'active')
        t.energy(dura, M)
        fire = t.put(t.basic_energy(F), P1, 'discard')
        await t.attack(dura, 'Metal Sharpener')
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(len(t.board.attached_energies(dura)), 1)

    # --- Archaludon: Metal Bridge / Iron Blaster ----------------------------
    async def test_metal_bridge_only_pokemon_with_metal_energy(self):
        t = self.table()
        arch = t.put(ARCHALUDON, P1, 'bench')
        with_metal = t.put(self.filler, P1, 'active')
        without = t.put(self.filler, P1, 'bench')
        t.energy(with_metal, M)
        t.energy(without, F)
        self.assertEqual(t.retreat(with_metal), 0)
        self.assertGreater(t.retreat(without), 0)
        # the opponent's Pokémon with Metal Energy is not "your Pokémon"
        t.energy(self.opp, M)
        self.assertGreater(t.retreat(self.opp), 0)

    async def test_iron_blaster_cant_attack_next_turn(self):
        t = self.table()
        arch = t.put(ARCHALUDON, P1, 'active')
        t.energy(arch, M, 3)
        await t.attack(arch, 'Iron Blaster')
        self.assertEqual(400 - t.hp(self.opp), 160)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(arch, 'Iron Blaster'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(arch, 'Iron Blaster'))

    # --- Varoom: Rigidify --------------------------------------------------
    async def test_rigidify_30_less_next_turn(self):
        t = self.table()
        varoom = t.put(VAROOM, P1, 'active')
        self.neutral(varoom)
        t.energy(varoom, M)
        await t.attack(varoom, 'Rigidify')
        self.assertEqual(await self.opponent_hits(t, varoom), 110 - 30)

    async def test_no_rigidify_full_damage(self):
        t = self.table()
        varoom = t.put(VAROOM, P1, 'active')
        self.neutral(varoom)
        self.assertEqual(await self.opponent_hits(t, varoom), 110)

    # --- Revavroom: Rumbling Engine / Knock Away ----------------------------
    async def test_rumbling_engine_discard_energy_draw_to_six(self):
        t = self.table()
        rev = t.put(REVAVROOM, P1, 'bench')
        t.put(self.filler, P1, 'active')
        energy = t.put(t.basic_energy(M), P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.use(rev, 'Rumbling Engine')
        self.assertIn(energy, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        t.put(t.basic_energy(M), P1, 'hand')
        self.assertIsNone(t.ability_offer(rev, 'Rumbling Engine'))   # once per turn

    async def test_rumbling_engine_needs_energy_in_hand(self):
        t = self.table()
        rev = t.put(REVAVROOM, P1, 'bench')
        t.put(self.filler, P1, 'active')
        t.put(self.item, P1, 'hand')
        self.assertIsNone(t.ability_offer(rev, 'Rumbling Engine'))

    async def test_knock_away(self):
        for heads, dmg in ((True, 180), (False, 90)):
            t = self.table()
            rev = t.put(REVAVROOM, P1, 'active')
            t.energy(rev, M, 4)
            t.heads = heads
            await t.attack(rev, 'Knock Away')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Bronzor: Mirror Draw ----------------------------------------------
    async def test_mirror_draw_matches_opponent_hand(self):
        t = self.table()
        bronzor = t.put(BRONZOR, P1, 'active')
        t.energy(bronzor, M)
        t.put(self.item, P1, 'hand')
        for _ in range(5):
            t.put(self.item, P2, 'hand')
        await t.attack(bronzor, 'Mirror Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 5)

    async def test_mirror_draw_no_draw_when_ahead(self):
        t = self.table()
        bronzor = t.put(BRONZOR, P1, 'active')
        t.energy(bronzor, M)
        for _ in range(3):
            t.put(self.item, P1, 'hand')
        t.put(self.item, P2, 'hand')
        await t.attack(bronzor, 'Mirror Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    # --- Bronzong: Metal Links ---------------------------------------------
    async def test_metal_links_benched_only(self):
        t = self.table()
        bronzong = t.put(BRONZONG, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        metal = t.put(t.basic_energy(M), P1, 'discard')
        seen = {}
        t.pokemon = lambda c, p: (seen.setdefault('c', list(c)), c[0])[1]
        await t.use(bronzong, 'Metal Links')
        self.assertNotIn(bronzong, seen.get('c', []))
        self.assertIn(metal, bench.children)
        t.put(t.basic_energy(M), P1, 'discard')
        self.assertIsNone(t.ability_offer(bronzong, 'Metal Links'))

    async def test_metal_links_needs_metal_in_discard(self):
        t = self.table()
        bronzong = t.put(BRONZONG, P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.put(t.basic_energy(F), P1, 'discard')
        entry = t.ability_offer(bronzong, 'Metal Links')
        if entry is not None:
            await t.do(entry)
        self.assertEqual(sum(len(t.board.attached_energies(p)) for p in t.board.pokemon_in_play(P1)), 0)

    # --- Zamazenta: Metal Shield / Retaliate --------------------------------
    async def test_metal_shield_needs_energy(self):
        for energy, dmg in ((True, 80), (False, 110)):
            t = self.table()
            zama = t.put(ZAMAZENTA, P1, 'active')
            self.neutral(zama)
            if energy:
                t.energy(zama, F)       # any Energy
            with self.subTest(energy=energy):
                self.assertEqual(await self.opponent_hits(t, zama), dmg)

    async def test_retaliate_after_knockout_last_turn(self):
        t = self.table()
        zama = t.put(ZAMAZENTA, P1, 'bench')
        t.energy(zama, M, 3)
        await self.ko_my_active_on_their_turn(t)
        self.assertIs(t.active(P1), zama)
        self.neutral(self.opp)
        await t.attack(zama, 'Retaliate')
        self.assertEqual(400 - t.hp(self.opp), 220)

    async def test_retaliate_without_knockout(self):
        t = self.table()
        zama = t.put(ZAMAZENTA, P1, 'active')
        t.energy(zama, M, 3)
        await t.attack(zama, 'Retaliate')
        self.assertEqual(400 - t.hp(self.opp), 100)

    # --- Iron Crown: Deleting Slash ----------------------------------------
    async def test_deleting_slash_three_benched_boundary(self):
        for bench, dmg in ((2, 40), (3, 120)):
            t = self.table()
            crown = t.put(IRON_CROWN, P1, 'active')
            t.energy(crown, M, 2)
            for _ in range(bench):
                t.put(self.filler, P2, 'bench')
            t.put(self.filler, P1, 'bench'); t.put(self.filler, P1, 'bench'); t.put(self.filler, P1, 'bench')
            await t.attack(crown, 'Deleting Slash')
            with self.subTest(bench=bench):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Cobalion: Quick Guard / Revenge Blast ------------------------------
    async def test_quick_guard_prevents_basic_attackers(self):
        t = self.table()
        cob = t.put(COBALION, P1, 'active')
        self.neutral(cob)
        t.energy(cob, M)
        await t.attack(cob, 'Quick Guard')
        self.assertEqual(await self.opponent_hits(t, cob), 0)
        t.next_turn()
        self.assertIsNone(t.attack_offer(cob, 'Quick Guard'))

    async def test_quick_guard_not_against_evolutions(self):
        t = self.table()
        cob = t.put(COBALION, P1, 'active')
        self.neutral(cob)
        t.energy(cob, M)
        await t.attack(cob, 'Quick Guard')
        dmg = await self.opponent_hits(t, cob, ARCHALUDON, 'Iron Blaster')
        self.assertEqual(dmg, 160)

    async def test_revenge_blast_counts_opponents_prizes(self):
        for taken, dmg in ((0, 30), (2, 90)):
            t = self.table()
            cob = t.put(COBALION, P1, 'active')
            t.energy(cob, M, 2)
            t.set_prizes(P2, 6 - taken)
            t.set_prizes(P1, 6)
            await t.attack(cob, 'Revenge Blast')
            with self.subTest(taken=taken):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Jirachi: Stellar Wish ---------------------------------------------
    async def test_stellar_wish_active_trainer_then_asleep(self):
        t = self.table()
        jirachi = t.put(JIRACHI, P1, 'active')
        t.deck(P1, [NEST, VAROOM, VAROOM, VAROOM, VAROOM])   # NEST deepest of top 5
        seen = {}
        t.picks = lambda cards, count, prompt, display: (
            seen.setdefault('n', t.names(cards)), [c for c in cards if name(c) == 'Nest Ball'][:1])[1]
        await t.use(jirachi, 'Stellar Wish')
        self.assertIn('Nest Ball', t.names(t.zone(P1, 'hand')))
        self.assertNotIn('Varoom', seen['n'])
        self.assertIn(ASLEEP, t.conditions(jirachi))

    async def test_stellar_wish_not_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        jirachi = t.put(JIRACHI, P1, 'bench')
        self.assertIsNone(t.ability_offer(jirachi, 'Stellar Wish'))

    # --- Magearna: Overhaul / Windup Cannon ---------------------------------
    async def test_overhaul_shuffles_hand_and_draws_six(self):
        t = self.table()
        mag = t.put(MAGEARNA, P1, 'active')
        t.energy(mag, M)
        marked = [t.put(VAROOM, P1, 'hand') for _ in range(3)]
        deck_before = len(t.zone(P1, 'deck'))
        await t.attack(mag, 'Overhaul')
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before + 3 - 6)

    async def test_windup_cannon_per_opponent_bench(self):
        for bench, dmg in ((0, 10), (3, 70)):
            t = self.table()
            mag = t.put(MAGEARNA, P1, 'active')
            t.energy(mag, M, 2)
            for _ in range(bench):
                t.put(self.filler, P2, 'bench')
            t.put(self.filler, P1, 'bench')     # my own Bench doesn't count
            await t.attack(mag, 'Windup Cannon')
            with self.subTest(bench=bench):
                self.assertEqual(400 - t.hp(self.opp), dmg)


if __name__ == "__main__":
    unittest.main()
