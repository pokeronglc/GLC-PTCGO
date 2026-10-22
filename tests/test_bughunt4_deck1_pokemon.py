"""Bug hunt round 4, deck 1: Mareep (TEU 41)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

L, W = PokemonTypes.LIGHTNING, PokemonTypes.WATER
MAREEP = 'SM9.Mareep_41'


class Deck1Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_shock_bolt_discards_only_lightning(self):
        t = Table(self)
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        m = t.put(MAREEP, P1, 'active')
        lightning = t.energy(m, L, 2)
        water = t.energy(m, W)
        before = t.hp(opp)
        await t.attack(m, 'Shock Bolt')
        self.assertEqual(before - t.hp(opp), 30)
        self.assertEqual(list(m.children), [water])
        for e in lightning:
            self.assertIn(e, t.zone(P1, 'discard'))

    async def test_shock_bolt_needs_lightning(self):
        t = Table(self)
        t.put(self.filler, P2, 'active')
        m = t.put(MAREEP, P1, 'active')
        t.energy(m, W)
        self.assertIsNone(t.attack_offer(m, 'Shock Bolt'))
