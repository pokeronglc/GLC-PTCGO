"""Bug hunt, deck 3 (Fighting): Special Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

F, D = PokemonTypes.FIGHTING, PokemonTypes.DARKNESS
MAKUHITA, HARIYAMA, TINGLU, GABITE = 'ME1.Makuhita_72', 'ME1.Hariyama_73', 'SV06.TingLu_110', 'BW6.Gabite_89'
AURORA, PRISM, STRONG = 'SWSH1.AuroraEnergy_186', 'BW4.PrismEnergy_93', 'XY10.StrongEnergy_115'
UNIT = 'SM6.UnitEnergyFightingDarknessFairy_118'
ARTAZON = 'SV2.Artazon_171'


class Deck3Attachments(unittest.IsolatedAsyncioTestCase):
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

    # --- Aurora Energy -----------------------------------------------------
    async def test_aurora_energy_needs_a_discard_then_any_type(self):
        t = self.table()
        mak = t.put(MAKUHITA, P1, 'active')
        aurora = t.put(AURORA, P1, 'hand')
        other = t.put(self.item, P1, 'hand')
        await t.play(aurora, targets=[mak.entity_id])
        self.assertIn(aurora, mak.children)
        self.assertIn(other, t.zone(P1, 'discard'))
        self.assertIsNotNone(t.attack_offer(mak, 'Corkscrew Punch'))      # [F]
        self.assertIsNone(t.attack_offer(mak, 'Confront'))                # [F][F]: one at a time

    async def test_aurora_energy_alone_in_hand_cannot_attach(self):
        t = self.table()
        mak = t.put(MAKUHITA, P1, 'active')
        aurora = t.put(AURORA, P1, 'hand')
        self.assertFalse(t.can(aurora, 'DefaultEnergyPlayAbility'))

    # --- Prism Energy ---------------------------------------------------------
    async def test_prism_energy_every_type_on_basic(self):
        t = self.table()
        mak = t.put(MAKUHITA, P1, 'active')
        t.energy(mak, F)
        t.attach(PRISM, mak)
        self.assertIsNotNone(t.attack_offer(mak, 'Confront'))             # [F][F]

    async def test_prism_energy_colorless_on_evolution(self):
        t = self.table()
        hari = t.put(HARIYAMA, P1, 'active')
        t.energy(hari, F, 2)
        t.attach(PRISM, hari)
        self.assertIsNone(t.attack_offer(hari, 'Wild Press'))             # [F][F][F]

    # --- Strong Energy -----------------------------------------------------------
    async def test_strong_energy_plus_20_to_active_fighting_only(self):
        t = self.table()
        mak = t.put(MAKUHITA, P1, 'active')
        strong = t.put(STRONG, P1, 'hand')
        await t.play(strong, targets=[mak.entity_id])
        self.assertIn(strong, mak.children)
        await t.attack(mak, 'Corkscrew Punch')
        self.assertEqual(400 - t.hp(self.opp), 30)

    async def test_strong_energy_not_on_non_fighting_nor_bench_damage(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        strong = t.put(STRONG, P1, 'hand')
        bench = t.put(MAKUHITA, P1, 'bench')
        targets = t.targets(strong, 'DefaultEnergyPlayAbility')
        self.assertNotIn(t.active(P1).entity_id, targets)
        self.assertIn(bench.entity_id, targets)
        # Bench damage from the attack is not boosted
        t = self.table()
        ting = t.put(TINGLU, P1, 'active')
        t.attach(STRONG, ting)
        victim = t.put(self.filler, P2, 'bench')
        t.stadium(ARTAZON, P1)
        await t.attack(ting, 'Ground Crasher')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(t.damage(victim), 30)

    # --- Unit Energy FDY -------------------------------------------------------------
    async def test_unit_energy_fdy_pays_fighting_one_at_a_time(self):
        t = self.table()
        mak = t.put(MAKUHITA, P1, 'active')
        t.attach(UNIT, mak)
        self.assertIsNotNone(t.attack_offer(mak, 'Corkscrew Punch'))      # [F]
        self.assertIsNone(t.attack_offer(mak, 'Confront'))                # [F][F]
        t.energy(mak, D)
        self.assertIsNone(t.attack_offer(mak, 'Confront'))
        t.energy(mak, F)
        self.assertIsNotNone(t.attack_offer(mak, 'Confront'))

    async def test_unit_energy_fdy_not_water(self):
        t = self.table()
        gabite = t.put(GABITE, P1, 'active')                              # Dragonslice [W][F]
        t.attach(UNIT, gabite)
        t.energy(gabite, F)
        self.assertIsNone(t.attack_offer(gabite, 'Dragonslice'))
        t.energy(gabite, PokemonTypes.WATER)
        self.assertIsNotNone(t.attack_offer(gabite, 'Dragonslice'))


if __name__ == "__main__":
    unittest.main()
