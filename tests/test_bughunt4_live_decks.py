"""Bug hunt 4 (Oct 15): cards from the 907 real decks in the live DECK log.

Found by bot-vs-bot games on those decks (spirit.tools.stress_bots with the
live decklists) and by pattern sweeps over today's reported bugs.
"""
import unittest

from tests.test_untested_trainers import Base
from tests.untested_trainer_kit import named
from tests.untested_card_index import card as card_index
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2


class EvolvingLosesHpBonus(Base):
    """Fighting Fury Belt gives +40 HP to a BASIC Pokémon only. Evolving a
    damaged Basic can leave the damage lethal: the Pokémon is Knocked Out.
    (Stress seed 4100507: Bronzong left in play at 0 HP.)"""

    async def test_evolving_into_lethal_damage_knocks_out(self):
        t = Table(self)
        bronzor = t.put('BW4.Bronzor_75', P1, 'active')
        t.attach(card_index('Fighting Fury Belt'), bronzor)
        t.put(self.filler, P1, 'bench')
        t.put(self.filler, P2, 'active')
        base = effective_max_hp(t.board, bronzor)
        self.assertEqual(base, 70 + 40, 'Bronzor 70 + Fighting Fury Belt 40')
        bronzong = t.put('XY4.Bronzong_61', P1, 'hand')
        evolved_max = 90
        bronzor.set_attribute(AttrID.HP, base - evolved_max)   # 90 damage on it
        t.set_prizes(P1, 3)
        t.set_prizes(P2, 3)
        t.deck(P1, [self.filler] * 3)
        t.deck(P2, [self.filler] * 3)
        prizes = len(t.zone(P2, 'prizes'))
        await t.play(bronzong, targets=[bronzor.entity_id])
        self.assertIsNot(t.active(P1), bronzong)
        self.assertIn(bronzong, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), prizes - 1, 'opponent takes a Prize')

    async def test_evolving_with_damage_below_hp_survives(self):
        t = Table(self)
        bronzor = t.put('BW4.Bronzor_75', P1, 'active')
        t.attach(card_index('Fighting Fury Belt'), bronzor)
        t.put(self.filler, P2, 'active')
        bronzor.set_attribute(AttrID.HP, effective_max_hp(t.board, bronzor) - 80)
        bronzong = t.put('XY4.Bronzong_61', P1, 'hand')
        await t.play(bronzong, targets=[bronzor.entity_id])
        self.assertIs(t.active(P1), bronzong)
        self.assertEqual(t.hp(bronzong), 10)


class NamedSearches(Base):
    """'... that have the word "Ball" in their name' (Apricorn Maker)."""

    async def test_apricorn_maker_only_ball_items(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        card = t.put('SM7.ApricornMaker_124', P1, 'hand')
        balls = t.deck(P1, [card_index('Ultra Ball'), card_index('Nest Ball'), card_index('Level Ball')])
        others = t.deck(P1, [card_index('Switch'), card_index('Energy Search')])
        seen = []
        t.picks = lambda cards, count, prompt, shown: (seen.append(list(cards)) or list(cards)[:count])
        await t.play(card)
        self.assertTrue(seen)
        for c in others:
            self.assertNotIn(c, seen[0])
        self.assertTrue(set(seen[0]) <= set(balls))
        self.assertEqual(sum(c in t.zone(P1, 'hand') for c in balls), 2)


class ElectroRainSpecialEnergy(Base):
    """Owner check (Oct 15): Alolan Raichu SM11 57 Electro Rain counts the
    Energy each discarded card provides -- while behind on Prizes Reversal
    Energy = 3 hits, Counter Energy = 2 hits (30 each)."""

    async def rain(self, special):
        from tests.untested_trainer_kit import neutral
        t = Table(self)
        r = t.put('SM11.AlolanRaichu_57', P1, 'active')
        t.attach(card_index(special), r)
        d = neutral(t.put(self.filler, P2, 'active'), hp=400)
        t.set_prizes(P1, 5)
        t.set_prizes(P2, 2)
        t.picks = lambda cards, count, prompt, shown: list(cards)[:count]
        t.pokemon = lambda cands, prompt: d
        await t.attack(r, 'Electro Rain')
        return 400 - t.hp(d)

    async def test_reversal_energy_three_hits(self):
        self.assertEqual(await self.rain('Reversal Energy'), 90)

    async def test_counter_energy_two_hits(self):
        self.assertEqual(await self.rain('Counter Energy'), 60)


class DiscardFromHandIfYouDo(Base):
    """'Discard an Item card from your hand. If you do, ...' with nothing to
    discard: the attack does nothing (no-op detector, Mandibuzz SM9 93 dealt
    its 60 without discarding; Torchic etc. drew without discarding)."""

    async def attack(self, ref, title, kind, hand=()):
        from tests.untested_trainer_kit import neutral
        from spirit.game.attributes import PokemonTypes as T
        t = Table(self)
        a = neutral(t.put(ref, P1, 'active'))
        t.energy(a, getattr(T, kind), 2)
        d = neutral(t.put(self.filler, P2, 'active'), hp=400)
        t.deck(P1, [self.filler] * 5)
        for spec in hand:
            t.put(spec, P1, 'hand')
        t.picks = lambda cards, count, prompt, shown: list(cards)[:count]
        t.pokemon = lambda cands, prompt: d
        await t.attack(a, title)
        return t, d

    async def test_trash_crash_needs_an_item(self):
        t, d = await self.attack('SM9.Mandibuzz_93', 'Trash Crash', 'DARKNESS')
        self.assertEqual(t.hp(d), 400)
        t, d = await self.attack('SM9.Mandibuzz_93', 'Trash Crash', 'DARKNESS',
                                 hand=[card_index('Switch')])
        self.assertEqual(t.hp(d), 340)
        self.assertEqual(t.zone(P1, 'hand'), [])

    async def test_flare_bonus_needs_a_fire_energy(self):
        t, _ = await self.attack('XY5.Torchic_26', 'Flare Bonus', 'FIRE', hand=[self.filler])
        self.assertEqual(len(t.zone(P1, 'hand')), 1, 'no Fire Energy: no draw')


if __name__ == '__main__':
    unittest.main()
