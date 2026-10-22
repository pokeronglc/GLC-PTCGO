"""Bugs found by the bot-vs-bot stress test (Oct 12) and Archen WHT 50."""
import unittest

from tests.test_bughunt7_chunk36 import Chunk36, FIRE, WATER, LIGHT
from tests.test_bughunt7_chunk9 import ELECTRODE_EVO, MAGNEMITE
from spirit.game.attributes import AttrID
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

PLUME, ARCHEN = 'RSV10PT5.AntiquePlumeFossil_79', 'RSV10PT5.Archen_50'
TOOL_JAMMER, FURY_BELT = 'SWSH5.ToolJammer_136', 'XY9.FightingFuryBelt_99'
POISONED = 'Poisoned'


class StressFindings(Chunk36):
    async def _to_deck(self, method):
        t = self.table()
        self.mine(t, self.filler)
        mon = t.put(self.filler, P1, 'bench')
        full = mon.get_attribute(AttrID.HP)
        mon.set_attribute(AttrID.HP, full - 50)
        ctx = EffectContext(t.session, P1, mon, None)
        await t._run(lambda: getattr(ctx, method)(mon))
        self.assertIn(mon, t.zone(P1, 'deck'))
        self.assertEqual(mon.get_attribute(AttrID.HP), full)

    async def test_bottom_of_deck_clears_damage(self):
        await self._to_deck('put_on_bottom_of_deck')

    async def test_top_of_deck_clears_damage(self):
        await self._to_deck('put_on_top_of_deck')

    async def test_tool_jammer_resyncs_opponents_belt_hp(self):
        t = self.table()
        mine = self.mine(t, self.filler)
        basic = t.put(self.filler, P2, 'active')    # opponent's Active Basic with a Belt
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        t.attach(FURY_BELT, basic)
        await t._run(lambda: t.session.resync_effective_max_hp())
        belted = basic.get_attribute(AttrID.HP)
        await t.play(t.put(TOOL_JAMMER, P1, 'hand'), targets=[mine.entity_id])
        self.assertIn(t.zone(P1, 'active')[0], [mine])
        self.assertEqual(basic.get_attribute(AttrID.HP), belted - 40)

    async def test_retreat_paid_with_pokemon_attached_as_energy(self):
        t = self.table()
        target = self.mine(t, MAGNEMITE, zone='active')
        new = self.mine(t, self.filler, zone='bench')
        electrode = self.mine(t, ELECTRODE_EVO, zone='bench')
        t.pokemon = lambda cands, prompt: target
        await t.use(electrode, 'Buzzap Thunder')
        self.assertIn(electrode, t.board.attached_energies(target))
        t.next_turn(); t.next_turn()
        retreat = next(iter(t.offers(target, 'BaseRetreat')))
        await t.do(retreat, targets=[new.entity_id, electrode.entity_id])
        self.assertIs(t.active(P1), new)

    async def test_archen_evolves_from_antique_plume_fossil(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        await t.play(t.put(PLUME, P1, 'hand'))
        fossil = t.zone(P1, 'bench')[0]
        t.next_turn(); t.next_turn()
        archen = t.put(ARCHEN, P1, 'hand')
        self.assertIn(fossil.entity_id, t.targets(archen, 'EvolvePokemonPlayAbility'))


for _n in [n for n in vars(Chunk36) if n.startswith('test_')]:
    setattr(StressFindings, _n, None)

if __name__ == '__main__':
    unittest.main()
