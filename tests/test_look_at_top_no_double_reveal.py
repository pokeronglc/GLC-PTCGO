"""Venonat UNB 9 Radar Eyes (live report, Oct 12): after picking from the
7 looked-at cards, the other cards "flashed up" before the shuffle -- the
attack revealed them in place AND showed them in the pick browser.  Same
double-show on Watchog's Scrutinize (which also re-revealed a fresh top 2
after the discard) and Alolan Muk's Adventurous Appetite."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2


class LookAtTopNoDoubleReveal(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def run_card(self, path, title, attack=True):
        t = Table(self)
        d = fixtures.definition(path)
        me = neutral(t.put(d, P1, 'active'))
        neutral(t.put(self.filler, P2, 'active'))
        reveals, browsers = [], []

        async def rv(ctx, cards, to_player=None):
            reveals.append(len(list(cards)))

        def picks(cards, count, prompt, display):
            browsers.append(len(display or []))
            return cards[:count]
        t.picks = picks
        with patch.object(EffectContext, 'reveal_cards', rv):
            if attack:
                ab = next(a for a in d.abilities if a.title == title)
                pay_cost(t, me, ab)
                t.state.turn_number = 3
                await t.attack(me, title)
            else:
                await t.effect(d, me, title)
        return t, reveals, browsers

    async def test_venonat_radar_eyes(self):
        t, reveals, browsers = await self.run_card('SM10.Venonat_9', 'Radar Eyes')
        self.assertEqual(browsers, [7])
        self.assertEqual(reveals, [])
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_watchog_scrutinize(self):
        t, reveals, browsers = await self.run_card('SM2.Watchog_108', 'Scrutinize')
        self.assertEqual(browsers, [2])
        self.assertEqual(reveals, [])

    async def test_alolan_muk_adventurous_appetite_shows_browser_even_without_items(self):
        t, reveals, browsers = await self.run_card(
            'SM9.AlolanMuk_84', 'Adventurous Appetite', attack=False)
        self.assertEqual(browsers, [6])          # filler deck has Items
        self.assertEqual(reveals, [])


if __name__ == '__main__':
    unittest.main()
