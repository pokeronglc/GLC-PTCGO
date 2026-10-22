"""Owner request (Oct 15): the Supporter VS Seeker takes from the discard
pile flashes up for both players (and so shows in the game log)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.test_bughunt12_wire import seat, msgs
from spirit.tools.effect_smoke import P1, P2


class VsSeekerReveal(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_chosen_supporter_is_revealed_to_both_players(self):
        for ref in ('XY4.VSSeeker_109', 'XY6.VSSeeker_110'):
            with self.subTest(ref):
                t = Table(self)
                t.put(self.filler, P1, 'active')
                t.put(self.filler, P2, 'active')
                supporter = t.put('SM10.Welder_189', P1, 'discard')
                seeker = t.put(ref, P1, 'hand')
                h1, h2 = seat(t.session, P1), seat(t.session, P2)
                t.picks = lambda cs, n, pr, sh: list(cs)[:n]
                await t.play(seeker)
                self.assertIn(supporter, t.zone(P1, 'hand'))
                for h in (h1, h2):
                    shown = [m['value']['entityID'] for m in msgs(h, 'RevealCardToAllEffect')]
                    self.assertIn(supporter.entity_id, shown)


if __name__ == '__main__':
    unittest.main()
