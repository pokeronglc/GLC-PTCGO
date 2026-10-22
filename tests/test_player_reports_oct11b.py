"""Player reports, Oct 11 (evening): Magmar Smoke Bomb, Great Haul Net."""
import unittest
from unittest.mock import patch

from tests.test_bughunt7_chunk36 import Chunk36, MAGMAR, FIRE, WATER
from tests.bughunt_table import Table
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2
from spirit.game.attributes import AttrID

HAUL_NET = 'ME4.GreatHaulNet_78'
SOBBLE = 'SWSH6.Sobble_41'


def pick_button(label):
    async def choose(ctx, prompt, buttons, *a, **k):
        return buttons.index(label)
    return patch.object(EffectContext, 'choose', choose)


class SmokeBombTests(Chunk36):
    async def test_no_coin_flipped_when_smoke_bomb_is_used(self):
        t = self.table()
        me = self.mine(t, MAGMAR, FIRE, 1, hp=300)
        seen = []
        t.heads = lambda title: (seen.append(title), False)[1]
        await t.attack(me, 'Smoke Bomb')
        self.assertEqual(seen, [])
        self.assertEqual(400 - t.hp(self.opp), 10)

    async def test_check_applies_to_the_defending_pokemon_only(self):
        t = self.table()
        me = self.mine(t, MAGMAR, FIRE, 1, hp=300)
        await t.attack(me, 'Smoke Bomb')
        checks = t.session.turn_state.attack_flip_checks
        self.assertEqual(set(checks), {self.opp.entity_id})


class GreatHaulNetTests(Chunk36):
    def _discard(self, t):
        mon = t.put(SOBBLE, P1, 'discard')
        energy = t.put(t.basic_energy(WATER), P1, 'discard')
        return mon, energy

    async def test_pokemon_only_leaves_energy_in_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        mon, energy = self._discard(t)
        with pick_button('Water Pokémon'):
            await t.play(t.put(HAUL_NET, P1, 'hand'))
        self.assertIn(mon, t.zone(P1, 'deck'))
        self.assertIn(energy, t.zone(P1, 'discard'))

    async def test_energy_only_leaves_pokemon_in_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        mon, energy = self._discard(t)
        with pick_button('Basic Water Energy'):
            await t.play(t.put(HAUL_NET, P1, 'hand'))
        self.assertIn(energy, t.zone(P1, 'deck'))
        self.assertIn(mon, t.zone(P1, 'discard'))

    async def test_both(self):
        t = self.table()
        self.mine(t, self.filler)
        mon, energy = self._discard(t)
        with pick_button('Both'):
            await t.play(t.put(HAUL_NET, P1, 'hand'))
        self.assertIn(mon, t.zone(P1, 'deck'))
        self.assertIn(energy, t.zone(P1, 'deck'))


for _cls in (SmokeBombTests, GreatHaulNetTests):
    for _n in [n for n in vars(Chunk36) if n.startswith('test_')]:
        setattr(_cls, _n, None)

if __name__ == '__main__':
    unittest.main()


DAN = 'SWSH2.Dan_158'
MAGNETON_CEC = 'SM12.Magneton_69'


class DanRockPaperScissorsTests(Chunk36):
    async def _play(self, picks):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        asked = []
        seq = iter(picks)

        async def rps(ctx, prompt, buttons, player_id=None, *a, **k):
            asked.append((player_id or ctx.player_id, list(buttons)))
            return next(seq)
        with patch.object(EffectContext, 'choose', rps):
            await t.play(t.put(DAN, P1, 'hand'))
        return t, asked

    async def test_win_draws_four(self):
        t, asked = await self._play([0, 2])          # Rock beats Scissors
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual([a[0] for a in asked], [P1, P2])
        self.assertEqual(asked[0][1], ['Rock', 'Paper', 'Scissors'])

    async def test_loss_draws_two(self):
        t, _ = await self._play([2, 0])              # Scissors loses to Rock
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    async def test_tie_is_replayed(self):
        t, asked = await self._play([1, 1, 1, 0])    # Paper tie, then Paper beats Rock
        self.assertEqual(len(asked), 4)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)


class CallSignalKnockOutFirstTests(Chunk36):
    async def test_magneton_is_knocked_out_before_the_search(self):
        from tests.test_bughunt7_chunk9 import SUPPORTER
        t = self.table()
        t.put(self.filler, P1, 'active')
        mag = self.mine(t, MAGNETON_CEC, zone='bench')
        t.deck(P1, [SUPPORTER] * 2)
        during = []
        t.picks = lambda cards, count, prompt, disp: (
            during.append(mag.get_attribute(AttrID.HP)), [])[1]
        await t.use(mag, 'Call Signal')
        self.assertEqual(during, [0])        # Knock Out already committed
        self.assertNotIn(mag, t.board.pokemon_in_play(P1))


for _cls in (DanRockPaperScissorsTests, CallSignalKnockOutFirstTests):
    for _n in [n for n in vars(Chunk36) if n.startswith('test_')]:
        setattr(_cls, _n, None)
