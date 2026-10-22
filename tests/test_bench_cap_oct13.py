"""Player reports Oct 13 (c).

1. Capture Energy searched (and shuffled) the deck under Parallel City with
   no Bench space left.  It still attaches, but "put a Basic Pokemon from
   your deck onto your Bench" has nowhere to go, so there is no search and
   no shuffle.  Same shrink-aware Bench check for Telepathic Psychic Energy,
   Phantump, Orbeetle, Empoleon (Emergency Surfacing) and Battle VIP Pass.
2. Ambipom ME2 79 Dual Tail ignored Weakness on the Active too: "(Don't
   apply Weakness and Resistance for Benched Pokemon.)" only covers the
   Bench.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.passives import effective_bench_capacity
from spirit.game.scripts.cards.SWSH9.Empoleon_37 import emergency_surfacing_condition
from spirit.tools.effect_smoke import P1, P2

PARALLEL = 'XY8.ParallelCity_145'
CAPTURE = 'SWSH2.CaptureEnergy_171'
BASIC = 'SM7.Onix_71'


def neutral(p, hp=None):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.set_attribute(AttrID.HP, hp)
    return p


class BenchCapacityShrink(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, benched):
        t = Table(self)
        self.me = neutral(t.put(self.filler, P1, 'active'))
        neutral(t.put(self.filler, P2, 'active'))
        for _ in range(benched):
            neutral(t.put(self.filler, P1, 'bench'))
        # P2 plays it facing normally: the Bench half points at P1.
        t.stadium(PARALLEL, P2)
        self.assertEqual(effective_bench_capacity(t.board, P1), 3)
        self.target = t.deck(P1, [BASIC])[0]
        return t

    def deck_ids(self, t):
        return [c.entity_id for c in t.zone(P1, 'deck')]

    async def test_capture_energy_full_shrunk_bench_attaches_without_search(self):
        t = self.table(3)
        before = self.deck_ids(t)
        card = t.put(CAPTURE, P1, 'hand')
        await t.play(card, targets=[self.me.entity_id])
        self.assertIn(card, list(self.me.children))
        self.assertEqual(self.deck_ids(t), before)       # no shuffle
        self.assertEqual(len(t.zone(P1, 'bench')), 3)
        self.assertEqual(t.shown, [])                    # no deck browser
        self.assertFalse(any('deck' in p.lower() for p in t.prompts), t.prompts)

    async def test_capture_energy_searches_when_room(self):
        t = self.table(2)
        card = t.put(CAPTURE, P1, 'hand')
        await t.play(card, targets=[self.me.entity_id])
        self.assertIn(card, list(self.me.children))
        self.assertIn(self.target, t.zone(P1, 'bench'))

    async def test_emergency_surfacing_respects_shrunk_bench(self):
        t = self.table(3)
        for c in t.zone(P1, 'hand'):
            t.board.find_player_area(P1, 'hand').remove_child(c)
        self.assertFalse(emergency_surfacing_condition(t.board, P1, None))
        bench = t.board.find_player_area(P1, 'bench')
        bench.remove_child(bench.children[0])
        self.assertTrue(emergency_surfacing_condition(t.board, P1, None))


class DualTailWeakness(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_active_takes_weakness_bench_does_not(self):
        t = Table(self)
        me = t.put('ME2.Ambipom_79', P1, 'active')
        t.energy(me, PokemonTypes.WATER, 3)
        kind = list(me.get_attribute(AttrID.POKEMON_TYPES))
        opp = neutral(t.put(self.filler, P2, 'active'), hp=400)
        opp.set_attribute(AttrID.WEAKNESS_TYPES, kind)
        bench = neutral(t.put(self.filler, P2, 'bench'), hp=400)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, kind)
        t.picks = lambda cards, count, prompt, shown: [opp, bench]
        await t.attack(me, 'Dual Tail')
        self.assertEqual(400 - t.hp(opp), 120)
        self.assertEqual(400 - t.hp(bench), 60)


if __name__ == '__main__':
    unittest.main()
