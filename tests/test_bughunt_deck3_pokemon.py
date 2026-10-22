"""Bug hunt, deck 3 (Fighting): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

F, D = PokemonTypes.FIGHTING, PokemonTypes.DARKNESS
URSALUNA, HAWLUCHA = 'SV085.BloodmoonUrsaluna_54', 'SV1.Hawlucha_118'
LUNATONE, SOLROCK = 'ME1.Lunatone_74', 'ME1.Solrock_75'
MAKUHITA, HARIYAMA = 'ME1.Makuhita_72', 'ME1.Hariyama_73'
MARSHADOW, OKIDOGI = 'ME1.Marshadow_80', 'SV085.Okidogi_57'
RIOLU, LUCARIO, TINGLU = 'SM5.Riolu_66', 'SV1.Lucario_114', 'SV06.TingLu_110'
NEST = 'SV1.NestBall_181'
ARTAZON = 'SV2.Artazon_171'


class Deck3Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    def neutral(self, p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def replace_opp_active(self, t, spec):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = t.put(spec, P2, 'active')
        return self.opp

    # --- Bloodmoon Ursaluna -------------------------------------------------
    async def test_battle_hardened_attaches_up_to_two_basic_fighting(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        for _ in range(3):
            t.put(t.basic_energy(F), P1, 'hand')
        t.put(t.basic_energy(D), P1, 'hand')
        urs = t.put(URSALUNA, P1, 'hand')
        await t.play(urs)
        self.assertIn(urs, t.zone(P1, 'bench'))
        energies = t.board.attached_energies(urs)
        self.assertEqual(len(energies), 2)
        for e in energies:
            self.assertIn(F.value, e.get_attribute(AttrID.POKEMON_TYPES))
        # The normal once-per-turn energy attachment is still available
        self.assertFalse(t.state.energy_attached)

    async def test_battle_hardened_not_from_deck(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(t.basic_energy(F), P1, 'hand')
        t.deck(P1, [URSALUNA])
        await t.play(t.put(NEST, P1, 'hand'))
        urs = next(c for c in t.zone(P1, 'bench') if self.name(c) == 'Bloodmoon Ursaluna')
        self.assertEqual(len(t.board.attached_energies(urs)), 0)

    async def test_mad_bite_30_per_counter(self):
        for counters in (0, 1):
            t = self.table()
            urs = t.put(URSALUNA, P1, 'active')
            t.energy(urs, F, 3)
            target = self.replace_opp_active(t, HARIYAMA)     # 150 HP
            self.neutral(target, hp=None)
            target.set_attribute(AttrID.HP, effective_max_hp(t.board, target) - 10 * counters)
            before = t.hp(target)
            await t.attack(urs, 'Mad Bite')
            with self.subTest(counters=counters):
                self.assertEqual(before - t.hp(target), 100 + 30 * counters)

    # --- Hawlucha -----------------------------------------------------------
    async def test_flying_entry_two_counters_on_opponents_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        a = self.neutral(t.put(self.filler, P2, 'bench'), hp=None)
        b = self.neutral(t.put(self.filler, P2, 'bench'), hp=None)
        c = self.neutral(t.put(self.filler, P2, 'bench'), hp=None)
        mine = t.put(self.filler, P1, 'bench')
        await t.play(t.put(HAWLUCHA, P1, 'hand'))
        damages = sorted([t.damage(a), t.damage(b), t.damage(c)])
        self.assertEqual(damages, [0, 10, 10])
        self.assertEqual(t.damage(mine), 0)

    async def test_flying_entry_declined_or_from_deck(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        a = t.put(self.filler, P2, 'bench')
        b = t.put(self.filler, P2, 'bench')
        t.yes = False
        await t.play(t.put(HAWLUCHA, P1, 'hand'))
        with self.subTest('declined'):
            self.assertEqual((t.damage(a), t.damage(b)), (0, 0))
        t = self.table()
        t.put(self.filler, P1, 'active')
        a = t.put(self.filler, P2, 'bench')
        b = t.put(self.filler, P2, 'bench')
        t.deck(P1, [HAWLUCHA])
        await t.play(t.put(NEST, P1, 'hand'))
        with self.subTest('nest ball'):
            self.assertEqual(len(t.zone(P1, 'bench')), 1)
            self.assertEqual((t.damage(a), t.damage(b)), (0, 0))

    # --- Lunatone / Solrock ---------------------------------------------------
    async def test_lunar_cycle_needs_solrock_and_basic_fighting(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        luna = t.put(LUNATONE, P1, 'bench')
        t.put(t.basic_energy(F), P1, 'hand')
        with self.subTest('no Solrock'):
            self.assertIsNone(t.ability_offer(luna, 'Lunar Cycle'))
        t.put(SOLROCK, P1, 'bench')
        self.assertIsNotNone(t.ability_offer(luna, 'Lunar Cycle'))
        await t.use(luna, 'Lunar Cycle')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_lunar_cycle_not_with_only_other_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        luna = t.put(LUNATONE, P1, 'bench')
        t.put(SOLROCK, P1, 'bench')
        t.put(t.basic_energy(D), P1, 'hand')
        t.put('XY10.StrongEnergy_115', P1, 'hand')
        self.assertIsNone(t.ability_offer(luna, 'Lunar Cycle'))

    async def test_lunar_cycle_only_one_per_turn_across_lunatones(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        l1 = t.put(LUNATONE, P1, 'bench')
        l2 = t.put(LUNATONE, P1, 'bench')
        t.put(SOLROCK, P1, 'bench')
        t.put(t.basic_energy(F), P1, 'hand')
        t.put(t.basic_energy(F), P1, 'hand')
        await t.use(l1, 'Lunar Cycle')
        self.assertIsNone(t.ability_offer(l2, 'Lunar Cycle'))

    async def test_cosmic_beam_needs_benched_lunatone_ignores_weakness(self):
        t = self.table()
        sol = t.put(SOLROCK, P1, 'active')
        t.energy(sol, F)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        await t.attack(sol, 'Cosmic Beam')
        with self.subTest('no Lunatone'):
            self.assertEqual(t.hp(self.opp), 400)
        t = self.table()
        sol = t.put(SOLROCK, P1, 'active')
        t.energy(sol, F)
        t.put(LUNATONE, P1, 'bench')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        await t.attack(sol, 'Cosmic Beam')
        with self.subTest('Lunatone, Weakness ignored'):
            self.assertEqual(400 - t.hp(self.opp), 70)

    # --- Hariyama -----------------------------------------------------------
    async def test_heave_ho_catcher_on_evolve_from_hand(self):
        t = self.table()
        mak = t.put(MAKUHITA, P1, 'active')
        target = t.put(self.filler, P2, 'bench')
        hari = t.put(HARIYAMA, P1, 'hand')
        await t.play(hari, targets=[mak.entity_id])
        self.assertIs(t.active(P2), target)

    async def test_heave_ho_catcher_declined(self):
        t = self.table()
        mak = t.put(MAKUHITA, P1, 'active')
        t.put(self.filler, P2, 'bench')
        t.yes = False
        await t.play(t.put(HARIYAMA, P1, 'hand'), targets=[mak.entity_id])
        self.assertIs(t.active(P2), self.opp)

    async def test_wild_press_recoil(self):
        t = self.table()
        hari = t.put(HARIYAMA, P1, 'active')
        t.energy(hari, F, 3)
        await t.attack(hari, 'Wild Press')
        self.assertEqual(400 - t.hp(self.opp), 210)
        self.assertEqual(t.damage(hari), 70)

    # --- Marshadow ------------------------------------------------------------
    async def _side_kick(self, ko):
        t = self.table()
        marsh = t.put(MARSHADOW, P1, 'active', hp=300)
        marsh.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.put(self.filler, P1, 'bench')
        t.energy(marsh, F, 2)
        self.opp.set_attribute(AttrID.HP, 60 if ko else 400)
        nxt = self.neutral(t.put(TINGLU, P2, 'bench'))
        t.energy(nxt, F, 3)
        await t.attack(marsh, 'Shadowy Side Kick')
        if ko:
            self.assertNotIn(self.opp, t.board.pokemon_in_play(P2))
            self.assertIs(t.active(P2), nxt)
            attacker = nxt
        else:
            self.assertEqual(400 - t.hp(self.opp), 60)
            # Make the next attack come from a Ting-Lu Active as well
            t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
            t.board.find_player_area(P2, 'bench').remove_child(nxt)
            t.board.add_card_to_area(nxt, t.board.find_player_area(P2, 'activePokemonArea'))
            attacker = nxt
        t.next_turn()
        before = t.hp(marsh)
        await t.attack(attacker, 'Hammer In', pid=P2)
        return before - t.hp(marsh)

    async def test_shadowy_side_kick_protects_after_ko(self):
        self.assertEqual(await self._side_kick(ko=True), 0)

    async def test_shadowy_side_kick_no_protection_without_ko(self):
        self.assertGreater(await self._side_kick(ko=False), 0)

    # --- Okidogi --------------------------------------------------------------
    async def test_adrena_power_with_darkness(self):
        t = self.table()
        oki = t.put(OKIDOGI, P1, 'active')
        base = effective_max_hp(t.board, oki)
        t.energy(oki, F, 2)
        await t.play(t.put(t.basic_energy(D), P1, 'hand'), targets=[oki.entity_id])
        self.assertEqual(effective_max_hp(t.board, oki), base + 100)
        self.assertEqual(t.hp(oki), base + 100)
        bench = t.put(self.filler, P2, 'bench')
        await t.attack(oki, 'Good Punch')
        self.assertEqual(400 - t.hp(self.opp), 170)

    async def test_adrena_power_without_darkness(self):
        t = self.table()
        oki = t.put(OKIDOGI, P1, 'active')
        base = effective_max_hp(t.board, oki)
        t.energy(oki, F, 2)
        self.assertEqual(effective_max_hp(t.board, oki), base)
        await t.attack(oki, 'Good Punch')
        self.assertEqual(400 - t.hp(self.opp), 70)

    # --- Riolu ------------------------------------------------------------------
    async def _detect(self, heads):
        t = self.table()
        riolu = t.put(RIOLU, P1, 'active')
        riolu.set_attribute(AttrID.WEAKNESS_TYPES, [])
        riolu.set_attribute(AttrID.HP, 300)
        t.energy(riolu, F)
        attacker = self.replace_opp_active(t, TINGLU)
        self.neutral(attacker)
        t.energy(attacker, F, 3)
        t.heads = heads
        await t.attack(riolu, 'Detect')
        t.next_turn()
        before = t.hp(riolu)
        await t.attack(attacker, 'Hammer In', pid=P2)
        return before - t.hp(riolu)

    async def test_detect_heads_prevents(self):
        self.assertEqual(await self._detect(True), 0)

    async def test_detect_tails_no_protection(self):
        self.assertEqual(await self._detect(False), 110)

    # --- Lucario ----------------------------------------------------------------
    async def _avenging(self, victim_spec):
        """P2 Knocks Out P1's Active (victim_spec) with an attack; P1 then
        uses Avenging Knuckle with a benched-then-promoted Lucario."""
        t = self.table()
        victim = t.put(victim_spec, P1, 'active', hp=10)
        victim.set_attribute(AttrID.RESISTANCE_TYPES, [])
        luc = t.put(LUCARIO, P1, 'bench')
        t.energy(luc, F)
        attacker = self.replace_opp_active(t, TINGLU)
        self.neutral(attacker)
        t.energy(attacker, F, 3)
        t.next_turn()
        await t.attack(attacker, 'Hammer In', pid=P2)
        self.assertNotIn(victim, t.board.pokemon_in_play(P1))
        self.assertIs(t.active(P1), luc)
        t.next_turn()
        before = t.hp(attacker)
        await t.attack(luc, 'Avenging Knuckle')
        return before - t.hp(attacker)

    async def test_avenging_knuckle_after_fighting_ko(self):
        self.assertEqual(await self._avenging(MAKUHITA), 150)

    async def test_avenging_knuckle_non_fighting_ko(self):
        self.assertEqual(await self._avenging(self.filler), 30)

    async def test_accelerating_stab_locks_next_turn(self):
        t = self.table()
        luc = t.put(LUCARIO, P1, 'active')
        t.energy(luc, F, 3)
        await t.attack(luc, 'Accelerating Stab')
        self.assertEqual(400 - t.hp(self.opp), 120)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(luc, 'Accelerating Stab'))
        self.assertIsNotNone(t.attack_offer(luc, 'Avenging Knuckle'))

    # --- Ting-Lu ------------------------------------------------------------------
    async def test_ground_crasher_with_stadium(self):
        for owner in (P1, P2):
            t = self.table()
            ting = t.put(TINGLU, P1, 'active')
            t.energy(ting, F)
            bench = t.put(self.filler, P2, 'bench')
            mine = t.put(self.filler, P1, 'bench')
            stadium = t.stadium(ARTAZON, owner)
            await t.attack(ting, 'Ground Crasher')
            with self.subTest(owner=owner):
                self.assertEqual(400 - t.hp(self.opp), 30)
                self.assertEqual(t.damage(bench), 30)
                self.assertEqual(t.damage(mine), 0)
                self.assertFalse(t.board.find_global_area('activeStadium').children)
                self.assertIn(stadium, t.zone(owner, 'discard'))

    async def test_ground_crasher_without_stadium(self):
        t = self.table()
        ting = t.put(TINGLU, P1, 'active')
        t.energy(ting, F)
        bench = t.put(self.filler, P2, 'bench')
        await t.attack(ting, 'Ground Crasher')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertEqual(t.damage(bench), 0)


if __name__ == "__main__":
    unittest.main()
