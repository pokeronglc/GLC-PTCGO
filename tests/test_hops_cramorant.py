"""Hop's Cramorant - Fickle Spitting: 120 damage only when the opponent has
exactly 3 or 4 Prize cards left; otherwise usable but does nothing."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P2

PATH = 'SV09.HopsCramorant_138'


class HopsCramorantTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def _damage_with_prizes(self, count):
        rig, e = self.rig(PATH, 'pokemon')
        prizes = rig.board.find_player_area(P2, 'prizePile')
        while len(prizes.children) > count:
            prizes.remove_child(prizes.children[-1])
        defender = rig.board.active_pokemon(P2)
        defender.set_attribute(AttrID.HP, 400)
        defender.set_attribute(AttrID.WEAKNESS_TYPES, [])
        defender.set_attribute(AttrID.RESISTANCE_TYPES, [])
        attack = next(a for a in fixtures.definition(PATH).abilities
                      if getattr(a, 'title', '') == 'Fickle Spitting')
        attacker = rig.board.active_pokemon(e['target'].owning_player_id) or e['target']
        await attack.effect(EffectContext(rig.session, e['target'].owning_player_id, attacker, attack))
        return 400 - defender.get_attribute(AttrID.HP, 0)

    async def test_damage_only_at_three_or_four_prizes(self):
        for count, expected in ((1, 0), (2, 0), (3, 120), (4, 120), (5, 0), (6, 0)):
            with self.subTest(prizes=count):
                self.assertEqual(await self._damage_with_prizes(count), expected)


if __name__ == "__main__":
    unittest.main()
