"""Bug hunt round 2, deck 4 (Lightning): Mareep, Ampharos, Galvantula, Wide Lens."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

L, W, D = PokemonTypes.LIGHTNING, PokemonTypes.WATER, PokemonTypes.DARKNESS
MAREEP, AMPHAROS = 'ME4.Mareep_27', 'ME4.Ampharos_29'
GALVANTULA, WIDE_LENS = 'RSV10PT5.Galvantula_34', 'XY6.WideLens_95'
CROBAT = 'SWSH12.Crobat_105'      # Critical Bite: 30 to 1 of the opponent's Benched Pokémon


class Deck4Cards(unittest.IsolatedAsyncioTestCase):
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

    # --- Mareep: Thunder Wave ---------------------------------------------
    async def test_mareep_thunder_wave_heads_and_tails(self):
        for heads in (True, False):
            t = self.table()
            mareep = t.put(MAREEP, P1, 'active')
            t.energy(mareep, L, 2)
            t.heads = heads
            await t.attack(mareep, 'Thunder Wave')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 20)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    # --- Ampharos: Synchro Pulse / Flashing Bolt -------------------------
    async def test_synchro_pulse_equal_hands_80_more(self):
        for mine, theirs, dmg in ((2, 2, 220), (0, 0, 220), (3, 2, 140)):
            t = self.table()
            amph = t.put(AMPHAROS, P1, 'active')
            t.energy(amph, L, 2)
            for _ in range(mine):
                t.put(self.item, P1, 'hand')
            for _ in range(theirs):
                t.put(self.item, P2, 'hand')
            await t.attack(amph, 'Flashing Bolt')
            with self.subTest(mine=mine, theirs=theirs):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    async def test_synchro_pulse_not_on_bench_damage(self):
        # Only Ampharos' own attacks against the Active are boosted: a different
        # attacker with equal hands gets nothing.
        t = self.table()
        t.put(AMPHAROS, P1, 'bench')
        mareep = t.put(MAREEP, P1, 'active')
        t.energy(mareep, L, 2)
        await t.attack(mareep, 'Thunder Wave')
        self.assertEqual(400 - t.hp(self.opp), 20)

    async def test_flashing_bolt_locked_next_turn(self):
        t = self.table()
        amph = t.put(AMPHAROS, P1, 'active')
        t.energy(amph, L, 2)
        await t.attack(amph, 'Flashing Bolt')
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(amph, 'Flashing Bolt'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(amph, 'Flashing Bolt'))

    # --- Galvantula: Discharge ----------------------------------------------
    async def test_discharge_discards_only_lightning(self):
        t = self.table()
        galv = t.put(GALVANTULA, P1, 'active')
        t.energy(galv, L, 3)
        water = t.energy(galv, W, 1)
        await t.attack(galv, 'Discharge')
        self.assertEqual(400 - t.hp(self.opp), 150)
        self.assertEqual(list(t.board.attached_energies(galv)), [water])
        self.assertEqual(len(t.zone(P1, 'discard')), 3)

    async def test_discharge_one_lightning(self):
        t = self.table()
        galv = t.put(GALVANTULA, P1, 'active')
        t.energy(galv, L, 1)
        await t.attack(galv, 'Discharge')
        self.assertEqual(400 - t.hp(self.opp), 50)

    # --- Wide Lens ------------------------------------------------------------
    async def _critical_bite(self, lens, weakness=(), resistance=()):
        t = self.table()
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D, 3)
        if lens:
            await t.play(t.put(WIDE_LENS, P1, 'hand'), targets=[crobat.entity_id])
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 300)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [x.value for x in weakness])
        bench.set_attribute(AttrID.RESISTANCE_TYPES, resistance[0].value if resistance else [])  # a single type, as on real cards
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(crobat, 'Critical Bite')
        return 300 - t.hp(bench)

    # Was a bug (fixed Oct 10): Wide Lens has no effect; EffectContext.deal_damage only applies W/R to the opponent's Active
    async def test_wide_lens_applies_weakness_to_bench(self):
        self.assertEqual(await self._critical_bite(True, weakness=[D]), 60)
        self.assertEqual(await self._critical_bite(False, weakness=[D]), 30)

    # Was a bug (fixed Oct 10): Wide Lens has no effect; EffectContext.deal_damage only applies W/R to the opponent's Active
    async def test_wide_lens_applies_resistance_to_bench(self):
        self.assertEqual(await self._critical_bite(True, resistance=[D]), 0)
        self.assertEqual(await self._critical_bite(False, resistance=[D]), 30)


if __name__ == "__main__":
    unittest.main()
