"""Player reports, 8 October: attacks, stadiums, trainers and evolution rules."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.models.board import EnergyEntity
from spirit.game.session.effects import EffectContext
from spirit.game.session.legal_actions import (
    _stadium_ability_entries, attack_cost_satisfied, compute_legal_actions,
)
from spirit.game.session.passives import (
    ability_locked, active_passives, effective_attack_cost, effective_max_hp,
)
from spirit.tools.effect_smoke import P1, P2


def _hp(board):
    return {pid: [p.get_attribute(AttrID.HP) for p in board.pokemon_in_play(pid)]
            for pid in (P1, P2)}


class _Base(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def attack(self, path, title, yes=True, setup=None):
        rig, e = self.rig(path)
        if setup:
            setup(rig, e)
        attack = next(a for a in fixtures.definition(path).abilities if a.title == title)
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        ctx.ask_yes_no = AsyncMock(return_value=yes)
        before = _hp(rig.board)
        await attack.effect(ctx)
        return rig, e, ctx, before, _hp(rig.board)

    def stadium(self, rig, path, owner=P2):
        card = self.add(rig, fixtures.definition(path), owner, 'hand')
        rig.board.move_card(card.entity_id,
                            rig.board.find_global_area('activeStadium').entity_id)
        return card


class AttackReports(_Base):
    async def test_top_burner_mills_one_per_fire_energy(self):
        rig, e, ctx, *_ = await self.attack('SM9.Moltres_19', 'Top Burner')
        deck = rig.board.find_player_area(P2, 'deck')
        # The rig attaches 6 Fire Energy; all are discarded and 6 cards milled.
        self.assertEqual(ctx.attached_energies(e['target']), [])
        self.assertEqual(len(deck.children), 27 - 6)

    async def test_super_sandstorm_skips_undamaged_bench(self):
        *_, before, after = await self.attack('SV10.Hippowdon_106', 'Super Sandstorm')
        self.assertEqual(after[P1], before[P1])
        self.assertEqual(after[P2][1:], before[P2][1:])

    async def test_super_sandstorm_hits_damaged_bench(self):
        def damage(rig, e):
            bench = rig.board.find_player_area(P2, 'bench').children[0]
            bench.set_attribute(AttrID.HP, bench.get_attribute(AttrID.HP) - 10)
        *_, before, after = await self.attack('SV10.Hippowdon_106', 'Super Sandstorm',
                                              setup=damage)
        self.assertEqual(before[P2][1] - after[P2][1], 40)
        self.assertEqual(after[P2][2], before[P2][2])

    async def test_chrono_burst_and_jungle_whip_are_optional_bonuses(self):
        for path, title in (('ME1.Dialga_95', 'Chrono Burst'), ('SV08.Zarude_11', 'Jungle Whip')):
            for yes, dealt, left in ((True, 160, 0), (False, 80, None)):
                with self.subTest(path=path, yes=yes):
                    rig, e, ctx, before, after = await self.attack(path, title, yes=yes)
                    self.assertEqual(before[P2][0] - after[P2][0], dealt)
                    energies = ctx.attached_energies(e['target'])
                    if left is not None:
                        self.assertEqual(len(energies), left)
                    else:
                        self.assertTrue(energies)

    async def test_vanguard_punch_recoil_scales_with_counters(self):
        def full(rig, e):
            e['target'].set_attribute(AttrID.HP, effective_max_hp(rig.board, e['target']))
        *_, before, after = await self.attack('SV05.Palafin_49', 'Vanguard Punch', setup=full)
        self.assertEqual(after[P1][0], before[P1][0])

        def hurt(rig, e):
            e['target'].set_attribute(AttrID.HP, effective_max_hp(rig.board, e['target']) - 20)
        *_, before, after = await self.attack('SV05.Palafin_49', 'Vanguard Punch', setup=hurt)
        self.assertEqual(before[P1][0] - after[P1][0], 20)

    async def test_time_manipulation_puts_cards_on_top(self):
        rig, e = self.rig('SV08.Dialga_135')
        attack = fixtures.definition('SV08.Dialga_135').abilities[0]
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        picked = {}

        async def search(pred, count, minimum=0, **kw):
            picked['cards'] = ctx.deck()[:count]
            return picked['cards']
        ctx.search_deck = search
        ctx.reorder_deck_top = AsyncMock(side_effect=lambda n, **kw: ctx.deck_top(n))
        hand = len(ctx.hand())
        await attack.effect(ctx)
        self.assertEqual(len(ctx.hand()), hand)
        self.assertEqual(set(ctx.deck_top(2)), set(picked['cards']))

    async def test_soprano_wave_hits_the_bench(self):
        *_, before, after = await self.attack('Promo_XY.Meloetta_120', 'Soprano Wave')
        hit = before[P2][0] - after[P2][0]
        self.assertEqual([b - a for b, a in zip(before[P2], after[P2])], [hit] * 3)

    async def test_destructive_drake_scales_with_discarded_energy(self):
        rig, e = self.rig('SM9.Moltres_19')
        attack = fixtures.definition('SM12.DragoniumZDragonClaw_190').granted_abilities[0]
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        count = len(ctx.attached_energies(e['target']))
        seen = {}
        original = ctx.deal_damage

        async def record(amount=None, *a, **kw):
            seen.setdefault('amount', amount)
            return await original(amount, *a, **kw)
        ctx.deal_damage = record
        await attack.effect(ctx)
        self.assertEqual(seen['amount'], 80 * count)

    async def test_raging_tentacles_costs_one_fighting_when_damaged(self):
        rig, e = self.rig('SV08.Grapploct_113')
        board, grapploct = rig.board, e['target']
        for card in list(grapploct.children):
            if isinstance(card, EnergyEntity):
                rig.to_area(card, P1, 'discard')
        rig.attach_energy_type(P1, grapploct, PokemonTypes.FIGHTING.value)
        attack = next(a for a in fixtures.definition('SV08.Grapploct_113').abilities
                      if a.title == 'Raging Tentacles')
        cost = {'Fighting': 2, 'Colorless': 1}
        energies = board.attached_energies(grapploct)
        grapploct.set_attribute(AttrID.HP, effective_max_hp(board, grapploct))
        self.assertFalse(attack_cost_satisfied(
            effective_attack_cost(board, grapploct, cost, attack=attack), energies, board))
        grapploct.set_attribute(AttrID.HP, effective_max_hp(board, grapploct) - 10)
        self.assertTrue(attack_cost_satisfied(
            effective_attack_cost(board, grapploct, cost, attack=attack), energies, board))

    async def test_dark_claw_only_boosts_the_active(self):
        def claw(rig, e):
            card = self.add(rig, fixtures.definition('BW5.DarkClaw_92'), P1, 'hand')
            rig.board.attach_card(card.entity_id, e['target'].entity_id)
        *_, before, after = await self.attack('SV10.TeamRocketsArbok_113', 'Spinning Tail',
                                              setup=claw)
        self.assertEqual([b - a for b, a in zip(before[P2], after[P2])], [50, 30, 30])


class FieldReports(_Base):
    async def test_mountain_ring_protects_both_benches(self):
        def ring(rig, e):
            self.stadium(rig, 'XY3.MountainRing_97')
        *_, before, after = await self.attack('ME3.Diggersby_65', 'Earthquake', setup=ring)
        self.assertEqual(after[P1][1:], before[P1][1:])

    async def test_daunting_pose_stops_counters_on_bench(self):
        def machoke(rig, e):
            self.add(rig, fixtures.definition('SM2.Machoke_64'), P2, 'bench')
        *_, before, after = await self.attack('SV08.Uxie_78', 'Painful Memories', setup=machoke)
        self.assertEqual(before[P2][0] - after[P2][0], 20)
        self.assertEqual(after[P2][1:], before[P2][1:])

    async def test_rough_seas_offered_for_damaged_lightning_pokemon(self):
        rig, e = self.rig('SV4.Zekrom_66')
        self.stadium(rig, 'XY5.RoughSeas_137')
        e['target'].set_attribute(AttrID.HP, 30)
        self.assertEqual(len(_stadium_ability_entries(
            rig.board, rig.session.turn_state, P1, 'g')), 1)

    async def test_scorched_earth_discards_and_draws_two(self):
        rig, e = self.rig('SM9.Moltres_19')
        stadium = self.stadium(rig, 'XY5.ScorchedEarth_138')
        ability = fixtures.definition('XY5.ScorchedEarth_138').ability
        ctx = EffectContext(rig.session, P1, stadium, ability)
        ctx.choose_cards = AsyncMock(side_effect=lambda cards, n, **kw: list(cards)[:n])
        hand = len(ctx.hand())
        await ability.effect(ctx)
        self.assertEqual(len(ctx.hand()), hand + 1)

    async def test_daunting_gaze_only_from_the_active_spot(self):
        rig, e = self.rig('SV09.Tyranitar_95')
        board = rig.board
        item = self.add(rig, self.item, P2, 'hand')
        blocked = lambda: any(p.blocks_trainer_play(item, P2, c) for p, c in active_passives(board))
        self.assertTrue(blocked())
        board.move_card(e['target'].entity_id, board.find_player_area(P1, 'discard').entity_id)
        self.assertFalse(blocked())

    async def test_lazy_turns_off_opposing_abilities(self):
        rig, e = self.rig('SM7.Slaking_115')
        board = rig.board
        munkidori = self.add(rig, fixtures.definition('SV06.Munkidori_95'), P2, 'bench')
        ability = fixtures.definition('SV06.Munkidori_95').abilities[0]
        self.assertTrue(ability_locked(board, munkidori, ability))
        board.move_card(e['target'].entity_id, board.find_player_area(P1, 'discard').entity_id)
        self.assertFalse(ability_locked(board, munkidori, ability))


class TrainerReports(_Base):
    async def test_kogas_trap_confuses_and_poisons(self):
        rig, e = self.rig('SM10.KogasTrap_177', 'trainer')
        await fixtures.definition('SM10.KogasTrap_177').effect(
            EffectContext(rig.session, P1, e['target'], None))
        self.assertEqual(sorted(rig.board.active_pokemon(P2).get_attribute(
            AttrID.SPECIAL_CONDITIONS)), ['Confused', 'Poisoned'])

    async def test_roller_skater_draws_four_after_an_energy(self):
        for energy, delta in ((True, 3), (False, 1)):
            with self.subTest(energy=energy):
                rig, e = self.rig('SM12.RollerSkater_203', 'trainer')
                ctx = EffectContext(rig.session, P1, e['target'], None)

                async def pick(cards, n, minimum=0, **kw):
                    pool = [c for c in cards if isinstance(c, EnergyEntity) == energy
                            and c is not e['target']]
                    return pool[:n]
                ctx.choose_cards = pick
                hand = len(ctx.hand())
                await fixtures.definition('SM12.RollerSkater_203').effect(ctx)
                self.assertEqual(len(ctx.hand()) - hand, delta)

    async def test_fossil_researcher_benches_restored_pokemon(self):
        rig, e = self.rig('XY3.FossilResearcher_92', 'trainer')
        self.add(rig, fixtures.definition('XY3.Tyrunt_61'), P1, 'deck')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        ctx.search_deck = AsyncMock(side_effect=lambda pred=None, count=1, **kw: [
            c for c in ctx.deck() if pred is None or pred(c)][:count])
        bench = rig.board.find_player_area(P1, 'bench')
        before = len(bench.children)
        await fixtures.definition('XY3.FossilResearcher_92').effect(ctx)
        self.assertEqual(len(bench.children), before + 1)

    async def test_sparkling_ripples_offers_any_card(self):
        rig, e = self.rig('XY5.Milotic_44')
        self.add(rig, self.item, P1, 'discard')
        ability = fixtures.definition('XY5.Milotic_44').abilities[0]
        ctx = EffectContext(rig.session, P1, e['target'], ability)
        ctx.ask_yes_no = AsyncMock(return_value=True)
        offered = {}

        async def pick(cards, n, **kw):
            offered['kinds'] = {type(c).__name__ for c in cards}
            return list(cards)[:n]
        ctx.choose_cards = pick
        await ability.effect(ctx)
        self.assertIn('TrainerEntity', offered['kinds'])
        self.assertIn('EnergyEntity', offered['kinds'])


class EvolutionReports(_Base):
    async def test_buff_padding_does_not_heal_on_evolution(self):
        for damage in (60, 0):
            with self.subTest(damage=damage):
                rig, e = self.rig('SV4.Onix_90')
                board, session, turn = rig.board, rig.session, rig.session.turn_state
                onix = board.find_player_area(P1, 'bench').children[0]
                pad = self.add(rig, fixtures.definition('SM9.BuffPadding_136'), P1, 'hand')
                board.attach_card(pad.entity_id, onix.entity_id)
                onix.set_attribute(AttrID.HP, effective_max_hp(board, onix) - damage)
                turn.begin_turn(P2)
                turn.begin_turn(P1)
                steelix = self.add(rig, fixtures.definition('SV4.Steelix_125'), P1, 'hand')
                await session.perform_evolution(P1, steelix, onix)
                await session.resync_effective_max_hp()
                self.assertEqual(effective_max_hp(board, steelix)
                                 - steelix.get_attribute(AttrID.HP), damage)

    async def test_adaptive_evolution_chains_in_one_turn(self):
        rig, e = self.rig('SM9.Moltres_19')
        board, session, turn = rig.board, rig.session, rig.session.turn_state
        turn.begin_turn(P2)
        turn.begin_turn(P1)
        scatterbug = self.add(rig, fixtures.definition('SV1.Scatterbug_8'), P1, 'bench')
        turn.mark_entered_play(scatterbug.entity_id)
        spewpa = self.add(rig, fixtures.definition('SV1.Spewpa_9'), P1, 'hand')
        offered = lambda card: any(a['entityID'] == card.entity_id
                                   for a in compute_legal_actions(board, turn, P1, session.game_id))
        self.assertTrue(offered(spewpa))
        await session.perform_evolution(P1, spewpa, scatterbug)
        vivillon = self.add(rig, fixtures.definition('SV1.Vivillon_10'), P1, 'hand')
        self.assertTrue(offered(vivillon))

    async def _trumbeak_board(self, with_pikipek=True):
        rig, e = self.rig('SM9.Moltres_19')
        board, session, turn = rig.board, rig.session, rig.session.turn_state
        pikipek = self.add(rig, fixtures.definition('SM1.Pikipek_106'), P1, 'bench') \
            if with_pikipek else None
        turn.begin_turn(P2)
        turn.begin_turn(P1)
        trumbeak = self.add(rig, fixtures.definition('SM8.Trumbeak_165'), P1, 'hand')
        offers = [a for a in compute_legal_actions(board, turn, P1, session.game_id)
                  if a['entityID'] == trumbeak.entity_id]
        return rig, trumbeak, pikipek, offers

    @staticmethod
    def _panel_titles(offers):
        from spirit.game.data_utils import ABILITIES_BY_ID
        return sorted(ABILITIES_BY_ID[a['selectableAction']['actionID']].title
                      for a in offers
                      if a['selectableAction']['selectionType'] == 'AbilitySelection')

    async def test_trumbeak_panel_has_mountain_pass_and_evolve(self):
        # Oct 9: offering both a drag-evolve and a hand Ability blocks the
        # client's drag, and asking on the drag froze it.  The click panel
        # carries both instead (fossil-style "Evolve" button).
        rig, trumbeak, pikipek, offers = await self._trumbeak_board()
        self.assertEqual(self._panel_titles(offers), ['Evolve', 'Mountain Pass'])
        self.assertNotIn('OutOfPlay', [a['selectableAction']['selectionType'] for a in offers])
        evolve = next(a for a in offers
                      if a['selectableAction']['selectionType'] == 'AbilitySelection'
                      and 'Mountain' not in str(a) and a['selectableAction']['description'] == 'UsePokemonAbility'
                      and self._panel_titles([a]) == ['Evolve'])
        with patch.object(rig.session, 'send_game_sequence', AsyncMock()), \
             patch.object(rig.session, 'broadcast_packet', AsyncMock()):
            await rig.session._apply_player_action(P1, evolve, [])
        self.assertIs(pikipek.parent, trumbeak)
        self.assertIn(trumbeak, rig.board.find_player_area(P1, 'bench').children)

    async def test_trumbeak_mountain_pass_still_offered_with_pikipek(self):
        rig, trumbeak, pikipek, offers = await self._trumbeak_board()
        self.assertIn('Mountain Pass', self._panel_titles(offers))

    async def test_trumbeak_no_evolve_button_without_target(self):
        rig, trumbeak, _, offers = await self._trumbeak_board(with_pikipek=False)
        self.assertEqual(self._panel_titles(offers), ['Mountain Pass'])


if __name__ == "__main__":
    unittest.main()


class FoilMaskFallbackTests(unittest.TestCase):
    """Amazing Rares and gold Secret Rares rendered see-through without masks."""

    @classmethod
    def setUpClass(cls):
        fixtures.HgssRulesTests.setUpClass.__func__(cls)

    def _attrs(self, path):
        import os
        import tempfile
        from spirit.game.foil_masks import strip_unrenderable_foil
        from spirit.game.scripts.cards import loader
        definition = fixtures.definition(path)
        attrs = definition.to_archetype_dict()['attributes']
        script = loader.script_by_guid[definition.guid.lower()]
        with tempfile.TemporaryDirectory() as empty:
            stripped = strip_unrenderable_foil(dict(attrs), script, loader.scripts_dir, empty)
            set_dir = os.path.join(empty, path.split('.')[0])
            os.makedirs(set_dir)
            stem = path.split('.')[1]
            for suffix in ('_foil', '_foil_secondary'):
                open(os.path.join(set_dir, stem + suffix + '.png'), 'wb').close()
            kept = not strip_unrenderable_foil(dict(attrs), script, loader.scripts_dir, empty)
        return stripped, kept

    def test_amazing_rare_without_masks_is_sent_plain(self):
        stripped, kept_with_masks = self._attrs('SWSH4.Rayquaza_138')
        self.assertTrue(stripped)
        self.assertTrue(kept_with_masks)

    def test_plain_holo_keeps_its_foil(self):
        stripped, _ = self._attrs('SWSH4.Dialga_121')
        self.assertFalse(stripped)
