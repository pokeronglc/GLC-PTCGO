"""Mew (XY10) - Memories of Dawn: Mew can use the attacks of your other Basic
Pokémon in play (not evolved ones, not the opponent's)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID, PokemonStage
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.passives import granted_extra_attacks
from spirit.tools.effect_smoke import P1, P2


def _attacks(card):
    return {a.ability_id for a in (def_for(card.archetype_id).abilities or []) if isinstance(a, Attack)}


class MemoriesOfDawnTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    def test_copies_own_benched_basics_only(self):
        rig, e = self.rig('XY10.Mew_29', 'pokemon')
        board = rig.board
        mew = e['target']
        bench = [p for p in board.pokemon_in_play(P1) if p is not mew
                 and def_for(p.archetype_id).display_name != 'Mew']
        self.assertGreaterEqual(len(bench), 2)
        bench[-1].set_attribute(AttrID.STAGE, PokemonStage.STAGE1.value)
        granted = {a.ability_id for a in granted_extra_attacks(board, mew)}
        self.assertTrue(_attacks(bench[0]))
        self.assertTrue(_attacks(bench[0]) <= granted)
        self.assertFalse(_attacks(bench[-1]) - _attacks(bench[0]) & granted)
        for theirs in board.pokemon_in_play(P2):
            self.assertFalse((_attacks(theirs) - _attacks(bench[0])) & granted)


if __name__ == "__main__":
    unittest.main()
