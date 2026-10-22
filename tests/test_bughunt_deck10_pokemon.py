"""Bug hunt, deck 10 (Darkness): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, ASLEEP, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

D = PokemonTypes.DARKNESS
KOFFING, WEEZING = 'SWSH45.Koffing_41', 'SWSH2.GalarianWeezing_113'
PURRLOIN, LIEPARD = 'RSV10PT5.Purrloin_55', 'SWSH9.Liepard_91'
TRUBBISH, GARBODOR = 'SWSH8.Trubbish_168', 'SWSH2.Garbodor_118'
ZUBAT, GOLBAT, CROBAT = 'ME4.Zubat_49', 'SWSH5.Golbat_90', 'SWSH12.Crobat_105'
PECHARUNT, SABLEYE, ABSOL = 'SVP.Pecharunt_149', 'SV2.Sableye_136', 'XY6.Absol_40'
QWILFISH, BONNET = 'ME4.Qwilfish_52', 'SV4.BruteBonnet_123'
CAPSULE = 'SV05.AncientBoosterEnergyCapsule_140'
ARTAZON = 'SV2.Artazon_171'
LELE = 'Promo_SM.TapuLele_152'          # a Basic with an activated Ability (Wonder Tag)


class Deck10Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    # --- Koffing: Ascension ------------------------------------------------
    async def test_koffing_ascension_evolves_from_deck(self):
        t = self.table()
        koffing = t.put(KOFFING, P1, 'active')
        t.energy(koffing, D)
        t.deck(P1, [WEEZING])
        await t.attack(koffing, 'Ascension')
        active = t.active(P1)
        self.assertEqual(def_for(active.archetype_id).display_name, 'Galarian Weezing')
        self.assertIn(koffing, list(active.children) + [active])

    async def test_koffing_ascension_without_evolution_in_deck(self):
        t = self.table()
        koffing = t.put(KOFFING, P1, 'active')
        t.energy(koffing, D)
        await t.attack(koffing, 'Ascension')
        self.assertIs(t.active(P1), koffing)

    # --- Galarian Weezing: Neutralizing Gas / Severe Poison ----------------
    async def test_neutralizing_gas_active_locks_opponent_only(self):
        t = self.table()
        t.put(WEEZING, P2, 'active')
        my_lele = t.put(LELE, P1, 'bench')
        # Wonder Tag is an on-bench trigger; use Liepard's activated Trade instead
        liepard = t.put(LIEPARD, P1, 'bench')
        t.put(self.filler, P1, 'hand'); t.put(self.filler, P1, 'hand')
        self.assertIsNone(t.ability_offer(liepard, 'Trade'))
        # Weezing on the Bench: no lock
        t2 = self.table()
        t2.put(WEEZING, P2, 'bench')
        liepard2 = t2.put(LIEPARD, P1, 'bench')
        t2.put(self.filler, P1, 'hand'); t2.put(self.filler, P1, 'hand')
        self.assertIsNotNone(t2.ability_offer(liepard2, 'Trade'))
        # Its owner's Abilities are not locked
        t3 = self.table()
        t3.put(WEEZING, P1, 'active')
        liepard3 = t3.put(LIEPARD, P1, 'bench')
        t3.put(self.filler, P1, 'hand'); t3.put(self.filler, P1, 'hand')
        self.assertIsNotNone(t3.ability_offer(liepard3, 'Trade'))

    async def test_severe_poison_four_counters(self):
        t = self.table()
        weezing = t.put(WEEZING, P1, 'active')
        t.energy(weezing, D)
        await t.attack(weezing, 'Severe Poison')
        self.assertIn(POISONED, t.conditions(self.opp))
        before = t.hp(self.opp)
        await t.checkup()
        self.assertEqual(before - t.hp(self.opp), 40)

    # --- Purrloin: Invite Evil ---------------------------------------------
    async def test_invite_evil_only_darkness_pokemon(self):
        t = self.table()
        purrloin = t.put(PURRLOIN, P1, 'active')
        t.energy(purrloin, D)
        t.deck(P1, [ZUBAT, TRUBBISH, SABLEYE, ABSOL, LELE])
        offered = {}

        def picks(cards, count, prompt, display):
            offered['names'] = t.names(cards)
            offered['count'] = count
            return cards[:count]
        t.picks = picks
        await t.attack(purrloin, 'Invite Evil')
        self.assertEqual(offered['count'], 3)
        self.assertNotIn('Tapu Lele', offered['names'])
        self.assertEqual(len([c for c in t.zone(P1, 'hand')
                              if def_for(c.archetype_id).display_name in ('Zubat', 'Trubbish', 'Sableye', 'Absol')]), 3)

    # --- Liepard: Trade -----------------------------------------------------
    async def test_trade_discards_one_draws_two_once(self):
        t = self.table()
        liepard = t.put(LIEPARD, P1, 'bench')
        t.put(self.filler, P1, 'hand')
        t.put(self.filler, P1, 'hand')
        await t.use(liepard, 'Trade')
        self.assertEqual(len(t.zone(P1, 'discard')), 1)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertIsNone(t.ability_offer(liepard, 'Trade'))

    async def test_trade_needs_a_card_to_discard(self):
        t = self.table()
        liepard = t.put(LIEPARD, P1, 'bench')
        self.assertIsNone(t.ability_offer(liepard, 'Trade'))

    # --- Trubbish ---------------------------------------------------------
    async def test_trubbish_call_for_family_and_poison(self):
        t = self.table()
        trubbish = t.put(TRUBBISH, P1, 'active')
        t.energy(trubbish, D, 2)
        t.deck(P1, [ZUBAT])
        await t.attack(trubbish, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 1)
        t.next_turn(); t.next_turn()
        before = t.hp(self.opp)
        await t.attack(trubbish, 'Super Poison Breath')
        self.assertEqual(before - t.hp(self.opp), 20)
        self.assertIn(POISONED, t.conditions(self.opp))

    # --- Garbodor: Poisonous Puddle -------------------------------------
    async def test_poisonous_puddle_needs_any_stadium_once(self):
        t = self.table()
        garbodor = t.put(GARBODOR, P1, 'bench')
        self.assertIsNone(t.ability_offer(garbodor, 'Poisonous Puddle'))
        t.stadium(ARTAZON, P2)            # the opponent's Stadium counts too
        self.assertIsNotNone(t.ability_offer(garbodor, 'Poisonous Puddle'))
        await t.use(garbodor, 'Poisonous Puddle')
        self.assertIn(POISONED, t.conditions(self.opp))
        self.assertIsNone(t.ability_offer(garbodor, 'Poisonous Puddle'))

    # --- Zubat / Golbat / Crobat ---------------------------------------
    async def test_zubat_supersonic_confuses(self):
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'active')
        t.energy(zubat, D)
        await t.attack(zubat, 'Supersonic')
        self.assertIn(CONFUSED, t.conditions(self.opp))

    async def test_golbat_discreet_draw_on_evolve_from_hand(self):
        t = self.table()
        zubat = t.put(ZUBAT, P1, 'bench')
        golbat = t.put(GOLBAT, P1, 'hand')
        hand = len(t.zone(P1, 'hand'))
        await t.play(golbat, targets=[zubat.entity_id])
        self.assertEqual(len(t.zone(P1, 'hand')), hand - 1 + 2)

    async def test_golbat_air_slash_discards_energy(self):
        t = self.table()
        golbat = t.put(GOLBAT, P1, 'active')
        t.energy(golbat, D, 2)
        before = t.hp(self.opp)
        await t.attack(golbat, 'Air Slash')
        self.assertEqual(before - t.hp(self.opp), 50)
        self.assertEqual(len(t.board.attached_energies(golbat)), 1)

    async def test_crobat_venomous_fang(self):
        t = self.table()
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D)
        before = t.hp(self.opp)
        await t.attack(crobat, 'Venomous Fang')
        self.assertEqual(before - t.hp(self.opp), 50)
        self.assertIn(POISONED, t.conditions(self.opp))

    async def test_critical_bite_bench_target_and_extra_prizes(self):
        t = self.table()
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D, 3)
        bench = t.put(self.filler, P2, 'bench', hp=30)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [D.value])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(crobat, 'Critical Bite')
        self.assertNotIn(bench, t.board.pokemon_in_play(P2))
        self.assertEqual(t.board.prizes_taken(P1), 3)

    async def test_critical_bite_no_weakness_on_bench(self):
        t = self.table()
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D, 3)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [D.value])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        before = t.hp(bench)
        await t.attack(crobat, 'Critical Bite')
        self.assertEqual(before - t.hp(bench), 30)
        self.assertEqual(t.board.prizes_taken(P1), 0)

    # --- Pecharunt ---------------------------------------------------------
    async def test_toxic_subjugation_active_adds_five_counters(self):
        for where, extra in (('active', 50), ('bench', 0)):
            t = self.table()
            pech = t.put(PECHARUNT, P1, where)
            if where == 'bench':
                t.put(self.filler, P1, 'active')
            self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
            before = t.hp(self.opp)
            await t.checkup()
            with self.subTest(where=where):
                self.assertEqual(before - t.hp(self.opp), 10 + extra)

    async def test_toxic_subjugation_off_under_neutralizing_gas(self):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        weezing = t.put(WEEZING, P2, 'active')
        t.put(PECHARUNT, P1, 'active')
        weezing.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        before = t.hp(weezing)
        await t.checkup()
        self.assertEqual(before - t.hp(weezing), 10)

    async def test_poison_chain_poisons_and_blocks_retreat(self):
        t = self.table()
        pech = t.put(PECHARUNT, P1, 'active')
        t.energy(pech, D, 2)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, PokemonTypes.WATER, 4)
        await t.attack(pech, 'Poison Chain')
        self.assertIn(POISONED, t.conditions(self.opp))
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))

    # --- Sableye -------------------------------------------------------
    async def test_sableye(self):
        t = self.table()
        sab = t.put(SABLEYE, P1, 'active')
        t.energy(sab, D)
        await t.attack(sab, 'Night Eyes')
        self.assertIn(ASLEEP, t.conditions(self.opp))
        for condition, dmg in (([], 20), ([CONFUSED], 90)):
            t = self.table()
            sab = t.put(SABLEYE, P1, 'active')
            t.energy(sab, D)
            self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, condition)
            before = t.hp(self.opp)
            await t.attack(sab, 'Unseen Claw')
            with self.subTest(condition=condition):
                self.assertEqual(before - t.hp(self.opp), dmg)

    # --- Absol: Cursed Eyes -----------------------------------------------
    async def test_cursed_eyes_moves_three_counters_on_bench_play(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.damage_on = self.opp
        self.opp.set_attribute(AttrID.HP, t.hp(self.opp) - 50)
        other = t.put(self.filler, P2, 'bench')
        absol = t.put(ABSOL, P1, 'hand')
        order = iter([self.opp, other])
        t.pokemon = lambda c, p: next(order)
        await t.play(absol)
        self.assertEqual(t.damage(self.opp), 20)
        self.assertEqual(t.damage(other), 30)

    # --- Qwilfish -----------------------------------------------------------
    async def test_poison_point_active_only(self):
        for where in ('active', 'bench'):
            t = self.table()
            q = t.put(QWILFISH, P1, where)
            if where == 'bench':
                t.put(self.filler, P1, 'active')
            t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
            attacker = t.put(SABLEYE, P2, 'active')
            t.energy(attacker, D)
            t.next_turn()
            await t.attack(attacker, 'Unseen Claw', pid=P2)
            with self.subTest(where=where):
                self.assertEqual(POISONED in t.conditions(attacker), where == 'active')

    async def test_venoshock(self):
        for condition, dmg in (([], 30), ([POISONED], 80)):
            t = self.table()
            q = t.put(QWILFISH, P1, 'active')
            t.energy(q, D)
            self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, condition)
            before = t.hp(self.opp)
            await t.attack(q, 'Venoshock')
            with self.subTest(condition=condition):
                self.assertEqual(before - t.hp(self.opp), dmg)

    # --- Brute Bonnet + Ancient Booster Energy Capsule ---------------------
    async def test_toxic_powder_needs_capsule_and_capsule_protects(self):
        t = self.table()
        bonnet = t.put(BONNET, P1, 'active')
        self.assertIsNone(t.ability_offer(bonnet, 'Toxic Powder'))
        t.attach(CAPSULE, bonnet)
        self.assertEqual(t.hp(bonnet), 120)  # max HP shown after attach is recomputed elsewhere
        await t.use(bonnet, 'Toxic Powder')
        self.assertIn(POISONED, t.conditions(self.opp))
        self.assertNotIn(POISONED, t.conditions(bonnet))   # the Capsule's holder can't be Poisoned
        self.assertIsNone(t.ability_offer(bonnet, 'Toxic Powder'))

    async def test_toxic_powder_poisons_own_active_without_protection(self):
        t = self.table()
        mine = t.put(self.filler, P1, 'active')
        bonnet = t.put(BONNET, P1, 'bench')
        t.attach(CAPSULE, bonnet)
        await t.use(bonnet, 'Toxic Powder')
        self.assertIn(POISONED, t.conditions(self.opp))
        self.assertIn(POISONED, t.conditions(mine))

    async def test_rampaging_hammer_locks_next_turn(self):
        t = self.table()
        bonnet = t.put(BONNET, P1, 'active')
        t.energy(bonnet, D, 3)
        self.opp.set_attribute(AttrID.HP, 400)
        await t.attack(bonnet, 'Rampaging Hammer')
        self.assertEqual(400 - t.hp(self.opp), 120)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(bonnet, 'Rampaging Hammer'))

    async def test_capsule_hp_and_cure(self):
        from spirit.game.session.passives import effective_max_hp
        t = self.table()
        bonnet = t.put(BONNET, P1, 'active')
        bonnet.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED, CONFUSED])
        capsule = t.put(CAPSULE, P1, 'hand')
        await t.play(capsule, targets=[bonnet.entity_id])
        self.assertEqual(effective_max_hp(t.board, bonnet), 120 + 60)
        self.assertEqual(t.conditions(bonnet), set())


if __name__ == "__main__":
    unittest.main()
