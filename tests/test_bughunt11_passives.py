"""Bug hunt 11: always-on effects (passive Abilities, Tools, Stadiums, Special Energy).

Found by an on/off differential probe (/home/claude/bughunt/hunt5/h5_probe.py): every
continuous text in the GLC pool was put on a board in several placements and the
observable numbers (damage, HP, retreat cost, types, locks, conditions, costs ...)
compared with the same board where the passive is switched off.  Each test below
asserts the PRINTED behaviour; the ones the engine gets wrong are expectedFailure
with a `# BUG:` line.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import pay_cost
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack
from spirit.game.session import passives as P
from spirit.tools.effect_smoke import P1, P2

W, R, F, L, M, G, D = (PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.FIGHTING,
                       PokemonTypes.LIGHTNING, PokemonTypes.METAL, PokemonTypes.GRASS,
                       PokemonTypes.DARKNESS)

TEDDIURSA = 'SWSH3.Teddiursa_138'     # Basic Colorless, Dig Claws [CC] 20
LARVITAR = 'SWSH3.Larvitar_86'        # Basic Fighting, Pierce [CC] 20
CUFANT = 'SWSH3.Cufant_131'           # Basic Metal
MAREANIE = 'SWSH3.Mareanie_51'        # Poison Tentacles [WC] 20 + Poisoned
TRAPINCH = 'DM.Trapinch_32'           # Mini Earthquake [F] 20, 10 to each of YOUR Benched
HITMONLEE = 'XY3.Hitmonlee_47'        # Stretch Kick [F]: 30 to 1 of opponent's Benched
SLITHER_WING = 'SV4.SlitherWing_107'  # Ancient Basic
TOGETIC = 'SM10.Togetic_137'          # Stage 1 Fairy
STAGE2 = 'BW7.Vileplume_3'            # any Stage 2

VILEPLUME_BW7 = 'BW7.Vileplume_3'     # Allergy Panic: Weakness x4 for each Pokémon
KABUTOPS_SV035 = 'SV035.Kabutops_141' # Ancient Way: Weakness x4 for opp's Active
UXIE_SM11 = 'SM11.Uxie_83'
MESPRIT, AZELF = 'SM11.Mesprit_84', 'SM11.Azelf_85'
ANCIENT_CAPSULE = 'SV4.AncientBoosterEnergyCapsule_159'
FULL_METAL_LAB = 'SV05.FullMetalLab_148'
ARIADOS_SV06 = 'SV06.Ariados_5'       # Big Net
HEAVY_BOOTS = 'XY8.HeavyBoots_141'
AQUA_BASE = 'TATM.TeamAquasSecretBase_28'
AQUA_MUK = 'TATM.TeamAquasMuk_8'
FLAREON_XY7 = 'XY7.Flareon_13'        # Flare Effect
GOURGEIST_XY4 = 'XY4.Gourgeist_45'    # Gourgantic
GRAVITY_MOUNTAIN = 'SV08.GravityMountain_177'
WIDE_LENS = 'XY6.WideLens_95'


def attack_of(spec, title):
    return next(a for a in fixtures.definition(spec).abilities
                if isinstance(a, Attack) and a.title == title)


class AlwaysOnTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # -- helpers ---------------------------------------------------------
    def mon(self, t, spec, pid=P1, zone='active', hp=400, weak=None):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [weak.value] if weak else [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.attribute_originals[AttrID.HP.value] = hp
            p.set_attribute(AttrID.HP, hp)
        return p

    async def hit(self, t, attacker, title, target, pid=P1):
        before = t.hp(target)
        await t.attack(attacker, title, pid=pid)
        return before - t.hp(target)

    async def larvitar_vs_weak(self, holder=None, holder_zone='bench', extra=()):
        """P1 Larvitar (Pierce, 20) hits P2's Active that is weak to Fighting."""
        t = Table(self)
        me = self.mon(t, LARVITAR)
        t.energy(me, F, 2)
        if holder:
            self.mon(t, holder, P1, holder_zone)
        for spec in extra:
            self.mon(t, spec, P1, 'bench')
        foe = self.mon(t, TEDDIURSA, P2, weak=F)
        return await self.hit(t, me, 'Pierce', foe)

    # ===================================================================
    # Root cause A: "apply Weakness ... as ×4 instead" — _BWTextPassive.
    # modify_weakness looks for "as 4 instead", but the stored text keeps the
    # multiplication sign ("as ×4 instead"), so the clause never matches.
    # ===================================================================
    async def test_weakness_control_is_x2(self):
        self.assertEqual(await self.larvitar_vs_weak(), 40)

    # FIXED Oct 13: Vileplume BW7 Allergy Panic never applies Weakness as x4 ("as ×4" vs "as 4" text match)
    async def test_vileplume_allergy_panic_weakness_x4(self):
        self.assertEqual(await self.larvitar_vs_weak(VILEPLUME_BW7), 80)

    # FIXED Oct 13: Kabutops SV035 Ancient Way never applies Weakness as x4 (same text match)
    async def test_kabutops_ancient_way_weakness_x4(self):
        self.assertEqual(await self.larvitar_vs_weak(KABUTOPS_SV035), 80)

    # FIXED Oct 13: Uxie SM11 Secret Territory never applies Weakness as x4 (same text match)
    async def test_uxie_secret_territory_weakness_x4(self):
        self.assertEqual(await self.larvitar_vs_weak(UXIE_SM11, extra=(MESPRIT, AZELF)), 80)

    # ===================================================================
    # Root cause B: _BWTextPassive.blocks_special_conditions ignores the
    # holder qualifier "the Ancient Pokémon this card is attached to".
    # ===================================================================
    async def poison_onto(self, carrier_spec):
        t = Table(self)
        mare = self.mon(t, MAREANIE)
        pay_cost(t, mare, attack_of(MAREANIE, 'Poison Tentacles'))
        foe = self.mon(t, carrier_spec, P2)
        t.attach(ANCIENT_CAPSULE, foe)
        await t.attack(mare, 'Poison Tentacles')
        return t, foe

    # FIXED Oct 13: Ancient Booster Energy Capsule stops Special Conditions on a non-Ancient Pokémon
    async def test_ancient_capsule_no_condition_shield_on_non_ancient(self):
        t, foe = await self.poison_onto(TEDDIURSA)
        self.assertIn('Poisoned', t.conditions(foe))

    async def test_ancient_capsule_condition_shield_on_ancient(self):   # control
        t, foe = await self.poison_onto(SLITHER_WING)
        self.assertNotIn('Poisoned', t.conditions(foe))

    async def test_ancient_capsule_hp_only_on_ancient(self):   # control (HP clause is scoped)
        t = Table(self)
        ted = t.put(TEDDIURSA, P1, 'active')
        wing = t.put(SLITHER_WING, P1, 'bench')
        base_ted, base_wing = P.effective_max_hp(t.board, ted), P.effective_max_hp(t.board, wing)
        t.attach(ANCIENT_CAPSULE, ted)
        t.attach(ANCIENT_CAPSULE, wing)
        self.assertEqual(P.effective_max_hp(t.board, ted), base_ted)
        self.assertEqual(P.effective_max_hp(t.board, wing), base_wing + 60)

    # ===================================================================
    # Root cause C: stadium texts "take N less damage from attacks from the
    # opponent's Pokémon (both yours and your opponent's)" — the "(both ...)"
    # branch drops the attacker-is-opponent check, so a player's own attack
    # damage to their own Benched Pokémon is reduced too.
    # ===================================================================
    # FIXED Oct 13: Full Metal Lab reduces your own attack's damage to your own Benched Metal Pokémon
    async def test_full_metal_lab_not_vs_own_attack(self):
        t = Table(self)
        trap = self.mon(t, TRAPINCH)
        t.energy(trap, F)
        steel = self.mon(t, CUFANT, P1, 'bench')
        self.mon(t, TEDDIURSA, P2)
        t.stadium(FULL_METAL_LAB, P1)
        before = t.hp(steel)
        await t.attack(trap, 'Mini Earthquake')
        self.assertEqual(before - t.hp(steel), 10)

    async def test_full_metal_lab_vs_opponent_attack(self):   # control
        t = Table(self)
        steel = self.mon(t, CUFANT)
        lar = self.mon(t, LARVITAR, P2)
        t.energy(lar, F, 2)
        t.stadium(FULL_METAL_LAB, P1)
        t.next_turn()
        self.assertEqual(await self.hit(t, lar, 'Pierce', steel, pid=P2), 0)

    # ===================================================================
    # Root cause D: _BWTextPassive.modify_retreat_cost scope words.
    # ===================================================================
    def retreat_board(self):
        t = Table(self)
        mine = self.mon(t, TOGETIC)            # Stage 1
        my_bench = self.mon(t, TEDDIURSA, P1, 'bench')
        theirs = self.mon(t, TOGETIC, P2)       # opponent's Active Evolution Pokémon
        their_bench = self.mon(t, TEDDIURSA, P2, 'bench')
        return t, mine, my_bench, theirs, their_bench

    # FIXED Oct 13: Ariados SV06 Big Net raises its OWN retreat cost instead of the opponent's Active Evolution Pokémon's
    async def test_ariados_big_net_targets_opponents_active_evolution(self):
        t, mine, my_bench, theirs, _ = self.retreat_board()
        ari = self.mon(t, ARIADOS_SV06, P1, 'bench')
        base_ari = int(ari.get_attribute(AttrID.RETREAT_COST) or 0)
        base_theirs = int(theirs.get_attribute(AttrID.RETREAT_COST) or 0)
        self.assertEqual((t.retreat(ari), t.retreat(theirs)), (base_ari, base_theirs + 1))

    # FIXED Oct 13: Heavy Boots adds [C] to the holder's retreat cost (and +20 HP) even below 3
    async def test_heavy_boots_needs_retreat_three(self):
        t = Table(self)
        ted = self.mon(t, TEDDIURSA, hp=None)          # retreat cost 1
        base_rc, base_hp = t.retreat(ted), P.effective_max_hp(t.board, ted)
        t.attach(HEAVY_BOOTS, ted)
        self.assertEqual((t.retreat(ted), P.effective_max_hp(t.board, ted)), (base_rc, base_hp))

    # FIXED Oct 13: Team Aqua's Secret Base only taxes the Stadium owner's Pokémon (text: each Pokémon in play)
    async def test_team_aqua_secret_base_both_players(self):
        t, mine, my_bench, theirs, their_bench = self.retreat_board()
        base = [int(p.get_attribute(AttrID.RETREAT_COST) or 0) for p in (mine, theirs)]
        t.stadium(AQUA_BASE, P1)
        self.assertEqual([t.retreat(mine), t.retreat(theirs)], [base[0] + 1, base[1] + 1])

    # FIXED Oct 13: Team Aqua's Muk Sludge Festival only taxes its owner's Pokémon (text: each Pokémon in play)
    async def test_team_aqua_muk_both_players(self):
        t, mine, my_bench, theirs, their_bench = self.retreat_board()
        base = [int(p.get_attribute(AttrID.RETREAT_COST) or 0) for p in (my_bench, theirs)]
        self.mon(t, AQUA_MUK, P1, 'bench')
        self.assertEqual([t.retreat(my_bench), t.retreat(theirs)], [base[0] + 1, base[1] + 1])

    # ===================================================================
    # Root cause E: "its maximum HP is N" is not handled by _BWTextPassive.max_hp_bonus.
    # ===================================================================
    # FIXED Oct 13: Gourgeist XY4 Gourgantic never sets max HP to 200 with Grass Energy attached
    async def test_gourgeist_gourgantic_max_hp_200(self):
        t = Table(self)
        g = t.put(GOURGEIST_XY4, P1, 'active')
        t.energy(g, G)
        self.assertEqual(P.effective_max_hp(t.board, g), 200)

    # FIXED Oct 13: Stakataka SM10 Wall of Stone never sets max HP to 200 when the opponent has 3 or fewer Prizes
    async def test_stakataka_wall_of_stone_max_hp_200(self):
        t = Table(self)
        s = t.put('SM10.Stakataka_106', P1, 'active')
        t.set_prizes(P2, 3)
        self.assertEqual(P.effective_max_hp(t.board, s), 200)

    # FIXED Oct 13: Solrock SM7 Sunbeam never set your Lunatone's max HP to 130
    async def test_solrock_sunbeam_lunatone_max_hp_130(self):
        t = Table(self)
        luna = t.put('SM7.Lunatone_61', P1, 'active')
        sol = t.put('SM7.Solrock_62', P1, 'bench')
        their_luna = t.put('SM7.Lunatone_61', P2, 'active')
        self.assertEqual((P.effective_max_hp(t.board, luna), P.effective_max_hp(t.board, sol),
                          P.effective_max_hp(t.board, their_luna)), (130, 90, 80))

    async def test_gourgeist_without_grass_keeps_printed_hp(self):   # control
        t = Table(self)
        g = t.put(GOURGEIST_XY4, P1, 'active')
        base = P.effective_max_hp(t.board, g)
        t.energy(g, W)
        self.assertEqual(P.effective_max_hp(t.board, g), base)
        self.assertNotEqual(base, 200)

    # FIXED Oct 13: Dodrio Retreat Aid also discounted your Benched Pokémon
    async def test_dodrio_retreat_aid_active_only(self):
        t, mine, my_bench, theirs, _ = self.retreat_board()
        base = (t.retreat(mine), t.retreat(my_bench), t.retreat(theirs))
        self.mon(t, 'XY8.Dodrio_117', P1, 'bench')
        self.assertEqual((t.retreat(mine), t.retreat(my_bench), t.retreat(theirs)),
                         (max(0, base[0] - 2), base[1], base[2]))

    async def test_kabutops_not_on_own_pokemon(self):   # control: only your opponent's Active
        t = Table(self)
        self.mon(t, KABUTOPS_SV035, P1, 'bench')
        mine = self.mon(t, TEDDIURSA, P1, weak=F)
        lar = self.mon(t, LARVITAR, P2)
        t.energy(lar, F, 2)
        t.next_turn()
        self.assertEqual(await self.hit(t, lar, 'Pierce', mine, pid=P2), 40)

    async def test_uxie_needs_mesprit_and_azelf(self):   # control
        self.assertEqual(await self.larvitar_vs_weak(UXIE_SM11, extra=(MESPRIT,)), 40)

    async def test_weakness_x4_does_not_stack(self):   # control (owner decision)
        self.assertEqual(await self.larvitar_vs_weak(VILEPLUME_BW7, extra=(KABUTOPS_SV035,)), 80)

    async def test_ariados_big_net_not_on_basic_or_bench(self):   # control
        t = Table(self)
        self.mon(t, ARIADOS_SV06, P1, 'active')
        foe = self.mon(t, TEDDIURSA, P2)                 # Basic Active
        bench_evo = self.mon(t, TOGETIC, P2, 'bench')    # Benched Evolution
        base = (int(foe.get_attribute(AttrID.RETREAT_COST) or 0),
                int(bench_evo.get_attribute(AttrID.RETREAT_COST) or 0))
        self.assertEqual((t.retreat(foe), t.retreat(bench_evo)), base)

    async def test_heavy_boots_on_retreat_three(self):   # control
        t = Table(self)
        cuf = self.mon(t, CUFANT, hp=None)              # retreat cost 3
        base_rc, base_hp = t.retreat(cuf), P.effective_max_hp(t.board, cuf)
        t.attach(HEAVY_BOOTS, cuf)
        self.assertEqual((t.retreat(cuf), P.effective_max_hp(t.board, cuf)), (base_rc, base_hp + 20))

    # Item F (investigated, not a game bug): the Burn checkup flip draws from
    # game_session's own `random`, not ctx.flip_coins, so `t.heads = False`
    # never reached it and Burned "disappeared" at random in the probe.  With
    # the flip itself forced, Burn behaves per the BW/XY rule, Chaos Tower or not.
    async def test_burn_checkup_with_forced_flip(self):
        from unittest import mock
        for tower in (None, P1, P2):
            for flip, stays in ((1, True), (0, False)):       # 1 = tails, 0 = heads
                t = Table(self)
                a1, a2 = self.mon(t, TEDDIURSA), self.mon(t, TEDDIURSA, P2)
                if tower:
                    t.stadium('XY10.ChaosTower_94', tower)
                for a in (a1, a2):
                    a.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Burned'])
                with mock.patch('spirit.game.session.game_session.random') as rnd:
                    rnd.choice.return_value = flip
                    await t.checkup()
                with self.subTest(tower=tower, flip=flip):
                    self.assertEqual((400 - t.hp(a1), 400 - t.hp(a2)), (20, 20))
                    self.assertEqual(('Burned' in t.conditions(a1), 'Burned' in t.conditions(a2)),
                                     (stays, stays))

    # ===================================================================
    # Controls for played cards the probe could not see directly.
    # ===================================================================
    async def test_focus_sash_fighting_only(self):
        for spec, survives in ((LARVITAR, True), (TEDDIURSA, False)):
            t = Table(self)
            me = self.mon(t, spec, hp=50)
            t.attach('XY3.FocusSash_91', me)
            self.mon(t, TEDDIURSA, P1, 'bench')
            att = self.mon(t, CUFANT, P2)
            t.energy(att, M, 3)
            t.next_turn()
            await t.attack(att, 'Strength', pid=P2)          # 60 damage
            with self.subTest(spec=spec):
                self.assertEqual(me in t.board.pokemon_in_play(P1), survives)

    async def test_tool_jammer_only_from_active(self):
        for zone, bonus in (('active', 0), ('bench', 30)):
            t = Table(self)
            holder = self.mon(t, TEDDIURSA, P1, zone)
            if zone == 'bench':
                self.mon(t, TEDDIURSA, P1, 'active')
            t.attach('SWSH5.ToolJammer_136', holder)
            foe = t.put(TEDDIURSA, P2, 'active')
            base = P.effective_max_hp(t.board, foe)
            t.attach('SWSH1.BigCharm_158', foe)
            with self.subTest(zone=zone):
                self.assertEqual(P.effective_max_hp(t.board, foe) - base, bonus)

    # ===================================================================
    # More controls for played cards the probe could not see directly.
    # ===================================================================
    async def test_gravity_mountain_stage2_minus_30(self):
        t = Table(self)
        s2 = t.put(STAGE2, P1, 'active')
        basic = t.put(TEDDIURSA, P1, 'bench')
        hp2, hpb = P.effective_max_hp(t.board, s2), P.effective_max_hp(t.board, basic)
        t.stadium(GRAVITY_MOUNTAIN, P2)
        self.assertEqual((P.effective_max_hp(t.board, s2), P.effective_max_hp(t.board, basic)),
                         (hp2 - 30, hpb))

    async def test_wide_lens_applies_weakness_to_bench(self):
        for lens, expected in ((False, 30), (True, 60)):
            t = Table(self)
            lee = self.mon(t, HITMONLEE)
            t.energy(lee, F)
            if lens:
                t.attach(WIDE_LENS, lee)
            self.mon(t, TEDDIURSA, P2)
            target = self.mon(t, TEDDIURSA, P2, 'bench', weak=F)
            t.pokemon = lambda c, p: target if target in c else c[0]
            t.picks = lambda cards, n, p, d: [target] if target in cards else list(cards)[:n]
            with self.subTest(lens=lens):
                self.assertEqual(await self.hit(t, lee, 'Stretch Kick', target), expected)


if __name__ == '__main__':
    unittest.main()
