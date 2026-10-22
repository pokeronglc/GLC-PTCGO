"""Clefairy CEC 144 Doll Swap: play Lillie's Poké Doll from hand as the new Active."""
import unittest
from tests.test_bughunt7_chunk36 import Chunk36, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

CLEFAIRY, DOLL = 'SM12.Clefairy_144', 'SM12.LilliesPokDoll_197'


class DollSwap(Chunk36):
    async def _swap(self, yes):
        t = self.table()
        clef = self.mine(t, CLEFAIRY, PokemonTypes.FIRE, 3)
        self.mine(t, self.filler, zone='bench')
        doll = t.put(DOLL, P1, 'hand')
        t.yes = yes
        await t.attack(clef, 'Doll Swap')
        return t, clef, doll

    async def test_doll_becomes_new_active(self):
        t, clef, doll = await self._swap(True)
        self.assertIn(clef, t.zone(P1, 'hand'))
        self.assertIs(t.active(P1), doll)

    async def test_declining_promotes_normally(self):
        t, clef, doll = await self._swap(False)
        self.assertIn(doll, t.zone(P1, 'hand'))
        self.assertIsNot(t.active(P1), doll)


for _n in [n for n in vars(Chunk36) if n.startswith('test_')]:
    setattr(DollSwap, _n, None)
