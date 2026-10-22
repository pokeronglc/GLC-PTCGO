"""Bug hunt 3 (Oct 14): Trainers / Tools / Stadiums / Special Energy no test had run.

Targets: dev_notes/card_coverage.csv Trainer + Energy rows whose display name
and module stem appear in no test file (264 cards, list in
dev_notes/untested_trainers_oct14.txt). Each test plays the card (or attacks
through the Tool / Stadium) with the real action executor and checks the
printed text.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.untested_trainer_kit import (
    C, G, R, W, L, P, F, D, M, Y, N, board, find, named, neutral, plain,
    plain_attack, strike, big, stage_of, weak_to, ultra_beast, end_turn, with_attack, equip, name_of, max_hp, subs, pay)
from spirit.game.attributes import AttrID, PokemonStage
from spirit.tools.effect_smoke import P1, P2
from tests.bughunt_table import Table
from tests.untested_card_index import card as card_index

BASIC, S1, S2 = PokemonStage.BASIC, PokemonStage.STAGE1, PokemonStage.STAGE2


class Base(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def through(self, tool, attacker, defender, *, on='def', stadium=None,
                      neutral_def=True, setup=None, neutral_atk=True, stadium_owner=P2):
        """Damage of one plain attack, with `tool` on the defender/attacker."""
        t, a, d = board(self, attacker, defender, neutral_def=neutral_def,
                        neutral_atk=neutral_atk)
        if tool is not None:
            t.attach(tool, d if on == 'def' else a)
        if stadium is not None:
            t.stadium(stadium, stadium_owner)
        if setup:
            setup(t, a, d)
        return await strike(t, a, d), t, a, d

    async def delta(self, tool, attacker, defender, **kw):
        """(damage without the card, damage with it)."""
        base, *_ = await self.through(None, attacker, defender, **kw)
        kw2 = dict(kw)
        stadium = kw2.pop('stadium', None)
        if tool is None and stadium is not None:
            without, *_ = await self.through(None, attacker, defender,
                                             **{k: v for k, v in kw2.items()})
            withit, *_ = await self.through(None, attacker, defender, stadium=stadium, **kw2)
            return without, withit
        withit, *_ = await self.through(tool, attacker, defender, stadium=stadium, **kw2)
        return base, withit


class DamageReductionTools(Base):
    """Berries, Vests, Helmets, Chestplates, Charms: '... takes N less damage'."""

    async def berry(self, ref, kind, other):
        atk = big(kind)
        b, w = await self.delta(ref, atk, None)
        self.assertEqual(b - w, min(60, b), ref)
        _, t, a, d = await self.through(ref, atk, None)
        self.assertEqual(t.attached(d), [], 'berry discarded after use')
        # RULING (owner, Oct 14): discarded even when it brings the damage to 0
        small = find(types=kind, nosub=__import__('tests.untested_trainer_kit', fromlist=['x']).RULE_BOX,
                     pred=lambda d: plain_attack(d) is not None and plain_attack(d).damage <= 60)
        got, t, a, d = await self.through(ref, small, None)
        self.assertEqual(got, 0)
        self.assertEqual(t.attached(d), [], 'berry discarded at 0 damage too')
        # other type: no reduction, berry stays
        atk2 = big(other)
        b2, w2 = await self.delta(ref, atk2, None)
        self.assertEqual(b2, w2, ref + ' vs other type')
        _, t, a, d = await self.through(ref, atk2, None)
        self.assertEqual(len(t.attached(d)), 1)

    async def test_occa_berry(self):
        await self.berry('SV07.OccaBerry_140', R, W)

    async def test_passho_berry(self):
        await self.berry('SV08.PasshoBerry_184', W, R)

    async def test_payapa_berry(self):
        await self.berry('SV07.PayapaBerry_141', P, R)

    async def test_colbur_berry(self):
        await self.berry('SV08.ColburBerry_168', D, R)

    async def test_babiri_berry(self):
        await self.berry('SV08.BabiriBerry_163', M, R)

    async def test_haban_berry(self):
        await self.berry('SV085.HabanBerry_111', N, R)

    async def test_rule_box_only_tools_do_nothing_to_plain_pokemon(self):
        """GLC has no rule-box Pokemon: these Tools only ever see plain ones."""
        for ref in ('SM8.ChoiceHelmet_169', 'SM8.FairyCharmDragon_177',
                    'SM8.FairyCharmFighting_176', 'SM8.FairyCharmGrass_174',
                    'SM10.FairyCharmLightning_172', 'SM9.FairyCharmUB_142',
                    'SM10.FairyCharmAbility_171'):
            for kind in (C, N, F, G, L):
                b, w = await self.delta(ref, big(kind), plain(Y))
                self.assertEqual(b, w, (ref, kind))

    async def test_rigid_band(self):
        s1 = plain(C, stage=S1)
        b, w = await self.delta('SV035.RigidBand_165', None, s1)
        self.assertEqual(b - w, 30)
        b, w = await self.delta('SV035.RigidBand_165', None, plain(C))
        self.assertEqual(b, w, 'Basic holder: nothing')

    async def test_rock_chestplate(self):
        b, w = await self.delta('SV1.RockChestplate_192', None, plain(F))
        self.assertEqual(b - w, 30)
        b, w = await self.delta('SV1.RockChestplate_192', None, plain(W))
        self.assertEqual(b, w)

    async def test_thick_scale(self):
        dragon = plain(N)
        for kind in (G, R, W, L):
            b, w = await self.delta('ME2PT5.ThickScale_211', plain(kind), dragon)
            self.assertEqual(b - w, min(50, b), kind)
        b, w = await self.delta('ME2PT5.ThickScale_211', plain(P), dragon)
        self.assertEqual(b, w, 'Psychic attacker: nothing')
        b, w = await self.delta('ME2PT5.ThickScale_211', plain(R), plain(C))
        self.assertEqual(b, w, 'non-Dragon holder: nothing')

    async def test_ancient_crystal(self):
        regi = find(name=lambda n: n in ('Regirock', 'Regice', 'Registeel', 'Regigigas'),
                    nosub=('V', 'VMAX', 'VSTAR', 'GX', 'EX'), quiet=False)
        b, w = await self.delta('SM5.AncientCrystal_118', None, regi)
        self.assertEqual(b - w, 30)
        b, w = await self.delta('SM5.AncientCrystal_118', None, plain(C))
        self.assertEqual(b, w)

    async def test_eviolite(self):
        b, w = await self.delta('BW3.Eviolite_91', None, plain(C))
        self.assertEqual(b - w, 20)
        b, w = await self.delta('BW3.Eviolite_91', None, plain(C, stage=S1))
        self.assertEqual(b, w)

    async def test_assault_vest(self):
        dce = named('Recycle Energy')

        def special(t, a, d):
            t.attach(dce, a)
        b, w = await self.delta('XY8.AssaultVest_133', None, None, setup=special)
        self.assertEqual(b - w, min(40, b))
        b, w = await self.delta('XY8.AssaultVest_133', None, None)
        self.assertEqual(b, w, 'attacker without Special Energy')


class WeaknessHpRetreat(Base):
    async def weakness_removed(self, ref, defender, *, stadium=False, setup=None):
        kind = R
        atk = big(kind)
        args = dict(neutral_def=False, setup=setup)
        if stadium:
            b, *_ = await self.through(None, atk, defender, **args)
            w, *_ = await self.through(None, atk, defender, stadium=ref, **args)
        else:
            b, *_ = await self.through(None, atk, defender, **args)
            w, *_ = await self.through(ref, atk, defender, **args)
        return b, w

    async def test_weakness_policy(self):
        dfn = weak_to(R)
        b, w = await self.weakness_removed('SM3.WeaknessPolicy_126', dfn)
        self.assertEqual(b, 2 * w)

    async def test_protective_goggles(self):
        b, w = await self.weakness_removed('SV035.ProtectiveGoggles_164', weak_to(R, stage=BASIC))
        self.assertEqual(b, 2 * w)
        b, w = await self.weakness_removed('SV035.ProtectiveGoggles_164', weak_to(R, stage=S1))
        self.assertEqual(b, w, 'Stage 1 holder keeps Weakness')

    async def test_shadow_circle(self):
        dark = lambda t, a, d: t.energy(d, D)
        b, w = await self.weakness_removed('XY1.ShadowCircle_126', weak_to(R), stadium=True, setup=dark)
        self.assertEqual(b, 2 * w)
        b, w = await self.weakness_removed('XY1.ShadowCircle_126', weak_to(R), stadium=True)
        self.assertEqual(b, w, 'no Darkness Energy: Weakness stays')

    async def test_plasma_frigate(self):
        plasma = named('Plasma Energy')
        b, w = await self.weakness_removed('BW8.PlasmaFrigate_124', weak_to(R), stadium=True,
                                           setup=lambda t, a, d: t.attach(plasma, d))
        self.assertEqual(b, 2 * w)
        b, w = await self.weakness_removed('BW8.PlasmaFrigate_124', weak_to(R), stadium=True)
        self.assertEqual(b, w)

    async def test_magnetic_storm(self):
        def resist(kind):
            from tests.untested_trainer_kit import _attr, RULE_BOX

            def ok(d):
                return _attr(d, AttrID.RESISTANCE_TYPES) == kind.value
            return find(pred=ok, nosub=RULE_BOX)
        dfn = resist(F)
        atk = big(F)
        from tests.untested_trainer_kit import _attr
        amount = _attr(dfn, AttrID.RESISTANCE_AMOUNT)
        b, *_ = await self.through(None, atk, dfn, neutral_def=False)
        w, *_ = await self.through(None, atk, dfn, neutral_def=False, stadium='XY2.MagneticStorm_91')
        self.assertEqual(w - b, amount, 'Resistance gone')

    def hp_with(self, tool, spec, stadium=None):
        t, a, d = board(self, None, spec, neutral_def=False, hp=None)
        base = max_hp(t, d)
        if stadium:
            t.stadium(stadium, P1)
        else:
            t.attach(tool, d)
        return max_hp(t, d) - base

    def test_hp_tools(self):
        self.assertEqual(self.hp_with('SM3.BodybuildingDumbbells_113', plain(C, stage=S1)), 40)
        self.assertEqual(self.hp_with('SM3.BodybuildingDumbbells_113', plain(C)), 0)
        self.assertEqual(self.hp_with('BW6.GiantCape_114', plain(C)), 20)
        self.assertEqual(self.hp_with('SWSH1.BigCharm_158', plain(C)), 30)
        cyn = find(name=lambda n: n.startswith("Cynthia's "), quiet=False)
        self.assertEqual(self.hp_with('SV10.CynthiasPowerWeight_162', cyn), 70)
        self.assertEqual(self.hp_with('SV10.CynthiasPowerWeight_162', plain(C)), 0)
        self.assertEqual(self.hp_with(None, plain(C, stage=S1), stadium='XY3.TrainingCenter_102'), 30)
        self.assertEqual(self.hp_with(None, plain(C, stage=S2), stadium='XY3.TrainingCenter_102'), 30)
        self.assertEqual(self.hp_with(None, plain(C), stadium='XY3.TrainingCenter_102'), 0)

    def retreat_with(self, spec, tool=None, stadium=None, energy=None, owner=P2):
        t, a, d = board(self, None, spec, neutral_def=False, hp=None)
        if energy:
            t.energy(d, energy)
        base = t.retreat(d)
        if tool:
            t.attach(tool, d)
        if stadium:
            t.stadium(stadium, owner)
        return base, t.retreat(d)

    def test_retreat_tools_and_stadiums(self):
        rc = lambda d: (__import__('tests.untested_trainer_kit', fromlist=['x'])._attr(d, AttrID.RETREAT_COST) or 0)
        s2 = find(stage=S2, pred=lambda d: rc(d) >= 2)
        b, w = self.retreat_with(s2, 'SV035.BigAirBalloon_155')
        self.assertGreater(b, 0)
        self.assertEqual(w, 0)
        s1 = find(stage=S1, pred=lambda d: rc(d) >= 2)
        b, w = self.retreat_with(s1, 'SV035.BigAirBalloon_155')
        self.assertEqual(b, w, 'Stage 1: nothing')
        heavy = find(pred=lambda d: (__import__('tests.untested_trainer_kit', fromlist=['x'])._attr(d, AttrID.RETREAT_COST) or 0) >= 3)
        for kind in (P, D):
            b, w = self.retreat_with(heavy, stadium='SM2.AltaroftheMoone_117', energy=kind)
            self.assertEqual(b - w, 2, kind)
        b, w = self.retreat_with(heavy, stadium='SM2.AltaroftheMoone_117', energy=R)
        self.assertEqual(b, w)
        b, w = self.retreat_with(heavy, stadium='XY1.FairyGarden_117', energy=Y)
        self.assertEqual(w, 0)
        b, w = self.retreat_with(heavy, stadium='XY1.FairyGarden_117', energy=R)
        self.assertEqual(b, w)
        b, w = self.retreat_with(plain(C), stadium='SM3.MountLanakila_118')
        self.assertEqual(w - b, 1)
        b, w = self.retreat_with(plain(C, stage=S1), stadium='SM3.MountLanakila_118')
        self.assertEqual(w, b, 'only Basic Pokemon')
        psy = find(name='Psyduck', quiet=False)
        b, w = self.retreat_with(psy, stadium='SVP.ParadiseResort_150')
        self.assertEqual(b - w, 1)
        ns = find(name=lambda n: n.startswith("N's "), quiet=False,
                  pred=lambda d: (__import__('tests.untested_trainer_kit', fromlist=['x'])._attr(d, AttrID.RETREAT_COST) or 0) >= 1)
        b, w = self.retreat_with(ns, stadium='SV09.NsCastle_152')
        self.assertEqual(w, 0)
        b, w = self.retreat_with(heavy, stadium='SV09.NsCastle_152')
        self.assertEqual(b, w)


class DamageBoostTools(Base):
    async def test_type_gloves(self):
        for ref, kind in (('SWSH9.CleansingGloves_136', P), ('SWSH6.CrushingGloves_133', M),
                          ('SWSH7.DiggingGloves_145', F), ('SWSH6.FireResistantGloves_138', R),
                          ('SWSH9.HuntingGloves_142', N), ('SWSH6.JustifiedGloves_143', D),
                          ('SWSH7.RubberGloves_156', L), ('SWSH8.SpongyGloves_243', W),
                          ('SWSH6.WeedingGloves_155', G)):
            b, w = await self.delta(ref, None, plain(kind), on='atk')
            self.assertEqual(w - b, 30, ref)
            other = C if kind != C else R
            b, w = await self.delta(ref, None, plain(other), on='atk')
            self.assertEqual(w, b, ref + ' vs other type')

    async def test_struggle_gloves(self):
        # +30 if the Defending Pokemon is of the type the holder is weak to
        atk = weak_to(R)
        b, w = await self.delta('SWSH3.StruggleGloves_171', atk, plain(R), on='atk',
                                neutral_atk=False)
        self.assertEqual(w - b, 30)
        b, w = await self.delta('SWSH3.StruggleGloves_171', atk, plain(W), on='atk',
                                neutral_atk=False)
        self.assertEqual(w, b)

    async def test_beastite(self):
        ub = ultra_beast()

        def taken(n):
            return lambda t, a, d: t.set_prizes(P1, 6 - n)
        for n in (0, 2, 5):
            b, w = await self.delta('SM12.Beastite_185', ub, None, on='atk', setup=taken(n))
            self.assertEqual(w - b, 10 * n, n)
        b, w = await self.delta('SM12.Beastite_185', plain(C), None, on='atk', setup=taken(3))
        self.assertEqual(w, b, 'not an Ultra Beast')

    async def test_reverse_valley(self):
        # orientation card; normal orientation = the player who played it
        # gets "+10 for your Darkness", the other side "your Metal takes 10 less"
        b, w = await self.delta(None, plain(D), None, stadium='XY9.ReverseValley_110',
                                stadium_owner=P1)
        self.assertEqual(w - b, 10)
        b, w = await self.delta(None, plain(D), None, stadium='XY9.ReverseValley_110')
        self.assertEqual(w, b, "opponent's Stadium: no bonus for my Darkness")
        b, w = await self.delta(None, big(R), plain(M), stadium='XY9.ReverseValley_110',
                                stadium_owner=P1)
        self.assertEqual(b - w, 10, "the other player's Metal takes 10 less")
        b, w = await self.delta(None, big(R), plain(M), stadium='XY9.ReverseValley_110')
        self.assertEqual(b, w)

    async def test_binding_mochi(self):
        def poison(t, a, d):
            a.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        b, w = await self.delta('SV065.BindingMochi_55', None, None, on='atk', setup=poison)
        self.assertEqual(w - b, 40)
        b, w = await self.delta('SV065.BindingMochi_55', None, None, on='atk')
        self.assertEqual(w, b)


class ReactiveTools(Base):
    async def ko_board(self, tool, defender=None, attacker=None, hp=10):
        t, a, d = board(self, attacker or big(C), defender, hp=hp)
        t.put(self.filler, P2, 'bench')
        t.attach(tool, d)
        a_hp = t.hp(a)
        await t.attack(a, t.atk.title)
        return t, a, d, a_hp - t.hp(a)

    async def test_vengeful_punch(self):
        t, a, d, hurt = await self.ko_board('SV3.VengefulPunch_197')
        self.assertEqual(hurt, 40)
        t, a, d, hurt = await self.ko_board('SV3.VengefulPunch_197', hp=400)
        self.assertEqual(hurt, 0, 'not Knocked Out: nothing')

    async def test_bursting_balloon(self):
        t, a, d, hurt = await self.ko_board('XY9.BurstingBalloon_97', hp=400)
        self.assertEqual(hurt, 60)
        t, a, d, hurt = await self.ko_board('XY9.BurstingBalloon_97', hp=10)
        self.assertEqual(hurt, 60, 'even if Knocked Out')
        # discarded at the end of the opponent's turn (P1 attacks; P2 owns it)
        t, a, d = board(self, big(C), None)
        bb = t.attach('XY9.BurstingBalloon_97', d)
        await end_turn(t)                 # end of P1's turn = opponent's turn for P2
        self.assertNotIn(bb, t.attached(d))
        self.assertIn(bb, t.zone(P2, 'discard'))
        t, a, d = board(self, big(C), None)
        bb = t.attach('XY9.BurstingBalloon_97', a)
        await end_turn(t)                 # end of P1's own turn: stays
        self.assertIn(bb, t.attached(a))

    async def test_spirit_mask(self):
        t, a, d = board(self, big(C), None)
        await equip(t, 'SWSH7.SpiritMask_160', d)
        for _ in range(3):
            t.put(self.item, P1, 'hand')
        await t.attack(a, t.atk.title)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        # on the Bench: nothing
        t, a, d = board(self, big(C), None)
        bench = neutral(t.put(self.filler, P2, 'bench'), hp=400)
        await equip(t, 'SWSH7.SpiritMask_160', bench)
        t.put(self.item, P1, 'hand')
        await t.attack(a, t.atk.title)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_adversity_policy(self):
        dfn = weak_to(R)
        t, a, d = board(self, big(R), dfn, neutral_def=False)
        t.attach('ME4.AdversityPolicy_74', d)
        before = len(t.zone(P2, 'hand'))
        await t.attack(a, t.atk.title)
        self.assertEqual(len(t.zone(P2, 'hand')), before + 3)
        t, a, d = board(self, big(W), dfn, neutral_def=False)
        t.attach('ME4.AdversityPolicy_74', d)
        await t.attack(a, t.atk.title)
        self.assertEqual(len(t.zone(P2, 'hand')), before, 'not its Weakness type')

    async def test_floral_crown(self):
        t, a, d = board(self, None, None)
        t.attach('TwentiethAnn.FloralCrown_126', d)
        d.set_attribute(AttrID.HP, 350)
        await end_turn(t)          # P1's turn ends = P2's opponent's turn
        self.assertEqual(t.hp(d), 370)
        await end_turn(t)          # P2's own turn: nothing
        self.assertEqual(t.hp(d), 370)

    async def test_healing_scarf(self):
        t, a, d = board(self, None, None)
        t.attach('XY6.HealingScarf_84', a)
        a.set_attribute(AttrID.HP, t.hp(a) - 50)
        before = t.hp(a)
        e = t.put(t.basic_energy(D), P1, 'hand')
        await t.play(e, targets=[a.entity_id])
        self.assertIn(e, t.attached(a))
        self.assertEqual(t.hp(a), before + 20)

    async def test_patrol_cap(self):
        mill, att = with_attack(r"^discard the top (card|\d+ cards?) of your opponent's deck\.?$")
        for active in (True, False):
            t, a, d = board(self, mill, None, pay_attack=False)
            pay(t, a, att)
            holder = d if active else neutral(t.put(self.filler, P2, 'bench'), hp=400)
            t.attach('SV3.PatrolCap_191', holder)
            deck = len(t.zone(P2, 'deck'))
            await t.attack(a, att.title)
            if active:
                self.assertEqual(len(t.zone(P2, 'deck')), deck, 'protected')
            else:
                self.assertLess(len(t.zone(P2, 'deck')), deck, 'Benched holder: no protection')

    async def test_bent_spoon(self):
        para, att = with_attack(r"^(?!.*\b(if|flip|choose|shuffle|discard|itself|bench)\b).*(your opponent's active pokémon|the defending pokémon) is now paralyzed")
        t, a, d = board(self, para, None, pay_attack=False)
        pay(t, a, att)
        t.attach('XY10.BentSpoon_93', d)
        await t.attack(a, att.title)
        self.assertNotIn('Paralyzed', t.conditions(d))
        self.assertGreater(400 - t.hp(d), 0, 'damage still done')

    async def test_protection_cube(self):
        rec, att = with_attack(r"^this pokémon does (\d+) damage to itself\.?$")
        t, a, d = board(self, rec, None, pay_attack=False)
        pay(t, a, att)
        t.attach('XY2.ProtectionCube_95', a)
        before = t.hp(a)
        await t.attack(a, att.title)
        self.assertEqual(t.hp(a), before)
        self.assertGreater(400 - t.hp(d), 0)

    async def test_panic_mask(self):
        # attacker with 40 HP or less remaining: no damage
        t, a, d = board(self, big(C), None)
        t.attach('SWSH11.PanicMask_165', d)
        a.set_attribute(AttrID.HP, 40)
        await t.attack(a, t.atk.title)
        self.assertEqual(t.hp(d), 400)
        t, a, d = board(self, big(C), None)
        t.attach('SWSH11.PanicMask_165', d)
        a.set_attribute(AttrID.HP, 50)
        await t.attack(a, t.atk.title)
        self.assertLess(t.hp(d), 400)

    async def test_full_face_guard(self):
        b, w = await self.delta('SWSH7.FullFaceGuard_148', None, plain(C))
        self.assertEqual(b - w, 20)
        ab = find(nosub=('V', 'VMAX'), quiet=False,
                  pred=lambda d: any(type(x).__name__ != 'Attack' for x in d.abilities))
        b, w = await self.delta('SWSH7.FullFaceGuard_148', None, ab)
        self.assertEqual(b, w, 'holder has an Ability')

    async def test_galarian_chestplate(self):
        gal = find(name=lambda n: n.startswith('Galarian '), quiet=False)
        b, w = await self.delta('SWSH6.GalarianChestplate_141', None, gal)
        self.assertEqual(b - w, 30)
        b, w = await self.delta('SWSH6.GalarianChestplate_141', None, plain(C))
        self.assertEqual(b, w)

    async def test_billowing_smoke(self):
        t, a, d, _ = await self.ko_board('SWSH3.BillowingSmoke_158')
        self.assertEqual(len(t.zone(P1, 'prizes')), 5, 'a Prize card was taken')
        self.assertEqual(len(t.zone(P1, 'hand')), 0, '... into the discard pile, not the hand')

    async def test_lillies_pearl(self):
        lil = find(name=lambda n: n.startswith("Lillie's "), quiet=False)
        t, a, d, _ = await self.ko_board('SV09.LilliesPearl_151', defender=lil)
        self.assertEqual(len(t.zone(P1, 'prizes')), 6, '1 fewer Prize')
        t, a, d, _ = await self.ko_board('SV09.LilliesPearl_151')
        self.assertEqual(len(t.zone(P1, 'prizes')), 5)

    async def test_reversal_trigger(self):
        plasma = find(pred=lambda d: 'Team Plasma' in subs(d), nosub=('EX',), quiet=False)
        t, a, d = board(self, big(C), plasma, hp=10)
        await equip(t, 'BW10.ReversalTrigger_86', d)
        bench = t.put(self.filler, P2, 'bench')
        self.assertEqual(len(t.zone(P2, 'hand')), 0)
        wanted = t.deck(P2, ['SWSH1.QuickBall_216'])[0]
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if c is wanted][:count] or cards[:count]
        await t.attack(a, t.atk.title)
        self.assertIn(wanted, t.zone(P2, 'hand'))

    async def test_team_plasma_badge_and_silver_mirror(self):
        # Badge makes the holder Team Plasma; Silver Mirror then stops its attacks
        t, a, d = board(self, big(C), None)
        await equip(t, 'BW9.TeamPlasmaBadge_104', a)
        t.attach('BW10.SilverMirror_89', d)
        await t.attack(a, t.atk.title)
        self.assertEqual(t.hp(d), 400)
        t, a, d = board(self, big(C), None)
        t.attach('BW10.SilverMirror_89', d)
        await t.attack(a, t.atk.title)
        self.assertLess(t.hp(d), 400, 'attacker is not Team Plasma')


class LiveReports(Base):
    async def test_tm_machine_only_technical_machines(self):
        """Owner report (Oct 14): TM Machine SV10 181 found Luxurious Cape."""
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        card = t.put('SV10.TMMachine_181', P1, 'hand')
        tms = t.deck(P1, ['SV4.TechnicalMachineEvolution_178', 'SV4.TechnicalMachineBlindside_176',
                          'SV08.TechnicalMachineFluorite_188', 'SV045.TechnicalMachineCrisisPunch_90'])
        cape = t.deck(P1, [card_index('Luxurious Cape')])[0]
        seen = []

        def picks(cards, count, prompt, shown):
            seen.append(list(cards))
            return list(cards)[:count]
        t.picks = picks
        await t.play(card)
        self.assertTrue(seen)
        self.assertNotIn(cape, seen[0])
        self.assertEqual(set(seen[0]), set(tms))
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(c in hand for c in tms), 3, 'up to 3')
        self.assertNotIn(cape, hand)


class DrawSupporters(Base):
    def setup_board(self, hand=3, bench=1):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        t.put(self.filler, P2, 'bench')
        for _ in range(bench):
            t.put(self.filler, P1, 'bench')
        for _ in range(hand):
            t.put(self.item, P1, 'hand')
        return t, me, opp

    async def play_ref(self, ref, hand=3, setup=None, heads=True, picks=None, pid=P1):
        t, me, opp = self.setup_board(hand)
        card = t.put(ref, P1, 'hand')
        t.heads = heads
        if picks is not None:
            t.picks = picks
        if setup:
            r = setup(t, me, opp)
            if hasattr(r, '__await__'):
                await r
        deck = len(t.zone(P1, 'deck'))
        offered = t.can(card, 'UseTrainerCard')
        if offered:
            await t.play(card)
        t.deck_before = deck
        return t, me, opp, offered

    def hand(self, t, pid=P1):
        return len(t.zone(pid, 'hand'))

    async def test_billy_onare(self):
        t, *_ , ok = await self.play_ref('SV09.BillyONare_142', hand=3)
        self.assertEqual(self.hand(t), 5)
        t, *_ , ok = await self.play_ref('SV09.BillyONare_142', hand=8)
        self.assertEqual(self.hand(t), 12, '8 + 2 = 10 -> 2 more')

    async def test_brassius(self):
        t, *_ , ok = await self.play_ref('SV085.Brassius_135', hand=4)
        self.assertEqual(self.hand(t), 5)

    async def test_bill_maintenance(self):
        t, *_ , ok = await self.play_ref('SM7.BillsMaintenance_126', hand=2)
        self.assertEqual(self.hand(t), 4, '2 - 1 shuffled + 3')
        t, *_ , ok = await self.play_ref('SM7.BillsMaintenance_126', hand=0)
        self.assertFalse(ok, 'needs another card to shuffle')

    async def test_coach_trainer_no_tag_team(self):
        t, *_ , ok = await self.play_ref('SM11.CoachTrainer_192', hand=2)
        self.assertEqual(self.hand(t), 4)

    async def test_daisys_help(self):
        t, *_ , ok = await self.play_ref('SV035.DaisysHelp_158', hand=2)
        self.assertEqual(self.hand(t), 4)

    async def test_dendra(self):
        t, *_ , ok = await self.play_ref('SV2.Dendra_179', hand=2)
        self.assertEqual(self.hand(t), 5)
        t, *_ , ok = await self.play_ref('SV2.Dendra_179', hand=0)
        self.assertFalse(ok)

    async def test_falkner(self):
        t, *_ , ok = await self.play_ref('SV2.Falkner_180', hand=1)
        self.assertEqual(self.hand(t), 3)
        t, *_ , ok = await self.play_ref('SV2.Falkner_180', hand=1,
                                          setup=lambda t, m, o: t.stadium('SWSH7.StormyMountains_232', P1))
        self.assertEqual(self.hand(t), 5)
        t, *_ , ok = await self.play_ref('SV2.Falkner_180', hand=1,
                                          setup=lambda t, m, o: t.stadium('SWSH7.StormyMountains_232', P2))
        self.assertEqual(self.hand(t), 3, "opponent's Stadium is not 'you have a Stadium in play'")

    async def test_grusha(self):
        t, *_ , ok = await self.play_ref('SV2.Grusha_184', hand=1)
        self.assertEqual(self.hand(t), 7, 'no Energy anywhere: up to 7')
        t, *_ , ok = await self.play_ref('SV2.Grusha_184', hand=1,
                                          setup=lambda t, m, o: t.energy(m, D))
        self.assertEqual(self.hand(t), 5)

    async def test_norman_no_ex(self):
        t, *_ , ok = await self.play_ref('SV4.Norman_168', hand=1)
        self.assertEqual(self.hand(t), 3)

    async def test_parasol_lady(self):
        t, *_ , ok = await self.play_ref('SV4.ParasolLady_169', hand=5)
        self.assertEqual(self.hand(t), 4)

    async def test_professor_birch(self):
        for heads, n in ((True, 7), (False, 4)):
            t, *_ , ok = await self.play_ref('XY5.ProfessorBirchsObservations_134', hand=3, heads=heads)
            self.assertEqual(self.hand(t), n)

    async def test_professor_oaks_hint(self):
        t, *_ , ok = await self.play_ref('XY12.ProfessorOaksHint_84', hand=2)
        self.assertEqual(self.hand(t), 7)

    async def test_youngster_and_shauna(self):
        t, *_ , ok = await self.play_ref('SV1.Youngster_198', hand=2)
        self.assertEqual(self.hand(t), 5)
        t, *_ , ok = await self.play_ref('SWSH8.Shauna_240', hand=2)
        self.assertEqual(self.hand(t), 5)

    async def test_sophocles(self):
        t, *_ , ok = await self.play_ref('SL.Sophocles_65', hand=3)
        self.assertEqual(self.hand(t), 5)
        t, *_ , ok = await self.play_ref('SL.Sophocles_65', hand=1)
        self.assertFalse(ok, 'needs 2 cards to discard')

    async def test_tv_reporter(self):
        t, *_ , ok = await self.play_ref('SM7.TVReporter_149', hand=1)
        self.assertEqual(self.hand(t), 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 2, 'TV Reporter + 1 discarded')

    async def test_team_grunts(self):
        for ref in ('TATM.TeamAquaGrunt_26', 'TATM.TeamMagmaGrunt_30'):
            t, *_ , ok = await self.play_ref(ref, hand=2)
            self.assertEqual(self.hand(t), 4, ref)
            t, *_ , ok = await self.play_ref(ref, hand=0)
            self.assertFalse(ok, ref)

    async def test_team_plasma_grunt(self):
        t, *_ , ok = await self.play_ref('BW8.TeamPlasmaGrunt_125', hand=2)
        self.assertFalse(ok, 'no Team Plasma card in hand')
        plasma = named('Plasma Energy')
        t, *_ , ok = await self.play_ref('BW8.TeamPlasmaGrunt_125', hand=2,
                                          setup=lambda t, m, o: t.put(plasma, P1, 'hand'))
        self.assertTrue(ok)
        self.assertEqual(self.hand(t), 6)
        self.assertIn('Plasma Energy', t.names(t.zone(P1, 'discard')))

    async def test_ilima(self):
        t, me, opp, ok = await self.play_ref(
            'SM1.Ilima_121', hand=2, setup=lambda t, m, o: [t.put(self.item, P2, 'hand') for _ in range(4)])
        self.assertEqual(self.hand(t), 6)
        self.assertEqual(self.hand(t, P2), 6)

    async def test_hugh(self):
        def setup(t, m, o):
            for _ in range(8):
                t.put(self.item, P2, 'hand')
        t, *_ , ok = await self.play_ref('BW7.Hugh_130', hand=1, setup=setup)
        self.assertEqual(self.hand(t), 5)
        self.assertEqual(self.hand(t, P2), 5)

    async def test_psychics_third_eye(self):
        t, *_ , ok = await self.play_ref('XY9.PsychicsThirdEye_108', hand=3,
                                          picks=lambda cards, count, prompt, shown: list(cards)[:2])
        self.assertEqual(self.hand(t), 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 3)

    async def test_bruno(self):
        t, *_ , ok = await self.play_ref('SWSH5.Bruno_121', hand=3)
        self.assertEqual(self.hand(t), 4)

        def ko(t, m, o):
            t.state.kos_suffered_last_turn = {P1: [{"entity_id": "x"}]}
            t.state.kos_by_attack_last_turn = {P1: [{"entity_id": "x"}]}
        t, *_ , ok = await self.play_ref('SWSH5.Bruno_121', hand=3, setup=ko)
        self.assertEqual(self.hand(t), 7)

    async def test_choy(self):
        t, *_ , ok = await self.play_ref('SWSH10.Choy_137', hand=1)
        self.assertEqual(self.hand(t), 4)

    async def test_zinnias_resolve(self):
        t, *_ , ok = await self.play_ref('SWSH7.ZinniasResolve_164', hand=2)
        self.assertEqual(self.hand(t), 2, 'discard 2, draw 1 per opposing Pokemon (2)')
        t, *_ , ok = await self.play_ref('SWSH7.ZinniasResolve_164', hand=1)
        self.assertFalse(ok)

    async def test_league_staff(self):
        t, *_ , ok = await self.play_ref('SWSH4.LeagueStaff_153', hand=1)
        self.assertEqual(self.hand(t), 3)

    async def test_ingo_emmet(self):
        for pick in (0, 1):
            t, me, opp = self.setup_board(3)
            card = t.put('SM9.IngoEmmet_144', P1, 'hand')
            bottom = t.deck(P1, [self.filler], top=False)[0]
            from spirit.game.session.effects import EffectContext
            from unittest.mock import patch

            async def choose(ctx, title, options, *a, **k):
                return pick
            with patch.object(EffectContext, 'choose', choose):
                await t.play(card)
            self.assertEqual(self.hand(t), 5)
            self.assertEqual(len(t.zone(P1, 'discard')), 4)
            self.assertEqual(bottom in t.zone(P1, 'hand'), pick == 1)

    async def test_giovannis_scheme_draw(self):
        from spirit.game.session.effects import EffectContext
        from unittest.mock import patch

        async def choose(ctx, title, options, *a, **k):
            return 0
        t, me, opp = self.setup_board(2)
        card = t.put('XY8.GiovannisScheme_138', P1, 'hand')
        with patch.object(EffectContext, 'choose', choose):
            await t.play(card)
        self.assertEqual(self.hand(t), 5)

    async def test_giovannis_scheme_damage(self):
        from spirit.game.session.effects import EffectContext
        from unittest.mock import patch

        async def choose(ctx, title, options, *a, **k):
            return 1
        t, a, d = board(self, None, None)
        card = t.put('XY8.GiovannisScheme_138', P1, 'hand')
        base = t.atk.damage
        with patch.object(EffectContext, 'choose', choose):
            await t.play(card)
        await t.attack(a, t.atk.title)
        self.assertEqual(400 - t.hp(d), base + 20)


class SearchHealItems(Base):
    setup_board = DrawSupporters.setup_board
    def pick(self, wanted):
        return lambda cards, count, prompt, shown: [c for c in cards if c in wanted][:count]

    async def test_cilan(self):
        t, me, opp = self.setup_board(0)
        card = t.put('BW4.Cilan_86', P1, 'hand')
        es = [t.put(t.basic_energy(k), P1, 'deck') for k in (R, W, G, L)]
        await t.play(card)
        self.assertEqual(sum(e in t.zone(P1, 'hand') for e in es), 3)

    async def test_trevor(self):
        t, me, opp = self.setup_board(0)
        card = t.put('Promo_XY.Trevor_33', P1, 'hand')
        mon = t.deck(P1, [self.filler])[0]
        await t.play(card)
        self.assertEqual(t.zone(P1, 'hand'), [mon])

    async def test_friend_ball(self):
        t, me, opp = self.setup_board(0)
        card = t.put('SM7.FriendBall_131', P1, 'hand')
        from tests.untested_trainer_kit import types_of
        kind = types_of(self.filler)[0]
        other = R if kind != R else W
        same, diff = t.deck(P1, [plain(kind, nosub=None) if False else self.filler, plain(other)])
        offered = []
        t.picks = lambda cards, count, prompt, shown: offered.extend(cards) or list(cards)[:count]
        await t.play(card)
        self.assertIn(same, offered)
        self.assertNotIn(diff, offered)

    async def test_misty_determination(self):
        t, me, opp = self.setup_board(1)
        card = t.put('HF.MistysDetermination_62', P1, 'hand')
        want = t.deck(P1, ['SWSH1.QuickBall_216'], top=True)[0]
        t.picks = self.pick({want}) if False else (
            lambda cards, count, prompt, shown: [want] if want in cards else list(cards)[:count])
        await t.play(card)
        self.assertIn(want, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    async def test_rika(self):
        t, me, opp = self.setup_board(0)
        card = t.put('SV4.Rika_172', P1, 'hand')
        top = t.deck(P1, ['SWSH1.QuickBall_216'] * 4)
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        rest = [c for c in top if c not in t.zone(P1, 'hand')]
        deck = t.zone(P1, 'deck')
        self.assertEqual(set(deck[:2]), set(rest), 'the other 2 on the bottom')

    async def test_raifort(self):
        t, me, opp = self.setup_board(0)
        card = t.put('SV06.Raifort_161', P1, 'hand')
        top = t.deck(P1, ['SWSH1.QuickBall_216'] * 5)
        t.picks = lambda cards, count, prompt, shown: list(cards)[:2] if 'iscard' in prompt or True else []
        await t.play(card)
        discarded = [c for c in top if c in t.zone(P1, 'discard')]
        self.assertGreaterEqual(len(discarded), 1)
        self.assertTrue(all(c in t.zone(P1, 'deck') for c in top if c not in discarded))

    async def test_pokenav(self):
        t, me, opp = self.setup_board(0)
        card = t.put('SM7.PokNav_140', P1, 'hand')
        mon, item = t.deck(P1, [self.filler, 'SWSH1.QuickBall_216'])
        offered = []
        t.picks = lambda cards, count, prompt, shown: offered.extend(cards) or list(cards)[:count]
        await t.play(card)
        self.assertIn(mon, offered)
        self.assertNotIn(item, offered)
        self.assertIn(mon, t.zone(P1, 'hand'))

    async def test_reserved_ticket(self):
        t, me, opp = self.setup_board(0)
        card = t.put('XY8.ReservedTicket_147', P1, 'hand')
        want = t.deck(P1, ['SWSH1.QuickBall_216'], top=False)[0]
        t.picks = lambda cards, count, prompt, shown: [want]
        await t.play(card)
        self.assertIs(t.zone(P1, 'deck')[-1], want, 'on top')

    async def test_return_label_and_surprise_box(self):
        for ref, zone in (('SM9.ReturnLabel_153', 'deck'), ('SM10.SurpriseBox_187', 'hand')):
            t, me, opp = self.setup_board(0)
            card = t.put(ref, P1, 'hand')
            x = t.put('SWSH1.QuickBall_216', P2, 'discard')
            await t.play(card)
            self.assertIn(x, t.zone(P2, zone), ref)
            if zone == 'deck':
                self.assertIs(t.zone(P2, 'deck')[0], x, 'bottom')

    async def test_shadow_triad(self):
        t, me, opp = self.setup_board(0)
        card = t.put('BW9.ShadowTriad_102', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        pe = t.put(named('Plasma Energy'), P1, 'discard')
        t.put('SWSH1.QuickBall_216', P1, 'discard')
        await t.play(card)
        self.assertIn(pe, t.zone(P1, 'hand'))

    async def test_saguaro(self):
        t, me, opp = self.setup_board(0)
        b = t.zone(P1, 'bench')[0]
        for p in (me, b):
            p.set_attribute(AttrID.HP, max_hp(t, p) - 60)
        card = t.put('SV2.Saguaro_187', P1, 'hand')
        picked = iter([me, b])
        t.pokemon = lambda c, p: next(picked)
        t.picks = lambda cards, count, prompt, shown: [x for x in cards if x in (me, b)][:count]
        await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 10)
        self.assertEqual(max_hp(t, b) - t.hp(b), 10)

    async def test_bianca_devotion(self):
        t, me, opp = self.setup_board(0)
        card = t.put('SV05.BiancasDevotion_142', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'), 'nobody at 30 HP or less')
        me.set_attribute(AttrID.HP, 30)
        await t.play(card)
        self.assertEqual(t.hp(me), max_hp(t, me))

    async def test_olympia(self):
        t, me, opp = self.setup_board(0)
        me.set_attribute(AttrID.HP, max_hp(t, me) - 50)
        card = t.put('TwentiethAnn.Olympia_66', P1, 'hand')
        await t.play(card)
        self.assertIn(me, t.zone(P1, 'bench'))
        self.assertEqual(max_hp(t, me) - t.hp(me), 20)

    async def test_team_yell_towel(self):
        t, me, opp = self.setup_board(0)
        for p in (me, opp):
            p.set_attribute(AttrID.HP, max_hp(t, p) - 60)
        card = t.put('SWSH45.TeamYellTowel_63', P1, 'hand')
        await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 10)
        self.assertEqual(max_hp(t, opp) - t.hp(opp), 10)

    async def test_moomoo_cheese(self):
        t, me, opp = self.setup_board(0)
        b = t.zone(P1, 'bench')[0]
        for p in (me, b):
            p.set_attribute(AttrID.HP, max_hp(t, p) - 40)
        t.energy(me, D)
        card = t.put('SWSH4.MoomooCheese_156', P1, 'hand')
        t.picks = lambda cards, count, prompt, shown: list(cards)[:count]
        await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 10)
        self.assertEqual(max_hp(t, b) - t.hp(b), 40, 'no Energy: not healed')

    async def test_hyper_potion(self):
        t, me, opp = self.setup_board(0)
        me.set_attribute(AttrID.HP, max_hp(t, me) - 130)
        es = t.energy(me, D, 3)
        card = t.put('SWSH1.HyperPotion_166', P1, 'hand')
        await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 10)
        self.assertEqual(len(t.attached(me)), 1)

    async def test_sweet_honey(self):
        t, me, opp = self.setup_board(0)
        me.set_attribute(AttrID.HP, max_hp(t, me) - 100)
        from unittest.mock import patch
        from spirit.game.session.effects import EffectContext

        async def two(ctx, *a, **k):
            return 2
        card = t.put('SWSH10.SweetHoney_153', P1, 'hand')
        with patch.object(EffectContext, 'flip_until_tails', two):
            await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 20)

    async def test_fighting_au_lait(self):
        t, me, opp = self.setup_board(0)
        me.set_attribute(AttrID.HP, max_hp(t, me) - 70)
        card = t.put('SV2.FightingAuLait_181', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'), 'same Prize count')
        t.set_prizes(P2, 4)
        await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 10)

    async def test_lucky_ice_pop(self):
        for heads in (True, False):
            t, me, opp = self.setup_board(0)
            me.set_attribute(AttrID.HP, max_hp(t, me) - 30)
            t.heads = heads
            card = t.put('SWSH7.LuckyIcePop_150', P1, 'hand')
            await t.play(card)
            self.assertEqual(max_hp(t, me) - t.hp(me), 10)
            self.assertEqual(card in t.zone(P1, 'hand'), heads)

    async def test_giacomo(self):
        t, me, opp = self.setup_board(0)
        ob = t.zone(P2, 'bench')[0]
        s1, s2 = named('Recycle Energy'), named('Recycle Energy')
        a = t.attach(s1, opp)
        b = t.attach(s2, ob)
        basic = t.energy(opp, D)
        card = t.put('SV085.Giacomo_138', P1, 'hand')
        await t.play(card)
        self.assertNotIn(a, t.attached(opp))
        self.assertNotIn(b, t.attached(ob))
        self.assertIn(basic, t.attached(opp))

    async def test_marnies_pride(self):
        t, me, opp = self.setup_board(0)
        b = t.zone(P1, 'bench')[0]
        e = t.put(t.basic_energy(D), P1, 'discard')
        card = t.put('SWSH9.MarniesPride_145', P1, 'hand')
        await t.play(card)
        self.assertIn(e, t.attached(b))

    async def test_team_aqua_admin(self):
        aqua = find(name=lambda n: n.startswith('Team Aqua'), quiet=False)
        t = Table(self)
        me = t.put(aqua, P1, 'active')
        t.put(self.filler, P2, 'active')
        e = t.put(t.basic_energy(W), P1, 'discard')
        card = t.put('TATM.TeamAquaAdmin_25', P1, 'hand')
        await t.play(card)
        self.assertIn(e, t.attached(me))

    async def test_expedition_uniform(self):
        t, me, opp = self.setup_board(0)
        bottom = t.deck(P1, ['SWSH1.QuickBall_216'] * 3, top=False)
        card = t.put('SWSH6.ExpeditionUniform_137', P1, 'hand')
        await t.play(card)
        self.assertEqual(set(t.zone(P1, 'deck')[-3:]), set(bottom))

    async def test_tool_box(self):
        t, me, opp = self.setup_board(0)
        tool = t.deck(P1, ['SWSH1.AirBalloon_156'])[0]
        card = t.put('SWSH11.ToolBox_168', P1, 'hand')
        await t.play(card)
        self.assertIn(tool, t.zone(P1, 'hand'))

    async def test_egg_incubator(self):
        for heads in (True, False):
            t, me, opp = self.setup_board(0, bench=0)
            t.heads = heads
            mon = t.deck(P1, [self.filler])[0]
            card = t.put('PGO.EggIncubator_66', P1, 'hand')
            await t.play(card)
            self.assertEqual(mon in t.zone(P1, 'bench'), heads)
            if not heads:
                self.assertIs(t.zone(P1, 'deck')[0], card, 'bottom of the deck')

    async def test_drone_rotom_and_hand_scope(self):
        for ref in ('SWSH4.DroneRotom_151', 'XY4.HandScope_96'):
            t, me, opp = self.setup_board(0)
            card = t.put(ref, P1, 'hand')
            await t.play(card)
            self.assertIn(card, t.zone(P1, 'discard'))

    async def test_hooligans(self):
        t, me, opp = self.setup_board(0)
        for _ in range(5):
            t.put(self.item, P2, 'hand')
        card = t.put('BW5.HooligansJimCas_95', P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)

    async def test_digging_duo(self):
        for heads, n in ((True, 8), (False, 3)):
            t, me, opp = self.setup_board(0)
            card = t.put('CZ.DiggingDuo_126', P1, 'hand')
            t.heads = heads
            seen = []
            t.picks = lambda cards, count, prompt, shown: seen.append(len(cards)) or list(cards)[:count]
            await t.play(card)
            self.assertEqual(seen, [n])
            self.assertEqual(len(t.zone(P1, 'hand')), 1)


class StadiumsAndMore(Base):
    setup_board = DrawSupporters.setup_board

    async def test_blizzard_town(self):
        t, a, d = board(self, big(C), None)
        t.stadium('SM11.BlizzardTown_187', P2)
        a.set_attribute(AttrID.HP, 40)
        self.assertIsNone(t.attack_offer(a, t.atk.title))
        a.set_attribute(AttrID.HP, 50)
        self.assertIsNotNone(t.attack_offer(a, t.atk.title))

    async def test_dyna_tree_hill(self):
        t, me, opp = self.setup_board(0)
        me.set_attribute(AttrID.HP, max_hp(t, me) - 30)
        t.stadium('SWSH6.DynaTreeHill_135', P2)
        card = t.put('SWSH7.LuckyIcePop_150', P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 30)

    async def test_circhester_bath(self):
        b, w = await self.delta(None, big(C), plain(C), stadium='SWSH4.CirchesterBath_150')
        self.assertEqual(b - w, 20)

    async def test_tower_of_waters(self):
        rs = find(pred=lambda d: 'Rapid Strike' in subs(d), quiet=False)
        t, a, d = board(self, None, rs, neutral_def=False, hp=None)
        base = t.retreat(d)
        t.stadium('SWSH5.TowerofWaters_138', P1)
        self.assertEqual(t.retreat(d), max(0, base - 2))

    async def test_skaters_park(self):
        t, me, opp = self.setup_board(0)
        e = t.energy(me, D, 3)
        t.stadium('SWSH8.SkatersPark_242', P1)
        cost = t.retreat(me)
        self.assertGreater(cost, 0)
        entry = t.offers(me, 'RetreatPokemon') or [x for x in t.actions() if 'Retreat' in x['selectableAction']['description']]
        self.assertTrue(entry)
        bench = t.zone(P1, 'bench')[0]
        await t.do(entry[0], targets=[bench.entity_id] + [x.entity_id for x in e[:cost]])
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(x in hand for x in e), cost, 'discarded Energy goes to the hand')

    async def test_community_center(self):
        t, me, opp = self.setup_board(1)
        me.set_attribute(AttrID.HP, max_hp(t, me) - 30)
        st = t.stadium('SV06.CommunityCenter_146', P2)
        self.assertFalse(t.can(st, None))
        sup = t.put('SV1.Youngster_198', P1, 'hand')
        await t.play(sup)
        entry = t.offers(st)
        self.assertTrue(entry, 'offered after a Supporter')
        await t.do(entry[0])
        self.assertEqual(max_hp(t, me) - t.hp(me), 20)
        self.assertFalse(t.offers(st), 'once per turn')

    async def test_tower_of_darkness(self):
        t, me, opp = self.setup_board(0)
        st = t.stadium('SWSH5.TowerofDarkness_137', P2)
        self.assertFalse(t.offers(st), 'needs a Single Strike card')
        ss = t.put('SWSH5.TowerofDarkness_137', P1, 'hand')    # Single Strike Stadium card
        entry = t.offers(st)
        self.assertTrue(entry)
        await t.do(entry[0])
        self.assertIn(ss, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    async def test_big_parasol(self):
        para, att = with_attack(r"^(?!.*\b(if|flip|choose|shuffle|discard|itself|bench)\b).*(your opponent's active pokémon|the defending pokémon) is now paralyzed")
        for active in (True, False):
            t, a, d = board(self, para, None, pay_attack=False)
            pay(t, a, att)
            holder = d if active else t.put(self.filler, P2, 'bench')
            t.attach('SWSH3.BigParasol_157', holder)
            await t.attack(a, att.title)
            self.assertEqual('Paralyzed' in t.conditions(d), not active)

    async def test_magma_pointer(self):
        magma = find(name=lambda n: n.startswith('Team Magma'), quiet=False)
        t, a, d = board(self, magma, None, pay_attack=False)
        t.energy(a, F)
        await equip(t, 'TATM.MagmaPointer_24', a)
        entry = t.attack_offer(a, 'Magma Pointer')
        self.assertIsNotNone(entry)
        await t.attack(a, 'Magma Pointer')
        self.assertEqual(400 - t.hp(d), 20)
        t, a, d = board(self, None, None, pay_attack=False)
        t.energy(a, F)
        await equip(t, 'TATM.MagmaPointer_24', a)
        self.assertIsNone(t.attack_offer(a, 'Magma Pointer'), 'not Team Magma')

    async def test_aqua_diffuser(self):
        aqua = find(name=lambda n: n.startswith("Team Aqua's"), quiet=False)
        t, a, d = board(self, aqua, None, pay_attack=False)
        t.energy(a, W)
        await equip(t, 'TATM.AquaDiffuser_23', a)
        self.assertIsNotNone(t.attack_offer(a, 'Aqua Diffuser'))
        t, a, d = board(self, None, None, pay_attack=False)
        t.energy(a, W)
        await equip(t, 'TATM.AquaDiffuser_23', a)
        self.assertIsNone(t.attack_offer(a, 'Aqua Diffuser'))

    async def test_normalium_z_tackle(self):
        tackle = find(quiet=False, pred=lambda d: any(x.title == 'Tackle' for x in d.abilities))
        t, a, d = board(self, tackle, None, pay_attack=False)
        t.energy(a, D, 4)
        await equip(t, 'SM11.NormaliumZTackle_203', a)
        self.assertIsNotNone(t.attack_offer(a, 'Barreling Blitz-GX'))
        t, a, d = board(self, None, None, pay_attack=False)
        t.energy(a, D, 4)
        await equip(t, 'SM11.NormaliumZTackle_203', a)
        self.assertIsNone(t.attack_offer(a, 'Barreling Blitz-GX'), 'no Tackle attack')

    async def test_shrine_of_memories(self):
        from tests.untested_trainer_kit import _defs, _attr
        from spirit.game.data_utils import PokemonCardDef
        # a Stage 1 whose Basic has a different attack
        pair = None
        for d in _defs():
            if isinstance(d, PokemonCardDef) and stage_of(d) == S1 and plain_attack(d):
                ev = _attr(d, AttrID.EVOLVES_FROM)
                name = ev.get('id') if isinstance(ev, dict) else None
                base = next((b for b in _defs() if isinstance(b, PokemonCardDef)
                             and b.name == name and stage_of(b) == BASIC and plain_attack(b)
                             and plain_attack(b).title != plain_attack(d).title), None)
                if base is not None:
                    pair = (base, d)
                    break
        base, evo = pair
        for owner in (P1, P2):
            t = Table(self)
            b = t.put(base, P1, 'active')
            t.put(self.filler, P2, 'active')
            pay(t, b, plain_attack(base))
            card = t.put(evo, P1, 'hand')
            await t.play(card, targets=[b.entity_id])
            mon = t.active(P1)
            self.assertIs(mon, card)
            title = plain_attack(base).title
            self.assertIsNone(t.attack_offer(mon, title))
            t.stadium('XY5.ShrineofMemories_139', owner)
            await t._run(lambda: t.session._refresh_dynamic_attacks(P1))
            self.assertIsNotNone(t.attack_offer(mon, title), owner)

    async def test_double_aqua_energy(self):
        aqua = find(name=lambda n: n.startswith('Team Aqua'), quiet=False)
        t = Table(self)
        me = t.put(aqua, P1, 'active')
        t.put(self.filler, P2, 'active')
        other = t.put(self.filler, P1, 'bench')
        e = t.put('TATM.DoubleAquaEnergy_33', P1, 'hand')
        self.assertNotIn(other.entity_id, t.targets(e, 'DefaultEnergyPlayAbility') or set())
        await t.play(e, targets=[me.entity_id])
        self.assertIn(e, t.attached(me))
        from spirit.game.session.legal_actions import energy_provided_count
        self.assertEqual(energy_provided_count(e, t.board), 2, 'WW on a Team Aqua Pokemon')
        await end_turn(t)
        self.assertNotIn(e, t.attached(me), 'discarded at the end of the turn')


class MoreTrainers(Base):
    setup_board = DrawSupporters.setup_board

    async def test_agatha(self):
        t, me, opp = self.setup_board(0)
        me.set_attribute(AttrID.HP, max_hp(t, me) - 50)
        card = t.put('SWSH6.Agatha_129', P1, 'hand')
        from unittest.mock import patch
        from spirit.game.session.effects import EffectContext
        orig = EffectContext.move_damage_counters
        await t.play(card)
        self.assertEqual(max_hp(t, me) - t.hp(me), 20)
        self.assertEqual(max_hp(t, opp) - t.hp(opp), 30)

    async def test_cross_switcher(self):
        t, me, opp = self.setup_board(0)
        a = t.put('SWSH8.CrossSwitcher_230', P1, 'hand')
        self.assertFalse(t.can(a, 'UseTrainerCard'), 'needs 2')
        b = t.put('SWSH8.CrossSwitcher_230', P1, 'hand')
        ob = t.zone(P2, 'bench')[0]
        mine = t.zone(P1, 'bench')[0]
        t.pokemon = lambda cands, prompt: ob if ob in cands else mine
        await t.play(a)
        self.assertIs(t.active(P2), ob)
        self.assertIs(t.active(P1), mine)
        self.assertIn(a, t.zone(P1, 'discard'))
        self.assertIn(b, t.zone(P1, 'discard'))

    async def test_karens_conviction(self):
        ss = find(pred=lambda d: 'Single Strike' in subs(d))
        for taken in (0, 3):
            t, a, d = board(self, ss, None)
            t.set_prizes(P2, 6 - taken)
            card = t.put('SWSH6.KarensConviction_144', P1, 'hand')
            base = t.atk.damage
            if t.can(card, 'UseTrainerCard'):
                await t.play(card)
            await t.attack(a, t.atk.title)
            self.assertEqual(400 - t.hp(d), base + 20 * taken)
        t, a, d = board(self, None, None)
        t.set_prizes(P2, 3)
        await t.play(t.put('SWSH6.KarensConviction_144', P1, 'hand'))
        await t.attack(a, t.atk.title)
        self.assertEqual(400 - t.hp(d), t.atk.damage, 'not Single Strike')

    async def test_lure_module(self):
        t, me, opp = self.setup_board(0)
        mine = t.deck(P1, [self.filler])[0]
        theirs = t.deck(P2, [self.filler])[0]
        card = t.put('PGO.LureModule_67', P1, 'hand')
        await t.play(card)
        self.assertIn(mine, t.zone(P1, 'hand'))
        self.assertIn(theirs, t.zone(P2, 'hand'))

    async def test_colress_machine(self):
        plasma = find(pred=lambda d: 'Team Plasma' in subs(d), nosub=('EX',), quiet=False)
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        pl = t.put(plasma, P1, 'bench')
        t.put(self.filler, P2, 'active')
        pe = t.deck(P1, [named('Plasma Energy')])[0]
        card = t.put('BW8.ColressMachine_119', P1, 'hand')
        await t.play(card)
        self.assertIn(pe, t.attached(pl))

    async def test_letter_of_encouragement(self):
        t, me, opp = self.setup_board(0)
        card = t.put('SV3.LetterofEncouragement_189', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.state.kos_suffered_last_turn = {P1: [{"entity_id": "x"}]}
        t.state.kos_by_attack_last_turn = {P1: [{"entity_id": "x"}]}
        es = [t.put(t.basic_energy(k), P1, 'deck') for k in (R, W, G, L)]
        await t.play(card)
        self.assertEqual(sum(e in t.zone(P1, 'hand') for e in es), 3)

    async def test_looker_whistle_and_nemona_backpack(self):
        t, me, opp = self.setup_board(0)
        looker = [t.put(card_index('Looker'), P1, 'deck') for _ in range(3)]
        card = t.put('SM5.LookerWhistle_127', P1, 'hand')
        await t.play(card)
        self.assertEqual(sum(c in t.zone(P1, 'hand') for c in looker), 2)
        t, me, opp = self.setup_board(0)
        nem = [t.put(card_index('Nemona'), P1, 'discard') for _ in range(3)]
        card = t.put('SV045.NemonasBackpack_83', P1, 'hand')
        await t.play(card)
        self.assertEqual(sum(c in t.zone(P1, 'hand') for c in nem), 2)

    async def test_root_fossil_lileep(self):
        t, me, opp = self.setup_board(0, bench=0)
        lileep = t.deck(P1, [card_index('Lileep')], top=False)[0]
        card = t.put('BW10.RootFossilLileep_87', P1, 'hand')
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if c is lileep][:count]
        await t.play(card)
        self.assertIn(lileep, t.zone(P1, 'bench'))

    async def test_here_comes_team_rocket(self):
        t, me, opp = self.setup_board(0)
        card = t.put('XY12.HereComesTeamRocket_113', P1, 'hand')
        await t.play(card)
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_sabrina_brycen_plain(self):
        t, me, opp = self.setup_board(0)
        es = [t.put(t.basic_energy(k), P1, 'deck') for k in (R, W, G)]
        card = t.put('Promo_SM.SabrinaBrycen_246', P1, 'hand')
        t.yes = False
        await t.play(card)
        self.assertEqual(sum(e in t.zone(P1, 'hand') for e in es), 2)

    async def test_misty_lorelei_plain(self):
        t, me, opp = self.setup_board(0)
        es = [t.put(t.basic_energy(W), P1, 'deck') for _ in range(4)] + [t.put(t.basic_energy(R), P1, 'deck')]
        card = t.put('SM12.MistyLorelei_199', P1, 'hand')
        t.yes = False
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(e in hand for e in es[:4]), 3)
        self.assertNotIn(es[4], hand)


if __name__ == '__main__':
    unittest.main()
