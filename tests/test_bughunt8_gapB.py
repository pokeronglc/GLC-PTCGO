"""Bug hunt round 8, gap group B: never-exercised text of Absol XY6 40,
Blend Energy WLFM / GFPD, Exp. Share, Volcanion ME1 25, Cinderace ME1 28,
Powerglass, Punk Helmet, Kecleon SM7 122, Latios ME1 101, Rapid Strike Scroll
of Swirls and Cursed Shovel -- each checked against its printed text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_pokemon_types, energy_provided_options
from spirit.tools.effect_smoke import P1, P2

W, L, F, M = (PokemonTypes.WATER, PokemonTypes.LIGHTNING,
              PokemonTypes.FIGHTING, PokemonTypes.METAL)
G, R, P, D = (PokemonTypes.GRASS, PokemonTypes.FIRE,
              PokemonTypes.PSYCHIC, PokemonTypes.DARKNESS)
C = PokemonTypes.COLORLESS

ABSOL = 'XY6.Absol_40'
SNEASEL = 'SM11.Sneasel_131'                    # plain Darkness "Slash" 30 (control)
BLEND_WLFM = 'BW6.BlendEnergyWaterLightningFightingMetal_118'
BLEND_GFPD = 'BW6.BlendEnergyGrassFirePsychicDarkness_117'
DRATINI = 'ME2PT5.Dratini_150'                  # Headbutt {W}{L}
AXEW = 'SV065.Axew_44'                          # Sharp Fang {F}{M}
APPLIN = 'SV06.Applin_126'                      # Rolling Tackle {G}{R}
NOIBAT = 'ME2PT5.Noibat_156'                    # Bite {P}{D}
EXP_SHARE = 'BW4.ExpShare_87'
EXP_SHARE_REPRINTS = ['DV.ExpShare_18', 'SM1.ExpShare_118', 'SV1.ExpShare_174',
                      'SWSH5.ExpShare_126', 'SWSH5.ExpShare_180', 'XY5.ExpShare_128']
VOLCANION = 'ME1.Volcanion_25'
CINDERACE = 'ME1.Cinderace_28'
POWERGLASS, POWERGLASS_2 = 'SV065.Powerglass_63', 'SV065.Powerglass_97'
PUNK_HELMET, PUNK_HELMET_2 = 'ME2.PunkHelmet_92', 'ME2.PunkHelmet_121'
KECLEON = 'SM7.Kecleon_122'
UNIT_LPM = 'SM5.UnitEnergyLightningPsychicMetal_138'
UNIT_GRW = 'SM5.UnitEnergyGrassFireWater_137'
LATIOS = 'ME1.Latios_101'
SCROLL = 'SWSH5.RapidStrikeScrollofSwirls_131'
SHINX_RS = 'SWSH5.Shinx_46'                     # Basic Rapid Strike
SHOVEL = 'SWSH2.CursedShovel_157'


class GapB(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # -- helpers ----------------------------------------------------------
    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.plain(self.opp)
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    @staticmethod
    def plain(p):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1, hp=None):
        p = self.plain(t.put(spec, pid, zone, hp=hp))
        if count:
            t.energy(p, kind, count)
        return p

    def swap_opp(self, t, spec, hp=None):
        area = t.board.find_player_area(P2, 'activePokemonArea')
        area.remove_child(self.opp)
        self.opp = self.mine(t, spec, zone='active', pid=P2, hp=hp)
        return self.opp

    def filler_attack(self):
        for a in self.filler.abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t, attacker=None):
        attacker = attacker or self.opp
        title, dmg = self.filler_attack()
        t.energy(attacker, W, 5)
        t.next_turn()
        await t.attack(attacker, title, pid=P2)
        return dmg

    def is_basic(self, card, kind=None):
        kinds = [kind] if kind else list(PokemonTypes)
        return any(card.archetype_id.lower() == (self.energies.get(k.value) or '').lower()
                   for k in kinds)

    def energies_on(self, p):
        return [c for c in p.children if self.is_basic(c) or 'Energy' in (
            def_for(c.archetype_id).display_name or '')]

    def can_attack(self, t, p, title):
        return t.attack_offer(p, title) is not None

    # --- Absol XY6 40: Mach Claw -----------------------------------------------
    async def test_absol_mach_claw_ignores_resistance(self):
        t = self.table()
        absol = self.mine(t, ABSOL, D, 2)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, D.value)
        self.opp.set_attribute(AttrID.RESISTANCE_AMOUNT, 30)
        await t.attack(absol, 'Mach Claw')
        self.assertEqual(400 - t.hp(self.opp), 30)

    async def test_absol_control_resistance_does_apply_to_plain_dark_attack(self):
        """Control: the same Resistance setup does reduce a plain Darkness attack."""
        t = self.table()
        sneasel = self.mine(t, SNEASEL, D, 2)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, D.value)
        self.opp.set_attribute(AttrID.RESISTANCE_AMOUNT, 30)
        await t.attack(sneasel, 'Slash')
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_absol_mach_claw_still_applies_weakness(self):
        t = self.table()
        absol = self.mine(t, ABSOL, D, 2)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [D.value])
        await t.attack(absol, 'Mach Claw')
        self.assertEqual(400 - t.hp(self.opp), 60)

    # --- Blend Energy WLFM BW6 118 ---------------------------------------------
    async def test_blend_wlfm_provides_each_listed_type(self):
        t = self.table()
        dratini = self.mine(t, DRATINI, W, 1)                 # {W}{L}: Blend = L
        await t.play(t.put(BLEND_WLFM, P1, 'hand'), targets=[dratini.entity_id])
        self.assertTrue(self.can_attack(t, dratini, 'Headbutt'))
        t2 = self.table()
        axew = self.mine(t2, AXEW, F, 1)                      # {F}{M}: Blend = M
        await t2.play(t2.put(BLEND_WLFM, P1, 'hand'), targets=[axew.entity_id])
        self.assertTrue(self.can_attack(t2, axew, 'Sharp Fang'))

    async def test_blend_wlfm_only_one_energy_at_a_time(self):
        t = self.table()
        dratini = self.mine(t, DRATINI)
        await t.play(t.put(BLEND_WLFM, P1, 'hand'), targets=[dratini.entity_id])
        self.assertFalse(self.can_attack(t, dratini, 'Headbutt'))   # 1 card, needs 2
        t.attach(BLEND_WLFM, dratini)
        self.assertTrue(self.can_attack(t, dratini, 'Headbutt'))    # 2 Blends: W + L

    async def test_blend_wlfm_does_not_provide_other_types(self):
        t = self.table()
        applin = self.mine(t, APPLIN, R, 1)                   # {G}{R}
        await t.play(t.put(BLEND_WLFM, P1, 'hand'), targets=[applin.entity_id])
        self.assertFalse(self.can_attack(t, applin, 'Rolling Tackle'))

    async def test_blend_wlfm_is_colorless_outside_play(self):
        t = self.table()
        card = t.put(BLEND_WLFM, P1, 'hand')
        self.assertEqual(energy_provided_options(t.board, card), [[C.value]])

    # --- Blend Energy GFPD BW6 117 ---------------------------------------------
    async def test_blend_gfpd_provides_each_listed_type(self):
        t = self.table()
        applin = self.mine(t, APPLIN, R, 1)                   # {G}{R}: Blend = G
        await t.play(t.put(BLEND_GFPD, P1, 'hand'), targets=[applin.entity_id])
        self.assertTrue(self.can_attack(t, applin, 'Rolling Tackle'))
        t2 = self.table()
        noibat = self.mine(t2, NOIBAT, P, 1)                  # {P}{D}: Blend = D
        await t2.play(t2.put(BLEND_GFPD, P1, 'hand'), targets=[noibat.entity_id])
        self.assertTrue(self.can_attack(t2, noibat, 'Bite'))

    async def test_blend_gfpd_only_one_and_not_other_types(self):
        t = self.table()
        applin = self.mine(t, APPLIN)
        await t.play(t.put(BLEND_GFPD, P1, 'hand'), targets=[applin.entity_id])
        self.assertFalse(self.can_attack(t, applin, 'Rolling Tackle'))
        t2 = self.table()
        dratini = self.mine(t2, DRATINI, W, 1)                # {W}{L}: no L from GFPD
        await t2.play(t2.put(BLEND_GFPD, P1, 'hand'), targets=[dratini.entity_id])
        self.assertFalse(self.can_attack(t2, dratini, 'Headbutt'))
        self.assertEqual(energy_provided_options(t2.board, t2.put(BLEND_GFPD, P1, 'hand')),
                         [[C.value]])

    # --- Exp. Share BW4 87 -----------------------------------------------------
    async def _exp_share_ko(self, t, victim_energy=(W, W), yes=True, holder_spec=None):
        victim = self.mine(t, self.filler)
        for kind in victim_energy:
            t.energy(victim, kind)
        victim.set_attribute(AttrID.HP, 10)
        holder = self.mine(t, holder_spec or self.filler, zone='bench')
        await t.play(t.put(EXP_SHARE, P1, 'hand'), targets=[holder.entity_id])
        t.yes = yes
        await self.opp_hits(t)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        return victim, holder

    async def test_exp_share_moves_one_basic_energy(self):
        t = self.table()
        victim, holder = await self._exp_share_ko(t)
        moved = [c for c in holder.children if self.is_basic(c, W)]
        self.assertEqual(len(moved), 1)                     # only 1, not both
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_basic(c, W)), 1)

    async def test_exp_share_is_optional(self):
        t = self.table()
        _, holder = await self._exp_share_ko(t, yes=False)
        self.assertEqual([c for c in holder.children if self.is_basic(c)], [])

    async def test_exp_share_ignores_special_energy(self):
        t = self.table()
        victim = self.mine(t, self.filler)
        t.attach(BLEND_WLFM, victim)
        victim.set_attribute(AttrID.HP, 10)
        holder = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(EXP_SHARE, P1, 'hand'), targets=[holder.entity_id])
        await self.opp_hits(t)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual([c for c in holder.children
                          if 'Exp' not in (def_for(c.archetype_id).display_name or '')], [])

    async def test_exp_share_not_on_poison_knockout(self):
        t = self.table()
        victim = self.mine(t, self.filler, W, 2, hp=10)
        holder = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(EXP_SHARE, P1, 'hand'), targets=[holder.entity_id])
        victim.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.checkup()
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual([c for c in holder.children if self.is_basic(c)], [])

    async def test_exp_share_not_when_opponents_active_is_knocked_out(self):
        t = self.table()
        title, _ = self.filler_attack()
        me = self.mine(t, self.filler, W, 5)
        holder = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(EXP_SHARE, P1, 'hand'), targets=[holder.entity_id])
        t.energy(self.opp, W, 2)
        self.opp.set_attribute(AttrID.HP, 10)
        self.mine(t, self.filler, zone='bench', pid=P2)
        victim = self.opp
        await t.attack(me, title)
        self.assertNotIn(victim, t.board.pokemon_in_play(P2))
        self.assertEqual([c for c in holder.children if self.is_basic(c)], [])

    async def test_exp_share_reprints_share_effect(self):
        base = fixtures.definition(EXP_SHARE).granted_abilities[0]
        for spec in EXP_SHARE_REPRINTS:
            with self.subTest(spec=spec):
                other = fixtures.definition(spec).granted_abilities[0]
                self.assertEqual(other.trigger, base.trigger)
                self.assertEqual(other.effect.__code__.co_code, base.effect.__code__.co_code)

    # --- Volcanion ME1 25: Backfire ---------------------------------------------
    async def test_volcanion_backfire_two_fire_to_hand(self):
        t = self.table()
        volc = self.mine(t, VOLCANION, R, 3)
        hand_before = len(t.zone(P1, 'hand'))
        await t.attack(volc, 'Backfire')
        self.assertEqual(400 - t.hp(self.opp), 130)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand) - hand_before, 2)
        self.assertTrue(all(self.is_basic(c, R) for c in hand))
        self.assertEqual(len([c for c in volc.children if self.is_basic(c, R)]), 1)

    async def test_volcanion_backfire_leaves_non_fire(self):
        t = self.table()
        volc = self.mine(t, VOLCANION, R, 2)
        water = t.energy(volc, W)
        await t.attack(volc, 'Backfire')
        self.assertIn(water, volc.children)
        self.assertEqual([c for c in volc.children if self.is_basic(c, R)], [])
        self.assertEqual(sum(1 for c in t.zone(P1, 'hand') if self.is_basic(c, R)), 2)

    # --- Cinderace ME1 28: Explosiveness ----------------------------------------
    def _clear(self, t, pid=P1):
        for zone in ('hand', 'deck'):
            area = t.board.find_player_area(pid, zone if zone != 'hand' else 'hand')
            for c in list(area.children):
                area.remove_child(c)

    async def test_cinderace_explosiveness_opening_active(self):
        t = Table(self)
        self._clear(t)
        cind = t.put(CINDERACE, P1, 'hand')
        self.assertEqual(t.board.setup_active_candidates(P1), [cind])
        self.assertTrue(t.board.player_has_any_basic(P1))   # hand is not a mulligan

    async def test_cinderace_explosiveness_not_bench_nor_mid_game(self):
        t = Table(self)
        self._clear(t)
        cind = t.put(CINDERACE, P1, 'hand')
        self.assertEqual(t.board.setup_bench_candidates(P1), [])
        self.assertEqual(t.board.basic_pokemon_in_hand(P1), [])
        t.put(self.filler, P1, 'active')
        self.assertFalse(t.can(cind, 'DefaultPokemonPlayAbility'))
        # not usable as a clicked Ability either
        self.assertEqual(t.offers(cind, 'UsePokemonAbility'), [])

    # --- Powerglass SFA 63 -------------------------------------------------------
    async def _glass(self, t, zone='active', discard=(W,), yes=True, spec=POWERGLASS):
        holder = self.mine(t, self.filler, zone=zone)
        if zone == 'bench':
            self.mine(t, self.filler)
        await t.play(t.put(spec, P1, 'hand'), targets=[holder.entity_id])
        for kind in discard:
            t.put(t.basic_energy(kind), P1, 'discard')
        t.yes = yes
        return holder

    async def test_powerglass_attaches_one_basic_from_discard(self):
        t = self.table()
        holder = await self._glass(t, discard=(W, R))
        await t.checkup()
        self.assertEqual(len([c for c in holder.children if self.is_basic(c)]), 1)
        self.assertEqual(len([c for c in t.zone(P1, 'discard') if self.is_basic(c)]), 1)

    async def test_powerglass_reprint_same(self):
        t = self.table()
        holder = await self._glass(t, spec=POWERGLASS_2)
        await t.checkup()
        self.assertEqual(len([c for c in holder.children if self.is_basic(c)]), 1)

    async def test_powerglass_optional(self):
        t = self.table()
        holder = await self._glass(t, yes=False)
        await t.checkup()
        self.assertEqual([c for c in holder.children if self.is_basic(c)], [])

    async def test_powerglass_not_on_bench(self):
        t = self.table()
        holder = await self._glass(t, zone='bench')
        await t.checkup()
        self.assertEqual([c for c in holder.children if self.is_basic(c)], [])

    async def test_powerglass_not_at_end_of_opponents_turn(self):
        t = self.table()
        holder = await self._glass(t)
        t.next_turn()
        await t.checkup()
        self.assertEqual([c for c in holder.children if self.is_basic(c)], [])

    async def test_powerglass_not_special_energy(self):
        t = self.table()
        holder = await self._glass(t, discard=())
        t.put(BLEND_WLFM, P1, 'discard')
        await t.checkup()
        self.assertEqual(len(holder.children), 1)       # only the Tool

    # --- Punk Helmet PFL 92 -------------------------------------------------------
    async def test_punk_helmet_four_counters_on_attacker(self):
        t = self.table()
        absol = self.mine(t, ABSOL)
        await t.play(t.put(PUNK_HELMET, P1, 'hand'), targets=[absol.entity_id])
        await self.opp_hits(t)
        self.assertEqual(400 - t.hp(self.opp), 40)

    async def test_punk_helmet_even_if_knocked_out(self):
        t = self.table()
        absol = self.mine(t, ABSOL, hp=10)
        self.mine(t, self.filler, zone='bench')
        await t.play(t.put(PUNK_HELMET_2, P1, 'hand'), targets=[absol.entity_id])
        await self.opp_hits(t)
        self.assertNotIn(absol, t.board.pokemon_in_play(P1))
        self.assertEqual(400 - t.hp(self.opp), 40)

    async def test_punk_helmet_needs_darkness_pokemon(self):
        t = self.table()
        me = self.mine(t, self.filler)
        me.set_attribute(AttrID.HP, 400)
        await t.play(t.put(PUNK_HELMET, P1, 'hand'), targets=[me.entity_id])
        await self.opp_hits(t)
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_punk_helmet_not_on_bench(self):
        t = self.table()
        self.mine(t, self.filler).set_attribute(AttrID.HP, 400)
        absol = self.mine(t, ABSOL, zone='bench')
        await t.play(t.put(PUNK_HELMET, P1, 'hand'), targets=[absol.entity_id])
        shinx = self.swap_opp(t, SHINX_RS)
        await t.play(t.put(SCROLL, P2, 'hand'), pid=P2, targets=[shinx.entity_id])
        t.energy(shinx, F)
        t.energy(shinx, W, 2)
        shinx.set_attribute(AttrID.HP, 400)
        t.next_turn()
        await t.attack(shinx, 'Matchless Maelstrom', pid=P2)
        self.assertEqual(t.damage(absol), 30)               # bench was hit
        self.assertEqual(400 - t.hp(shinx), 0)

    # --- Kecleon CES 122: Unit Color 2 ---------------------------------------------
    async def test_kecleon_unit_color_with_unit_lpm(self):
        t = self.table()
        kec = self.mine(t, KECLEON)
        await t.play(t.put(UNIT_LPM, P1, 'hand'), targets=[kec.entity_id])
        types = effective_pokemon_types(t.board, kec)
        # Owner ruling (Oct 13): those three types AND it stays Colorless.
        self.assertEqual(sorted(types), sorted([C.value, L.value, P.value, M.value]))

    async def test_kecleon_unit_color_lightning_weakness_hits(self):
        """Being a Lightning Pokémon must matter in play: an opponent's
        Lightning-weak Pokémon takes x2 from Kecleon's Slash."""
        t = self.table()
        kec = self.mine(t, KECLEON)
        await t.play(t.put(UNIT_LPM, P1, 'hand'), targets=[kec.entity_id])
        t.energy(kec, W, 2)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])
        await t.attack(kec, 'Slash')
        self.assertEqual(400 - t.hp(self.opp), 160)

    async def test_kecleon_unit_color_without_unit_energy(self):
        t = self.table()
        kec = self.mine(t, KECLEON, W, 1)
        await t.play(t.put(UNIT_GRW, P1, 'hand'), targets=[kec.entity_id])
        types = effective_pokemon_types(t.board, kec)
        for kind in (L, P, M):
            self.assertNotIn(kind.value, types)
        self.assertEqual(types, [C.value])                 # still just Colorless

    # --- Latios ME1 101: Lustrous Assist -------------------------------------------
    async def test_latios_lustrous_assist_not_freely_usable(self):
        """Its only trigger (a Mega Latias ex moving Bench->Active) can't
        happen in the GLC pool, so it must never be offered as a plain click."""
        t = self.table()
        for zone in ('active', 'bench'):
            with self.subTest(zone=zone):
                t = self.table()
                if zone == 'bench':
                    self.mine(t, self.filler)
                lat = self.mine(t, LATIOS, zone=zone)
                benched = self.mine(t, self.filler, W, 2, zone='bench')
                self.assertIsNone(t.ability_offer(lat, 'Lustrous Assist'))
                self.assertEqual(len(benched.children), 2)

    # --- Rapid Strike Scroll of Swirls BST 131 -------------------------------------
    async def _scroll(self, t, spec=SHINX_RS, energy=(F, W, W)):
        me = self.mine(t, spec)
        for kind in energy:
            t.energy(me, kind)
        await t.play(t.put(SCROLL, P1, 'hand'), targets=[me.entity_id])
        return me

    async def test_scroll_matchless_maelstrom_hits_each_opponent(self):
        t = self.table()
        me = await self._scroll(t)
        b1 = self.mine(t, self.filler, zone='bench', pid=P2)
        b2 = self.mine(t, self.filler, zone='bench', pid=P2)
        b2.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])    # bench: no Weakness
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [L.value])  # Active: Weakness
        mine_b = self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Matchless Maelstrom')
        self.assertEqual(400 - t.hp(self.opp), 60)
        self.assertEqual(t.damage(b1), 30)
        self.assertEqual(t.damage(b2), 30)
        self.assertEqual(t.damage(mine_b), 0)
        self.assertEqual(t.damage(me), 0)

    async def test_scroll_needs_rapid_strike_holder(self):
        t = self.table()
        me = await self._scroll(t, spec=self.filler)
        self.assertIsNone(t.attack_offer(me, 'Matchless Maelstrom'))

    async def test_scroll_needs_fighting_energy(self):
        t = self.table()
        me = await self._scroll(t, energy=(W, W, W))
        self.assertIsNone(t.attack_offer(me, 'Matchless Maelstrom'))

    # --- Cursed Shovel RCL 157 -------------------------------------------------------
    async def test_cursed_shovel_discards_top_two_of_opponents_deck(self):
        t = self.table()
        victim = self.mine(t, self.filler, hp=10)
        self.mine(t, self.filler, zone='bench')
        await t.play(t.put(SHOVEL, P1, 'hand'), targets=[victim.entity_id])
        deck_before = len(t.zone(P2, 'deck'))
        my_deck = len(t.zone(P1, 'deck'))
        await self.opp_hits(t)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before - 2)
        self.assertEqual(len(t.zone(P2, 'discard')), 2)
        self.assertEqual(len(t.zone(P1, 'deck')), my_deck)

    async def test_cursed_shovel_nothing_if_survives(self):
        t = self.table()
        victim = self.mine(t, self.filler)
        victim.set_attribute(AttrID.HP, 400)
        await t.play(t.put(SHOVEL, P1, 'hand'), targets=[victim.entity_id])
        deck_before = len(t.zone(P2, 'deck'))
        await self.opp_hits(t)
        self.assertIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before)

    async def test_cursed_shovel_benched_ko_by_attack_damage(self):
        t = self.table()
        self.mine(t, self.filler).set_attribute(AttrID.HP, 400)
        victim = self.mine(t, self.filler, zone='bench', hp=10)
        await t.play(t.put(SHOVEL, P1, 'hand'), targets=[victim.entity_id])
        shinx = self.swap_opp(t, SHINX_RS)
        shinx.set_attribute(AttrID.HP, 400)
        await t.play(t.put(SCROLL, P2, 'hand'), pid=P2, targets=[shinx.entity_id])
        t.energy(shinx, F)
        t.energy(shinx, W, 2)
        deck_before = len(t.zone(P2, 'deck'))
        t.next_turn()
        await t.attack(shinx, 'Matchless Maelstrom', pid=P2)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before - 2)

    async def test_cursed_shovel_not_on_poison_knockout(self):
        t = self.table()
        victim = self.mine(t, self.filler, hp=10)
        self.mine(t, self.filler, zone='bench')
        await t.play(t.put(SHOVEL, P1, 'hand'), targets=[victim.entity_id])
        victim.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        deck_before = len(t.zone(P2, 'deck'))
        await t.checkup()
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before)


if __name__ == '__main__':
    unittest.main()
