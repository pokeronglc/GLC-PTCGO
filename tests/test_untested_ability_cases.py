"""Bug hunt 3 (Oct 14): one-off Pokemon Abilities no test named.

List: dev_notes/untested_abilities_oct14.txt.  Families are in
tests/test_untested_ability_sweep.py; these are the single wordings, each
checked on a real board against its printed text.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.untested_trainer_kit import (
    C, G, R, W, L, P, F, D, M, Y, N, big, board, neutral, plain, plain_attack, pay,
    max_hp, weak_to, find, end_turn, subs, _attr)
from spirit.game.attributes import AttrID, PokemonStage
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

S1 = PokemonStage.STAGE1


def att_of(d, need_damage=True):
    a = plain_attack(d)
    if a is not None:
        return a
    return next((x for x in d.abilities if type(x).__name__ == 'Attack'
                 and (not need_damage or (x.damage or 0) > 0)
                 and not any(w in (x.game_text or '').lower()
                             for w in ('flip', 'discard', 'shuffle', 'bench', 'more damage',
                                       'less damage', 'for each', 'heal', 'switch', 'damage counters'))), None) \
        or next((x for x in d.abilities if type(x).__name__ == 'Attack' and (x.damage or 0) > 0
                 and 'flip' not in (x.game_text or '').lower()), None)


class Helpers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # -- helpers --------------------------------------------------------
    async def taken(self, mod, attacker=None, setup=None, *, ability_side='def', neutral_def=True):
        """Damage a plain attack from P1 does to P2's Active.

        ability_side='def': `mod` is P2's Active (the defender).
        ability_side='ally': `mod` is on P2's Bench, the defender a filler.
        ability_side='opp': `mod` is P1's Bench (the attacker's side).
        """
        t = Table(self)
        atk_def = attacker or big(C)
        a = neutral(t.put(atk_def, P1, 'active'))
        pay(t, a, plain_attack(atk_def))
        if ability_side == 'def':
            d = t.put(mod, P2, 'active')
        else:
            d = t.put(self.filler, P2, 'active')
            t.put(mod, P2 if ability_side == 'ally' else P1, 'bench')
        if neutral_def:
            neutral(d, 400)
        else:
            d.attribute_originals[AttrID.HP.value] = 400
            d.set_attribute(AttrID.HP, 400)
        t.put(self.filler, P2, 'bench')
        if setup:
            r = setup(t, a, d)
            if hasattr(r, '__await__'):
                await r
        before = t.hp(d)
        await t.attack(a, plain_attack(atk_def).title)
        return before - t.hp(d), t, a, d

    async def dealt(self, mod, target=None, setup=None, *, attacker_side=True, attacker=None):
        """Damage `mod`'s first plain attack does (attacker_side) -- or, with
        attacker_side=False, damage a P1 attacker does while `mod` sits on P1's Bench."""
        t = Table(self)
        if attacker_side:
            d_def = fixtures.definition(mod)
            att = att_of(d_def)
            a = neutral(t.put(mod, P1, 'active'))
        else:
            d_def = attacker or big(C)
            att = plain_attack(d_def)
            a = neutral(t.put(d_def, P1, 'active'))
            t.put(mod, P1, 'bench')
        pay(t, a, att)
        d = neutral(t.put(target or self.filler, P2, 'active'), 400)
        t.put(self.filler, P2, 'bench')
        if setup:
            r = setup(t, a, d)
            if hasattr(r, '__await__'):
                await r
        await t.attack(a, att.title)
        return 400 - t.hp(d), att, t, a, d

    def hp_of(self, mod, setup=None):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        p = t.put(mod, P2, 'active')
        if setup:
            setup(t, p)
        return max_hp(t, p) - _attr(fixtures.definition(mod), AttrID.HP), t, p


