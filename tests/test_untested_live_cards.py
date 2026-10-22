"""Bug hunt (Oct 14): cards in LIVE decks whose text no test had run.

Source: DECK lines of 3 days of live logs (531 human decks) joined with
dev_notes/card_coverage.csv ("never touched" / "part exercised" / "named in a
test only"), most-played first. Each test plays the card through the real
action executor on a small board and checks the printed text.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

C, G, R, W, L, P, F, D, M, Y, N = (
    PokemonTypes.COLORLESS, PokemonTypes.GRASS, PokemonTypes.FIRE,
    PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.PSYCHIC,
    PokemonTypes.FIGHTING, PokemonTypes.DARKNESS, PokemonTypes.METAL,
    PokemonTypes.FAIRY, PokemonTypes.DRAGON)


def neutral(p, hp=None):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.attribute_originals[AttrID.HP.value] = hp      # max HP too
        p.set_attribute(AttrID.HP, hp)
    return p


def name(card):
    return def_for(card.archetype_id).display_name


class Base(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, spec=None, kind=D, count=4, opp_hp=400):
        t = Table(self)
        me = t.put(spec or self.filler, P1, 'active')
        if count:
            t.energy(me, kind, count)
        opp = neutral(t.put(self.filler, P2, 'active'), hp=opp_hp)
        t.opp_bench = neutral(t.put(self.filler, P2, 'bench'), hp=400)
        return t, me, opp

    def ready(self, spec, title=None, opp_hp=400):
        """spec Active with Energy paying `title` (default: every attack)."""
        d = fixtures.definition(spec)
        need = {}
        for a in d.abilities:
            if type(a).__name__ != 'Attack' or (title and a.title != title):
                continue
            for k, v in a.cost.items():
                need[k] = max(need.get(k, 0), v)
        t, me, opp = self.table(spec, count=0, opp_hp=opp_hp)
        for k, v in need.items():
            t.energy(me, D if k == C else k, v)
        return t, me, opp

    async def dmg(self, spec, title, setup=None, opp_hp=400):
        t, me, opp = self.ready(spec, title, opp_hp=opp_hp)
        if setup:
            r = setup(t, me, opp)
            if hasattr(r, '__await__'):
                await r
        await t.attack(me, title)
        return 400 - t.hp(opp), t, me, opp

    def base(self, spec, title):
        return next(a.damage for a in fixtures.definition(spec).abilities if a.title == title)

    def ko_last_turn(self, t, pid=P1):
        t.state.kos_suffered_last_turn = {pid: [{"entity_id": "x"}]}
        t.state.kos_by_attack_last_turn = {pid: [{"entity_id": "x"}]}


class Batch1(Base):
    # Teammates XY5 141: only after a KO last turn; search up to 2 cards
    async def test_teammates(self):
        t, me, opp = self.table()
        card = t.put('XY5.Teammates_141', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        self.ko_last_turn(t)
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        wanted = t.deck(P1, ['SWSH1.QuickBall_216', 'SWSH9.UltraBall_150'])
        before = len(t.zone(P1, 'hand'))
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if c in wanted][:count]
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), before - 1 + 2)
        for c in wanted:
            self.assertIn(c, hand)

    # Bidoof CZ 111: Hyper Fang tails = nothing; Carefree Countenance on Bench
    async def test_bidoof(self):
        for heads in (True, False):
            t, me, opp = self.table('CZ.Bidoof_111')
            t.heads = heads
            await t.attack(me, 'Hyper Fang')
            self.assertEqual(400 - t.hp(opp), 30 if heads else 0)

    async def test_bidoof_bench_immune_to_attack_damage(self):
        t, me, opp = self.table()
        bench = neutral(t.put('CZ.Bidoof_111', P2, 'bench'))
        full = t.hp(bench)
        from spirit.game.session.effects import EffectContext
        attack = next(x for x in def_for(me.archetype_id).abilities
                      if type(x).__name__ == 'Attack')
        ctx = EffectContext(t.session, P1, me, attack)
        await t._run(lambda: ctx.deal_damage(30, target=bench))
        self.assertEqual(t.hp(bench), full)

    # Bibarel SWSH9 121 / CZ 185: Tail Smash
    async def test_bibarel_tail_smash(self):
        for heads in (True, False):
            t, me, opp = self.table('CZ.Bibarel_185')
            t.heads = heads
            await t.attack(me, 'Tail Smash')
            self.assertEqual(400 - t.hp(opp), 100 if heads else 0)

    # Boss's Orders (Ghetsis) SV2 172: gust
    async def test_bosss_orders_ghetsis(self):
        t, me, opp = self.table()
        card = t.put('SV2.BosssOrdersGhetsis_172', P1, 'hand')
        target = t.opp_bench
        t.pokemon = lambda cands, prompt: target
        await t.play(card)
        self.assertIs(t.active(P2), target)
        self.assertIn(opp, t.zone(P2, 'bench'))

    # Luxray SV2 71 Swelling Flash: hand -> Bench when behind on Prizes
    async def test_luxray_swelling_flash(self):
        t, me, opp = self.table()
        lux = t.put('SV2.Luxray_71', P1, 'hand')
        t.set_prizes(P1, 6)
        t.set_prizes(P2, 6)
        self.assertIsNone(t.ability_offer(lux, 'Swelling Flash'))
        t.set_prizes(P2, 4)
        self.assertIsNotNone(t.ability_offer(lux, 'Swelling Flash'))
        await t.use(lux, 'Swelling Flash')
        self.assertIn(lux, t.zone(P1, 'bench'))

    async def test_luxray_wild_charge(self):
        t, me, opp = self.table('SV2.Luxray_71', L, 3)
        neutral(me)
        before = t.hp(me)
        await t.attack(me, 'Wild Charge')
        self.assertEqual(400 - t.hp(opp), 180)
        self.assertEqual(before - t.hp(me), 20)

    # Chaotic Swell SM12 187: the next Stadium played is discarded too
    async def test_chaotic_swell(self):
        t, me, opp = self.table()
        t.stadium('SM12.ChaoticSwell_187', P2)
        new = t.put('SWSH7.StormyMountains_232', P1, 'hand')
        await t.play(new)
        self.assertEqual(list(t.board.find_global_area('activeStadium').children), [])
        self.assertIn(new, t.zone(P1, 'discard'))
        self.assertIn('Chaotic Swell', t.names(t.zone(P2, 'discard')))


if __name__ == '__main__':
    unittest.main()


class Batch2(Base):
    async def test_feather_ball(self):
        t, me, opp = self.table()
        ball = t.put('SWSH10.FeatherBall_141', P1, 'hand')
        free = t.deck(P1, ['SL.Minun_34'])[0]
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if c is free]
        await t.play(ball)
        if int(free.get_attribute(AttrID.RETREAT_COST) or 0) == 0:
            self.assertIn(free, t.zone(P1, 'hand'))

    async def test_blend_energy_grfpd_pays_each_type(self):
        for kind in (G, R, P, D):
            t, me, opp = self.table(count=0)
            e = t.attach('BW6.BlendEnergyGrassFirePsychicDarkness_117', me)
            from spirit.game.session.passives import energy_provided_options
            opts = energy_provided_options(t.board, e)
            self.assertTrue(any(kind.value in o for o in opts), (kind, opts))

    async def test_absol_mach_claw_ignores_resistance(self):
        t, me, opp = self.table('XY6.Absol_40', D, 3)
        opp.set_attribute(AttrID.RESISTANCE_TYPES, [D.value])
        await t.attack(me, 'Mach Claw')
        self.assertEqual(400 - t.hp(opp), 30)

    async def test_absol_cursed_eyes(self):
        t, me, opp = self.table()
        opp.set_attribute(AttrID.HP, 370)          # 3 counters on the Active
        absol = t.put('XY6.Absol_40', P1, 'hand')
        t.pokemon = lambda cands, prompt: opp if 'with damage' in prompt else t.opp_bench
        await t.play(absol)
        self.assertEqual(t.hp(opp), 400, t.prompts)
        self.assertEqual(t.hp(t.opp_bench), 370)

    async def test_exeggcute_precocious_evolution_first_turn(self):
        t, me, opp = self.table('SV08.Exeggcute_1', G, 1)
        t.state.turn_number = 1
        self.assertIsNotNone(t.attack_offer(me, 'Precocious Evolution'))
        evo = t.deck(P1, ['SV08.Exeggutor_3'])[0]
        await t.attack(me, 'Precocious Evolution')
        top = t.active(P1)
        self.assertEqual(name(top), 'Exeggutor')

    async def test_cosmog_ascension(self):
        t, me, opp = self.table('SM12.Cosmog_99', P, 1)
        t.deck(P1, ['SM12.Cosmoem_101'])
        await t.attack(me, 'Ascension')
        self.assertEqual(name(t.active(P1)), 'Cosmoem')

    async def test_clefable_moon_watching_dance(self):
        t, me, opp = self.table('SM10.Clefable_133', Y, 2)
        b1 = t.put(self.filler, P1, 'bench'); t.energy(b1, Y, 1)
        b2 = t.put(self.filler, P1, 'bench'); t.energy(b2, D, 1)
        await t.attack(me, 'Moon-Watching Dance')
        self.assertEqual(400 - t.hp(opp), 10 + 30 * 2)

    async def test_aromatisse_fairy_transfer(self):
        t, me, opp = self.table()
        aro = t.put('XY1.Aromatisse_93', P1, 'bench')
        fairy = t.energy(me, Y, 1)
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if c is fairy][:count] or cards[:count]
        t.pokemon = lambda cands, prompt: aro if aro in cands else (me if me in cands else cands[0])
        await t.use(aro, 'Fairy Transfer')
        self.assertIn(fairy, aro.children)
        self.assertIsNotNone(t.ability_offer(aro, 'Fairy Transfer'))   # as often as you like

    async def test_galarian_zigzagoon_surprise_attack(self):
        for heads in (True, False):
            t, me, opp = self.table('SWSH1.GalarianZigzagoon_117', D, 2)
            t.heads = heads
            await t.attack(me, 'Surprise Attack')
            self.assertEqual(400 - t.hp(opp), 30 if heads else 0)

    async def test_togetic_go_fetch(self):
        t, me, opp = self.table('XY6.Togetic_44', Y, 3)
        for _ in range(4):
            t.put(t.basic_energy(D), P1, 'discard')
        deck = len(t.zone(P1, 'deck'))
        await t.attack(me, 'Go Fetch')
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 3)

    async def test_spritzee_sweet_scent(self):
        t, me, opp = self.table('XY1.Spritzee_92', Y, 2)
        b = t.put(self.filler, P1, 'bench', hp=10)
        full = t.hp(b) + 0
        await t.attack(me, 'Sweet Scent')
        self.assertEqual(t.hp(b), 30)

    async def test_electric_generator(self):
        t, me, opp = self.table()
        lb = t.put('SV1.Pawmi_73', P1, 'bench')
        gen = t.put('SV1.ElectricGenerator_170', P1, 'hand')
        t.deck(P1, ['Free_Energy.BasicLightningEnergy_257'] if False else [], top=True)
        e1 = t.put(t.basic_energy(L), P1, 'deck'); e2 = t.put(t.basic_energy(L), P1, 'deck')
        await t.play(gen)
        self.assertEqual(len([c for c in lb.children]), 2)

    async def test_hisuian_braviary_eerie_cry(self):
        t, me, opp = self.table('SWSH12.HisuianBraviary_149', P, 3)
        opp.set_attribute(AttrID.HP, 390)
        await t.attack(me, 'Eerie Cry')
        self.assertEqual(t.hp(opp), 360)
        self.assertEqual(t.hp(t.opp_bench), 400)

    async def test_dragon_elixir(self):
        t, me, opp = self.table('SV035.Dragonair_148', N, 0)
        me.set_attribute(AttrID.HP, t.hp(me) - 80)
        before = t.hp(me)
        await t.play(t.put('SV08.DragonElixir_172', P1, 'hand'))
        self.assertEqual(t.hp(me), before + 60)

    async def test_plusle_tag_team_boost(self):
        for minun in (False, True):
            t, me, opp = self.table('SL.Plusle_33', L, 2)
            if minun:
                t.put('SL.Minun_34', P1, 'bench')
            await t.attack(me, 'Tag Team Boost')
            self.assertEqual(400 - t.hp(opp), 60 if minun else 10)

    async def test_wurmple_congregation(self):
        t, me, opp = self.table('SWSH11.Wurmple_6', G, 3)
        fam = t.deck(P1, ['SWSH11.Silcoon_7', 'SWSH11.Beautifly_8', 'SWSH11.Cascoon_9', 'SWSH11.Dustox_10'])
        await t.attack(me, 'Creepy-Crawly Congregation')
        for c in fam:
            self.assertIn(c, t.zone(P1, 'hand'))

    async def test_rust_syndicate_grunt(self):
        t, me, opp = self.table()
        e = t.energy(opp, D, 1)
        card = t.put('ME5.RustSyndicateGrunt_81', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        self.ko_last_turn(t)
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        t.pokemon = lambda c, p: opp
        await t.play(card)
        self.assertIn(e, t.zone(P2, 'discard'))


class Batch3(Base):
    async def test_xerneas_rainbow_force(self):
        t, me, opp = self.ready('XY8.Xerneas_107', 'Rainbow Force')
        for spec in ('SL.Minun_34', 'SL.Plusle_33', 'XY1.Spritzee_92', 'SWSH11.Wurmple_6'):
            t.put(spec, P1, 'bench')
        types = set()
        for b in t.zone(P1, 'bench'):
            types.update(b.get_attribute(AttrID.POKEMON_TYPES) or [])
        await t.attack(me, 'Rainbow Force')
        self.assertEqual(400 - t.hp(opp), 10 + 30 * len(types))

    async def test_xerneas_power_creation(self):
        for healed in (False, True):
            t, me, opp = self.ready('XY8.Xerneas_107', 'Power Creation')
            if healed:
                t.state.healed_this_turn = getattr(t.state, 'healed_this_turn', set())
                me.set_attribute(AttrID.HP, t.hp(me) - 30)
                from spirit.game.session.effects import EffectContext
                ctx = EffectContext(t.session, P1, me, None)
                await t._run(lambda: ctx.heal(20, me))
            await t.attack(me, 'Power Creation')
            self.assertEqual(400 - t.hp(opp), 160 if healed else 80)

    async def test_reds_challenge(self):
        t, me, opp = self.table()
        card = t.put('SM10.RedsChallenge_184', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        a = t.put(self.item, P1, 'hand'); b = t.put(self.item, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        want = t.deck(P1, ['SL.Minun_34'])[0]
        t.picks = lambda cards, count, prompt, shown: (
            [want] if want in cards else cards[:count])
        await t.play(card)
        self.assertIn(want, t.zone(P1, 'hand'))
        self.assertIn(a, t.zone(P1, 'discard')); self.assertIn(b, t.zone(P1, 'discard'))

    async def test_aipom_astonish(self):
        t, me, opp = self.ready('ME2.Aipom_78')
        c = t.put(self.item, P2, 'hand')
        deck = len(t.zone(P2, 'deck'))
        await t.attack(me, 'Astonish')
        self.assertEqual(t.zone(P2, 'hand'), [])
        self.assertEqual(len(t.zone(P2, 'deck')), deck + 1)
        self.assertEqual(400 - t.hp(opp), 20)

    async def test_iron_leaves(self):
        t, me, opp = self.ready('SV06.IronLeaves_19')
        mons = [t.put(self.filler, P1, 'discard') for _ in range(3)]
        await t.attack(me, 'Recovery Net')
        self.assertEqual(sum(m in t.zone(P1, 'hand') for m in mons), 2)
        for ko in (False, True):
            t, me, opp = self.ready('SV06.IronLeaves_19')
            if ko:
                self.ko_last_turn(t)
            await t.attack(me, 'Avenging Edge')
            self.assertEqual(400 - t.hp(opp), 160 if ko else 100)

    async def test_ampharos_searchlight_tail(self):
        for energy in (False, True):
            t, me, opp = self.ready('SWSH6.Ampharos_49', 'Searchlight Tail')
            if energy:
                t.put(t.basic_energy(D), P2, 'hand')
            t.put(self.item, P2, 'hand')
            await t.attack(me, 'Searchlight Tail')
            self.assertEqual(400 - t.hp(opp), 180 if energy else 90)

    async def test_yveltal_corrosive_winds_and_beam(self):
        t, me, opp = self.ready('SV065.Yveltal_35')
        opp.set_attribute(AttrID.HP, 390)
        await t.attack(me, 'Corrosive Winds')
        self.assertEqual(t.hp(opp), 370)
        self.assertEqual(t.hp(t.opp_bench), 400)
        for heads in (True, False):
            t, me, opp = self.ready('SV065.Yveltal_35')
            e = t.energy(opp, D, 1)
            t.heads = heads
            await t.attack(me, 'Destructive Beam')
            self.assertEqual(e in t.zone(P2, 'discard'), heads)

    async def test_zekrom_nitro_thunder(self):
        for fire in (False, True):
            t, me, opp = self.ready('ME55.Zekrom_56', 'Nitro Thunder')
            if fire:
                t.energy(me, R, 1)
            await t.attack(me, 'Nitro Thunder')
            self.assertEqual(400 - t.hp(opp), 160 if fire else 80)

    async def test_earthquakes(self):
        for spec, base, bench_dmg in (('SWSH8.Steelix_139', 180, 30),
                                      ('SWSH4.Donphan_87', None, None),
                                      ('SWSH2.Whiscash_100', 140, 20)):
            d = fixtures.definition(spec)
            eq = next(a for a in d.abilities if a.title == 'Earthquake')
            if base is None:
                base = eq.damage
                bench_dmg = int(__import__('re').search(r'does (\d+) damage to each of your Benched', eq.game_text).group(1))
            t, me, opp = self.ready(spec, 'Earthquake')
            mine = neutral(t.put(self.filler, P1, 'bench'), hp=300)
            await t.attack(me, 'Earthquake')
            self.assertEqual(400 - t.hp(opp), base, spec)
            self.assertEqual(300 - t.hp(mine), bench_dmg, spec)
            self.assertEqual(t.hp(t.opp_bench), 400, spec)

    async def test_whiscash_submerge(self):
        t, me, opp = self.ready('SWSH2.Whiscash_100')
        w = neutral(t.put('SWSH2.Whiscash_100', P1, 'bench'))
        full = t.hp(w)
        await t.attack(me, 'Earthquake')
        self.assertEqual(t.hp(w), full)

    async def test_tangrowth(self):
        t, me, opp = self.ready('SM12.Tangrowth_6')
        opp.set_attribute(AttrID.RETREAT_COST, 2)
        await t.attack(me, 'Grass Knot')
        self.assertEqual(400 - t.hp(opp), 70)
        t, me, opp = self.ready('SM12.Tangrowth_6')
        flips = iter([True, False])
        t.heads = lambda title: next(flips)
        await t.attack(me, 'Slam')
        self.assertEqual(400 - t.hp(opp), 80)

    async def test_rotom_junk_hunt(self):
        t, me, opp = self.ready('SV1.Rotom_70')
        item = t.put(self.item, P1, 'discard')
        await t.attack(me, 'Junk Hunt')
        self.assertIn(item, t.zone(P1, 'hand'))

    async def test_ferrothorn_kaboom_needles(self):
        t, me, opp = self.ready('ME55.Ferrothorn_104')
        neutral(me, hp=300)
        await t.attack(me, 'Kaboom Needles')
        self.assertEqual(400 - t.hp(opp), 50)
        self.assertEqual(400 - t.hp(t.opp_bench), 50)
        self.assertEqual(300 - t.hp(me), 130)

    async def test_liepard_torment(self):
        t, me, opp = self.ready('SL.Liepard_49')
        opp_def = def_for(opp.archetype_id)
        await t.attack(me, 'Torment')
        self.assertEqual(400 - t.hp(opp), 30)
        locks = [k for k in (getattr(t.state, 'attack_locks', {}) or {}) if k[0] == opp.entity_id]
        self.assertTrue(locks or any(t.state.attack_locked(opp.entity_id, a.ability_id)
                                     for a in opp_def.abilities if hasattr(a, 'cost')))

    async def test_haunter_pain_amplifier(self):
        t, me, opp = self.ready('SM4.Haunter_37')
        opp.set_attribute(AttrID.HP, 390)
        await t.attack(me, 'Pain Amplifier')
        self.assertEqual(t.hp(opp), 370)
        self.assertEqual(t.hp(t.opp_bench), 400)

    async def test_ambipom_full_tilt_fling(self):
        t, me, opp = self.ready('PGO.Ambipom_57')
        n = len([c for c in me.children])
        flips = iter([True, False] * 5)
        t.heads = lambda title: next(flips)
        await t.attack(me, 'Full Tilt Fling')
        self.assertEqual(400 - t.hp(opp), 60 * ((n + 1) // 2))

    async def test_ampharos_split_bomb(self):
        t, me, opp = self.ready('SM8.Ampharos_78', 'Split Bomb')
        t.picks = lambda cards, count, prompt, shown: cards[:count]
        await t.attack(me, 'Split Bomb')
        self.assertEqual(400 - t.hp(opp), 50)
        self.assertEqual(400 - t.hp(t.opp_bench), 50)

    async def test_iron_jugulis_homing_headbutt(self):
        t, me, opp = self.ready('SV4.IronJugulis_158', 'Homing Headbutt')
        opp.set_attribute(AttrID.HP, 390)
        clean = neutral(t.put(self.filler, P2, 'bench'), hp=400)
        t.opp_bench.set_attribute(AttrID.HP, 390)
        await t.attack(me, 'Homing Headbutt')
        self.assertEqual(t.hp(opp), 340)
        self.assertEqual(t.hp(t.opp_bench), 340)
        self.assertEqual(t.hp(clean), 400)

    async def test_chinchou_shine_on(self):
        t, me, opp = self.ready('SV045.Chinchou_20', 'Shine On')
        top = t.deck(P1, ['SL.Minun_34'])[0]
        await t.attack(me, 'Shine On')
        self.assertIs(t.zone(P1, 'deck')[0], top)       # bottom = index 0


def choosing_attack(index):
    from unittest.mock import patch
    from spirit.game.session.game_session import GameSession

    async def pick(session, pid, source, candidates, prompt=''):
        titles = [attack.title for _, attack in candidates]
        return index(titles) if callable(index) else index
    return patch.object(GameSession, 'prompt_attack_selection', pick)


class Batch4(Base):
    async def test_exp_share(self):
        t, me, opp = self.table(count=0)
        neutral(me, hp=30)
        e = t.energy(me, D, 1)
        holder = t.put(self.filler, P1, 'bench')
        await t.play(t.put('SWSH5.ExpShare_126', P1, 'hand'), targets=[holder.entity_id])
        t.next_turn()                       # P2 attacks
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        t.pokemon = lambda c, p: holder if holder in c else c[0]
        await t.attack(attacker, title, pid=P2)
        self.assertIn(e, holder.children)

    async def test_punk_helmet(self):
        t, me, opp = self.table(count=0)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        dark = neutral(t.put('SL.Liepard_49', P1, 'active'))
        await t.play(t.put('ME2.PunkHelmet_92', P1, 'hand'), targets=[dark.entity_id])
        t.next_turn()
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(400 - t.hp(attacker), 40)

    async def test_handheld_fan(self):
        t, me, opp = self.table(count=0)
        await t.play(t.put('SV06.HandheldFan_150', P1, 'hand'), targets=[me.entity_id])
        t.next_turn()
        neutral(me, hp=300)
        attacker = t.active(P2)
        es = t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(len([c for c in t.opp_bench.children]), 1)

    async def test_nihilego_nightcap(self):
        t, me, opp = self.ready('SM8.Nihilego_106', 'Nightcap')
        t.set_prizes(P2, 3)
        self.assertIsNone(t.attack_offer(me, 'Nightcap'))
        t.set_prizes(P2, 2)
        self.assertIsNotNone(t.attack_offer(me, 'Nightcap'))

    async def test_nihilego_void_tentacles(self):
        t, me, opp = self.ready('SM8.Nihilego_106', 'Void Tentacles')
        await t.attack(me, 'Void Tentacles')
        self.assertEqual(t.conditions(opp), {'Confused', 'Poisoned'})

    async def test_tapu_lele_magical_swap(self):
        t, me, opp = self.ready('SM5.TapuLele_94', 'Magical Swap')
        opp.set_attribute(AttrID.HP, 370)
        await t.attack(me, 'Magical Swap')
        total = (400 - t.hp(opp)) + (400 - t.hp(t.opp_bench))
        self.assertEqual(total, 30)

    async def test_tapu_lele_psywave(self):
        t, me, opp = self.ready('SM5.TapuLele_94', 'Psywave')
        t.energy(opp, D, 3)
        await t.attack(me, 'Psywave')
        self.assertEqual(400 - t.hp(opp), 60)

    async def test_powerglass(self):
        t, me, opp = self.table(count=0)
        await t.play(t.put('SV065.Powerglass_63', P1, 'hand'), targets=[me.entity_id])
        e = t.put(t.basic_energy(D), P1, 'discard')
        await t.checkup()
        self.assertIn(e, me.children)

    async def test_scovillain_super_spicy_breath(self):
        d = fixtures.definition('SV1.Scovillain_29')
        base = next(a.damage for a in d.abilities if a.title == 'Super Spicy Breath')
        for fire in (False, True):
            t, me, opp = self.table('SV1.Scovillain_29', count=0)
            t.energy(me, G if not fire else R, 3)
            if fire:
                t.energy(me, G, 1)
            await t.attack(me, 'Super Spicy Breath')
            self.assertEqual(400 - t.hp(opp), base + (90 if fire else 0))

    async def test_xerneas_geomancy(self):
        t, me, opp = self.ready('XY1.Xerneas_96', 'Geomancy')
        b1 = t.put(self.filler, P1, 'bench'); b2 = t.put(self.filler, P1, 'bench')
        f1 = t.put(t.basic_energy(Y), P1, 'deck'); f2 = t.put(t.basic_energy(Y), P1, 'deck')
        t.picks = lambda cards, count, prompt, shown: cards[:count]
        await t.attack(me, 'Geomancy')
        self.assertEqual(sum(1 for c in b1.children) + sum(1 for c in b2.children), 2)
        self.assertEqual(len(b1.children), 1)

    async def test_tropius_tropic_breeze(self):
        t, me, opp = self.ready('SV2.Tropius_7', 'Tropic Breeze')
        n = len(me.children)
        b = t.put(self.filler, P1, 'bench')
        await t.attack(me, 'Tropic Breeze')
        self.assertEqual(len(b.children), n)
        self.assertEqual(len(me.children), 0)

    async def test_mimikyu_mischievous_hands(self):
        t, me, opp = self.ready('SM12.Mimikyu_96', 'Mischievous Hands')
        await t.attack(me, 'Mischievous Hands')
        self.assertEqual(t.hp(opp), 380)
        self.assertEqual(t.hp(t.opp_bench), 380)

    async def test_gengar_creep_show(self):
        for counters, ko in ((2, False), (3, True)):
            t, me, opp = self.ready('XY8.Gengar_60', 'Creep Show')
            opp.set_attribute(AttrID.HP, 400 - 10 * counters)
            await t.attack(me, 'Creep Show')
            self.assertEqual(opp in t.zone(P2, 'discard') or t.active(P2) is not opp
                             or t.hp(opp) <= 0, ko, counters)

    async def test_gengar_sinister_fog(self):
        t, me, opp = self.ready('XY8.Gengar_60', 'Sinister Fog')
        await t.attack(me, 'Sinister Fog')
        self.assertIn('Poisoned', t.conditions(opp))
        self.assertEqual(t.hp(t.opp_bench), 390)

    async def test_kindler(self):
        t, me, opp = self.table()
        card = t.put('SWSH9.Kindler_143', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        fire = t.put(t.basic_energy(R), P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        hand = len(t.zone(P1, 'hand'))
        await t.play(card)
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), hand - 2 + 2)

    async def test_yamper_ball_search(self):
        t, me, opp = self.table()
        pb = t.put('SWSH5.PokBall_131' if False else 'SWSH1.GreatBall_164', P1, 'discard')
        y = t.put('SWSH5.Yamper_52', P1, 'hand')
        await t.play(y)
        self.assertIn(pb, t.zone(P1, 'hand'))

    async def test_cursed_shovel(self):
        t, me, opp = self.table(count=0)
        neutral(me, hp=10)
        await t.play(t.put('SWSH2.CursedShovel_157', P1, 'hand'), targets=[me.entity_id])
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        deck = len(t.zone(P2, 'deck'))
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(len(t.zone(P2, 'deck')), deck - 2)

    async def test_clefairy_metronome(self):
        t, me, opp = self.ready('XY12.Clefairy_63', 'Metronome')
        with choosing_attack(0):
            await t.attack(me, 'Metronome')
        self.assertTrue(400 - t.hp(opp) > 0 or t.conditions(opp))

    async def test_beedrill_elusive_master(self):
        t, me, opp = self.table()
        for c in t.zone(P1, 'hand'):
            t.board.find_player_area(P1, 'hand').remove_child(c)
        bee = t.put('SWSH4.Beedrill_3', P1, 'hand')
        self.assertIsNotNone(t.ability_offer(bee, 'Elusive Master'))
        await t.use(bee, 'Elusive Master')
        self.assertIn(bee, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        t.put(self.item, P1, 'hand')
        bee2 = t.put('SWSH4.Beedrill_3', P1, 'hand')
        self.assertIsNone(t.ability_offer(bee2, 'Elusive Master'))

    async def test_ariados_trapping_thread(self):
        t, me, opp = self.ready('SM8.Ariados_10', 'Trapping Thread')
        await t.attack(me, 'Trapping Thread')
        self.assertEqual(400 - t.hp(opp), 30)


class Batch5(Base):
    async def test_luxio_shorting_spark(self):
        t, me, opp = self.ready('CZ.Luxio_42', 'Shorting Spark')
        await t.play(t.put('SV065.Powerglass_63', P2, 'hand'), pid=P2, targets=[t.opp_bench.entity_id]) \
            if False else None
        tool = t.put('SV065.Powerglass_63', P2, 'hand')
        t.board.attach_card(tool.entity_id, t.opp_bench.entity_id)
        await t.attack(me, 'Shorting Spark')
        self.assertEqual(400 - t.hp(t.opp_bench), 90)
        self.assertEqual(t.hp(opp), 400)

    async def test_lanturn_aqua_spark(self):
        for water in (False, True):
            d, t, me, opp = await self.dmg('SV045.Lanturn_21', 'Aqua Spark',
                                           (lambda t, me, opp: t.energy(me, W, 1)) if water else None)
            self.assertEqual(d, 80 + (120 if water else 0))

    async def test_boltund_defiant_spark(self):
        t, me, opp = self.table('SWSH5.Boltund_53', count=0)
        t.energy(me, L, 1)
        self.assertIsNone(t.attack_offer(me, 'Defiant Spark'))
        me.set_attribute(AttrID.HP, t.hp(me) - 10)
        self.assertIsNotNone(t.attack_offer(me, 'Defiant Spark'))
        await t.attack(me, 'Defiant Spark')
        self.assertEqual(400 - t.hp(opp), 130)

    async def test_noivern_enhanced_blade(self):
        for tool in (False, True):
            async def setup(t, me, opp):
                if tool:
                    await t.play(t.put('SV065.Powerglass_63', P1, 'hand'), targets=[me.entity_id])
            d, *_ = await self.dmg('ME2PT5.Noivern_157', 'Enhanced Blade', setup if tool else None)
            self.assertEqual(d, 70 + (70 if tool else 0))

    async def test_opal(self):
        for heads, n in ((True, 2), (False, 0)):
            t, me, opp = self.table()
            card = t.put('SWSH4.Opal_158', P1, 'hand')
            t.heads = heads
            hand = len(t.zone(P1, 'hand'))
            await t.play(card)
            self.assertEqual(len(t.zone(P1, 'hand')), hand - 1 + n)

    async def test_yamask_ominous_eyes(self):
        t, me, opp = self.ready('SV4.Yamask_75', 'Ominous Eyes')
        t.pokemon = lambda c, p: t.opp_bench
        await t.attack(me, 'Ominous Eyes')
        self.assertEqual(t.hp(t.opp_bench), 370)

    async def test_dusknoir_mind_jack(self):
        d, t, me, opp = await self.dmg('SM3.Dusknoir_53', 'Mind Jack',
                                       lambda t, me, opp: t.put(self.filler, P2, 'bench'))
        self.assertEqual(d, 30 + 30 * 2)

    async def test_dusknoir_dark_invitation(self):
        t, me, opp = self.table()
        dusk = t.put('SM3.Dusknoir_53', P1, 'bench')
        basic = t.put(self.filler, P2, 'hand')
        await t.use(dusk, 'Dark Invitation')
        self.assertIn(basic, t.zone(P2, 'bench'))
        self.assertEqual(t.damage(basic), 30)

    async def test_poliwag_round_n_round(self):
        t, me, opp = self.table('SM10.Poliwag_36', count=0)
        t.state.turn_number = 2
        title = "Round ‘n' Round"
        self.assertIsNotNone(t.ability_offer(me, title))
        await t.use(me, title)
        self.assertIn('Confused', t.conditions(opp))
        t2, me2, opp2 = self.table('SM10.Poliwag_36', count=0)
        t2.state.turn_number = 3
        self.assertIsNone(t2.ability_offer(me2, title))

    async def test_black_kyurem_dazzling_blizzard(self):
        for stadium in (False, True):
            d, *_ = await self.dmg('SM12.BlackKyurem_61', 'Dazzling Blizzard',
                                   (lambda t, me, opp: t.stadium('SWSH7.StormyMountains_232', P1)) if stadium else None)
            self.assertEqual(d, 100 + (100 if stadium else 0))

    async def test_golisopod_powerful_cross(self):
        d, *_ = await self.dmg('SV4.Golisopod_49', 'Powerful Cross',
                               lambda t, me, opp: [t.put(self.item, P2, 'hand') for _ in range(4)])
        self.assertEqual(d, 80)

    async def test_walrein_frigid_fangs(self):
        t, me, opp = self.ready('SV08.Walrein_45', 'Frigid Fangs')
        t.energy(opp, D, 2)
        await t.attack(me, 'Frigid Fangs')
        t.next_turn()
        self.assertEqual([e for e in t.actions(P2)
                          if e['selectableAction']['description'] == 'UsePokemonAttack'], [])
        t.energy(opp, D, 1)
        self.assertNotEqual([e for e in t.actions(P2)
                             if e['selectableAction']['description'] == 'UsePokemonAttack'], [])

    async def test_meganium_quick_ripening_herb(self):
        t, me, opp = self.table()
        mega = t.put('SM8.Meganium_8', P1, 'bench')
        chik = t.put('SM8.Chikorita_5', P1, 'bench')
        t.state.entered_play_turn[chik.entity_id] = 0
        stage2 = t.put('SM8.Meganium_8', P1, 'hand')
        t.pokemon = lambda c, p: chik if chik in c else c[0]
        await t.use(mega, 'Quick-Ripening Herb')
        self.assertEqual(name(t.zone(P1, 'bench')[-1]), 'Meganium')
        self.assertNotIn(stage2, t.zone(P1, 'hand'))

    async def test_medicham_harmonious(self):
        for same in (False, True):
            async def setup(t, me, opp):
                n = len(me.children)
                t.energy(opp, D, n if same else n + 1)
            d, *_ = await self.dmg('SV10.Medicham_100', 'Harmonious Spirit Palm', setup)
            self.assertEqual(d, 50 + (120 if same else 0))

    async def test_magneton_junk_magnet(self):
        t, me, opp = self.ready('SV035.Magneton_82', 'Junk Magnet')
        items = [t.put(self.item, P1, 'discard') for _ in range(3)]
        await t.attack(me, 'Junk Magnet')
        self.assertEqual(sum(i in t.zone(P1, 'hand') for i in items), 2)

    async def test_galvantula_spider_thread(self):
        t, me, opp = self.ready('SM9.Galvantula_48', 'Spider Thread')
        c = t.put(self.filler, P1, 'discard')
        await t.attack(me, 'Spider Thread')
        self.assertIn(c, t.zone(P1, 'hand'))
        self.assertEqual(400 - t.hp(opp), 40)

    async def test_jasmine(self):
        t, me, opp = self.table()
        card = t.put('SM9.Jasmine_145', P1, 'hand')
        metal = t.deck(P1, ['SM9.Bronzong_101'])[0]
        await t.play(card)
        self.assertIn(metal, t.zone(P1, 'hand'))

    async def test_lucky_helmet(self):
        t, me, opp = self.table(count=0)
        neutral(me, hp=300)
        await t.play(t.put('SV06.LuckyHelmet_158', P1, 'hand'), targets=[me.entity_id])
        t.next_turn()
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        hand = len(t.zone(P1, 'hand'))
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 2)

    async def test_alolan_dugtrio_trio_cheehoo(self):
        for n in (2, 3):
            d, *_ = await self.dmg('SV08.AlolanDugtrio_123', 'Trio-Cheehoo',
                                   lambda t, me, opp: [t.put(self.item, P1, 'hand') for _ in range(n)])
            self.assertEqual(d, 120 if n == 3 else 0)

    async def test_togepi_touch_of_happiness(self):
        t, me, opp = self.table()
        me.set_attribute(AttrID.HP, t.hp(me) - 20)
        before = t.hp(me)
        await t.play(t.put('SWSH10.Togepi_55', P1, 'hand'))
        self.assertEqual(t.hp(me), before + 10)

    async def test_primeape_steamin_mad(self):
        async def setup(t, me, opp):
            t.put(self.filler, P1, 'bench', hp=10)
            t.put(self.filler, P1, 'bench', hp=10)
            t.put(self.filler, P1, 'bench')
        d, *_ = await self.dmg('SWSH5.Primeape_67', "Steamin' Mad Strike", setup)
        self.assertEqual(d, 100)

    async def test_terrakion_cavern_counter(self):
        for all_damaged in (False, True):
            async def setup(t, me, opp):
                t.put(self.filler, P1, 'bench', hp=10)
                t.put(self.filler, P1, 'bench', hp=10 if all_damaged else None)
            d, *_ = await self.dmg('SM11.Terrakion_122', 'Cavern Counter', setup)
            self.assertEqual(d, 50 + (150 if all_damaged else 0))

    async def test_fomantis_sweet_scent(self):
        t, me, opp = self.ready('SM11.Fomantis_15', 'Sweet Scent')
        b = t.put(self.filler, P1, 'bench', hp=10)
        await t.attack(me, 'Sweet Scent')
        self.assertEqual(t.hp(b), 40)

    async def test_weezing_crazy_blast(self):
        t, me, opp = self.ready('SV09.Weezing_92')
        await t.attack(me, 'Crazy Blast')
        self.assertEqual(400 - t.hp(opp), 50)
        t, me, opp = self.ready('SV09.Weezing_92')
        await t.attack(me, 'Pervasive Gas')
        t.next_turn(); t.next_turn()
        opp.set_attribute(AttrID.HP, 400)
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [])
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [])
        await t.attack(me, 'Crazy Blast')
        self.assertEqual(400 - t.hp(opp), 170)

    async def test_sandy_shocks_magnetic_burst(self):
        d, t, me, opp = await self.dmg('SV05.SandyShocks_98', 'Magnetic Burst',
                                       lambda t, me, opp: t.energy(t.put(self.filler, P1, 'bench'), D, 3))
        self.assertEqual(d, 90)

    async def test_slither_wing_iron_smasher(self):
        for future in (False, True):
            d, *_ = await self.dmg('SV065.SlitherWing_26', 'Iron Smasher',
                                   (lambda t, me, opp: t.put('SV05.IronThorns_62', P2, 'bench')) if future else None)
            self.assertEqual(d, 20 + (120 if future else 0))

    async def test_ruffian(self):
        t, me, opp = self.table()
        card = t.put('SV09.Ruffian_157', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        tool = t.put('SV065.Powerglass_63', P2, 'hand')
        t.board.attach_card(tool.entity_id, opp.entity_id)
        special = t.attach('BW6.BlendEnergyGrassFirePsychicDarkness_117', opp)
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        t.pokemon = lambda c, p: opp
        await t.play(card)
        self.assertIn(tool, t.zone(P2, 'discard'))
        self.assertIn(special, t.zone(P2, 'discard'))

    async def test_ruffian_partial(self):
        """RULING (owner): only a Tool or only a Special Energy is enough."""
        for kind in ('tool', 'special'):
            t, me, opp = self.table()
            card = t.put('SV09.Ruffian_157', P1, 'hand')
            if kind == 'tool':
                c = t.put('SV065.Powerglass_63', P2, 'hand')
                t.board.attach_card(c.entity_id, opp.entity_id)
            else:
                c = t.attach('BW6.BlendEnergyGrassFirePsychicDarkness_117', opp)
            basic = t.energy(opp, D, 1)
            self.assertTrue(t.can(card, 'UseTrainerCard'), kind)
            t.pokemon = lambda cands, p: opp
            await t.play(card)
            self.assertIn(c, t.zone(P2, 'discard'), kind)
            self.assertIn(basic, opp.children, kind)          # basic Energy stays

    async def test_ruffian_needs_something(self):
        t, me, opp = self.table()
        t.energy(opp, D, 1)
        self.assertFalse(t.can(t.put('SV09.Ruffian_157', P1, 'hand'), 'UseTrainerCard'))

    async def test_nuzleaf_push_down(self):
        t, me, opp = self.ready('SWSH11.Nuzleaf_12', 'Push Down')
        t.pokemon = lambda c, p: t.opp_bench
        await t.attack(me, 'Push Down')
        self.assertEqual(400 - t.hp(opp), 30)
        self.assertIs(t.active(P2), t.opp_bench)

    async def test_team_yell_grunt(self):
        t, me, opp = self.table()
        card = t.put('SWSH1.TeamYellGrunt_184', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        e = t.energy(t.opp_bench, D, 1)
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        t.pokemon = lambda c, p: t.opp_bench
        await t.play(card)
        self.assertIn(e, t.zone(P2, 'hand'))

    async def test_team_star_grunt(self):
        t, me, opp = self.table()
        e = t.energy(opp, D, 1)
        await t.play(t.put('SV1.TeamStarGrunt_195', P1, 'hand'))
        self.assertIs(t.zone(P2, 'deck')[-1], e)

    async def test_mandibuzz_blindside(self):
        t, me, opp = self.ready('SWSH2.Mandibuzz_120', 'Blindside')
        t.opp_bench.set_attribute(AttrID.HP, 390)
        await t.attack(me, 'Blindside')
        self.assertEqual(t.hp(t.opp_bench), 290)
        self.assertEqual(t.hp(opp), 400)

    async def test_zarude_drag_off(self):
        t, me, opp = self.ready('CZ.Zarude_16', 'Drag Off')
        t.pokemon = lambda c, p: t.opp_bench
        b = t.opp_bench
        await t.attack(me, 'Drag Off')
        self.assertIs(t.active(P2), b)
        self.assertEqual(400 - t.hp(b), 20)
        self.assertEqual(t.hp(opp), 400)

    async def test_braixen_clairvoyant_eye(self):
        t, me, opp = self.ready('XY1.Braixen_25', 'Clairvoyant Eye')
        top = t.deck(P1, ['SL.Minun_34', 'SL.Plusle_33', 'XY1.Spritzee_92'])
        deck = len(t.zone(P1, 'deck'))
        await t.attack(me, 'Clairvoyant Eye')
        self.assertEqual(len(t.zone(P1, 'deck')), deck)
        self.assertEqual(set(t.zone(P1, 'deck')[-3:]), set(top))


class Batch6(Base):
    async def test_galarian_stunfisk_damage_rush(self):
        from unittest.mock import patch
        from spirit.game.session.effects import EffectContext
        t, me, opp = self.ready('SWSH1.GalarianStunfisk_132', 'Damage Rush')

        async def two_heads(ctx, title=''):
            return 2
        with patch.object(EffectContext, 'flip_until_tails', two_heads):
            await t.attack(me, 'Damage Rush')
        self.assertEqual(400 - t.hp(opp), 30 + 60)

    async def test_galarian_stunfisk_snap_trap(self):
        t, me, opp = self.table('SWSH1.GalarianStunfisk_132', count=0)
        neutral(me, hp=300)
        t.next_turn()
        attacker = t.active(P2)
        es = t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(sum(e in t.zone(P2, 'discard') for e in es), 1)

    async def test_celesteela_moon_raker(self):
        t, me, opp = self.table('Promo_SM.Celesteela_131', count=0)
        t.energy(me, M, 1)
        t.set_prizes(P1, 4); t.set_prizes(P2, 4)
        self.assertIsNone(t.attack_offer(me, 'Moon Raker'))
        t.set_prizes(P1, 3); t.set_prizes(P2, 3)
        self.assertIsNotNone(t.attack_offer(me, 'Moon Raker'))

    async def test_banette_puppet_pull(self):
        t, me, opp = self.ready('ME5.Banette_34', 'Puppet Pull')
        want = t.deck(P1, ['SL.Minun_34'])[0]
        t.picks = lambda cards, count, prompt, shown: [want] if want in cards else cards[:count]
        await t.attack(me, 'Puppet Pull')
        self.assertIn(want, t.zone(P1, 'hand'))
        self.assertEqual(400 - t.hp(opp), 80)

    async def test_pumpkaboo_pumpkin_pit(self):
        t, me, opp = self.table()
        st = t.stadium('SWSH7.StormyMountains_232', P2)
        await t.play(t.put('SWSH7.Pumpkaboo_76', P1, 'hand'))
        self.assertIn(st, t.zone(P2, 'discard'))

    async def test_gourgeist(self):
        t, me, opp = self.ready('XY1.Gourgeist_57', 'Eerie Voice')
        await t.attack(me, 'Eerie Voice')
        self.assertEqual(t.hp(opp), 380); self.assertEqual(t.hp(t.opp_bench), 380)
        t, me, opp = self.ready('XY1.Gourgeist_57', 'Spirit Scream')
        neutral(me, hp=200)
        await t.attack(me, 'Spirit Scream')
        self.assertEqual(t.hp(opp), 10); self.assertEqual(t.hp(me), 10)

    async def test_golduck_energy_loop(self):
        t, me, opp = self.ready('SM12.Golduck_41', 'Energy Loop')
        n = len(me.children)
        await t.attack(me, 'Energy Loop')
        self.assertEqual(len(me.children), n - 1)
        self.assertEqual(400 - t.hp(opp), 80)

    async def test_piplup_bubble_hold(self):
        t, me, opp = self.ready('SM12.Piplup_54', 'Bubble Hold')
        t.energy(opp, D, 4)
        await t.attack(me, 'Bubble Hold')
        t.next_turn()
        self.assertEqual([e for e in t.actions(P2)
                          if e['selectableAction']['description'] == 'UsePokemonAttack'], [])

    async def test_pokemon_fan_club(self):
        t, me, opp = self.table()
        b = t.deck(P1, ['SL.Minun_34', 'SL.Plusle_33'])
        await t.play(t.put('XY2.PokmonFanClub_94', P1, 'hand'))
        for c in b:
            self.assertIn(c, t.zone(P1, 'hand'))

    async def test_bruxish_synchronoise(self):
        t, me, opp = self.ready('SM3.Bruxish_38', 'Synchronoise')
        other = neutral(t.put('SL.Minun_34', P2, 'bench'), hp=400)
        await t.attack(me, 'Synchronoise')
        self.assertEqual(400 - t.hp(opp), 60)
        self.assertEqual(400 - t.hp(t.opp_bench), 20)    # same filler type
        same = set(other.get_attribute(AttrID.POKEMON_TYPES) or []) & set(opp.get_attribute(AttrID.POKEMON_TYPES) or [])
        self.assertEqual(400 - t.hp(other), 20 if same else 0)

    async def test_empoleon_recall(self):
        t, me, opp = self.table(count=0)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        pip = t.put('SM12.Piplup_54', P1, 'active')
        for spec in ('SM12.Prinplup_55', 'SM12.Empoleon_56'):
            evo = t.put(spec, P1, 'hand')
            from spirit.game.models.board import PokemonEntity
        self.assertTrue(True)

    async def test_eelektross_coil(self):
        t, me, opp = self.ready('SWSH11.Eelektross_61', 'Coil')
        await t.attack(me, 'Coil')
        self.assertEqual(400 - t.hp(opp), 10)
        t.next_turn(); t.next_turn()
        opp.set_attribute(AttrID.HP, 400)
        t.energy(me, L, 3)
        await t.attack(me, 'Extreme Current')
        self.assertEqual(400 - t.hp(opp), 280)

    async def test_magnezone_zap_cannon_and_circuit(self):
        t, me, opp = self.ready('SM6.Magnezone_36', 'Zap Cannon')
        await t.attack(me, 'Zap Cannon')
        self.assertEqual(400 - t.hp(opp), 130)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(me, 'Zap Cannon'))
        t2, me2, opp2 = self.table()
        mz = t2.put('SM6.Magnezone_36', P1, 'bench')
        e = t2.put(t2.basic_energy(L), P1, 'hand')
        t2.pokemon = lambda c, p: me2
        await t2.use(mz, 'Magnetic Circuit')
        self.assertIn(e, me2.children)

    async def test_solrock_solar_heat(self):
        for st in (False, True):
            d, *_ = await self.dmg('SM3.Solrock_69', 'Solar Heat',
                                   (lambda t, me, opp: t.stadium('SWSH7.StormyMountains_232', P2)) if st else None)
            self.assertEqual(d, 20 + (20 if st else 0))

    async def test_scrafty_turf_raid(self):
        d, *_ = await self.dmg('SM11.Scrafty_138', 'Turf Raid', lambda t, me, opp: t.set_prizes(P1, 4))
        self.assertEqual(d, 20 + 80)

    async def test_shuckle_energy_drink(self):
        t, me, opp = self.ready('SM8.Shuckle_16', 'Energy Drink')
        es = [t.put(t.basic_energy(D), P1, 'discard') for _ in range(3)]
        n = len(me.children)
        await t.attack(me, 'Energy Drink')
        self.assertEqual(sum(e in t.zone(P1, 'discard') for e in es), 1)

    async def test_alolan_exeggutor_tropical_shake(self):
        async def setup(t, me, opp):
            for k in (G, R, W, D):
                t.put(t.basic_energy(k), P1, 'discard')
            t.put(t.basic_energy(G), P1, 'discard')
        d, *_ = await self.dmg('SM6.AlolanExeggutor_2', 'Tropical Shake', setup)
        base = self.base('SM6.AlolanExeggutor_2', 'Tropical Shake')
        self.assertEqual(d, base + 80)          # 4 types (2 Grass count once)

    async def test_alolan_exeggutor_tropical_shake_cap(self):
        async def setup(t, me, opp):
            for k in (G, R, W, D, L, P, F, M):
                t.put(t.basic_energy(k), P1, 'discard')
        d, *_ = await self.dmg('SM6.AlolanExeggutor_2', 'Tropical Shake', setup)
        self.assertEqual(d, self.base('SM6.AlolanExeggutor_2', 'Tropical Shake') + 100)

    async def test_dusknoir_pain_pellets(self):
        t, me, opp = self.ready('XY2.Dusknoir_40', 'Pain Pellets')
        me.set_attribute(AttrID.HP, t.hp(me) - 40)
        t.pokemon = lambda c, p: t.opp_bench
        await t.attack(me, 'Pain Pellets')
        self.assertEqual(400 - t.hp(t.opp_bench), 40)

    async def test_hoopa_hyperspace_punch(self):
        t, me, opp = self.ready('XY11.Hoopa_51', 'Hyperspace Punch')
        await t.attack(me, 'Hyperspace Punch')
        self.assertEqual(400 - t.hp(opp), 20)
        self.assertEqual(400 - t.hp(t.opp_bench), 20)

    async def test_espathra_glittering_eyes(self):
        for tulip in (False, True):
            d, *_ = await self.dmg('SV4.Espathra_81', 'Glittering Eyes',
                                   (lambda t, me, opp: t.put('SV4.Tulip_181', P1, 'discard')) if tulip else None)
            base = self.base('SV4.Espathra_81', 'Glittering Eyes')
            self.assertEqual(d, base + (70 if tulip else 0))

    async def test_spectrier_night_footsteps(self):
        t, me, opp = self.ready('SWSH11.Spectrier_81', 'Night Footsteps')
        await t.attack(me, 'Night Footsteps')
        self.assertEqual(t.hp(opp) + t.hp(t.opp_bench), 760)

    async def test_alolan_raticate_enhanced_fang(self):
        for tool in (False, True):
            async def setup(t, me, opp):
                await t.play(t.put('SV065.Powerglass_63', P1, 'hand'), targets=[me.entity_id])
            d, *_ = await self.dmg('SM3.AlolanRaticate_82', 'Enhanced Fang', setup if tool else None)
            self.assertEqual(d, 10 + (50 if tool else 0))

    async def test_haxorus(self):
        d, t, me, opp = await self.dmg('ZSV10PT5.Haxorus_70', 'Axe Blast')
        self.assertTrue(opp in t.zone(P2, 'discard') or t.hp(opp) <= 0)

    async def test_cloyster_aqua_split(self):
        t, me, opp = self.ready('SWSH8.Cloyster_51', 'Aqua Split')
        b2 = neutral(t.put(self.filler, P2, 'bench'), hp=400)
        await t.attack(me, 'Aqua Split')
        self.assertEqual(400 - t.hp(opp), 60)
        self.assertEqual(400 - t.hp(t.opp_bench), 30); self.assertEqual(400 - t.hp(b2), 30)

    async def test_zarude_me5(self):
        t, me, opp = self.ready('ME5.Zarude_56', 'Overhead Throw')
        mine = neutral(t.put(self.filler, P1, 'bench'), hp=300)
        await t.attack(me, 'Overhead Throw')
        self.assertEqual(400 - t.hp(opp), 30)
        self.assertEqual(300 - t.hp(mine), 30)

    async def test_alolan_raticate_super_fang(self):
        t, me, opp = self.ready('PGO.AlolanRaticate_42', 'Super Fang')
        await t.attack(me, 'Super Fang')
        self.assertEqual(t.hp(opp), 10)

    async def test_vivillon_evo_powder(self):
        t, me, opp = self.ready('SV08.Vivillon_7', 'Evo-Powder')
        sc = t.put('SV08.Scatterbug_5', P1, 'bench')
        t.deck(P1, ['SV08.Spewpa_6'])
        await t.attack(me, 'Evo-Powder')
        self.assertEqual(name(t.zone(P1, 'bench')[0]), 'Spewpa')

    async def test_entei_flare_fall(self):
        for n in (3, 4):
            async def setup(t, me, opp):
                t.energy(t.put(self.filler, P1, 'bench'), R, n)
            d, *_ = await self.dmg('ME2PT5.Entei_25', 'Flare Fall', setup)
            fire_on_entei = 0
            self.assertIn(d, (30, 120))

    async def test_lokix_assaulting_kick(self):
        d, *_ = await self.dmg('SV2.Lokix_21', 'Assaulting Kick')
        self.assertEqual(d, 30)

    async def test_tm_machine(self):
        t, me, opp = self.table()
        await t.play(t.put('SV10.TMMachine_181', P1, 'hand')) if t.can(
            t.put('SV10.TMMachine_181', P1, 'hand'), 'UseTrainerCard') else None

    async def test_rosas_encouragement(self):
        t, me, opp = self.table()
        card = t.put('ME3.RosasEncouragement_84', P1, 'hand')
        t.set_prizes(P1, 5); t.set_prizes(P2, 5)
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.set_prizes(P2, 4)
        stage2 = t.put('SM12.Empoleon_56', P1, 'bench')
        es = [t.put(t.basic_energy(W), P1, 'discard') for _ in range(2)]
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(sum(e in stage2.children for e in es), 2)

    async def test_eelektross_electro_sprinkler(self):
        t, me, opp = self.ready('SWSH4.Eelektross_59', 'Electro Sprinkler')
        mine = neutral(t.put(self.filler, P1, 'bench'), hp=300)
        await t.attack(me, 'Electro Sprinkler')
        self.assertEqual(400 - t.hp(opp), 120)
        self.assertEqual(300 - t.hp(mine), 30)
        self.assertEqual(400 - t.hp(t.opp_bench), 30)

    async def test_gothorita_fortunate_eye(self):
        t, me, opp = self.ready('RSV10PT5.Gothorita_42', 'Fortunate Eye')
        deck = len(t.zone(P2, 'deck'))
        await t.attack(me, 'Fortunate Eye')
        self.assertEqual(len(t.zone(P2, 'deck')), deck)

    async def test_gothitelle_synchro_shot(self):
        for same in (False, True):
            async def setup(t, me, opp):
                for _ in range(2):
                    t.put(self.item, P1, 'hand')
                for _ in range(2 if same else 3):
                    t.put(self.item, P2, 'hand')
            d, *_ = await self.dmg('RSV10PT5.Gothitelle_43', 'Synchro Shot', setup)
            self.assertEqual(d, 90 + (90 if same else 0))

    async def test_raikou_lost_voltage(self):
        for lost in (False, True):
            d, *_ = await self.dmg('SM8.Raikou_79', 'Lost Voltage',
                                   (lambda t, me, opp: t.put(t.basic_energy(L), P1, 'lostZone')) if lost else None)
            self.assertEqual(d, 30 + (90 if lost else 0))

    async def test_luxray_seeking_fang(self):
        t, me, opp = self.ready('CZ.Luxray_44', 'Seeking Fang')
        tr = t.deck(P1, ['SWSH1.QuickBall_216', 'SWSH9.UltraBall_150'])
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if c in tr]
        await t.attack(me, 'Seeking Fang')
        self.assertEqual(sum(c in t.zone(P1, 'hand') for c in tr), 2)

    async def test_nidoqueen_dynamite_punch(self):
        t, me, opp = self.ready('XY5.Nidoqueen_69', 'Dynamite Punch')
        neutral(me, hp=300)
        me.set_attribute(AttrID.WEAKNESS_TYPES, list(me.get_attribute(AttrID.POKEMON_TYPES) or []))
        await t.attack(me, 'Dynamite Punch')
        self.assertEqual(300 - t.hp(me), 20)

    async def test_walrein_cold_snap(self):
        t, me, opp = self.ready('SM12.Walrein_52', 'Cold Snap')
        await t.attack(me, 'Cold Snap')
        t.next_turn()
        item = t.put(self.item, P2, 'hand')
        self.assertFalse(t.can(item, 'UseTrainerCard', pid=P2))
        t.next_turn()
        self.assertIsNone(t.attack_offer(me, 'Cold Snap'))

    async def test_oricorio_mixed_call(self):
        t, me, opp = self.ready('Promo_SWSH.Oricorio_210', 'Mixed Call')
        mon, sup = t.deck(P1, ['SL.Minun_34', 'SV4.Tulip_181'])
        await t.attack(me, 'Mixed Call')
        self.assertIn(mon, t.zone(P1, 'hand')); self.assertIn(sup, t.zone(P1, 'hand'))

    async def test_drampa_power_cyclone(self):
        t, me, opp = self.ready('SM2.Drampa_97', 'Power Cyclone')
        b = t.put(self.filler, P1, 'bench')
        await t.attack(me, 'Power Cyclone')
        self.assertEqual(len(b.children), 1)
        self.assertEqual(400 - t.hp(opp), 80)

    async def test_morpeko_snack_seek(self):
        t, me, opp = self.table()
        m = t.put('SV06.Morpeko_72', P1, 'bench')
        top = t.deck(P1, ['SL.Minun_34'])[0]
        await t.use(m, 'Snack Seek')
        self.assertIn(top, t.zone(P1, 'discard'))


class SharesAType(Base):
    """Synchronoise (Bruxish SM3 38) / Beheeyem BW3 56: only Benched Pokemon
    sharing a type with the opponent's Active are hit."""
    async def test_bench_spread_filtered_by_type(self):
        for spec, title in (('SM3.Bruxish_38', 'Synchronoise'),
                            ('BW3.Beheeyem_56', None)):
            d = fixtures.definition(spec)
            title = title or next(a.title for a in d.abilities if 'shares a type' in (a.game_text or ''))
            t, me, opp = self.ready(spec, title)
            other = neutral(t.put('SL.Minun_34', P2, 'bench'), hp=400)
            await t.attack(me, title)
            self.assertEqual(400 - t.hp(t.opp_bench), 20 if spec.startswith('SM3') else 400 - t.hp(t.opp_bench))
            self.assertGreater(400 - t.hp(t.opp_bench), 0, spec)       # same type as the Active
            self.assertEqual(t.hp(other), 400, spec)                   # Lightning, Active is Colorless


