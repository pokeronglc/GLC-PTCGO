"""Bug hunt round 7, chunk 47: Ho-Oh, Shining Arceus, Ether, Energy Sticker,
Spearow, Fearow, Noivern, Wooper, Quagsire, Magnezone, Shinx, Luxio,
Cyclizar, Aerodactyl, Antique Plume Fossil -- each checked against its
printed text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes, SpecialConditions
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, LIGHT, GRASS = (PokemonTypes.FIRE, PokemonTypes.WATER,
                             PokemonTypes.LIGHTNING, PokemonTypes.GRASS)

HOOH = 'SM8.HoOh_160'
ARCEUS = 'SL.ShiningArceus_57'
ETHER = 'BW8.Ether_121'
STICKER = 'SV035.EnergySticker_159'
SPEAROW, FEAROW = 'SV035.Spearow_21', 'SV035.Fearow_22'
NOIVERN = 'SV09.Noivern_128'
WOOPER, QUAGSIRE = 'SVP.Wooper_155', 'DM.Quagsire_26'
MAGNEZONE = 'BW8.Magnezone_46'
SHINX, LUXIO = 'SM5.Shinx_45', 'SM5.Luxio_47'
CYCLIZAR = 'SV4.Cyclizar_157'
AERODACTYL = 'SV035.Aerodactyl_142'
PLUME = 'RSV10PT5.AntiquePlumeFossil_79'
SUPPORTER = 'SV1.ProfessorsResearchProfessorSada_189'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk47(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None, hp=400):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.big(self.opp, hp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, {'hand': 'hand', 'discard': 'discard'}[zone])
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None, base=400):
        return base - (target or self.opp).get_attribute(AttrID.HP)

    async def evolve(self, t, base, spec):
        card = t.put(spec, base.owning_player_id, 'hand')
        await t._run(lambda: t.session.perform_evolution(base.owning_player_id, card, base))
        return card

    # --- Ho-Oh LOT 160: Rainbow Burn ------------------------------------------
    async def test_hooh_rainbow_burn_counts_types(self):
        t = self.table()
        hooh = self.mine(t, HOOH, FIRE, 2)
        t.energy(hooh, WATER, 1)
        await t.attack(hooh, 'Rainbow Burn')
        self.assertEqual(self.dealt(), 30 + 2 * 30)

    async def test_hooh_rainbow_burn_one_type(self):
        t = self.table()
        hooh = self.mine(t, HOOH, FIRE, 3)
        await t.attack(hooh, 'Rainbow Burn')
        self.assertEqual(self.dealt(), 60)

    # --- Shining Arceus SLG 57 ---------------------------------------------------
    async def test_arceus_ultimate_arrow_hits_every_opponent_pokemon(self):
        t = self.table()
        bench = t.put(self.filler, P2, 'bench')
        self.big(bench)
        arceus = self.mine(t, ARCEUS, WATER, 4)
        mybench = self.mine(t, self.filler, zone='bench')
        await t.attack(arceus, 'Ultimate Arrow')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(self.dealt(bench), 30)
        self.assertEqual(t.damage(mybench), 0)
        self.assertEqual(t.damage(arceus), 0)

    def _arrow_from_p2(self, t):
        old = t.active(P2)
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(old)
        a = self.mine(t, ARCEUS, WATER, 4, pid=P2)
        return a

    async def test_arceus_fabled_defense_active_protects_bench(self):
        t = self.table()
        mine = self.mine(t, ARCEUS, hp=400)
        bench = self.mine(t, self.filler, zone='bench')
        attacker = self._arrow_from_p2(t)
        t.next_turn()
        await t.attack(attacker, 'Ultimate Arrow', pid=P2)
        self.assertEqual(t.damage(bench), 0)
        self.assertEqual(400 - t.hp(mine), 30, 'Active Arceus itself still takes damage')

    async def test_arceus_fabled_defense_on_bench_does_nothing(self):
        t = self.table()
        self.mine(t, self.filler, zone='active')
        arceus = self.mine(t, ARCEUS, zone='bench')
        bench = self.mine(t, self.filler, zone='bench')
        attacker = self._arrow_from_p2(t)
        t.next_turn()
        await t.attack(attacker, 'Ultimate Arrow', pid=P2)
        self.assertEqual(t.damage(bench), 30)
        self.assertEqual(t.damage(arceus), 30)

    # --- Ether PLS 121 -----------------------------------------------------------
    async def test_ether_attaches_revealed_basic_energy(self):
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        energy = t.deck(P1, [t.basic_energy(WATER)])[0]
        deck_top = t.zone(P1, 'deck')[-1]
        self.assertIs(deck_top, energy, 'sanity: deck top is the end of the list')
        ether = t.put(ETHER, P1, 'hand')
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.play(ether)
        self.assertIn(energy, t.attached(bench))

    async def test_ether_non_energy_stays_on_top(self):
        t = self.table()
        active = self.mine(t, self.filler)
        top = t.deck(P1, [self.filler])[0]
        ether = t.put(ETHER, P1, 'hand')
        await t.play(ether)
        self.assertIs(t.zone(P1, 'deck')[-1], top)
        self.assertEqual([c for c in t.attached(active)], [])

    # --- Energy Sticker MEW 159 --------------------------------------------------
    async def test_energy_sticker_heads_attaches_to_bench(self):
        t = self.table()
        active = self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        energy = t.put(t.basic_energy(FIRE), P1, 'discard')
        sticker = t.put(STICKER, P1, 'hand')
        t.heads = True
        t.pokemon = lambda c, p: c[0]
        await t.play(sticker)
        self.assertIn(energy, t.attached(bench))
        self.assertEqual(t.attached(active), [])

    async def test_energy_sticker_tails_does_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        energy = t.put(t.basic_energy(FIRE), P1, 'discard')
        sticker = t.put(STICKER, P1, 'hand')
        t.heads = False
        await t.play(sticker)
        self.assertIn(energy, t.zone(P1, 'discard'))
        self.assertEqual(t.attached(bench), [])

    async def test_energy_sticker_never_targets_active(self):
        # no Benched Pokémon: the Active must not receive the Energy
        t = self.table()
        active = self.mine(t, self.filler)
        energy = t.put(t.basic_energy(FIRE), P1, 'discard')
        sticker = t.put(STICKER, P1, 'hand')
        t.heads = True
        if t.can(sticker, 'UseTrainerCard'):
            await t.play(sticker)
        self.assertNotIn(energy, t.attached(active))
        self.assertIn(energy, t.zone(P1, 'discard'))

    # --- Spearow MEW 21 / Shinx UPR 45: Evolutionary Advantage --------------------
    async def test_evolutionary_advantage_second_players_first_turn(self):
        for basic, stage1 in ((SPEAROW, FEAROW), (SHINX, LUXIO)):
            for turn, legal in ((1, False), (2, True)):
                with self.subTest(basic=basic, turn=turn):
                    t = Table(self)
                    t.state.turn_number = turn
                    b = t.put(basic, P1, 'active')
                    t.state.entered_play_turn[b.entity_id] = turn
                    t.put(self.filler, P2, 'active')
                    card = t.put(stage1, P1, 'hand')
                    self.assertEqual(t.can(card, 'EvolvePokemonPlayAbility'), legal)

    async def test_evolutionary_advantage_not_on_later_turn_when_just_played(self):
        t = Table(self)
        t.state.turn_number = 4
        b = t.put(SPEAROW, P1, 'active')
        t.state.entered_play_turn[b.entity_id] = 4
        t.put(self.filler, P2, 'active')
        card = t.put(FEAROW, P1, 'hand')
        self.assertFalse(t.can(card, 'EvolvePokemonPlayAbility'))

    # --- Fearow MEW 22: Beak Catch -------------------------------------------------
    async def test_fearow_beak_catch_takes_up_to_three(self):
        t = self.table()
        fearow = self.mine(t, FEAROW, WATER, 1)
        self.clear(t, P1, 'hand')
        wanted = t.deck(P1, [WOOPER, SHINX, SPEAROW, CYCLIZAR])
        deck_before = len(t.zone(P1, 'deck'))
        seen = []

        def picks(cards, count, prompt, display):
            seen.append(count)
            return [c for c in cards if c in wanted][:count]
        t.picks = picks
        await t.attack(fearow, 'Beak Catch')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertTrue(all(c in wanted for c in hand))
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before - 3)
        self.assertLessEqual(max(seen), 3)

    async def test_fearow_beak_catch_may_take_zero(self):
        t = self.table()
        fearow = self.mine(t, FEAROW, WATER, 1)
        self.clear(t, P1, 'hand')
        deck_before = len(t.zone(P1, 'deck'))
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(fearow, 'Beak Catch')
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before)

    # --- Noivern JTG 128: Tuning Echo / Frightening Howl -----------------------------
    def _hands(self, t, mine, theirs):
        self.clear(t, P1, 'hand')
        self.clear(t, P2, 'hand')
        for _ in range(mine):
            t.put(self.item, P1, 'hand')
        for _ in range(theirs):
            t.put(self.item, P2, 'hand')

    async def test_noivern_tuning_echo_equal_hands_free_howl(self):
        t = self.table()
        noivern = self.mine(t, NOIVERN)
        self._hands(t, 3, 3)
        self.assertIsNotNone(t.attack_offer(noivern, 'Frightening Howl'))
        await t.attack(noivern, 'Frightening Howl')
        self.assertEqual(self.dealt(), 110)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    async def test_noivern_tuning_echo_unequal_hands_needs_energy(self):
        t = self.table()
        noivern = self.mine(t, NOIVERN)
        self._hands(t, 3, 4)
        self.assertIsNone(t.attack_offer(noivern, 'Frightening Howl'))
        t.energy(noivern, WATER, 3)
        self.assertIsNotNone(t.attack_offer(noivern, 'Frightening Howl'))

    # --- Wooper SVP 155: Scoop Water ---------------------------------------------------
    async def test_wooper_scoop_water_shuffles_three_water(self):
        t = self.table()
        wooper = self.mine(t, WOOPER, WATER, 1)
        waters = [t.put(t.basic_energy(WATER), P1, 'discard') for _ in range(4)]
        fire = t.put(t.basic_energy(FIRE), P1, 'discard')
        deck_before = len(t.zone(P1, 'deck'))
        offered = []

        def picks(cards, count, prompt, display):
            offered.append(list(cards))
            return list(cards)[:count]
        t.picks = picks
        await t.attack(wooper, 'Scoop Water')
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before + 3)
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(sum(1 for w in waters if w in t.zone(P1, 'discard')), 1)
        for cards in offered:
            self.assertNotIn(fire, cards)

    # --- Quagsire DRM 26: Wash Out / Hydro Pump ----------------------------------------
    async def test_quagsire_wash_out_moves_water_repeatedly(self):
        t = self.table()
        active = self.mine(t, self.filler)
        quag = self.mine(t, QUAGSIRE, zone='bench')
        e1, e2 = t.energy(quag, WATER, 2)
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        t.pokemon = lambda c, p: quag if quag in c else c[0]
        await t.use(quag, 'Wash Out')          # Oct 23: any number in one activation
        self.assertEqual({id(c) for c in t.attached(active)}, {id(e1), id(e2)})
        self.assertEqual(t.attached(quag), [])

    async def test_quagsire_wash_out_ignores_non_water_and_active(self):
        t = self.table()
        active = self.mine(t, QUAGSIRE)
        t.energy(active, WATER, 1)
        bench = self.mine(t, self.filler, zone='bench')
        fire = t.energy(bench, FIRE, 1)
        entry = t.ability_offer(active, 'Wash Out')
        if entry is not None:
            await t.do(entry)
        self.assertIn(fire, t.attached(bench))

    async def test_quagsire_hydro_pump_counts_water_only(self):
        t = self.table()
        quag = self.mine(t, QUAGSIRE, WATER, 2)
        t.energy(quag, FIRE, 1)
        await t.attack(quag, 'Hydro Pump')
        self.assertEqual(self.dealt(), 60 + 2 * 20)

    # --- Magnezone PLS 46: Dual Brains / Gyro Ball -------------------------------------
    def _one_supporter_played(self, t):
        t.state.supporter_played = True
        t.state.supporters_played = 1

    async def test_magnezone_dual_brains_allows_second_supporter(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, MAGNEZONE, zone='bench')
        card = t.put(SUPPORTER, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        self._one_supporter_played(t)
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        t.state.supporters_played = 2
        self.assertFalse(t.can(card, 'UseTrainerCard'), 'never a third')

    async def test_magnezone_dual_brains_real_play_twice(self):
        t = self.table()
        self.mine(t, MAGNEZONE)
        s1 = t.put(SUPPORTER, P1, 'hand')
        await t.play(s1)
        s2 = t.put(SUPPORTER, P1, 'hand')
        self.assertTrue(t.can(s2, 'UseTrainerCard'))
        await t.play(s2)
        s3 = t.put(SUPPORTER, P1, 'hand')
        self.assertFalse(t.can(s3, 'UseTrainerCard'))

    async def test_magnezone_dual_brains_opponents_does_not_help_me(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(MAGNEZONE, P2, 'bench')
        card = t.put(SUPPORTER, P1, 'hand')
        self._one_supporter_played(t)
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_magnezone_gyro_ball_switches_both(self):
        t = self.table()
        their_bench = t.put(self.filler, P2, 'bench')
        self.big(their_bench)
        mag = self.mine(t, MAGNEZONE, LIGHT, 3)
        my_bench = self.mine(t, self.filler, zone='bench')
        await t.attack(mag, 'Gyro Ball')
        self.assertEqual(self.dealt(), 80, 'damage hits the original Defending Pokémon')
        self.assertIs(t.active(P1), my_bench)
        self.assertIs(t.active(P2), their_bench)

    # --- Luxio UPR 47: Disconnect ----------------------------------------------------------
    async def test_luxio_disconnect_locks_opponent_items_next_turn(self):
        t = self.table()
        luxio = self.mine(t, LUXIO, WATER, 1)
        item = t.put(ETHER, P2, 'hand')
        t.deck(P2, [t.basic_energy(WATER)])
        await t.attack(luxio, 'Disconnect')
        self.assertEqual(self.dealt(), 30)
        mine = t.put(ETHER, P1, 'hand')
        t.next_turn()
        self.assertFalse(t.can(item, 'UseTrainerCard', pid=P2))
        t.next_turn()
        t.deck(P1, [t.basic_energy(WATER)])
        self.assertTrue(t.can(mine, 'UseTrainerCard'), 'my own Items are not locked')
        t.next_turn()
        self.assertTrue(t.can(item, 'UseTrainerCard', pid=P2), 'lock has expired')

    # --- Cyclizar PAR 157: Driving Buddy ---------------------------------------------------
    async def test_cyclizar_driving_buddy_after_supporter(self):
        t = self.table()
        cyc = self.mine(t, CYCLIZAR, WATER, 3)
        sup = t.put(SUPPORTER, P1, 'hand')
        await t.play(sup)
        await t.attack(cyc, 'Driving Buddy')
        self.assertEqual(self.dealt(), 140)

    async def test_cyclizar_driving_buddy_without_supporter(self):
        t = self.table()
        cyc = self.mine(t, CYCLIZAR, WATER, 3)
        t.put(SUPPORTER, P1, 'hand')
        await t.attack(cyc, 'Driving Buddy')
        self.assertEqual(self.dealt(), 70)

    async def test_cyclizar_opponent_supporter_last_turn_does_not_count(self):
        t = self.table()
        cyc = self.mine(t, CYCLIZAR, WATER, 3)
        t.next_turn()
        sup = t.put(SUPPORTER, P2, 'hand')
        await t.play(sup, pid=P2)
        t.next_turn()
        await t.attack(cyc, 'Driving Buddy')
        self.assertEqual(self.dealt(), 70)

    # --- Aerodactyl MEW 142: Devolution Ray -----------------------------------------------
    async def test_aerodactyl_devolution_ray_devolves_evolved(self):
        t = Table(self)
        wooper = t.put(WOOPER, P2, 'active')
        quag = await self.evolve(t, wooper, QUAGSIRE)
        self.big(quag)
        quag.set_attribute(AttrID.HP, 400)
        aero = self.mine(t, AERODACTYL, WATER, 2)
        await t.attack(aero, 'Devolution Ray')
        self.assertIn('Quagsire', [name(c) for c in t.zone(P2, 'hand')])
        self.assertNotIn('Quagsire', [name(p) for p in t.board.pokemon_in_play(P2)])

    async def test_aerodactyl_devolution_ray_basic_untouched(self):
        t = self.table()
        aero = self.mine(t, AERODACTYL, WATER, 2)
        self.clear(t, P2, 'hand')
        await t.attack(aero, 'Devolution Ray')
        self.assertEqual(self.dealt(), 100)
        self.assertEqual(t.zone(P2, 'hand'), [])
        self.assertIs(t.active(P2), self.opp)

    # --- Antique Plume Fossil WHT 79 ------------------------------------------------------
    async def _fossil(self, t, active):
        t.put(self.filler, P1, 'active')
        card = t.put(PLUME, P1, 'hand')
        await t.play(card)
        fossil = next(p for p in t.board.pokemon_in_play(P1) if name(p) == 'Antique Plume Fossil')
        if active:
            await t._run(lambda: EffectContext(t.session, P1, fossil, None).switch_active(P1, fossil))
        return fossil

    async def test_plume_fossil_bench_prevents_spread(self):
        t = self.table()
        fossil = await self._fossil(t, active=False)
        attacker = self._arrow_from_p2(t)
        t.next_turn()
        await t.attack(attacker, 'Ultimate Arrow', pid=P2)
        self.assertEqual(t.damage(fossil), 0)
        self.assertIn(fossil, t.board.pokemon_in_play(P1))

    async def test_plume_fossil_active_not_protected(self):
        t = self.table()
        fossil = await self._fossil(t, active=True)
        attacker = self._arrow_from_p2(t)
        t.next_turn()
        await t.attack(attacker, 'Ultimate Arrow', pid=P2)
        self.assertEqual(t.damage(fossil), 30)

    async def test_plume_fossil_cannot_be_affected_by_conditions(self):
        t = self.table()
        fossil = await self._fossil(t, active=True)
        ctx = EffectContext(t.session, P2, self.opp, None)
        await t._run(lambda: ctx.apply_special_condition(fossil, SpecialConditions.POISONED))
        self.assertEqual(t.conditions(fossil), set())


if __name__ == '__main__':
    unittest.main()
