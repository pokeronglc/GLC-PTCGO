"""Player reports, Oct 11: Mismagius Mysterious Message, Florges Calming
Aroma, Peonia Prize spots, Butterfree Scale Hurricane, Bunnelby, Xerosic."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests import test_sweep_coins as sc
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost
from spirit.game.attributes import PokemonTypes as T
from spirit.tools.effect_smoke import P1, P2


def atk(spec, title):
    return next(a for a in fixtures.definition(spec).abilities if a.title == title)


class PlayerReportsOct11(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, spec=None):
        t = Table(self)
        t.heads = True
        me = neutral(t.put(spec or self.filler, P1, 'active'))
        mb = neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        ob = neutral(t.put(self.filler, P2, 'bench'))
        return t, me, mb, opp, ob

    async def test_mysterious_message_knocks_itself_out(self):
        t, *_ = self.table()
        mis = neutral(t.put('SM10.Mismagius_78', P1, 'bench'))
        await t.do(t.ability_offer(mis, 'Mysterious Message'))
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        self.assertNotIn(mis, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)          # opponent takes a Prize

    async def test_calming_aroma(self):
        for fairy, offered in ((2, True), (1, False)):
            t, me, *_ = self.table('XY8.Florges_103')
            t.energy(me, T.FAIRY, fairy)
            self.assertEqual(bool(t.attack_offer(me, 'Wonder Shine')), offered, fairy)

    async def test_peonia_returns_cards_to_the_same_spots(self):
        t, *_ = self.table()
        pile = t.board.find_player_area(P1, 'prizePile')
        before = list(pile.children)
        await t.play(t.put('SWSH6.Peonia_149', P1, 'hand'))
        slots = {c.entity_id: c.board_slot for c in pile.children}
        # The 3 Prizes left behind keep their spots (3, 4, 5); the 3 new ones
        # fill the gaps the taken ones left (0, 1, 2).
        self.assertEqual([slots[c.entity_id] for c in before[3:]], [3, 4, 5])
        self.assertEqual(sorted(slots.values()), [0, 1, 2, 3, 4, 5])

    async def test_scale_hurricane_needs_two_heads(self):
        for seq, want in (([True, False, False, False], set()), ([True, True, False, False], {'Paralyzed'})):
            t, me, mb, opp, ob = self.table('SV09.Butterfree_3')
            t.heads = sc.coins(seq)
            pay_cost(t, me, atk('SV09.Butterfree_3', 'Scale Hurricane'))
            await t.attack(me, 'Scale Hurricane')
            self.assertEqual(t.conditions(opp), want)

    async def test_bunnelby(self):
        t, me, *_ = self.table('XY5.Bunnelby_121')
        pay_cost(t, me, atk('XY5.Bunnelby_121', 'Burrow'))
        mine, theirs = len(t.zone(P1, 'deck')), len(t.zone(P2, 'deck'))
        await t.attack(me, 'Burrow')
        self.assertEqual((len(t.zone(P1, 'deck')), len(t.zone(P2, 'deck'))), (mine, theirs - 1))

    async def test_xerosic(self):
        t, me, mb, opp, ob = self.table()
        tool = t.attach('SWSH1.AirBalloon_156', opp)
        await t.play(t.put('XY4.Xerosic_110', P1, 'hand'))
        self.assertIn(tool, t.zone(P2, 'discard'))


if __name__ == "__main__":
    unittest.main()
