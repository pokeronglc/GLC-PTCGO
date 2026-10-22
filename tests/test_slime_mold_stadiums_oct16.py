"""Owner report (Oct 16): with Toedscruel SV4 17 (Slime Mold Colony) in
play, the opponent still used their own Training Court to put basic Energy
from their discard pile into their hand. A Stadium's ability is a Trainer
card's effect, so it is blocked (and not offered). PokéStop's Items are in
the discard pile when they would go to the hand, so they stay there."""
import unittest

from tests.test_untested_trainers import Base
from tests.untested_card_index import card as card_index
from tests.bughunt_table import Table
from tests.untested_trainer_kit import D
from spirit.tools.effect_smoke import P1, P2


class SlimeMoldStadiums(Base):
    async def use(self, stadium, toedscruel, owner=P2):
        t = Table(self)
        t.put('SV4.Toedscruel_17' if toedscruel else self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        st = t.stadium(stadium, owner)
        t.put(t.basic_energy(D), P2, 'discard')
        t.deck(P2, [card_index('Switch'), self.filler, card_index('Nest Ball')])
        t.next_turn()
        t.picks = lambda cs, n, pr, sh: list(cs)[:n]
        entry = next(iter(t.offers(st, None, P2)), None)
        if entry is not None:
            await t.do(entry, pid=P2)
        return entry is not None, t.zone(P2, 'hand')

    async def test_training_court_blocked_by_slime_mold_colony(self):
        for ref in ('SWSH2.TrainingCourt_169', 'SWSH8.TrainingCourt_282'):
            with self.subTest(ref):
                offered, hand = await self.use(ref, toedscruel=False)
                self.assertTrue(offered)
                self.assertEqual(len(hand), 1)
                offered, hand = await self.use(ref, toedscruel=True)
                self.assertFalse(offered)
                self.assertEqual(hand, [])

    async def test_pokestop_items_stay_in_discard_under_slime_mold_colony(self):
        offered, hand = await self.use('PGO.PokStop_68', toedscruel=False)
        self.assertEqual(len(hand), 2)
        offered, hand = await self.use('PGO.PokStop_68', toedscruel=True)
        self.assertEqual(hand, [])

    async def test_toedscruel_players_own_stadium_is_not_blocked(self):
        """Owner ruling (Oct 16): Slime Mold Colony only stops effects of the
        opponent's own cards -- the Toedscruel player's PokéStop / Training
        Court works normally for the opponent."""
        offered, hand = await self.use('PGO.PokStop_68', toedscruel=True, owner=P1)
        self.assertEqual(len(hand), 2)
        offered, hand = await self.use('SWSH2.TrainingCourt_169', toedscruel=True, owner=P1)
        self.assertTrue(offered)
        self.assertEqual(len(hand), 1)


if __name__ == '__main__':
    unittest.main()
