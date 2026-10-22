"""Bug hunt round 2, deck 1 (Colorless): every Pokémon, checked against its
printed text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W = PokemonTypes.WATER          # pays [C]
TEDDIURSA, URSARING, URSALUNA = 'SWSH3.Teddiursa_138', 'SWSH7.Ursaring_127', 'SWSH10.Ursaluna_124'
PIDGEY, PIDGEOTTO = 'SV035.Pidgey_16', 'SM9.Pidgeotto_123'
SKITTY, DELCATTY = 'SV05.Skitty_130', 'SM7.Delcatty_121'
SNORLAX, DITTO, BUNNELBY, DUNSPARCE = 'SWSH4.Snorlax_131', 'BW7.Ditto_108', 'XY5.Bunnelby_121', 'SWSH8.Dunsparce_207'
SABLEYE = 'SV2.Sableye_136'     # a Darkness Basic
GUZMA, N = 'SM3.Guzma_115', 'XY10.N_105'
NEST = 'SV1.NestBall_181'


def name(card):
    return def_for(card.archetype_id).display_name


class Deck1Pokemon(unittest.IsolatedAsyncioTestCase):
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

    # --- Teddiursa: Baby-Doll Eyes -----------------------------------------
    async def test_baby_doll_eyes_blocks_retreat_next_turn_only(self):
        t = self.table()
        ted = t.put(TEDDIURSA, P1, 'active')
        t.energy(ted, W)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W, 4)
        await t.attack(ted, 'Baby-Doll Eyes')
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn(); t.next_turn()          # the lock is over
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))

    # --- Ursaluna -------------------------------------------------------------
    async def test_peat_hunt_up_to_two_cards(self):
        t = self.table()
        luna = t.put(URSALUNA, P1, 'active')
        t.energy(luna, W)
        for spec in (GUZMA, N, NEST):
            t.put(spec, P1, 'discard')
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', (len(cards), count)), cards[:count])[1]
        await t.attack(luna, 'Peat Hunt')
        self.assertEqual(seen['c'], (3, 2))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_bulky_bump_discards_two_energy(self):
        t = self.table()
        luna = t.put(URSALUNA, P1, 'active')
        t.energy(luna, W, 3)
        await t.attack(luna, 'Bulky Bump')
        self.assertEqual(400 - t.hp(self.opp), 200)
        self.assertEqual(len(t.board.attached_energies(luna)), 1)

    async def test_ursa_line_evolves(self):
        t = self.table()
        ted = t.put(TEDDIURSA, P1, 'active')
        ring = t.put(URSARING, P1, 'hand')
        await t.play(ring, targets=[ted.entity_id])
        self.assertEqual(name(t.active(P1)), 'Ursaring')

    # --- Pidgey: Call for Family ----------------------------------------------
    async def test_pidgey_call_for_family_up_to_two_basics(self):
        t = self.table()
        pidgey = t.put(PIDGEY, P1, 'active')
        t.energy(pidgey, W)
        t.deck(P1, [SABLEYE, SKITTY, TEDDIURSA, URSARING])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', (t.names(cards), count)), cards[:count])[1]
        await t.attack(pidgey, 'Call for Family')
        names, count = seen['c']
        self.assertEqual(count, 2)
        self.assertNotIn('Ursaring', names)
        self.assertEqual(len(t.zone(P1, 'bench')), 2)

    async def test_pidgey_call_for_family_bench_space(self):
        t = self.table()
        pidgey = t.put(PIDGEY, P1, 'active')
        t.energy(pidgey, W)
        for _ in range(4):
            t.put(self.filler, P1, 'bench')
        t.deck(P1, [SABLEYE, SKITTY, TEDDIURSA])
        await t.attack(pidgey, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Pidgeotto: Air Mail ----------------------------------------------------
    async def test_air_mail_top_two_one_to_hand_other_bottom(self):
        t = self.table()
        pidgeotto = t.put(PIDGEOTTO, P1, 'bench')
        a, b = t.deck(P1, [GUZMA, N])     # N is the top card
        seen = {}

        def picks(cards, count, prompt, display):
            seen['c'] = (sorted(t.names(cards)), count)
            return [c for c in cards if c is a][:1]
        t.picks = picks
        await t.use(pidgeotto, 'Air Mail')
        self.assertEqual(seen['c'], (['Guzma', 'N'], 1))
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Guzma'])
        deck = t.zone(P1, 'deck')
        self.assertIs(deck[0], b, 'the other card goes to the bottom')
        self.assertIsNone(t.ability_offer(pidgeotto, 'Air Mail'))

    # --- Skitty / Delcatty --------------------------------------------------------
    async def test_skitty_call_for_family_one_basic(self):
        t = self.table()
        skitty = t.put(SKITTY, P1, 'active')
        t.energy(skitty, W)
        t.deck(P1, [SABLEYE, TEDDIURSA, URSARING])
        await t.attack(skitty, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 1)
        self.assertNotEqual(name(t.zone(P1, 'bench')[0]), 'Ursaring')

    async def test_search_for_friends_two_supporters_on_evolve(self):
        t = self.table()
        skitty = t.put(SKITTY, P1, 'active')
        for spec in (GUZMA, N, NEST):
            t.put(spec, P1, 'discard')
        cat = t.put(DELCATTY, P1, 'hand')
        await t.play(cat, targets=[skitty.entity_id])
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Guzma', 'N'])

    async def test_search_for_friends_may_decline(self):
        t = self.table()
        for spec in (GUZMA, N):
            t.put(spec, P1, 'discard')
        skitty = t.put(SKITTY, P1, 'active')
        cat = t.put(DELCATTY, P1, 'hand')
        t.yes = False                       # "you may": declining keeps them in the discard
        await t.play(cat, targets=[skitty.entity_id])
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    # --- Snorlax: Gormandize ----------------------------------------------------
    async def test_gormandize_draws_to_seven_and_ends_turn(self):
        t = self.table()
        lax = t.put(SNORLAX, P1, 'active')
        t.put(self.item, P1, 'hand')
        over = await t.use(lax, 'Gormandize')
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        self.assertTrue(over, 'using Gormandize ends the turn')

    async def test_gormandize_active_only(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        lax = t.put(SNORLAX, P1, 'bench')
        self.assertIsNone(t.ability_offer(lax, 'Gormandize'))

    async def test_body_slam_paralyzes_on_heads(self):
        for heads in (True, False):
            t = self.table()
            lax = t.put(SNORLAX, P1, 'active')
            t.energy(lax, W, 4)
            t.heads = heads
            await t.attack(lax, 'Body Slam')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 100)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    # --- Ditto: Transform ----------------------------------------------------------
    async def test_transform_becomes_basic_keeps_attachments_and_damage(self):
        t = self.table()
        ditto = t.put(DITTO, P1, 'active', hp=50)
        energy = t.energy(ditto, W)
        sab = t.put(SABLEYE, P1, 'hand')
        await t.use(ditto, 'Transform')
        top = t.active(P1)
        self.assertEqual(name(top), 'Sableye')
        self.assertIn(energy, t.board.attached_energies(top))
        self.assertEqual(t.damage(top), 20)
        self.assertNotIn(sab, t.zone(P1, 'hand'))

    async def test_transform_needs_basic_in_hand(self):
        t = self.table()
        ditto = t.put(DITTO, P1, 'active')
        t.put(URSARING, P1, 'hand')        # an Evolution card doesn't qualify
        self.assertIsNone(t.ability_offer(ditto, 'Transform'))

    # --- Bunnelby: Burrow / Rototiller / Omega Barrage ------------------------
    async def test_burrow_discards_opponent_top_card(self):
        t = self.table()
        bun = t.put(BUNNELBY, P1, 'active')
        t.energy(bun, W)
        top = t.deck(P2, [GUZMA])[0]
        await t.attack(bun, 'Burrow')
        self.assertIn(top, t.zone(P2, 'discard'))
        self.assertEqual(t.zone(P1, 'discard'), [])

    async def test_omega_barrage_attacks_twice_then_stops(self):
        t = self.table()
        bun = t.put(BUNNELBY, P1, 'active')
        t.energy(bun, W)
        t.deck(P2, [GUZMA, N, NEST])
        self.assertFalse(await t.attack(bun, 'Burrow'))     # the turn goes on
        self.assertIsNotNone(t.attack_offer(bun, 'Burrow'))
        self.assertTrue(await t.attack(bun, 'Burrow'))      # the second attack ends it
        self.assertEqual(len(t.zone(P2, 'discard')), 2)

    async def test_rototiller_shuffles_discard_card_into_deck(self):
        t = self.table()
        bun = t.put(BUNNELBY, P1, 'active')
        t.energy(bun, W)
        card = t.put(GUZMA, P1, 'discard')
        await t.attack(bun, 'Rototiller')
        self.assertIn(card, t.zone(P1, 'deck'))
        self.assertEqual(t.zone(P1, 'discard'), [])

    # --- Dunsparce: Mysterious Nest ----------------------------------------------
    async def test_mysterious_nest_colorless_no_weakness_both_sides(self):
        from tests.bughunt_table import Table as _T  # noqa
        F = PokemonTypes.FIGHTING
        # opponent's Colorless active, weak to Fighting: no Weakness
        t = self.table()
        t.put(DUNSPARCE, P1, 'bench')
        attacker = t.put(SABLEYE, P1, 'active')
        attacker.set_attribute(AttrID.POKEMON_TYPES, [F.value])
        t.energy(attacker, PokemonTypes.DARKNESS)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        await t.attack(attacker, 'Unseen Claw')
        self.assertEqual(400 - t.hp(self.opp), 20)
        # Non-Colorless target keeps its Weakness
        t = self.table()
        t.put(DUNSPARCE, P1, 'bench')
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        target = t.put(SABLEYE, P2, 'active')
        target.set_attribute(AttrID.HP, 400)
        target.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        target.set_attribute(AttrID.RESISTANCE_TYPES, [])
        attacker = t.put(SABLEYE, P1, 'active')
        attacker.set_attribute(AttrID.POKEMON_TYPES, [F.value])
        t.energy(attacker, PokemonTypes.DARKNESS)
        await t.attack(attacker, 'Unseen Claw')
        self.assertEqual(400 - t.hp(target), 40)

    async def test_mysterious_nest_protects_own_colorless_too(self):
        F = PokemonTypes.FIGHTING
        t = self.table()
        t.put(DUNSPARCE, P2, 'bench')        # the opponent's Dunsparce
        attacker = t.put(SABLEYE, P1, 'active')
        attacker.set_attribute(AttrID.POKEMON_TYPES, [F.value])
        t.energy(attacker, PokemonTypes.DARKNESS)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        await t.attack(attacker, 'Unseen Claw')
        self.assertEqual(400 - t.hp(self.opp), 20)


if __name__ == "__main__":
    unittest.main()
