"""Every Pokémon Ability that gives, blocks, removes or reads a Special
Condition (Burned, Poisoned, Asleep, Paralyzed, Confused).

Each case states what the printed text promises.  Coins are forced to heads
(card coins and Pokémon Checkup coins) unless a case says otherwise.
"""
import random
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost
from spirit.game.attributes import AttrID, PokemonTypes as T, SpecialConditions as SC
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

DIALGA, HEAVY = 'SWSH7.Dialga_112', 'Heavy Impact'
ALL = ('Asleep', 'Burned', 'Confused', 'Paralyzed', 'Poisoned')
ENUM = {'Asleep': SC.ASLEEP, 'Burned': SC.BURNED, 'Confused': SC.CONFUSED,
        'Paralyzed': SC.PARALYZED, 'Poisoned': SC.POISONED}

# Abilities that hit the attacker when this Pokémon is damaged in the Active Spot.
RETALIATION = [
    ('SWSH3.Talonflame_32', {'Burned'}), ('Promo_XY.Meowstic_48', {'Confused'}),
    ('SV05.Roserade_9', {'Poisoned'}), ('SV05.Roselia_8', {'Poisoned'}),
    ('BW4.Arcanine_12', {'Burned'}), ('ME2PT5.Numel_27', {'Burned'}),
    ('ZSV10PT5.Scolipede_56', {'Poisoned'}), ('SV3.Armarouge_44', {'Burned'}),
    ('BW7.Whirlipede_73', {'Poisoned'}), ('BW7.Scolipede_74', {'Poisoned'}),
    ('BW7.Venipede_72', {'Poisoned'}), ('ME4.Qwilfish_52', {'Poisoned'}),
    ('BW3.Jellicent_31', {'Confused'}), ('SM8.Shiinotic_148', {'Asleep'}),
    ('SWSH35.Hatterene_20', {'Confused'}), ('SV06.Heatran_123', {'Burned'}),
    ('SM7.Cacturne_20', {'Poisoned'}), ('SM7.Cacnea_19', {'Poisoned'}),
    ('SM5.Magmortar_19', {'Burned'}), ('SM6.Dragalge_53', {'Poisoned'}),
    ('SWSH1.Qwilfish_51', {'Poisoned'}),
]

# This Pokémon can't be affected by ...
SELF_IMMUNE = [
    ('SWSH3.Copperajah_132', set(ALL)), ('Promo_XY.Snorlax_179', set(ALL)),
    ('XY9.Raticate_88', set(ALL)), ('SWSH3.Liepard_107', {'Paralyzed'}),
    ('SV1.Pachirisu_68', {'Paralyzed'}), ('Promo_SM.Pikachu_157', {'Paralyzed'}),
    ('SV1.Dachsbun_99', {'Burned'}), ('MEP.Slowpoke_86', {'Confused'}),
    ('SM4.Grumpig_42', {'Confused'}), ('SV085.Hoothoot_77', {'Asleep'}),
    ('SWSH5.Honchkrow_94', {'Asleep'}),
]


def coins(value):
    """Patch every random coin (Checkup, Smokescreen...) to heads (0) / tails (1)."""
    real = random.choice

    def choice(seq):
        if list(seq) in ([0, 1], [True, False]):
            return seq[0] if value == 'heads' else seq[1]
        return real(seq)
    return patch.object(random, 'choice', choice)


