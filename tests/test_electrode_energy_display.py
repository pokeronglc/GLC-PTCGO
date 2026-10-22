"""Electrode (XY12) - Buzzap Thunder: once attached as Special Energy the
client is told it is an Energy card (so it shows as an attachment and can be
picked by Enhanced Hammer / Faba), and told again when it leaves."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID, CardType
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1

PATH = 'XY12.Electrode_40'


def _card_type_updates(broadcast, entity_id):
    out = []
    for call in broadcast.call_args_list:
        text = str(call.args[1])
        if entity_id in text and f"'name': {AttrID.CARD_TYPE.value}" in text:
            out.append(CardType.ENERGY.value if f"'value': {CardType.ENERGY.value}," in text
                       else CardType.POKEMON.value)
    return out


class ElectrodeEnergyDisplayTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def test_shown_as_energy_while_attached(self):
        rig, e = self.rig(PATH, 'pokemon')
        board, session = rig.board, rig.session
        electrode = next(p for p in board.find_player_area(P1, 'bench').children
                         if p.archetype_id == e['target'].archetype_id)
        target = board.active_pokemon(P1)
        ability = next(a for a in fixtures.definition(PATH).abilities if a.title == 'Buzzap Thunder')
        ctx = EffectContext(session, P1, electrode, ability)
        with patch.object(EffectContext, 'choose_pokemon', AsyncMock(return_value=target)), \
             patch.object(session, 'send_game_sequence', AsyncMock()):
            await ability.effect(ctx)
        self.assertIn(electrode, board.attached_energies(target))
        broadcast = AsyncMock()
        with patch.object(session, 'broadcast_packet', broadcast):
            await session._sync_pokemon_energy_types()
            await session._sync_pokemon_energy_types()   # no repeat
        self.assertEqual(_card_type_updates(broadcast, electrode.entity_id), [CardType.ENERGY.value])
        # Oct 13: the client also gets ENERGY_INFO (two Lightning), which is
        # what it draws the Energy symbols under the Pokemon from.
        info = [str(c.args[1]) for c in broadcast.call_args_list
                if electrode.entity_id in str(c.args[1])
                and f"'name': {AttrID.ENERGY_INFO.value}" in str(c.args[1])]
        self.assertEqual(len(info), 1)
        self.assertIn("'options': [[8, 8]]", info[0])
        board.move_card(electrode.entity_id, board.find_player_area(P1, 'discard').entity_id)
        broadcast = AsyncMock()
        with patch.object(session, 'broadcast_packet', broadcast):
            await session._sync_pokemon_energy_types()
        self.assertEqual(_card_type_updates(broadcast, electrode.entity_id), [CardType.POKEMON.value])

    async def test_reseated_on_the_board_after_retyping(self):
        """Oct 13: the board's Energy circles only redraw on a move, so the
        retyped Electrode is re-seated (same parent, same position) AFTER its
        CARD_TYPE / ENERGY_INFO updates."""
        rig, e = self.rig(PATH, 'pokemon')
        board, session = rig.board, rig.session
        electrode = next(p for p in board.find_player_area(P1, 'bench').children
                         if p.archetype_id == e['target'].archetype_id)
        target = board.active_pokemon(P1)
        ability = next(a for a in fixtures.definition(PATH).abilities if a.title == 'Buzzap Thunder')
        ctx = EffectContext(session, P1, electrode, ability)
        with patch.object(EffectContext, 'choose_pokemon', AsyncMock(return_value=target)), \
             patch.object(session, 'send_game_sequence', AsyncMock()):
            await ability.effect(ctx)
        order = []
        broadcast = AsyncMock(side_effect=lambda *a, **k: order.append('attr'))
        seq = AsyncMock(side_effect=lambda players, name, msgs: order.append(('seq', getattr(name, 'value', name), msgs)))
        with patch.object(session, 'broadcast_packet', broadcast), \
             patch.object(session, 'send_game_sequence', seq):
            await session._sync_pokemon_energy_types()
            await session._sync_pokemon_energy_types()        # nothing new: no re-seat
        moves = [o for o in order if isinstance(o, tuple)]
        self.assertEqual(len(moves), 1)
        _, name, msgs = moves[0]
        self.assertEqual(name, 'GroupedMove')
        # Oct 14: the client draws an Energy circle only for children whose
        # ENTITY NAME is ...entities.Energy -> re-introduce it as Energy first.
        intro = msgs[0]['value']
        self.assertEqual(intro['entityID'], electrode.entity_id)
        self.assertEqual(intro['entityName'], 'com.direwolfdigital.cake.rules.entities.Energy')
        attrs = {a['name']: a['value'] for a in intro['attributeMap']}
        self.assertEqual(attrs[AttrID.CARD_TYPE.value], CardType.ENERGY.value)
        self.assertIs(attrs[AttrID.IS_SPECIAL_ENERGY.value], True)
        value = msgs[1]['value']
        self.assertEqual((value['entityID'], value['destinationID']),
                         (electrode.entity_id, target.entity_id))
        self.assertEqual(value['positionInParent'], target.children.index(electrode))
        self.assertTrue(order.index(moves[0]) > order.index('attr'))
        # Reconnect snapshots carry the same identity while attached ...
        tree = electrode.serialize(P1)
        self.assertEqual(tree['entityName'], 'com.direwolfdigital.cake.rules.entities.Energy')
        # ... and it is a Pokemon again once it leaves.
        board.move_card(electrode.entity_id, board.find_player_area(P1, 'discard').entity_id)
        order.clear()
        with patch.object(session, 'broadcast_packet', broadcast), \
             patch.object(session, 'send_game_sequence', seq):
            await session._sync_pokemon_energy_types()
        intros = [m['value'] for o in order if isinstance(o, tuple) for m in o[2]
                  if 'entityName' in m['value']]
        self.assertEqual([i['entityName'] for i in intros],
                         ['com.direwolfdigital.cake.rules.entities.Pokemon'])
        self.assertEqual(electrode.serialize(P1)['entityName'],
                         'com.direwolfdigital.cake.rules.entities.Pokemon')


if __name__ == "__main__":
    unittest.main()