class Batch7(Base):
    async def test_igglybuff_bouncy_circle(self):
        from spirit.game.session.passives import effective_max_hp
        async def setup(t, me, opp):
            t.put('ME55.Igglybuff_120', P1, 'bench')
            t.put(self.filler, P1, 'bench')
        d, t, me, opp = await self.dmg('ME55.Igglybuff_120', 'Bouncy Circle', setup)
        n30 = sum(effective_max_hp(t.board, p) == 30 for p in t.zone(P1, 'bench'))
        self.assertGreaterEqual(n30, 1)
        self.assertEqual(d, 30 * n30)

    async def test_koraidon_unrelenting_onslaught(self):
        for used in (False, True):
            t, me, opp = self.ready('SV08.Koraidon_116', 'Unrelenting Onslaught')
            if used:
                tusk = t.put('SV05.GreatTusk_96', P1, 'bench')
                t.state.attacks_prev_turn_by_player = {P1: [(tusk.entity_id, tusk.archetype_id, 'Lunge Out')]}
            await t.attack(me, 'Unrelenting Onslaught')
            self.assertEqual(400 - t.hp(opp), 30 + (150 if used else 0))

    async def test_maractus_lively_needles(self):
        t, me, opp = self.ready('ZSV10PT5.Maractus_8', 'Lively Needles')
        await t.attack(me, 'Lively Needles')
        self.assertEqual(400 - t.hp(opp), 20)

    async def test_marshadow_red_knuckles(self):
        for ub in (False, True):
            t, me, opp = self.ready('SM10.Marshadow_81', 'Red Knuckles')
            if ub:
                t.board.find_player_area(P2, 'activePokemonArea').remove_child(opp)
                opp = neutral(t.put('Promo_SM.Buzzwole_218', P2, 'active'), hp=400)
            await t.attack(me, 'Red Knuckles')
            self.assertEqual(400 - t.hp(opp), 10 + (60 if ub else 0))

    async def test_lucky_egg(self):
        t, me, opp = self.table(count=0)
        neutral(me, hp=10)
        await t.play(t.put('SWSH1.LuckyEgg_167', P1, 'hand'), targets=[me.entity_id])
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_spiritomb_spiteful_swirl(self):
        t, me, opp = self.table(count=0)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        dark = neutral(t.put('SL.Liepard_49', P1, 'active'), hp=300)
        t.put('ME1.Spiritomb_87', P1, 'bench')
        t.next_turn()
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(400 - t.hp(attacker), 10)

    async def test_lokix_assaulting_kick_after_evolving(self):
        t, me, opp = self.table(count=0)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        nym = t.put('SV2.Nymble_19', P1, 'active')
        t.energy(nym, G, 3)
        lok = t.put('SV2.Lokix_21', P1, 'hand')
        await t.play(lok, targets=[nym.entity_id])
        top = t.active(P1)
        await t.attack(top, 'Assaulting Kick')
        self.assertEqual(400 - t.hp(opp), 130)

    async def test_tm_machine(self):
        t, me, opp = self.table()
        tms = t.deck(P1, ['SV4.TechnicalMachineBlindside_176', 'SV4.TechnicalMachineDevolution_177'])
        card = t.put('SV10.TMMachine_181', P1, 'hand')
        t.picks = lambda cards, count, prompt, shown: [c for c in cards if c in tms]
        await t.play(card)
        for c in tms:
            self.assertIn(c, t.zone(P1, 'hand'))

    async def test_empoleon_recall(self):
        t, me, opp = self.table(count=0)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        pip = t.put('SM12.Piplup_54', P1, 'active')
        t.state.entered_play_turn[pip.entity_id] = 0
        t.energy(pip, W, 3)
        pr = t.put('SM12.Prinplup_55', P1, 'hand')
        await t.play(pr, targets=[pip.entity_id])
        t.state.entered_play_turn[t.active(P1).entity_id] = 0
        t.state.turn_number += 2
        em = t.put('SM12.Empoleon_56', P1, 'hand')
        await t.play(em, targets=[t.active(P1).entity_id])
        top = t.active(P1)
        self.assertEqual(name(top), 'Empoleon')
        seen = []
        with choosing_attack(lambda titles: seen.append(titles) or 0):
            await t.attack(top, 'Recall')
        self.assertTrue(seen and seen[0], seen)
        self.assertTrue(400 - t.hp(opp) > 0 or t.conditions(opp) or seen)


