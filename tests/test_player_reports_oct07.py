"""Player reports: Inkay/Malamar family, Parallel City over Parallel City,
Spring Bloom with Growing Grass Energy, Distortion Door not benching."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.data_utils import CARD_DEFS_BY_GUID, PokemonCardDef
from spirit.game.session.effects import EffectContext, is_energy_of_type
from spirit.game.session.legal_actions import same_stadium_in_play
from spirit.game.attributes import PokemonTypes
from spirit.tools.effect_smoke import P1, P2


def _def_named(name, **match):
    return next(d for d in CARD_DEFS_BY_GUID.values()
                if d.display_name == name
                and all(getattr(d, k, None) == v for k, v in match.items()))


class PlayerReportOct07Tests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def test_every_malamar_shares_inkays_family(self):
        key = str(AttrID.FAMILY_ID.value)
        inkay = {d.extra_attributes[key]['value'] for d in CARD_DEFS_BY_GUID.values()
                 if isinstance(d, PokemonCardDef) and d.display_name == 'Inkay'}
        malamar = {d.extra_attributes[key]['value'] for d in CARD_DEFS_BY_GUID.values()
                   if isinstance(d, PokemonCardDef) and d.display_name == 'Malamar'}
        self.assertEqual(len(inkay), 1)
        self.assertEqual(malamar, inkay)

    def test_parallel_city_cannot_replace_parallel_city(self):
        rig, e = self.rig('XY8.ParallelCity_145')
        city = fixtures.definition('XY8.ParallelCity_145')
        slot = rig.board.find_global_area('activeStadium')
        rig.board.move_card(e['target'].entity_id, slot.entity_id)
        second = self.add(rig, city, P2, 'hand')
        self.assertTrue(same_stadium_in_play(rig.board, second))

    async def test_spring_bloom_ignores_growing_grass_energy_in_hand(self):
        rig, e = self.rig('SWSH5.Cherrim_8')
        hand = rig.board.find_player_area(P1, 'hand')
        deck = rig.board.find_player_area(P1, 'deck')
        for card in list(hand.children):
            if type(card).__name__ == 'EnergyEntity':
                rig.board.move_card(card.entity_id, deck.entity_id)
        growing = self.add(rig, _def_named('Growing Grass Energy'), P1, 'hand')
        self.assertFalse(is_energy_of_type(growing, PokemonTypes.GRASS))
        ability = fixtures.definition('SWSH5.Cherrim_8').abilities[0]
        self.assertFalse(ability.condition(rig.board, P1, e['target']))
        # Attached, it does provide Grass.
        rig.attach(growing, e['target'])
        self.assertTrue(is_energy_of_type(growing, PokemonTypes.GRASS))

    async def test_distortion_door_benches_giratina_before_counters(self):
        rig, e = self.rig('SM8.Giratina_97')
        board = rig.board
        definition = fixtures.definition('SM8.Giratina_97')
        discard = board.find_player_area(P1, 'discard')
        bench = board.find_player_area(P1, 'bench')
        giratina = next(c for c in discard.children if c.archetype_id == definition.guid)
        opp_bench = list(board.find_player_area(P2, 'bench').children)
        before = [p.get_attribute(AttrID.HP) for p in opp_bench]
        ability = definition.abilities[0]
        self.assertTrue(ability.condition(board, P1, giratina))
        ctx = EffectContext(rig.session, P1, giratina, ability)
        ctx.ask_yes_no = AsyncMock(return_value=True)
        await ability.effect(ctx)
        self.assertIn(giratina, bench.children)
        self.assertEqual([p.get_attribute(AttrID.HP) for p in opp_bench],
                         [hp - 10 for hp in before[:2]] + before[2:])

    async def test_distortion_door_needs_bench_space(self):
        rig, e = self.rig('SM8.Giratina_97')
        board = rig.board
        definition = fixtures.definition('SM8.Giratina_97')
        bench = board.find_player_area(P1, 'bench')
        filler = fixtures.definition('BW7.Charmander_18')
        while len(bench.children) < 5:
            self.add(rig, filler, P1, 'bench')
        self.assertFalse(definition.abilities[0].condition(board, P1, None))


if __name__ == "__main__":
    unittest.main()


class FamilyGapTests(unittest.TestCase):
    """Stamped MEP Toxel (and Tyrunt) were imported without a family ID."""

    @classmethod
    def setUpClass(cls):
        fixtures.HgssRulesTests.setUpClass.__func__(cls)
        # Other suites re-import card scripts into the shared registry; apply
        # the loader's normalisation to whatever definitions are current.
        from spirit.game.scripts.cards import loader
        loader._normalize_evolution_families()

    def test_every_glc_pokemon_has_its_lines_family(self):
        from spirit.game import glc
        key = str(AttrID.FAMILY_ID.value)
        missing = [(d.set_code, d.collector_number, d.display_name)
                   for d in CARD_DEFS_BY_GUID.values()
                   if isinstance(d, PokemonCardDef) and glc.is_glc_legal(d)
                   and not (d.extra_attributes.get(key) or {}).get('value')]
        self.assertEqual(missing, [])
        toxels = {d.extra_attributes[key]['value'] for d in CARD_DEFS_BY_GUID.values()
                  if isinstance(d, PokemonCardDef) and d.display_name in ('Toxel', 'Toxtricity')}
        self.assertEqual(toxels, {848})


class HandAndAbilityGateTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def test_call_a_buddy_needs_an_empty_hand(self):
        rig, e = self.rig('ME5.Silvally_70')
        board = rig.board
        hand = board.find_player_area(P1, 'hand')
        deck = board.find_player_area(P1, 'deck')
        for card in list(hand.children)[1:]:
            board.move_card(card.entity_id, deck.entity_id)
        ability = fixtures.definition('ME5.Silvally_70').abilities[0]
        self.assertFalse(ability.condition(board, P1, e['target']))
        board.move_card(hand.children[0].entity_id, deck.entity_id)
        self.assertTrue(ability.condition(board, P1, e['target']))

    def test_greens_exploration_blocked_by_an_ability_pokemon(self):
        from spirit.game.session.legal_actions import trainer_condition_met
        rig, e = self.rig('SM10.GreensExploration_175')
        definition = fixtures.definition('SM10.GreensExploration_175')
        self.assertTrue(trainer_condition_met(definition.condition, rig.board, P1, e['target']))
        self.add(rig, fixtures.definition('ME5.Silvally_70'), P1, 'bench')
        self.assertFalse(trainer_condition_met(definition.condition, rig.board, P1, e['target']))


class ScaleUpHealTests(unittest.IsolatedAsyncioTestCase):
    """Alolan Exeggutor: Energy attached by an effect switches on Scale Up
    (+250 HP); damage taken must stay the same, so Mega Drain heals."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_effect_attach_keeps_damage_then_heals(self):
        from spirit.game.models.board import EnergyEntity
        from spirit.game.session import passives
        rig, e = self.rig('ME55.AlolanExeggutor_2')
        board, exeggutor = rig.board, e['target']
        for card in list(exeggutor.children):
            if isinstance(card, EnergyEntity):
                rig.to_area(card, P1, 'discard')
        exeggutor.set_attribute(AttrID.HP, 100)               # 50 damage of 150
        grass = next(d for d in CARD_DEFS_BY_GUID.values()
                     if d.display_name == 'Grass Energy' and 'Special' not in (d.subtypes or []))
        ctx = EffectContext(rig.session, P1, exeggutor, None)
        for _ in range(6):
            await ctx.attach_energy(self.add(rig, grass, P1, 'hand'), exeggutor)
        self.assertEqual(passives.effective_max_hp(board, exeggutor), 400)
        self.assertEqual(exeggutor.get_attribute(AttrID.HP), 350)   # still 50 damage
        attack = next(a for a in fixtures.definition('ME55.AlolanExeggutor_2').abilities
                      if a.title == 'Mega Drain')
        await attack.effect(EffectContext(rig.session, P1, exeggutor, attack))
        self.assertEqual(exeggutor.get_attribute(AttrID.HP), 400)


class NeedlyArmorTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_three_counters_per_grass_energy(self):
        from spirit.game.models.board import EnergyEntity
        rig, e = self.rig('ME4.Chesnaught_7')
        board, chesnaught = rig.board, e['target']
        for card in list(chesnaught.children):
            if isinstance(card, EnergyEntity):
                rig.to_area(card, P1, 'discard')
        grass = next(d for d in CARD_DEFS_BY_GUID.values()
                     if d.display_name == 'Grass Energy' and 'Special' not in (d.subtypes or []))
        for _ in range(3):
            rig.attach(self.add(rig, grass, P1, 'hand'), chesnaught)
        attacker = board.active_pokemon(P2)
        before = attacker.get_attribute(AttrID.HP)
        ability = fixtures.definition('ME4.Chesnaught_7').abilities[0]
        ctx = EffectContext(rig.session, P1, chesnaught, ability)
        ctx.damaged_by = attacker
        await ability.effect(ctx)
        self.assertEqual(before - attacker.get_attribute(AttrID.HP), 90)


class ProtonFirstTurnTests(unittest.TestCase):
    """Reprints dropped Team Rocket's Proton's first-turn exemption."""

    @classmethod
    def setUpClass(cls):
        fixtures.HgssRulesTests.setUpClass.__func__(cls)

    def test_every_printing_keeps_usable_first_turn(self):
        printings = [d for d in CARD_DEFS_BY_GUID.values()
                     if d.display_name == "Team Rocket's Proton"]
        self.assertGreaterEqual(len(printings), 3)
        self.assertTrue(all(d.usable_first_turn for d in printings))


