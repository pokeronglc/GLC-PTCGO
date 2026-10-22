"""Bug hunt round 2, deck 10 (Darkness): Supporters and Items, through the
real play-trainer executor (so play conditions apply)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

D, W = PokemonTypes.DARKNESS, PokemonTypes.WATER
GRIMSLEY, MALLOW_LANA = 'ME2.GrimsleysMove_90', 'SM12.MallowLana_198'
MAX_REVIVE, ICE_CREAM = 'XY1.MaxRevive_120', 'ME2.JumboIceCream_91'
TRANSCEIVER = 'SV10.TeamRocketsTransceiver_178'
ARIANA, GUZMA = 'SV10.TeamRocketsAriana_171', 'SM3.Guzma_115'
ZUBAT, CROBAT, SABLEYE = 'SV065.Zubat_27', 'ME4.Crobat_51', 'BW5.Sableye_62'
LELE = 'Promo_SM.TapuLele_152'
NEST = 'SV1.NestBall_181'


class Deck10Trainers2(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Grimsley's Move ---------------------------------------------------
    async def test_grimsleys_move_benches_darkness_basic_from_top_seven(self):
        t = self.table()
        # top of deck = last children; add 6 then the Darkness Basic among them
        zubat = t.deck(P1, [ZUBAT])[0]
        t.deck(P1, [NEST] * 6)
        await t.play(t.put(GRIMSLEY, P1, 'hand'))
        self.assertIn(zubat, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'deck')), 36)

    async def test_grimsleys_move_skips_non_darkness_and_eighth_card(self):
        t = self.table()
        deep = t.deck(P1, [ZUBAT])[0]                  # 8th from the top
        lele = t.deck(P1, [LELE])[0]                   # non-Darkness Basic
        t.deck(P1, [NEST] * 6)
        seen = {}

        def picks(cards, count, prompt, display):
            seen.setdefault('cards', []).extend(cards)
            return cards[:count]
        t.picks = picks
        await t.play(t.put(GRIMSLEY, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'bench'), [])
        self.assertNotIn(deep, seen.get('cards', []))
        self.assertNotIn(lele, seen.get('cards', []))

    async def test_grimsleys_move_any_darkness_pokemon_even_stage_2(self):
        # RULING?: the printed text says "a Darkness Pokémon" (not "Basic"),
        # which reads as allowing Evolution Pokémon; the engine allows it.
        t = self.table()
        crobat = t.deck(P1, [CROBAT])[0]
        t.deck(P1, [NEST] * 3)
        await t.play(t.put(GRIMSLEY, P1, 'hand'))
        self.assertIn(crobat, t.zone(P1, 'bench'))

    async def test_grimsleys_move_not_on_first_turn(self):
        t = self.table()
        t.deck(P1, [ZUBAT])
        card = t.put(GRIMSLEY, P1, 'hand')
        t.state.turn_number = 1
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.state.turn_number = 3
        self.assertTrue(t.can(card, 'UseTrainerCard'))

    async def test_grimsleys_move_rest_goes_to_bottom(self):
        t = self.table()
        top = t.deck(P1, [LELE] + [NEST] * 6)
        bottom_before = t.zone(P1, 'deck')[0]
        await t.play(t.put(GRIMSLEY, P1, 'hand'))
        deck = t.zone(P1, 'deck')
        self.assertEqual(set(deck[:7]), set(top))       # looked-at 7 now at the bottom
        self.assertIsNot(deck[0], bottom_before)

    # --- Mallow & Lana -----------------------------------------------------
    async def test_mallow_lana_switch_and_heal_after_discarding_two(self):
        t = self.table()
        self.me.set_attribute(AttrID.HP, t.hp(self.me) - 150)
        bench = t.put(SABLEYE, P1, 'bench')
        a = t.put(NEST, P1, 'hand'); b = t.put(NEST, P1, 'hand')
        t.yes = True
        await t.play(t.put(MALLOW_LANA, P1, 'hand'))
        self.assertIs(t.active(P1), bench)
        self.assertEqual(t.damage(self.me), 30)
        self.assertIn(a, t.zone(P1, 'discard'))
        self.assertIn(b, t.zone(P1, 'discard'))

    async def test_mallow_lana_no_heal_without_discard(self):
        t = self.table()
        self.me.set_attribute(AttrID.HP, t.hp(self.me) - 150)
        bench = t.put(SABLEYE, P1, 'bench')
        t.put(NEST, P1, 'hand')                      # only one other card
        await t.play(t.put(MALLOW_LANA, P1, 'hand'))
        self.assertIs(t.active(P1), bench)
        self.assertEqual(t.damage(self.me), 150)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_mallow_lana_needs_a_benched_pokemon(self):
        t = self.table()
        card = t.put(MALLOW_LANA, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Max Revive ----------------------------------------------------------
    async def test_max_revive_puts_pokemon_on_top_of_deck(self):
        t = self.table()
        mon = t.put(ZUBAT, P1, 'discard')
        t.put(NEST, P1, 'discard')
        await t.play(t.put(MAX_REVIVE, P1, 'hand'))
        self.assertIs(t.zone(P1, 'deck')[-1], mon)
        self.assertNotIn(mon, t.zone(P1, 'hand'))

    async def test_max_revive_needs_pokemon_in_discard(self):
        t = self.table()
        t.put(NEST, P1, 'discard')
        card = t.put(MAX_REVIVE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Jumbo Ice Cream -----------------------------------------------------
    async def test_jumbo_ice_cream_heals_80_with_three_energy(self):
        t = self.table()
        t.energy(self.me, W, 3)
        self.me.set_attribute(AttrID.HP, t.hp(self.me) - 100)
        await t.play(t.put(ICE_CREAM, P1, 'hand'))
        self.assertEqual(t.damage(self.me), 20)

    async def test_jumbo_ice_cream_not_with_two_energy(self):
        t = self.table()
        t.energy(self.me, W, 2)
        self.me.set_attribute(AttrID.HP, t.hp(self.me) - 100)
        self.assertFalse(t.can(t.put(ICE_CREAM, P1, 'hand'), 'UseTrainerCard'))

    async def test_jumbo_ice_cream_not_for_benched(self):
        t = self.table()
        bench = t.put(SABLEYE, P1, 'bench')
        t.energy(bench, D, 3)
        bench.set_attribute(AttrID.HP, t.hp(bench) - 30)
        self.assertFalse(t.can(t.put(ICE_CREAM, P1, 'hand'), 'UseTrainerCard'))

    # --- Team Rocket's Transceiver -----------------------------------------
    async def test_transceiver_finds_team_rocket_supporter_only(self):
        t = self.table()
        t.deck(P1, [GUZMA, ARIANA, NEST])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'] = t.names(cards)
            return cards[:count]
        t.picks = picks
        await t.play(t.put(TRANSCEIVER, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ["Team Rocket's Ariana"])
        self.assertNotIn('Guzma', seen['names'])

    async def test_transceiver_finds_nothing_without_one(self):
        t = self.table()
        t.deck(P1, [GUZMA])
        await t.play(t.put(TRANSCEIVER, P1, 'hand'))
        self.assertEqual(self.hand_names(t), [])


if __name__ == '__main__':
    unittest.main()