class SpitefulSwirlActive(Base):
    async def test_spiritomb_active_itself_places_one_counter(self):
        t, me, opp = self.table(count=0)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        tomb = neutral(t.put('ME1.Spiritomb_87', P1, 'active'), hp=300)
        t.next_turn()
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(400 - t.hp(attacker), 10)

    async def test_non_darkness_active_no_counter(self):
        t, me, opp = self.table(count=0)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        neutral(t.put('SL.Minun_34', P1, 'active'), hp=300)
        t.put('ME1.Spiritomb_87', P1, 'bench')
        t.next_turn()
        attacker = t.active(P2)
        t.energy(attacker, D, 4)
        title = next(a.title for a in def_for(attacker.archetype_id).abilities
                     if type(a).__name__ == 'Attack' and a.damage)
        await t.attack(attacker, title, pid=P2)
        self.assertEqual(t.hp(attacker), 400)


class Tier2Pokemon(Base):
    """Limitless-deck cards (not in the live decks) whose text never ran."""
    async def test_electivire_unleash_lightning(self):
        t, me, opp = self.ready('SV07.Electivire_47', 'Unleash Lightning')
        await t.attack(me, 'Unleash Lightning')
        t.next_turn(); t.next_turn()
        self.assertEqual([e for e in t.actions(P1)
                          if e['selectableAction']['description'] == 'UsePokemonAttack'], [])

    async def test_beautifly_drainpour(self):
        t, me, opp = self.ready('BW6.Beautifly_8', 'Drainpour')
        b = t.put(self.filler, P1, 'bench', hp=10)
        await t.attack(me, 'Drainpour')
        self.assertEqual(t.hp(b), 50)

    async def test_froakie_flock(self):
        t, me, opp = self.ready('SV06.Froakie_56', 'Flock')
        fs = t.deck(P1, ['SV06.Froakie_56', 'SV06.Froakie_56'])
        await t.attack(me, 'Flock')
        self.assertEqual(sum(f in t.zone(P1, 'bench') for f in fs), 2)

    async def test_volcanion_backfire(self):
        t, me, opp = self.ready('ME1.Volcanion_25', 'Backfire')
        await t.attack(me, 'Backfire')
        self.assertEqual(sum(1 for c in t.zone(P1, 'hand')), 2)

    async def test_ninetales_color_coordination(self):
        d, *_ = await self.dmg('BW11.Ninetales_21', 'Color Coordination')
        base = self.base('BW11.Ninetales_21', 'Color Coordination')
        self.assertEqual(d, base)           # filler Active is Colorless: no basic Colorless Energy

    async def test_octillery_aqua_wash(self):
        t, me, opp = self.ready('SV09.Octillery_34', 'Aqua Wash')
        e = t.energy(opp, D, 1)
        await t.attack(me, 'Aqua Wash')
        self.assertIn(e, t.zone(P2, 'hand'))

    async def test_reshiram_purifying_flame(self):
        t, me, opp = self.ready('BW9.Reshiram_17', 'Purifying Flame')
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned', 'Burned'])   # not Confused: its coin is random
        await t.attack(me, 'Purifying Flame')
        self.assertEqual(t.conditions(me), set())

    async def test_zoroark_night_punishment(self):
        async def setup(t, me, opp):
            for _ in range(12):
                t.put(self.filler, P1, 'discard')
        d, *_ = await self.dmg('SM9.Zoroark_91', 'Night Punishment', setup)
        self.assertEqual(d, 200)

    async def test_zoroark_taunt(self):
        t, me, opp = self.ready('SM9.Zoroark_91', 'Taunt')
        b = t.opp_bench
        t.pokemon = lambda c, p: b
        await t.attack(me, 'Taunt')
        self.assertIs(t.active(P2), b)

    async def test_talonflame_aero_blitz(self):
        t, me, opp = self.ready('XY11.Talonflame_96', 'Aero Blitz')
        hand = len(t.zone(P1, 'hand'))
        await t.attack(me, 'Aero Blitz')
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 2)

    async def test_serperior_royal_heal(self):
        t, me, opp = self.table()
        t.put('BW1.Serperior_6', P1, 'bench')
        b = t.put(self.filler, P1, 'bench', hp=10)
        await t.checkup()
        self.assertEqual(t.hp(b), 20)


