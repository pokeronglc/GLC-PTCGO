"""Burn Brightly makes each basic Fire Energy provide two.  The legacy
client's tray counts printed pips, so the server pays fixed costs itself."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.data_utils import CARD_DEFS_BY_GUID
from spirit.game.models.board import EnergyEntity
from spirit.game.session import legal_actions as la
from spirit.tools.effect_smoke import P1


def _basic(name):
    return next(d for d in CARD_DEFS_BY_GUID.values()
                if d.display_name == name and 'Special' not in (d.subtypes or []))


class BurnBrightlyPaymentTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def board_with(self, *names):
        rig, e = self.rig('PGO.Charizard_10')
        board = rig.board
        bench = board.find_player_area(P1, 'bench')
        zard = e['target']
        active = next(p for p in bench.children if p.archetype_id != zard.archetype_id)
        board.move_card(zard.entity_id, bench.entity_id)
        board.move_card(active.entity_id,
                        board.find_player_area(P1, 'activePokemonArea').entity_id)
        for card in list(active.children):
            if isinstance(card, EnergyEntity):
                rig.to_area(card, P1, 'discard')
        energies = []
        for name in names:
            energy = self.add(rig, _basic(name), P1, 'hand')
            rig.attach(energy, active)
            energies.append(energy)
        return rig, active, energies

    def retreat_entry(self, rig, active, cost):
        with patch.object(la, 'effective_retreat_cost', lambda b, p: cost):
            return next(a for a in la.compute_legal_actions(
                rig.board, rig.session.turn_state, P1, rig.session.game_id)
                if a['entityID'] == active.entity_id
                and a['selectableAction']['description'] == la.ACTION_RETREAT)

    async def test_retreat_two_with_two_fire_discards_one(self):
        rig, active, fires = self.board_with('Fire Energy', 'Fire Energy')
        entry = self.retreat_entry(rig, active, 2)
        self.assertEqual(len(entry['_autoRetreatEnergyIDs']), 1)
        names = [i['name'] for i in entry['targetInfoLst']]
        self.assertNotIn(la.SelectionKind.RETREAT_COST_ENTITY_LIST.value, names)

    async def test_fire_pays_before_a_second_card(self):
        rig, active, energies = self.board_with('Fire Energy', 'Psychic Energy')
        entry = self.retreat_entry(rig, active, 2)
        self.assertEqual(entry['_autoRetreatEnergyIDs'], [energies[0].entity_id])

    async def test_real_choice_still_asks(self):
        rig, active, energies = self.board_with(
            'Fire Energy', 'Fire Energy', 'Psychic Energy')
        entry = self.retreat_entry(rig, active, 3)
        self.assertNotIn('_autoRetreatEnergyIDs', entry)

    async def test_discard_two_energy_pays_with_one_fire(self):
        rig, active, fires = self.board_with('Fire Energy', 'Fire Energy', 'Fire Energy')
        offer = AsyncMock()
        with patch('spirit.game.session.game_session.AIPlayer', type('NotAI', (), {})), \
                patch.object(rig.session, '_run_pick_offer', offer):
            picked = await rig.session.prompt_energy_unit_picker(
                P1, active.entity_id, fires, 2)
        offer.assert_not_awaited()
        self.assertEqual(len(picked), 1)

    async def test_without_burn_brightly_nothing_changes(self):
        rig, active, fires = self.board_with('Fire Energy', 'Fire Energy')
        guid = fixtures.definition('PGO.Charizard_10').guid
        for pokemon in list(rig.board.find_player_area(P1, 'bench').children):
            if pokemon.archetype_id == guid:
                rig.to_area(pokemon, P1, 'discard')
        self.assertIsNone(la.forced_energy_payment(fires, 1, rig.board))


if __name__ == "__main__":
    unittest.main()


class OtherDoublerPaymentTests(unittest.IsolatedAsyncioTestCase):
    """Jungle Totem, Wild Growth and Psychic Mirage share the same fix."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_each_doubler_pays_with_the_fewest_cards(self):
        for path, energy_name in (('SL.Venusaur_3', 'Grass Energy'),
                                  ('ME1.Meganium_10', 'Grass Energy'),
                                  ('BW4.Gardevoir_57', 'Psychic Energy')):
            with self.subTest(path=path):
                rig, e = self.rig(path)
                board = rig.board
                active = e['target']
                for card in list(active.children):
                    if isinstance(card, EnergyEntity):
                        rig.to_area(card, P1, 'discard')
                energies = []
                for _ in range(3):
                    energy = self.add(rig, _basic(energy_name), P1, 'hand')
                    rig.attach(energy, active)
                    energies.append(energy)
                # A second copy is benched: the effect still doesn't stack.
                self.assertEqual([la.energy_provided_count(x, board) for x in energies],
                                 [2, 2, 2])
                with patch.object(la, 'effective_retreat_cost', lambda b, p: 2):
                    entry = next(a for a in la.compute_legal_actions(
                        board, rig.session.turn_state, P1, rig.session.game_id)
                        if a['entityID'] == active.entity_id
                        and a['selectableAction']['description'] == la.ACTION_RETREAT)
                self.assertEqual(len(entry['_autoRetreatEnergyIDs']), 1)


class EnergyDisplaySyncTests(unittest.IsolatedAsyncioTestCase):
    """The client's pip tray reads ENERGY_INFO: show the doubled Fire."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_doubled_fire_is_sent_and_reverted(self):
        rig, e = self.rig('PGO.Charizard_10')
        session, board = rig.session, rig.board
        zard = e['target']
        fire = self.add(rig, _basic('Fire Energy'), P1, 'hand')
        rig.attach(fire, zard)
        sent = []

        async def capture(name, value, flags=0):
            inner = value.get('message') or value.get('msg') or value
            sent.append(inner)
        with patch.object(session, 'broadcast_packet', side_effect=capture):
            await session._sync_energy_display()
            first = [m for m in sent if fire.entity_id in str(m)]
            self.assertTrue(first)
            self.assertIn('[6, 6]', str(first[-1]))
            # Printed value stays on the server.
            self.assertEqual(fire.get_attribute(la.AttrID.ENERGY_INFO), {'options': [[6]]})
            sent.clear()
            await session._sync_energy_display()
            self.assertFalse([m for m in sent if fire.entity_id in str(m)])
            # Every Charizard leaves play -> the printed single Fire comes back.
            guid = zard.archetype_id
            for pid in (P1,):
                for pokemon in list(board.pokemon_in_play(pid)):
                    if pokemon.archetype_id == guid and pokemon is not zard:
                        rig.to_area(pokemon, P1, 'discard')
            rig.to_area(fire, P1, 'discard')
            await session._sync_energy_display()
            back = [m for m in sent if fire.entity_id in str(m)]
            self.assertTrue(back)
            self.assertIn('[[6]]', str(back[-1]).replace(' ', '').replace("'options':", ''))
