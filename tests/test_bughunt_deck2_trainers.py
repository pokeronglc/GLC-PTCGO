"""Bug hunt, deck 2 (Psychic): Supporters, Items, the Stadium and the
Special Energy, through the real play executor."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

P, D, G = PokemonTypes.PSYCHIC, PokemonTypes.DARKNESS, PokemonTypes.GRASS
RALTS, KIRLIA, GARDEVOIR = 'ME2PT5.Ralts_87', 'SWSH12.Kirlia_68', 'BW4.Gardevoir_57'
ABRA, KADABRA, ALAKAZAM = 'ME1.Abra_54', 'ME1.Kadabra_55', 'ME1.Alakazam_56'
GIRATINA, MEW, MUNKIDORI, DEOXYS = 'SM8.Giratina_97', 'CEL25.Mew_11', 'SV085.Munkidori_44', 'ME4.Deoxys_32'
GOLBAT, SABLEYE, ZUBAT = 'SWSH5.Golbat_90', 'SV2.Sableye_136', 'ME4.Zubat_49'
HILDA, TULIP, RAIHAN = 'RSV10PT5.Hilda_84', 'SV4.Tulip_181', 'SWSH7.Raihan_152'
DAWN, MARNIE = 'ME2.Dawn_87', 'SWSH35.Marnie_56'
FOG, TREASURE = 'SWSH6.FogCrystal_140', 'SM6.MysteriousTreasure_113'
ROPE, RETRIEVAL = 'BW8.EscapeRope_120', 'BW1.EnergyRetrieval_92'
SILENT_LAB, TELEPATHIC = 'XY5.SilentLab_140', 'ME3.TelepathicPsychicEnergy_88'
NEST, ARTAZON = 'SV1.NestBall_181', 'SV2.Artazon_171'


class GroupTable(Table):
    """Table that also scripts search_deck_groups browsers (Hilda, Dawn):
    each slot takes its first `count` cards; offered names are recorded."""

    def __init__(self, test):
        super().__init__(test)
        self.groups = []

    def _patches(self):
        table = self

        async def groups(session, player_id, source_entity_id, specs, prompt='',
                         display_cards=None, total=None, any_of=False):
            table.groups.append([table.names(s['cards']) for s in specs])
            return [[c.entity_id for c in s['cards'][:s['count']]] for s in specs]
        return super()._patches() + [
            patch.object(type(self.session), 'prompt_card_chooser_groups', groups)]


class Deck2Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = GroupTable(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    def browse(self, t, take=None):
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count] if take is None else take(cards, count)
        t.picks = picks
        return seen

    # --- Hilda ------------------------------------------------------------
    async def test_hilda_evolution_and_energy(self):
        t = self.table()
        t.deck(P1, [RALTS, KIRLIA, t.basic_energy(P), NEST])
        await t.play(t.put(HILDA, P1, 'hand'))
        names = self.hand_names(t)
        self.assertIn('Kirlia', names)
        self.assertNotIn('Ralts', names)            # a Basic is not an Evolution
        self.assertNotIn('Nest Ball', names)
        self.assertEqual(len(names), 2)
        self.assertNotIn('Ralts', t.groups[-1][0])

    # --- Tulip ------------------------------------------------------------
    async def test_tulip_up_to_four_psychic_pokemon_or_basic_psychic_energy(self):
        t = self.table()
        for spec in (RALTS, KIRLIA, GOLBAT, t.basic_energy(P), t.basic_energy(P),
                     t.basic_energy(G), TELEPATHIC, ABRA):
            t.put(spec, P1, 'discard')
        seen = self.browse(t)
        await t.play(t.put(TULIP, P1, 'hand'))
        self.assertEqual(seen['count'], 4)
        self.assertNotIn('Golbat', seen['names'])
        self.assertNotIn('Telepathic Psychic Energy', seen['names'])   # not Basic
        self.assertEqual(len(seen['names']), 5)                        # Ralts Kirlia Abra + 2 P
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    # --- Raihan -----------------------------------------------------------
    async def test_raihan_needs_knockout_last_turn(self):
        t = self.table()
        t.put(t.basic_energy(P), P1, 'discard')
        card = t.put(RAIHAN, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_raihan_attach_basic_energy_then_any_card(self):
        t = self.table()
        t.state.kos_suffered_last_turn = {P1: [{'archetype_id': 'x', 'subtypes': []}]}
        energy = t.put(t.basic_energy(P), P1, 'discard')
        t.put(TELEPATHIC, P1, 'discard')
        t.deck(P1, ['SM3.Guzma_115'])
        card = t.put(RAIHAN, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.append(t.names(cards)),
                                                         [c for c in cards if def_for(c.archetype_id).display_name == 'Guzma'][:1] or cards[:count])[1]
        await t.play(card)
        self.assertIn(energy, self.me.children)
        self.assertNotIn('Telepathic Psychic Energy', offered[0])
        self.assertEqual(self.hand_names(t), ['Guzma'])

    # --- Dawn -------------------------------------------------------------
    async def test_dawn_basic_stage1_stage2(self):
        t = self.table()
        t.deck(P1, [ABRA, KADABRA, ALAKAZAM, NEST])
        await t.play(t.put(DAWN, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Abra', 'Alakazam', 'Kadabra'])

    async def test_dawn_missing_stage_still_gets_others(self):
        t = self.table()
        t.deck(P1, [ABRA, ALAKAZAM])
        await t.play(t.put(DAWN, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Abra', 'Alakazam'])

    # --- Marnie -----------------------------------------------------------
    async def test_marnie_five_and_four_hands_to_bottom(self):
        t = self.table()
        mine = [t.put(GOLBAT, P1, 'hand') for _ in range(3)]
        theirs = [t.put(GOLBAT, P2, 'hand') for _ in range(7)]
        await t.play(t.put(MARNIE, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)
        for pid, cards in ((P1, mine), (P2, theirs)):
            deck = t.zone(pid, 'deck')
            with self.subTest(pid=pid):
                # every old hand card went to the deck (bottom), none drawn back
                self.assertTrue(set(cards) <= set(deck))
                self.assertFalse(set(cards) & set(t.zone(pid, 'hand')))

    # --- Fog Crystal ------------------------------------------------------
    async def test_fog_crystal_basic_psychic_pokemon_or_psychic_energy(self):
        t = self.table()
        t.deck(P1, [RALTS, KIRLIA, SABLEYE, t.basic_energy(P), t.basic_energy(G)])
        seen = self.browse(t)
        await t.play(t.put(FOG, P1, 'hand'))
        self.assertEqual(seen['count'], 1)
        self.assertNotIn('Kirlia', seen['names'])
        self.assertNotIn('Sableye', seen['names'])
        self.assertEqual(len(seen['names']), 2)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    # --- Mysterious Treasure ---------------------------------------------
    async def test_mysterious_treasure(self):
        t = self.table()
        t.deck(P1, [KIRLIA, SABLEYE])
        card = t.put(TREASURE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.put(NEST, P1, 'hand')
        seen = self.browse(t, take=lambda cards, count: [c for c in cards
                       if def_for(c.archetype_id).display_name in ('Nest Ball', 'Kirlia')][:count])
        await t.play(card)
        self.assertEqual(self.hand_names(t), ['Kirlia'])
        self.assertIn('Nest Ball', t.names(t.zone(P1, 'discard')))

    async def test_mysterious_treasure_no_darkness(self):
        t = self.table()
        t.deck(P1, [SABLEYE])
        t.put(NEST, P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.append(t.names(cards)), cards[:count])[1]
        await t.play(t.put(TREASURE, P1, 'hand'))
        self.assertNotIn('Sableye', self.hand_names(t))

    # --- Escape Rope ------------------------------------------------------
    async def test_escape_rope_both_switch(self):
        t = self.table()
        mine = t.put(RALTS, P1, 'bench')
        theirs = t.put(SABLEYE, P2, 'bench')
        await t.play(t.put(ROPE, P1, 'hand'))
        self.assertIs(t.active(P1), mine)
        self.assertIs(t.active(P2), theirs)

    async def test_escape_rope_only_side_with_bench_switches(self):
        t = self.table()
        theirs = t.put(SABLEYE, P2, 'bench')
        await t.play(t.put(ROPE, P1, 'hand'))
        self.assertIs(t.active(P1), self.me)
        self.assertIs(t.active(P2), theirs)
        t = self.table()
        card = t.put(ROPE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Energy Retrieval -------------------------------------------------
    async def test_energy_retrieval_two_basic(self):
        t = self.table()
        for spec in (t.basic_energy(P), t.basic_energy(G), t.basic_energy(P), TELEPATHIC):
            t.put(spec, P1, 'discard')
        seen = self.browse(t)
        await t.play(t.put(RETRIEVAL, P1, 'hand'))
        self.assertEqual(seen['count'], 2)
        self.assertNotIn('Telepathic Psychic Energy', seen['names'])
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    async def test_energy_retrieval_needs_basic_energy(self):
        t = self.table()
        t.put(TELEPATHIC, P1, 'discard')
        card = t.put(RETRIEVAL, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Silent Lab -------------------------------------------------------
    async def test_silent_lab_basics_lose_abilities_everywhere(self):
        t = self.table()
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        mew = t.put(MEW, P1, 'active')
        munk = t.put(MUNKIDORI, P1, 'bench')
        t.energy(munk, D)
        hurt = t.put(self.filler, P1, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 30)
        gira = t.put(GIRATINA, P1, 'discard')
        self.assertIsNotNone(t.ability_offer(mew, 'Mysterious Tail'))
        self.assertIsNotNone(t.ability_offer(gira, 'Distortion Door'))
        t.stadium(SILENT_LAB, P2)                   # either player's Stadium
        self.assertIsNone(t.ability_offer(mew, 'Mysterious Tail'))
        self.assertIsNone(t.ability_offer(munk, 'Adrena-Brain'))
        self.assertIsNone(t.ability_offer(gira, 'Distortion Door'))

    async def test_silent_lab_spares_evolved_pokemon(self):
        t = self.table()
        kirlia = t.put(KIRLIA, P1, 'bench')
        t.put(NEST, P1, 'hand')
        t.stadium(SILENT_LAB, P1)
        self.assertIsNotNone(t.ability_offer(kirlia, 'Refinement'))

    async def test_silent_lab_blocks_gardevoir_mirage_not(self):
        # Gardevoir (Stage 2) keeps Psychic Mirage under Silent Lab.
        t = self.table()
        deoxys = t.put(DEOXYS, P1, 'bench')
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        t.board.find_player_area(P1, 'bench').remove_child(deoxys)
        t.board.add_card_to_area(deoxys, t.board.find_player_area(P1, 'activePokemonArea'))
        t.energy(deoxys, P, 2)
        t.put(GARDEVOIR, P1, 'bench')
        t.stadium(SILENT_LAB, P1)
        self.assertIsNotNone(t.attack_offer(deoxys, 'Psyspear'))

    # --- Telepathic Psychic Energy ---------------------------------------
    async def test_telepathic_benches_two_basic_psychic_on_attach_to_psychic(self):
        t = self.table()
        ralts = t.put(RALTS, P1, 'bench')
        t.deck(P1, [ABRA, MEW, KIRLIA, SABLEYE, DEOXYS])
        seen = self.browse(t)
        energy = t.put(TELEPATHIC, P1, 'hand')
        await t.play(energy, targets=[ralts.entity_id])
        self.assertIn(energy, ralts.children)
        self.assertEqual(seen['count'], 2)
        self.assertNotIn('Kirlia', seen['names'])
        self.assertNotIn('Sableye', seen['names'])
        self.assertEqual(len(t.zone(P1, 'bench')), 3)

    async def test_telepathic_nothing_on_non_psychic(self):
        t = self.table()
        t.deck(P1, [ABRA, MEW])
        energy = t.put(TELEPATHIC, P1, 'hand')
        await t.play(energy, targets=[self.me.entity_id])
        self.assertIn(energy, self.me.children)
        self.assertEqual(len(t.zone(P1, 'bench')), 0)

    async def test_telepathic_provides_psychic(self):
        t = self.table()
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        abra = t.put(ABRA, P1, 'active')
        t.attach(TELEPATHIC, abra)
        self.assertIsNotNone(t.attack_offer(abra, 'Teleportation Attack'))


if __name__ == "__main__":
    unittest.main()
