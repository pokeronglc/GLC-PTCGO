"""Team Rocket's Tyranitar - Sand Stream: during Checkup, while Active, put 2
damage counters on each of the opponent's BASIC Pokémon only."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID, PokemonStage
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

PATH = 'SV10.TeamRocketsTyranitar_96'


class SandStreamTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def _run(self, bench_source=False):
        rig, e = self.rig(PATH, 'pokemon')
        board = rig.board
        opp = board.pokemon_in_play(P2)
        self.assertGreaterEqual(len(opp), 3)
        opp[-1].set_attribute(AttrID.STAGE, PokemonStage.STAGE1.value)
        opp[-2].set_attribute(AttrID.STAGE, PokemonStage.STAGE2.value)
        for p in opp:
            p.set_attribute(AttrID.HP, effective_max_hp(board, p))
        source = e['target']
        if bench_source:
            active = board.find_player_area(P1, 'activePokemonArea')
            bench = board.find_player_area(P1, 'bench')
            active.remove_child(source)
            board.add_card_to_area(source, bench)
        ability = next(a for a in fixtures.definition(PATH).abilities if a.title == 'Sand Stream')
        await ability.effect(EffectContext(rig.session, P1, source, ability))
        return [effective_max_hp(board, p) - p.get_attribute(AttrID.HP) for p in opp]

    async def test_only_basics_take_counters(self):
        damage = await self._run()
        self.assertEqual(damage[-1], 0)
        self.assertEqual(damage[-2], 0)
        self.assertTrue(all(d == 20 for d in damage[:-2]))

    async def test_nothing_from_the_bench(self):
        self.assertTrue(all(d == 0 for d in await self._run(bench_source=True)))


if __name__ == "__main__":
    unittest.main()
