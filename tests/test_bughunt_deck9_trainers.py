"""Bug hunt, deck 9 (Fire): Supporters, Items, Tool and Stadiums, through the
real executor."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

R, M = PokemonTypes.FIRE, PokemonTypes.METAL
SALANDIT, SALAZZLE = 'CZ.Salandit_27', 'SM10.Salazzle_31'
SLUGMA, MAGCARGO = 'SM7.Slugma_23', 'SM7.Magcargo_24'
TORCHIC, COMBUSKEN = 'XY5.Torchic_26', 'SWSH3.Combusken_23'
CHIYU, BRONZOR = 'SV4.ChiYu_29', 'SV3.Bronzor_144'
WELDER, BIRD_KEEPER, LANA, BLACKSMITH = ('SM10.Welder_189', 'SWSH3.BirdKeeper_159',
                                         'SV06.LanasAid_155', 'XY2.Blacksmith_88')
FIRE_CRYSTAL, RED_CARD = 'SM10.FireCrystal_173', 'XY1.RedCard_124'
TM_EVO, POKESTOP, MAGMA = 'SV4.TechnicalMachineEvolution_178', 'PGO.PokStop_68', 'SWSH9.MagmaBasin_144'
MAGNETIC, NEST = 'ME4.MagneticMetalEnergy_85', 'SV1.NestBall_181'


class Deck9Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=None):
        t = Table(self)
        self.me = t.put(me or CHIYU, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    # --- Welder ---------------------------------------------------------------
    async def test_welder_two_fire_then_draw_three_not_the_turn_attach(self):
        t = self.table()
        fires = [t.put(t.basic_energy(R), P1, 'hand') for _ in range(3)]
        await t.play(t.put(WELDER, P1, 'hand'))
        attached = [f for f in fires if f in self.me.children]
        self.assertEqual(len(attached), 2)
        self.assertEqual(len(t.zone(P1, 'hand')), 1 + 3)
        # Welder's attachments are not the once-per-turn attachment from hand
        left = next(f for f in fires if f not in self.me.children)
        self.assertTrue(t.can(left, 'DefaultEnergyPlayAbility'))

    async def test_welder_without_fire_energy_no_draw(self):
        t = self.table()
        t.put(t.basic_energy(M), P1, 'hand')
        card = t.put(WELDER, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
            self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.board.attached_energies(self.me)), 0)

    # --- Bird Keeper -------------------------------------------------------
    async def test_bird_keeper_switch_and_draw_three(self):
        t = self.table()
        bench = t.put(SLUGMA, P1, 'bench')
        await t.play(t.put(BIRD_KEEPER, P1, 'hand'))
        self.assertIs(t.active(P1), bench)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_bird_keeper_needs_bench(self):
        t = self.table()
        self.assertFalse(t.can(t.put(BIRD_KEEPER, P1, 'hand'), 'UseTrainerCard'))

    # --- Lana's Aid -----------------------------------------------------------
    async def test_lanas_aid_pokemon_and_basic_energy_only(self):
        t = self.table()
        slugma = t.put(SLUGMA, P1, 'discard')
        fire = t.put(t.basic_energy(R), P1, 'discard')
        special = t.put(MAGNETIC, P1, 'discard')
        nest = t.put(NEST, P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['c'], seen['count'] = list(cards), count
            return cards[:count]
        t.picks = picks
        await t.play(t.put(LANA, P1, 'hand'))
        self.assertEqual(seen['count'], 3)
        self.assertNotIn(special, seen['c'])
        self.assertNotIn(nest, seen['c'])
        self.assertIn(slugma, t.zone(P1, 'hand'))
        self.assertIn(fire, t.zone(P1, 'hand'))

    async def test_lanas_aid_unplayable_without_targets(self):
        t = self.table()
        t.put(MAGNETIC, P1, 'discard')
        t.put(NEST, P1, 'discard')
        self.assertFalse(t.can(t.put(LANA, P1, 'hand'), 'UseTrainerCard'))

    # --- Blacksmith -------------------------------------------------------
    async def test_blacksmith_two_fire_to_fire_pokemon(self):
        t = self.table(me=BRONZOR)                    # Metal Active
        fire_mon = t.put(SLUGMA, P1, 'bench')
        for _ in range(3):
            t.put(t.basic_energy(R), P1, 'discard')
        offered = {}
        t.pokemon = lambda c, p: (offered.setdefault('p', t.names(c)), c[0])[1]
        await t.play(t.put(BLACKSMITH, P1, 'hand'))
        self.assertEqual(offered.get('p', ['Slugma']), ['Slugma'])
        self.assertEqual(len(t.board.attached_energies(fire_mon)), 2)
        self.assertEqual(len(t.board.attached_energies(self.me)), 0)

    async def test_blacksmith_needs_fire_pokemon(self):
        t = self.table(me=BRONZOR)
        for _ in range(2):
            t.put(t.basic_energy(R), P1, 'discard')
        card = t.put(BLACKSMITH, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertEqual(len(t.board.attached_energies(self.me)), 0)

    # --- Fire Crystal -------------------------------------------------------
    async def test_fire_crystal_three_fire_from_discard(self):
        t = self.table()
        fires = [t.put(t.basic_energy(R), P1, 'discard') for _ in range(4)]
        metal = t.put(t.basic_energy(M), P1, 'discard')
        await t.play(t.put(FIRE_CRYSTAL, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertNotIn(metal, hand)

    async def test_fire_crystal_needs_fire_in_discard(self):
        t = self.table()
        t.put(t.basic_energy(M), P1, 'discard')
        self.assertFalse(t.can(t.put(FIRE_CRYSTAL, P1, 'hand'), 'UseTrainerCard'))

    # --- Red Card ------------------------------------------------------------
    async def test_red_card_opponent_shuffles_and_draws_four(self):
        t = self.table()
        old = [t.put(SLUGMA, P2, 'hand') for _ in range(7)]
        mine = [t.put(SLUGMA, P1, 'hand') for _ in range(2)]
        await t.play(t.put(RED_CARD, P1, 'hand'))
        self.assertEqual(len(t.zone(P2, 'hand')), 4)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        deck = t.zone(P2, 'deck')
        self.assertTrue(all(c in deck or c in t.zone(P2, 'hand') for c in old))

    # --- Technical Machine: Evolution -----------------------------------------
    async def test_tm_evolution_evolves_two_benched_and_is_discarded(self):
        t = self.table()
        sal = t.put(SALANDIT, P1, 'bench')
        slug = t.put(SLUGMA, P1, 'bench')
        tor = t.put(TORCHIC, P1, 'bench')
        t.deck(P1, [SALAZZLE, MAGCARGO, COMBUSKEN])
        t.energy(self.me, R)
        tm = t.put(TM_EVO, P1, 'hand')
        await t.play(tm, targets=[self.me.entity_id])
        self.assertIn(tm, self.me.children)
        t.picks = lambda cards, count, prompt, display: (
            [c for c in cards if c in (sal, slug)] or cards[:count])[:count]
        self.assertIsNotNone(t.attack_offer(self.me, 'Evolution'))
        await t.attack(self.me, 'Evolution')
        names = t.names(t.board.pokemon_in_play(P1))
        self.assertEqual(sum(n in ('Salazzle', 'Magcargo', 'Combusken') for n in names), 2)
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        self.assertIn(tm, t.zone(P1, 'discard'))

    async def test_tm_evolution_needs_energy(self):
        t = self.table()
        t.put(SALANDIT, P1, 'bench')
        tm = t.put(TM_EVO, P1, 'hand')
        await t.play(tm, targets=[self.me.entity_id])
        self.assertIsNone(t.attack_offer(self.me, 'Evolution'))

    # --- PokéStop -------------------------------------------------------------
    async def test_pokestop_items_to_hand_once_each_player(self):
        t = self.table()
        stop = t.stadium(POKESTOP, P2)
        t.deck(P1, [NEST, SLUGMA, t.basic_energy(R)])     # top 3 (filler deck is Items too)
        await t.do(self.stadium_action(t, stop))
        hand = t.zone(P1, 'hand')
        self.assertEqual(t.names(hand), ['Nest Ball'])
        self.assertEqual(len(t.zone(P1, 'discard')), 2)
        self.assertIsNone(self.stadium_action(t, stop))
        t.next_turn()
        self.assertIsNotNone(self.stadium_action(t, stop, P2))

    # --- Magma Basin ---------------------------------------------------------
    async def test_magma_basin_benched_fire_and_two_counters(self):
        t = self.table()
        basin = t.stadium(MAGMA, P2)
        slug = t.put(SLUGMA, P1, 'bench')
        bronzor = t.put(BRONZOR, P1, 'bench')
        fire = t.put(t.basic_energy(R), P1, 'discard')
        offered = {}
        t.pokemon = lambda c, p: (offered.setdefault('p', list(c)), slug if slug in c else c[0])[1]
        await t.do(self.stadium_action(t, basin))
        self.assertNotIn(self.me, offered['p'])          # Active isn't Benched
        self.assertNotIn(bronzor, offered['p'])          # not Fire
        self.assertIn(fire, slug.children)
        self.assertEqual(t.damage(slug), 20)
        t.put(t.basic_energy(R), P1, 'discard')
        self.assertIsNone(self.stadium_action(t, basin))

    async def test_magma_basin_no_benched_fire(self):
        t = self.table()
        basin = t.stadium(MAGMA, P1)
        t.put(BRONZOR, P1, 'bench')
        t.put(t.basic_energy(R), P1, 'discard')
        self.assertIsNone(self.stadium_action(t, basin))


if __name__ == "__main__":
    unittest.main()
