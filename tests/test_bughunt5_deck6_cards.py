"""Bug hunt round 5, deck 6 (Dragon): Bagon CES 104, Shelgon CES 105,
Salamence EVS 109, Dratini SUM 94, Dragonair SUM 95, Dragonite TEU 119,
Drampa EVS 119, Gapejaw Bog ASR 142."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

R, W, L, G, F = (PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.LIGHTNING,
                 PokemonTypes.GRASS, PokemonTypes.FIGHTING)
BAGON, SHELGON, SALAMENCE = 'SM7.Bagon_104', 'SM7.Shelgon_105', 'SWSH7.Salamence_109'
DRATINI, DRAGONAIR, DRAGONITE = 'SM1.Dratini_94', 'SM1.Dragonair_95', 'SM9.Dragonite_119'
DRAMPA, BOG = 'SWSH7.Drampa_119', 'SWSH10.GapejawBog_142'
RESEARCH = 'CZ.ProfessorsResearch_150'    # Supporter
NEST = 'SM1.NestBall_123'                 # Basic from deck onto Bench
CHERUBI = 'SWSH9.Cherubi_12'


class Deck6Cards5(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        mon._start_hp = mon.get_attribute(AttrID.HP, 0)
        return mon

    @staticmethod
    def took(t, mon):
        return mon._start_hp - t.hp(mon)

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
        return t

    # --- Bagon: Reckless Charge --------------------------------------------
    async def test_reckless_charge_self_damage(self):
        t = self.table()
        b = t.put(BAGON, P1, 'active')
        t.energy(b, R, 2)
        await t.attack(b, 'Reckless Charge')
        self.assertEqual(self.took(t, self.opp), 40)
        self.assertEqual(t.damage(b), 10)

    # --- Shelgon: Raging Blade ---------------------------------------------
    async def test_raging_blade_undamaged(self):
        t = self.table()
        s = t.put(SHELGON, P1, 'active')
        t.energy(s, R); t.energy(s, W)
        await t.attack(s, 'Raging Blade')
        self.assertEqual(self.took(t, self.opp), 30)

    async def test_raging_blade_damaged(self):
        t = self.table()
        s = t.put(SHELGON, P1, 'active', hp=80)
        t.energy(s, R); t.energy(s, W)
        await t.attack(s, 'Raging Blade')
        self.assertEqual(self.took(t, self.opp), 80)

    # --- Salamence: Intimidating Roar / Fierce Dragon ----------------------
    async def test_intimidating_roar_switches_opponent_once(self):
        t = self.table()
        sal = t.put(SALAMENCE, P1, 'active')
        benched = t.put(CHERUBI, P2, 'bench')
        await t.use(sal, 'Intimidating Roar')
        self.assertIs(t.active(P2), benched)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIs(t.active(P1), sal)                 # my side untouched
        self.assertIsNone(t.ability_offer(sal, 'Intimidating Roar'))

    async def test_intimidating_roar_works_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sal = t.put(SALAMENCE, P1, 'bench')
        benched = t.put(CHERUBI, P2, 'bench')
        await t.use(sal, 'Intimidating Roar')
        self.assertIs(t.active(P2), benched)

    async def test_intimidating_roar_needs_opponent_bench(self):
        t = self.table()
        sal = t.put(SALAMENCE, P1, 'active')
        t.put(self.filler, P1, 'bench')
        self.assertIsNone(t.ability_offer(sal, 'Intimidating Roar'))

    async def test_fierce_dragon_clean_target(self):
        t = self.table()
        sal = t.put(SALAMENCE, P1, 'active')
        t.energy(sal, R); t.energy(sal, W)
        await t.attack(sal, 'Fierce Dragon')
        self.assertEqual(self.took(t, self.opp), 100)

    async def test_fierce_dragon_damaged_target(self):
        # 100 alone would not KO the damaged filler; 100+120 does.
        t = Table(self)
        opp = t.put(self.filler, P2, 'active')
        self.neutral(opp, t.hp(opp) - 10)                 # 1 damage counter
        self.assertGreater(t.hp(opp), 100)
        self.assertLessEqual(t.hp(opp), 220)
        t.put(self.filler, P2, 'bench')                    # keeps the game going
        sal = t.put(SALAMENCE, P1, 'active')
        t.energy(sal, R); t.energy(sal, W)
        await t.attack(sal, 'Fierce Dragon')
        self.assertIn(opp, t.zone(P2, 'discard'))

    # --- Dratini: Signs of Evolution -----------------------------------------
    async def test_signs_of_evolution_one_of_each(self):
        t = self.table()
        d = t.put(DRATINI, P1, 'active')
        t.energy(d, G)
        family = t.deck(P1, [DRATINI, DRATINI, DRAGONAIR, DRAGONITE])
        await t.attack(d, 'Signs of Evolution')
        hand = t.zone(P1, 'hand')
        self.assertEqual(t.names(hand), ['Dragonair', 'Dragonite', 'Dratini'])
        self.assertEqual(sum(1 for c in family if c in t.zone(P1, 'deck')), 1)

    async def test_signs_of_evolution_ignores_others(self):
        t = self.table()
        d = t.put(DRATINI, P1, 'active')
        t.energy(d, G)
        t.deck(P1, [BAGON, SHELGON, DRAGONAIR])
        await t.attack(d, 'Signs of Evolution')
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Dragonair'])

    # --- Dragonair: Dragon's Wish ------------------------------------------
    def energy_play_ok(self, t, card):
        return t.can(card, 'DefaultEnergyPlayAbility')

    # FIXED (was BUG): Dragon's Wish does nothing; the shared interpreter has no handler and legal_actions has no 'unlimited attach' hook
    async def test_dragons_wish_next_turn_any_number(self):
        t = self.table()
        da = t.put(DRAGONAIR, P1, 'active')
        t.energy(da, W)
        bench = t.put(self.filler, P1, 'bench')
        await t.attack(da, "Dragon's Wish")
        t.next_turn(); t.next_turn()
        e1, e2, e3 = (t.put(t.basic_energy(k), P1, 'hand') for k in (W, L, G))
        await t.play(e1, targets=[da.entity_id])
        self.assertTrue(self.energy_play_ok(t, e2))
        await t.play(e2, targets=[bench.entity_id])
        await t.play(e3, targets=[da.entity_id])
        self.assertIn(e1, da.children)
        self.assertIn(e2, bench.children)
        self.assertIn(e3, da.children)

    async def test_dragons_wish_expires_after_next_turn(self):
        t = self.table()
        da = t.put(DRAGONAIR, P1, 'active')
        t.energy(da, W)
        await t.attack(da, "Dragon's Wish")
        for _ in range(4):
            t.next_turn()
        e1, e2 = (t.put(t.basic_energy(W), P1, 'hand') for _ in range(2))
        await t.play(e1, targets=[da.entity_id])
        self.assertFalse(self.energy_play_ok(t, e2))

    async def test_normal_turn_one_energy_only(self):
        t = self.table()
        da = t.put(DRAGONAIR, P1, 'active')
        e1, e2 = (t.put(t.basic_energy(W), P1, 'hand') for _ in range(2))
        await t.play(e1, targets=[da.entity_id])
        self.assertFalse(self.energy_play_ok(t, e2))

    # --- Dragonite: Fast Call ------------------------------------------------
    async def test_fast_call_finds_supporter_once(self):
        t = self.table()
        dn = t.put(DRAGONITE, P1, 'active')
        sup = t.deck(P1, [RESEARCH])[0]
        t.deck(P1, [BAGON, NEST])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'] = list(cards)
            return [c for c in cards if c is sup][:count]
        t.picks = picks
        await t.use(dn, 'Fast Call')
        self.assertEqual(t.zone(P1, 'hand'), [sup])
        self.assertEqual(t.names(seen['cards']), ["Professor's Research"])
        self.assertIsNone(t.ability_offer(dn, 'Fast Call'))

    async def test_fast_call_works_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        dn = t.put(DRAGONITE, P1, 'bench')
        sup = t.deck(P1, [RESEARCH])[0]
        await t.use(dn, 'Fast Call')
        self.assertIn(sup, t.zone(P1, 'hand'))

    # --- Drampa: Berserk -----------------------------------------------------
    async def test_berserk_no_bench_damage(self):
        t = self.table()
        dr = t.put(DRAMPA, P1, 'active', hp=50)          # own Active damage doesn't count
        t.energy(dr, W); t.energy(dr, F)
        t.put(self.filler, P1, 'bench')
        await t.attack(dr, 'Berserk')
        self.assertEqual(self.took(t, self.opp), 70)

    async def test_berserk_damaged_bench(self):
        t = self.table()
        dr = t.put(DRAMPA, P1, 'active')
        t.energy(dr, W); t.energy(dr, F)
        b = t.put(self.filler, P1, 'bench')
        b.set_attribute(AttrID.HP, t.hp(b) - 10)
        await t.attack(dr, 'Berserk')
        self.assertEqual(self.took(t, self.opp), 160)

    async def test_berserk_opponent_bench_damage_doesnt_count(self):
        t = self.table()
        dr = t.put(DRAMPA, P1, 'active')
        t.energy(dr, W); t.energy(dr, F)
        ob = t.put(self.filler, P2, 'bench')
        ob.set_attribute(AttrID.HP, t.hp(ob) - 10)
        await t.attack(dr, 'Berserk')
        self.assertEqual(self.took(t, self.opp), 70)

    # --- Gapejaw Bog -------------------------------------------------------
    async def test_gapejaw_bog_both_players_bench_from_hand(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.stadium(BOG, P1)
        mine = t.put(BAGON, P1, 'hand')
        await t.play(mine)
        self.assertIn(mine, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(mine), 20)
        t.next_turn()
        theirs = t.put(DRATINI, P2, 'hand')
        await t.play(theirs, pid=P2)
        self.assertIn(theirs, t.zone(P2, 'bench'))
        self.assertEqual(t.damage(theirs), 20)

    async def test_gapejaw_bog_not_for_evolution(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.stadium(BOG, P1)
        b = t.put(BAGON, P1, 'bench')
        t.state.entered_play_turn[b.entity_id] = 0
        sh = t.put(SHELGON, P1, 'hand')
        await t.play(sh, targets=[b.entity_id])
        top = t.zone(P1, 'bench')[0]
        self.assertEqual(t.damage(top), 0)

    async def test_gapejaw_bog_not_for_bench_from_deck(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.stadium(BOG, P1)
        target = t.deck(P1, [BAGON])[0]
        await t.play(t.put(NEST, P1, 'hand'))
        self.assertIn(target, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(target), 0)


if __name__ == '__main__':
    unittest.main()
