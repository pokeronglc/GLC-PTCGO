"""Bug hunt, deck 10 (Darkness): Supporters and Items, through the real
play-trainer executor (so play conditions and once-per-turn rules apply)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.models.board import create_card_entity
from spirit.game.scripts.cards import loader
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

D = PokemonTypes.DARKNESS
ZUBAT, GOLBAT, CROBAT = 'ME4.Zubat_49', 'SWSH5.Golbat_90', 'SWSH12.Crobat_105'
SABLEYE, ABSOL, PECHARUNT = 'SV2.Sableye_136', 'XY6.Absol_40', 'SVP.Pecharunt_149'
LELE = 'Promo_SM.TapuLele_152'
NEST, QUICK, LEVEL = 'SV1.NestBall_181', 'SWSH8.QuickBall_237', 'SWSH5.LevelBall_129'
FLOAT, CAPSULE, ARTAZON = 'XY8.FloatStone_137', 'SV05.AncientBoosterEnergyCapsule_140', 'SV2.Artazon_171'
HIDING = 'SWSH3.HidingDarknessEnergy_175'
GUZMA, GUZMA_HALA, IONO, N = 'SM3.Guzma_115', 'SM12.GuzmaHala_193', 'SV2.Iono_185', 'XY10.N_105'
ARVEN, BALL_GUY, PIERS = 'SV3.Arven_186', 'SWSH45.BallGuy_57', 'SWSH3.Piers_165'
FABA, LUSAMINE, TEAMMATES = 'SM8.Faba_173', 'SM4.Lusamine_96', 'XY5.Teammates_141'
LILLIE = 'ME1.LilliesDetermination_119'


class Deck10Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Supporters -------------------------------------------------------
    async def test_arven_item_and_tool(self):
        t = self.table()
        t.deck(P1, [NEST, FLOAT, ARTAZON])
        card = t.put(ARVEN, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: (
            [c for c in cards if def_for(c.archetype_id).display_name in ('Nest Ball', 'Float Stone')][:1] or cards[:count])
        await t.play(card)
        names = self.hand_names(t)
        self.assertEqual(len(names), 2)
        self.assertIn('Float Stone', names)          # the Tool
        self.assertNotIn('Artazon', names)           # a Stadium is neither

    async def test_guzma_switches_both(self):
        t = self.table()
        opp_bench = t.put(SABLEYE, P2, 'bench')
        my_bench = t.put(ZUBAT, P1, 'bench')
        await t.play(t.put(GUZMA, P1, 'hand'))
        self.assertIs(t.active(P2), opp_bench)
        self.assertIs(t.active(P1), my_bench)

    async def test_guzma_needs_opponent_bench(self):
        t = self.table()
        card = t.put(GUZMA, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_guzma_and_hala_basic_and_extra(self):
        t = self.table()
        t.deck(P1, [ARTAZON, FLOAT, HIDING])
        card = t.put(GUZMA_HALA, P1, 'hand')
        await t.play(card)
        self.assertEqual(self.hand_names(t), ['Artazon'])
        t = self.table()
        t.deck(P1, [ARTAZON, FLOAT, HIDING])
        t.put(self.filler, P1, 'hand'); t.put(self.filler, P1, 'hand')
        await t.play(t.put(GUZMA_HALA, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Artazon', 'Float Stone', 'Hiding Darkness Energy'])
        self.assertEqual(len(t.zone(P1, 'discard')), 3)   # 2 paid + the Supporter

    async def test_iono_draws_by_prizes(self):
        t = self.table()
        t.set_prizes(P1, 4); t.set_prizes(P2, 2)
        for _ in range(3):
            t.put(self.filler, P1, 'hand'); t.put(self.filler, P2, 'hand')
        await t.play(t.put(IONO, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)

    async def test_n_draws_by_prizes(self):
        t = self.table()
        t.set_prizes(P1, 5); t.set_prizes(P2, 1)
        await t.play(t.put(N, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)

    async def test_lillies_determination_six_or_eight(self):
        for prizes, drawn in ((6, 8), (5, 6), (2, 6)):
            t = self.table()
            t.set_prizes(P1, prizes)
            t.put(self.filler, P1, 'hand')
            await t.play(t.put(LILLIE, P1, 'hand'))
            with self.subTest(prizes=prizes):
                self.assertEqual(len(t.zone(P1, 'hand')), drawn)

    async def test_ball_guy_only_poke_ball_cards(self):
        t = self.table()
        t.deck(P1, [NEST, QUICK, LEVEL, FLOAT, ARTAZON])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        await t.play(t.put(BALL_GUY, P1, 'hand'))
        self.assertEqual(seen['count'], 3)
        self.assertNotIn('Float Stone', seen['names'])
        self.assertEqual(self.hand_names(t), ['Level Ball', 'Nest Ball', 'Quick Ball'])

    async def test_piers_energy_and_darkness_pokemon(self):
        t = self.table()
        t.deck(P1, [t.basic_energy(D), SABLEYE, LELE])
        await t.play(t.put(PIERS, P1, 'hand'))
        names = self.hand_names(t)
        self.assertIn('Sableye', names)
        self.assertNotIn('Tapu Lele', names)
        self.assertEqual(len(names), 2)

    async def test_faba_lost_zones_tool_energy_or_stadium(self):
        t = self.table()
        tool = t.attach(FLOAT, self.opp)
        t.pokemon = lambda c, p: c[0]
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is tool][:1] or cards[:count]
        await t.play(t.put(FABA, P1, 'hand'))
        self.assertNotIn(tool, self.opp.children)
        lost = t.board.find_player_area(P2, 'lostZone')
        self.assertIn(tool, list(lost.children) if lost else [])

    async def test_faba_stadium(self):
        t = self.table()
        stadium = t.stadium(ARTAZON, P2)
        await t.play(t.put(FABA, P1, 'hand'))
        self.assertFalse(t.board.find_global_area('activeStadium').children)

    async def test_lusamine_supporters_and_stadiums(self):
        t = self.table()
        for spec in (GUZMA, ARTAZON, NEST):
            t.put(spec, P1, 'discard')
        await t.play(t.put(LUSAMINE, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Artazon', 'Guzma'])

    async def test_teammates_needs_knockout_last_turn(self):
        t = self.table()
        card = t.put(TEAMMATES, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_one_supporter_per_turn(self):
        t = self.table()
        await t.play(t.put(N, P1, 'hand'))
        second = t.put(LILLIE, P1, 'hand')
        self.assertFalse(t.can(second, 'UseTrainerCard'))

    # --- Items --------------------------------------------------------------
    async def test_rare_candy(self):
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'bench')
        candy = t.put('ME1.RareCandy_125', P1, 'hand')
        crobat = t.put(CROBAT, P1, 'hand')
        self.assertTrue(t.can(candy, 'UseTrainerCard'))
        await t.play(candy)
        self.assertEqual(t.names(t.board.pokemon_in_play(P1)).count('Crobat'), 1)
        # Not on a Basic played this turn
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'bench')
        t.state.mark_entered_play(zubat.entity_id)
        candy = t.put('ME1.RareCandy_125', P1, 'hand')
        t.put(CROBAT, P1, 'hand')
        self.assertFalse(t.can(candy, 'UseTrainerCard'))

    async def test_buddy_buddy_poffin(self):
        t = self.table()
        small = [s for s in (ZUBAT, SABLEYE, ABSOL, PECHARUNT, LELE)
                 if fixtures.definition(s).extra_attributes[str(AttrID.HP.value)]['value'] <= 70]
        big = [s for s in (ZUBAT, SABLEYE, ABSOL, PECHARUNT, LELE)
               if fixtures.definition(s).extra_attributes[str(AttrID.HP.value)]['value'] > 70]
        t.deck(P1, small + big)
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        await t.play(t.put('SV05.BuddyBuddyPoffin_144', P1, 'hand'))
        self.assertEqual(seen['count'], 2)
        for spec in big:
            self.assertNotIn(fixtures.definition(spec).display_name, seen['names'])
        self.assertEqual(len(t.zone(P1, 'bench')), min(2, len(small)))

    async def test_dark_patch_benched_darkness_only(self):
        t = self.table()
        sab = t.put(SABLEYE, P1, 'bench')
        lele = t.put(LELE, P1, 'bench')
        t.put(t.basic_energy(D), P1, 'discard')
        offered = {}
        t.pokemon = lambda c, p: (offered.setdefault('c', t.names(c)), c[0])[1]
        await t.play(t.put('SWSH10.DarkPatch_139', P1, 'hand'))
        self.assertEqual(offered['c'], ['Sableye'])
        self.assertEqual(len(t.board.attached_energies(sab)), 1)

    async def test_evolution_incense(self):
        t = self.table()
        t.deck(P1, [GOLBAT, SABLEYE])
        await t.play(t.put('SWSH1.EvolutionIncense_163', P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Golbat'])

    async def test_hisuian_heavy_ball(self):
        t = self.table()
        prizes = t.zone(P1, 'prizes')
        t.board.find_player_area(P1, 'prizePile').remove_child(prizes[0])
        lele = t.put(LELE, P1, 'prizes')
        ball = t.put('SWSH10.HisuianHeavyBall_146', P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is lele][:1]
        await t.play(ball)
        self.assertIn(lele, t.zone(P1, 'hand'))
        self.assertIn(ball, t.zone(P1, 'prizes'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)

    async def test_hypnotoxic_laser(self):
        for heads, conds in ((True, {POISONED, ASLEEP}), (False, {POISONED})):
            t = self.table()
            t.heads = heads
            await t.play(t.put('BW8.HypnotoxicLaser_123', P1, 'hand'))
            with self.subTest(heads=heads):
                self.assertEqual(t.conditions(self.opp), conds)

    async def test_level_ball_90_or_less(self):
        t = self.table()
        specs = [ZUBAT, SABLEYE, ABSOL, PECHARUNT, CROBAT, LELE]
        t.deck(P1, specs)
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:1])[1]
        await t.play(t.put(LEVEL, P1, 'hand'))
        for spec in specs:
            hp = fixtures.definition(spec).extra_attributes[str(AttrID.HP.value)]['value']
            name = fixtures.definition(spec).display_name
            with self.subTest(card=name, hp=hp):
                self.assertEqual(name in seen['n'], hp <= 90)

    async def test_nest_ball(self):
        t = self.table()
        t.deck(P1, [GOLBAT, SABLEYE])
        await t.play(t.put(NEST, P1, 'hand'))
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Sableye'])

    async def test_night_stretcher(self):
        t = self.table()
        t.put(SABLEYE, P1, 'discard')
        t.put(t.basic_energy(D), P1, 'discard')
        t.put(HIDING, P1, 'discard')
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:1])[1]
        await t.play(t.put('ME2PT5.NightStretcher_196', P1, 'hand'))
        self.assertNotIn('Hiding Darkness Energy', seen['n'])
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_poke_pad_no_rule_box(self):
        t = self.table()
        t.deck(P1, [SABLEYE])
        await t.play(t.put('ME3.PokPad_81', P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Sableye'])

    async def test_pokegear(self):
        t = self.table()
        t.deck(P1, [N, ZUBAT, NEST])
        await t.play(t.put('SV1.Pokgear30_186', P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['N'])

    async def test_quick_ball_discard_one_basic(self):
        t = self.table()
        t.deck(P1, [SABLEYE, GOLBAT])
        ball = t.put(QUICK, P1, 'hand')
        self.assertFalse(t.can(ball, 'UseTrainerCard'))     # needs another card to discard
        t.put(self.filler, P1, 'hand')
        await t.play(ball)
        self.assertEqual(self.hand_names(t), ['Sableye'])

    async def test_ultra_ball_discard_two(self):
        t = self.table()
        t.deck(P1, [CROBAT])
        ball = t.put('ME1.UltraBall_131', P1, 'hand')
        t.put(self.filler, P1, 'hand')
        self.assertFalse(t.can(ball, 'UseTrainerCard'))
        t.put(self.filler, P1, 'hand')
        await t.play(ball)
        self.assertEqual(self.hand_names(t), ['Crobat'])

    async def test_tag_call(self):
        t = self.table()
        t.deck(P1, [GUZMA_HALA, GUZMA])
        await t.play(t.put('SM12.TagCall_206', P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Guzma & Hala'])

    async def test_vs_seeker(self):
        t = self.table()
        seeker = t.put('XY4.VSSeeker_109', P1, 'hand')
        self.assertFalse(t.can(seeker, 'UseTrainerCard'))
        t.put(GUZMA, P1, 'discard')
        await t.play(seeker)
        self.assertEqual(self.hand_names(t), ['Guzma'])

    async def test_professors_letter(self):
        t = self.table()
        t.deck(P1, [t.basic_energy(D), t.basic_energy(D), HIDING])
        await t.play(t.put('XY8.ProfessorsLetter_146', P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertNotIn('Hiding Darkness Energy', self.hand_names(t))

    async def test_counter_catcher_only_when_behind(self):
        t = self.table()
        bench = t.put(SABLEYE, P2, 'bench')
        card = t.put('SV4.CounterCatcher_160', P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))     # 6 v 6
        t.set_prizes(P2, 4)
        await t.play(card)
        self.assertIs(t.active(P2), bench)

    async def test_scoop_up_net(self):
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'bench')
        golbat_def = fixtures.definition(GOLBAT)
        golbat = t.put(GOLBAT, P1, 'hand')
        await t._run(lambda: t.session.perform_evolution(P1, golbat, zubat))
        golbat = next(p for p in t.board.pokemon_in_play(P1) if def_for(p.archetype_id).display_name == 'Golbat')
        energy = t.energy(golbat, D)
        t.pokemon = lambda c, p: golbat if golbat in c else c[0]
        await t.play(t.put('SWSH2.ScoopUpNet_165', P1, 'hand'))
        self.assertEqual([n for n in self.hand_names(t) if n in ('Golbat', 'Zubat')], ['Golbat', 'Zubat'])
        self.assertIn(energy, t.zone(P1, 'discard'))

    async def test_rescue_carrier(self):
        t = self.table()
        for spec in (ZUBAT, CROBAT, SABLEYE):
            t.put(spec, P1, 'discard')
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', (t.names(cards), count)), cards[:count])[1]
        await t.play(t.put('SWSH7.RescueCarrier_154', P1, 'hand'))
        names, count = seen['n']
        self.assertEqual(count, 2)
        crobat_hp = fixtures.definition(CROBAT).extra_attributes[str(AttrID.HP.value)]['value']
        self.assertEqual('Crobat' in names, crobat_hp <= 90)


if __name__ == "__main__":
    unittest.main()
