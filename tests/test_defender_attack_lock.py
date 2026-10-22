"""'During your opponent's next turn, the Defending Pokémon can't use attacks'
(Aurorus POR Freezing Chill, Cubchoo BLK Snotted Up) locks the DEFENDER,
not the attacker."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P2

CARDS = [('ME3.Aurorus_24', 'Freezing Chill'), ('ZSV10PT5.Cubchoo_25', 'Snotted Up')]


class DefenderAttackLockTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def test_defender_locked_attacker_free(self):
        for path, title in CARDS:
            with self.subTest(path=path):
                attack = next(a for a in fixtures.definition(path).abilities
                              if isinstance(a, Attack) and a.title == title)
                self.assertFalse(attack.locks_next_turn)
                rig, e = self.rig(path, 'pokemon')
                attacker = e['target']
                defender = rig.board.active_pokemon(P2)
                await attack.effect(EffectContext(rig.session, attacker.owning_player_id, attacker, attack))
                locks = rig.session.turn_state.attack_locks
                self.assertTrue(any(key[0] == defender.entity_id for key in locks))
                self.assertFalse(any(key[0] == attacker.entity_id for key in locks))

    def test_self_locks_still_flagged(self):
        attack = Attack("X", "During your next turn, this Pokémon can't use X.", locks_next_turn=True)
        self.assertTrue(attack.locks_next_turn)


if __name__ == "__main__":
    unittest.main()
