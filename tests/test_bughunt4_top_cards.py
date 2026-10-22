"""Bug hunt 4d (Oct 15): the most-used live-deck cards no test had named,
checked against their printed text (usage from the live DECK log)."""
import unittest

from tests.test_untested_trainers import Base
from tests.untested_trainer_kit import neutral, plain, C, G, R, W, L, P, F, D, M
from tests.untested_card_index import card as card_index
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID
from spirit.game.session.passives import effective_max_hp, effective_retreat_cost
from spirit.tools.effect_smoke import P1, P2


def damage(t, p, n):
    p.set_attribute(AttrID.HP, effective_max_hp(t.board, p) - n)


class TopTrainers(Base):
    def table(self):
        t = Table(self)
        t.put(self.filler, P2, 'active')
        t.set_prizes(P1, 6)
        t.set_prizes(P2, 6)
        return t

    async def test_wondrous_patch_basic_psychic_to_benched_psychic(self):
        t = self.table()
        t.put(plain(P), P1, 'active')
        good = t.put(plain(P), P1, 'bench')
        other = t.put(plain(F), P1, 'bench')
        e_p = t.put(t.basic_energy(P), P1, 'discard')
        e_f = t.put(t.basic_energy(F), P1, 'discard')
        card = t.put('ME2.WondrousPatch_94', P1, 'hand')
        cards, mons = [], []
        t.picks = lambda cs, n, pr, sh: (cards.append(list(cs)) or list(cs)[:n])
        t.pokemon = lambda cs, pr: (mons.append(list(cs)) or cs[0])
        await t.play(card)
        self.assertNotIn(e_f, [c for s in cards for c in s])
        self.assertNotIn(other, [c for s in mons for c in s])
        self.assertNotIn(t.active(P1), [c for s in mons for c in s])
        self.assertIn(e_p, t.attached(good))

    async def test_heavy_ball_retreat_cost_three_or_more(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        card = t.put('BW4.HeavyBall_88', P1, 'hand')
        snorlax = t.put(card_index('Snorlax'), P1, 'deck')
        light = t.put(plain(C), P1, 'deck')
        self.assertGreaterEqual(effective_retreat_cost(t.board, snorlax), 3)
        seen = []
        t.picks = lambda cs, n, pr, sh: (seen.append(list(cs)) or list(cs)[:n])
        await t.play(card)
        flat = [c for s in seen for c in s]
        self.assertIn(snorlax, flat)
        if effective_retreat_cost(t.board, light) < 3:
            self.assertNotIn(light, flat)
        self.assertIn(snorlax, t.zone(P1, 'hand'))

    async def test_acro_bike_one_to_hand_one_discarded(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        card = t.put('XY5.AcroBike_122', P1, 'hand')
        deck = t.deck(P1, [self.filler, self.filler, card_index('Switch')])
        top2 = list(t.zone(P1, 'deck'))[-2:]
        t.picks = lambda cs, n, pr, sh: list(cs)[:1]
        await t.play(card)
        hand, disc = t.zone(P1, 'hand'), t.zone(P1, 'discard')
        moved = [c for c in deck if c in hand or c in disc]
        self.assertEqual(len(moved), 2)
        self.assertEqual(sum(c in hand for c in deck), 1)
        self.assertEqual(sum(c in disc for c in deck), 1)

    async def test_pal_pad_two_supporters_back_into_deck(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        card = t.put('SWSH1.PalPad_172', P1, 'hand')
        sups = [t.put(card_index(n), P1, 'discard') for n in ('Iono', 'Guzma', 'Arven')]
        item = t.put(card_index('Switch'), P1, 'discard')
        seen = []
        t.picks = lambda cs, n, pr, sh: (seen.append(list(cs)) or list(cs)[:n])
        await t.play(card)
        self.assertNotIn(item, [c for s in seen for c in s])
        self.assertEqual(sum(c in t.zone(P1, 'deck') for c in sups), 2)

    async def test_max_potion_heals_all_and_discards_energy(self):
        t = self.table()
        a = t.put(plain(C), P1, 'active')
        t.energy(a, D, 2)
        damage(t, a, 50)
        card = t.put('BW9.MaxPotion_121', P1, 'hand')
        t.pokemon = lambda cs, pr: a
        await t.play(card)
        self.assertEqual(t.damage(a), 0)
        self.assertEqual([c for c in t.attached(a)], [])

    async def test_professor_turos_scenario_returns_pokemon_discards_attachments(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        b = t.put(plain(C), P1, 'bench')
        e = t.energy(b, D, 1)
        card = t.put('SV085.ProfessorTurosScenario_121', P1, 'hand')
        t.pokemon = lambda cs, pr: b
        await t.play(card)
        self.assertIn(b, t.zone(P1, 'hand'))
        self.assertIn(e, t.zone(P1, 'discard'))


class TopPokemon(Base):
    async def strike(self, ref, title, *, kind, energy=3, setup=None, def_hp=600):
        t = Table(self)
        a = neutral(t.put(ref, P1, 'active'))
        t.energy(a, kind, energy)
        d = neutral(t.put(self.filler, P2, 'active'), hp=def_hp)
        t.put(self.filler, P2, 'bench')
        t.set_prizes(P1, 6)
        t.set_prizes(P2, 6)
        t.deck(P1, [self.filler] * 10)
        if setup:
            setup(t, a, d)
        before = t.hp(d)
        t.picks = lambda cs, n, pr, sh: list(cs)[:n]
        t.pokemon = lambda cs, pr: cs[0]
        await t.attack(a, title)
        return t, a, d, before - t.hp(d)

    async def test_hoopa_assault_gate_needs_to_have_moved_up(self):
        *_, dmg = await self.strike('CZ.Hoopa_83', 'Assault Gate', kind=D)
        self.assertEqual(dmg, 0, 'did not move from the Bench this turn')

        def moved(t, a, d):
            t.state.became_active_turn[a.entity_id] = t.state.turn_number
        *_, dmg = await self.strike('CZ.Hoopa_83', 'Assault Gate', kind=D, setup=moved)
        self.assertEqual(dmg, 90)

    async def test_zapdos_thunderous_assault_bonus_after_moving_up(self):
        *_, plain_dmg = await self.strike('Promo_SM.Zapdos_159', 'Thunderous Assault', kind=L)

        def moved(t, a, d):
            t.state.became_active_turn[a.entity_id] = t.state.turn_number
        *_, bonus = await self.strike('Promo_SM.Zapdos_159', 'Thunderous Assault', kind=L, setup=moved)
        self.assertEqual((plain_dmg, bonus), (10, 80))

    async def test_onix_raging_swing_per_damage_counter(self):
        *_, dmg = await self.strike('PGO.Onix_36', 'Raging Swing', kind=F, energy=4,
                                    setup=lambda t, a, d: damage(t, a, 30))
        self.assertEqual(dmg, 150)

    async def test_galarian_obstagoon_scarring_shout_counts_defender(self):
        *_, dmg = await self.strike('ME2PT5.GalarianObstagoon_132', 'Scarring Shout', kind=D,
                                    setup=lambda t, a, d: damage(t, d, 20))
        self.assertEqual(dmg, 140)

    async def test_absol_claw_rend_bonus_on_damaged_active(self):
        *_, undamaged = await self.strike('SWSH10.Absol_97', 'Claw Rend', kind=D)
        *_, damaged = await self.strike('SWSH10.Absol_97', 'Claw Rend', kind=D,
                                        setup=lambda t, a, d: damage(t, d, 10))
        self.assertEqual((undamaged, damaged), (50, 120))

    async def test_amoonguss_dangerous_reaction_with_condition(self):
        *_, none = await self.strike('ZSV10PT5.Amoonguss_11', 'Dangerous Reaction', kind=G)

        def poison(t, a, d):
            d.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        *_, with_cond = await self.strike('ZSV10PT5.Amoonguss_11', 'Dangerous Reaction', kind=G,
                                          setup=poison)
        self.assertEqual(none, 30)
        self.assertGreaterEqual(with_cond, 150)

    async def test_cleffa_grasping_draw_until_seven(self):
        def hand(t, a, d):
            for _ in range(3):
                t.put(self.filler, P1, 'hand')
        t, a, d, _ = await self.strike('SV3.Cleffa_80', 'Grasping Draw', kind=P, setup=hand)
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_absol_swirling_disaster_hits_every_opponent_pokemon(self):
        t, a, d, dmg = await self.strike('SWSH10.Absol_97', 'Swirling Disaster', kind=D)
        self.assertEqual(dmg, 10)
        for b in t.zone(P2, 'bench'):
            self.assertEqual(t.damage(b), 10)


class TopAbilities(Base):
    async def test_dusclops_cursed_blast_five_counters_and_self_ko(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        dus = t.put('SV065.Dusclops_19', P1, 'bench')
        d = neutral(t.put(self.filler, P2, 'active'), hp=300)
        t.set_prizes(P1, 6)
        t.set_prizes(P2, 6)
        t.pokemon = lambda cs, pr: d
        await t.use(dus, 'Cursed Blast')
        self.assertEqual(t.damage(d), 50)
        self.assertIn(dus, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5, 'opponent takes a Prize')

    async def test_kricketune_swelling_tune_grass_only_not_kricketune_no_stacking(self):
        t = Table(self)
        k1 = t.put('SWSH10.Kricketune_10', P1, 'active')
        k2 = t.put('SWSH10.Kricketune_10', P1, 'bench')
        grass = t.put(plain(G), P1, 'bench')
        fire = t.put(plain(R), P1, 'bench')
        t.put(self.filler, P2, 'active')
        printed = lambda p: p.attribute_originals.get(AttrID.HP.value)
        self.assertEqual(effective_max_hp(t.board, grass), printed(grass) + 40)
        self.assertEqual(effective_max_hp(t.board, fire), printed(fire))
        self.assertEqual(effective_max_hp(t.board, k2), printed(k2))

    async def test_giratina_distortion_door_from_discard(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        g = t.put('Promo_SM.Giratina_151', P1, 'discard')
        t.put(self.filler, P2, 'active')
        b1 = neutral(t.put(self.filler, P2, 'bench'), hp=200)
        b2 = neutral(t.put(self.filler, P2, 'bench'), hp=200)
        b3 = neutral(t.put(self.filler, P2, 'bench'), hp=200)
        picks = [b1, b2]
        t.pokemon = lambda cs, pr: picks.pop(0) if picks and picks[0] in cs else cs[0]
        t.picks = lambda cs, n, pr, sh: [c for c in cs if c in (b1, b2)][:n] or list(cs)[:n]
        await t.use(g, 'Distortion Door')
        self.assertIn(g, t.zone(P1, 'bench'))
        self.assertEqual(sorted([t.damage(b1), t.damage(b2), t.damage(b3)]), [0, 10, 10])


if __name__ == '__main__':
    unittest.main()


class TopCardsBatch2(Base):
    """Next tier of live-deck cards no test had named."""

    def table(self, ref=None, zone='active'):
        t = Table(self)
        t.set_prizes(P1, 6)
        t.set_prizes(P2, 6)
        t.deck(P1, [self.filler] * 6)
        t.deck(P2, [self.filler] * 6)
        return t

    async def test_toxicroak_more_poison_two_extra_counters(self):
        t = self.table()
        t.put('SWSH1.Toxicroak_124', P1, 'active')
        d = neutral(t.put(self.filler, P2, 'active'), hp=300)
        d.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        await t.checkup()
        self.assertEqual(t.damage(d), 30)

    async def test_tangela_toxic_two_counters(self):
        t = self.table()
        a = neutral(t.put('SM12.Tangela_5', P1, 'active'))
        t.energy(a, G, 1)
        d = neutral(t.put(self.filler, P2, 'active'), hp=300)
        await t.attack(a, 'Toxic')
        self.assertIn('Poisoned', t.conditions(d))
        await t.checkup()
        self.assertEqual(t.damage(d), 20)

    async def test_hisuian_overqwil_tormenting_poison_five_counters(self):
        t = self.table()
        a = neutral(t.put('SWSH10.HisuianOverqwil_90', P1, 'active'))
        t.energy(a, D, 2)
        d = neutral(t.put(self.filler, P2, 'active'), hp=300)
        await t.attack(a, 'Tormenting Poison')
        await t.checkup()
        self.assertEqual(t.damage(d), 50)

    async def test_metagross_levitation_field_no_retreat_cost(self):
        t = self.table()
        heavy = t.put(card_index('Snorlax'), P1, 'active')
        t.put('SWSH4.Metagross_118', P1, 'bench')
        t.put(self.filler, P2, 'active')
        self.assertEqual(effective_retreat_cost(t.board, heavy), 0)

    async def test_omastar_primordial_tentacles_opponent_cannot_retreat(self):
        from spirit.game.session.passives import active_passives
        t = self.table()
        t.put('SV035.Omastar_139', P1, 'active')
        d = t.put(self.filler, P2, 'active')
        t.put(self.filler, P2, 'bench')
        blocked = any(getattr(p, 'blocks_retreat', lambda *a: False)(d, c)
                      for p, c in active_passives(t.board))
        self.assertTrue(blocked)

    async def test_omastar_fossil_bind_items_locked_when_fewer_in_play(self):
        t = self.table()
        t.put('SM9.Omastar_76', P1, 'active')
        t.put(self.filler, P2, 'active')
        t.put(self.filler, P2, 'bench')
        item = t.put(card_index('Switch'), P2, 'hand')
        t.state.active_player_id = P2
        self.assertFalse(t.can(item, 'UseTrainerCard', P2), 'opponent has more Pokémon: Items locked')
        t.put(self.filler, P1, 'bench')
        t.put(self.filler, P1, 'bench')
        self.assertTrue(t.can(item, 'UseTrainerCard', P2))

    async def test_kyogre_high_water_two_water_from_discard(self):
        t = self.table()
        a = neutral(t.put('SM12.Kyogre_53', P1, 'active'))
        t.energy(a, W, 1)
        b = t.put(plain(C), P1, 'bench')
        w = [t.put(t.basic_energy(W), P1, 'discard') for _ in range(3)]
        f = t.put(t.basic_energy(F), P1, 'discard')
        t.put(self.filler, P2, 'active')
        seen = []
        t.picks = lambda cs, n, pr, sh: (seen.append(list(cs)) or list(cs)[:n])
        t.pokemon = lambda cs, pr: b
        await t.attack(a, 'High Water')
        self.assertNotIn(f, [c for s in seen for c in s])
        self.assertEqual(sum(e in t.attached(b) for e in w), 2)

    async def test_zeraora_discharge_per_lightning_discarded(self):
        t = self.table()
        a = neutral(t.put('SM10.Zeraora_60', P1, 'active'))
        t.energy(a, L, 3)
        d = neutral(t.put(self.filler, P2, 'active'), hp=600)
        t.yes = True
        await t.attack(a, 'Discharge')
        self.assertEqual(t.damage(d), 150)
        self.assertEqual(t.attached(a), [])

    async def test_marnies_morpeko_spiky_wheel_per_darkness(self):
        t = self.table()
        a = neutral(t.put('SV10.MarniesMorpeko_137', P1, 'active'))
        t.energy(a, D, 2)
        t.energy(a, L, 1)
        d = neutral(t.put(self.filler, P2, 'active'), hp=600)
        await t.attack(a, 'Spiky Wheel')
        self.assertEqual(t.damage(d), 20 + 2 * 40)

    async def test_heatmor_charring_breath_needs_burned(self):
        for burned in (False, True):
            t = self.table()
            a = neutral(t.put('DM.Heatmor_10', P1, 'active'))
            t.energy(a, R, 2)
            d = neutral(t.put(self.filler, P2, 'active'), hp=600)
            if burned:
                d.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Burned'])
            await t.attack(a, 'Charring Breath')
            self.assertEqual(t.damage(d), 120 if burned else 0)

    async def test_magearna_change_clothes_tool_to_hand(self):
        t = self.table()
        mag = t.put('SM5.Magearna_91', P1, 'bench')
        a = t.put(plain(C), P1, 'active')
        tool = t.attach(card_index('Float Stone'), a)
        t.put(self.filler, P2, 'active')
        t.pokemon = lambda cs, pr: a
        t.picks = lambda cs, n, pr, sh: list(cs)[:n]
        await t.use(mag, 'Change Clothes')
        self.assertIn(tool, t.zone(P1, 'hand'))
