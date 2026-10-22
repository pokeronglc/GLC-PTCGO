"""Trainer deck searches that offered the wrong cards or the wrong number.

Found from a player report (Brigette only took 1 Basic Pokémon) and a sweep
of every GLC-legal Item and Supporter that searches the deck.
"""
import unittest
from unittest import mock
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit import config
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1

DECK = ['BW7.Charmander_18', 'BW7.Charmeleon_19', 'BW7.Charizard_20', 'BW5.Bulbasaur_1',
        'BW1.Munna_48', 'BW1.Timburr_58', 'BW1.Pikachu_115', 'BW7.Snorlax_109',
        'SV09.HopsWooloo_135', 'SV09.HopsSnorlax_117', 'ME3.Amaura_23',
        'SV10.TeamRocketsEkans_112', 'SV10.TeamRocketsRaticate_148',
        'SM7.ApricornMaker_124', 'SV1.Nemona_180', 'SV065.NightStretcher_61',
        'XY5.RepeatBall_136']


def name(card):
    return def_for(card.archetype_id).display_name


class TrainerSearchFixTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def play(self, path, hand=(), heads=True):
        """Play a Trainer against DECK, taking the most cards each search allows.
        Returns (offered name sets per search, counts per search, ctx)."""
        rig, e = self.rig(path, 'trainer')
        for key in DECK:
            self.add(rig, fixtures.definition(key), P1, 'deck')
        for key in hand:
            self.add(rig, fixtures.definition(key), P1, 'hand')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        offered, counts = [], []

        async def search_deck(predicate=None, count=1, **kw):
            eligible = [c for c in ctx.deck() if predicate is None or predicate(c)]
            offered.append({name(c) for c in eligible})
            counts.append(count)
            return eligible[:count]

        async def search_deck_groups(groups, **kw):
            chosen, used = [], set()
            for group in groups:
                predicate, n = group[0], group[1]
                eligible = [c for c in ctx.deck() if predicate(c) and c not in used]
                offered.append({name(c) for c in eligible})
                counts.append(n)
                used.update(eligible[:n])
                chosen.append(eligible[:n])
            return chosen

        ctx.search_deck = search_deck
        ctx.search_deck_groups = search_deck_groups
        ctx.choose_cards = AsyncMock(side_effect=lambda cards, count=1, **kw: list(cards)[:count])
        ctx.flip_coins = AsyncMock(return_value=[heads])
        ctx.shuffle_deck = AsyncMock()
        ctx.shuffle_into_deck = AsyncMock()
        ctx.bench_before = len(ctx.my_bench())
        ctx.hand_pokemon_before = sum(1 for c in ctx.hand() if c.get_attribute(
            fixtures.AttrID.CARD_TYPE) == 0)
        with mock.patch.object(config, "GLC_ONLY", True):
            await fixtures.definition(path).effect(ctx)
        return offered, counts, ctx

    async def test_brigette_benches_three_basic_pokemon(self):
        offered, counts, ctx = await self.play('XY8.Brigette_134')
        self.assertEqual(counts, [3])
        self.assertNotIn('Charmeleon', offered[0])
        self.assertEqual(len(ctx.my_bench()) - ctx.bench_before, 3)

    async def test_hops_bag_only_basic_hops_pokemon(self):
        offered, counts, _ = await self.play('SV09.HopsBag_147')
        self.assertEqual(offered, [{"Hop's Wooloo", "Hop's Snorlax"}])

    async def test_korrina_finds_a_fighting_pokemon_and_an_item(self):
        offered, counts, ctx = await self.play('XY3.Korrina_111')
        self.assertEqual(counts, [1, 1])
        self.assertIn('Timburr', offered[0])
        self.assertNotIn('Munna', offered[0])
        self.assertIn('Night Stretcher', offered[1])
        self.assertTrue({'Timburr', 'Night Stretcher'} <= {name(c) for c in ctx.hand()})

    async def test_larrys_skill_finds_three_kinds(self):
        offered, counts, _ = await self.play('SV085.LarrysSkill_115')
        self.assertEqual(counts, [1, 1, 1])
        self.assertIn('Nemona', offered[1])
        self.assertNotIn('Night Stretcher', offered[1])

    async def test_love_ball_matches_opponents_names_only(self):
        rig_names = None
        offered, _, ctx = await self.play('SV06.LoveBall_156')
        rig_names = {name(p) for p in ctx.opponent_pokemon_in_play()}
        self.assertTrue(offered[0])
        self.assertLessEqual(offered[0], rig_names)

    async def test_repeat_ball_matches_your_names_only(self):
        offered, _, ctx = await self.play('XY5.RepeatBall_136')
        self.assertLessEqual(offered[0], {name(p) for p in ctx.my_pokemon_in_play()})

    async def test_fossil_researcher_only_amaura_or_tyrunt(self):
        offered, _, _ = await self.play('XY3.FossilResearcher_110')
        self.assertEqual(offered, [{'Amaura'}])

    async def test_poke_maniac_retreat_cost_exactly_four(self):
        offered, _, _ = await self.play('SM11.PokManiac_204')
        self.assertIn('Snorlax', offered[0])
        self.assertNotIn('Charizard', offered[0])   # retreat cost 3

    async def test_professor_elms_lecture_60_hp_or_less(self):
        offered, _, _ = await self.play('SM8.ProfessorElmsLecture_188')
        self.assertIn('Pikachu', offered[0])        # 60 HP
        self.assertNotIn('Munna', offered[0])       # 70 HP

    async def test_professor_oaks_setup_different_types(self):
        _, counts, ctx = await self.play('SM12.ProfessorOaksSetup_201')
        new = ctx.my_bench()[ctx.bench_before:]
        types = [tuple(p.get_attribute(fixtures.AttrID.POKEMON_TYPES) or []) for p in new]
        self.assertEqual(len(new), 3)
        self.assertEqual(len(types), len(set(types)))

    async def test_apricorn_maker_only_ball_items(self):
        offered, _, _ = await self.play('SM7.ApricornMaker_124')
        self.assertEqual(offered, [{'Repeat Ball'}])

    async def test_team_rockets_great_ball_coin_picks_the_stage(self):
        offered, _, _ = await self.play('ME2PT5.TeamRocketsGreatBall_205', heads=True)
        self.assertEqual(offered, [{"Team Rocket's Raticate"}])
        offered, _, _ = await self.play('ME2PT5.TeamRocketsGreatBall_205', heads=False)
        self.assertEqual(offered, [{"Team Rocket's Ekans"}])

    async def test_perrin_finds_as_many_pokemon_as_went_back(self):
        offered, counts, ctx = await self.play('SV06.Perrin_160', hand=['BW1.Munna_48'])
        returned = ctx.shuffle_into_deck.await_args.args[0]
        self.assertTrue(1 <= len(returned) <= 2)
        self.assertEqual(counts, [len(returned)])


if __name__ == "__main__":
    unittest.main()
