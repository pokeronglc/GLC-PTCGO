"""Bug hunt round 6, deck 5 (Fire): Growlithe SVI 31, Arcanine UNB 22,
Larvesta CRE 23, Volcarona CRE 24, Slugma PRC 22, Heatmor FST 41,
Volcanion UNB 25, Heavy Ball BKT 140."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

R, W, G = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS
GROWLITHE, ARCANINE = 'SV1.Growlithe_31', 'SM10.Arcanine_22'
LARVESTA, VOLCARONA = 'SWSH6.Larvesta_23', 'SWSH6.Volcarona_24'
SLUGMA = 'XY5.Slugma_22'
HEATMOR = 'SWSH8.Heatmor_41'
VOLCANION = 'SM10.Volcanion_25'
HEAVY_BALL = 'XY8.HeavyBall_140'
CUFANT = 'SV2.Cufant_149'          # Retreat Cost 3
BELDUM = 'SWSH12.Beldum_117'       # Retreat Cost 1
HOP = 'CZ.Hop_133'


class Deck5Cards(unittest.IsolatedAsyncioTestCase):
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
    def fires(pokemon):
        return [c for c in pokemon.children
                if PokemonTypes.FIRE.value in (c.get_attribute(AttrID.POKEMON_TYPES) or [])]

    # --- Growlithe: Stoke ---------------------------------------------------
    async def test_stoke_attaches_up_to_two_basic_fire_to_self(self):
        t = self.table()
        g = t.put(GROWLITHE, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.energy(g, W)
        f1, f2, f3, w = t.deck(P1, [t.basic_energy(R)] * 3 + [t.basic_energy(W)])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['offered'], seen['count'] = list(cards), count
            return list(cards)[:count]
        t.picks = picks
        await t.attack(g, 'Stoke')
        self.assertEqual(seen['count'], 2)
        self.assertNotIn(w, seen['offered'])
        self.assertEqual(len(self.fires(g)), 2)
        self.assertEqual(bench.children, [])
        self.assertEqual(t.hp(self.opp), 400)

    async def test_stoke_no_fire_in_deck_attaches_nothing(self):
        t = self.table()
        g = t.put(GROWLITHE, P1, 'active')
        t.energy(g, W)
        t.deck(P1, [t.basic_energy(W)])
        await t.attack(g, 'Stoke')
        self.assertEqual(len(g.children), 1)

    # --- Arcanine: Grand Flame / Heat Tackle --------------------------------
    async def test_grand_flame_two_fire_from_discard_to_benched(self):
        t = self.table()
        a = t.put(ARCANINE, P1, 'active')
        t.energy(a, R, 3)
        bench = t.put(self.filler, P1, 'bench')
        f1 = t.put(t.basic_energy(R), P1, 'discard')
        f2 = t.put(t.basic_energy(R), P1, 'discard')
        w = t.put(t.basic_energy(W), P1, 'discard')
        seen = {}

        def pokemon(cands, prompt):
            seen['cands'] = list(cands)
            return bench
        t.pokemon = pokemon
        await t.attack(a, 'Grand Flame')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertIn(f1, bench.children)
        self.assertIn(f2, bench.children)
        self.assertIn(w, t.zone(P1, 'discard'))
        self.assertNotIn(a, seen.get('cands', [bench]), 'Benched Pokémon only')
        self.assertEqual(len(a.children), 3)

    async def test_grand_flame_no_bench_just_damage(self):
        t = self.table()
        a = t.put(ARCANINE, P1, 'active')
        t.energy(a, R, 3)
        f1 = t.put(t.basic_energy(R), P1, 'discard')
        await t.attack(a, 'Grand Flame')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertIn(f1, t.zone(P1, 'discard'))
        self.assertEqual(len(a.children), 3)

    async def test_heat_tackle_self_damage(self):
        t = self.table()
        a = t.put(ARCANINE, P1, 'active')
        self.neutral(a, 140)
        t.energy(a, R, 4)
        await t.attack(a, 'Heat Tackle')
        self.assertEqual(400 - t.hp(self.opp), 190)
        self.assertEqual(140 - t.hp(a), 50)

    # --- Larvesta: Flame Charge ---------------------------------------------
    async def test_flame_charge_fire_energy_to_self(self):
        t = self.table()
        lv = t.put(LARVESTA, P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.energy(lv, R)
        w, f = t.deck(P1, [t.basic_energy(W), t.basic_energy(R)])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['offered'] = list(cards)
            return list(cards)[:count]
        t.picks = picks
        await t.attack(lv, 'Flame Charge')
        self.assertEqual(400 - t.hp(self.opp), 10)
        self.assertNotIn(w, seen['offered'])
        self.assertIn(f, lv.children)
        self.assertEqual(len(lv.children), 2)

    # --- Volcarona: Fire Spin -----------------------------------------------
    async def test_fire_spin_discards_two_energy(self):
        t = self.table()
        v = t.put(VOLCARONA, P1, 'active')
        t.energy(v, R, 4)
        await t.attack(v, 'Fire Spin')
        self.assertEqual(400 - t.hp(self.opp), 170)
        self.assertEqual(len(v.children), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    # --- Slugma: Grass Fire --------------------------------------------------
    async def test_grass_fire_discards_grass_energy_only(self):
        t = self.table()
        s = t.put(SLUGMA, P1, 'active')
        t.energy(s, R)
        grass = t.energy(self.opp, G)
        water = t.energy(self.opp, W)
        await t.attack(s, 'Grass Fire')
        self.assertIn(grass, t.zone(P2, 'discard'))
        self.assertIn(water, self.opp.children)
        self.assertEqual(t.hp(self.opp), 400)

    async def test_grass_fire_no_grass_discards_nothing(self):
        t = self.table()
        s = t.put(SLUGMA, P1, 'active')
        t.energy(s, R)
        water = t.energy(self.opp, W)
        bench = t.put(self.filler, P2, 'bench')
        bgrass = t.energy(bench, G)
        await t.attack(s, 'Grass Fire')
        self.assertIn(water, self.opp.children)
        self.assertIn(bgrass, bench.children, 'Active Pokémon only')

    # --- Heatmor: Flame Cloak / Exciting Flame ------------------------------
    async def test_flame_cloak_fire_from_discard_to_self(self):
        t = self.table()
        h = t.put(HEATMOR, P1, 'active')
        t.energy(h, R)
        bench = t.put(self.filler, P1, 'bench')
        w = t.put(t.basic_energy(W), P1, 'discard')
        f = t.put(t.basic_energy(R), P1, 'discard')
        await t.attack(h, 'Flame Cloak')
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertIn(f, h.children)
        self.assertIn(w, t.zone(P1, 'discard'))
        self.assertEqual(bench.children, [])

    async def test_exciting_flame_needs_three_extra_energy(self):
        for count, bench_dmg in ((6, 180), (5, 0)):
            with self.subTest(energy=count):
                t = self.table()
                h = t.put(HEATMOR, P1, 'active')
                t.energy(h, R, count)
                b = t.put(self.filler, P2, 'bench')
                self.neutral(b)
                await t.attack(h, 'Exciting Flame')
                self.assertEqual(400 - t.hp(self.opp), 90)
                self.assertEqual(400 - t.hp(b), bench_dmg)

    # --- Volcanion: Flare Starter / High-Heat Blast -------------------------
    async def flare_starter(self, turn, active_pid=P1):
        t = self.table()
        t.state.turn_number = turn
        v = t.put(VOLCANION, P1, 'active')
        t.energy(v, R)
        bench = t.put(self.filler, P1, 'bench')
        t.deck(P1, [t.basic_energy(R)] * 4 + [t.basic_energy(W)])
        seen = {}

        def picks(cards, count, prompt, display):
            seen.setdefault('counts', []).append(count)
            seen['offered'] = list(cards)
            return list(cards)[:count]
        t.picks = picks
        t.pokemon = lambda cands, prompt: bench
        await t.attack(v, 'Flare Starter')
        return t, v, bench, seen

    async def test_flare_starter_one_fire_to_any_pokemon(self):
        t, v, bench, seen = await self.flare_starter(3)
        self.assertEqual(len(self.fires(bench)), 1)
        self.assertEqual(len(v.children), 1)
        self.assertEqual(seen['counts'], [1])

    # FIXED (was BUG): Flare Starter ignores "If you go second and it's your first turn, ... up to 3".
    async def test_flare_starter_going_second_first_turn_up_to_three(self):
        t, v, bench, seen = await self.flare_starter(2)
        self.assertEqual(len(self.fires(bench)), 3)

    async def test_flare_starter_going_first_turn_one_only(self):
        # turn 1 is the first player's first turn (attacking is normally not
        # allowed then; run the effect directly to check the count)
        t = self.table()
        t.state.turn_number = 1
        v = t.put(VOLCANION, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.deck(P1, [t.basic_energy(R)] * 4)
        t.pokemon = lambda cands, prompt: bench
        await t.effect(VOLCANION, v, 'Flare Starter')
        self.assertEqual(len(self.fires(bench)), 1)

    async def test_high_heat_blast_four_fire_in_play(self):
        for total, dealt in ((4, 110), (3, 50)):
            with self.subTest(fire=total):
                t = self.table()
                v = t.put(VOLCANION, P1, 'active')
                t.energy(v, R, 2)
                b = t.put(self.filler, P1, 'bench')
                t.energy(b, R, total - 2)
                t.energy(self.opp, R, 3)        # opponent's Fire doesn't count
                await t.attack(v, 'High-Heat Blast')
                self.assertEqual(400 - t.hp(self.opp), dealt)

    # --- Heavy Ball ----------------------------------------------------------
    async def test_heavy_ball_only_retreat_three_or_more(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        heavy, light = t.deck(P1, [CUFANT, BELDUM])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['offered'] = list(cards)
            return list(cards)[:count]
        t.picks = picks
        card = t.put(HEAVY_BALL, P1, 'hand')
        await t.play(card)
        self.assertNotIn(light, seen['offered'])
        self.assertIn(heavy, t.zone(P1, 'hand'))
        self.assertIn(light, t.zone(P1, 'deck'))
        self.assertIn(card, t.zone(P1, 'discard'))


if __name__ == '__main__':
    unittest.main()
