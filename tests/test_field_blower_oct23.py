"""Report (Oct 23): Field Blower picking Luxurious Cape + Tropical Beach only
discarded Tropical Beach. The engine discards both picks from every
board position; the game log now records what the player actually picked
("NAME picked 2 (...): Luxurious Cape (on X), Tropical Beach") so a repeat
can be checked."""
import logging
import unittest
from types import SimpleNamespace

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.tools.effect_smoke import P1, P2

CAPE, BEACH, BLOWER = 'SV4.LuxuriousCape_166', 'PROMO_BW.TropicalBeach_BW28', 'SM2.FieldBlower_125'


class FieldBlowerOct23(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    def table(self, cape_owner, beach_owner, bench):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        holder = t.put(self.filler, cape_owner, 'bench') if bench else t.active(cape_owner)
        cape = t.attach(CAPE, holder)
        beach = t.stadium(BEACH, beach_owner)
        t.state.turn_number = 5
        t.state.active_player_id = P1
        return t, cape, beach

    async def test_both_picks_discarded_everywhere(self):
        for cape_owner in (P1, P2):
            for beach_owner in (P1, P2):
                for bench in (False, True):
                    with self.subTest(cape=cape_owner, beach=beach_owner, bench=bench):
                        t, cape, beach = self.table(cape_owner, beach_owner, bench)
                        blower = t.put(BLOWER, P1, 'hand')
                        self.assertTrue(t.offers(blower))
                        await t.play(blower)
                        self.assertIn(cape, t.zone(cape_owner, 'discard'))
                        self.assertIn(beach, t.zone(beach_owner, 'discard'))

    async def test_pick_is_logged_with_card_names(self):
        t, cape, beach = self.table(P2, P2, False)
        player = SimpleNamespace(screen_name='Tester')
        with self.assertLogs(level=logging.INFO) as logs:
            t.session._log_picked(player, 'playmat.prompt.sm2_125.fieldblower',
                                  [cape.entity_id, beach.entity_id])
        line = '\n'.join(logs.output)
        self.assertIn('Tester picked 2', line)
        self.assertIn('Luxurious Cape (on ', line)
        self.assertIn('Tropical Beach', line)


if __name__ == '__main__':
    unittest.main()