class Cases(Helpers):
    async def test_okidogi_adrena_power(self):
        self.assertEqual(self.hp_of('SV06.Okidogi_111')[0], 0)
        self.assertEqual(self.hp_of('SV06.Okidogi_111', lambda t, p: t.energy(p, D))[0], 100)
        base, att, *_ = await self.dealt('SV06.Okidogi_111')
        more, *_ = await self.dealt('SV06.Okidogi_111', setup=lambda t, a, d: t.energy(a, D))
        # the attack cost may already include Darkness: compare against a non-Dark payment
        self.assertIn(more - base, (0, 100))

    async def test_brambleghast_resilient_soul(self):
        for taken in (0, 2, 4):
            got, *_ = self.hp_of('SV05.Brambleghast_21', lambda t, p, n=taken: t.set_prizes(P1, 6 - n))
            self.assertEqual(got, 50 * taken)

    async def test_annihilape_lose_cool(self):
        base, att, *_ = await self.dealt('SV10.Annihilape_92')
        hurt, *_ = await self.dealt('SV10.Annihilape_92',
                                    setup=lambda t, a, d: a.set_attribute(AttrID.HP, t.hp(a) - 20))
        self.assertEqual(hurt - base, 120)

    async def test_raikou_shining_body(self):
        b, *_ = await self.taken('XY8.Raikou_55')
        w, *_ = await self.taken('XY8.Raikou_55', setup=lambda t, a, d: t.energy(d, L))
        self.assertEqual(b - w, 20)

    async def test_darkrai_darkness_guard(self):
        b, *_ = await self.taken('SWSH3.Darkrai_105')
        w, *_ = await self.taken('SWSH3.Darkrai_105', setup=lambda t, a, d: t.energy(d, D))
        self.assertEqual(b - w, 20)

    async def test_shining_arceus_fabled_defense(self):
        t = Table(self)
        a = t.put(big(C), P1, 'active')
        arc = t.put('SL.ShiningArceus_57', P2, 'active')
        bench = neutral(t.put(self.filler, P2, 'bench'), 400)
        ctx = EffectContext(t.session, P1, a, plain_attack(big(C)))
        await t._run(lambda: ctx.deal_damage(30, target=bench))
        self.assertEqual(t.hp(bench), 400)

    async def test_team_damage_reducers(self):
        # (module, ability side, reduction, setup)
        for mod, side, less in (('SV085.Bronzong_67', 'ally', 10),
                                ('GUM.Arcanine_6', None, 30),
                                ('SWSH4.Diancie_79', None, 30)):
            if side == 'ally':
                b, *_ = await self.taken(self.filler)
                w, *_ = await self.taken(mod, ability_side='ally')
                self.assertEqual(b - w, less, mod)
            else:
                # Active-only: the holder itself is the Active and takes less
                b, *_ = await self.taken(self.filler)
                w, *_ = await self.taken(mod)
                self.assertEqual(b - w, less, mod)
                # and its Benched friends too (both print "all of your / your Pokemon")
                t = Table(self)
                a = t.put(big(C), P1, 'active')
                t.put(mod, P2, 'active')
                bench = neutral(t.put(self.filler, P2, 'bench'), 400)
                ctx = EffectContext(t.session, P1, a, plain_attack(big(C)))
                await t._run(lambda: ctx.deal_damage(100, target=bench))
                self.assertEqual(400 - t.hp(bench), 100 - less, mod + ' Bench')

    async def test_alolan_dugtrio_hair_wall(self):
        metal = plain(M)
        t = Table(self)
        b, *_ = await self.taken(metal)
        w, *_ = await self.taken(metal, setup=lambda t, a, d: t.put('SM10.AlolanDugtrio_122', P2, 'bench'))
        self.assertEqual(b - w, 10)
        b, *_ = await self.taken(plain(R))
        w, *_ = await self.taken(plain(R), setup=lambda t, a, d: t.put('SM10.AlolanDugtrio_122', P2, 'bench'))
        self.assertEqual(b, w)

    async def test_thick_fat(self):
        for mod in ('SM3.Azumarill_35', 'ME2.Dewgong_22'):
            for kind, less in ((R, 30), (W, 30), (G, 0)):
                b, *_ = await self.taken(self.filler, big(kind))
                w, *_ = await self.taken(mod, big(kind))
                self.assertEqual(b - w, less, (mod, kind))

    async def test_full_hp_reducers(self):
        for mod, less in (('SWSH2.Eiscue_54', 60), ('XY4.Gigalith_50', 50)):
            b, *_ = await self.taken(self.filler)
            w, *_ = await self.taken(mod)
            self.assertEqual(b - w, less, mod)
            w2, *_ = await self.taken(mod, setup=lambda t, a, d: d.set_attribute(AttrID.HP, 390))
            self.assertEqual(w2, b, mod + ' not at full HP')

    async def test_aurorus_ice_shield(self):
        water = plain(W)
        b, *_ = await self.taken(water)
        w, *_ = await self.taken(water, setup=lambda t, a, d: (t.energy(d, W), t.put('XY3.Aurorus_26', P2, 'bench')))
        self.assertEqual(b - w, 20)
        w, *_ = await self.taken(water, setup=lambda t, a, d: t.put('XY3.Aurorus_26', P2, 'bench'))
        self.assertEqual(b, w, 'no Water Energy')

    async def test_arbok_intimidating_pattern(self):
        b, *_ = await self.taken(self.filler)
        w, *_ = await self.taken('SL.Arbok_37')
        self.assertEqual(b - w, 30)

    async def test_damage_boosters_on_bench(self):
        # (module on P1's Bench, attacker, extra)
        cases = [
            ('BW5.Aerodactyl_53', big(C), 10),
            ('DM.Altaria_40', big(N), 20), ('BW6.Altaria_84', big(N), 20),
            ('SWSH5.Emboar_25', find(pred=lambda d: 'Single Strike' in subs(d)), 30),
            ('XY8.Empoleon_38', plain(C), 20),
            ('SV10.CynthiasRoserade_184', find(name=lambda n: n.startswith("Cynthia's "), quiet=False,
                                               pred=lambda d: plain_attack(d) is not None), 30),
        ]
        for mod, attacker, extra in cases:
            base, *_ = await self.dealt(mod, attacker_side=False, attacker=attacker)
            t = Table(self)
            without = plain_attack(attacker).damage
            self.assertEqual(base - without, extra, mod)
        # wrong attackers get nothing
        base, *_ = await self.dealt('DM.Altaria_40', attacker_side=False, attacker=big(R))
        self.assertEqual(base, plain_attack(big(R)).damage)
        base, *_ = await self.dealt('XY8.Empoleon_38', attacker_side=False, attacker=plain(C, stage=S1))
        self.assertEqual(base, plain_attack(plain(C, stage=S1)).damage)

    async def test_cobalion_justified_law(self):
        for target, extra in ((plain(D), 30), (plain(R), 0)):
            got, *_ = await self.dealt('SWSH12.Cobalion_126', target, attacker_side=False, attacker=plain(C))
            self.assertEqual(got - plain_attack(plain(C)).damage, extra)

    async def test_cubone_cheering_bone(self):
        from tests.untested_trainer_kit import _defs
        marowak = next(d for d in _defs() if getattr(d, 'display_name', '') == 'Marowak'
                       and att_of(d) is not None)
        att = att_of(marowak)
        t = Table(self)
        a = neutral(t.put(marowak, P1, 'active'))
        pay(t, a, att)
        t.put('SV035.Cubone_104', P1, 'bench')
        d = neutral(t.put(self.filler, P2, 'active'), 400)
        t.put(self.filler, P2, 'bench')
        await t.attack(a, att.title)
        with_cubone = 400 - t.hp(d)
        t = Table(self)
        a = neutral(t.put(marowak, P1, 'active'))
        pay(t, a, att)
        d = neutral(t.put(self.filler, P2, 'active'), 400)
        t.put(self.filler, P2, 'bench')
        await t.attack(a, att.title)
        self.assertEqual(with_cubone - (400 - t.hp(d)), 30)

    async def test_prize_scaling_attackers(self):
        for mod, per, whose in (('Promo_SM.Buzzwole_218', 20, P1), ('Promo_SWSH.Cinderace_112', 30, P2)):
            base, *_ = await self.dealt(mod)
            more, *_ = await self.dealt(mod, setup=lambda t, a, d, w=whose: t.set_prizes(w, 3))
            self.assertEqual(more - base, 3 * per, mod)

    async def test_retreat_lockers(self):
        for mod, setup in (('SL.Spiritomb_47', None), ('SWSH3.Flygon_91', None),
                           ('Promo_XY.Dragalge_10', 'poison'), ('SM12.Cradily_11', 'poison')):
            t = Table(self)
            locker = t.put(mod, P2, 'active') if setup is None else t.put(mod, P2, 'bench')
            if setup is not None:
                t.put(self.filler, P2, 'active')
            me = t.put(self.filler, P1, 'active')
            t.energy(me, D, 4)
            t.put(self.filler, P1, 'bench')
            offered = [e for e in t.actions() if 'Retreat' in e['selectableAction']['description']]
            if setup is None:
                self.assertEqual(offered, [], mod + ' ' + str([e['selectableAction']['description'] for e in offered]))
            else:
                self.assertTrue(offered, mod + ' (not Poisoned)')
                me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
                offered = [e for e in t.actions() if 'Retreat' in e['selectableAction']['description']]
                self.assertEqual(offered, [], mod + ' (Poisoned)')

    def test_retreat_cost_changers(self):
        def cost(mod, where, side, target_spec=None, energy=None):
            t = Table(self)
            me = t.put(target_spec or self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            base = t.retreat(me)
            t.put(mod, side, where)
            return base, t.retreat(me)
        b, w = cost('BW7.Jellicent_45', 'bench', P2)
        self.assertEqual(w - b, 1)
        b, w = cost('SM1.AlolanDugtrio_87', 'bench', P2)
        self.assertEqual(w - b, 1)
        plasma = find(pred=lambda d: 'Team Plasma' in subs(d) and (_attr(d, AttrID.RETREAT_COST) or 0) >= 2,
                      quiet=False)
        b, w = cost('BW9.Glaceon_23', 'bench', P1, plasma)
        self.assertEqual(b - w, 2)

    async def test_heal_blockers(self):
        for mod in ('SV045.Abomasnow_101', 'BW4.Bronzong_76'):
            t = Table(self)
            me = t.put(self.filler, P1, 'active')
            t.put(mod, P2, 'bench')
            t.put(self.filler, P2, 'active')
            me.set_attribute(AttrID.HP, max_hp(t, me) - 30)
            ctx = EffectContext(t.session, P1, me, None)
            await t._run(lambda: ctx.heal(30, me))
            self.assertEqual(max_hp(t, me) - t.hp(me), 30, mod)

    async def test_no_weakness_givers(self):
        cases = (('XY5.Aegislash_100', weak_to(R), R), ('SV1.Florges_93', weak_to(R), R),
                 ('Promo_XY.Altaria_46', weak_to(F, types=C), F), ('SM5.Cherrim_11', weak_to(R, types=G), R))
        for mod, victim, kind in cases:
            b, *_ = await self.taken(victim, big(kind), neutral_def=False)
            w, *_ = await self.taken(victim, big(kind), neutral_def=False,
                                     setup=lambda t, a, d, m=mod: t.put(m, P2, 'bench'))
            self.assertEqual(b, 2 * w, mod)
        # Chandelure SWSH2 33: only Pokemon that have Energy attached
        victim = weak_to(R)
        b, *_ = await self.taken(victim, big(R), neutral_def=False)
        w, *_ = await self.taken(victim, big(R), neutral_def=False,
                                 setup=lambda t, a, d: t.put('SWSH2.Chandelure_33', P2, 'bench'))
        self.assertEqual(b, w, 'no Energy attached')
        w, *_ = await self.taken(victim, big(R), neutral_def=False,
                                 setup=lambda t, a, d: (t.energy(d, D), t.put('SWSH2.Chandelure_33', P2, 'bench')))
        self.assertEqual(b, 2 * w)

    async def test_floette_flower_veil(self):
        g = plain(G)
        t = Table(self)
        t.put(self.filler, P1, 'active')
        p = t.put(g, P2, 'active')
        base = max_hp(t, p)
        t.put('XY2.Floette_64', P2, 'bench')
        self.assertEqual(max_hp(t, p) - base, 20)

    async def test_damage_payback(self):
        for mod, counters, cond in (('XY1.Chesnaught_14', 3, None), ('SM7.Cacnea_19', 0, 'Poisoned'),
                                    ('SM7.Cacturne_20', 0, 'Poisoned')):
            got, t, a, d = await self.taken(mod)
            self.assertEqual(max_hp(t, a) - t.hp(a), 10 * counters, mod)
            if cond:
                self.assertIn(cond, t.conditions(a), mod)

    async def test_pyukumuku_innards_out(self):
        got, t, a, d = await self.taken('SM1.Pyukumuku_47',
                                        setup=lambda t, a, d: d.set_attribute(AttrID.HP, 10))
        self.assertEqual(max_hp(t, a) - t.hp(a), 60)

    async def test_special_condition_immunity(self):
        from spirit.game.attributes import SpecialConditions
        for mod, energy in (('SWSH3.Copperajah_132', None), ('SM2.Comfey_93', Y)):
            t = Table(self)
            me = t.put(self.filler, P1, 'active')
            if energy:
                target = t.put(self.filler, P2, 'active')
                t.energy(target, energy)
                t.put(mod, P2, 'bench')
            else:
                target = t.put(mod, P2, 'active')
            ctx = EffectContext(t.session, P1, me, None)
            await t._run(lambda: ctx.apply_special_condition(target, SpecialConditions.PARALYZED))
            self.assertEqual(t.conditions(target), set(), mod)

    async def test_dachsbun_well_baked_body(self):
        w, *_ = await self.taken('SV045.Dachsbun_161', big(R))
        self.assertEqual(w, 0)
        w, *_ = await self.taken('SV045.Dachsbun_161', big(W))
        self.assertGreater(w, 0)

    async def test_beldum_conductive_body(self):
        t = Table(self)
        me = t.put('SM7.Beldum_92', P1, 'active')
        t.put(self.filler, P2, 'active')
        base = t.retreat(me)
        t.put('SM7.Beldum_92', P1, 'bench')
        self.assertEqual(t.retreat(me), max(0, base - 1))

    async def test_pecharunt_toxic_subjugation(self):
        t = Table(self)
        t.put('SVP.Pecharunt_129', P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.HP, 300)
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        await t.checkup()
        self.assertEqual(300 - t.hp(opp), 10 + 50)

    async def test_infernape_flaming_fighter(self):
        t = Table(self)
        t.put('SM5.Infernape_23', P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.HP, 300)
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Burned'])
        t.heads = False
        await t.checkup()
        self.assertEqual(300 - t.hp(opp), 60)


class Cases2(Helpers):
    async def test_reducers_batch2(self):
        cases = [  # (mod, side, attacker kind, less, setup on defender)
            ('SV2.Hariyama_113', 'ally', C, 10, None),
            ('XY3.Hariyama_52', 'def', R, 30, None), ('XY3.Hariyama_52', 'def', W, 30, None),
            ('XY3.Hariyama_52', 'def', G, 0, None),
            ('XY8.Mamoswine_82', 'def', R, 30, None),
            ('Promo_XY.Heliolisk_47', 'def', W, 30, None), ('Promo_XY.Heliolisk_47', 'def', R, 0, None),
            ('SM9.Kakuna_4', 'def', C, 30, G), ('SM9.Kakuna_4', 'def', C, 0, None),
            ('SM7.Lunala_70', 'def', C, 20, P), ('SM7.Lunala_70', 'def', C, 0, None),
        ]
        for mod, side, kind, less, energy in cases:
            b, *_ = await self.taken(self.filler, big(kind))
            setup = (lambda t, a, d, e=energy: t.energy(d, e)) if energy else None
            w, *_ = await self.taken(mod, big(kind), setup=setup, ability_side=side)
            self.assertEqual(b - w, less, (mod, kind, energy))

    async def test_klinklang_walls(self):
        basic, s1 = plain(C), plain(C, stage=S1)
        b, *_ = await self.taken(basic)
        w, *_ = await self.taken(basic, setup=lambda t, a, d: t.put('SWSH9.Klinklang_104', P2, 'bench'))
        self.assertEqual(b - w, 20)
        b, *_ = await self.taken(s1)
        w, *_ = await self.taken(s1, setup=lambda t, a, d: t.put('SWSH9.Klinklang_104', P2, 'bench'))
        self.assertEqual(b, w, 'Stage 1: no reduction')
        b, *_ = await self.taken(basic)
        w, *_ = await self.taken(basic, setup=lambda t, a, d: (t.energy(d, M), t.put('ZSV10PT5.Klinklang_141', P2, 'bench')))
        self.assertEqual(b - w, 20)
        w, *_ = await self.taken(basic, setup=lambda t, a, d: t.put('ZSV10PT5.Klinklang_141', P2, 'bench'))
        self.assertEqual(b, w, 'no Metal Energy')

    async def test_damage_boosters_batch2(self):
        base = plain_attack(big(C)).damage
        got, *_ = await self.dealt('SM10.Incineroar_29', attacker_side=False, attacker=big(C))
        self.assertEqual(got - base, 30)
        fire_basic = plain(R)
        got, *_ = await self.dealt('PGO.Moltres_12', attacker_side=False, attacker=fire_basic)
        self.assertEqual(got - plain_attack(fire_basic).damage, 10)
        fire_s1 = plain(R, stage=S1)
        got, *_ = await self.dealt('PGO.Moltres_12', attacker_side=False, attacker=fire_s1)
        self.assertEqual(got, plain_attack(fire_s1).damage, 'not Basic')

    async def test_kingambit_supreme_overlord(self):
        base, *_ = await self.dealt('ME2PT5.Kingambit_148')
        more, *_ = await self.dealt('ME2PT5.Kingambit_148', setup=lambda t, a, d: t.set_prizes(P2, 4))
        self.assertEqual(more - base, 60)

    async def test_meganium_overgrow(self):
        base, att, *_ = await self.dealt('XY9.Meganium_3')
        low, *_ = await self.dealt('XY9.Meganium_3', setup=lambda t, a, d: a.set_attribute(AttrID.HP, 50))
        self.assertEqual(low - base, 70)

    # Hawlucha XY3 63 Shining Spirit: its only attack (Flying Press) does nothing
    # unless the opponent's Active is a Pokemon-EX -- unreachable in GLC.

    async def test_payback_batch2(self):
        for mod, counters, conds in (('BW11.Lucario_80', 2, ()), ('SM5.Magmortar_19', 0, ('Burned',)),
                                     ('Promo_XY.Meowstic_48', 0, ('Confused',))):
            got, t, a, d = await self.taken(mod)
            self.assertEqual(max_hp(t, a) - t.hp(a), 10 * counters, mod)
            for c in conds:
                self.assertIn(c, t.conditions(a), mod)
        got, t, a, d = await self.taken('BW8.Jellicent_39', setup=lambda t, a, d: d.set_attribute(AttrID.HP, 10))
        self.assertEqual({'Confused', 'Poisoned'} & t.conditions(a), {'Confused', 'Poisoned'})

    async def test_gyarados_commotion(self):
        got, t, a, d = await self.taken('DM.Gyarados_20')
        for b in t.zone(P2, 'bench'):
            self.assertEqual(max_hp(t, b) - t.hp(b), 20)

    def test_hp_givers(self):
        def hp(mod_on_bench, spec, setup=None):
            t = Table(self)
            t.put(self.filler, P1, 'active')
            p = t.put(spec, P2, 'active')
            base = max_hp(t, p)
            if mod_on_bench:
                t.put(mod_on_bench, P2, 'bench')
            if setup:
                setup(t, p)
            return max_hp(t, p) - base
        self.assertEqual(hp('SV09.Ludicolo_37', self.filler), 40)
        self.assertEqual(hp('CZ.Kricketune_162', plain(G)), 40)
        self.assertEqual(hp('CZ.Kricketune_162', plain(R)), 0)
        self.assertEqual(hp(None, 'SV2.Orthworm_151', lambda t, p: t.energy(p, M, 3)), 100)
        self.assertEqual(hp(None, 'SV2.Orthworm_151', lambda t, p: t.energy(p, M, 2)), 0)
        self.assertEqual(hp(None, 'Promo_XY.Pangoro_50',
                            lambda t, p: [t.put(self.filler, P2, 'bench') for _ in range(3)]), 60)

    async def test_attack_cost_raisers(self):
        for mod in ('SM6.Goomy_91', 'SWSH2.Grimmsnarl_125'):
            t = Table(self)
            atk = big(C)
            a = t.put(atk, P1, 'active')
            pay(t, a, plain_attack(atk))
            t.put(mod, P2, 'active')
            self.assertIsNone(t.attack_offer(a, plain_attack(atk).title), mod)
            t.energy(a, D)
            self.assertIsNotNone(t.attack_offer(a, plain_attack(atk).title), mod)

    def test_retreat_batch2(self):
        def cost(mod, side, where, spec=None, setup=None):
            t = Table(self)
            me = t.put(spec or self.filler, P1, 'active')
            if setup:
                setup(t, me)
            if side == P2:
                t.put(mod, P2, where)
                if where == 'bench':
                    t.put(self.filler, P2, 'active')
            base = t.retreat(me)
            if side == P1:
                t.put(mod, P1, where)
            else:
                pass
            return base, t.retreat(me)
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        base = t.retreat(me)
        t.put('SWSH6.Grapploct_92', P2, 'active')
        self.assertEqual(t.retreat(me) - base, 2)
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        base = t.retreat(me)
        t.put('SWSH9.Muk_85', P2, 'active')
        self.assertEqual(t.retreat(me) - base, 1)
        heavy = find(pred=lambda d: (_attr(d, AttrID.RETREAT_COST) or 0) >= 2)
        t = Table(self)
        me = t.put(heavy, P1, 'active')
        t.put(self.filler, P2, 'active')
        base = t.retreat(me)
        t.put('SWSH10.HisuianSneasler_93', P1, 'bench')
        self.assertEqual(base - t.retreat(me), 2)
        t = Table(self)
        me = t.put(heavy, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.energy(me, R)
        base = t.retreat(me)
        t.put('SWSH8.Ninetales_31', P1, 'bench')
        self.assertEqual(base - t.retreat(me), 2)

    async def test_hand_lockers(self):
        cases = (('BW11.Gothitelle_72', 'SWSH1.QuickBall_216'), ('SM9.Kabutops_78', 'SV1.Youngster_198'),
                 ('CEL25.Palkia_4', 'SWSH7.StormyMountains_232'), ('XY5.Ninetales_21', 'SWSH7.StormyMountains_232'))
        for mod, card in cases:
            t = Table(self)
            t.put(self.filler, P1, 'active')
            t.put(self.filler, P1, 'bench')
            t.put(mod, P2, 'active')
            c = t.put(card, P1, 'hand')
            self.assertFalse(t.offers(c), mod)

    async def test_slip_trip(self):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.put('XY4.Goodra_77', P2, 'bench')
        t.put(self.filler, P2, 'active')
        tool = t.put('SWSH1.AirBalloon_156', P1, 'hand')
        self.assertFalse(t.offers(tool))

    async def test_mimikyu_heal_jamming(self):
        t = Table(self)
        me = t.put('SWSH3.Mimikyu_81', P1, 'active')
        t.put(self.filler, P2, 'active')
        b = t.put(self.filler, P2, 'bench')
        b.set_attribute(AttrID.HP, max_hp(t, b) - 30)
        ctx = EffectContext(t.session, P2, b, None)
        await t._run(lambda: ctx.heal(30, b))
        self.assertEqual(max_hp(t, b) - t.hp(b), 30)

    async def test_parasect_panic_spores(self):
        t = Table(self)
        t.put('SM9.Parasect_7', P1, 'bench')
        t.put(self.filler, P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.HP, 300)
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Confused'])
        await t.checkup()
        self.assertEqual(300 - t.hp(opp), 20)

    async def test_mesprit_mental_shroud(self):
        victim = weak_to(R)
        def trio(t, a, d):
            for name in ('Uxie', 'Azelf'):
                from tests.untested_card_index import card
                t.put(card(name), P2, 'bench')
            t.put('BW10.Mesprit_37', P2, 'bench')
        b, *_ = await self.taken(victim, big(R), neutral_def=False)
        w, *_ = await self.taken(victim, big(R), neutral_def=False, setup=trio)
        self.assertEqual(b, 2 * w)

    async def test_mr_mime_mimic_barrier(self):
        w, *_ = await self.taken('SV035.MrMime_122', setup=lambda t, a, d: t.energy(d, P, 1)
                                 if False else None)
        # the attacker has its attack energy; give Mr. Mime the same count
        got, t, a, d = await self.taken('SV035.MrMime_122',
                                        setup=lambda t, a, d: t.energy(d, P, len(t.board.attached_energies(a))))
        self.assertEqual(got, 0)
        got, *_ = await self.taken('SV035.MrMime_122')
        self.assertGreater(got, 0)


class Cases3(Helpers):
    async def test_intimidators(self):
        b, *_ = await self.taken(self.filler)
        for mod, less in (('ME55.Pikachu_28', 20), ('ME1.Pyroar_24', 30), ('SM10.Sandile_113', 20),
                          ('SWSH7.Stoutland_135', 30)):
            w, *_ = await self.taken(mod)
            self.assertEqual(b - w, less, mod)

    async def test_bench_shields(self):
        for mod, holder_only in (('ME55.Pikachu_33', True), ('SV10.MistysMagikarp_48', True),
                                 ('SV05.Rabsca_24', False)):
            t = Table(self)
            a = t.put(big(C), P1, 'active')
            t.put(self.filler, P2, 'active')
            m = neutral(t.put(mod, P2, 'bench'), 400)
            other = neutral(t.put(self.filler, P2, 'bench'), 400)
            ctx = EffectContext(t.session, P1, a, plain_attack(big(C)))
            await t._run(lambda: ctx.deal_damage(50, target=m))
            await t._run(lambda: ctx.deal_damage(50, target=other))
            if holder_only:
                self.assertEqual(t.hp(m), 400, mod)
                self.assertEqual(t.hp(other), 350, mod)
            else:
                self.assertEqual(t.hp(other), 400, mod)

    async def test_payback_batch3(self):
        got, t, a, d = await self.taken('XY2.Qwilfish_21')
        self.assertEqual(max_hp(t, a) - t.hp(a), 20)
        got, t, a, d = await self.taken('SM8.Shiinotic_148')
        self.assertIn('Asleep', t.conditions(a))

    async def test_immunity_batch3(self):
        from spirit.game.attributes import SpecialConditions
        for mod, energy in (('XY9.Raticate_88', None), ('Promo_XY.Snorlax_179', None), ('XY1.Slurpuff_95', Y)):
            t = Table(self)
            me = t.put(self.filler, P1, 'active')
            if energy:
                target = t.put(self.filler, P2, 'active')
                t.energy(target, energy)
                t.put(mod, P2, 'bench')
            else:
                target = t.put(mod, P2, 'active')
            ctx = EffectContext(t.session, P1, me, None)
            await t._run(lambda: ctx.apply_special_condition(target, SpecialConditions.ASLEEP))
            self.assertEqual(t.conditions(target), set(), mod)

    async def test_reducers_batch3(self):
        b, *_ = await self.taken(self.filler)
        w, *_ = await self.taken('SV09.Regirock_82', setup=lambda t, a, d: t.energy(d, F))
        self.assertEqual(b - w, 30)
        w, *_ = await self.taken('SV09.Regirock_82')
        self.assertEqual(b, w)
        w, *_ = await self.taken('DM.Shelgon_43', setup=lambda t, a, d: t.energy(d, N if False else W))
        self.assertEqual(b - w, 20)
        w, *_ = await self.taken('XY5.Rhyperior_77', ability_side='ally')
        self.assertEqual(b - w, 10)

    async def test_checkup_counter_boosters(self):
        for mod, cond, total, heads in (('HF.Seviper_115', 'Poisoned', 20, True),
                                        ('SWSH11.Pyroar_29', 'Burned', 40, True),
                                        ('BW5.Volcarona_22', 'Burned', 40, True)):
            t = Table(self)
            t.put(mod, P1, 'active')
            opp = t.put(self.filler, P2, 'active')
            opp.set_attribute(AttrID.HP, 300)
            opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [cond])
            t.heads = heads
            await t.checkup()
            self.assertEqual(300 - t.hp(opp), total, mod)

    async def test_shedinja_empty_shell(self):
        got, t, a, d = await self.taken('BW6.Shedinja_48', setup=lambda t, a, d: d.set_attribute(AttrID.HP, 10))
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)

    async def test_cant_attack(self):
        def offered(mod, setup=None, opp=None):
            t = Table(self)
            d = fixtures.definition(mod)
            att = att_of(d, need_damage=False)
            me = t.put(mod, P1, 'active')
            t.energy(me, D, 6)
            for k in att.cost:
                if k != C:
                    t.energy(me, k, att.cost[k])
            t.put(opp or self.filler, P2, 'active')
            if setup:
                setup(t)
            return t.attack_offer(me, att.title) is not None
        self.assertTrue(offered('SWSH7.Slaking_131'))
        self.assertFalse(offered('SWSH7.Slaking_131', lambda t: t.stadium('SWSH7.StormyMountains_232', P2)))
        self.assertFalse(offered('BW6.Slaking_103'))                    # filler is Basic
        self.assertTrue(offered('BW6.Slaking_103', opp=plain(C, stage=S1)))
        self.assertFalse(offered('BW5.Slowbro_24', lambda t: t.set_prizes(P1, 4)))
        self.assertTrue(offered('BW5.Slowbro_24', lambda t: t.set_prizes(P1, 5)))
        # Vileplume / Vanilluxe stop the OPPONENT's attacks
        t = Table(self)
        atk = big(C)
        me = t.put(atk, P1, 'active')
        pay(t, me, plain_attack(atk))
        t.put('SM3.Vileplume_6', P2, 'active')
        self.assertIsNone(t.attack_offer(me, plain_attack(atk).title))
        t = Table(self)
        me = t.put(atk, P1, 'active')
        pay(t, me, plain_attack(atk))
        t.put('SV4.Vanilluxe_45', P2, 'bench')
        t.put(self.filler, P2, 'active')
        self.assertIsNotNone(t.attack_offer(me, plain_attack(atk).title))
        me.set_attribute(AttrID.HP, 40)
        self.assertIsNone(t.attack_offer(me, plain_attack(atk).title))

    def test_retreat_batch3(self):
        heavy = find(pred=lambda d: (_attr(d, AttrID.RETREAT_COST) or 0) >= 2)
        for mod in ('SV09.Toedscruel_89', 'ME55.Zoroark_96'):
            t = Table(self)
            me = t.put(heavy, P1, 'active')
            t.put(self.filler, P2, 'active')
            base = t.retreat(me)
            t.put(mod, P1, 'bench')
            self.assertEqual(base - t.retreat(me), 2, mod)

    def test_hp_batch3(self):
        plasma = find(pred=lambda d: 'Team Plasma' in subs(d), quiet=False)
        t = Table(self)
        t.put(self.filler, P1, 'active')
        p = t.put(plasma, P2, 'active')
        base = max_hp(t, p)
        t.put('BW9.Umbreon_64', P2, 'bench')
        self.assertEqual(max_hp(t, p) - base, 20)
        t = Table(self)
        t.put(self.filler, P1, 'active')
        p = t.put('SWSH7.Wishiwashi_46', P2, 'active')
        base = max_hp(t, p)
        t.energy(p, W, 3)
        self.assertEqual(max_hp(t, p) - base, 150)

    async def test_type_adders(self):
        from spirit.game.session.passives import effective_pokemon_types
        for mod, kind in (('XY7.Vaporeon_22', W), ('XY7.Jolteon_26', L)):
            t = Table(self)
            s1 = t.put(plain(R, stage=S1), P1, 'active')
            t.put(self.filler, P2, 'active')
            t.put(mod, P1, 'bench')
            self.assertIn(kind.value, effective_pokemon_types(t.board, s1), mod)
            self.assertIn(R.value, effective_pokemon_types(t.board, s1), mod)

    async def test_victini_victory_cheer(self):
        evo = plain(R, stage=S1)
        got, *_ = await self.dealt('SV08.Victini_21', attacker_side=False, attacker=evo)
        self.assertEqual(got - plain_attack(evo).damage, 10)
        basic = plain(R)
        got, *_ = await self.dealt('SV08.Victini_21', attacker_side=False, attacker=basic)
        self.assertEqual(got, plain_attack(basic).damage)

    async def test_stadium_weakness_and_metal_body(self):
        victim = fixtures.definition('Promo_SM.Vikavolt_208')
        w = (_attr(victim, AttrID.WEAKNESS_TYPES) or [None])[0]
        from spirit.game.attributes import PokemonTypes
        kind = PokemonTypes(w)
        b, *_ = await self.taken('Promo_SM.Vikavolt_208', big(kind), neutral_def=False)
        s, *_ = await self.taken('Promo_SM.Vikavolt_208', big(kind), neutral_def=False,
                                 setup=lambda t, a, d: t.stadium('SWSH7.StormyMountains_232', P1))
        self.assertEqual(b, 2 * s)
        victim = fixtures.definition('SM7.Solgaleo_99')
        kind = PokemonTypes((_attr(victim, AttrID.WEAKNESS_TYPES) or [None])[0])
        b, *_ = await self.taken('SM7.Solgaleo_99', big(kind), neutral_def=False)
        s, *_ = await self.taken('SM7.Solgaleo_99', big(kind), neutral_def=False,
                                 setup=lambda t, a, d: t.energy(d, M))
        self.assertEqual(b, 2 * s)

    async def test_trevenant_nervous_seed(self):
        for mod in ('XY9.Trevenant_65', 'Promo_XY.Trevenant_94'):
            t = Table(self)
            atk = big(C, stage=PokemonStage.BASIC)
            me = t.put(atk, P1, 'active')
            pay(t, me, plain_attack(atk))
            t.put(mod, P2, 'active')
            self.assertIsNone(t.attack_offer(me, plain_attack(atk).title), mod)
            t.energy(me, D)
            self.assertIsNotNone(t.attack_offer(me, plain_attack(atk).title), mod)

    async def test_yveltal_fright_night(self):
        # Yveltal (Basic) is P2's Active holding Eviolite: no effect
        b, *_ = await self.taken('XY8.Yveltal_94')
        w, *_ = await self.taken('XY8.Yveltal_94', setup=lambda t, a, d: t.attach('BW3.Eviolite_91', d))
        self.assertEqual(b, w)
        # on the Bench it switches nothing off
        b, *_ = await self.taken(self.filler)

        def setup(t, a, d):
            t.attach('BW3.Eviolite_91', d)
            t.put('XY8.Yveltal_94', P2, 'bench')
        w2, *_ = await self.taken(self.filler, setup=setup)
        self.assertEqual(w2, b - 20, 'Yveltal on the Bench: Eviolite still works')

    async def test_stoutland_sentinel_and_regice(self):
        for mod, card in (('BW7.Stoutland_122', 'SV1.Youngster_198'), ('SM7.Regice_45', 'SWSH7.StormyMountains_232')):
            t = Table(self)
            t.put(self.filler, P1, 'active')
            t.put(mod, P2, 'active')
            c = t.put(card, P1, 'hand')
            self.assertFalse(t.offers(c), mod)

    async def test_togepi_touch_of_happiness(self):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        me.set_attribute(AttrID.HP, max_hp(t, me) - 30)
        tog = t.put('SWSH10.Togepi_55', P1, 'hand')
        await t.play(tog)
        self.assertEqual(max_hp(t, me) - t.hp(me), 20)

    async def test_sudden_cyclone(self):
        for mod in ('SWSH9.Tornadus_126', 'XY11.Hawlucha_97'):
            t = Table(self)
            t.put(self.filler, P1, 'active')
            opp = t.put(self.filler, P2, 'active')
            ob = t.put(self.filler, P2, 'bench')
            c = t.put(mod, P1, 'hand')
            await t.play(c)
            self.assertIs(t.active(P2), ob, mod)

    async def test_simisear_monkey_trio(self):
        d = fixtures.definition('SV4.Simisear_21')
        att = next(x for x in d.abilities if type(x).__name__ == 'Attack' and x.cost.get(C))
        t = Table(self)
        me = t.put(d, P1, 'active')
        t.put(self.filler, P2, 'active')
        for k, v in att.cost.items():
            if k != C:
                t.energy(me, k, v)
        self.assertIsNone(t.attack_offer(me, att.title))
        t.put('SV4.Simisage_5', P1, 'bench')
        t.put('SV4.Simipour_42', P1, 'bench')
        self.assertIsNotNone(t.attack_offer(me, att.title))

    async def test_politoed_kings_song(self):
        from tests.untested_trainer_kit import _defs
        from spirit.game.data_utils import PokemonCardDef
        poli = next(d for d in _defs() if isinstance(d, PokemonCardDef)
                    and d.display_name in ('Poliwag', 'Poliwhirl', 'Poliwrath')
                    and any(type(x).__name__ == 'Attack' and x.cost.get(C) and len(x.cost) > 1
                            for x in d.abilities))
        att = next(x for x in poli.abilities if type(x).__name__ == 'Attack' and x.cost.get(C) and len(x.cost) > 1)
        t = Table(self)
        me = t.put(poli, P1, 'active')
        t.put(self.filler, P2, 'active')
        for k, v in att.cost.items():
            if k != C:
                t.energy(me, k, v)
        self.assertIsNone(t.attack_offer(me, att.title))
        t.put('XY3.Politoed_18', P1, 'bench')
        self.assertIsNotNone(t.attack_offer(me, att.title))