class DevolutionSprayZStadiumTests(unittest.IsolatedAsyncioTestCase):
    """Spray Z's "can't evolve this turn" yields to Forest of Vitality /
    Forest of Giant Plants, like plain Devolution Spray."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def sprayed(self, stadium, spray_path='SM10.DevolutionSprayZ_166'):
        from spirit.game.session.legal_actions import compute_legal_actions
        rig, e = self.rig(spray_path)
        board, session, ts = rig.board, rig.session, rig.session.turn_state
        if stadium:
            card = self.add(rig, fixtures.definition(stadium), P2, 'hand')
            board.move_card(card.entity_id, board.find_global_area('activeStadium').entity_id)
        roselia = self.add(rig, fixtures.definition('SV05.Roselia_8'), P1, 'bench')
        ts.begin_turn(P2); ts.begin_turn(P1)
        roserade = self.add(rig, fixtures.definition('SV05.Roserade_9'), P1, 'hand')
        await session.perform_evolution(P1, roserade, roselia)
        ts.begin_turn(P2); ts.begin_turn(P1)
        spray = fixtures.definition(spray_path)
        ctx = EffectContext(session, P1, e['target'], None)
        ctx.choose_pokemon = AsyncMock(return_value=roserade)
        ctx.choose = AsyncMock(return_value=0)
        await spray.effect(ctx)
        self.assertIn(roselia, board.find_player_area(P1, 'bench').children)
        again = self.add(rig, fixtures.definition('SV05.Roserade_9'), P1, 'hand')
        return any(roselia.entity_id in ti.get('validTargets', [])
                   for entry in compute_legal_actions(board, ts, P1, session.game_id)
                   if entry['entityID'] == again.entity_id
                   for ti in entry['targetInfoLst'])

    async def test_lock_without_stadium(self):
        self.assertFalse(await self.sprayed(None))

    async def test_forest_of_vitality_lifts_lock(self):
        self.assertTrue(await self.sprayed('ME1.ForestofVitality_117'))

    async def test_forest_of_giant_plants_lifts_lock(self):
        self.assertTrue(await self.sprayed('XY7.ForestofGiantPlants_74'))

    async def test_plain_devolution_spray_locks_too(self):
        # Oct 9 report: Roselia re-evolved straight after a plain Devolution Spray.
        for path in ('BW6.DevolutionSpray_113', 'XY10.DevolutionSpray_95'):
            with self.subTest(path=path):
                self.assertFalse(await self.sprayed(None, path))
                self.assertTrue(await self.sprayed('ME1.ForestofVitality_117', path))


class ZoomingDrawTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def test_counter_is_placed_before_the_draw(self):
        rig, e = self.rig('SV035.Dodrio_85')
        dodrio = e['target']
        ability = fixtures.definition('SV035.Dodrio_85').abilities[0]
        hand = rig.board.find_player_area(P1, 'hand')
        before_hand, before_hp = len(hand.children), dodrio.get_attribute(AttrID.HP)
        ctx = EffectContext(rig.session, P1, dodrio, ability)
        await ability.effect(ctx)
        self.assertEqual(len(hand.children), before_hand + 1)
        self.assertEqual(dodrio.get_attribute(AttrID.HP), before_hp - 10)


class EffectBenchStadiumTests(unittest.IsolatedAsyncioTestCase):
    """Risky Ruins watches every bench placement; Gapejaw Bog only from hand."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def door_with(self, stadium_key):
        rig, e = self.rig('SM8.Giratina_97')
        board = rig.board
        stadium = self.add(rig, fixtures.definition(stadium_key), P1, 'hand')
        board.move_card(stadium.entity_id, board.find_global_area('activeStadium').entity_id)
        definition = fixtures.definition('SM8.Giratina_97')
        giratina = next(c for c in board.find_player_area(P1, 'discard').children
                        if c.archetype_id == definition.guid)
        rig.session.turn_state.active_player_id = P1
        printed = giratina.get_attribute(AttrID.HP)
        ability = definition.abilities[0]
        ctx = EffectContext(rig.session, P1, giratina, ability)
        ctx.ask_yes_no = AsyncMock(return_value=True)
        await ability.effect(ctx)
        self.assertIn(giratina, board.find_player_area(P1, 'bench').children)
        return giratina.get_attribute(AttrID.HP), printed

    async def test_risky_ruins_counts_distortion_door(self):
        hp, printed = await self.door_with('ME1.RiskyRuins_127')
        self.assertEqual(hp, printed - 20)

    async def test_gapejaw_bog_ignores_distortion_door(self):
        hp, printed = await self.door_with('SWSH10.GapejawBog_142')
        self.assertEqual(hp, printed)


class RotomDexFaceDownTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_replacement_prizes_are_hidden_before_moving(self):
        rig, e = self.rig('SM1.RotomDex_131')
        board = rig.board
        prizes = board.find_player_area(P1, 'prizePile')
        count = len(prizes.children)
        self.assertGreater(count, 0)
        dex = fixtures.definition('SM1.RotomDex_131')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        sent = []
        original = ctx._queue
        ctx._queue = lambda msg, **kw: (sent.append(msg), original(msg, **kw))[1]
        await dex.effect(ctx)
        self.assertEqual(len(prizes.children), count)
        for card in prizes.children:
            kinds = [m['name'] for m in sent if isinstance(m, dict)
                     and (m.get('value') or {}).get('entityID') == card.entity_id]
            into_prizes = len(kinds) - 1 - kinds[::-1].index('EntityMoved')
            self.assertEqual(kinds[into_prizes - 1], 'AttributesReset', kinds)
