"""Bug hunt round 7, chunk 9: Magneton (SSP/CEC), Electrode (EVO/PLF),
Froakie, Greninja (DET), Energy Search, Eri, Ponyta (TEF/CEC), Rapidash,
Sneasel, Weavile (MEP), Magnemite -- each checked against its printed text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, LIGHT, DARK = (PokemonTypes.FIRE, PokemonTypes.WATER,
                            PokemonTypes.LIGHTNING, PokemonTypes.DARKNESS)

MAGNETON_SSP, MAGNETON_CEC = 'SV08.Magneton_59', 'SM12.Magneton_69'
ELECTRODE_EVO, ELECTRODE_PLF = 'XY12.Electrode_40', 'BW9.Electrode_33'
FROAKIE, GRENINJA = 'ME4.Froakie_20', 'GUM.Greninja_9'
ENERGY_SEARCH, ERI = 'ME3.EnergySearch_72', 'SV05.Eri_146'
PONYTA_TEF, PONYTA_CEC, RAPIDASH = 'SV05.Ponyta_26', 'SM12.Ponyta_23', 'SWSH12.Rapidash_22'
SNEASEL, WEAVILE_MEP, MAGNEMITE = 'SM5.Sneasel_73', 'MEP.Weavile_21', 'SV2.Magnemite_65'
THERAPEUTIC = 'SV2.TherapeuticEnergy_193'      # Special Energy
SUPPORTER = ERI                                # any Supporter card


class Chunk9(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    def neutral(self, p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def is_energy_of(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    def is_def(self, card, spec):
        d = fixtures.definition(spec) if isinstance(spec, str) else spec
        return card.archetype_id.lower() == d.guid.lower()

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        title, dmg = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    # --- Magneton SSP 59: Overvolt Discharge --------------------------------
    async def test_magneton_ssp_overvolt_discharge(self):
        t = self.table()
        mag = self.mine(t, MAGNETON_SSP, zone='bench')
        lightning = self.mine(t, MAGNEMITE, zone='active')
        other = self.mine(t, self.filler, zone='bench')       # Colorless, not Lightning
        for kind in (LIGHT, LIGHT, FIRE, WATER):
            t.put(t.basic_energy(kind), P1, 'discard')
        t.put(THERAPEUTIC, P1, 'discard')
        seen = []
        t.pokemon = lambda cands, prompt: (seen.append(list(cands)) or lightning)
        await t.use(mag, 'Overvolt Discharge')
        attached = t.board.attached_energies(lightning)
        self.assertEqual(len(attached), 3)
        self.assertFalse(any(self.is_def(c, THERAPEUTIC) for c in attached))
        self.assertTrue(all(other not in c for c in seen))
        self.assertTrue(all(mag in c for c in seen))          # itself is Lightning
        self.assertNotIn(mag, t.board.pokemon_in_play(P1))     # Knocked Out
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)          # opponent took a Prize

    # --- Magneton CEC 69: Call Signal ---------------------------------------
    async def test_magneton_cec_call_signal(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mag = self.mine(t, MAGNETON_CEC, zone='bench')
        t.deck(P1, [SUPPORTER] * 4 + [ENERGY_SEARCH])
        hand0 = len(t.zone(P1, 'hand'))
        counts = []
        t.picks = lambda cards, count, prompt, disp: (counts.append((len(cards), count)) or cards[:count])
        await t.use(mag, 'Call Signal')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand) - hand0, 3)
        self.assertTrue(all(self.is_def(c, SUPPORTER) for c in hand))
        self.assertEqual(counts[-1][1], 3)
        self.assertNotIn(mag, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)

    # BUG: Call Signal only Knocks Out Magneton when a Supporter was taken (bw_era 'if picks and ...').

    async def test_magneton_cec_call_signal_take_zero_still_ko(self):
        # "If you searched your deck in this way" -- searching and finding 0 still counts.
        t = self.table()
        t.put(self.filler, P1, 'active')
        mag = self.mine(t, MAGNETON_CEC, zone='bench')
        t.deck(P1, [SUPPORTER])
        t.picks = lambda cards, count, prompt, disp: []
        await t.use(mag, 'Call Signal')
        self.assertFalse(any(self.is_def(c, SUPPORTER) for c in t.zone(P1, 'hand')))
        self.assertNotIn(mag, t.board.pokemon_in_play(P1))

    # --- Electrode EVO 40: Buzzap Thunder -----------------------------------
    async def test_electrode_evo_buzzap_thunder(self):
        t = self.table()
        target = self.mine(t, MAGNEMITE, zone='active')
        other = self.mine(t, self.filler, zone='bench')
        electrode = self.mine(t, ELECTRODE_EVO, zone='bench')
        seen = []
        t.pokemon = lambda cands, prompt: (seen.append(list(cands)) or target)
        await t.use(electrode, 'Buzzap Thunder')
        self.assertIn(electrode, t.board.attached_energies(target))
        # only one legal target here, so the chooser may be skipped
        self.assertTrue(all(other not in c and electrode not in c for c in seen))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)          # it was Knocked Out
        # provides 2 Lightning: Magnemite's Speed Ball [L][C] is now payable
        self.assertIsNotNone(t.attack_offer(target, 'Speed Ball'))

    async def test_electrode_evo_needs_lightning_target(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        electrode = self.mine(t, ELECTRODE_EVO, zone='bench')
        self.assertIsNone(t.ability_offer(electrode, 'Buzzap Thunder'))

    # --- Electrode PLF 33: Magnetic Draw ------------------------------------
    async def test_electrode_plf_magnetic_draw(self):
        t = self.table()
        electrode = self.mine(t, ELECTRODE_PLF)
        t.put(self.item, P1, 'hand')
        await t.use(electrode, 'Magnetic Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    async def test_electrode_plf_magnetic_draw_full_hand(self):
        t = self.table()
        electrode = self.mine(t, ELECTRODE_PLF)
        for _ in range(5):
            t.put(self.item, P1, 'hand')
        deck0 = len(t.zone(P1, 'deck'))
        if t.ability_offer(electrode, 'Magnetic Draw') is not None:
            await t.use(electrode, 'Magnetic Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        self.assertEqual(len(t.zone(P1, 'deck')), deck0)

    # --- Froakie CRI 20: Collect --------------------------------------------
    async def test_froakie_collect(self):
        t = self.table()
        froakie = self.mine(t, FROAKIE, WATER, 1)
        await t.attack(froakie, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Greninja DET 9 ------------------------------------------------------
    async def test_greninja_evasion_jutsu(self):
        for heads in (True, False):
            t = self.table()
            gren = self.mine(t, GRENINJA)
            gren.set_attribute(AttrID.HP, 140)
            t.heads = heads
            dmg = await self.opp_hits(t)
            with self.subTest(heads=heads):
                self.assertEqual(t.damage(gren), 0 if heads else dmg)

    async def test_greninja_furious_shurikens(self):
        t = self.table()
        gren = self.mine(t, GRENINJA, WATER, 2)
        b1 = self.neutral(t.put(self.filler, P2, 'bench'))
        b2 = self.neutral(t.put(self.filler, P2, 'bench'))
        mine_b = self.mine(t, self.filler, zone='bench')
        await t.attack(gren, 'Furious Shurikens')
        hits = sorted(400 - t.hp(p) for p in (self.opp, b1, b2))
        self.assertEqual(hits, [0, 50, 50])
        self.assertEqual(t.damage(mine_b), 0)
        self.assertEqual(t.damage(gren), 0)

    async def test_greninja_furious_shurikens_single_target(self):
        t = self.table()
        gren = self.mine(t, GRENINJA, WATER, 2)
        await t.attack(gren, 'Furious Shurikens')
        self.assertEqual(400 - t.hp(self.opp), 50)

    # --- Energy Search POR 72 -----------------------------------------------
    async def test_energy_search_basic_only(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.deck(P1, [THERAPEUTIC, t.basic_energy(FIRE)])
        card = t.put(ENERGY_SEARCH, P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, disp: (offered.extend(cards) or cards[:count])
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertTrue(self.is_energy_of(hand[0], FIRE))
        self.assertFalse(any(self.is_def(c, THERAPEUTIC) for c in offered))

    # --- Eri TEF 146 --------------------------------------------------------
    async def test_eri_discards_up_to_two_items(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        for spec in (self.item, self.item, self.item, SUPPORTER, t.basic_energy(FIRE)):
            t.put(spec, P2, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, disp: (offered.append((list(cards), count)) or cards[:count])
        eri = t.put(ERI, P1, 'hand')
        await t.play(eri)
        opp_hand = t.zone(P2, 'hand')
        self.assertEqual(len(opp_hand), 3)
        self.assertEqual(sum(self.is_def(c, self.item) for c in opp_hand), 1)
        self.assertEqual(len([c for c in t.zone(P2, 'discard') if self.is_def(c, self.item)]), 2)
        for cards, count in offered:
            self.assertTrue(all(self.is_def(c, self.item) for c in cards))

    async def test_eri_no_items_discards_nothing(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(SUPPORTER, P2, 'hand')
        t.put(t.basic_energy(FIRE), P2, 'hand')
        eri = t.put(ERI, P1, 'hand')
        if t.can(eri, 'UseTrainerCard'):
            await t.play(eri)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)
        self.assertEqual(len(t.zone(P2, 'discard')), 0)

    # --- Ponyta TEF 26: Charge Energy ---------------------------------------
    async def test_ponyta_tef_charge_energy(self):
        t = self.table()
        ponyta = self.mine(t, PONYTA_TEF, FIRE, 1)
        t.deck(P1, [THERAPEUTIC, t.basic_energy(WATER), t.basic_energy(FIRE)])
        offered = []
        t.picks = lambda cards, count, prompt, disp: (offered.append((list(cards), count)) or cards[:count])
        await t.attack(ponyta, 'Charge Energy')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertFalse(self.is_def(hand[0], THERAPEUTIC))
        self.assertTrue(all(not self.is_def(c, THERAPEUTIC) for cards, _ in offered for c in cards))
        self.assertTrue(all(count == 1 for _, count in offered))

    # --- Ponyta CEC 23: Minor Errand-Running --------------------------------
    async def test_ponyta_cec_minor_errand_running(self):
        t = self.table()
        ponyta = self.mine(t, PONYTA_CEC, FIRE, 1)
        t.deck(P1, [THERAPEUTIC, t.basic_energy(WATER), t.basic_energy(FIRE),
                    t.basic_energy(LIGHT)])
        await t.attack(ponyta, 'Minor Errand-Running')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertFalse(any(self.is_def(c, THERAPEUTIC) for c in hand))

    async def test_ponyta_cec_may_take_zero(self):
        t = self.table()
        ponyta = self.mine(t, PONYTA_CEC, FIRE, 1)
        t.deck(P1, [t.basic_energy(FIRE)])
        t.picks = lambda cards, count, prompt, disp: []
        await t.attack(ponyta, 'Minor Errand-Running')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Rapidash SIT 22: Heat Boost ----------------------------------------
    # BUG: Heat Boost's source_predicate uses energy_card_types (Energy cards only) -> never matches a Pokémon.

    async def test_rapidash_heat_boost(self):
        t = self.table()
        ponyta = self.mine(t, PONYTA_TEF, FIRE, 2)
        rapidash = self.mine(t, RAPIDASH, zone='bench')
        bench_opp = self.neutral(t.put(self.filler, P2, 'bench'))
        fire = t.put(t.basic_energy(FIRE), P1, 'hand')
        await t.use(rapidash, 'Heat Boost')
        self.assertIn(fire, t.zone(P1, 'discard'))
        await t.attack(ponyta, 'Flame Tail')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(400 - t.hp(bench_opp), 0)

    async def test_rapidash_heat_boost_not_for_non_fire_pokemon(self):
        # A Water Pokémon with Fire Energy attached is not a "Fire Pokémon".
        t = self.table()
        froakie = self.mine(t, FROAKIE, WATER, 1)
        t.energy(froakie, FIRE, 1)
        rapidash = self.mine(t, RAPIDASH, zone='bench')
        t.put(t.basic_energy(FIRE), P1, 'hand')
        await t.use(rapidash, 'Heat Boost')
        await t.attack(froakie, 'Water Gun')
        self.assertEqual(400 - t.hp(self.opp), 10)

    async def test_rapidash_heat_boost_needs_fire_energy_in_hand(self):
        t = self.table()
        self.mine(t, PONYTA_TEF, FIRE, 1)
        rapidash = self.mine(t, RAPIDASH, zone='bench')
        t.put(t.basic_energy(WATER), P1, 'hand')
        self.assertIsNone(t.ability_offer(rapidash, 'Heat Boost'))

    # --- Sneasel UPR 73: Sneaky Smash ---------------------------------------
    async def test_sneasel_sneaky_smash_going_second_first_turn(self):
        t = self.table()
        t.state.turn_number = 2
        sneasel = self.mine(t, SNEASEL, DARK, 1)
        bench_opp = self.neutral(t.put(self.filler, P2, 'bench'))
        e = t.energy(bench_opp, WATER, 1)
        t.pokemon = lambda cands, prompt: bench_opp if bench_opp in cands else cands[0]
        await t.attack(sneasel, 'Sneaky Smash')
        self.assertNotIn(e, bench_opp.children)
        self.assertIn(e, t.zone(P2, 'discard'))

    async def test_sneasel_sneaky_smash_not_later_turns(self):
        for turn in (1, 3, 4):
            t = self.table()
            t.state.turn_number = turn
            sneasel = self.mine(t, SNEASEL, DARK, 1)
            t.energy(self.opp, WATER, 1)
            with self.subTest(turn=turn):
                self.assertIsNone(t.attack_offer(sneasel, 'Sneaky Smash'))

    # --- Weavile MEP 21: Retaliatory Claw -----------------------------------
    async def test_weavile_mep_retaliatory_claw(self):
        for hp, expected in ((50, 190), (60, 20)):
            t = self.table()
            weavile = self.mine(t, WEAVILE_MEP, DARK, 2)
            weavile.set_attribute(AttrID.HP, hp)
            await t.attack(weavile, 'Retaliatory Claw')
            with self.subTest(hp=hp):
                self.assertEqual(400 - t.hp(self.opp), expected)

    # --- Magnemite PAL 65: Magnetic Charge ----------------------------------
    async def test_magnemite_magnetic_charge(self):
        t = self.table()
        mite = self.mine(t, MAGNEMITE, LIGHT, 1)
        bench = self.mine(t, self.filler, zone='bench')
        for kind in (LIGHT, LIGHT, LIGHT, FIRE):
            t.put(t.basic_energy(kind), P1, 'discard')
        seen = []
        t.pokemon = lambda cands, prompt: (seen.append(list(cands)) or bench)
        await t.attack(mite, 'Magnetic Charge')
        attached = t.board.attached_energies(bench)
        self.assertEqual(len(attached), 2)
        self.assertTrue(all(self.is_energy_of(c, LIGHT) for c in attached))
        self.assertTrue(all(mite not in c for c in seen))       # Benched only
        self.assertEqual(len(t.board.attached_energies(mite)), 1)

    async def test_magnemite_magnetic_charge_no_bench(self):
        t = self.table()
        mite = self.mine(t, MAGNEMITE, LIGHT, 1)
        t.put(t.basic_energy(LIGHT), P1, 'discard')
        if t.attack_offer(mite, 'Magnetic Charge') is not None:
            await t.attack(mite, 'Magnetic Charge')
        self.assertEqual(len(t.board.attached_energies(mite)), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)


if __name__ == "__main__":
    unittest.main()