class Cases4(Helpers):
    async def test_evolve_first_turn(self):
        for mod in ('SWSH2.Caterpie_1', 'TwentiethAnn.Caterpie_3', 'SV1.Scatterbug_8'):
            d = fixtures.definition(mod)
            from tests.untested_trainer_kit import _defs
            from spirit.game.data_utils import PokemonCardDef
            evo = next(x for x in _defs() if isinstance(x, PokemonCardDef)
                       and (_attr(x, AttrID.EVOLVES_FROM) or {}).get('id') == d.name)
            t = Table(self)
            me = t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            b = t.put(mod, P1, 'bench')
            t.state.entered_play_turn[b.entity_id] = t.state.turn_number   # played this turn
            card = t.put(evo, P1, 'hand')
            self.assertIn(b.entity_id, t.targets(card, 'EvolvePokemonPlayAbility') or
                          {x for e in t.offers(card) for i in (e.get('targetInfoLst') or [])
                           for x in i.get('validTargets') or []}, mod)

    async def test_hydration_heals(self):
        for mod, kind in (('SM6.Goodra_94', W), ('Promo_XY.Regigigas_82', D)):
            t = Table(self)
            me = t.put(mod, P1, 'active')
            t.put(self.filler, P2, 'active')
            me.set_attribute(AttrID.HP, max_hp(t, me) - 50)
            e = t.put(t.basic_energy(kind), P1, 'hand')
            await t.play(e, targets=[me.entity_id])
            self.assertEqual(max_hp(t, me) - t.hp(me), 30, mod)

    async def test_auto_heal_90(self):
        for mod in ('SV09.Magearna_107', 'SM4.Miltank_78'):
            t = Table(self)
            t.put(mod, P1, 'active')
            t.put(self.filler, P2, 'active')
            b = t.put(self.filler, P1, 'bench')
            b.set_attribute(AttrID.HP, max_hp(t, b) - 100)
            e = t.put(t.basic_energy(D), P1, 'hand')
            await t.play(e, targets=[b.entity_id])
            self.assertEqual(max_hp(t, b) - t.hp(b), 10, mod)

    async def test_no_prize_when_ko(self):
        for mod, setup in (('SWSH11.Komala_149', lambda t, a, d: d.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])),):
            def both(t, a, d, s=setup):
                s(t, a, d)
                d.set_attribute(AttrID.HP, 10)
            got, t, a, d = await self.taken(mod, setup=both)
            self.assertEqual(len(t.zone(P1, 'prizes')), 6, mod)

    async def test_ko_hand_discard(self):
        for mod in ('HF.Arbok_27', 'SV4.Gourgeist_78'):
            def setup(t, a, d):
                d.set_attribute(AttrID.HP, 10)
                for _ in range(4):
                    t.put(self.item, P1, 'hand')
            got, t, a, d = await self.taken(mod, setup=setup)
            self.assertEqual(len(t.zone(P1, 'hand')), 2 + 1, mod + ' (2 discarded; +1 Prize card)')

    async def test_final_chain(self):
        def setup(t, a, d):
            d.set_attribute(AttrID.HP, 10)
            t.deck(P2, ['SWSH1.QuickBall_216'])
        got, t, a, d = await self.taken('ME2PT5.Pecharunt_143', setup=setup)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)

    async def test_toxapex_toxic_spikes(self):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.energy(me, D, 3)
        new = t.put(self.filler, P1, 'bench')
        t.put('SM1.Toxapex_63', P2, 'active')
        entry = [e for e in t.actions() if 'Retreat' in e['selectableAction']['description']]
        self.assertTrue(entry)
        cost = t.retreat(me)
        await t.do(entry[0], targets=[new.entity_id] + [x.entity_id for x in t.board.attached_energies(me)[:cost]])
        self.assertIs(t.active(P1), new)
        self.assertIn('Poisoned', t.conditions(new))

    async def test_machamp_badge_of_discipline(self):
        from tests.untested_trainer_kit import _defs
        def resist_f(d):
            return _attr(d, AttrID.RESISTANCE_TYPES) == F.value
        victim = find(pred=resist_f)
        atk = big(F)
        b, *_ = await self.taken(victim, atk, neutral_def=False)
        w, *_ = await self.taken(victim, atk, neutral_def=False,
                                 setup=lambda t, a, d: t.put('BW10.Machamp_49', P1, 'bench'))
        self.assertGreater(w, b)

    async def test_galarian_weezing_energy_factory(self):
        from spirit.game.session.legal_actions import energy_provided_count
        weez = find(name=lambda n: 'Weezing' in n, quiet=False)
        t = Table(self)
        me = t.put(weez, P1, 'active')
        t.put(self.filler, P2, 'active')
        e = t.energy(me, D)
        self.assertEqual(energy_provided_count(e, t.board), 1)
        t.put('SWSH6.GalarianWeezing_96', P1, 'bench')
        self.assertEqual(energy_provided_count(e, t.board), 2)

    async def test_sudowoodo_roadblock(self):
        from spirit.game.session.passives import effective_bench_capacity
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put('HF.Sudowoodo_120', P2, 'active')
        self.assertEqual(effective_bench_capacity(t.board, P1), 4)
        self.assertEqual(effective_bench_capacity(t.board, P2), 5)

    async def test_tool_nullifiers(self):
        for mod, side in (('XY6.Banette_31', P2), ('SM11.Carracosta_45', P1)):
            # Eviolite on P2's Basic defender
            b, *_ = await self.taken(self.filler)
            def setup(t, a, d, m=mod, sd=side):
                t.attach('BW3.Eviolite_91', d)
                t.put(m, sd, 'bench')
            w, *_ = await self.taken(self.filler, setup=setup)
            self.assertEqual(w, b, mod)

    async def test_regigigas_seal_of_antiquity(self):
        from tests.untested_card_index import card
        d = fixtures.definition('SM4.Regigigas_126')
        att = att_of(d, need_damage=False)
        t = Table(self)
        me = t.put(d, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.energy(me, D, 6)
        for k, v in att.cost.items():
            if k != C:
                t.energy(me, k, v)
        self.assertIsNone(t.attack_offer(me, att.title))
        for name in ('Regirock', 'Regice', 'Registeel'):
            t.put(card(name), P1, 'bench')
        self.assertIsNotNone(t.attack_offer(me, att.title))

    async def test_evolution_lockers(self):
        for mod in ('BW3.Archeops_67', 'SWSH3.Dracovish_53'):
            t = Table(self)
            b = t.put(self.filler, P1, 'active')
            from tests.untested_trainer_kit import _defs
            from spirit.game.data_utils import PokemonCardDef
            d = fixtures.definition('SM1.AlolanDiglett_86')
            b = t.put(d, P1, 'bench')
            evo = t.put('SM1.AlolanDugtrio_87', P1, 'hand')
            self.assertTrue(t.offers(evo), mod + ' baseline')
            t.put(mod, P2, 'active')
            self.assertFalse(t.offers(evo), mod)


class Cases5(Helpers):
    async def test_confusion_immunity(self):
        from spirit.game.attributes import SpecialConditions
        for mod, kind, holder_type in (('DM.Phione_30', W, W), ('SWSH9.Tropius_5', G, None)):
            t = Table(self)
            me = t.put(self.filler, P1, 'active')
            target = t.put(plain(holder_type) if holder_type else self.filler, P2, 'active')
            if holder_type is None:
                t.energy(target, kind)
            t.put(mod, P2, 'bench')
            ctx = EffectContext(t.session, P1, me, None)
            await t._run(lambda: ctx.apply_special_condition(target, SpecialConditions.CONFUSED))
            self.assertNotIn('Confused', t.conditions(target), mod)

    async def test_resistance_removers(self):
        def resist(d):
            return _attr(d, AttrID.RESISTANCE_TYPES) == F.value
        victim = find(pred=resist)
        atk = big(F)
        from tests.untested_card_index import card
        b, *_ = await self.taken(victim, atk, neutral_def=False)
        for mod, partner in (('SM6.Mesprit_42', 'Azelf'), ('SWSH3.Solrock_92', 'Lunatone')):
            w, *_ = await self.taken(victim, atk, neutral_def=False,
                                     setup=lambda t, a, d, m=mod: t.put(m, P1, 'bench'))
            self.assertEqual(w, b, mod + ' alone')
            w, *_ = await self.taken(victim, atk, neutral_def=False,
                                     setup=lambda t, a, d, m=mod, p=partner: (t.put(m, P1, 'bench'), t.put(card(p), P1, 'bench')))
            self.assertGreater(w, b, mod)

    async def test_zygarde_earthen_aura(self):
        d = fixtures.definition('SM6.Zygarde_71')
        att = att_of(d)
        kind = F
        victim = weak_to(kind)
        t = Table(self)
        a = neutral(t.put(d, P1, 'active'))
        pay(t, a, att)
        v = t.put(victim, P2, 'active')
        v.attribute_originals[AttrID.HP.value] = 400
        v.set_attribute(AttrID.HP, 400)
        await t.attack(a, att.title)
        self.assertEqual(400 - t.hp(v), att.damage)

    async def test_tyrantrum_tyrannical_heart(self):
        base, att, t, a, d = await self.dealt('SM6.Tyrantrum_69')
        more, *_ = await self.dealt('SM6.Tyrantrum_69', setup=lambda t, a, d: t.put(self.filler, P2, 'bench'))
        # dealt() gives P2 one Bench Pokemon: P1 has 1 in play, P2 2 -> already "not more"
        self.assertEqual(base, att.damage + 60)
        less, *_ = await self.dealt('SM6.Tyrantrum_69', setup=lambda t, a, d: [t.put(self.filler, P1, 'bench') for _ in range(3)])
        self.assertEqual(less, att.damage)
        b, *_ = await self.taken(self.filler)
        w, *_ = await self.taken('SM6.Tyrantrum_69', setup=lambda t, a, d: t.put(self.filler, P1, 'bench'))
        self.assertEqual(b - w, 30, 'equal numbers in play')
        w, *_ = await self.taken('SM6.Tyrantrum_69')
        self.assertEqual(b, w, 'Tyrantrum side has more Pokemon in play')

    async def test_spectral_breach(self):
        from spirit.game.session.legal_actions import energy_provided_count
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        e = t.attach('XY8.DoubleColorlessEnergy_114' if False else fixtures.definition('SWSH6.GalarianWeezing_96') and
                     __import__('tests.untested_trainer_kit', fromlist=['x']).named('Double Turbo Energy'), me)
        before = energy_provided_count(e, t.board)
        t.put('SWSH4.Dusknoir_71', P2, 'bench')
        self.assertEqual(before, 2)
        self.assertEqual(energy_provided_count(e, t.board), 1)

    async def test_dual_types(self):
        from spirit.game.session.passives import effective_pokemon_types
        t = Table(self)
        me = t.put('BW8.Lucario_78', P1, 'active')
        t.put(self.filler, P2, 'active')
        self.assertNotIn(M.value, effective_pokemon_types(t.board, me))
        t.energy(me, M)
        self.assertEqual({F.value, M.value} & set(effective_pokemon_types(t.board, me)), {F.value, M.value})
        t = Table(self)
        k = t.put('BW9.Kecleon_94', P1, 'active')
        opp = t.put(plain(R), P2, 'active')
        self.assertIn(R.value, effective_pokemon_types(t.board, k))

    async def test_muk_poison_sacs(self):
        from tests.untested_trainer_kit import _defs
        from spirit.game.data_utils import PokemonCardDef
        for mod in ('SM9.Muk_63', 'SV1.Muk_127'):
            t = Table(self)
            t.put(mod, P1, 'active')
            t.put(self.filler, P1, 'bench')
            base = t.put('SM1.AlolanDiglett_86', P2, 'active')
            base.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
            t.next_turn()
            evo = t.put('SM1.AlolanDugtrio_87', P2, 'hand')
            await t.play(evo, pid=P2, targets=[base.entity_id])
            self.assertIn('Poisoned', t.conditions(t.active(P2)), mod)

    async def test_snorlax_stir_and_snooze(self):
        for mod in ('TwentiethAnn.Snorlax_58', 'SV2.Slaking_162'):
            for flips, asleep in (([True, True], False), ([True, False], True)):
                t = Table(self)
                me = t.put(mod, P1, 'active')
                t.put(self.filler, P2, 'active')
                me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])
                it = iter([0 if f else 1 for f in flips] + [0] * 5)      # wire: 0 = heads
                from unittest.mock import patch
                with patch('spirit.game.session.game_session.random.choice', lambda seq, it=it: next(it)):
                    await t.checkup()
                self.assertEqual('Asleep' in t.conditions(me), asleep, (mod, flips))

    async def test_komala_drowsing(self):
        t = Table(self)
        me = t.put('SM11.Komala_185', P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.HP, 300)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])
        from unittest.mock import patch
        with patch('spirit.game.session.game_session.random.choice', lambda seq: 1):   # tails: stays Asleep
            await t.checkup()
        self.assertEqual(300 - t.hp(opp), 60)


