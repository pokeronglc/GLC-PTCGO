"""Bug hunt, deck 8 (Metal): Supporters, Items, Tools, Stadium and Special
Energy, through the real executor."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

M, F = PokemonTypes.METAL, PokemonTypes.FIRE
DURALUDON, ARCHALUDON = 'SWSH2.Duraludon_138', 'SV07.Archaludon_107'
VAROOM, REVAVROOM = 'SV065.Varoom_43', 'SV1.Revavroom_142'
BRONZOR, BRONZONG = 'SV3.Bronzor_144', 'XY4.Bronzong_61'
RESEARCH, PHILIPPE = 'SV09.ProfessorsResearch_155', 'ME4.Philippe_79'
EVOSODA, SAUCER, DEFENDER = 'XY1.Evosoda_116', 'SWSH1.MetalSaucer_170', 'ME1.IronDefender_118'
ESCAPE, FFB = 'SM5.EscapeBoard_122', 'XY9.FightingFuryBelt_99'
CORONET, MAGNETIC = 'SM5.MtCoronet_130', 'ME4.MagneticMetalEnergy_85'


class Deck8Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=None):
        t = Table(self)
        self.me = t.put(me or self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    def neutral(self, pokemon, hp=400):
        pokemon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        pokemon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            pokemon.set_attribute(AttrID.HP, hp)

    async def opponent_hits(self, t, defender):
        """P2's Duraludon uses Power Beam (110) on P1's Active."""
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        attacker = t.put(DURALUDON, P2, 'active')
        t.energy(attacker, M, 3)
        t.next_turn()
        before = t.hp(defender)
        await t.attack(attacker, 'Power Beam', pid=P2)
        return before - t.hp(defender)

    # --- Professor's Research ------------------------------------------
    async def test_professors_research_discard_hand_draw_seven(self):
        t = self.table()
        old = [t.put(VAROOM, P1, 'hand') for _ in range(3)]
        await t.play(t.put(RESEARCH, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        for c in old:
            self.assertIn(c, t.zone(P1, 'discard'))

    # --- Philippe ---------------------------------------------------------
    async def test_philippe_two_basic_metal_to_metal_pokemon(self):
        t = self.table()
        dura = t.put(DURALUDON, P1, 'bench')
        for _ in range(3):
            t.put(t.basic_energy(M), P1, 'discard')
        t.put(MAGNETIC, P1, 'discard')
        offered = {}
        t.pokemon = lambda c, p: (offered.setdefault('p', t.names(c)), c[0])[1]
        t.picks = lambda cards, count, prompt, display: (offered.setdefault('e', (t.names(cards), count)), cards[:count])[1]
        await t.play(t.put(PHILIPPE, P1, 'hand'))
        self.assertEqual(offered['p'], ['Duraludon'])          # Snorlax isn't Metal
        names, count = offered['e']
        self.assertEqual(count, 2)
        self.assertNotIn('Magnetic Metal Energy', names)        # Basic only
        self.assertEqual(len(t.board.attached_energies(dura)), 2)

    async def test_philippe_needs_metal_pokemon(self):
        t = self.table()
        t.put(t.basic_energy(M), P1, 'discard')
        card = t.put(PHILIPPE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Evosoda -----------------------------------------------------------
    async def test_evosoda_evolves_from_deck(self):
        t = self.table(me=DURALUDON)      # mono-Metal board (GLC evolution-search ruling)
        varoom = t.put(VAROOM, P1, 'bench')
        t.deck(P1, [REVAVROOM])
        t.pokemon = lambda c, p: varoom if varoom in c else c[0]
        await t.play(t.put(EVOSODA, P1, 'hand'))
        self.assertIn('Revavroom', t.names(t.board.pokemon_in_play(P1)))

    async def test_evosoda_not_on_pokemon_played_this_turn(self):
        t = self.table(me=DURALUDON)
        varoom = t.put(VAROOM, P1, 'bench')
        t.state.mark_entered_play(varoom.entity_id)
        t.state.mark_entered_play(self.me.entity_id)
        t.deck(P1, [REVAVROOM])
        card = t.put(EVOSODA, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Metal Saucer ------------------------------------------------------
    async def test_metal_saucer_benched_metal_only(self):
        t = self.table(me=DURALUDON)
        bench_metal = t.put(VAROOM, P1, 'bench')
        t.put(self.filler, P1, 'bench')
        energy = t.put(t.basic_energy(M), P1, 'discard')
        offered = {}
        t.pokemon = lambda c, p: (offered.setdefault('p', t.names(c)), c[0])[1]
        await t.play(t.put(SAUCER, P1, 'hand'))
        self.assertEqual(offered['p'], ['Varoom'])
        self.assertIn(energy, bench_metal.children)

    async def test_metal_saucer_not_for_active_only_metal(self):
        t = self.table(me=DURALUDON)
        t.put(self.filler, P1, 'bench')
        t.put(t.basic_energy(M), P1, 'discard')
        card = t.put(SAUCER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Iron Defender -----------------------------------------------------
    async def test_iron_defender_metal_pokemon_take_30_less(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        varoom = t.put(VAROOM, P1, 'active')
        self.neutral(varoom)
        await t.play(t.put(DEFENDER, P1, 'hand'))
        self.assertEqual(await self.opponent_hits(t, varoom), 80)

    async def test_iron_defender_not_non_metal(self):
        t = self.table()
        self.neutral(self.me)
        await t.play(t.put(DEFENDER, P1, 'hand'))
        self.assertEqual(await self.opponent_hits(t, self.me), 110)

    # Was a bug (fixed Oct 10): Iron Defender only shields Pokémon in play when it's played; new ones are unprotected
    async def test_iron_defender_includes_new_metal_pokemon(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        old = t.put(DURALUDON, P1, 'active')
        await t.play(t.put(DEFENDER, P1, 'hand'))
        # a Metal Pokémon is benched (real play) after the Item, then becomes Active
        newcomer = t.put(VAROOM, P1, 'hand')
        await t.play(newcomer)
        self.assertIn(newcomer, t.zone(P1, 'bench'))
        # the Pokémon that was in play leaves play (e.g. picked up by Scoop Up Net)
        t.board.move_card(old.entity_id, t.board.find_player_area(P1, 'hand').entity_id)
        t.board.move_card(newcomer.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        self.assertIs(t.active(P1), newcomer)
        self.neutral(newcomer)
        self.assertEqual(await self.opponent_hits(t, newcomer), 80)

    # --- Escape Board --------------------------------------------------------
    async def test_escape_board_minus_one_and_retreat_while_asleep(self):
        t = self.table(me=BRONZOR)          # retreat 2
        t.put(self.filler, P1, 'bench')
        t.energy(self.me, M, 2)
        board = t.put(ESCAPE, P1, 'hand')
        await t.play(board, targets=[self.me.entity_id])
        self.assertEqual(t.retreat(self.me), 1)
        self.me.set_attribute(AttrID.SPECIAL_CONDITIONS, [ASLEEP])
        self.assertTrue(t.can(self.me, 'BaseRetreat'))
        self.me.set_attribute(AttrID.SPECIAL_CONDITIONS, [PARALYZED])
        self.assertTrue(t.can(self.me, 'BaseRetreat'))

    async def test_no_escape_board_cant_retreat_asleep(self):
        t = self.table(me=BRONZOR)
        t.put(self.filler, P1, 'bench')
        t.energy(self.me, M, 2)
        self.me.set_attribute(AttrID.SPECIAL_CONDITIONS, [ASLEEP])
        self.assertFalse(t.can(self.me, 'BaseRetreat'))

    # --- Fighting Fury Belt --------------------------------------------------
    async def test_fighting_fury_belt_basic_hp_and_damage(self):
        t = self.table(me=BRONZOR)
        t.energy(self.me, M, 2)
        base = effective_max_hp(t.board, self.me)
        belt = t.put(FFB, P1, 'hand')
        await t.play(belt, targets=[self.me.entity_id])
        self.assertEqual(effective_max_hp(t.board, self.me), base + 40)
        await t.attack(self.me, 'Speed Dive')
        self.assertEqual(400 - t.hp(self.opp), 40)

    async def test_fighting_fury_belt_not_on_stage1(self):
        t = self.table(me=ARCHALUDON)
        t.energy(self.me, M, 3)
        base = effective_max_hp(t.board, self.me)
        belt = t.put(FFB, P1, 'hand')
        await t.play(belt, targets=[self.me.entity_id])
        self.assertEqual(effective_max_hp(t.board, self.me), base)
        await t.attack(self.me, 'Iron Blaster')
        self.assertEqual(400 - t.hp(self.opp), 160)

    # --- Mt. Coronet --------------------------------------------------------
    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_mt_coronet_two_metal_once_each_player(self):
        t = self.table()
        coronet = t.stadium(CORONET, P2)               # opponent's Stadium works for me
        for _ in range(3):
            t.put(t.basic_energy(M), P1, 'discard')
        fire = t.put(t.basic_energy(F), P1, 'discard')
        await t.do(self.stadium_action(t, coronet))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(c not in t.zone(P1, 'discard') and c is not fire for c in hand))
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertIsNone(self.stadium_action(t, coronet))
        t.next_turn()
        t.put(t.basic_energy(M), P2, 'discard'); t.put(t.basic_energy(M), P2, 'discard')
        await t.do(self.stadium_action(t, coronet, P2), pid=P2)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)

    async def test_mt_coronet_no_metal_in_discard(self):
        t = self.table()
        coronet = t.stadium(CORONET, P1)
        t.put(t.basic_energy(F), P1, 'discard')
        self.assertIsNone(self.stadium_action(t, coronet))

    # --- Magnetic Metal Energy ---------------------------------------------
    async def test_magnetic_metal_energy_provides_metal_and_free_retreat(self):
        t = self.table(me=BRONZOR)
        energy = t.put(MAGNETIC, P1, 'hand')
        await t.play(energy, targets=[self.me.entity_id])
        self.assertIn(energy, self.me.children)
        self.assertEqual(t.retreat(self.me), 0)
        self.assertIsNotNone(t.attack_offer(self.me, 'Mirror Draw'))   # costs [M]

    async def test_magnetic_metal_energy_non_metal_keeps_retreat(self):
        t = self.table()
        base = t.retreat(self.me)
        energy = t.put(MAGNETIC, P1, 'hand')
        await t.play(energy, targets=[self.me.entity_id])
        self.assertEqual(t.retreat(self.me), base)


if __name__ == "__main__":
    unittest.main()
