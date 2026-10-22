"""Bug hunt round 7, chunk 23: Togetic (SSP/UNB), Porygon LOR, Porygon-Z BUS,
Slowbro PBL, Roller Skates, Starmie BKT, Tyrogue UNB, Vitality Band, Charcadet
PAR, Metagross SIT, Tympole RCL, Palpitoad BLK, Seismitoad OBF, Empoleon BRS --
each checked against its printed text, including the cases where it should NOT
work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Triggers, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY, METAL = (PokemonTypes.FIRE, PokemonTypes.WATER,
                           PokemonTypes.PSYCHIC, PokemonTypes.METAL)

TOGETIC_SSP = 'SV08.Togetic_71'
PORYGON = 'SWSH11.Porygon_140'
PORYGON2 = 'SM3.Porygon2_104'
PORYGONZ = 'SM3.PorygonZ_105'
SLOWBRO = 'ME5.Slowbro_30'
TOGEPI = 'SM10.Togepi_136'
TOGETIC_UNB = 'SM10.Togetic_137'
ROLLER = 'XY4.RollerSkates_103'
STARMIE = 'XY8.Starmie_30'
TYROGUE = 'SM10.Tyrogue_100'
VBAND = 'SV1.VitalityBand_197'
CHARCADET = 'SV4.Charcadet_25'
METAGROSS = 'SWSH12.Metagross_119'
TYMPOLE = 'SWSH2.Tympole_44'
PALPITOAD = 'ZSV10PT5.Palpitoad_20'
SEISMITOAD = 'SV3.Seismitoad_52'
EMPOLEON = 'SWSH9.Empoleon_37'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk23(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def table(self, opp=None):
        t = Table(self)
        self.opp = self.neutral(t.put(opp or self.filler, P2, 'active'))
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    async def evolve(self, t, base, spec):
        card = t.put(spec, base.owning_player_id, 'hand')
        await t._run(lambda: t.session.perform_evolution(base.owning_player_id, card, base))
        return card

    def two_turns(self, t):
        t.next_turn()
        t.next_turn()

    # --- Togetic SSP 71: Draining Kiss -----------------------------------
    async def test_togetic_ssp_draining_kiss(self):
        t = self.table()
        tog = self.mine(t, TOGETIC_SSP, WATER, 2)
        tog.set_attribute(AttrID.HP, 40)       # 50 damage
        await t.attack(tog, 'Draining Kiss')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertEqual(t.damage(tog), 20)

    async def test_togetic_ssp_draining_kiss_no_overheal(self):
        t = self.table()
        tog = self.mine(t, TOGETIC_SSP, WATER, 2)
        await t.attack(tog, 'Draining Kiss')
        self.assertEqual(t.damage(tog), 0)
        self.assertEqual(400 - t.hp(self.opp), 30)

    # --- Porygon LOR 140: Branch Calculation ------------------------------
    async def _branch(self, which):
        t = self.table()
        pory = self.mine(t, PORYGON, WATER, 1)
        mine_cards = t.deck(P1, [self.filler, TYMPOLE, TOGEPI, TYROGUE])
        opp_cards = t.deck(P2, [self.filler, TYMPOLE, TOGEPI, TYROGUE])
        seen = []

        async def chooser(pid, source_id, cards, count, minimum=None, **kw):
            seen.append((pid, list(cards)))
            return [c.entity_id for c in reversed(list(cards))]

        async def choose(ctx, prompt, buttons, player_id=None, descriptions=None,
                         use_panel=True):
            return which

        with patch.object(t.session, 'prompt_card_chooser', chooser), \
                patch.object(EffectContext, 'choose', choose):
            await t.attack(pory, 'Branch Calculation')
        return t, seen, mine_cards, opp_cards

    async def test_porygon_branch_calculation_opponent_deck(self):
        t, seen, mine_cards, opp_cards = await self._branch(1)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], P1, 'the attacker looks and orders')
        self.assertEqual(set(seen[0][1]), set(opp_cards))
        # first pick = new top (top of the deck is the last child)
        self.assertEqual(t.zone(P2, 'deck')[-4:], list(reversed(opp_cards)), 'order reversed')
        self.assertEqual(t.zone(P1, 'deck')[-4:], mine_cards, 'own deck untouched')

    async def test_porygon_branch_calculation_own_deck(self):
        t, seen, mine_cards, opp_cards = await self._branch(0)
        self.assertEqual(set(seen[0][1]), set(mine_cards))
        self.assertEqual(t.zone(P2, 'deck')[-4:], opp_cards)

    # --- Porygon-Z BUS 105: Initialize / Zap Cannon -----------------------
    def _initialize_board(self, t):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        return t.put(TOGEPI, P2, 'active'), t.put(TYMPOLE, P2, 'bench')

    async def test_porygonz_initialize_devolves_each_opponent_evolved(self):
        t = self.table()
        togepi, tympole = self._initialize_board(t)
        togetic = await self.evolve(t, togepi, TOGETIC_UNB)
        palpi = await self.evolve(t, tympole, PALPITOAD)
        seis = await self.evolve(t, palpi, SEISMITOAD)
        basic_opp = t.put(TYROGUE, P2, 'bench')
        # my own evolved Pokémon must stay evolved
        my_tog = await self.evolve(t, self.mine(t, TOGEPI, zone='bench'), TOGETIC_UNB)
        p2 = self.mine(t, PORYGON2, zone='active')
        pz = t.put(PORYGONZ, P1, 'hand')
        t.yes = True
        await t.play(pz, targets=[p2.entity_id])
        self.assertIn(pz, t.board.pokemon_in_play(P1))
        hand = t.zone(P2, 'hand')
        self.assertEqual(sorted(name(c) for c in hand), ['Seismitoad', 'Togetic'])
        self.assertEqual(sorted(t.names(t.board.pokemon_in_play(P2))),
                         ['Palpitoad', 'Togepi', 'Tyrogue'])
        self.assertIn(my_tog, t.board.pokemon_in_play(P1))
        self.assertNotIn(togetic, t.board.pokemon_in_play(P2))
        self.assertIn(basic_opp, t.board.pokemon_in_play(P2))

    async def test_porygonz_initialize_may_decline(self):
        t = self.table()
        togepi, _ = self._initialize_board(t)
        togetic = await self.evolve(t, togepi, TOGETIC_UNB)
        p2 = self.mine(t, PORYGON2, zone='active')
        pz = t.put(PORYGONZ, P1, 'hand')
        t.yes = False
        await t.play(pz, targets=[p2.entity_id])
        self.assertIn(pz, t.board.pokemon_in_play(P1))
        self.assertIn(togetic, t.board.pokemon_in_play(P2))
        self.assertEqual(t.zone(P2, 'hand'), [])

    async def test_porygonz_zap_cannon_locks_next_turn(self):
        t = self.table()
        pz = self.mine(t, PORYGONZ, WATER, 3)
        await t.attack(pz, 'Zap Cannon')
        self.assertEqual(400 - t.hp(self.opp), 80)
        self.two_turns(t)
        self.assertIsNone(t.attack_offer(pz, 'Zap Cannon'), 'locked next turn')
        self.two_turns(t)
        self.assertIsNotNone(t.attack_offer(pz, 'Zap Cannon'), 'free again after')

    # --- Slowbro PBL 30: All Out ------------------------------------------
    async def test_slowbro_all_out_empty_hand(self):
        t = self.table()
        sb = self.mine(t, SLOWBRO, PSY, 1)
        self.assertEqual(t.zone(P1, 'hand'), [])
        await t.attack(sb, 'All Out')
        self.assertEqual(400 - t.hp(self.opp), 210)

    async def test_slowbro_all_out_with_card_in_hand(self):
        t = self.table()
        sb = self.mine(t, SLOWBRO, PSY, 1)
        t.put(self.item, P1, 'hand')
        await t.attack(sb, 'All Out')
        self.assertEqual(400 - t.hp(self.opp), 50)

    # --- Togetic UNB 137: Energy Present ----------------------------------
    async def test_togetic_unb_energy_present(self):
        t = self.table()
        tog = self.mine(t, TOGETIC_UNB, WATER, 1)
        bench = self.mine(t, self.filler, zone='bench')
        energy = t.put(t.basic_energy(FIRE), P1, 'hand')
        t.put(self.item, P1, 'hand')
        offered = []

        def picks(cards, count, prompt, display):
            offered.append(list(cards))
            return [c for c in cards if c is energy][:count]
        t.picks = picks
        targets = []

        def pick_pokemon(cands, prompt):
            targets.append(list(cands))
            return bench if bench in cands else cands[0]
        t.pokemon = pick_pokemon
        await t.attack(tog, 'Energy Present')
        self.assertIn(energy, list(bench.children))
        self.assertTrue(all(name(c) != 'Pokégear 3.0' for cs in offered for c in cs),
                        'only Energy cards offered')
        for cands in targets:
            self.assertNotIn(tog, cands, 'Active is not a Benched target')

    async def test_togetic_unb_energy_present_no_bench(self):
        t = self.table()
        tog = self.mine(t, TOGETIC_UNB, WATER, 1)
        energy = t.put(t.basic_energy(FIRE), P1, 'hand')
        await t.attack(tog, 'Energy Present')
        self.assertIn(energy, t.zone(P1, 'hand'))
        self.assertEqual(len(tog.children), 1)

    # --- Roller Skates PHF 103 --------------------------------------------
    async def test_roller_skates_heads_draws_three(self):
        t = self.table()
        self.mine(t, self.filler)
        rs = t.put(ROLLER, P1, 'hand')
        t.heads = True
        self.assertTrue(t.can(rs, 'UseTrainerCard'))
        await t.play(rs)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertIn(rs, t.zone(P1, 'discard'))

    async def test_roller_skates_tails_draws_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        rs = t.put(ROLLER, P1, 'hand')
        t.heads = False
        await t.play(rs)
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertIn(rs, t.zone(P1, 'discard'))

    # --- Starmie BKT 30: Deep Sea Swirl / Balance Bind ---------------------
    async def test_starmie_deep_sea_swirl(self):
        t = self.table()
        st = self.mine(t, STARMIE, WATER, 1)
        old = [t.put(TYMPOLE, P1, 'hand') for _ in range(3)]
        deck0 = len(t.zone(P1, 'deck'))
        await t.attack(st, 'Deep Sea Swirl')
        self.assertEqual(len(t.zone(P1, 'hand')), 7)
        self.assertEqual(len(t.zone(P1, 'deck')), deck0 + 3 - 7)
        self.assertEqual(t.zone(P1, 'discard'), [])
        self.assertTrue(all(c in t.zone(P1, 'hand') + t.zone(P1, 'deck') for c in old))

    async def test_starmie_balance_bind_equal_bench(self):
        t = self.table()
        st = self.mine(t, STARMIE, WATER, 2)
        self.mine(t, self.filler, zone='bench')
        self.neutral(t.put(self.filler, P2, 'bench'))
        await t.attack(st, 'Balance Bind')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertIn(PARALYZED, t.conditions(self.opp))

    # BUG: the "same number of Benched Pokémon" condition is ignored (always Paralyzes)
    async def test_starmie_balance_bind_unequal_bench(self):
        t = self.table()
        st = self.mine(t, STARMIE, WATER, 2)
        self.mine(t, self.filler, zone='bench')
        await t.attack(st, 'Balance Bind')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertNotIn(PARALYZED, t.conditions(self.opp))

    # --- Tyrogue UNB 100: Bratty Kick -------------------------------------
    def _kick_table(self, heads):
        t = self.table()
        ty = self.mine(t, TYROGUE)
        opp_bench = self.neutral(t.put(self.filler, P2, 'bench'))
        mine = self.mine(t, self.filler, zone='bench')
        t.heads = heads
        self.cands = []

        def picks(cards, count, prompt, display):
            self.cands.append(list(cards))
            return [opp_bench]
        t.picks = picks
        t.pokemon = lambda c, p: opp_bench
        return t, ty, opp_bench, mine

    async def test_tyrogue_bratty_kick_heads_places_counters(self):
        t, ty, opp_bench, mine = self._kick_table(True)
        self.assertIsNotNone(t.ability_offer(ty, 'Bratty Kick'))
        await t.use(ty, 'Bratty Kick')
        self.assertEqual(400 - t.hp(opp_bench), 30)
        self.assertEqual(400 - t.hp(self.opp), 0)
        self.assertTrue(all(mine not in c and ty not in c for c in self.cands))

    # BUG: "If you use this Ability, your turn ends" is ignored (turn continues)
    async def test_tyrogue_bratty_kick_ends_turn(self):
        t, ty, opp_bench, mine = self._kick_table(True)
        ended = await t.use(ty, 'Bratty Kick')
        self.assertTrue(ended, 'turn ends')

    # BUG: no coin flip: counters are always placed (tails too)
    async def test_tyrogue_bratty_kick_tails_no_counters(self):
        t, ty, opp_bench, mine = self._kick_table(False)
        await t.use(ty, 'Bratty Kick')
        self.assertEqual(400 - t.hp(opp_bench), 0)
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Vitality Band SVI 197 --------------------------------------------
    async def test_vitality_band_active_only(self):
        for target in ('active', 'bench'):
            t = self.table()
            emp = self.mine(t, EMPOLEON, WATER, 1)
            band = t.put(VBAND, P1, 'hand')
            await t.play(band, targets=[emp.entity_id])
            opp_bench = self.neutral(t.put(self.filler, P2, 'bench'))
            victim = self.opp if target == 'active' else opp_bench
            t.pokemon = lambda c, p: victim
            t.picks = lambda cards, count, prompt, display: [victim]
            await t.attack(emp, 'Water Arrow')
            with self.subTest(target=target):
                self.assertEqual(400 - t.hp(victim), 70 if target == 'active' else 60)

    async def test_vitality_band_no_boost_to_zero_damage(self):
        t = self.table()
        tym = self.mine(t, TYMPOLE, WATER, 1)
        await t.play(t.put(VBAND, P1, 'hand'), targets=[tym.entity_id])
        await t.attack(tym, 'Spiral Attack')
        self.assertEqual(400 - t.hp(self.opp), 0)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    # --- Charcadet PAR 25: Protect ----------------------------------------
    async def _protect(self, heads, attack):
        t = self.table(opp=SEISMITOAD if attack == 'Echoed Voice' else TYMPOLE)
        # 2 Energy: an opposing Active Seismitoad's Quaking Zone adds [C]
        ch = self.mine(t, CHARCADET, WATER, 2, hp=400)
        t.energy(self.opp, WATER, 2)
        t.heads = heads
        await t.attack(ch, 'Protect')
        t.next_turn()
        await t.attack(self.opp, attack, pid=P2)
        return t, ch

    async def test_charcadet_protect_heads_blocks_damage_and_effects(self):
        t, ch = await self._protect(True, 'Echoed Voice')
        self.assertEqual(400 - t.hp(ch), 0)
        t, ch = await self._protect(True, 'Spiral Attack')
        self.assertNotIn(CONFUSED, t.conditions(ch))

    async def test_charcadet_protect_tails_no_protection(self):
        t, ch = await self._protect(False, 'Echoed Voice')
        self.assertEqual(400 - t.hp(ch), 120)
        t, ch = await self._protect(False, 'Spiral Attack')
        self.assertIn(CONFUSED, t.conditions(ch))

    # --- Metagross SIT 119: Emergency Entry / Meteor Mash ------------------
    async def test_metagross_emergency_entry(self):
        t = self.table()
        self.mine(t, self.filler)
        meta_card = t.put(METAGROSS, P1, 'hand')
        t.yes = True
        await t._run(lambda: t.session._fire_triggered_abilities(
            P1, meta_card, Triggers.ON_TURN_DRAWN))
        self.assertIn(meta_card, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_metagross_emergency_entry_full_bench_or_declined(self):
        for case in ('full', 'declined'):
            t = self.table()
            self.mine(t, self.filler)
            if case == 'full':
                for _ in range(5):
                    self.mine(t, self.filler, zone='bench')
            meta_card = t.put(METAGROSS, P1, 'hand')
            t.yes = case != 'declined'
            await t._run(lambda: t.session._fire_triggered_abilities(
                P1, meta_card, Triggers.ON_TURN_DRAWN))
            with self.subTest(case=case):
                self.assertEqual(t.zone(P1, 'hand'), [meta_card])

    async def test_metagross_meteor_mash_next_turn_bonus(self):
        t = self.table()
        mg = self.mine(t, METAGROSS, METAL, 2)
        await t.attack(mg, 'Meteor Mash')
        self.assertEqual(400 - t.hp(self.opp), 100)
        self.opp.set_attribute(AttrID.HP, 400)
        self.two_turns(t)
        await t.attack(mg, 'Meteor Mash')
        self.assertEqual(400 - t.hp(self.opp), 200)

    async def test_metagross_meteor_mash_bonus_does_not_skip_a_turn(self):
        t = self.table()
        mg = self.mine(t, METAGROSS, METAL, 2)
        await t.attack(mg, 'Meteor Mash')
        self.opp.set_attribute(AttrID.HP, 400)
        self.two_turns(t)
        self.two_turns(t)     # skipped a turn without attacking
        await t.attack(mg, 'Meteor Mash')
        self.assertEqual(400 - t.hp(self.opp), 100)

    # --- Tympole RCL 44: Spiral Attack ------------------------------------
    async def test_tympole_spiral_attack_confuses_active_only(self):
        t = self.table()
        tym = self.mine(t, TYMPOLE, WATER, 1)
        bench = self.neutral(t.put(self.filler, P2, 'bench'))
        await t.attack(tym, 'Spiral Attack')
        self.assertIn(CONFUSED, t.conditions(self.opp))
        self.assertNotIn(CONFUSED, t.conditions(bench))
        self.assertNotIn(CONFUSED, t.conditions(tym))

    # --- Palpitoad BLK 20: Round ------------------------------------------
    # BUG: Round counts every Pokémon in play (both sides), not only yours with Round
    async def test_palpitoad_round_counts_round_users(self):
        for extra in (0, 2):
            t = self.table()
            pal = self.mine(t, PALPITOAD, WATER, 2)
            for _ in range(extra):
                self.mine(t, PALPITOAD, zone='bench')
            self.mine(t, TYMPOLE, zone='bench')      # no Round
            await t.attack(pal, 'Round')
            with self.subTest(extra=extra):
                self.assertEqual(400 - t.hp(self.opp), 40 * (1 + extra))

    # BUG: Round counts the opponent's Pokémon too
    async def test_palpitoad_round_ignores_opponents_round(self):
        t = self.table()
        pal = self.mine(t, PALPITOAD, WATER, 2)
        self.neutral(t.put(PALPITOAD, P2, 'bench'))
        await t.attack(pal, 'Round')
        self.assertEqual(400 - t.hp(self.opp), 40)

    # --- Seismitoad OBF 52: Quaking Zone / Echoed Voice --------------------
    async def test_seismitoad_quaking_zone_active(self):
        t = self.table(opp=TYMPOLE)
        self.mine(t, SEISMITOAD)
        t.energy(self.opp, WATER, 1)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, 'Spiral Attack', pid=P2),
                          'costs C more: 1 Energy is not enough')
        t.energy(self.opp, WATER, 1)
        self.assertIsNotNone(t.attack_offer(self.opp, 'Spiral Attack', pid=P2))

    async def test_seismitoad_quaking_zone_not_from_bench_nor_own(self):
        t = self.table(opp=TYMPOLE)
        self.mine(t, self.filler)
        self.mine(t, SEISMITOAD, zone='bench')
        t.energy(self.opp, WATER, 1)
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, 'Spiral Attack', pid=P2),
                             'Benched Seismitoad has no effect')
        # own attacks unaffected while Active
        t2 = self.table()
        seis = self.mine(t2, SEISMITOAD, WATER, 2)
        self.assertIsNotNone(t2.attack_offer(seis, 'Echoed Voice'))

    async def test_seismitoad_echoed_voice_next_turn_bonus(self):
        t = self.table()
        seis = self.mine(t, SEISMITOAD, WATER, 2)
        await t.attack(seis, 'Echoed Voice')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.opp.set_attribute(AttrID.HP, 400)
        self.two_turns(t)
        await t.attack(seis, 'Echoed Voice')
        self.assertEqual(400 - t.hp(self.opp), 220)

    async def test_seismitoad_echoed_voice_bonus_expires(self):
        t = self.table()
        seis = self.mine(t, SEISMITOAD, WATER, 2)
        await t.attack(seis, 'Echoed Voice')
        self.opp.set_attribute(AttrID.HP, 400)
        self.two_turns(t)
        self.two_turns(t)
        await t.attack(seis, 'Echoed Voice')
        self.assertEqual(400 - t.hp(self.opp), 120)

    # --- Empoleon BRS 37: Emergency Surfacing / Water Arrow ----------------
    async def test_empoleon_emergency_surfacing(self):
        t = self.table()
        self.mine(t, self.filler)
        emp = t.put(EMPOLEON, P1, 'discard')
        t.yes = True
        self.assertIsNotNone(t.ability_offer(emp, 'Emergency Surfacing'))
        await t.use(emp, 'Emergency Surfacing')
        self.assertIn(emp, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_empoleon_emergency_surfacing_needs_empty_hand_and_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        emp = t.put(EMPOLEON, P1, 'discard')
        t.put(self.item, P1, 'hand')
        self.assertIsNone(t.ability_offer(emp, 'Emergency Surfacing'), 'hand not empty')
        t2 = self.table()
        self.mine(t2, self.filler)
        emp2 = t2.put(EMPOLEON, P1, 'bench')
        self.assertIsNone(t2.ability_offer(emp2, 'Emergency Surfacing'), 'in play')

    async def test_empoleon_water_arrow_no_wr_on_bench(self):
        t = self.table()
        emp = self.mine(t, EMPOLEON, WATER, 1)
        bench = self.neutral(t.put(self.filler, P2, 'bench'))
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [WATER.value])
        t.pokemon = lambda c, p: bench
        t.picks = lambda cards, count, prompt, display: [bench]
        await t.attack(emp, 'Water Arrow')
        self.assertEqual(400 - t.hp(bench), 60)
        self.assertEqual(400 - t.hp(self.opp), 0)


if __name__ == '__main__':
    unittest.main()
