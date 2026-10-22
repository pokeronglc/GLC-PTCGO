"""Bug hunt round 4, deck 3 (Grass): Oddish OBF 1, Turtwig TEF 10,
Celebi MEG 12, Growing Grass Energy POR 86."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

G, R, W = PokemonTypes.GRASS, PokemonTypes.FIRE, PokemonTypes.WATER
ODDISH, TURTWIG, CELEBI = 'SV3.Oddish_1', 'SV05.Turtwig_10', 'ME1.Celebi_12'
GROWING = 'ME3.GrowingGrassEnergy_86'
QUILAVA, MOLTRES = 'SWSH10.Quilava_24', 'SWSH9.Moltres_21'
ARTAZON = 'SV2.Artazon_171'
HIDING = 'SWSH3.HidingDarknessEnergy_175'


class Deck3Cards(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    # --- Oddish: Feelin' Fine ----------------------------------------------
    async def test_feelin_fine_draws_one(self):
        t = self.table()
        o = t.put(ODDISH, P1, 'active')
        t.energy(o, W)
        top = t.deck(P1, [MOLTRES])[0]
        await t.attack(o, "Feelin' Fine")
        self.assertEqual(t.zone(P1, 'hand'), [top])

    # --- Turtwig: Solid Shell ---------------------------------------------
    async def _hit_turtwig(self, where='active'):
        t = self.table()
        tw = t.put(TURTWIG, P1, where)
        if where == 'bench':
            t.put(self.filler, P1, 'active')
        t.next_turn()
        q = t.put(QUILAVA, P2, 'bench')
        t.energy(q, R, 2)
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(q.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        return t, tw, q

    async def test_solid_shell_after_weakness(self):
        t, tw, q = await self._hit_turtwig()
        await t.attack(q, 'Flare', P2)
        self.assertEqual(t.damage(tw), 40 * 2 - 20)

    async def test_solid_shell_does_not_reduce_own_side(self):
        # Opponent's Turtwig doesn't protect mine; my attack on their Turtwig is reduced.
        t = self.table()
        their = t.put(TURTWIG, P2, 'bench')
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(their.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        their.set_attribute(AttrID.WEAKNESS_TYPES, [])
        m = t.put(MOLTRES, P1, 'active')
        t.energy(m, R)
        await t.attack(m, 'Inferno Wings')
        self.assertEqual(t.damage(their), 0)                  # 20 - 20

    # --- Celebi: Traverse Time ----------------------------------------------
    async def test_traverse_time_grass_pokemon_and_stadiums(self):
        t = self.table()
        c = t.put(CELEBI, P1, 'active')
        t.energy(c, G)
        good = t.deck(P1, [ODDISH, TURTWIG, ARTAZON])
        bad = t.deck(P1, [MOLTRES, t.basic_energy(G), GROWING])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'], seen['count'] = list(cards), count
            return [x for x in cards if x in good][:count]
        t.picks = picks
        await t.attack(c, 'Traverse Time')
        self.assertEqual(seen['count'], 3)
        for b in bad:
            self.assertNotIn(b, seen['cards'])
        self.assertEqual(sorted(t.zone(P1, 'hand'), key=id), sorted(good, key=id))

    async def test_traverse_time_may_take_fewer(self):
        t = self.table()
        c = t.put(CELEBI, P1, 'active')
        t.energy(c, G)
        good = t.deck(P1, [ODDISH, ARTAZON])
        t.picks = lambda cards, count, prompt, display: [good[1]]
        await t.attack(c, 'Traverse Time')
        self.assertEqual(t.zone(P1, 'hand'), [good[1]])

    # --- Growing Grass Energy ----------------------------------------------
    async def test_growing_grass_hp_on_grass_pokemon(self):
        t = self.table()
        tw = t.put(TURTWIG, P1, 'active')
        e = t.put(GROWING, P1, 'hand')
        await t.play(e, targets=[tw.entity_id])
        self.assertIn(e, tw.children)
        self.assertEqual(effective_max_hp(t.board, tw), 100)
        self.assertEqual(t.hp(tw), 100)

    async def test_growing_grass_no_hp_on_non_grass(self):
        t = self.table()
        m = t.put(MOLTRES, P1, 'active')
        e = t.put(GROWING, P1, 'hand')
        await t.play(e, targets=[m.entity_id])
        self.assertIn(e, m.children)
        self.assertEqual(effective_max_hp(t.board, m), 120)

    async def test_growing_grass_provides_grass_for_cost(self):
        t = self.table()
        c = t.put(CELEBI, P1, 'active')
        e = t.put(GROWING, P1, 'hand')
        await t.play(e, targets=[c.entity_id])
        self.assertIsNotNone(t.attack_offer(c, 'Solar Cutter'))
        self.assertEqual(effective_max_hp(t.board, c), 100)

    async def test_growing_grass_not_fire(self):
        t = self.table()
        m = t.put(MOLTRES, P1, 'active')
        e = t.put(GROWING, P1, 'hand')
        await t.play(e, targets=[m.entity_id])
        self.assertIsNone(t.attack_offer(m, 'Inferno Wings'))

    async def test_growing_grass_hp_lost_when_moved_off(self):
        t = self.table()
        tw = t.put(TURTWIG, P1, 'active')
        e = t.put(GROWING, P1, 'hand')
        await t.play(e, targets=[tw.entity_id])
        t.board.move_card(e.entity_id, t.board.find_player_area(P1, 'discard').entity_id)
        self.assertEqual(effective_max_hp(t.board, tw), 80)
