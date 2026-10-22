"""Owner report (Oct 15): Medicham XY5 81 (Ω Barrage) + Relicanth SV05 84
(evolved Pokémon may use attacks of their previous Evolutions) could not use
Meditite's Spirited Headbutt ("can't use Spirited Headbutt during your next
turn") as its SECOND attack in the same turn. The lock starts next turn."""
import unittest

from tests import test_ancient_traits_full as traits
from tests.test_ancient_traits_full import FI
from spirit.tools.effect_smoke import P1, P2


class BarrageNextTurnLock(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(traits.AncientTraitsFull.setUpClass.__func__)
    table = traits.AncientTraitsFull.table
    _plain = traits.AncientTraitsFull._plain
    rig = traits.AncientTraitsFull.rig
    add = traits.AncientTraitsFull.add

    async def test_spirited_headbutt_twice_with_barrage(self):
        t = self.table()
        meditite = t.put('SM11.Meditite_109', P1, 'active')
        t.energy(meditite, FI, 2)
        t.put('SV05.Relicanth_84', P1, 'bench')
        medicham = t.put('XY5.Medicham_81', P1, 'hand')
        await t.play(medicham, targets=[meditite.entity_id])
        mon = t.active(P1)
        self.assertIs(mon, medicham)
        hp = t.hp(self.opp)
        self.assertFalse(await t.attack(mon, 'Spirited Headbutt'))      # turn goes on
        self.assertIsNotNone(t.attack_offer(mon, 'Spirited Headbutt'),
                             'second Spirited Headbutt this turn')
        self.assertTrue(await t.attack(mon, 'Spirited Headbutt'))       # turn ends
        self.assertEqual(hp - t.hp(self.opp), 80)
        # ...and it is locked during the owner's next turn.
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(mon, 'Spirited Headbutt'))

    async def test_plain_next_turn_lock_still_applies(self):
        t = self.table()
        mon = t.put('SM11.Meditite_109', P1, 'active')
        t.energy(mon, FI, 1)
        await t.attack(mon, 'Spirited Headbutt')
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(mon, 'Spirited Headbutt'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(mon, 'Spirited Headbutt'))


if __name__ == '__main__':
    unittest.main()