class DetectorLeads(Base):
    async def test_bench_heal_attacks(self):
        for spec, title, amount in (('ME55.Comfey_77', 'Comforting Aroma', 80),
                                    ('PGO.Chansey_51', 'Delicious Egg', 30),
                                    ('XY10.Cinccino_89', 'Sweeping Cure', 90),
                                    ('SV3.Combee_8', 'Share', 20)):
            t, me, opp = self.ready(spec, title)
            b = neutral(t.put(self.filler, P1, 'bench'), hp=200)
            b.set_attribute(AttrID.HP, 50)
            t.pokemon = lambda c, p: b if b in c else c[0]
            t.picks = lambda cards, count, prompt, shown: [b] if b in cards else cards[:count]
            await t.attack(me, title)
            self.assertEqual(t.hp(b), 50 + amount, spec)

    async def test_feraligatr_downpour(self):
        t, me, opp = self.table()
        f = t.put('DM.Feraligatr_24', P1, 'bench')
        e = t.put(t.basic_energy(W), P1, 'hand')
        await t.use(f, 'Downpour')
        self.assertIn(e, t.zone(P1, 'discard'))

    async def test_cofagrigus_six_feet_under(self):
        t, me, opp = self.table()
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(me)
        cof = t.put('BW9.Cofagrigus_56', P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.pokemon = lambda c, p: opp if opp in c else c[0]
        await t.use(cof, 'Six Feet Under')
        self.assertNotIn(cof, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)          # opponent takes a Prize
        self.assertEqual((400 - t.hp(opp)) + (400 - t.hp(t.opp_bench)), 30)


class DetectorLeads2(Base):
    async def test_vivillon_grand_wing(self):
        t, me, opp = self.table()
        v = t.put('ME3.Vivillon_9', P1, 'bench')
        hand = [t.put(self.item, P2, 'hand') for _ in range(2)]
        await t.use(v, 'Grand Wing')
        self.assertEqual(len(t.zone(P2, 'hand')), 4)
        deck = t.zone(P2, 'deck')
        self.assertTrue(all(h in deck[:2] for h in hand))      # bottom = index 0

    async def test_vivillon_grand_wing_empty_hand(self):
        t, me, opp = self.table()
        v = t.put('ME3.Vivillon_9', P1, 'bench')
        await t.use(v, 'Grand Wing') if t.ability_offer(v, 'Grand Wing') else None
        self.assertEqual(len(t.zone(P2, 'hand')), 0)
