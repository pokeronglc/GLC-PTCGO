"""'If 1 of your Pokémon used <X> during your last turn, this attack can't be
used.' -- Mewtwo XY12 Barrier, Terrakion SIT Cavern Tackle (and Giratina DLR
Chaos Crawler, tested in upcoming/ME6).

John's ruling (Oct 2026): the restriction is on the player, so switching to
another copy, or the user leaving play, doesn't clear it. It lasts for the
player's next turn only. Pokémon Ranger removes the attack's damage shield
but NOT this restriction (ruling Oct 24).
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

PSY, FIGHT, M = PokemonTypes.PSYCHIC, PokemonTypes.FIGHTING, PokemonTypes.METAL
MEWTWO, TERRAKION = 'XY12.Mewtwo_51', 'SWSH12.Terrakion_97'
DURALUDON = 'SWSH2.Duraludon_138'   # Power Beam [M][M][C] 110
RANGER = 'XY11.PokmonRanger_104'

CASES = ((MEWTWO, 'Barrier', PSY, 2), (TERRAKION, 'Cavern Tackle', FIGHT, 3))


class RepeatAttackLock(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    @staticmethod
    def neutral(p):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])

    def table(self, spec, kind, count):
        t = Table(self)
        first = t.put(spec, P1, 'active')
        second = t.put(spec, P1, 'bench')
        for p in (first, second):
            self.neutral(p)
            t.energy(p, kind, count)
        opp = t.put(DURALUDON, P2, 'active')
        opp.set_attribute(AttrID.HP, 400)
        self.neutral(opp)
        t.energy(opp, M, 3)
        t.state.turn_number = 5
        t.state.active_player_id = P1
        return t, first, second, opp

    def swap(self, t, out, into):
        active = t.board.find_player_area(P1, 'activePokemonArea')
        bench = t.board.find_player_area(P1, 'bench')
        active.remove_child(out)
        bench.remove_child(into)
        t.board.add_card_to_area(into, active)
        t.board.add_card_to_area(out, bench)
        self.assertIs(t.active(P1), into)

    async def test_shield_blocks_next_turn_damage(self):
        for spec, title, kind, count in CASES:
            with self.subTest(title):
                t, me, _, opp = self.table(spec, kind, count)
                await t.attack(me, title)
                t.next_turn()
                before = t.hp(me)
                await t.attack(opp, 'Power Beam', pid=P2)
                self.assertEqual(t.hp(me), before)

    async def test_lock_survives_switching_and_lasts_one_turn(self):
        for spec, title, kind, count in CASES:
            with self.subTest(title):
                t, me, spare, _ = self.table(spec, kind, count)
                self.assertIsNotNone(t.attack_offer(me, title))
                await t.attack(me, title)
                t.next_turn(); t.next_turn()
                self.assertIsNone(t.attack_offer(me, title))
                self.swap(t, me, spare)
                self.assertIsNone(t.attack_offer(spare, title))
                t.next_turn(); t.next_turn()
                self.assertIsNotNone(t.attack_offer(spare, title))

    async def test_lock_holds_after_the_user_leaves_play(self):
        for spec, title, kind, count in CASES:
            with self.subTest(title):
                t, me, spare, _ = self.table(spec, kind, count)
                await t.attack(me, title)
                t.next_turn(); t.next_turn()
                t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
                bench = t.board.find_player_area(P1, 'bench')
                bench.remove_child(spare)
                t.board.add_card_to_area(spare, t.board.find_player_area(P1, 'activePokemonArea'))
                self.assertIsNone(t.attack_offer(spare, title))

    async def test_ranger_removes_the_shield_but_not_the_lock(self):
        for spec, title, kind, count in CASES:
            with self.subTest(title):
                t, me, _, opp = self.table(spec, kind, count)
                await t.attack(me, title)
                t.next_turn()
                ranger = t.put(RANGER, P2, 'hand')
                self.assertTrue(t.offers(ranger, pid=P2))
                await t.play(ranger, pid=P2)
                before = t.hp(me)
                await t.attack(opp, 'Power Beam', pid=P2)
                self.assertLess(t.hp(me), before)
                t.next_turn()
                self.assertIsNone(t.attack_offer(me, title))
                ranger2 = t.put(RANGER, P1, 'hand')
                self.assertFalse(t.offers(ranger2))   # nothing for Ranger to remove

    async def test_ranger_not_playable_without_a_live_effect(self):
        t, me, _, _ = self.table(MEWTWO, PSY, 2)
        ranger = t.put(RANGER, P1, 'hand')
        self.assertFalse(t.offers(ranger))

    async def test_opponents_lock_is_separate(self):
        t, me, _, _ = self.table(MEWTWO, PSY, 2)
        t.state.lock_attack_name(P2, 'Barrier')
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(me, 'Barrier'))


if __name__ == '__main__':
    unittest.main()
