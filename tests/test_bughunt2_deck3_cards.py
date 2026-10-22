"""Bug hunt round 2, deck 3 (Dragon): Reshiram, Regidrago and the Trainers."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

R, L, W, G = PokemonTypes.FIRE, PokemonTypes.LIGHTNING, PokemonTypes.WATER, PokemonTypes.GRASS
RESHIRAM, REGIDRAGO = 'XY6.Reshiram_63', 'SWSH10.Regidrago_118'
TEDDIURSA, URSARING = 'SWSH3.Teddiursa_138', 'SWSH7.Ursaring_127'
SABLEYE = 'SV2.Sableye_136'
SWITCH_CART, MAX_ELIXIR, ACRO = 'SWSH10.SwitchCart_154', 'XY9.MaxElixir_102', 'SM7.AcroBike_123'
LANA, BAG, SWITCH, FOREST = 'SM12.LanasFishingRod_195', 'SM8.AdventureBag_167', 'ME1.Switch_130', 'SM9.ViridianForest_156'
FLOAT, GUZMA, N, NEST = 'XY8.FloatStone_137', 'SM3.Guzma_115', 'XY10.N_105', 'SV1.NestBall_181'
SPECIAL_ENERGY = 'SWSH3.HidingDarknessEnergy_175'


def name(card):
    return def_for(card.archetype_id).display_name


class Deck3Cards(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=None):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        self.me = t.put(me or self.filler, P1, 'active')
        return t

    # --- Reshiram: Turboblaze -------------------------------------------------
    async def test_turboblaze_fire_from_hand_to_dragon(self):
        t = self.table(RESHIRAM)
        drago = t.put(REGIDRAGO, P1, 'bench')
        other = t.put(self.filler, P1, 'bench')
        fire = t.put(t.basic_energy(R), P1, 'hand')
        offered = {}
        t.pokemon = lambda c, p: (offered.setdefault('c', set(c)), drago if drago in c else c[0])[1]
        await t.use(self.me, 'Turboblaze')
        self.assertIn(fire, t.board.attached_energies(drago))
        self.assertNotIn(other, offered.get('c', set()), 'only Dragon Pokémon may receive it')
        self.assertIsNone(t.ability_offer(self.me, 'Turboblaze'))      # once per turn

    async def test_turboblaze_only_fire_and_only_active(self):
        t = self.table(RESHIRAM)
        t.put(t.basic_energy(W), P1, 'hand')
        self.assertIsNone(t.ability_offer(self.me, 'Turboblaze'), 'no Fire Energy in hand')
        t = self.table()
        resh = t.put(RESHIRAM, P1, 'bench')
        t.put(t.basic_energy(R), P1, 'hand')
        self.assertIsNone(t.ability_offer(resh, 'Turboblaze'), 'Benched Reshiram')

    async def test_turboblaze_does_not_use_manual_attachment(self):
        t = self.table(RESHIRAM)
        t.put(t.basic_energy(R), P1, 'hand')
        await t.use(self.me, 'Turboblaze')
        second = t.put(t.basic_energy(R), P1, 'hand')
        self.assertTrue(t.offers(second, 'DefaultEnergyPlayAbility'))

    async def test_bright_wing_discards_a_fire_energy(self):
        t = self.table(RESHIRAM)
        fires = t.energy(self.me, R, 2)
        t.energy(self.me, L)
        t.energy(self.me, W)
        await t.attack(self.me, 'Bright Wing')
        self.assertEqual(400 - t.hp(self.opp), 110)
        left = t.board.attached_energies(self.me)
        self.assertEqual(len(left), 3)
        self.assertEqual(len([e for e in fires if e in t.zone(P1, 'discard')]), 1)

    # --- Regidrago: Dragon's Hoard ------------------------------------------------
    async def test_dragons_hoard_draws_to_four_active_only(self):
        t = self.table(REGIDRAGO)
        t.put(self.item, P1, 'hand')
        await t.use(self.me, "Dragon's Hoard")
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        t = self.table()
        bench = t.put(REGIDRAGO, P1, 'bench')
        self.assertIsNone(t.ability_offer(bench, "Dragon's Hoard"))

    async def test_dragons_hoard_one_per_turn_across_regidrago(self):
        t = self.table(REGIDRAGO)
        first = self.me
        second = t.put(REGIDRAGO, P1, 'bench')
        await t.use(first, "Dragon's Hoard")
        for _ in range(3):                      # back under 4 cards
            t.board.move_card(t.zone(P1, 'hand')[0].entity_id,
                              t.board.find_player_area(P1, 'discard').entity_id)
        await t.play(t.put(SWITCH, P1, 'hand'))
        self.assertIs(t.active(P1), second)
        self.assertIsNone(t.ability_offer(second, "Dragon's Hoard"))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.ability_offer(second, "Dragon's Hoard"))

    async def test_dragons_hoard_not_with_four_cards(self):
        t = self.table(REGIDRAGO)
        for _ in range(4):
            t.put(self.item, P1, 'hand')
        self.assertIsNone(t.ability_offer(self.me, "Dragon's Hoard"))

    # --- Switch Cart ---------------------------------------------------------------
    async def test_switch_cart_switches_basic_and_heals_30(self):
        t = self.table()
        self.me.set_attribute(AttrID.HP, t.hp(self.me) - 50)
        bench = t.put(SABLEYE, P1, 'bench', hp=30)
        await t.play(t.put(SWITCH_CART, P1, 'hand'))
        self.assertIs(t.active(P1), bench)
        self.assertEqual(t.damage(self.me), 20)
        self.assertEqual(t.damage(bench), 40)            # the new Active isn't healed

    async def test_switch_cart_needs_basic_active_and_bench(self):
        t = self.table(URSARING)
        t.put(SABLEYE, P1, 'bench')
        self.assertFalse(t.can(t.put(SWITCH_CART, P1, 'hand'), 'UseTrainerCard'))
        t = self.table()
        self.assertFalse(t.can(t.put(SWITCH_CART, P1, 'hand'), 'UseTrainerCard'))

    # --- Max Elixir -----------------------------------------------------------------
    async def test_max_elixir_basic_energy_to_benched_basic(self):
        t = self.table()
        basic = t.put(SABLEYE, P1, 'bench')
        evo = t.put(URSARING, P1, 'bench')
        energy = t.deck(P1, [t.basic_energy(R), SPECIAL_ENERGY, GUZMA, N, NEST, FLOAT])[0]
        seen = {}
        t.picks = lambda cards, count, prompt, display: (
            seen.setdefault('c', (t.names(cards), len(display or []))), cards[:1])[1]
        targets = {}
        t.pokemon = lambda c, p: (targets.setdefault('c', list(c)), c[0])[1]
        await t.play(t.put(MAX_ELIXIR, P1, 'hand'))
        names, shown = seen['c']
        self.assertEqual(shown, 6)
        self.assertNotIn('Hiding Darkness Energy', names)
        self.assertIn(energy, t.board.attached_energies(basic))
        self.assertNotIn(evo, targets.get('c', []))
        self.assertNotIn(self.me, targets.get('c', []))
        self.assertEqual(len(t.zone(P1, 'deck')), 35)

    async def test_max_elixir_needs_benched_basic(self):
        t = self.table()
        t.put(URSARING, P1, 'bench')
        t.deck(P1, [t.basic_energy(R)])
        self.assertFalse(t.can(t.put(MAX_ELIXIR, P1, 'hand'), 'UseTrainerCard'))

    # --- Acro Bike ----------------------------------------------------------------------
    async def test_acro_bike_one_to_hand_other_discarded(self):
        t = self.table()
        g, n = t.deck(P1, [GUZMA, N])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', (len(cards), count)), [c for c in cards if c is g])[1]
        await t.play(t.put(ACRO, P1, 'hand'))
        self.assertEqual(seen['c'], (2, 1))
        self.assertEqual(t.zone(P1, 'hand'), [g])
        self.assertIn(n, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Lana's Fishing Rod ------------------------------------------------------------
    async def test_lanas_rod_pokemon_and_tool(self):
        t = self.table()
        poke = t.put(SABLEYE, P1, 'discard')
        tool = t.put(FLOAT, P1, 'discard')
        other = t.put(GUZMA, P1, 'discard')
        await t.play(t.put(LANA, P1, 'hand'))
        deck = t.zone(P1, 'deck')
        self.assertIn(poke, deck)
        self.assertIn(tool, deck)
        self.assertIn(other, t.zone(P1, 'discard'))

    async def test_lanas_rod_nothing_to_shuffle(self):
        t = self.table()
        t.put(GUZMA, P1, 'discard')
        self.assertFalse(t.can(t.put(LANA, P1, 'hand'), 'UseTrainerCard'))

    async def test_lanas_rod_only_pokemon_in_discard(self):
        # RULING?: playable with just one of the two kinds? Expect yes (do as much as you can).
        t = self.table()
        poke = t.put(SABLEYE, P1, 'discard')
        card = t.put(LANA, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertIn(poke, t.zone(P1, 'deck'))

    # --- Adventure Bag --------------------------------------------------------------------
    async def test_adventure_bag_up_to_two_tools(self):
        t = self.table()
        t.deck(P1, [FLOAT, FLOAT, FLOAT, NEST, SABLEYE])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', (t.names(cards), count)), cards[:count])[1]
        await t.play(t.put(BAG, P1, 'hand'))
        names, count = seen['c']
        self.assertEqual(count, 2)
        self.assertEqual(set(names), {'Float Stone'})
        self.assertEqual(self.hand_names(t), ['Float Stone', 'Float Stone'])

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Switch ------------------------------------------------------------------------------
    async def test_switch(self):
        t = self.table(URSARING)                         # any Active, Evolution included
        bench = t.put(SABLEYE, P1, 'bench')
        await t.play(t.put(SWITCH, P1, 'hand'))
        self.assertIs(t.active(P1), bench)
        t = self.table()
        self.assertFalse(t.can(t.put(SWITCH, P1, 'hand'), 'UseTrainerCard'))

    # --- Viridian Forest ----------------------------------------------------------------------
    async def _forest_entry(self, t, stadium, pid):
        offers = t.offers(stadium, None, pid)
        return next(iter(offers), None)

    async def test_viridian_forest_discard_one_for_basic_energy_each_player(self):
        t = self.table()
        stadium = t.stadium(FOREST, P2)                   # the opponent's Stadium works for me too
        fire = t.deck(P1, [t.basic_energy(R), SPECIAL_ENERGY])[0]
        junk = t.put(GUZMA, P1, 'hand')
        entry = await self._forest_entry(t, stadium, P1)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P1)
        self.assertIn(junk, t.zone(P1, 'discard'))
        self.assertEqual(t.zone(P1, 'hand'), [fire])
        self.assertIsNone(await self._forest_entry(t, stadium, P1), 'once per turn')
        t.next_turn()
        t.put(GUZMA, P2, 'hand')
        t.deck(P2, [t.basic_energy(W)])
        self.assertIsNotNone(await self._forest_entry(t, stadium, P2))

    async def test_viridian_forest_needs_a_card_to_discard(self):
        t = self.table()
        stadium = t.stadium(FOREST, P1)
        t.deck(P1, [t.basic_energy(R)])
        self.assertIsNone(await self._forest_entry(t, stadium, P1))


if __name__ == "__main__":
    unittest.main()
