"""Every Trainer / Energy card in the pool whose text gives, blocks, removes or
reads a Special Condition (Burned, Poisoned, Asleep, Paralyzed, Confused).
Card texts from the official card database; each test states the promise.
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
from spirit.game.session.passives import effective_max_hp, effective_retreat_cost
from spirit.tools.effect_smoke import P1, P2

DIALGA, HEAVY = 'SWSH7.Dialga_112', 'Heavy Impact'
ALL = ('Asleep', 'Burned', 'Confused', 'Paralyzed', 'Poisoned')
ENUM = {'Asleep': SC.ASLEEP, 'Burned': SC.BURNED, 'Confused': SC.CONFUSED,
        'Paralyzed': SC.PARALYZED, 'Poisoned': SC.POISONED}


def coins(value):
    real = random.choice

    def choice(seq):
        if list(seq) in ([0, 1], [True, False]):
            return seq[0] if value == 'heads' else seq[1]
        return real(seq)
    return patch.object(random, 'choice', choice)


class StatusTrainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me_spec=None, opp_spec=None, me_conds=(), opp_conds=()):
        t = Table(self)
        t.heads = True
        me = neutral(t.put(me_spec or self.filler, P1, 'active'))
        mb = neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(opp_spec or self.filler, P2, 'active'))
        ob = neutral(t.put(self.filler, P2, 'bench'))
        for p in (me, mb, opp, ob):
            p.set_attribute(AttrID.POKEMON_TYPES, [T.COLORLESS.value])
            p.set_attribute(AttrID.HP, effective_max_hp(t.board, p))
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, list(me_conds))
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, list(opp_conds))
        return t, me, mb, opp, ob

    async def give(self, t, target, cond, by=P2):
        ctx = EffectContext(t.session, by, t.active(by), None)
        await t._run(lambda: ctx.apply_special_condition(target, ENUM[cond]))
        return cond in t.conditions(target)

    async def play(self, t, spec, targets=(), pid=P1):
        card = t.put(spec, pid, 'hand')
        await t.play(card, pid=pid, targets=targets)
        return card

    async def attach(self, t, spec, pokemon):
        card = t.put(spec, pokemon.owning_player_id, 'hand')
        await t.play(card, pid=pokemon.owning_player_id, targets=[pokemon.entity_id])
        return card

    # ------------------------------------------------------------ give
    async def test_items_supporters_that_give(self):
        t, me, mb, opp, ob = self.table()
        await self.play(t, 'HF.KogasTrap_59')
        self.assertEqual(t.conditions(opp), {'Confused', 'Poisoned'})

        t, me, mb, opp, ob = self.table()
        await self.play(t, 'SWSH3.YellHorn_173')
        self.assertEqual((t.conditions(me), t.conditions(opp)), ({'Confused'}, {'Confused'}))

        t, me, mb, opp, ob = self.table()
        opp.set_attribute(AttrID.POKEMON_TYPES, [T.DARKNESS.value])
        await self.play(t, 'ME5.DarkBell_106')
        self.assertEqual((t.conditions(me), t.conditions(opp)), ({'Confused'}, set()))

        t, me, mb, opp, ob = self.table()
        await self.play(t, 'TwentiethAnn.Imakuni_63')
        self.assertEqual((t.conditions(me), t.conditions(opp)), ({'Confused'}, set()))

        for heads, want in ((True, {'Poisoned', 'Asleep'}), (False, {'Poisoned'})):
            t, me, mb, opp, ob = self.table()
            t.heads = heads
            await self.play(t, 'BW8.HypnotoxicLaser_123')
            self.assertEqual(t.conditions(opp), want, heads)

        t, me, mb, opp, ob = self.table()
        me.set_attribute(AttrID.HP, effective_max_hp(t.board, me) - 60)
        await self.play(t, 'SWSH10.SpicySeasonedCurry_151')
        self.assertEqual(t.conditions(me), {'Burned'})
        self.assertEqual(effective_max_hp(t.board, me) - t.hp(me), 20)

    async def test_lisias_appeal(self):
        t, me, mb, opp, ob = self.table()
        await self.play(t, 'SV08.LisiasAppeal_179', targets=[ob.entity_id])
        self.assertIs(t.active(P2), ob)
        self.assertEqual(t.conditions(ob), {'Confused'})

    async def test_janines_secret_art(self):
        t, me, mb, opp, ob = self.table()
        me.set_attribute(AttrID.POKEMON_TYPES, [T.DARKNESS.value])
        t.deck(P1, [t.basic_energy(T.DARKNESS), t.basic_energy(T.DARKNESS)])
        await self.play(t, 'SV065.JaninesSecretArt_59')
        self.assertTrue(t.board.attached_energies(me))
        self.assertEqual(t.conditions(me), {'Poisoned'})

    # ------------------------------------------------------------ remove
    async def test_cures(self):
        conds = ['Poisoned', 'Confused']
        t, me, *_ = self.table(me_conds=conds)
        await self.play(t, 'BW1.FullHeal_95')
        self.assertEqual(t.conditions(me), set())
        for spec in ('SM1.BigMalasada_114', 'ME3.LumioseGalette_78', 'SM8.MixedHerbs_184'):
            with self.subTest(card=spec):
                t, me, *_ = self.table(me_conds=conds)
                await self.play(t, spec)
                self.assertEqual(len(t.conditions(me)), 1)        # ONE condition
        t, me, *_ = self.table(me_conds=conds)
        await self.play(t, 'SWSH7.AromaLady_141')
        self.assertEqual(t.conditions(me), set())
        for spec in ('ME1.PokemonCenterLady_123', 'HF.PokmonCenterLady_64'):
            with self.subTest(card=spec):
                t, me, *_ = self.table(me_conds=conds)
                me.set_attribute(AttrID.HP, effective_max_hp(t.board, me) - 80)
                await self.play(t, spec, targets=[me.entity_id])
                self.assertEqual(t.conditions(me), set())
                self.assertEqual(effective_max_hp(t.board, me) - t.hp(me), 20)
        for heads in (True, False):
            t, me, *_ = self.table(me_conds=conds)
            t.heads = heads
            me.set_attribute(AttrID.HP, effective_max_hp(t.board, me) - 80)
            await self.play(t, 'SM7.LifeHerb_136', targets=[me.entity_id])
            self.assertEqual(t.conditions(me), set() if heads else set(conds), heads)

    async def test_lum_berry(self):
        t, me, *_ = self.table(me_conds=['Poisoned', 'Confused'])
        berry = t.attach('SWSH1.LumBerry_168', me)
        await t._run(lambda: t.session._fire_passive_event(P1, "on_end_turn"))
        self.assertEqual(t.conditions(me), set())
        self.assertNotIn(berry, me.children)

    # ------------------------------------------------------------ block
    async def test_tool_and_energy_immunities(self):
        cases = [
            ('XY3.SparklingRobe_99', None, None, set(ALL)),
            ('SWSH6.ImpactEnergy_157', None, None, {'Poisoned'}),
            ('SWSH6.SpiralEnergy_159', None, None, {'Paralyzed'}),
            ('SV2.TherapeuticEnergy_193', None, None, {'Asleep', 'Confused', 'Paralyzed'}),
            ('SWSH4.AromaticGrassEnergy_162', T.GRASS, None, set(ALL)),
            ('ME4.BubblyWaterEnergy_84', T.WATER, None, set(ALL)),
        ]
        for spec, ptype, _, blocked in cases:
            for cond in ALL:
                with self.subTest(card=spec, condition=cond):
                    t, me, *_ = self.table()
                    if ptype is not None:
                        me.set_attribute(AttrID.POKEMON_TYPES, [ptype.value])
                    t.attach(spec, me)
                    self.assertEqual(await self.give(t, me, cond), cond not in blocked)
        # Heavy Boots: Retreat Cost 3+ only.
        t, me, *_ = self.table()
        me.set_attribute(AttrID.RETREAT_COST, 3)
        t.attach('XY8.HeavyBoots_141', me)
        self.assertFalse(await self.give(t, me, 'Confused'))
        t, me, *_ = self.table()
        me.set_attribute(AttrID.RETREAT_COST, 1)
        t.attach('XY8.HeavyBoots_141', me)
        self.assertTrue(await self.give(t, me, 'Confused'))

    async def test_attaching_immunity_removes_existing(self):
        t, me, *_ = self.table(me_conds=['Poisoned', 'Confused'])
        await self.attach(t, 'XY3.SparklingRobe_99', me)
        self.assertEqual(t.conditions(me), set())
        t, me, *_ = self.table(me_conds=['Paralyzed', 'Poisoned'])
        await self.attach(t, 'SV2.TherapeuticEnergy_193', me)
        self.assertEqual(t.conditions(me), {'Poisoned'})

    async def test_stadium_immunities(self):
        t, me, mb, opp, ob = self.table()
        me.set_attribute(AttrID.POKEMON_TYPES, [T.METAL.value])
        t.stadium('XY4.SteelShelter_105', P2)
        self.assertFalse(await self.give(t, me, 'Poisoned'))
        self.assertTrue(await self.give(t, opp, 'Poisoned', by=P1))
        t, me, mb, opp, ob = self.table()
        t.stadium('SV06.FestivalGrounds_149', P2)
        t.energy(me, T.WATER)
        self.assertFalse(await self.give(t, me, 'Asleep'))
        self.assertTrue(await self.give(t, opp, 'Asleep', by=P1))

    async def test_fossils(self):
        for spec in ('SV035.AntiqueDomeFossil_152', 'SWSH3.RareFossil_167'):
            with self.subTest(card=spec):
                t, me, *_ = self.table()
                fossil = t.put(spec, P1, 'bench')
                for cond in ALL:
                    self.assertFalse(await self.give(t, fossil, cond), cond)

    # ------------------------------------------------------- retaliation tools
    async def test_retaliation_tools(self):
        cases = [('SWSH2.BurningScarf_155', T.FIRE, {'Burned'}),
                 ('SM11.EarRingingBell_194', None, {'Confused'}),
                 ('SM1.PoisonBarb_124', None, {'Poisoned'})]
        for spec, ptype, want in cases:
            with self.subTest(card=spec):
                t, me, mb, opp, ob = self.table(None, DIALGA)
                if ptype is not None:
                    me.set_attribute(AttrID.POKEMON_TYPES, [ptype.value])
                me.set_attribute(AttrID.HP, 900)
                t.attach(spec, me)
                pay_cost(t, opp, next(a for a in fixtures.definition(DIALGA).abilities if a.title == HEAVY))
                t.next_turn()
                await t.attack(opp, HEAVY, pid=P2)
                self.assertEqual(t.conditions(opp), want)

    async def test_retaliation_tool_requirements(self):
        # Burning Scarf needs a Fire Pokémon; Hypnotizer a Team Rocket's Pokémon.
        for holder_spec, tool, ptype, want in (
                (None, 'SWSH2.BurningScarf_155', T.WATER, set()),
                ('SV10.TeamRocketsGolbat_121', 'ME2PT5.TeamRocketsHypnotizer_206', None, {'Asleep'}),
                (None, 'ME2PT5.TeamRocketsHypnotizer_206', None, set())):
            with self.subTest(tool=tool, holder=holder_spec):
                t, me, mb, opp, ob = self.table(holder_spec, DIALGA)
                if ptype is not None:
                    me.set_attribute(AttrID.POKEMON_TYPES, [ptype.value])
                me.set_attribute(AttrID.HP, 900)
                t.attach(tool, me)
                pay_cost(t, opp, next(a for a in fixtures.definition(DIALGA).abilities if a.title == HEAVY))
                t.next_turn()
                await t.attack(opp, HEAVY, pid=P2)
                self.assertEqual(t.conditions(opp), want)

    async def evolve_keeps(self, stadium=None, owner=P1, conds=('Confused', 'Poisoned'), muk=False):
        t, me, mb, opp, ob = self.table('SM3.Pikachu_40', me_conds=conds)
        t.state.entered_play_turn[me.entity_id] = t.state.turn_number - 1
        if stadium:
            t.stadium(stadium, owner)
        if muk:
            t.put('SV1.Muk_127', P2, 'bench')
        card = t.put('SM3.Raichu_41', P1, 'hand')
        entry = next(e for e in t.offers(card) if e['selectableAction']['description'] == 'EvolvePokemonPlayAbility')
        t.yes = False                       # decline Evoshock
        await t.do(entry, targets=[me.entity_id])
        return t.conditions(t.active(P1))

    async def test_evolution_keeps_conditions(self):
        self.assertEqual(await self.evolve_keeps(), set())                         # normal rule
        self.assertEqual(await self.evolve_keeps('ME2.DizzyingValley_88'), {'Confused'})
        self.assertEqual(await self.evolve_keeps('SM4.SeaofNothingness_99'), {'Confused', 'Poisoned'})
        self.assertEqual(await self.evolve_keeps(muk=True), {'Poisoned'})          # opponent's Muk

    async def test_dust_island(self):
        for stadium, want in (('SM10.DustIsland_168', {'Poisoned'}), (None, set())):
            t, me, mb, opp, ob = self.table(me_conds=['Poisoned'])
            if stadium:
                t.stadium(stadium, P2)
            await self.play(t, 'BW1.Switch_104', targets=[mb.entity_id])
            self.assertIs(t.active(P1), mb)
            self.assertEqual(t.conditions(mb), want, stadium)

    async def test_binding_mochi(self):
        for poisoned, extra in ((True, 40), (False, 0)):
            t, me, mb, opp, ob = self.table(DIALGA)
            pay_cost(t, me, next(a for a in fixtures.definition(DIALGA).abilities if a.title == HEAVY))
            t.attach('SV065.BindingMochi_55', me)
            if poisoned:
                me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
            opp.set_attribute(AttrID.HP, 900)
            await t.attack(me, HEAVY)
            self.assertEqual(900 - t.hp(opp), 210 + extra, poisoned)

    async def test_escape_board_and_windup_arm(self):
        t, me, mb, opp, ob = self.table(me_conds=['Asleep'])
        t.energy(me, T.WATER, 4)
        t.attach('SM5.EscapeBoard_122', me)
        self.assertTrue(t.can(me, 'BaseRetreat'))
        t, me, mb, opp, ob = self.table(DIALGA, me_conds=['Paralyzed'])
        pay_cost(t, me, next(a for a in fixtures.definition(DIALGA).abilities if a.title == HEAVY))
        self.assertIsNone(t.attack_offer(me, HEAVY))
        t.attach('SWSH11.WindupArm_170', me)
        self.assertIsNotNone(t.attack_offer(me, HEAVY))

    # --------------------------------------------------------- stadiums
    async def checkup_damage(self, stadium, conds, value='tails', types=None):
        t, me, mb, opp, ob = self.table(opp_conds=conds)
        if types:
            opp.set_attribute(AttrID.POKEMON_TYPES, [types.value])
        t.stadium(stadium, P1)
        before = t.hp(opp)
        with coins(value):
            await t.checkup()
        return before - t.hp(opp), t.conditions(opp)

    async def test_poison_stadiums(self):
        self.assertEqual((await self.checkup_damage('BW8.VirbankCityGym_126', ['Poisoned']))[0], 30)
        self.assertEqual((await self.checkup_damage('SV05.PerilousJungle_156', ['Poisoned']))[0], 30)
        self.assertEqual((await self.checkup_damage('SV05.PerilousJungle_156', ['Poisoned'],
                                                    types=T.DARKNESS))[0], 10)

    async def test_wela_volcano_park(self):
        dealt, conds = await self.checkup_damage('DM.WelaVolcanoPark_63', ['Burned'], value='heads')
        self.assertIn('Burned', conds)

    async def test_slumbering_forest(self):
        t, me, mb, opp, ob = self.table(opp_conds=['Asleep'])
        t.stadium('SM11.SlumberingForest_207', P1)
        seq = iter([0, 1])           # heads then tails: still Asleep
        real = random.choice
        with patch.object(random, 'choice', lambda s: next(seq) if list(s) == [0, 1] else real(s)):
            await t.checkup()
        self.assertIn('Asleep', t.conditions(opp))

    async def test_chaos_tower(self):
        t, me, mb, opp, ob = self.table(me_conds=['Confused'])
        card = t.put('XY10.ChaosTower_94', P1, 'hand')
        entry = next(e for e in t.offers(card) if e['selectableAction']['description'] == 'DefaultStadiumPlayAbility')
        await t.do(entry, amounts=[0])
        # Whichever player the tower faces, that side's Confused/Poisoned
        # (or Asleep/Paralyzed) are blocked.
        mine_blocked = not await self.give(t, me, 'Poisoned')
        theirs_blocked = not await self.give(t, opp, 'Poisoned', by=P1)
        self.assertNotEqual(mine_blocked, theirs_blocked)

    async def test_all_night_party(self):
        t, me, *_ = self.table(me_conds=['Asleep'])
        me.set_attribute(AttrID.HP, effective_max_hp(t.board, me) - 50)
        stadium = t.stadium('XY9.AllNightParty_96', P1)
        entry = next((e for e in t.actions() if e['entityID'] == stadium.entity_id), None)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(t.conditions(me), set())
        self.assertEqual(effective_max_hp(t.board, me) - t.hp(me), 20)

    # --------------------------------------------------------- supporters
    async def test_atticus_needs_poison(self):
        t, me, mb, opp, ob = self.table()
        card = t.put('SV045.Atticus_77', P1, 'hand')
        self.assertFalse(t.offers(card))
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        self.assertTrue(t.offers(card))

    async def test_roxies_performance(self):
        t, me, mb, opp, ob = self.table()
        t.energy(opp, T.WATER, 4)
        await self.play(t, 'ME4.RoxiesPerformance_112')
        t.next_turn()
        self.assertTrue(t.can(opp, 'BaseRetreat', pid=P2))
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        self.assertFalse(t.can(opp, 'BaseRetreat', pid=P2))


if __name__ == "__main__":
    unittest.main()
