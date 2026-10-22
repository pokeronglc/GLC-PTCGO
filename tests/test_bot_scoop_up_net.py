"""The bot must not Scoop Up Net its only Pokémon (an instant loss)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.session.ai_policy import choose_action
from spirit.game.session.legal_actions import compute_legal_actions
from spirit.tools.effect_smoke import P1


class BotScoopUpNetTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def offered_net(self, keep_bench):
        rig, e = self.rig('SWSH2.ScoopUpNet_207', 'trainer')
        board, session = rig.board, rig.session
        if not keep_bench:
            discard = board.find_player_area(P1, 'discard')
            for pokemon in list(board.find_player_area(P1, 'bench').children):
                board.move_card(pokemon.entity_id, discard.entity_id)
        actions = compute_legal_actions(board, session.turn_state, P1, session.game_id)
        net = e['target']
        only_trainers = [a for a in actions if a['entityID'] == net.entity_id]
        if not only_trainers:
            return None
        picked = choose_action(session, P1, only_trainers)
        return picked is not None

    def test_lone_pokemon_is_never_scooped(self):
        self.assertIs(self.offered_net(keep_bench=False), False)

    def test_with_a_bench_it_may_still_play_it(self):
        self.assertIs(self.offered_net(keep_bench=True), True)


if __name__ == "__main__":
    unittest.main()
