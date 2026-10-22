"""Bug hunt round 2, deck 8 (Fire): Supporter, Items, Tool and Stadiums."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

R, W = PokemonTypes.FIRE, PokemonTypes.WATER
CHARMANDER, CHARMELEON = 'SWSH4.Charmander_23', 'ME2PT5.Charmeleon_21'
LITWICK, LAMPENT, CHANDELURE = 'SWSH11.Litwick_24', 'SWSH2.Lampent_32', 'SV06.Chandelure_38'
SIZZLIPEDE, CENTISKORCH = 'SWSH8.Sizzlipede_47', 'SWSH1.Centiskorch_39'
DARTRIX, DECIDUEYE = 'SV3.Dartrix_14', 'SM12.Decidueye_20'
GIOVANNI, DUSK, SWITCH = 'SV035.GiovannisCharisma_161', 'SM10.DuskStone_167', 'ME1.EnergySwitch_115'
CUPS, BATON = 'SWSH7.SwitchingCups_162', 'SM3.WishfulBaton_128'
HEARTH, PILLAR = 'SM11.GiantHearth_197', 'SM7.SkyPillar_144'
HEAT_FIRE = 'SWSH3.HeatFireEnergy_174'
ARTAZON = 'SV2.Artazon_171'


class Deck8Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        for p in (self.me, self.opp):
            p.set_attribute(AttrID.WEAKNESS_TYPES, [])
            p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    # --- Giovanni's Charisma -------------------------------------------
    async def test_giovannis_charisma_bounce_then_attach(self):
        t = self.table()
        theirs = t.energy(self.opp, W)
        mine = t.put(t.basic_energy(R), P1, 'hand')
        await t.play(t.put(GIOVANNI, P1, 'hand'))
        self.assertIn(theirs, t.zone(P2, 'hand'))
        self.assertIn(mine, self.me.children)

    async def test_giovannis_charisma_no_attach_if_nothing_bounced(self):
        t = self.table()
        mine = t.put(t.basic_energy(R), P1, 'hand')
        card = t.put(GIOVANNI, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertIn(mine, t.zone(P1, 'hand'))     # "If you do" failed

    # --- Dusk Stone --------------------------------------------------------
    async def test_dusk_stone_evolves_lampent_put_into_play_this_turn(self):
        t = self.table()
        lampent = t.put(LAMPENT, P1, 'bench')
        t.state.mark_entered_play(lampent.entity_id)
        t.deck(P1, [CHANDELURE])
        stone = t.put(DUSK, P1, 'hand')
        self.assertTrue(t.can(stone, 'UseTrainerCard'))
        await t.play(stone)
        self.assertIn('Chandelure', t.names(t.board.pokemon_in_play(P1)))

    async def test_dusk_stone_only_named_pokemon(self):
        t = self.table()
        charmander = t.put(CHARMANDER, P1, 'bench')
        t.put(LAMPENT, P1, 'bench')
        t.deck(P1, [CHARMELEON])                  # evolves from in-play, but not named
        stone = t.put(DUSK, P1, 'hand')
        if t.can(stone, 'UseTrainerCard'):
            await t.play(stone)
        self.assertNotIn('Charmeleon', t.names(t.board.pokemon_in_play(P1)))

    # --- Energy Switch ---------------------------------------------------
    async def test_energy_switch_moves_basic_energy(self):
        t = self.table()
        bench = t.put(self.filler, P1, 'bench')
        fire = t.energy(bench, R)
        t.pokemon = lambda c, p: bench if 'from' in p.lower() and bench in c else (
            self.me if self.me in c else c[0])
        t.picks = lambda cards, count, prompt, display: [fire] if fire in cards else cards[:count]
        await t.play(t.put(SWITCH, P1, 'hand'))
        self.assertIn(fire, self.me.children)

    async def test_energy_switch_not_special_and_needs_two_pokemon(self):
        t = self.table()
        t.energy(self.me, R)
        card = t.put(SWITCH, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))   # only 1 Pokémon
        t = self.table()
        bench = t.put(self.filler, P1, 'bench')
        t.attach(HEAT_FIRE, bench)
        card = t.put(SWITCH, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))   # only a Special Energy

    # --- Switching Cups --------------------------------------------------
    async def test_switching_cups_swaps_hand_card_with_top(self):
        t = self.table()
        top = t.deck(P1, [CHARMANDER])[0]
        held = t.put(LITWICK, P1, 'hand')
        await t.play(t.put(CUPS, P1, 'hand'))
        self.assertIn(top, t.zone(P1, 'hand'))
        self.assertIs(t.zone(P1, 'deck')[-1], held)

    async def test_switching_cups_needs_another_card_in_hand(self):
        t = self.table()
        card = t.put(CUPS, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Wishful Baton ---------------------------------------------------
    async def _ko_with_baton(self, where):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        holder = t.put(self.filler, P2, where, hp=10)
        holder.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.play_target = holder
        receiver = t.put(self.filler, P2, 'bench')
        if where == 'bench':
            t.put(self.filler, P2, 'active')
            t.board.find_player_area(P2, 'bench').remove_child(receiver)
            t.board.find_player_area(P2, 'bench').children.append(receiver)
        energies = t.energy(holder, W, 4)
        t.attach(BATON, holder)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        attacker = t.put(DARTRIX, P1, 'active')
        t.energy(attacker, PokemonTypes.GRASS, 2)
        t.pokemon = lambda c, p: (holder if holder in c else
                                  receiver if receiver in c else c[0])
        t.picks = lambda cards, count, prompt, display: cards[:count]
        await t.attack(attacker, 'Shoot Through')
        return t, holder, receiver, energies

    async def test_wishful_baton_moves_up_to_three_basic_energy_on_active_ko(self):
        t, holder, receiver, energies = await self._ko_with_baton('active')
        self.assertNotIn(holder, t.board.pokemon_in_play(P2))
        self.assertEqual(len([e for e in energies if e in receiver.children]), 3)

    async def test_wishful_baton_not_when_knocked_out_on_bench(self):
        t, holder, receiver, energies = await self._ko_with_baton('bench')
        self.assertNotIn(holder, t.board.pokemon_in_play(P2))
        self.assertEqual([e for e in energies if e in receiver.children], [])

    # --- Giant Hearth ------------------------------------------------------
    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_giant_hearth_discard_one_for_two_fire_both_players(self):
        for owner, user in ((P1, P1), (P1, P2)):
            t = self.table()
            if user == P2:
                t.next_turn()
            hearth = t.stadium(HEARTH, owner)
            t.deck(user, [t.basic_energy(R), t.basic_energy(R), t.basic_energy(R), t.basic_energy(W), HEAT_FIRE])
            junk = t.put(self.filler, user, 'hand')
            seen = []
            t.picks = lambda cards, count, prompt, display: (seen.append((t.names(cards), count)), (
                [junk] if junk in cards else cards[:count]))[1]
            entry = self.stadium_action(t, hearth, user)
            with self.subTest(user=user):
                self.assertIsNotNone(entry)
                await t.do(entry, pid=user)
                hand = t.zone(user, 'hand')
                self.assertIn(junk, t.zone(user, 'discard'))
                self.assertEqual(len(hand), 2)
                fire_guid = t.basic_energy(R).guid.lower()
                self.assertTrue(all(c.archetype_id.lower() == fire_guid for c in hand), t.names(hand))
                self.assertNotIn('Heat Fire Energy', t.names(hand))
                self.assertIsNone(self.stadium_action(t, hearth, user))

    async def test_giant_hearth_needs_a_card_to_discard(self):
        t = self.table()
        hearth = t.stadium(HEARTH, P1)
        t.deck(P1, [t.basic_energy(R)])
        self.assertIsNone(self.stadium_action(t, hearth, P1))

    # --- Sky Pillar --------------------------------------------------------
    async def test_sky_pillar_protects_benched_from_attack(self):
        for owner in (P1, P2):
            t = self.table()
            t.stadium(PILLAR, owner)
            bench = t.put(self.filler, P2, 'bench')
            t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
            d = t.put(DARTRIX, P1, 'active')
            t.energy(d, PokemonTypes.GRASS, 2)
            t.pokemon = lambda c, p: bench if bench in c else c[0]
            before_a, before_b = t.hp(self.opp), t.hp(bench)
            await t.attack(d, 'Shoot Through')
            with self.subTest(owner=owner):
                self.assertEqual(before_a - t.hp(self.opp), 40)   # Active still hit
                self.assertEqual(before_b - t.hp(bench), 0)

    async def test_sky_pillar_does_not_stop_own_effects_or_active(self):
        # Without Sky Pillar the bench damage lands (control).
        t = self.table()
        bench = t.put(self.filler, P2, 'bench')
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        d = t.put(DARTRIX, P1, 'active')
        t.energy(d, PokemonTypes.GRASS, 2)
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        before_b = t.hp(bench)
        await t.attack(d, 'Shoot Through')
        self.assertEqual(before_b - t.hp(bench), 20)


if __name__ == "__main__":
    unittest.main()
