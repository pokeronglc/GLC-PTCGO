"""Bug hunt round 4, deck 0: Wurmple (DRX 6), Silcoon (LOR 7)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

G, W = PokemonTypes.GRASS, PokemonTypes.WATER
WURMPLE, SILCOON = 'BW6.Wurmple_6', 'SWSH11.Silcoon_7'


class Deck0Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    async def test_wurmple_sleep_poison_heads(self):
        t = self.table()
        w = t.put(WURMPLE, P1, 'active')
        t.energy(w, W)
        t.heads = True
        await t.attack(w, 'Sleep Poison')
        self.assertEqual(t.conditions(self.opp), {ASLEEP, POISONED})

    async def test_wurmple_sleep_poison_tails(self):
        t = self.table()
        w = t.put(WURMPLE, P1, 'active')
        t.energy(w, W)
        t.heads = False
        await t.attack(w, 'Sleep Poison')
        self.assertEqual(t.conditions(self.opp), set())

    async def _string(self, heads):
        t = self.table()
        s = t.put(SILCOON, P1, 'active')
        t.energy(s, G)
        t.energy(self.opp, W, 3)       # opponent can afford Heavy Impact
        t.heads = heads
        await t.attack(s, 'Entangling String')
        t.next_turn()
        return t, s

    async def test_silcoon_entangling_string_heads_blocks_one_turn(self):
        t, s = await self._string(True)
        offers = [e for e in t.offers(self.opp, 'UsePokemonAttack', P2)]
        self.assertEqual(offers, [])
        t.next_turn(); t.next_turn()   # back to P2 two turns later: lock expired
        self.assertTrue(t.offers(self.opp, 'UsePokemonAttack', P2))

    async def test_silcoon_entangling_string_tails_no_lock(self):
        t, s = await self._string(False)
        self.assertTrue(t.offers(self.opp, 'UsePokemonAttack', P2))
        self.assertEqual(t.hp(self.opp), 400)   # no damage printed

    async def test_silcoon_lock_follows_defending_pokemon_only(self):
        t = self.table()
        s = t.put(SILCOON, P1, 'active')
        t.energy(s, G)
        other = t.put(self.filler, P2, 'bench')
        t.energy(other, W, 3)
        t.heads = True
        await t.attack(s, 'Entangling String')
        t.next_turn()
        # retreat-swap the other one in: it was not the Defending Pokemon
        active = t.board.find_player_area(P2, 'activePokemonArea')
        bench = t.board.find_player_area(P2, 'bench')
        t.board.move_card(self.opp.entity_id, bench.entity_id)
        t.board.move_card(other.entity_id, active.entity_id)
        self.assertIs(t.active(P2), other)
        self.assertTrue(t.offers(other, 'UsePokemonAttack', P2))
