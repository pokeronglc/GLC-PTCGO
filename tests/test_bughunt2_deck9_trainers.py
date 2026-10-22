"""Bug hunt round 2, deck 9 (Grass): Supporters, Tools and Special Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

G, W, F = PokemonTypes.GRASS, PokemonTypes.WATER, PokemonTypes.FIGHTING
APPLIN, HOPPIP, SKIPLOOM, JUMPLUFF = ('SWSH2.Applin_21', 'SWSH7.Hoppip_2',
                                      'SWSH7.Skiploom_3', 'SWSH7.Jumpluff_4')
ROWLET, DARTRIX = 'SV065.Rowlet_3', 'SV3.Dartrix_14'
AVERY, ROSEANNE = 'SWSH6.Avery_130', 'SWSH9.RoseannesBackup_148'
SCROLL, TM_DEVO = 'SWSH5.RapidStrikeScrollofSwirls_131', 'SV4.TechnicalMachineDevolution_177'
RSE = 'SWSH5.RapidStrikeEnergy_140'
FLOAT, ARTAZON, NEST = 'XY8.FloatStone_137', 'SV2.Artazon_171', 'SV1.NestBall_181'


class Deck9Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=True):
        t = Table(self)
        if me:
            self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    async def evolve(self, t, base, spec):
        card = t.put(spec, base.owning_player_id, 'hand')
        await t._run(lambda: t.session.perform_evolution(base.owning_player_id, card, base))
        return card

    # --- Avery ------------------------------------------------------------
    async def test_avery_draw_three_and_opponent_bench_to_three(self):
        t = self.table()
        bench = [t.put(self.filler, P2, 'bench') for _ in range(5)]
        mine = [t.put(self.filler, P1, 'bench') for _ in range(5)]
        await t.play(t.put(AVERY, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(len(t.zone(P2, 'bench')), 3)
        self.assertEqual(len(t.zone(P1, 'bench')), 5)      # my Bench untouched
        self.assertEqual(len([c for c in t.zone(P2, 'discard') if c in bench]), 2)

    async def test_avery_small_bench_untouched(self):
        t = self.table()
        for _ in range(3):
            t.put(self.filler, P2, 'bench')
        await t.play(t.put(AVERY, P1, 'hand'))
        self.assertEqual(len(t.zone(P2, 'bench')), 3)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    # --- Roseanne's Backup -----------------------------------------------
    async def test_roseannes_backup_one_of_each_category(self):
        t = self.table()
        cards = [t.put(s, P1, 'discard') for s in (ROWLET, FLOAT, ARTAZON, RSE)]
        item = t.put(NEST, P1, 'discard')
        await t.play(t.put(ROSEANNE, P1, 'hand'))
        deck = t.zone(P1, 'deck')
        for c in cards:
            self.assertIn(c, deck)
        self.assertIn(item, t.zone(P1, 'discard'))

    async def test_roseannes_backup_choose_only_energy(self):
        t = self.table()
        rowlet = t.put(ROWLET, P1, 'discard')
        energy = t.put(t.basic_energy(G), P1, 'discard')
        t.yes = lambda prompt: 'Energy' in prompt
        await t.play(t.put(ROSEANNE, P1, 'hand'))
        self.assertIn(energy, t.zone(P1, 'deck'))
        self.assertIn(rowlet, t.zone(P1, 'discard'))

    async def test_roseannes_backup_needs_a_target(self):
        t = self.table()
        t.put(NEST, P1, 'discard')          # Items don't count
        card = t.put(ROSEANNE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Rapid Strike Scroll of Swirls ----------------------------------
    async def test_matchless_maelstrom_on_rapid_strike(self):
        t = self.table(me=False)
        hoppip = t.put(HOPPIP, P1, 'active')
        t.energy(hoppip, F, 3)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        mine = t.put(self.filler, P1, 'bench')
        await t.play(t.put(SCROLL, P1, 'hand'), targets=[hoppip.entity_id])
        before = t.hp(bench)
        await t.attack(hoppip, 'Matchless Maelstrom')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertEqual(before - t.hp(bench), 30)
        self.assertEqual(t.damage(mine), 0)

    # Was a bug (fixed Oct 10): the Rapid Strike holder condition is ignored (no usage_restriction flag), any holder can attack
    async def test_matchless_maelstrom_not_on_non_rapid_strike(self):
        t = self.table(me=False)
        applin = t.put(APPLIN, P1, 'active')
        t.energy(applin, F, 3)
        await t.play(t.put(SCROLL, P1, 'hand'), targets=[applin.entity_id])
        self.assertIsNone(t.attack_offer(applin, 'Matchless Maelstrom'))

    # --- Technical Machine: Devolution ----------------------------------
    async def test_tm_devolution_devolves_each_evolved(self):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        hop_a = t.put(HOPPIP, P2, 'active')
        skip_a = await self.evolve(t, hop_a, SKIPLOOM)
        hop_b = t.put(HOPPIP, P2, 'bench')
        skip_b = await self.evolve(t, hop_b, SKIPLOOM)
        jump_b = await self.evolve(t, skip_b, JUMPLUFF)
        basic = t.put(ROWLET, P2, 'bench')
        my_hop = t.put(HOPPIP, P1, 'bench')
        my_skip = await self.evolve(t, my_hop, SKIPLOOM)
        t.energy(self.me, W)
        await t.play(t.put(TM_DEVO, P1, 'hand'), targets=[self.me.entity_id])
        await t.attack(self.me, 'Devolution')
        hand = t.zone(P2, 'hand')
        self.assertEqual(set(t.names(hand)), {'Skiploom', 'Jumpluff'})
        self.assertEqual(len(hand), 2)
        self.assertEqual(sorted(t.names(t.board.pokemon_in_play(P2))),
                         ['Hoppip', 'Rowlet', 'Skiploom'])
        self.assertIn('Skiploom', t.names(t.board.pokemon_in_play(P1)))  # mine untouched

    async def test_tm_devolution_discarded_end_of_turn(self):
        t = self.table()
        tm = t.put(TM_DEVO, P1, 'hand')
        await t.play(tm, targets=[self.me.entity_id])
        self.assertIn(tm, self.me.children)
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        self.assertIn(tm, t.zone(P1, 'discard'))

    # --- Rapid Strike Energy -------------------------------------------
    async def test_rapid_strike_energy_two_water_fighting_rapid_strike_only(self):
        t = self.table(me=False)
        hoppip = t.put(HOPPIP, P1, 'active')
        applin = t.put(APPLIN, P1, 'bench')
        energy = t.put(RSE, P1, 'hand')
        targets = t.targets(energy, 'DefaultEnergyPlayAbility')
        self.assertIn(hoppip.entity_id, targets)
        self.assertNotIn(applin.entity_id, targets)
        await t.play(energy, targets=[hoppip.entity_id])
        self.assertIsNone(t.attack_offer(hoppip, 'Continuous Spin'))   # no Grass
        t.energy(hoppip, W)
        await t.play(t.put(SCROLL, P1, 'hand'), targets=[hoppip.entity_id])
        # [F][C][C] paid by Rapid Strike Energy (2) + 1 Water
        self.assertIsNotNone(t.attack_offer(hoppip, 'Matchless Maelstrom'))


if __name__ == "__main__":
    unittest.main()
