"""Owner rulings Oct 13 (b).

1. Deck-only Trainers can't be played with an EMPTY deck: Clay SM12 188,
   Hole-Digging Shovel ME3 74, N's Resolve SM12 200, Underground Expedition
   SM7 150, Emma ME4 77, Lillie's Full Force SM12 196, Gym Badge Promo_XY 203
   (and reprints); Team Rocket's Handiwork XY10 112 needs a card in the
   OPPONENT's deck.
2. "During your next turn, the Defending Pokémon takes N more damage" style
   debuffs work only during the attacking player's own next turn -- not
   during the opponent's turn in between (their own recoil is unaffected).
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

FIGHT, LIGHT, GRASS, PSY = (PokemonTypes.FIGHTING, PokemonTypes.LIGHTNING,
                            PokemonTypes.GRASS, PokemonTypes.PSYCHIC)

# (spec, display) -- every printing of each ruled card.
EMPTY_DECK_BLOCKED = [
    'SM12.Clay_188',
    'ME3.HoleDiggingShovel_74',
    'SM12.NsResolve_200', 'SM12.NsResolve_232',
    'SM7.UndergroundExpedition_150', 'SM7.UndergroundExpedition_168',
    'ME4.Emma_77', 'ME4.Emma_107',
    'SM12.LilliesFullForce_196', 'SM12.LilliesFullForce_230',
] + [f'Promo_XY.GymBadge_{n}' for n in range(203, 211)]
HANDIWORK = ['XY10.TeamRocketsHandiwork_112', 'XY10.TeamRocketsHandiwork_124']

ONIX = 'SM7.Onix_71'           # Screech: +20 during your next turn
MAWILE = 'SWSH11.Mawile_71'    # Tempting Trap: +90 during your next turn
BEEDRILL = 'XY5.Beedrill_3'    # Allergic Shock: KO if damaged during your next turn
ELECTRIKE = 'ME1.Electrike_49'  # Thunder Jolt 30, also 10 to itself


def clear(t, pid, zone):
    area = t.board.find_player_area(pid, zone)
    for card in list(area.children):
        area.remove_child(card)


def neutral(p, hp=None):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.set_attribute(AttrID.HP, hp)
    return p


class EmptyDeckTrainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        neutral(t.put(self.filler, P1, 'active'))
        neutral(t.put(self.filler, P2, 'active'))
        # N's Resolve / Emma have something to work on when the deck has cards.
        t.put('SM12.NsResolve_200', P2, 'hand')
        return t

    async def test_blocked_with_empty_own_deck(self):
        for spec in EMPTY_DECK_BLOCKED:
            with self.subTest(spec):
                t = self.table()
                clear(t, P1, 'deck')
                card = t.put(spec, P1, 'hand')
                self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_playable_with_cards_in_deck(self):
        for spec in EMPTY_DECK_BLOCKED:
            with self.subTest(spec):
                t = self.table()
                card = t.put(spec, P1, 'hand')
                self.assertTrue(t.can(card, 'UseTrainerCard'))

    async def test_handiwork_needs_opponents_deck(self):
        for spec in HANDIWORK:
            with self.subTest(spec):
                t = self.table()
                clear(t, P2, 'deck')
                card = t.put(spec, P1, 'hand')
                self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_handiwork_ignores_own_empty_deck(self):
        for spec in HANDIWORK:
            with self.subTest(spec):
                t = self.table()
                clear(t, P1, 'deck')
                card = t.put(spec, P1, 'hand')
                self.assertTrue(t.can(card, 'UseTrainerCard'))


class OwnNextTurnDebuffs(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def board(self, attacker_spec, kinds, hp=400):
        t = Table(self)
        me = neutral(t.put(attacker_spec, P1, 'active'), hp=hp)
        for kind, count in kinds:
            t.energy(me, kind, count)
        foe = neutral(t.put(ELECTRIKE, P2, 'active'), hp=400)
        t.energy(foe, LIGHT, 1)
        neutral(t.put(self.filler, P2, 'bench'))         # a KO doesn't end the game
        return t, me, foe

    async def recoil(self, t, foe):
        """P2's Thunder Jolt on P2's own turn; returns the self-damage taken."""
        before = t.hp(foe)
        await t.attack(foe, 'Thunder Jolt', pid=P2)
        return before - t.hp(foe)

    async def test_onix_screech(self):
        t, onix, foe = self.board(ONIX, [(FIGHT, 2)], hp=None)   # printed HP: Rage counts counters
        await t.attack(onix, 'Screech')
        t.next_turn()                                   # opponent's turn
        self.assertEqual(await self.recoil(t, foe), 10)  # not 30
        t.next_turn()                                   # Onix's next turn
        counters = t.damage(onix) // 10                 # Thunder Jolt hit Onix
        self.assertEqual(counters, 3)
        before = t.hp(foe)
        await t.attack(onix, 'Rage')
        self.assertEqual(before - t.hp(foe), 10 + 10 * counters + 20)
        t.next_turn()                                   # effect gone
        self.assertEqual(await self.recoil(t, foe), 10)

    async def test_mawile_tempting_trap(self):
        t, mawile, foe = self.board(MAWILE, [(PSY, 3)])
        await t.attack(mawile, 'Tempting Trap')
        t.next_turn()
        self.assertEqual(await self.recoil(t, foe), 10)  # not 100
        t.next_turn()
        before = t.hp(foe)
        await t.attack(mawile, 'Bite')
        self.assertEqual(before - t.hp(foe), 90 + 90)
        t.next_turn()
        self.assertEqual(await self.recoil(t, foe), 10)

    async def test_beedrill_allergic_shock(self):
        t, beedrill, foe = self.board(BEEDRILL, [(GRASS, 2)])
        await t.attack(beedrill, 'Allergic Shock')
        t.next_turn()
        self.assertEqual(await self.recoil(t, foe), 10)  # recoil doesn't KO it
        self.assertIs(t.active(P2), foe)
        t.next_turn()
        await t.attack(beedrill, 'Twineedle')
        self.assertNotIn(foe, t.zone(P2, 'active'))     # Knocked Out now


if __name__ == '__main__':
    unittest.main()
