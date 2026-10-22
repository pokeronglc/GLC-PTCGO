"""Bug hunt round 7, chunk 31: Claydol, Stonjourner, Squirtle, Wartortle, Blastoise,
Zorua, Zoroark, Energy Pouch, Misdreavus, Mismagius, Spritzee, Aromatisse,
Gossifleur, Eldegoss, Fossil Researcher -- each checked against its printed text,
including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
GRASS, FIGHT, DARK = PokemonTypes.GRASS, PokemonTypes.FIGHTING, PokemonTypes.DARKNESS

CLAYDOL = 'SWSH12.Claydol_94'
STONJOURNER = 'SWSH12.Stonjourner_101'
SQUIRTLE = 'BW7.Squirtle_29'
WARTORTLE = 'PGO.Wartortle_16'
BLASTOISE = 'SM9.Blastoise_25'
ZORUA = 'SV065.Zorua_31'
ZOROARK = 'BW1.Zoroark_71'
POUCH = 'XY10.EnergyPouch_97'
MISDREAVUS = 'ME2PT5.Misdreavus_85'
MISMAGIUS = 'SWSH12.Mismagius_64'
SPRITZEE = 'ME3.Spritzee_35'
AROMATISSE = 'ME3.Aromatisse_36'
GOSSIFLEUR = 'SWSH1.Gossifleur_20'
ELDEGOSS = 'SWSH7.Eldegoss_16'
FOSSIL_RESEARCHER = 'XY3.FossilResearcher_92'
AMAURA, TYRUNT = 'XY3.Amaura_25', 'XY3.Tyrunt_61'
CARMINE = 'SV06.Carmine_145'
CRABOMINABLE = 'SM1.Crabominable_43'
DTE = 'SWSH10.DoubleTurboEnergy_216'
BALTOY = 'SWSH12.Baltoy_93'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk31(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def is_kind(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    def energies_on(self, pokemon):
        return [c for c in pokemon.children if self.is_energy(c)]

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    # --- Claydol SIT 94: Mystery Charge ---------------------------------------
    async def test_claydol_mystery_charge_attaches_fighting_from_discard(self):
        t = self.table()
        clay = self.mine(t, CLAYDOL)
        bench = self.mine(t, self.filler, zone='bench')
        fight = t.put(t.basic_energy(FIGHT), P1, 'discard')
        t.put(t.basic_energy(WATER), P1, 'discard')
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        t.picks = lambda cards, count, prompt, display: (
            [bench] if bench in cards else [fight] if fight in cards else list(cards)[:count])
        self.assertIsNotNone(t.ability_offer(clay, 'Mystery Charge'))
        await t.use(clay, 'Mystery Charge')
        self.assertIn(fight, bench.children)
        self.assertEqual(len(self.energies_on(bench)), 1)
        self.assertIsNone(t.ability_offer(clay, 'Mystery Charge'))   # once per turn

    async def test_claydol_mystery_charge_blocked_by_supporter_in_discard(self):
        t = self.table()
        clay = self.mine(t, CLAYDOL)
        t.put(t.basic_energy(FIGHT), P1, 'discard')
        t.put(CARMINE, P1, 'discard')
        self.assertIsNone(t.ability_offer(clay, 'Mystery Charge'))

    async def test_claydol_mystery_charge_ignores_opponent_supporters(self):
        t = self.table()
        clay = self.mine(t, CLAYDOL)
        t.put(t.basic_energy(FIGHT), P1, 'discard')
        t.put(CARMINE, P2, 'discard')
        self.assertIsNotNone(t.ability_offer(clay, 'Mystery Charge'))

    async def test_claydol_mystery_charge_needs_fighting_energy(self):
        t = self.table()
        clay = self.mine(t, CLAYDOL)
        t.put(t.basic_energy(WATER), P1, 'discard')
        self.assertIsNone(t.ability_offer(clay, 'Mystery Charge'))

    # --- Stonjourner SIT 101: Mystery Press -----------------------------------
    async def test_stonjourner_mystery_press_bonus_without_supporters(self):
        t = self.table()
        st = self.mine(t, STONJOURNER, FIGHT, 3)
        t.put(CARMINE, P2, 'discard')        # opponent's discard is irrelevant
        await t.attack(st, 'Mystery Press')
        self.assertEqual(self.dealt(), 190)

    async def test_stonjourner_mystery_press_no_bonus_with_supporter(self):
        t = self.table()
        st = self.mine(t, STONJOURNER, FIGHT, 3)
        t.put(CARMINE, P1, 'discard')
        await t.attack(st, 'Mystery Press')
        self.assertEqual(self.dealt(), 60)

    # --- Squirtle BCR 29: Shell Shield ----------------------------------------
    async def test_squirtle_shell_shield_prevents_bench_damage(self):
        t = self.table(CRABOMINABLE)
        self.mine(t, self.filler).set_attribute(AttrID.HP, 300)
        sq = self.mine(t, SQUIRTLE, zone='bench')
        other = self.mine(t, self.filler, zone='bench')
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Avalanche', pid=P2)
        self.assertEqual(t.damage(sq), 0)
        self.assertEqual(t.damage(other), 10)

    async def test_squirtle_shell_shield_not_while_active(self):
        t = self.table()
        sq = self.mine(t, SQUIRTLE)
        t.put(self.filler, P1, 'bench')
        sq.set_attribute(AttrID.HP, 300)    # big HP so the hit is measurable
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        self.assertEqual(300 - t.hp(sq), 80)

    async def test_squirtle_water_splash(self):
        for heads, dmg in ((True, 30), (False, 10)):
            t = self.table()
            sq = self.mine(t, SQUIRTLE, WATER, 2)
            t.heads = heads
            await t.attack(sq, 'Water Splash')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), dmg)

    # --- Wartortle PGO 16: Hydro Pump -----------------------------------------
    async def test_wartortle_hydro_pump_counts_only_water(self):
        for kinds, dmg in (([WATER] * 3, 80), ([WATER, WATER, FIRE], 70), ([FIRE] * 3, 50)):
            t = self.table()
            w = self.mine(t, WARTORTLE)
            for k in kinds:
                t.energy(w, k)
            t.energy(self.opp, WATER, 2)      # opponent's Water doesn't count
            await t.attack(w, 'Hydro Pump')
            with self.subTest(kinds=[k.name for k in kinds]):
                self.assertEqual(self.dealt(), dmg)

    # --- Blastoise TEU 25: Powerful Squall / Hydro Tackle ---------------------
    async def test_blastoise_powerful_squall_top_six_water_only(self):
        t = self.table()
        bl = self.mine(t, BLASTOISE)
        bench = self.mine(t, self.filler, zone='bench')
        seventh = t.deck(P1, [t.basic_energy(WATER)])[0]
        top = t.deck(P1, [t.basic_energy(WATER), self.item, t.basic_energy(FIRE),
                          t.basic_energy(WATER), self.item, self.item])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        targets = iter([bl, bench])
        t.pokemon = lambda c, p: next(targets)
        await t.use(bl, 'Powerful Squall')
        self.assertEqual(sorted(offered, key=id), sorted([top[0], top[3]], key=id))
        self.assertIn(top[0], bl.children + bench.children)
        self.assertIn(top[3], bl.children + bench.children)
        self.assertEqual(len(self.energies_on(bl)), 1)
        self.assertEqual(len(self.energies_on(bench)), 1)
        self.assertIn(top[2], t.zone(P1, 'deck'))
        self.assertIn(seventh, t.zone(P1, 'deck'))
        self.assertIsNone(t.ability_offer(bl, 'Powerful Squall'))

    async def test_blastoise_hydro_tackle_self_damage(self):
        t = self.table()
        bl = self.mine(t, BLASTOISE, WATER, 3)
        await t.attack(bl, 'Hydro Tackle')
        self.assertEqual(self.dealt(), 150)
        self.assertEqual(t.damage(bl), 30)

    # --- Zorua SFA 31: Double Scratch -----------------------------------------
    async def test_zorua_double_scratch(self):
        for heads, dmg in ((True, 40), (False, 0)):
            t = self.table()
            z = self.mine(t, ZORUA, DARK, 2)
            t.heads = heads
            await t.attack(z, 'Double Scratch')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), dmg)

    async def test_zorua_double_scratch_one_heads(self):
        t = self.table()
        z = self.mine(t, ZORUA, DARK, 2)
        flips = iter([True, False])
        t.heads = lambda title: next(flips)
        await t.attack(z, 'Double Scratch')
        self.assertEqual(self.dealt(), 20)

    # --- Zoroark BLW 71: Nasty Plot / Foul Play -------------------------------
    async def test_zoroark_nasty_plot_any_card(self):
        t = self.table()
        z = self.mine(t, ZOROARK, DARK, 1)
        self.clear_hand(t)
        target = t.deck(P1, [CARMINE], top=False)[0]
        t.picks = lambda cards, count, prompt, display: (
            [target] if target in cards else list(cards)[:count])
        await t.attack(z, 'Nasty Plot')
        self.assertEqual(t.zone(P1, 'hand'), [target])
        self.assertEqual(self.dealt(), 0)

    async def test_zoroark_foul_play_copies_defending_attack(self):
        t = self.table()
        z = self.mine(t, ZOROARK, DARK, 2)    # Heavy Impact costs CCC: still copied
        seen = []

        async def pick(player_id, source, candidates, prompt):
            seen.extend(candidates)
            return 0
        with patch.object(t.session, 'prompt_attack_selection', pick):
            await t.attack(z, 'Foul Play')
        self.assertEqual([a.title for _, a in seen], ['Heavy Impact'])
        self.assertTrue(all(p is self.opp for p, _ in seen))
        self.assertEqual(self.dealt(), 80)

    async def test_zoroark_foul_play_ignores_benched_attacks(self):
        t = self.table()
        z = self.mine(t, ZOROARK, DARK, 2)
        t.put(STONJOURNER, P2, 'bench')
        seen = []

        async def pick(player_id, source, candidates, prompt):
            seen.extend(candidates)
            return 0
        with patch.object(t.session, 'prompt_attack_selection', pick):
            await t.attack(z, 'Foul Play')
        self.assertNotIn('Mystery Press', [a.title for _, a in seen])

    # --- Energy Pouch FCO 97 ----------------------------------------------------
    async def test_energy_pouch_returns_basic_energy_on_attack_ko(self):
        t = self.table()
        victim = self.mine(t, self.filler, WATER, 2)
        t.attach(DTE, victim)
        t.put(self.filler, P1, 'bench')
        await t.play(t.put(POUCH, P1, 'hand'), targets=[victim.entity_id])
        self.assertTrue(any(name(c) == 'Energy Pouch' for c in victim.children))
        self.clear_hand(t)
        victim.set_attribute(AttrID.HP, 10)
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(1 for c in hand if self.is_kind(c, WATER)), 2)
        self.assertNotIn('Double Turbo Energy', [name(c) for c in hand])
        self.assertIn('Double Turbo Energy', [name(c) for c in t.zone(P1, 'discard')])

    async def test_energy_pouch_not_on_poison_ko(self):
        t = self.table()
        victim = self.mine(t, self.filler, WATER, 2)
        t.put(self.filler, P1, 'bench')
        await t.play(t.put(POUCH, P1, 'hand'), targets=[victim.entity_id])
        self.clear_hand(t)
        victim.set_attribute(AttrID.HP, 10)
        victim.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.checkup()
        if victim in t.board.pokemon_in_play(P1):
            await t.knockouts(None)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertEqual(sum(1 for c in t.zone(P1, 'hand') if self.is_energy(c)), 0)
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_kind(c, WATER)), 2)

    async def test_energy_pouch_not_on_own_attack_self_ko(self):
        """Hydro Tackle knocking out its own user is not an opponent's attack."""
        t = self.table()
        bl = self.mine(t, BLASTOISE, WATER, 3)
        t.put(self.filler, P1, 'bench')
        await t.play(t.put(POUCH, P1, 'hand'), targets=[bl.entity_id])
        self.clear_hand(t)
        bl.set_attribute(AttrID.HP, 30)
        await t.attack(bl, 'Hydro Tackle')
        self.assertNotIn(bl, t.board.pokemon_in_play(P1))
        self.assertEqual(sum(1 for c in t.zone(P1, 'hand') if self.is_energy(c)), 0)

    # --- Misdreavus ASC 85: Ascension -----------------------------------------
    async def test_misdreavus_ascension_evolves_from_deck(self):
        t = self.table()
        m = self.mine(t, MISDREAVUS, PSY, 1)
        t.deck(P1, [WARTORTLE, MISMAGIUS, ELDEGOSS])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.attack(m, 'Ascension')
        act = t.active(P1)
        self.assertEqual(name(act), 'Mismagius')
        self.assertTrue(all(name(c) == 'Mismagius' for c in offered))
        self.assertEqual(len(self.energies_on(act)), 1)

    async def test_misdreavus_ascension_no_evolution_in_deck(self):
        t = self.table()
        m = self.mine(t, MISDREAVUS, PSY, 1)
        t.deck(P1, [WARTORTLE, ELDEGOSS])
        await t.attack(m, 'Ascension')
        self.assertEqual(name(t.active(P1)), 'Misdreavus')
        self.assertEqual(t.names([c for c in t.zone(P1, 'deck') if name(c) != name(t.put(self.item, P2, 'hand'))]),
                         ['Eldegoss', 'Wartortle'])

    # --- Mismagius SIT 64: Spiteful Magic / Eerie Voice -----------------------
    async def _mismagius_ko(self, full):
        t = self.table(STONJOURNER)
        t.state.turn_number = 3
        mis = self.mine(t, MISMAGIUS)
        if not full:
            mis.set_attribute(AttrID.HP, 80)
        t.put(self.filler, P1, 'bench')
        self.opp.set_attribute(AttrID.HP, 130)
        t.energy(self.opp, FIGHT, 3)
        t.next_turn()
        await t.attack(self.opp, 'Mystery Press', pid=P2)
        self.assertNotIn(mis, t.board.pokemon_in_play(P1))
        return t

    async def test_mismagius_spiteful_magic_full_hp_ko(self):
        t = await self._mismagius_ko(True)
        self.assertEqual(t.hp(self.opp), 130 - 80)

    async def test_mismagius_spiteful_magic_not_full_hp(self):
        t = await self._mismagius_ko(False)
        self.assertEqual(t.hp(self.opp), 130)

    async def test_mismagius_spiteful_magic_needs_ko(self):
        t = self.table()
        mis = self.mine(t, MISMAGIUS)
        mis.set_attribute(AttrID.HP, 90)
        self.opp.set_attribute(AttrID.HP, 300)
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)     # 80 < 90
        self.assertIn(mis, t.board.pokemon_in_play(P1))
        self.assertEqual(t.hp(self.opp), 300)

    async def test_mismagius_eerie_voice_each_opponent(self):
        t = self.table()
        mis = self.mine(t, MISMAGIUS, PSY, 1)
        ob = t.put(self.filler, P2, 'bench')
        mine_b = self.mine(t, self.filler, zone='bench')
        await t.attack(mis, 'Eerie Voice')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(t.damage(ob), 20)
        self.assertEqual(t.damage(mine_b), 0)

    # --- Spritzee POR 35: Sweet Scent ------------------------------------------
    async def test_spritzee_sweet_scent_heals_one_of_yours(self):
        t = self.table()
        sp = self.mine(t, SPRITZEE, WATER, 1)
        hurt = self.mine(t, self.filler, zone='bench')
        full = effective = t.hp(hurt)
        hurt.set_attribute(AttrID.HP, full - 50)
        self.opp.set_attribute(AttrID.HP, 300)
        seen = []
        t.pokemon = lambda c, p: (seen.extend(c), hurt)[1]
        t.picks = lambda cards, count, prompt, display: (
            seen.extend(cards), [hurt] if hurt in cards else list(cards)[:count])[1]
        await t.attack(sp, 'Sweet Scent')
        self.assertEqual(t.damage(hurt), 20)
        self.assertNotIn(self.opp, seen)
        self.assertEqual(t.hp(self.opp), 300)

    # --- Aromatisse POR 36: Scent Collection / Draining Kiss ------------------
    async def test_aromatisse_scent_collection_two_basic_psychic(self):
        t = self.table()
        ar = self.mine(t, AROMATISSE)
        self.clear_hand(t)
        t.deck(P1, [t.basic_energy(PSY), t.basic_energy(WATER), t.basic_energy(PSY),
                    t.basic_energy(PSY)])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.use(ar, 'Scent Collection')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(self.is_kind(c, PSY) for c in hand))
        self.assertFalse(any(self.is_kind(c, WATER) for c in offered))
        self.assertIsNone(t.ability_offer(ar, 'Scent Collection'))

    async def test_aromatisse_draining_kiss_heals_self(self):
        t = self.table()
        ar = self.mine(t, AROMATISSE, PSY, 2)
        ar.set_attribute(AttrID.HP, 120 - 50)
        await t.attack(ar, 'Draining Kiss')
        self.assertEqual(self.dealt(), 50)
        self.assertEqual(t.damage(ar), 20)

    # --- Gossifleur SSH 20: Call for Family -----------------------------------
    async def test_gossifleur_call_for_family_up_to_three_basics(self):
        t = self.table()
        g = self.mine(t, GOSSIFLEUR, WATER, 1)
        t.deck(P1, [ELDEGOSS, ZORUA, SQUIRTLE, MISDREAVUS, SPRITZEE])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.attack(g, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 3)
        self.assertNotIn('Eldegoss', [name(c) for c in offered])

    async def test_gossifleur_call_for_family_bench_space(self):
        t = self.table()
        g = self.mine(t, GOSSIFLEUR, WATER, 1)
        for _ in range(3):
            self.mine(t, self.filler, zone='bench')
        t.deck(P1, [ZORUA, SQUIRTLE, MISDREAVUS])
        await t.attack(g, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Eldegoss EVS 16: Cotton Lift / Cotton Guard --------------------------
    async def test_eldegoss_cotton_lift_basic_energy_only(self):
        t = self.table()
        el = self.mine(t, ELDEGOSS)
        self.clear_hand(t)
        t.deck(P1, [DTE, t.basic_energy(WATER), t.basic_energy(FIRE), t.basic_energy(PSY)])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.use(el, 'Cotton Lift')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(self.is_energy(c) for c in hand))
        self.assertNotIn('Double Turbo Energy', [name(c) for c in offered])
        self.assertIsNone(t.ability_offer(el, 'Cotton Lift'))

    async def test_eldegoss_cotton_guard_minus_30_next_turn_only(self):
        t = self.table()
        el = self.mine(t, ELDEGOSS, GRASS, 1)
        el.set_attribute(AttrID.HP, 300)
        await t.attack(el, 'Cotton Guard')
        self.assertEqual(self.dealt(), 30)
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        self.assertEqual(300 - t.hp(el), 50)
        t.next_turn()
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)
        self.assertEqual(300 - t.hp(el), 50 + 80)

    # --- Fossil Researcher FFI 92 -----------------------------------------------
    async def test_fossil_researcher_benches_amaura_and_tyrunt(self):
        t = self.table()
        self.mine(t, self.filler)
        t.deck(P1, [AMAURA, ZORUA, TYRUNT, AMAURA])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), [c for c in cards if name(c) in ('Amaura', 'Tyrunt')][:count])[1]
        card = t.put(FOSSIL_RESEARCHER, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        bench = t.names(t.zone(P1, 'bench'))
        self.assertEqual(len(bench), 2)
        self.assertTrue(all(n in ('Amaura', 'Tyrunt') for n in bench))
        self.assertNotIn('Zorua', [name(c) for c in offered])

    async def test_fossil_researcher_ignores_other_basics(self):
        t = self.table()
        self.mine(t, self.filler)
        t.deck(P1, [ZORUA, SQUIRTLE])
        card = t.put(FOSSIL_RESEARCHER, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertEqual(t.zone(P1, 'bench'), [])


if __name__ == '__main__':
    unittest.main()