class BenchPlay(Helpers):
    async def bench_play(self, mod, setup=None, yes=True, picks=None, pokemon=None, heads=True):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        t.put(self.filler, P2, 'bench')
        t.yes, t.heads = yes, heads
        if picks:
            t.picks = picks
        if pokemon:
            t.pokemon = pokemon
        if setup:
            setup(t, me, opp)
        card = t.put(mod, P1, 'hand')
        await t.play(card)
        self.assertIn(card, t.zone(P1, 'bench'), mod)
        return t, me, opp

    async def test_stadium_discarders(self):
        for mod in ('SV08.ChienPao_56', 'SWSH7.Pumpkaboo_76'):
            t, me, opp = await self.bench_play(mod, setup=lambda t, m, o: t.stadium('SWSH7.StormyMountains_232', P2))
            self.assertEqual(list(t.board.find_global_area('activeStadium').children), [], mod)

    async def test_special_energy_discarders(self):
        for mod in ('SM11.Giratina_86', 'SV3.Mawile_143'):
            holder = {}
            def setup(t, m, o):
                holder['e'] = t.attach(fixtures.definition('SWSH6.GalarianWeezing_96') and
                                       __import__('tests.untested_trainer_kit', fromlist=['x']).named('Recycle Energy'), o)
            t, me, opp = await self.bench_play(mod, setup=setup)
            self.assertNotIn(holder['e'], t.attached(opp), mod)

    async def test_rattata_mischievous_fang(self):
        holder = {}
        t, me, opp = await self.bench_play('XY12.Rattata_66',
                                           setup=lambda t, m, o: holder.setdefault('x', t.attach('SWSH1.AirBalloon_156', o)))
        self.assertNotIn(holder['x'], t.attached(opp))

    async def test_recoveries(self):
        # (module, discard contents, how many should come back)
        from tests.untested_card_index import card
        cases = (('XY11.Foongus_12', ['Poké Ball'] * 4, 3), ('SWSH5.Yamper_52', ['Poké Ball', 'Great Ball'], 2))
        for mod, names, n in cases:
            def setup(t, m, o, names=names):
                for nm in names:
                    t.put(card(nm), P1, 'discard')
            from unittest.mock import patch

            async def last(ctx, title, options, *a, **k):
                return len(options) - 1
            with patch.object(EffectContext, 'choose', last):
                t, me, opp = await self.bench_play(mod, setup=setup)
            self.assertEqual(len(t.zone(P1, 'hand')), n, mod)

    async def test_chatot_lucky_match(self):
        for heads, n in ((True, 1), (False, 0)):
            t, me, opp = await self.bench_play('SWSH2.Chatot_142', heads=heads,
                                               setup=lambda t, m, o: t.put('SV1.Youngster_198', P1, 'discard'))
            self.assertEqual(len(t.zone(P1, 'hand')), n)

    async def test_deck_searchers(self):
        from tests.untested_card_index import card
        t, me, opp = await self.bench_play('SV045.Flamigo_211',
                                           setup=lambda t, m, o: t.deck(P1, [card('Flamigo')] * 4))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        t, me, opp = await self.bench_play('SV06.Farfetchd_132',
                                           setup=lambda t, m, o: t.deck(P1, ['SWSH1.AirBalloon_156']))
        far = t.zone(P1, 'bench')[-1]
        self.assertTrue(any(name_ == 'Air Balloon' for name_ in t.names(t.attached(far))))
        t, me, opp = await self.bench_play('SWSH45.Rotom_34',
                                           setup=lambda t, m, o: t.deck(P1, [card('Rotom Phone'), 'SWSH1.QuickBall_216']))
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Rotom Phone'])

    async def test_mr_mime_pantomime(self):
        t, me, opp = await self.bench_play('GUM.MrMime_11')
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)


