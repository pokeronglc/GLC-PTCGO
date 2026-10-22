"""Bug hunt 10: "next turn" / "this turn" effects (timing, scope, expiry).

Regression tests for real bugs found by the next-turn sweep
(audits/results/hunt4/). Each asserts the CORRECT behaviour; the ones
still broken are marked @unittest.expectedFailure with a `# BUG:` line.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import pay_cost, neutral
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.passives import compute_damage
from spirit.tools.effect_smoke import P1, P2


def _attack_def(pokemon, title):
    return next(a for a in def_for(pokemon.archetype_id).abilities
                if isinstance(a, Attack) and a.title == title)


class NextTurnBugs(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def board(self, mine, theirs=None):
        t = Table(self)
        me = neutral(t.put(mine, P1, 'active'))
        opp = neutral(t.put(theirs or self.filler, P2, 'active'))
        neutral(t.put(self.filler, P1, 'bench'))
        neutral(t.put(self.filler, P2, 'bench'))
        return t, me, opp

    async def use_attack(self, t, me, title):
        pay_cost(t, me, _attack_def(me, title))
        await t.attack(me, title)

    # ------------------------------------------------------------------
    # "The Defending Pokémon's Weakness is now X ... (The amount of
    # Weakness doesn't change.)" on a Pokémon with NO Weakness.
    # ------------------------------------------------------------------
    async def _weakness_change(self, path, title):
        t, me, opp = self.board(path)
        opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        await self.use_attack(t, me, title)
        t.next_turn()
        t.next_turn()                       # the attacker's next turn
        # a Colorless/Darkness/Psychic attacker hits for 100: no Weakness to apply
        attacker = neutral(t.put(self.filler, P1, 'bench'))
        typ = {'SV08.Oranguru_156': PokemonTypes.COLORLESS, 'SWSH9.Spiritomb_89': PokemonTypes.DARKNESS,
               'SM10.Meowstic_80': PokemonTypes.PSYCHIC}[path]
        attacker.set_attribute(AttrID.POKEMON_TYPES, [typ.value])
        return compute_damage(t.board, attacker, opp, 100).amount

    # FIXED Oct 13 (was: a Pokémon with no Weakness gains a x2 Weakness ("the amount of Weakness doesn't change")
    async def test_oranguru_now_youre_in_my_power_no_weakness_stays_none(self):
        self.assertEqual(await self._weakness_change('SV08.Oranguru_156', "Now You're in My Power"), 100)

    # FIXED Oct 13 (was: a Pokémon with no Weakness gains a x2 Weakness ("the amount of Weakness doesn't change")
    async def test_spiritomb_ticking_terror_no_weakness_stays_none(self):
        self.assertEqual(await self._weakness_change('SWSH9.Spiritomb_89', 'Ticking Terror'), 100)

    async def test_oranguru_existing_weakness_changes_type_keeps_amount(self):
        """Control: with a Fire Weakness, Colorless now hits x2 during the next turn only."""
        t, me, opp = self.board('SV08.Oranguru_156')
        opp.set_attribute(AttrID.WEAKNESS_TYPES, [PokemonTypes.FIRE.value])
        await self.use_attack(t, me, "Now You're in My Power")
        t.next_turn()
        t.next_turn()
        attacker = neutral(t.put(self.filler, P1, 'bench'))
        attacker.set_attribute(AttrID.POKEMON_TYPES, [PokemonTypes.COLORLESS.value])
        self.assertEqual(compute_damage(t.board, attacker, opp, 100).amount, 200)
        t.next_turn()
        t.next_turn()
        self.assertEqual(compute_damage(t.board, attacker, opp, 100).amount, 100)

    # ------------------------------------------------------------------
    # Wingull SM1 37 Roost: "Heal 30 damage from this Pokémon. It can't
    # retreat during your next turn."  "It" = Wingull, on ITS next turn.
    # ------------------------------------------------------------------
    async def _roost(self):
        t, me, opp = self.board('SM1.Wingull_37')
        t.energy(me, PokemonTypes.WATER, 3)
        t.energy(opp, PokemonTypes.WATER, 4)
        await self.use_attack(t, me, 'Roost')
        t.next_turn()                                   # opponent's turn
        opp_can_retreat = t.can(opp, 'BaseRetreat', P2)
        t.next_turn()                                   # Wingull's next turn
        wingull_can_retreat = t.can(me, 'BaseRetreat', P1)
        t.next_turn()
        t.next_turn()
        wingull_later = t.can(me, 'BaseRetreat', P1)
        return opp_can_retreat, wingull_can_retreat, wingull_later

    # FIXED Oct 13 (was: Roost's "It can't retreat during your next turn" locks the DEFENDING Pokémon for the opponent's turn
    async def test_wingull_roost_does_not_lock_the_defending_pokemon(self):
        opp_can_retreat, _, _ = await self._roost()
        self.assertTrue(opp_can_retreat)

    # FIXED Oct 13 (was: Roost never stops Wingull itself from retreating during its owner's next turn
    async def test_wingull_roost_locks_itself_next_turn_only(self):
        _, wingull_can_retreat, wingull_later = await self._roost()
        self.assertEqual((wingull_can_retreat, wingull_later), (False, True))


if __name__ == '__main__':
    unittest.main()
