"""Owner ruling (Oct 21, game 31548cc8): Articuno SM9 32's Blizzard Veil does
not stop Hex Maniac, so a Benched Manaphy loses Wave Veil and Psyspear's
bench damage lands. (Ribombee's Mysterious Buzz still shields Fairies.)"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import PokemonTypes as PT
from spirit.tools.effect_smoke import P1, P2


class HexVsBlizzardVeil(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def run_game(self, hex_played):
        t = Table(self)
        t.put('SM9.Articuno_32', P1, 'active', hp=400)
        t.put('CZ.Manaphy_166', P1, 'bench')
        marsh = t.put('SWSH8.Marshtomp_63', P1, 'bench')
        deoxys = t.put('ME4.Deoxys_32', P2, 'active')
        t.energy(deoxys, PT.PSYCHIC, 5)
        t.next_turn()
        if hex_played:
            await t.play(t.put('XY7.HexManiac_75', P2, 'hand'), pid=P2)
        t.picks = lambda c, n, p, s: [marsh]
        await t.attack(deoxys, 'Psyspear', pid=P2)
        return marsh in t.zone(P1, 'discard')   # 90 HP: 120 knocks it out

    async def test_wave_veil_on_without_hex(self):
        self.assertFalse(await self.run_game(False))

    async def test_hex_switches_wave_veil_off_through_blizzard_veil(self):
        self.assertTrue(await self.run_game(True))


if __name__ == "__main__":
    unittest.main()