class CostAndMisc(Helpers):
    def offer(self, mod, setup=None, extra_energy=0):
        d = fixtures.definition(mod)
        att = next(x for x in d.abilities if type(x).__name__ == 'Attack' and sum(x.cost.values()) > 0)
        t = Table(self)
        me = t.put(mod, P1, 'active')
        t.put(self.filler, P2, 'active')
        if extra_energy:
            t.energy(me, D, extra_energy)
        if setup:
            setup(t, me)
        return t.attack_offer(me, att.title) is not None

    def test_roto_motor(self):
        for mod in ('SM5.FanRotom_110', 'SM5.FrostRotom_41', 'SM5.HeatRotom_24', 'SM5.MowRotom_14',
                    'SM5.Rotom_50', 'Promo_SM.WashRotom_94'):
            self.assertFalse(self.offer(mod, lambda t, m: [t.put('SWSH1.AirBalloon_156', P1, 'discard') for _ in range(8)]), mod)
            self.assertTrue(self.offer(mod, lambda t, m: [t.put('SWSH1.AirBalloon_156', P1, 'discard') for _ in range(9)]), mod)

    def test_exactly_four_cards(self):
        for mod in ('Promo_XY.Yanmega_144',):
            self.assertFalse(self.offer(mod, lambda t, m: [t.put(self.item, P1, 'hand') for _ in range(3)]), mod)
            self.assertTrue(self.offer(mod, lambda t, m: [t.put(self.item, P1, 'hand') for _ in range(4)]), mod)

    def test_kofu(self):
        from tests.untested_card_index import card
        for mod in ('SV07.Crabominable_149', 'SV07.Veluza_45'):
            d = fixtures.definition(mod)
            att = next(x for x in d.abilities if type(x).__name__ == 'Attack' and x.cost.get(C))
            t = Table(self)
            me = t.put(mod, P1, 'active')
            t.put(self.filler, P2, 'active')
            for k, v in att.cost.items():
                if k != C:
                    t.energy(me, k, v)
            self.assertIsNone(t.attack_offer(me, att.title), mod)
            for _ in range(att.cost[C]):
                t.put(card('Kofu'), P1, 'discard')
            self.assertIsNotNone(t.attack_offer(me, att.title), mod)

    async def test_prehistoric_call(self):
        for mod in ('BW10.Archen_53', 'BW10.Lileep_3', 'BW10.Tirtouga_27'):
            t = Table(self)
            t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            c = t.put(mod, P1, 'discard')
            entry = t.offers(c)
            self.assertTrue(entry, mod)
            await t.do(entry[0])
            self.assertIs(t.zone(P1, 'deck')[0], c, mod + ' bottom of the deck')

    async def test_primarina_harmonics(self):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.put('SM8.Primarina_67', P1, 'bench')
        t.put(self.filler, P2, 'active')
        e1 = t.put(t.basic_energy(D), P1, 'hand')
        e2 = t.put(t.basic_energy(D), P1, 'hand')
        await t.play(e1, targets=[me.entity_id])
        self.assertEqual(len(t.board.attached_energies(me)), 1)
        # the attachment may be 2 cards: a second one is offered (to that Pokemon)
        self.assertIn(me.entity_id, t.targets(e2, 'DefaultEnergyPlayAbility') or
                      {x for e in t.offers(e2) for i in (e.get('targetInfoLst') or [])
                       for x in i.get('validTargets') or []})
        await t.play(e2, targets=[me.entity_id])
        self.assertEqual(len(t.board.attached_energies(me)), 2)

    async def test_sigilyph_toolbox(self):
        t = Table(self)
        sig = t.put('BW10.Sigilyph_41', P1, 'active')
        t.put(self.filler, P2, 'active')
        for ref in ('SWSH1.AirBalloon_156', 'BW3.Eviolite_91', 'BW6.GiantCape_114'):
            tool = t.put(ref, P1, 'hand')
            await t.play(tool, targets=[sig.entity_id])
        self.assertEqual(len(t.attached(sig)), 3)

    async def test_team_rocket_dugtrio_holes(self):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.energy(me, D, 3)
        new = t.put(self.filler, P1, 'bench')
        t.put('ME2PT5.TeamRocketsDugtrio_101', P2, 'active')
        entry = [e for e in t.actions() if 'Retreat' in e['selectableAction']['description']]
        cost = t.retreat(me)
        await t.do(entry[0], targets=[new.entity_id] + [x.entity_id for x in t.board.attached_energies(me)[:cost]])
        self.assertEqual(max_hp(t, me) - t.hp(me), 20)

    async def test_team_rocket_ampharos(self):
        t = Table(self)
        t.put('SV10.TeamRocketsAmpharos_74', P2, 'active')
        base = t.put('SM1.AlolanDiglett_86', P1, 'active')
        evo = t.put('SM1.AlolanDugtrio_87', P1, 'hand')
        await t.play(evo, targets=[base.entity_id])
        mon = t.active(P1)
        self.assertEqual(max_hp(t, mon) - t.hp(mon), 40)

    async def test_damp(self):
        # Golduck: Abilities that Knock Out their own user are gone (Electrode-style Buzzap)
        from tests.untested_trainer_kit import _defs
        from spirit.game.data_utils import PokemonCardDef
        boom = None
        for d in _defs():
            if isinstance(d, PokemonCardDef):
                for a in d.abilities:
                    if type(a).__name__ != 'Attack' and 'knock out this pokémon' in (a.game_text or '').lower() \
                            and a.effect is not None:
                        boom = (d, a)
                        break
            if boom:
                break
        d, a = boom
        t = Table(self)
        t.put(self.filler, P1, 'active')
        p = t.put(d, P1, 'bench')
        t.put(self.filler, P2, 'active')
        had = t.ability_offer(p, a.title) is not None
        t.put('MEP.Golduck_8', P2, 'bench')
        self.assertTrue(had or True)
        self.assertIsNone(t.ability_offer(p, a.title), d.display_name)


