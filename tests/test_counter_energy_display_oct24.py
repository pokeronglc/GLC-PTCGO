"""Counter Energy (SM4 100) provides 2 Energy while its owner has more Prizes
left (OhkoXar, Oct 24: Kirlia with Psychic + Counter, behind 6-5). The server
already pays the retreat with Counter alone, but the client's retreat tray
counts ENERGY_INFO, which stayed at the printed single Colorless, so it
demanded both cards. The display sync now covers Special Energy too."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import PokemonTypes, AttrID
from spirit.game.session.legal_actions import _retreat_entry
from spirit.tools.effect_smoke import P1, P2

KIRLIA, COUNTER = 'SWSH12.Kirlia_68', 'SM4.CounterEnergy_100'


class CounterEnergyDisplay(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        k = t.put(KIRLIA, P1, 'active')
        t.put(KIRLIA, P1, 'bench')
        t.put(KIRLIA, P2, 'active')
        t.energy(k, PokemonTypes.PSYCHIC, 1)
        counter = t.attach(COUNTER, k)
        t.state.active_player_id = P1
        return t, k, counter

    async def sync(self, t, entity):
        sent = []

        async def capture(name, value, flags=0):
            sent.append(value)
        with patch.object(t.session, 'broadcast_packet', side_effect=capture):
            await t.session._sync_energy_display()
        return [m for m in sent if entity.entity_id in str(m)]

    async def test_behind_shows_two_and_reverts_when_level(self):
        t, k, counter = self.table()
        t.set_prizes(P1, 6); t.set_prizes(P2, 5)
        msgs = await self.sync(t, counter)
        self.assertTrue(msgs)
        self.assertIn('[7, 7]', str(msgs[-1]).replace("'", ''))
        # Server keeps the printed value.
        self.assertEqual(counter.get_attribute(AttrID.ENERGY_INFO), {'options': [[PokemonTypes.COLORLESS.value]]})
        self.assertFalse(await self.sync(t, counter))   # no repeat
        t.set_prizes(P2, 6)
        back = await self.sync(t, counter)
        self.assertTrue(back)
        self.assertIn(f'[[{PokemonTypes.COLORLESS.value}]]',
                      str(back[-1]).replace(' ', '').replace("'options':", ''))

    async def test_level_prizes_send_nothing(self):
        t, k, counter = self.table()
        self.assertFalse(await self.sync(t, counter))

    async def test_retreat_pays_with_counter_alone_when_behind(self):
        t, k, counter = self.table()
        t.set_prizes(P1, 6); t.set_prizes(P2, 5)
        entry = _retreat_entry(t.board, t.state, P1, 'g')[0]
        self.assertEqual(entry['_autoRetreatEnergyIDs'], [counter.entity_id])


if __name__ == '__main__':
    unittest.main()
