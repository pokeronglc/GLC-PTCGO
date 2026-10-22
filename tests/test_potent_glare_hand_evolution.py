"""Team Rocket's Arbok's Potent Glare ("your opponent can't play any Pokémon
that has an Ability from their hand, except for Team Rocket's Pokémon") also
stops Rare Candy and a Fossil's Evolve putting such a card from hand (Oct 21)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.tools.effect_smoke import P1, P2

ARBOK, CANDY = 'SV10.TeamRocketsArbok_113', 'SWSH1.RareCandy_180'


class PotentGlareHandEvolution(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, glare=True):
        t = Table(self)
        t.put(ARBOK if glare else self.filler, P2, 'active')
        return t

    async def candy_into(self, basic, stage2, glare=True):
        t = self.table(glare)
        mon = t.put(basic, P1, 'active')
        evo = t.put(stage2, P1, 'hand')
        candy = t.put(CANDY, P1, 'hand')
        t.next_turn(); t.next_turn()
        offered = bool(t.offers(candy))
        if offered:
            await t.play(candy)
        return t, mon, evo, offered

    async def test_rare_candy_blocked_for_ability_stage2(self):
        t, mon, evo, offered = await self.candy_into('SV035.Dratini_147', 'SV035.Dragonite_149')
        self.assertFalse(offered)
        self.assertIn(evo, t.zone(P1, 'hand'))

    async def test_rare_candy_fine_without_glare(self):
        t, mon, evo, offered = await self.candy_into('SV035.Dratini_147', 'SV035.Dragonite_149', glare=False)
        self.assertTrue(offered)
        self.assertIs(t.active(P1), evo)

    async def test_rare_candy_fine_for_no_ability_stage2(self):
        t, mon, evo, offered = await self.candy_into('SV035.Gastly_92', 'SV035.Gengar_94')
        self.assertTrue(offered)
        self.assertIs(t.active(P1), evo)

    async def test_team_rocket_stage2_allowed(self):
        t, mon, evo, offered = await self.candy_into('SV10.TeamRocketsMareep_72', 'SV10.TeamRocketsAmpharos_74')
        self.assertTrue(offered)
        self.assertIs(t.active(P1), evo)

    async def test_effect_refuses_blocked_hand_card(self):
        from spirit.game.session.effects import EffectContext
        t = self.table()
        mon = t.put('SV035.Dratini_147', P1, 'active')
        evo = t.put('SV035.Dragonite_149', P1, 'hand')
        ctx = EffectContext(t.session, P1, mon, None)
        self.assertFalse(await ctx.evolve_pokemon(mon, evo))
        self.assertIn(evo, t.zone(P1, 'hand'))


if __name__ == "__main__":
    unittest.main()