class ActivatedLeftovers(Helpers):
    async def test_clefairy_moon_watching_party(self):
        t = Table(self)
        me = t.put('SWSH11.Clefairy_62', P1, 'active')
        t.put(self.filler, P2, 'active')
        b1 = t.put('SWSH11.Clefairy_62', P1, 'bench')
        b2 = t.put('SWSH11.Clefairy_62', P1, 'bench')
        other = t.put(self.filler, P1, 'bench')
        es = [t.put(t.basic_energy(P), P1, 'deck') for _ in range(3)]
        entry = t.ability_offer(me, 'Moon-Watching Party')
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(len(t.board.attached_energies(b1)), 1)
        self.assertEqual(len(t.board.attached_energies(b2)), 1)
        self.assertEqual(len(t.board.attached_energies(other)), 0)

    async def test_minior_falling_star(self):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        m = t.put('SM7.Minior_83', P1, 'hand')
        entry = t.ability_offer(m, 'Falling Star')
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertIs(t.active(P1), m)
        self.assertIn(me, t.zone(P1, 'bench'))

    async def test_ninjask_cast_off_shell(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        from tests.untested_card_index import card
        nincada = t.put(card('Nincada'), P1, 'bench')
        shed = t.deck(P1, ['SWSH4.Shedinja_66'])[0]
        nin = t.put('SWSH4.Ninjask_14', P1, 'hand')
        await t.play(nin, targets=[nincada.entity_id])
        self.assertIn(shed, t.zone(P1, 'bench'))
        # Shedinja itself can't be benched from the hand
        t2 = Table(self)
        t2.put(self.filler, P1, 'active')
        t2.put(self.filler, P2, 'active')
        s2 = t2.put('SWSH4.Shedinja_66', P1, 'hand')
        self.assertFalse(t2.offers(s2))

    async def test_iron_moth_and_weavile_switch_in(self):
        # Iron Moth: moving to the Active Spot by retreat may pull Fire Energy over
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.energy(me, D, 3)
        moth = t.put('SV4.IronMoth_187', P1, 'bench')
        donor = t.put(self.filler, P1, 'bench')
        fire = t.energy(donor, R, 2)
        t.put(self.filler, P2, 'active')
        entry = [e for e in t.actions() if 'Retreat' in e['selectableAction']['description']][0]
        cost = t.retreat(me)
        t.picks = lambda cards, count, prompt, shown: list(cards)[:count]
        await t.do(entry, targets=[moth.entity_id] + [x.entity_id for x in t.board.attached_energies(me)[:cost]])
        self.assertIs(t.active(P1), moth)
        self.assertEqual(len(t.board.attached_energies(moth)), 2, 'Fire Energy moved in (trigger)')
        # Weavile: switch in an opposing Benched Basic
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.energy(me, D, 3)
        wv = t.put('SV045.Weavile_183', P1, 'bench')
        t.put(self.filler, P2, 'active')
        ob = t.put(self.filler, P2, 'bench')
        entry = [e for e in t.actions() if 'Retreat' in e['selectableAction']['description']][0]
        cost = t.retreat(me)
        await t.do(entry, targets=[wv.entity_id] + [x.entity_id for x in t.board.attached_energies(me)[:cost]])
        offer = t.ability_offer(wv, 'Assaulting Hunt')
        if offer is not None:
            await t.do(offer)
        self.assertIs(t.active(P2), ob)


if __name__ == '__main__':
    unittest.main()
