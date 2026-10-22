"""Bug hunt, deck 4 (Psychic toolbox): every card, checked against its text,
including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

P, D, G = PokemonTypes.PSYCHIC, PokemonTypes.DARKNESS, PokemonTypes.GRASS
NATU, GALLADE, INKAY = 'XY6.Natu_28', 'SWSH10.Gallade_62', 'SWSH11.Inkay_77'
MALAMAR = 'HF.Malamar_118'        # "HIF 87" = Hidden Fates Shiny Vault SV18 (69 + 18)
BOULDER, MIME, MIMIKYU = 'SV07.IronBoulder_71', 'BW9.MrMime_47', 'Promo_SM.Mimikyu_99'
PATCH, BLOWER = 'ME3.WondrousPatch_117', 'SM2.FieldBlower_163'
TIMEPIECE, BLINDSIDE = 'ME1.StrangeTimepiece_128', 'SV4.TechnicalMachineBlindside_176'
MYSTERY = 'XY4.MysteryEnergy_112'
RALTS, KIRLIA = 'ME2PT5.Ralts_87', 'SWSH12.Kirlia_68'
ABRA, KADABRA, ALAKAZAM = 'ME1.Abra_54', 'ME1.Kadabra_55', 'ME1.Alakazam_56'
ZUBAT, GOLBAT, CROBAT, SABLEYE = 'ME4.Zubat_49', 'SWSH5.Golbat_90', 'SWSH12.Crobat_105', 'SV2.Sableye_136'
GUZMA, NEST, FLOAT, ARTAZON = 'SM3.Guzma_115', 'SV1.NestBall_181', 'XY8.FloatStone_137', 'SV2.Artazon_171'


class Deck4Cards(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def mine(self, t, spec, energy=0, kind=P):
        mon = t.put(spec, P1, 'active')
        if energy:
            t.energy(mon, kind, energy)
        return mon

    # --- Natu (ROS): Psywave + extra Prize -----------------------------------
    async def test_psywave_ten_per_energy_on_defender(self):
        for count in (0, 3):
            t = self.table()
            natu = self.mine(t, NATU, 2)
            if count:
                t.energy(self.opp, G, count)
            await t.attack(natu, 'Psywave')
            with self.subTest(energy=count):
                self.assertEqual(400 - t.hp(self.opp), 10 * count)

    async def test_natu_ko_takes_one_more_prize(self):
        t = self.table()
        natu = self.mine(t, NATU, 2)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, G, 2)
        self.opp.set_attribute(AttrID.HP, 20)
        await t.attack(natu, 'Psywave')
        self.assertNotIn(self.opp, t.board.pokemon_in_play(P2))
        self.assertEqual(t.board.prizes_taken(P1), 2)

    # --- Gallade (ASR): Buddy Catch / Swirling Slice ------------------------
    async def test_buddy_catch_supporter_only_once(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        gallade = t.put(GALLADE, P1, 'bench')
        t.deck(P1, [GUZMA, NEST, ABRA])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:count])[1]
        await t.use(gallade, 'Buddy Catch')
        self.assertEqual(seen['n'], ['Guzma'])
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Guzma'])
        self.assertIsNone(t.ability_offer(gallade, 'Buddy Catch'))

    async def test_swirling_slice_moves_energy_to_bench(self):
        t = self.table()
        gallade = self.mine(t, GALLADE, 3)
        bench = t.put(self.filler, P1, 'bench')
        await t.attack(gallade, 'Swirling Slice')
        self.assertEqual(400 - t.hp(self.opp), 160)
        self.assertEqual(len(t.board.attached_energies(gallade)), 2)
        self.assertEqual(len(t.board.attached_energies(bench)), 1)

    # --- Inkay (LOR): Fickle Attack ------------------------------------------
    async def test_fickle_attack(self):
        for heads, dmg in ((True, 30), (False, 0)):
            t = self.table()
            inkay = self.mine(t, INKAY, 1)
            t.heads = heads
            await t.attack(inkay, 'Fickle Attack')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Malamar (HIF): Psychic Recharge ------------------------------------
    async def test_hif_malamar_is_hidden_fates_and_recharges(self):
        self.assertEqual(fixtures.definition(MALAMAR).set_code, 'HF')
        t = self.table()
        mal = t.put(MALAMAR, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.put(t.basic_energy(P), P1, 'discard')
        await t.use(mal, 'Psychic Recharge')
        self.assertEqual(len(t.board.attached_energies(bench)), 1)
        self.assertIsNone(t.ability_offer(mal, 'Psychic Recharge'))

    async def test_hif_malamar_no_psychic_energy_in_discard(self):
        t = self.table()
        mal = t.put(MALAMAR, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.put(t.basic_energy(G), P1, 'discard')
        entry = t.ability_offer(mal, 'Psychic Recharge')
        if entry is not None:
            await t.do(entry)
        self.assertEqual(len(t.board.attached_energies(bench)), 0)

    # --- Iron Boulder: Adjusted Horn ----------------------------------------
    async def horn(self, mine, theirs):
        t = self.table()
        boulder = self.mine(t, BOULDER, 2)
        for _ in range(mine):
            t.put(self.item, P1, 'hand')
        for _ in range(theirs):
            t.put(self.item, P2, 'hand')
        await t.attack(boulder, 'Adjusted Horn')
        return 400 - t.hp(self.opp)

    async def test_adjusted_horn_equal_hands(self):
        self.assertEqual(await self.horn(2, 2), 170)
        self.assertEqual(await self.horn(0, 0), 170)

    async def test_adjusted_horn_does_nothing_with_unequal_hands(self):
        # BUG: "If you don't have the same number of cards in your hand ... does nothing" is ignored
        self.assertEqual(await self.horn(2, 3), 0)

    # --- Mr. Mime (PLF): Bench Barrier / Psy Bolt ---------------------------
    async def test_bench_barrier_protects_own_bench_only(self):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        crobat = t.put(CROBAT, P2, 'active')
        t.energy(crobat, D, 3)
        my_active = t.put(self.filler, P1, 'active')
        my_active.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.put(MIME, P1, 'bench')
        target = t.put(self.filler, P1, 'bench')
        t.next_turn()
        t.pokemon = lambda c, p: target if target in c else c[0]
        before = t.hp(target)
        await t.attack(crobat, 'Critical Bite', pid=P2)    # 30 to a Benched Pokémon
        self.assertEqual(t.hp(target), before)

    async def test_bench_barrier_belongs_to_its_owner(self):
        t = self.table()
        t.put(MIME, P2, 'bench')        # the opponent's Mime protects only their own bench
        crobat = self.mine(t, CROBAT, 3, D)
        t.put(MIME, P1, 'bench')        # my Mime doesn't stop my own attacks either
        target = t.put(self.filler, P2, 'bench')
        t.pokemon = lambda c, p: target if target in c else c[0]
        before = t.hp(target)
        await t.attack(crobat, 'Critical Bite')
        self.assertEqual(before - t.hp(target), 0)   # opponent's Mime still protects it
        # remove the opponent's Mime: now damage lands
        t = self.table()
        crobat = self.mine(t, CROBAT, 3, D)
        t.put(MIME, P1, 'bench')
        target = t.put(self.filler, P2, 'bench')
        t.pokemon = lambda c, p: target if target in c else c[0]
        before = t.hp(target)
        await t.attack(crobat, 'Critical Bite')
        self.assertEqual(before - t.hp(target), 30)

    async def test_psy_bolt_paralyzes_on_heads(self):
        for heads in (True, False):
            t = self.table()
            mime = self.mine(t, MIME, 2)
            t.heads = heads
            await t.attack(mime, 'Psy Bolt')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 20)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    # --- Mimikyu (SMP 99): Filch / Copycat ----------------------------------
    async def test_filch_draws_two(self):
        t = self.table()
        mim = self.mine(t, MIMIKYU, 1)
        await t.attack(mim, 'Filch')
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    async def test_copycat_uses_opponents_last_attack(self):
        t = self.table(opp=SABLEYE)
        t.energy(self.opp, D)
        mim = self.mine(t, MIMIKYU, 2)
        mim.set_attribute(AttrID.HP, 400)
        mim.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.next_turn()
        await t.attack(self.opp, 'Unseen Claw', pid=P2)       # 20 to Mimikyu
        t.next_turn()
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [CONFUSED])
        await t.attack(mim, 'Copycat')
        self.assertEqual(400 - t.hp(self.opp), 90)            # Unseen Claw +70 vs Confused

    async def test_copycat_nothing_without_last_attack(self):
        t = self.table()
        mim = self.mine(t, MIMIKYU, 2)
        await t.attack(mim, 'Copycat')
        self.assertEqual(t.hp(self.opp), 400)

    # --- Wondrous Patch ------------------------------------------------------
    async def test_wondrous_patch_benched_psychic_only(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        ralts = t.put(RALTS, P1, 'bench')
        other = t.put(SABLEYE, P1, 'bench')
        t.put(t.basic_energy(P), P1, 'discard')
        offered = []
        t.pokemon = lambda c, p: (offered.extend(c), c[0])[1]
        await t.play(t.put(PATCH, P1, 'hand'))
        self.assertEqual(offered, [ralts])
        self.assertEqual(len(t.board.attached_energies(ralts)), 1)

    async def test_wondrous_patch_needs_basic_psychic_and_benched_psychic(self):
        t = self.table()
        ralts_active = t.put(RALTS, P1, 'active')     # Active Psychic doesn't count
        t.put(t.basic_energy(P), P1, 'discard')
        card = t.put(PATCH, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.put(RALTS, P1, 'bench')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(RALTS, P1, 'bench')
        t.put(MYSTERY, P1, 'discard')                 # special Psychic: no
        card = t.put(PATCH, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Field Blower --------------------------------------------------------
    async def test_field_blower_up_to_two_tools_or_stadium(self):
        t = self.table()
        me = t.put(self.filler, P1, 'active')
        tool = t.attach(FLOAT, self.opp)
        stadium = t.stadium(ARTAZON, P1)
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', count), list(cards)[:count])[1]
        await t.play(t.put(BLOWER, P1, 'hand'))
        self.assertEqual(seen['c'], 2)
        self.assertNotIn(tool, self.opp.children)
        self.assertFalse(t.board.find_global_area('activeStadium').children)
        self.assertIn(tool, t.zone(P2, 'discard'))

    async def test_field_blower_needs_a_target(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        card = t.put(BLOWER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Strange Timepiece ----------------------------------------------------
    async def evolved(self, t, chain, where='active'):
        mon = t.put(chain[0], P1, where)
        for spec in chain[1:]:
            card = t.put(spec, P1, 'hand')
            await t._run(lambda: t.session.perform_evolution(P1, card, mon))
            mon = next(p for p in t.board.pokemon_in_play(P1)
                       if def_for(p.archetype_id).display_name == def_for(card.archetype_id).display_name)
        return mon

    async def test_strange_timepiece_devolves_psychic_any_number(self):
        t = self.table()
        ala = await self.evolved(t, [ABRA, KADABRA, ALAKAZAM])
        ala.set_attribute(AttrID.HP, t.hp(ala) - 30)

        async def choose(ctx, prompt, options, *a, **k):
            return len(options) - 1                 # remove both Evolution cards
        with patch.object(EffectContext, 'choose', choose):
            await t.play(t.put(TIMEPIECE, P1, 'hand'))
        active = t.active(P1)
        self.assertEqual(def_for(active.archetype_id).display_name, 'Abra')
        hand = [n for n in t.names(t.zone(P1, 'hand')) if n != 'Pokégear 3.0']   # Psychic Draw draws
        self.assertEqual(hand, ['Alakazam', 'Kadabra'])
        self.assertEqual(t.damage(active), 30)

    async def test_strange_timepiece_not_playable_without_evolved_psychic(self):
        t = self.table()
        t.put(ABRA, P1, 'active')                     # Basic Psychic only
        card = t.put(TIMEPIECE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_strange_timepiece_not_playable_with_only_non_psychic_evolved(self):
        # BUG: play condition accepts any evolved Pokémon, not only an evolved Psychic one
        t = self.table()
        await self.evolved(t, [ZUBAT, GOLBAT])
        card = t.put(TIMEPIECE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Technical Machine: Blindside -------------------------------------
    async def test_blindside_damaged_target_and_discard_end_of_turn(self):
        t = self.table()
        me = self.mine(t, MIMIKYU, 3)
        tm = t.put(BLINDSIDE, P1, 'hand')
        await t.play(tm, targets=[me.entity_id])
        self.assertIn(tm, me.children)
        clean = t.put(self.filler, P2, 'bench')
        hurt = t.put(self.filler, P2, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 10)   # 1 damage counter
        offered = []
        t.pokemon = lambda c, p: (offered.extend(c), hurt if hurt in c else c[0])[1]
        await t.attack(me, 'Blindside')
        self.assertNotIn(clean, offered)
        self.assertNotIn(self.opp, offered)          # undamaged Active: not a target
        self.assertEqual(t.damage(hurt), 110)
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        self.assertIn(tm, t.zone(P1, 'discard'))

    async def test_blindside_needs_three_energy(self):
        t = self.table()
        me = self.mine(t, MIMIKYU, 2)
        await t.play(t.put(BLINDSIDE, P1, 'hand'), targets=[me.entity_id])
        self.assertIsNone(t.attack_offer(me, 'Blindside'))

    # --- Mystery Energy -------------------------------------------------------
    async def test_mystery_energy_psychic_only_and_retreat(self):
        t = self.table()
        gallade = t.put(GALLADE, P1, 'active')      # retreat 2
        sab = t.put(SABLEYE, P1, 'bench')
        energy = t.put(MYSTERY, P1, 'hand')
        targets = t.targets(energy, 'DefaultEnergyPlayAbility')
        self.assertIn(gallade.entity_id, targets)
        self.assertNotIn(sab.entity_id, targets)
        await t.play(energy, targets=[gallade.entity_id])
        self.assertIn(energy, gallade.children)
        self.assertEqual(t.retreat(gallade), 0)

    async def test_mystery_energy_provides_psychic(self):
        t = self.table()
        inkay = t.put(INKAY, P1, 'active')
        t.attach(MYSTERY, inkay)
        self.assertIsNotNone(t.attack_offer(inkay, 'Fickle Attack'))


if __name__ == "__main__":
    unittest.main()
