"""Bug hunt round 5, deck 4 (Colorless): every Pokémon, checked against its
printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, F, D = PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.DARKNESS
PIDGEY = 'SM9.Pidgey_122'
PORYGON, PORYGON2, PORYGONZ = 'SM10.Porygon_155', 'SM10.Porygon2_156', 'SM10.PorygonZ_157'
SLAKOTH, VIGOROTH, SLAKING = 'SM11.Slakoth_168', 'SWSH7.Vigoroth_130', 'SM7.Slaking_115'
DITTO, KANGASKHAN = 'CZ.Ditto_107', 'SWSH3.Kangaskhan_133'
LUGIA, SNORLAX = 'CEL25.Lugia_22', 'SWSH11.Snorlax_143'
LIEPARD = 'SWSH9.Liepard_91'              # activated Ability: Trade
ZUBAT = 'ME4.Zubat_49'                     # Supersonic: confuses
TIMBURR = 'BW1.Timburr_58'                 # vanilla Fighting attacker (Pound 30, FF)
ARTAZON = 'SV2.Artazon_171'
WARP, WGUARD = 'SL.WarpEnergy_70', 'SM11.WeaknessGuardEnergy_213'


class Bughunt5Deck4Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    @staticmethod
    def lost(p, hp=400):
        return hp - p.get_attribute(AttrID.HP, 0)

    def name(self, card):
        return def_for(card.archetype_id).display_name

    async def test_set_codes(self):
        for path, code in ((PIDGEY, 'SM9'), (PORYGON, 'SM10'), (PORYGON2, 'SM10'),
                           (PORYGONZ, 'SM10'), (SLAKOTH, 'SM11'), (VIGOROTH, 'SWSH7'),
                           (SLAKING, 'SM7'), (DITTO, 'CZ'), (KANGASKHAN, 'SWSH3'),
                           (LUGIA, 'CEL25'), (SNORLAX, 'SWSH11')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Pidgey (TEU 122): Quick Attack ------------------------------------
    async def test_pidgey_quick_attack_heads_and_tails(self):
        for heads, expected in ((True, 20), (False, 10)):
            with self.subTest(heads=heads):
                t = self.table()
                p = t.put(PIDGEY, P1, 'active')
                t.energy(p, W)
                t.heads = heads
                await t.attack(p, 'Quick Attack')
                self.assertEqual(self.lost(self.opp), expected)

    # --- Porygon (UNB 155): Quick Draw ---------------------------------------
    async def test_porygon_quick_draw_draws_one(self):
        t = self.table()
        p = t.put(PORYGON, P1, 'active')
        t.energy(p, W)
        deck = len(t.zone(P1, 'deck'))
        await t.attack(p, 'Quick Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P1, 'deck')), deck - 1)
        self.assertEqual(self.lost(self.opp), 0)

    # --- Porygon2 (UNB 156): Double Draw -------------------------------------
    async def test_porygon2_double_draw_draws_two(self):
        t = self.table()
        p = t.put(PORYGON2, P1, 'active')
        t.energy(p, W)
        await t.attack(p, 'Double Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(self.lost(self.opp), 0)

    async def test_porygon2_evolves_from_porygon(self):
        t = self.table()
        p = t.put(PORYGON, P1, 'bench')
        p2 = t.put(PORYGON2, P1, 'hand')
        await t.play(p2, targets=[p.entity_id])
        self.assertIn(p2, t.zone(P1, 'bench'))

    # --- Porygon-Z (UNB 157): Crazy Code / Tantrum ---------------------------
    async def test_crazy_code_attaches_special_energy_repeatedly(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        z = t.put(PORYGONZ, P1, 'bench')
        target = t.put(self.filler, P1, 'bench')
        e1 = t.put(WGUARD, P1, 'hand')
        e2 = t.put(WGUARD, P1, 'hand')
        t.pokemon = lambda c, p: target if target in c else c[0]
        await t.use(z, 'Crazy Code')          # one activation loops over the hand
        self.assertIn(e1, target.children)
        self.assertIn(e2, target.children)
        # "As often as you like": usable again once another Special Energy is in hand.
        e3 = t.put(WGUARD, P1, 'hand')
        self.assertIsNotNone(t.ability_offer(z, 'Crazy Code'))
        await t.use(z, 'Crazy Code')
        self.assertIn(e3, target.children)
        # It did not use the once-per-turn manual Energy attachment.
        basic = t.put(t.basic_energy(W), P1, 'hand')
        self.assertTrue(t.can(basic, 'DefaultEnergyPlayAbility'))

    async def test_crazy_code_not_for_basic_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        z = t.put(PORYGONZ, P1, 'bench')
        t.put(t.basic_energy(W), P1, 'hand')
        self.assertIsNone(t.ability_offer(z, 'Crazy Code'))

    async def test_tantrum_confuses_self(self):
        t = self.table()
        z = t.put(PORYGONZ, P1, 'active')
        t.energy(z, W, 3)
        await t.attack(z, 'Tantrum')
        self.assertEqual(self.lost(self.opp), 120)
        self.assertIn(CONFUSED, t.conditions(z))
        self.assertNotIn(CONFUSED, t.conditions(self.opp))

    # --- Slakoth (UNM 168): Boundless Power -----------------------------------
    async def test_boundless_power_locks_next_turn_only(self):
        t = self.table()
        s = t.put(SLAKOTH, P1, 'active')
        t.energy(s, W, 3)
        await t.attack(s, 'Boundless Power')
        self.assertEqual(self.lost(self.opp), 60)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(s, 'Boundless Power'))
        self.assertIsNone(t.attack_offer(s, 'Scratch'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(s, 'Boundless Power'))

    # --- Vigoroth (EVS 130): Shatter -----------------------------------------
    async def test_shatter_discards_any_stadium(self):
        for owner in (P1, P2):
            with self.subTest(owner=owner):
                t = self.table()
                v = t.put(VIGOROTH, P1, 'active')
                t.energy(v, W)
                stadium = t.stadium(ARTAZON, owner)
                await t.attack(v, 'Shatter')
                self.assertEqual(self.lost(self.opp), 20)
                self.assertEqual(list(t.board.find_global_area('activeStadium').children), [])
                self.assertIn(stadium, t.zone(owner, 'discard'))

    async def test_shatter_without_stadium_still_damages(self):
        t = self.table()
        v = t.put(VIGOROTH, P1, 'active')
        t.energy(v, W)
        self.assertIsNotNone(t.attack_offer(v, 'Shatter'))
        await t.attack(v, 'Shatter')
        self.assertEqual(self.lost(self.opp), 20)

    # --- Slaking (CES 115): Lazy / Critical Move ------------------------------
    def _lazy_board(self, slaking_zone, slaking_owner=P1):
        t = self.table()
        if slaking_zone == 'active' and slaking_owner == P1:
            t.put(SLAKING, P1, 'active')
        else:
            t.put(self.filler, P1, 'active')
            t.put(SLAKING, slaking_owner, 'bench' if slaking_owner == P1 else slaking_zone)
        t.next_turn()                     # P2 to act
        liepard = t.put(LIEPARD, P2, 'bench')
        t.put(self.filler, P2, 'hand')
        t.put(self.filler, P2, 'hand')
        return t, liepard

    async def test_lazy_active_turns_off_opponent_abilities(self):
        t, liepard = self._lazy_board('active')
        self.assertIsNone(t.ability_offer(liepard, 'Trade', pid=P2))

    async def test_lazy_on_bench_does_nothing(self):
        t, liepard = self._lazy_board('bench')
        self.assertIsNotNone(t.ability_offer(liepard, 'Trade', pid=P2))

    async def test_lazy_does_not_affect_own_side(self):
        t = self.table()
        t.put(SLAKING, P1, 'active')
        liepard = t.put(LIEPARD, P1, 'bench')
        t.put(self.filler, P1, 'hand')
        t.put(self.filler, P1, 'hand')
        self.assertIsNotNone(t.ability_offer(liepard, 'Trade'))

    async def test_lazy_does_not_stop_opponents_lazy(self):
        # Both Actives are Slaking: each Lazy is excepted, so each keeps working.
        t = Table(self)
        mine = t.put(SLAKING, P1, 'active')
        theirs = t.put(SLAKING, P2, 'active')
        my_liepard = t.put(LIEPARD, P1, 'bench')
        t.put(self.filler, P1, 'hand')
        t.put(self.filler, P1, 'hand')
        # The opponent's Lazy still shuts off my Liepard.
        self.assertIsNone(t.ability_offer(my_liepard, 'Trade'))

    async def test_critical_move_discards_energy_and_locks(self):
        t = self.table()
        s = t.put(SLAKING, P1, 'active')
        t.energy(s, W, 4)
        await t.attack(s, 'Critical Move')
        self.assertEqual(self.lost(self.opp), 160)
        self.assertEqual(len(t.board.attached_energies(s)), 3)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(s, 'Critical Move'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(s, 'Critical Move'))

    # --- Ditto (CRZ 107): Sudden Transformation ------------------------------
    @staticmethod
    async def sync(t, pid=P1):
        # The live game re-syncs the Active's attack list before every offer.
        await t.session._refresh_dynamic_attacks(pid)

    async def test_ditto_uses_basic_attacks_from_discard(self):
        t = self.table()
        d = t.put(DITTO, P1, 'active')
        t.energy(d, W, 2)
        t.put(SLAKOTH, P1, 'discard')
        await self.sync(t)
        self.assertIsNotNone(t.attack_offer(d, 'Scratch'))
        self.assertIsNone(t.attack_offer(d, 'Boundless Power'))   # needs 3 Energy
        await t.attack(d, 'Scratch')
        self.assertEqual(self.lost(self.opp), 30)

    async def test_ditto_ignores_evolved_and_opponent_discard(self):
        t = self.table()
        d = t.put(DITTO, P1, 'active')
        t.energy(d, W, 3)
        t.put(VIGOROTH, P1, 'discard')           # Stage 1: not usable
        t.put(SLAKOTH, P2, 'discard')            # opponent's discard: not usable
        await self.sync(t)
        self.assertIsNone(t.attack_offer(d, 'Shatter'))
        self.assertIsNone(t.attack_offer(d, 'Scratch'))

    async def test_ditto_on_bench_offers_nothing(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        d = t.put(DITTO, P1, 'bench')
        t.energy(d, W, 2)
        t.put(SLAKOTH, P1, 'discard')
        await self.sync(t)
        self.assertIsNone(t.attack_offer(d, 'Scratch'))

    # --- Kangaskhan (DAA 133): Rally Back -----------------------------------
    async def _ko_my_active_by_attack(self, t):
        victim = t.put(self.filler, P1, 'active', hp=30)
        victim.set_attribute(AttrID.WEAKNESS_TYPES, [])
        victim.set_attribute(AttrID.RESISTANCE_TYPES, [])
        k = t.put(KANGASKHAN, P1, 'bench')
        t.energy(k, W, 2)
        t.next_turn()
        timburr = t.active(P2)
        t.energy(timburr, F, 2)
        await t.attack(timburr, 'Pound', pid=P2)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        t.next_turn()
        return k

    async def test_rally_back_after_attack_ko(self):
        t = self.table(TIMBURR)
        k = await self._ko_my_active_by_attack(t)
        self.assertIs(t.active(P1), k)
        await t.attack(k, 'Rally Back')
        self.assertEqual(self.lost(self.opp), 120)

    async def test_rally_back_without_ko(self):
        t = self.table()
        k = t.put(KANGASKHAN, P1, 'active')
        t.energy(k, W, 2)
        await t.attack(k, 'Rally Back')
        self.assertEqual(self.lost(self.opp), 30)

    async def test_rally_back_not_two_turns_later(self):
        t = self.table(TIMBURR)
        k = await self._ko_my_active_by_attack(t)
        t.next_turn(); t.next_turn()      # opponent's last turn had no KO
        await t.attack(k, 'Rally Back')
        self.assertEqual(self.lost(self.opp), 30)

    # --- Lugia (CEL 22): Aero Ball / Deep Crush ----------------------------
    async def test_aero_ball_counts_both_actives_not_bench(self):
        t = self.table()
        l = t.put(LUGIA, P1, 'active')
        t.energy(l, W, 2)
        t.energy(self.opp, D, 3)
        bench = t.put(self.filler, P1, 'bench')
        t.energy(bench, W, 4)
        await t.attack(l, 'Aero Ball')
        self.assertEqual(self.lost(self.opp), 100)

    async def test_deep_crush_locks_next_turn(self):
        t = self.table()
        l = t.put(LUGIA, P1, 'active')
        t.energy(l, W, 4)
        await t.attack(l, 'Deep Crush')
        self.assertEqual(self.lost(self.opp), 160)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(l, 'Deep Crush'))
        self.assertIsNone(t.attack_offer(l, 'Aero Ball'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(l, 'Deep Crush'))

    # --- Snorlax (LOR 143): Unfazed Fat / Thumping Snore ---------------------
    async def test_unfazed_fat_blocks_effects_not_damage(self):
        t = self.table(ZUBAT)
        s = t.put(SNORLAX, P1, 'active')
        self.big(s)
        t.next_turn()
        zubat = t.active(P2)
        t.energy(zubat, D)
        await t.attack(zubat, 'Supersonic', pid=P2)
        self.assertNotIn(CONFUSED, t.conditions(s))

    async def test_unfazed_fat_only_for_itself(self):
        t = self.table(ZUBAT)
        victim = t.put(self.filler, P1, 'active')
        self.big(victim)
        t.put(SNORLAX, P1, 'bench')
        t.next_turn()
        zubat = t.active(P2)
        t.energy(zubat, D)
        await t.attack(zubat, 'Supersonic', pid=P2)
        self.assertIn(CONFUSED, t.conditions(victim))

    async def test_thumping_snore_sleeps_two_coin_checkup(self):
        t = self.table()
        s = t.put(SNORLAX, P1, 'active')
        t.energy(s, W, 3)
        await t.attack(s, 'Thumping Snore')
        self.assertEqual(self.lost(self.opp), 180)
        self.assertIn(ASLEEP, t.conditions(s))
        self.assertEqual(t.session.sleep_checkup_coins.get(s.entity_id), 2)
        # Checkup flips with random.choice([0, 1]); 0 = heads.
        flips = iter([0, 1])
        with patch('spirit.game.session.game_session.random.choice', lambda _: next(flips)):
            await t.checkup()
        self.assertIn(ASLEEP, t.conditions(s))      # one tails: still Asleep
        flips = iter([0, 0])
        with patch('spirit.game.session.game_session.random.choice', lambda _: next(flips)):
            await t.checkup()
        self.assertNotIn(ASLEEP, t.conditions(s))   # both heads: wakes up


if __name__ == '__main__':
    unittest.main()
