"""Gardenia's Vigor: the draw is shown to the player BEFORE the attach prompt
(it used to play out after it, like Welder)."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1

PATH = 'SWSH10.GardeniasVigor_143'


class GardeniasVigorOrderTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def test_draw_flushed_before_attach_prompt(self):
        rig, e = self.rig(PATH, 'trainer')
        events = []
        original_flush = EffectContext.flush_choreography

        async def flush(ctx_self, *a, **k):
            events.append('flush')
            return await original_flush(ctx_self, *a, **k)

        async def choose(ctx_self, *a, **k):
            events.append('prompt')
            return None

        with patch.object(EffectContext, 'flush_choreography', flush), \
             patch.object(EffectContext, 'choose_pokemon', choose), \
             patch('spirit.game.card_effects.trainers.is_grass_energy_card', lambda c: True):
            await fixtures.definition(PATH).effect(EffectContext(rig.session, P1, e['target'], None))
        self.assertIn('prompt', events)
        self.assertIn('flush', events[:events.index('prompt')])


if __name__ == "__main__":
    unittest.main()
