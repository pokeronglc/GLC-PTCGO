"""Bug hunt round 2, deck 8 (Fire): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Triggers, def_for
from spirit.tools.effect_smoke import P1, P2

R, W = PokemonTypes.FIRE, PokemonTypes.WATER
CHARMANDER, CHARMELEON = 'SWSH4.Charmander_23', 'ME2PT5.Charmeleon_21'
LITWICK, LAMPENT, CHANDELURE = 'SWSH11.Litwick_24', 'SWSH2.Lampent_32', 'SV06.Chandelure_38'
SIZZLIPEDE, CENTISKORCH = 'SWSH8.Sizzlipede_47', 'SWSH1.Centiskorch_39'
SLUGMA, CASTFORM = 'SWSH11.Slugma_21', 'SV08.CastformSunnyForm_20'
MOLTRES, ORICORIO = 'SM9.Moltres_19', 'SM2.Oricorio_14'
HEAT_FIRE = 'SWSH3.HeatFireEnergy_174'
APPLIN = 'SWSH2.Applin_21'          # a Basic Grass Pokémon


class Deck8Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    # --- Charmander: Collect ---------------------------------------------
    async def test_charmander_collect_draws_one(self):
        t = self.table()
        c = t.put(CHARMANDER, P1, 'active')
        t.energy(c, R)
        await t.attack(c, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    # --- Charmeleon (vanilla attack): evolves from Charmander only ----------
    async def test_charmeleon_evolves_from_charmander_only(self):
        t = self.table()
        c = t.put(CHARMANDER, P1, 'bench')
        lit = t.put(LITWICK, P1, 'bench')
        meleon = t.put(CHARMELEON, P1, 'hand')
        self.assertEqual(t.targets(meleon, 'EvolvePokemonPlayAbility'), {c.entity_id})

    # --- Litwick: Kindling Panic ----------------------------------------
    async def test_kindling_panic_mills_opponent_one(self):
        t = self.table()
        lit = t.put(LITWICK, P1, 'active')
        t.energy(lit, R)
        mine, theirs = len(t.zone(P1, 'deck')), len(t.zone(P2, 'deck'))
        await t.attack(lit, 'Kindling Panic')
        self.assertEqual(len(t.zone(P2, 'deck')), theirs - 1)
        self.assertEqual(len(t.zone(P2, 'discard')), 1)
        self.assertEqual(len(t.zone(P1, 'deck')), mine)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Lampent: Top Entry / Reignite ----------------------------------
    async def test_top_entry_benches_when_drawn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        lampent = t.put(LAMPENT, P1, 'hand')
        await t._run(lambda: t.session._fire_triggered_abilities(P1, lampent, Triggers.ON_TURN_DRAWN))
        self.assertIn(lampent, t.zone(P1, 'bench'))

    async def test_top_entry_not_with_full_bench_or_declined(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        for _ in range(5):
            t.put(self.filler, P1, 'bench')
        lampent = t.put(LAMPENT, P1, 'hand')
        await t._run(lambda: t.session._fire_triggered_abilities(P1, lampent, Triggers.ON_TURN_DRAWN))
        self.assertIn(lampent, t.zone(P1, 'hand'))
        t = self.table()
        t.put(self.filler, P1, 'active')
        lampent = t.put(LAMPENT, P1, 'hand')
        t.yes = False
        await t._run(lambda: t.session._fire_triggered_abilities(P1, lampent, Triggers.ON_TURN_DRAWN))
        self.assertIn(lampent, t.zone(P1, 'hand'))

    async def test_reignite_attaches_basic_fire_to_any_of_yours(self):
        t = self.table()
        lampent = t.put(LAMPENT, P1, 'active')
        t.energy(lampent, R)
        bench = t.put(self.filler, P1, 'bench')
        fire = t.put(t.basic_energy(R), P1, 'discard')
        t.put(t.basic_energy(W), P1, 'discard')
        t.put(HEAT_FIRE, P1, 'discard')
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', list(cards)), [fire])[1]
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(lampent, 'Reignite')
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertIn(fire, bench.children)
        self.assertEqual([c for c in seen['c'] if self.name(c) in ('Heat Fire Energy',)], [])
        self.assertEqual(len(seen['c']), 1)

    # --- Chandelure: Mind Ruler (Alluring Light covered elsewhere) ----------
    async def test_mind_ruler_30_per_card_in_opponent_hand(self):
        for n in (0, 3):
            t = self.table()
            ch = t.put(CHANDELURE, P1, 'active')
            t.energy(ch, R)
            for _ in range(n):
                t.put(self.filler, P2, 'hand')
            t.put(self.filler, P1, 'hand')      # my own hand doesn't count
            await t.attack(ch, 'Mind Ruler')
            with self.subTest(hand=n):
                self.assertEqual(400 - t.hp(self.opp), 30 * n)

    # --- Sizzlipede: Singe ----------------------------------------------
    async def test_sizzlipede_singe_burns(self):
        t = self.table()
        s = t.put(SIZZLIPEDE, P1, 'active')
        t.energy(s, R)
        await t.attack(s, 'Singe')
        self.assertIn(BURNED, t.conditions(self.opp))
        self.assertEqual(t.hp(self.opp), 400)

    # --- Centiskorch -------------------------------------------------------
    async def test_hundred_foot_flames_mills_per_fire_energy(self):
        t = self.table()
        c = t.put(CENTISKORCH, P1, 'active')
        t.energy(c, R, 3)
        t.energy(c, W, 2)                         # non-Fire don't count
        theirs = len(t.zone(P2, 'deck'))
        await t.attack(c, 'Hundred Foot Flames')
        self.assertEqual(len(t.zone(P2, 'deck')), theirs - 3)
        self.assertEqual(t.hp(self.opp), 400)

    async def test_searing_flame_110_and_burn(self):
        t = self.table()
        c = t.put(CENTISKORCH, P1, 'active')
        t.energy(c, R, 4)
        await t.attack(c, 'Searing Flame')
        self.assertEqual(400 - t.hp(self.opp), 110)
        self.assertIn(BURNED, t.conditions(self.opp))

    # --- Slugma: Draw In ------------------------------------------------
    async def test_draw_in_attaches_fire_from_discard_to_self(self):
        t = self.table()
        s = t.put(SLUGMA, P1, 'active')
        t.energy(s, R)
        fire = t.put(t.basic_energy(R), P1, 'discard')
        t.put(t.basic_energy(W), P1, 'discard')
        await t.attack(s, 'Draw In')
        self.assertIn(fire, s.children)
        self.assertEqual(len(t.board.attached_energies(s)), 2)

    async def test_draw_in_special_energy_is_not_a_fire_energy_card(self):
        # "Fire Energy card" = basic Fire Energy (the Lampent script itself
        # follows this ruling); Heat Fire Energy is a Special Energy card.
        t = self.table()
        s = t.put(SLUGMA, P1, 'active')
        t.energy(s, R)
        heat = t.put(HEAT_FIRE, P1, 'discard')
        await t.attack(s, 'Draw In')
        self.assertIn(heat, t.zone(P1, 'discard'))

    # --- Castform Sunny Form ------------------------------------------------
    async def test_castform_singe_burns(self):
        t = self.table()
        c = t.put(CASTFORM, P1, 'active')
        t.energy(c, R)
        await t.attack(c, 'Singe')
        self.assertIn(BURNED, t.conditions(self.opp))

    async def test_sunny_assist_moves_all_energy_to_one_benched(self):
        t = self.table()
        c = t.put(CASTFORM, P1, 'active')
        energies = [t.energy(c, R), t.energy(c, W), t.energy(c, R)]
        b1 = t.put(self.filler, P1, 'bench')
        b2 = t.put(self.filler, P1, 'bench')
        t.pokemon = lambda cands, p: b2 if b2 in cands else cands[0]
        await t.attack(c, 'Sunny Assist')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(t.board.attached_energies(c), [])
        self.assertEqual(set(t.board.attached_energies(b2)), set(energies))
        self.assertEqual(t.board.attached_energies(b1), [])

    async def test_sunny_assist_without_bench_keeps_energy(self):
        t = self.table()
        c = t.put(CASTFORM, P1, 'active')
        t.energy(c, R, 2)
        await t.attack(c, 'Sunny Assist')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(len(t.board.attached_energies(c)), 2)

    # --- Moltres -------------------------------------------------------------
    async def test_top_burner_discards_fire_and_mills_that_many(self):
        t = self.table()
        m = t.put(MOLTRES, P1, 'active')
        t.energy(m, R, 3)
        water = t.energy(m, W)
        theirs = len(t.zone(P2, 'deck'))
        await t.attack(m, 'Top Burner')
        self.assertEqual(t.board.attached_energies(m), [water])
        self.assertEqual(len(t.zone(P2, 'deck')), theirs - 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 3)
        self.assertEqual(t.hp(self.opp), 400)

    async def test_fire_spin_180_discards_three(self):
        t = self.table()
        m = t.put(MOLTRES, P1, 'active')
        t.energy(m, R, 5)
        await t.attack(m, 'Fire Spin')
        self.assertEqual(400 - t.hp(self.opp), 180)
        self.assertEqual(len(t.board.attached_energies(m)), 2)

    # --- Oricorio ---------------------------------------------------------
    async def test_passionate_dance_up_to_three_basic_fire(self):
        t = self.table()
        o = t.put(ORICORIO, P1, 'active')
        t.energy(o, R)
        t.deck(P1, [CHARMANDER, LITWICK, SLUGMA, SIZZLIPEDE, CHARMELEON, APPLIN])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        await t.attack(o, 'Passionate Dance')
        self.assertEqual(seen['count'], 3)
        self.assertNotIn('Charmeleon', seen['names'])
        self.assertNotIn('Applin', seen['names'])
        self.assertEqual(len(t.zone(P1, 'bench')), 3)

    async def test_kindle_discards_own_then_opponents_energy(self):
        t = self.table()
        o = t.put(ORICORIO, P1, 'active')
        t.energy(o, R, 2)
        t.energy(self.opp, W)
        await t.attack(o, 'Kindle')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertEqual(len(t.board.attached_energies(o)), 1)
        self.assertEqual(t.board.attached_energies(self.opp), [])


if __name__ == "__main__":
    unittest.main()
