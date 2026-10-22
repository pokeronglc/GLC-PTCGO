"""Alolan Raichu SM11 57 Electro Rain / Starmie SWSH8 53 Multishot Star:
discard counts by live Energy provision."""
import unittest

from tests.test_bughunt7_chunk36 import Chunk36, LIGHT, WATER
from tests.test_bughunt7_chunk9 import ELECTRODE_EVO
from spirit.game.attributes import AttrID
from spirit.tools.effect_smoke import P1, P2

RAICHU, STARMIE = 'SM11.AlolanRaichu_57', 'SWSH8.Starmie_53'
COUNTER = 'SM4.CounterEnergy_100'


class EnergyRain(Chunk36):
    def _behind(self, t):
        t.set_prizes(P1, 6)
        t.set_prizes(P2, 3)

    async def _attack(self, t, me, title):
        hits = []
        real = t.session  # noqa
        t.picks = lambda cards, count, prompt, disp: cards[:count]
        t.pokemon = lambda cands, prompt: (hits.append(1), self.opp)[1]
        before = t.hp(self.opp)
        await t.attack(me, title)
        return len(hits), before - t.hp(self.opp)

    async def test_raichu_counter_and_electrode_count_two_each(self):
        t = self.table(hp=1000)
        self._behind(t)
        me = self.mine(t, RAICHU, LIGHT, 1)
        t.attach(COUNTER, me)
        electrode = self.mine(t, ELECTRODE_EVO, zone='bench')
        t.pokemon = lambda cands, prompt: me
        await t.use(electrode, 'Buzzap Thunder')
        self.assertIn(electrode, t.board.attached_energies(me))
        t.next_turn(); t.next_turn()
        self._behind(t)
        hits, dealt = await self._attack(t, me, 'Electro Rain')
        self.assertEqual(hits, 1 + 2 + 2)            # basic L + Counter + Electrode
        self.assertEqual(dealt, 150)

    async def test_starmie_counts_cards_and_offers_counter(self):
        t = self.table(hp=1000)
        self._behind(t)
        me = self.mine(t, STARMIE, WATER, 1)
        t.attach(COUNTER, me)
        hits, dealt = await self._attack(t, me, 'Multishot Star')
        self.assertEqual(hits, 2)                    # 2 cards discarded
        self.assertEqual(dealt, 60)


for _n in [n for n in vars(Chunk36) if n.startswith('test_')]:
    setattr(EnergyRain, _n, None)
