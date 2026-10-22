"""Bug hunt, deck 7 (Water): Pokémon, checked against their text, including
the cases where they should NOT work.  Frosmoth's Ice Dance and Baxcalibur's
Super Cold are covered in tests/test_player_reports_oct09.py."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, CONFUSED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, L, F = PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.FIRE
FRIGIBAX, ARCTIBAX = 'SV045.Frigibax_17', 'SV2.Arctibax_59'
BASCULIN, BASCULEGION = 'SWSH10.HisuianBasculin_43', 'SWSH10.HisuianBasculegion_44'
REMORAID, OCTILLERY = 'ME4.Remoraid_16', 'XY8.Octillery_33'
SNOM = 'SV05.Snom_45'
SOBBLE, DRIZZILE, INTELEON = 'SWSH1.Sobble_55', 'SWSH1.Drizzile_56', 'SWSH1.Inteleon_58'
WAILMER, WAILORD = 'ME5.Wailmer_15', 'SV09.Wailord_41'
CRYOGONAL, KYOGRE, WISHIWASHI = 'SM11.Cryogonal_46', 'CZ.Kyogre_36', 'SM12.Wishiwashi_62'
BLITZLE = 'SV08.Blitzle_62'
SPLASH = 'XY9.SplashEnergy_113'
NEST, FLOAT, NESSA = 'SV1.NestBall_181', 'XY8.FloatStone_137', 'SWSH4.Nessa_157'


class Deck7Pokemon(unittest.IsolatedAsyncioTestCase):
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

    def name(self, card):
        return def_for(card.archetype_id).display_name

    # --- Frigibax: Collect ---------------------------------------------
    async def test_frigibax_collect_draws_one(self):
        t = self.table()
        f = t.put(FRIGIBAX, P1, 'active')
        t.energy(f, W)
        await t.attack(f, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    # --- Hisuian Basculin: Gather the Crew -------------------------------
    async def test_gather_the_crew_two_basics_free(self):
        t = self.table()
        b = t.put(BASCULIN, P1, 'active')                 # no Energy needed
        t.deck(P1, [SNOM, SOBBLE, REMORAID, DRIZZILE])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', (t.names(cards), count)), cards[:count])[1]
        await t.attack(b, 'Gather the Crew')
        names, count = seen['n']
        self.assertEqual(count, 2)
        self.assertNotIn('Drizzile', names)
        self.assertEqual(len(t.zone(P1, 'bench')), 2)

    async def test_gather_the_crew_respects_bench_space(self):
        t = self.table()
        b = t.put(BASCULIN, P1, 'active')
        for _ in range(4):
            t.put(self.filler, P1, 'bench')
        t.deck(P1, [SNOM, SOBBLE, REMORAID])
        await t.attack(b, 'Gather the Crew')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Hisuian Basculegion: Grudge Dive --------------------------------
    async def test_grudge_dive_after_attack_knockout(self):
        t = self.table(BLITZLE)
        victim = t.put(self.filler, P1, 'active', hp=10)
        bas = t.put(BASCULEGION, P1, 'bench')
        t.energy(bas, W)
        t.energy(self.opp, L, 2)
        t.next_turn()
        t.pokemon = lambda c, p: bas if bas in c else c[0]
        await t.attack(self.opp, 'Static Shock', pid=P2)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        if t.active(P1) is not bas:
            t.board.move_card(bas.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        t.next_turn()
        self.neutral(self.opp)
        await t.attack(bas, 'Grudge Dive')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    async def test_grudge_dive_without_knockout(self):
        t = self.table()
        bas = t.put(BASCULEGION, P1, 'active')
        t.energy(bas, W)
        await t.attack(bas, 'Grudge Dive')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertNotIn(CONFUSED, t.conditions(self.opp))

    async def test_grudge_dive_ignores_poison_knockout(self):
        t = self.table()
        victim = t.put(self.filler, P1, 'active', hp=10)
        bas = t.put(BASCULEGION, P1, 'bench')
        t.energy(bas, W)
        victim.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        t.next_turn()
        t.pokemon = lambda c, p: bas if bas in c else c[0]
        await t.checkup()
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        if t.active(P1) is not bas:
            t.board.move_card(bas.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        t.next_turn()
        await t.attack(bas, 'Grudge Dive')
        self.assertEqual(400 - t.hp(self.opp), 30)

    # --- Octillery ------------------------------------------------------
    async def test_abyssal_hand_draws_to_five_once(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        o = t.put(OCTILLERY, P1, 'bench')
        t.put(self.item, P1, 'hand'); t.put(self.item, P1, 'hand')
        await t.use(o, 'Abyssal Hand')
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        t.board.move_card(t.zone(P1, 'hand')[0].entity_id,
                          t.board.find_player_area(P1, 'discard').entity_id)
        self.assertIsNone(t.ability_offer(o, 'Abyssal Hand'))

    async def test_abyssal_hand_not_with_five_cards(self):
        t = self.table()
        o = t.put(OCTILLERY, P1, 'active')
        for _ in range(5):
            t.put(self.item, P1, 'hand')
        self.assertIsNone(t.ability_offer(o, 'Abyssal Hand'))

    async def test_octillery_hug_blocks_retreat(self):
        t = self.table()
        o = t.put(OCTILLERY, P1, 'active')
        t.energy(o, W, 3)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, F, 4)
        await t.attack(o, 'Hug')
        self.assertEqual(400 - t.hp(self.opp), 40)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))

    async def test_abyssal_hand_off_under_neutralizing_gas(self):
        t = Table(self)
        t.put('SWSH2.GalarianWeezing_113', P2, 'active')
        o = t.put(OCTILLERY, P1, 'active')
        self.assertIsNone(t.ability_offer(o, 'Abyssal Hand'))

    # --- Snom ------------------------------------------------------------
    async def test_snom_powder_snow(self):
        t = self.table()
        s = t.put(SNOM, P1, 'active')
        t.energy(s, W)
        await t.attack(s, 'Powder Snow')
        self.assertEqual(400 - t.hp(self.opp), 10)
        self.assertIn(ASLEEP, t.conditions(self.opp))

    # --- Drizzile / Inteleon: Shady Dealings -----------------------------
    async def test_drizzile_shady_dealings_one_trainer(self):
        t = self.table()
        sobble = t.put(SOBBLE, P1, 'active')
        t.deck(P1, [NEST, FLOAT, SNOM])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', (t.names(cards), count)), [c for c in cards if self.name(c) == 'Float Stone'][:count])[1]
        await t.play(t.put(DRIZZILE, P1, 'hand'), targets=[sobble.entity_id])
        names, count = seen['n']
        self.assertEqual(count, 1)
        self.assertNotIn('Snom', names)
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Float Stone'])

    async def test_inteleon_shady_dealings_two_trainers(self):
        t = self.table()
        drizzile = t.put(DRIZZILE, P1, 'active')
        t.deck(P1, [NEST, FLOAT, NESSA])
        t.picks = lambda cards, count, prompt, display: [c for c in cards if self.name(c) in ('Float Stone', 'Nessa')][:count]
        await t.play(t.put(INTELEON, P1, 'hand'), targets=[drizzile.entity_id])
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Float Stone', 'Nessa'])

    async def test_shady_dealings_not_when_put_into_play_without_evolving(self):
        # Already in play (not played from hand to evolve): nothing to offer.
        t = self.table()
        dz = t.put(DRIZZILE, P1, 'active')
        self.assertIsNone(t.ability_offer(dz, 'Shady Dealings'))

    async def test_inteleon_aqua_bullet(self):
        t = self.table()
        i = t.put(INTELEON, P1, 'active')
        t.energy(i, W, 2)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [W.value])
        before = t.hp(bench)
        await t.attack(i, 'Aqua Bullet')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertEqual(before - t.hp(bench), 20)

    # --- Wailord: Hydro Pump ----------------------------------------------
    async def test_hydro_pump_counts_water_energy_only(self):
        t = self.table()
        w = t.put(WAILORD, P1, 'active')
        t.energy(w, W, 2)
        t.energy(w, F, 2)
        await t.attack(w, 'Hydro Pump')
        self.assertEqual(400 - t.hp(self.opp), 10 + 100)

    async def test_hydro_pump_counts_splash_energy(self):
        t = self.table()
        w = t.put(WAILORD, P1, 'active')
        t.energy(w, W, 3)
        t.attach(SPLASH, w)
        await t.attack(w, 'Hydro Pump')
        self.assertEqual(400 - t.hp(self.opp), 10 + 200)

    # --- Cryogonal: Frozen Lock ------------------------------------------
    async def test_frozen_lock_blocks_items_not_supporters(self):
        t = self.table()
        c = t.put(CRYOGONAL, P1, 'active')
        t.energy(c, W)
        await t.attack(c, 'Frozen Lock')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.next_turn()
        item = t.put(self.item, P2, 'hand')
        t.put(self.item, P2, 'deck')
        sup = t.put('SV2.Iono_185', P2, 'hand')
        self.assertFalse(t.can(item, 'UseTrainerCard', P2))
        self.assertTrue(t.can(sup, 'UseTrainerCard', P2))
        t.next_turn()
        mine = t.put(self.item, P1, 'hand')          # the attacker isn't locked
        self.assertTrue(t.can(mine, 'UseTrainerCard', P1))
        t.next_turn()
        self.assertTrue(t.can(item, 'UseTrainerCard', P2))   # lock is over

    # --- Kyogre -----------------------------------------------------------
    async def test_wave_summoning_attaches_water_from_deck(self):
        t = self.table()
        k = t.put(KYOGRE, P1, 'active')
        t.energy(k, F)
        fire, water = t.deck(P1, [t.basic_energy(F), t.basic_energy(W)])
        await t.attack(k, 'Wave Summoning')
        self.assertIn(water, k.children)
        self.assertNotIn(fire, k.children)

    async def test_dynamic_wave_returns_three_and_hits_any(self):
        t = self.table()
        k = t.put(KYOGRE, P1, 'active')
        energies = t.energy(k, W, 5)
        bench = t.put(self.filler, P2, 'bench', hp=400)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [W.value])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(k, 'Dynamic Wave')
        self.assertEqual(len(t.board.attached_energies(k)), 2)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(400 - t.hp(bench), 180)          # no Weakness on the Bench
        self.assertEqual(t.hp(self.opp), 400)

    # --- Wishiwashi: Scatter --------------------------------------------
    async def end_opponent_turn(self, t):
        t.next_turn()
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P2))

    async def test_scatter_tails_shuffles_damaged_wishiwashi(self):
        t = self.table()
        t.put(self.filler, P1, 'bench')
        w = t.put(WISHIWASHI, P1, 'active', hp=170)
        energy = t.energy(w, W)
        t.heads = False
        await self.end_opponent_turn(t)
        self.assertIn(w, t.zone(P1, 'deck'))
        self.assertIn(energy, t.zone(P1, 'deck'))
        self.assertIsNotNone(t.active(P1))

    async def test_scatter_no_flip_when_undamaged_or_heads(self):
        for hp, heads in ((180, False), (170, True)):
            t = self.table()
            t.put(self.filler, P1, 'bench')
            w = t.put(WISHIWASHI, P1, 'active', hp=hp)
            t.heads = heads
            await self.end_opponent_turn(t)
            with self.subTest(hp=hp, heads=heads):
                self.assertIs(t.active(P1), w)

    async def test_scatter_not_at_end_of_own_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'bench')
        w = t.put(WISHIWASHI, P1, 'active', hp=170)
        t.heads = False
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        self.assertIs(t.active(P1), w)


if __name__ == "__main__":
    unittest.main()