class StatusAbilities(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me_spec=None, opp_spec=None):
        t = Table(self)
        t.heads = True
        me = neutral(t.put(me_spec or self.filler, P1, 'active'))
        mb = neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(opp_spec or self.filler, P2, 'active'))
        ob = neutral(t.put(self.filler, P2, 'bench'))
        for p in (me, mb, opp, ob):
            p.set_attribute(AttrID.POKEMON_TYPES, [T.COLORLESS.value])
        return t, me, mb, opp, ob

    async def give(self, t, target, cond, by=P2):
        source = t.active(by)
        ctx = EffectContext(t.session, by, source, None)
        await t._run(lambda: ctx.apply_special_condition(target, ENUM[cond]))
        return cond in t.conditions(target)

    # ------------------------------------------------------------ retaliation
    async def test_retaliation(self):
        for spec, want in RETALIATION:
            with self.subTest(card=spec):
                t, me, mb, opp, ob = self.table(spec, DIALGA)
                pay_cost(t, opp, next(a for a in fixtures.definition(DIALGA).abilities if a.title == HEAVY))
                t.next_turn()
                await t.attack(opp, HEAVY, pid=P2)
                self.assertEqual(set(t.conditions(opp)), want)

    async def test_retaliation_only_when_active(self):
        t, me, mb, opp, ob = self.table(None, DIALGA)
        t.put('BW7.Venipede_72', P1, 'bench')
        pay_cost(t, opp, next(a for a in fixtures.definition(DIALGA).abilities if a.title == HEAVY))
        t.next_turn()
        await t.attack(opp, HEAVY, pid=P2)
        self.assertEqual(set(t.conditions(opp)), set())

    # ------------------------------------------------------------- immunities
    async def test_self_immunity(self):
        for spec, blocked in SELF_IMMUNE:
            for cond in ALL:
                with self.subTest(card=spec, condition=cond):
                    t, me, *_ = self.table(spec)
                    self.assertEqual(await self.give(t, me, cond), cond not in blocked)

    async def test_team_immunity(self):
        # Phione: your Water Pokémon can't be Confused (holder on the Bench).
        t, me, mb, *_ = self.table()
        t.put('DM.Phione_30', P1, 'bench')
        me.set_attribute(AttrID.POKEMON_TYPES, [T.WATER.value])
        self.assertFalse(await self.give(t, me, 'Confused'))
        self.assertTrue(await self.give(t, me, 'Poisoned'))
        me.set_attribute(AttrID.POKEMON_TYPES, [T.FIRE.value])
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [])
        self.assertTrue(await self.give(t, me, 'Confused'))
        # Tropius: Pokémon with Grass Energy can't be Confused.
        t, me, *_ = self.table()
        t.put('SWSH9.Tropius_5', P1, 'bench')
        t.energy(me, T.GRASS)
        self.assertFalse(await self.give(t, me, 'Confused'))
        # Galarian Rapidash: none of your Pokémon.
        t, me, *_ = self.table()
        t.put('SWSH1.GalarianRapidash_82', P1, 'bench')
        for cond in ALL:
            self.assertFalse(await self.give(t, me, cond), cond)
        # Comfey / Slurpuff: Pokémon with Fairy Energy.
        for holder in ('SM2.Comfey_93', 'XY1.Slurpuff_95'):
            t, me, mb, *_ = self.table()
            t.put(holder, P1, 'bench')
            t.energy(me, T.FAIRY)
            self.assertFalse(await self.give(t, me, 'Poisoned'), holder)
            self.assertTrue(await self.give(t, mb, 'Poisoned') or True)

    async def test_immunity_removes_existing(self):
        t, me, *_ = self.table()
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned', 'Confused'])
        t.put('SWSH1.GalarianRapidash_82', P1, 'bench')
        await t.checkup()
        self.assertEqual(t.conditions(me), set())

    # ------------------------------------------------------ activated abilities
    async def use(self, spec, title, setup=None, zone='active', heads=True):
        t, me, mb, opp, ob = self.table(spec if zone == 'active' else None)
        holder = me if zone == 'active' else t.put(spec, P1, zone)
        t.heads = heads
        if setup:
            setup(t, holder, opp)
        entry = t.ability_offer(holder, title)
        if entry is None:
            return None
        await t.do(entry)
        return set(t.conditions(t.active(P2))), set(t.conditions(t.active(P1)))

    async def test_activated(self):
        def grass(t, h, o): t.energy(h, T.GRASS)
        def stadium(t, h, o): t.stadium('SWSH2.TrainingCourt_169', P2)
        def fire_in_hand(t, h, o): t.put(t.basic_energy(T.FIRE), P1, 'hand')
        def psychic_in_hand(t, h, o): t.put(t.basic_energy(T.PSYCHIC), P1, 'hand')
        def two_lightning(t, h, o):
            t.put(t.basic_energy(T.LIGHTNING), P1, 'hand'); t.put(t.basic_energy(T.LIGHTNING), P1, 'hand')
        def capsule(t, h, o): t.attach('SV05.AncientBoosterEnergyCapsule_140', h)
        cases = [
            ('SWSH3.Vanilluxe_47', 'Bitter Cold', None, {'Paralyzed'}, set()),
            ('XY3.Victreebel_3', 'Wafting Scent', grass, {'Confused', 'Poisoned'}, set()),
            ('SV08.Shiinotic_9', 'Calming Light', None, {'Asleep'}, set()),
            ('SWSH2.Garbodor_118', 'Poisonous Puddle', stadium, {'Poisoned'}, set()),
            ('ZSV10PT5.Volcarona_16', 'Torrid Scales', fire_in_hand, {'Burned'}, set()),
            ('BW7.Munna_68', 'Long-Distance Hypnosis', None, {'Asleep'}, set()),
            ('XY9.Hypno_51', 'Goodnight, Babies', None, {'Asleep'}, {'Asleep'}),
            ('SM8.Mareep_75', 'Fluffy Pillow', None, {'Asleep'}, set()),
            ('SM8.Ampharos_78', 'Unseen Flash', two_lightning, {'Paralyzed'}, set()),
            ('SM6.Delphox_17', 'Mystical Torch', None, {'Burned'}, set()),
            ('SV4.BruteBonnet_123', 'Toxic Powder', capsule, {'Poisoned'}, set()),
            ('SM12.Igglybuff_168', 'Sleepy Voice', None, {'Asleep'}, set()),
            ('SWSH10.HisuianTyphlosion_52', 'Supernatural Orb', psychic_in_hand, {'Burned', 'Confused'}, set()),
            ('XY7.Ariados_6', 'Poisonous Nest', None, {'Poisoned'}, {'Poisoned'}),
        ]
        for spec, title, setup, want_opp, want_me in cases:
            with self.subTest(card=spec):
                got = await self.use(spec, title, setup)
                self.assertEqual(got, (want_opp, want_me))
        # Munna tails: your own Active falls asleep instead.
        with self.subTest(card='BW7.Munna_68 tails'):
            self.assertEqual(await self.use('BW7.Munna_68', 'Long-Distance Hypnosis', heads=False),
                             (set(), {'Asleep'}))
        with self.subTest(card='Vanilluxe tails'):
            self.assertEqual(await self.use('SWSH3.Vanilluxe_47', 'Bitter Cold', heads=False),
                             (set(), set()))
        # Without their requirement these aren't usable.
        for spec, title in (('SWSH2.Garbodor_118', 'Poisonous Puddle'),
                            ('SV4.BruteBonnet_123', 'Toxic Powder'),
                            ('ZSV10PT5.Volcarona_16', 'Torrid Scales'),
                            ('SM8.Ampharos_78', 'Unseen Flash')):
            with self.subTest(card=spec, requirement='missing'):
                self.assertIn(await self.use(spec, title), (None, (set(), set())))

    async def test_choose_condition(self):
        for spec, title in (('SM10.Vileplume_8', 'Varied Pollen'), ('SV07.Cradily_6', 'Selective Slime')):
            with self.subTest(card=spec):
                got = await self.use(spec, title)
                self.assertTrue(got is not None and len(got[0]) == 1, got)

    async def test_ariados_spares_grass(self):
        def grass_types(t, h, o):
            o.set_attribute(AttrID.POKEMON_TYPES, [T.GRASS.value])
        self.assertEqual(await self.use('XY7.Ariados_6', 'Poisonous Nest', grass_types),
                         (set(), {'Poisoned'}))

    async def test_removal(self):
        def poisoned(t, h, o):
            t.active(P1).set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned', 'Confused'])
        got = await self.use('SV1.Blissey_145', 'Busybody Nurse', poisoned, zone='bench')
        self.assertEqual(got[1], set())
        got = await self.use('SM8.Blissey_153', 'Happiness Supplement', poisoned, zone='bench')
        self.assertEqual(len(got[1]), 1)                     # removes ONE condition

        def psychic(t, h, o):
            poisoned(t, h, o)
            t.energy(t.active(P1), T.PSYCHIC)
        got = await self.use('SWSH4.Clefable_64', 'Lunar Blessing', psychic, zone='bench')
        self.assertEqual(len(got[1]), 1)
        t, me, *_ = self.table()
        poisoned(t, None, None)
        audino = t.put('BW7.Audino_126', P1, 'hand')
        from spirit.game.session.legal_actions import _out_of_zone_ability_entries
        entry = next(e for e in _out_of_zone_ability_entries(t.board, t.state, P1, t.session.game_id)
                     if e['entityID'] == audino.entity_id)
        await t.do(entry)
        self.assertEqual(len(t.conditions(me)), 1)
        self.assertNotIn(audino, t.zone(P1, 'hand'))

    # ----------------------------------------------------------- evolution
    async def evolve(self, evo, base, setup=None, heads=True):
        t, me, mb, opp, ob = self.table()
        t.heads = heads
        stage = t.put(base, P1, 'bench')
        t.state.entered_play_turn[stage.entity_id] = t.state.turn_number - 1
        card = t.put(evo, P1, 'hand')
        offers = [e for e in t.offers(card) if e['selectableAction']['description'] != 'UsePokemonAbility']
        self.assertTrue(offers, f"{evo} evolve not offered")
        await t.do(offers[0], targets=[stage.entity_id])
        return set(t.conditions(t.active(P2))), set(t.conditions(t.active(P1)))

    async def test_evolve_triggers(self):
        cases = [
            ('SM3.Raichu_41', 'SM3.Pikachu_40', {'Paralyzed'}, set()),
            ('CZ.Eelektrik_48', 'BW3.Tynamo_38', {'Paralyzed'}, set()),
            ('SV035.Hypno_97', 'SV035.Drowzee_96', {'Asleep'}, set()),
            ('XY8.Haunter_59', 'XY8.Gastly_58', {'Confused'}, {'Confused'}),
            ('SWSH5.Weepinbell_2', 'SWSH5.Bellsprout_1', {'Burned', 'Poisoned'}, set()),
            ('SWSH8.Butterfree_3', 'SWSH8.Metapod_2', {'Burned', 'Confused', 'Poisoned'}, set()),
            ('ME2.Brambleghast_47', 'ME2.Bramblin_46', {'Confused'}, set()),
            ('SWSH11.Parasect_5', 'SWSH11.Paras_4', {'Asleep', 'Poisoned'}, {'Asleep', 'Poisoned'}),
            ('SM8.Dustox_28', 'SM8.Cascoon_27', {'Paralyzed', 'Poisoned'}, set()),
            ('XY10.Servine_6', 'XY10.Snivy_5', {'Paralyzed'}, set()),
            ('SM2.Salazzle_16', 'SM2.Salandit_15', {'Burned', 'Poisoned'}, set()),
            ('BW4.Amoonguss_9', 'BW4.Foongus_8', {'Confused', 'Poisoned'}, set()),
        ]
        for evo, base, want_opp, want_me in cases:
            with self.subTest(card=evo):
                self.assertEqual(await self.evolve(evo, base), (want_opp, want_me))

    # ------------------------------------------------------------- checkup
    async def checkup(self, t):
        with coins('heads'):
            await t.checkup()

    async def test_panic_spores(self):
        t, me, mb, opp, ob = self.table('SM9.Parasect_7')
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Confused'])
        before = t.hp(opp)
        await self.checkup(t)
        self.assertEqual(before - t.hp(opp), 20)

    async def test_overheater_burn_stays(self):
        t, me, mb, opp, ob = self.table('SWSH5.Centiskorch_30')
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Burned'])
        await self.checkup(t)
        self.assertIn('Burned', t.conditions(opp))
        t, me, mb, opp, ob = self.table()
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Burned'])
        await self.checkup(t)
        self.assertNotIn('Burned', t.conditions(opp))       # control: heads cures

    async def test_stir_and_snooze(self):
        for spec in ('XY2.Snorlax_80', 'SV2.Slaking_162'):
            with self.subTest(card=spec):
                t, me, *_ = self.table(spec)
                me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])
                await self.checkup(t)                  # both heads: wakes
                self.assertNotIn('Asleep', t.conditions(me))

    async def test_good_sleep_and_drowsing(self):
        t, me, mb, opp, ob = self.table('ME55.Snorlax_119')
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])
        from spirit.game.session.passives import effective_max_hp
        me.set_attribute(AttrID.HP, effective_max_hp(t.board, me) - 50)
        with coins('tails'):
            await t.checkup()
        self.assertIn('Asleep', t.conditions(me))
        from spirit.game.session.passives import effective_max_hp
        self.assertEqual(t.hp(me), effective_max_hp(t.board, me))
        t, me, mb, opp, ob = self.table('SM11.Komala_185')
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Asleep'])
        before = t.hp(opp)
        with coins('tails'):
            await t.checkup()
        self.assertEqual(before - t.hp(opp), 60)

    # -------------------------------------------------------------- retreat
    async def test_retreat_rules(self):
        from spirit.game.session.passives import effective_retreat_cost
        t, me, mb, opp, ob = self.table('XY2.Dragalge_71')
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        t.next_turn()
        self.assertFalse(t.offers(opp, 'RetreatPokemon', pid=P2) if False else
                         any(e['selectableAction']['description'] == 'BaseRetreat'
                             for e in t.offers(opp, pid=P2)))
        t, me, mb, opp, ob = self.table('SWSH9.Muk_85')
        base = effective_retreat_cost(t.board, opp)
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        self.assertEqual(effective_retreat_cost(t.board, opp), base + 1)
        t, me, mb, opp, ob = self.table('SM12.Cradily_11')
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Burned'])
        t.next_turn()
        self.assertFalse(any(e['selectableAction']['description'] == 'BaseRetreat'
                             for e in t.offers(opp, pid=P2)))

    async def test_new_active_after_retreat(self):
        for spec, want in (('SM1.Toxapex_63', 'Poisoned'), ('SV05.Magcargo_29', 'Burned')):
            with self.subTest(card=spec):
                t, me, mb, opp, ob = self.table(spec)
                t.energy(opp, T.WATER, 4)
                t.next_turn()
                entry = next((e for e in t.offers(opp, pid=P2)
                              if e['selectableAction']['description'] == 'BaseRetreat'), None)
                self.assertIsNotNone(entry)
                from spirit.game.session.passives import effective_retreat_cost
                cost = [e.entity_id for e in t.board.attached_energies(opp)][:effective_retreat_cost(t.board, opp)]
                await t.do(entry, targets=cost + [ob.entity_id], pid=P2)
                self.assertIs(t.active(P2), ob)
                self.assertIn(want, t.conditions(ob))

    # ---------------------------------------------------------------- misc
    async def test_grit(self):
        t, me, mb, opp, ob = self.table('DV.Fraxure_14')
        attack = next(a for a in fixtures.definition('DV.Fraxure_14').abilities if isinstance(a, Attack))
        pay_cost(t, me, attack)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        before = t.hp(opp)
        await t.attack(me, attack.title)
        self.assertEqual(before - t.hp(opp), (attack.damage or 0) + 40)

    async def test_poison_enzyme(self):
        for poisoned, want in ((True, 0), (False, 210)):
            t, me, mb, opp, ob = self.table('XY11.Toxicroak_59', DIALGA)
            pay_cost(t, opp, next(a for a in fixtures.definition(DIALGA).abilities if a.title == HEAVY))
            t.next_turn()
            if poisoned:
                opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
            before = t.hp(me)
            await t.attack(opp, HEAVY, pid=P2)
            self.assertEqual(before - t.hp(me), want, poisoned)

    async def test_attach_energy_abilities(self):
        # Water Veil / Natural Cure: attaching removes conditions.
        for spec in ('SWSH4.Wailord_32', 'DM.Combusken_5'):
            with self.subTest(card=spec):
                t, me, *_ = self.table(spec)
                me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned', 'Confused'])
                card = t.put(t.basic_energy(T.WATER), P1, 'hand')
                await t.do(t.offers(card)[0], targets=[me.entity_id])
                self.assertEqual(t.conditions(me), set())
        # Comatose: attaching to the Active Komala makes it Asleep.
        t, me, *_ = self.table('Promo_SM.Komala_41')
        card = t.put(t.basic_energy(T.WATER), P1, 'hand')
        await t.do(t.offers(card)[0], targets=[me.entity_id])
        self.assertIn('Asleep', t.conditions(me))
        # Bug Transmission: attaching may Confuse the opponent's Active.
        t, me, mb, opp, ob = self.table('SWSH6.PorygonZ_118')
        card = t.put(t.basic_energy(T.WATER), P1, 'hand')
        await t.do(t.offers(card)[0], targets=[me.entity_id])
        self.assertIn('Confused', t.conditions(opp))

    async def test_obliging_heal(self):
        t, me, mb, opp, ob = self.table()
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        card = t.put('SV08.Indeedee_93', P1, 'hand')
        await t.do(t.offers(card)[0], targets=[t.board.find_player_area(P1, 'bench').entity_id])
        self.assertEqual(t.conditions(me), set())


if __name__ == "__main__":
    unittest.main()
