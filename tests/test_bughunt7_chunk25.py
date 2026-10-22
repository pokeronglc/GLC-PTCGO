"""Bug hunt round 7, chunk 25: Brambleghast, Castform Rainy Form, Cinderace,
Energy Loto, Totodile, Croconaw, Drayton, Repel, Bubbly Water Energy,
Capturing Aroma, Devolution Spray Z, Ace Trainer, Call Bell, Urbain,
Naclstack -- each checked against its printed text, including the cases where
it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes, SpecialConditions
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, GRASS = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS
FIGHT = PokemonTypes.FIGHTING

BRAMBLEGHAST = 'SV05.Brambleghast_21'
CASTFORM = 'SWSH6.CastformRainyForm_33'
CINDERACE = 'SWSH1.Cinderace_34'
LOTO = 'SWSH10.EnergyLoto_140'
TOTODILE, CROCONAW = 'ME2PT5.Totodile_41', 'ME2PT5.Croconaw_42'
DRAYTON = 'SV08.Drayton_174'
REPEL = 'ME1.Repel_126'
BUBBLY = 'ME4.BubblyWaterEnergy_84'
AROMA = 'SWSH12.CapturingAroma_153'
SPRAY_Z = 'SM10.DevolutionSprayZ_166'
ACE = 'XY7.AceTrainer_69'
CALL_BELL = 'SV08.CallBell_165'
URBAIN = 'ME2PT5.Urbain_214'
NACLSTACK = 'ME1.Naclstack_83'
STADIUM = 'SV08.GravityMountain_177'
SWITCH = 'CZ.Switch_144'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk25(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def opp_bench(self, t):
        b = t.put(self.filler, P2, 'bench')
        b.set_attribute(AttrID.HP, 400)
        b.set_attribute(AttrID.WEAKNESS_TYPES, [])
        b.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return b

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def energies_on(self, pokemon):
        return [c for c in pokemon.children if self.is_energy(c)]

    def dealt(self, target=None):
        return 400 - (target or self.opp).get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Brambleghast TEF 21 -------------------------------------------------
    async def test_brambleghast_resilient_soul_hp_per_prize_taken(self):
        t = self.table()
        b = self.mine(t, BRAMBLEGHAST)
        self.assertEqual(effective_max_hp(t.board, b), 100)       # 6 left: none taken
        t.set_prizes(P2, 4)
        self.assertEqual(effective_max_hp(t.board, b), 200)
        t.set_prizes(P1, 1)                                       # my prizes don't count
        self.assertEqual(effective_max_hp(t.board, b), 200)

    async def test_brambleghast_powerful_needles_coin_per_energy(self):
        for heads, expected in ((True, 240), (False, 0)):
            t = self.table()
            b = self.mine(t, BRAMBLEGHAST, GRASS, 3)
            t.heads = heads
            await t.attack(b, 'Powerful Needles')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), expected)

    # --- Castform Rainy Form CRE 33 ------------------------------------------
    async def test_castform_weather_reading_eight_stadiums_free_rainfall(self):
        t = self.table()
        c = self.mine(t, CASTFORM)
        ob = self.opp_bench(t)
        for _ in range(8):
            t.put(STADIUM, P1, 'discard')
        self.assertIsNotNone(t.attack_offer(c, 'Rainfall'))
        await t.attack(c, 'Rainfall')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(self.dealt(ob), 20)

    async def test_castform_weather_reading_seven_stadiums_not_enough(self):
        t = self.table()
        c = self.mine(t, CASTFORM)
        for _ in range(7):
            t.put(STADIUM, P1, 'discard')
        for _ in range(3):
            t.put(STADIUM, P2, 'discard')          # opponent's discard doesn't count
        self.assertIsNone(t.attack_offer(c, 'Rainfall'))

    # --- Cinderace SSH 34 -----------------------------------------------------
    async def test_cinderace_libero_on_switch_attaches_two_fire_from_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        cind = self.mine(t, CINDERACE, zone='bench')
        fires = [t.put(t.basic_energy(FIRE), P1, 'discard') for _ in range(3)]
        t.put(t.basic_energy(WATER), P1, 'discard')
        t.yes = True
        t.pokemon = lambda c, p: cind if cind in c else c[0]
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        await t.play(t.put(SWITCH, P1, 'hand'))
        self.assertIs(t.active(P1), cind)
        on = self.energies_on(cind)
        self.assertEqual(len(on), 2)
        self.assertTrue(all(c in fires for c in on))

    # BUG: Libero ("Once during your turn") fires on promotion after a KO during the opponent's turn
    async def test_cinderace_libero_not_on_opponents_turn_promotion(self):
        """'Once during your turn': promotion after a KO on the opponent's turn."""
        t = self.table()
        victim = self.mine(t, self.filler)
        victim.set_attribute(AttrID.HP, 10)
        cind = self.mine(t, CINDERACE, zone='bench')
        for _ in range(2):
            t.put(t.basic_energy(FIRE), P1, 'discard')
        title, _ = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        t.yes = True
        t.pokemon = lambda c, p: cind if cind in c else c[0]
        await t.attack(self.opp, title, pid=P2)
        self.assertIs(t.active(P1), cind)
        self.assertEqual(self.energies_on(cind), [])

    async def test_cinderace_flare_striker_discards_two(self):
        t = self.table()
        cind = self.mine(t, CINDERACE, FIRE, 3)
        await t.attack(cind, 'Flare Striker')
        self.assertEqual(self.dealt(), 190)
        self.assertEqual(len(self.energies_on(cind)), 1)

    # --- Energy Loto ASR 140 --------------------------------------------------
    async def test_energy_loto_finds_energy_in_top_seven(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.deck(P1, [t.basic_energy(WATER)] + [self.item] * 6)   # energy 7th from top
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        await t.play(t.put(LOTO, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertTrue(self.is_energy(hand[0]))

    async def test_energy_loto_misses_eighth_card(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.deck(P1, [t.basic_energy(WATER)] + [self.item] * 7)   # energy 8th from top
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), [])[1]
        await t.play(t.put(LOTO, P1, 'hand'))
        self.assertEqual(offered, [])
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Totodile ASC 41 ------------------------------------------------------
    async def test_totodile_slight_intrusion_hurts_itself(self):
        t = self.table()
        toto = self.mine(t, TOTODILE, WATER, 2)
        await t.attack(toto, 'Slight Intrusion')
        self.assertEqual(self.dealt(), 40)
        self.assertEqual(t.damage(toto), 10)

    # --- Croconaw ASC 42 ------------------------------------------------------
    async def test_croconaw_crunch_heads_discards_energy(self):
        for heads in (True, False):
            t = self.table()
            croc = self.mine(t, CROCONAW, WATER, 2)
            t.energy(self.opp, WATER, 2)
            t.heads = heads
            await t.attack(croc, 'Crunch')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), 50)
                self.assertEqual(len(self.energies_on(self.opp)), 1 if heads else 2)
                self.assertEqual(len(self.energies_on(croc)), 2)

    # --- Drayton SSP 174 ------------------------------------------------------
    async def test_drayton_takes_pokemon_and_trainer_from_top_seven(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        deep = t.deck(P1, [CROCONAW])[0]                          # 8th
        top = t.deck(P1, [TOTODILE, t.basic_energy(WATER)] + [self.item] * 5)
        seen = []

        async def groups(pid, src, specs, prompt, **k):
            seen.extend(c for s in specs for c in s['cards'])
            return [[s['cards'][0].entity_id] if s['cards'] else [] for s in specs]
        card = t.put(DRAYTON, P1, 'hand')
        with patch.object(t.session, 'prompt_card_chooser_groups', groups, create=True):
            await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertIn(top[0], hand)
        self.assertEqual(sorted(name(c) for c in hand), sorted(['Totodile', name(top[2])]))
        self.assertNotIn(deep, seen)
        self.assertNotIn(top[1], seen)                            # Energy not choosable
        self.assertIn(deep, t.zone(P1, 'deck'))

    # --- Repel MEG 126 --------------------------------------------------------
    async def test_repel_switches_opponent_active(self):
        t = self.table()
        self.mine(t, self.filler)
        ob = self.opp_bench(t)
        old = self.opp
        t.pokemon = lambda c, p: ob if ob in c else c[0]
        await t.play(t.put(REPEL, P1, 'hand'))
        self.assertIs(t.active(P2), ob)
        self.assertIn(old, t.zone(P2, 'bench'))

    async def test_repel_needs_opponent_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, self.filler, zone='bench')                  # my bench is irrelevant
        card = t.put(REPEL, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Bubbly Water Energy CRI 84 ------------------------------------------
    async def test_bubbly_water_cures_and_protects_water_pokemon(self):
        t = self.table()
        toto = self.mine(t, TOTODILE)
        toto.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED, CONFUSED])
        await t.play(t.put(BUBBLY, P1, 'hand'), targets=[toto.entity_id])
        self.assertEqual(t.conditions(toto), set())
        ctx = EffectContext(t.session, P2, self.opp, None)
        await t._run(lambda: ctx.apply_special_condition(toto, SpecialConditions.POISONED))
        self.assertEqual(t.conditions(toto), set())

    async def test_bubbly_water_does_nothing_for_non_water(self):
        t = self.table()
        me = self.mine(t, self.filler)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.play(t.put(BUBBLY, P1, 'hand'), targets=[me.entity_id])
        self.assertEqual(t.conditions(me), {POISONED})
        ctx = EffectContext(t.session, P2, self.opp, None)
        await t._run(lambda: ctx.apply_special_condition(me, SpecialConditions.CONFUSED))
        self.assertIn(CONFUSED, t.conditions(me))

    # --- Capturing Aroma SIT 153 ---------------------------------------------
    async def test_capturing_aroma_heads_evolution_tails_basic(self):
        for heads, want in ((True, 'Croconaw'), (False, 'Totodile')):
            t = self.table()
            self.mine(t, self.filler)
            self.clear_hand(t)
            t.deck(P1, [TOTODILE, CROCONAW], top=False)
            offered = []
            t.heads = heads
            t.picks = lambda cards, count, prompt, display: (
                offered.extend(cards), list(cards)[:count])[1]
            await t.play(t.put(AROMA, P1, 'hand'))
            with self.subTest(heads=heads):
                self.assertEqual([name(c) for c in t.zone(P1, 'hand')], [want])
                self.assertTrue(all(name(c) == want for c in offered))

    # --- Devolution Spray Z UNB 166 ------------------------------------------
    async def test_devolution_spray_z_devolves_and_blocks_evolving(self):
        t = self.table()
        toto = self.mine(t, TOTODILE)
        croc_card = t.put(CROCONAW, P1, 'hand')
        await t.play(croc_card, targets=[toto.entity_id])
        evolved = t.active(P1)
        self.assertEqual(name(evolved), 'Croconaw')
        t.next_turn()
        t.next_turn()
        evolved = t.active(P1)
        evolved.set_attribute(AttrID.HP, effective_max_hp(t.board, evolved) - 30)
        t.pokemon = lambda c, p: c[0]

        async def choose(ctx, prompt, buttons, *a, **k):
            return 0
        with patch.object(EffectContext, 'choose', choose):
            await t.play(t.put(SPRAY_Z, P1, 'hand'))
        now = t.active(P1)
        self.assertEqual(name(now), 'Totodile')
        self.assertEqual(t.damage(now), 30)
        self.assertIn('Croconaw', t.names(t.zone(P1, 'deck')))
        again = t.put(CROCONAW, P1, 'hand')
        self.assertFalse(t.can(again, 'EvolvePokemonPlayAbility'))

    async def test_devolution_spray_z_needs_evolved_pokemon(self):
        t = self.table()
        self.mine(t, TOTODILE)
        t.put(CROCONAW, P2, 'bench')                              # opponent's doesn't count
        card = t.put(SPRAY_Z, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Ace Trainer AOR 69 ---------------------------------------------------
    async def test_ace_trainer_behind_shuffles_and_draws_6_and_3(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        mine = [t.put(TOTODILE, P1, 'hand') for _ in range(2)]
        theirs = [t.put(TOTODILE, P2, 'hand') for _ in range(5)]
        t.set_prizes(P1, 5)
        t.set_prizes(P2, 4)
        card = t.put(ACE, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        self.assertEqual(len(t.zone(P2, 'hand')), 3)
        deck1, deck2 = t.zone(P1, 'deck'), t.zone(P2, 'deck')
        self.assertTrue(all(c in deck1 or c in t.zone(P1, 'hand') for c in mine))
        self.assertTrue(all(c in deck2 or c in t.zone(P2, 'hand') for c in theirs))

    async def test_ace_trainer_not_playable_when_prizes_equal_or_ahead(self):
        for mine_left, theirs_left in ((4, 4), (3, 4)):
            t = self.table()
            self.mine(t, self.filler)
            t.set_prizes(P1, mine_left)
            t.set_prizes(P2, theirs_left)
            card = t.put(ACE, P1, 'hand')
            with self.subTest(mine=mine_left, theirs=theirs_left):
                self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Call Bell SSP 165 ----------------------------------------------------
    async def test_call_bell_turn_two_finds_supporter(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        sup = t.deck(P1, [URBAIN], top=False)[0]
        t.deck(P1, [TOTODILE])
        t.state.turn_number = 2
        card = t.put(CALL_BELL, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.play(card)
        self.assertEqual(t.zone(P1, 'hand'), [sup])
        self.assertTrue(offered and all(name(c) == 'Urbain' for c in offered))

    async def test_call_bell_not_on_turn_one_or_later_turns(self):
        for turn in (1, 3, 4):
            t = self.table()
            self.mine(t, self.filler)
            t.deck(P1, [URBAIN])
            t.state.turn_number = turn
            card = t.put(CALL_BELL, P1, 'hand')
            with self.subTest(turn=turn):
                self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Urbain ASC 214 -------------------------------------------------------
    async def test_urbain_draws_three(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        top = t.deck(P1, [TOTODILE, TOTODILE, TOTODILE, CROCONAW])
        await t.play(t.put(URBAIN, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertNotIn(top[0], hand)                            # 4th card stays

    # --- Naclstack MEG 83 -----------------------------------------------------
    async def test_naclstack_rock_hurl_ignores_resistance(self):
        t = self.table()
        n = self.mine(t, NACLSTACK, FIGHT, 2)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, FIGHT.value)
        await t.attack(n, 'Rock Hurl')
        self.assertEqual(self.dealt(), 50)

    async def test_naclstack_rock_hurl_still_applies_weakness(self):
        t = self.table()
        n = self.mine(t, NACLSTACK, FIGHT, 2)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [FIGHT.value])
        await t.attack(n, 'Rock Hurl')
        self.assertEqual(self.dealt(), 100)


if __name__ == '__main__':
    unittest.main()
