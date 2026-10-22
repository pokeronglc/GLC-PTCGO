"""Double Turbo Energy's "20 less damage" applies to the attack it was
attached for, even when that attack discards it before doing damage."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

CASES = [  # (card, attack, printed damage)
    ('SWSH9.Infernape_26', 'Burning Kick', 160),       # discards everything BEFORE damage
    ('TwentiethAnn.Raichu_27', 'Thunderbolt', 100),    # discards everything after damage
    ('BW4.Reshiram_21', 'Blue Flare', 120),            # DTE stays attached
]


class DoubleTurboDiscardTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _damage(self, path, title, with_turbo):
        rig, e = self.rig(path, 'pokemon')
        board, attacker = rig.board, e['target']
        if with_turbo:
            turbo = self.add(rig, fixtures.definition('SWSH9.DoubleTurboEnergy_151'), P1, 'hand')
            board.attach_card(turbo.entity_id, attacker.entity_id)
        defender = board.active_pokemon(P2)
        defender.set_attribute(AttrID.HP, 999)
        defender.set_attribute(AttrID.WEAKNESS_TYPES, [])
        defender.set_attribute(AttrID.RESISTANCE_TYPES, [])
        attack = next(a for a in fixtures.definition(path).abilities if getattr(a, 'title', '') == title)
        await attack.effect(EffectContext(rig.session, P1, attacker, attack))
        return 999 - defender.get_attribute(AttrID.HP)

    async def test_twenty_less_exactly_once(self):
        for path, title, printed in CASES:
            with self.subTest(card=path):
                self.assertEqual(await self._damage(path, title, False), printed)
                self.assertEqual(await self._damage(path, title, True), printed - 20)


if __name__ == "__main__":
    unittest.main()
