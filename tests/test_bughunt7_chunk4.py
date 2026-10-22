"""Bug hunt round 7, chunk 4: each card checked against its printed text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, D, G = PokemonTypes.WATER, PokemonTypes.DARKNESS, PokemonTypes.GRASS
P, F, M = PokemonTypes.PSYCHIC, PokemonTypes.FIGHTING, PokemonTypes.METAL

ROSERADE, ROSELIA = 'SV05.Roserade_9', 'SV05.Roselia_8'
MEDICAL = 'SV4.MedicalEnergy_182'
CRISIS = 'SV045.TechnicalMachineCrisisPunch_90'
JUDGE = 'ME3.Judge_76'
FINIZEN, PALAFIN = 'SV3.Finizen_60', 'SV3.Palafin_62'
FEEBAS_SSP, FEEBAS_SIT, MILOTIC = 'SV08.Feebas_41', 'SWSH12.Feebas_39', 'XY2.Milotic_23'
SABLEYE_GRI, SABLEYE_CES = 'SM2.Sableye_80', 'SM7.Sableye_88'
TAILLOW = 'SWSH4.Taillow_133'
GOLBAT_CRI = 'ME4.Golbat_50'
JIRACHI = 'SWSH4.Jirachi_119'
GOLBAT_BST, CROBAT = 'SWSH5.Golbat_90', 'SWSH5.Crobat_91'
DODUO = 'SV035.Doduo_84'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk4(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    @staticmethod
    def neutral(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)

    def filler_attack(self):
        return self.filler.abilities[0].title

    # --- Roserade (TEF 9) ----------------------------------------------------
    async def test_roserade_poison_point_active_poisons_attacker(self):
        t = self.table()
        rose = t.put(ROSERADE, P1, 'active')
        self.neutral(rose)
        t.energy(self.opp, W, 4)
        t.next_turn()
        await t.attack(self.opp, self.filler_attack(), pid=P2)
        self.assertGreater(400 - t.hp(rose), 0)
        self.assertIn(POISONED, t.conditions(self.opp))

    async def test_roserade_poison_point_not_on_own_attack(self):
        # Damage it takes from its own side / nothing: attacking does not poison
        t = self.table()
        rose = t.put(ROSERADE, P1, 'active')
        t.energy(rose, G, 2)
        await t.attack(rose, 'Bind Down')
        self.assertNotIn(POISONED, t.conditions(self.opp))
        self.assertNotIn(POISONED, t.conditions(rose))

    async def test_roserade_bind_down_blocks_retreat_next_turn_only(self):
        t = self.table()
        rose = t.put(ROSERADE, P1, 'active')
        t.energy(rose, G, 2)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W, 4)
        await t.attack(rose, 'Bind Down')
        self.assertEqual(400 - t.hp(self.opp), 70)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))

    # --- Medical Energy (PAR 182) --------------------------------------------
    async def test_medical_energy_heals_30_on_attach_from_hand(self):
        t = self.table()
        mon = t.put(self.filler, P1, 'active')
        mon.set_attribute(AttrID.HP, t.hp(mon) - 50)
        card = t.put(MEDICAL, P1, 'hand')
        await t.play(card, targets=[mon.entity_id])
        self.assertIn(card, mon.children)
        self.assertEqual(t.damage(mon), 20)

    async def test_medical_energy_raw_attach_does_not_heal_and_provides_colorless(self):
        # Not attached from hand (e.g. moved by an effect): no heal
        t = self.table()
        mon = t.put(DODUO, P1, 'active')
        mon.set_attribute(AttrID.HP, t.hp(mon) - 30)
        t.attach(MEDICAL, mon)
        self.assertEqual(t.damage(mon), 30)
        # It pays Doduo's [C] attack
        self.assertIsNotNone(t.attack_offer(mon, 'Reckless Charge'))

    # --- Technical Machine: Crisis Punch (PAF 90) ----------------------------
    async def _crisis(self, opp_prizes):
        t = self.table()
        mon = t.put(self.filler, P1, 'active')
        t.energy(mon, W, 3)
        await t.play(t.put(CRISIS, P1, 'hand'), targets=[mon.entity_id])
        t.set_prizes(P2, opp_prizes)
        return t, mon

    async def test_crisis_punch_usable_with_opponent_at_1_prize(self):
        t, mon = await self._crisis(1)
        self.assertIsNotNone(t.attack_offer(mon, 'Crisis Punch'))
        await t.attack(mon, 'Crisis Punch')
        self.assertEqual(400 - t.hp(self.opp), 280)

    # BUG: TM granted attack's "only when opponent has exactly 1 Prize" is not installed as a usage condition; it is offered at 2 Prizes and does nothing

    async def test_crisis_punch_not_offered_with_opponent_at_2_prizes(self):
        t, mon = await self._crisis(2)
        self.assertIsNone(t.attack_offer(mon, 'Crisis Punch'))

    async def test_crisis_punch_discarded_end_of_turn(self):
        t, mon = await self._crisis(2)
        tm = next(c for c in mon.children if name(c) == 'Technical Machine: Crisis Punch')
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        self.assertIn(tm, t.zone(P1, 'discard'))

    # --- Judge (POR 76) ------------------------------------------------------
    async def test_judge_both_players_shuffle_and_draw_4(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        for _ in range(7):
            t.put(self.item, P2, 'hand')
        mine = [t.put(self.item, P1, 'hand') for _ in range(2)]
        judge = t.put(JUDGE, P1, 'hand')
        await t.play(judge)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)
        self.assertIn(judge, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'deck')), 30 + 2 - 4)

    async def test_judge_not_playable_second_supporter(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        await t.play(t.put(JUDGE, P1, 'hand'))
        self.assertFalse(t.can(t.put(JUDGE, P1, 'hand'), 'UseTrainerCard'))

    # --- Finizen (OBF 60) ----------------------------------------------------
    async def test_finizen_valiant_evolution_switches_then_evolves(self):
        t = self.table()
        fin = t.put(FINIZEN, P1, 'active')
        t.energy(fin, W)
        other = t.put(self.filler, P1, 'bench')
        t.deck(P1, [PALAFIN])
        await t.attack(fin, 'Valiant Evolution')
        self.assertIs(t.active(P1), other)
        bench = t.zone(P1, 'bench')
        self.assertEqual([name(c) for c in bench], ['Palafin'])
        self.assertIn(fin, list(bench[0].children))

    # BUG: with no Benched Pokemon the switch fails but Finizen still evolves (ignores "If you do")

    async def test_finizen_valiant_evolution_no_bench_no_evolve(self):
        t = self.table()
        fin = t.put(FINIZEN, P1, 'active')
        t.energy(fin, W)
        t.deck(P1, [PALAFIN])
        await t.attack(fin, 'Valiant Evolution')
        self.assertIs(t.active(P1), fin)
        self.assertEqual(name(t.active(P1)), 'Finizen')
        self.assertIn('Palafin', t.names(t.zone(P1, 'deck')))

    # --- Feebas (SSP 41) -----------------------------------------------------
    async def test_feebas_leap_out_switches(self):
        t = self.table()
        feebas = t.put(FEEBAS_SSP, P1, 'active')
        t.energy(feebas, W)
        other = t.put(self.filler, P1, 'bench')
        await t.attack(feebas, 'Leap Out')
        self.assertIs(t.active(P1), other)
        self.assertIn(feebas, t.zone(P1, 'bench'))
        self.assertEqual(t.hp(self.opp), 400)

    async def test_feebas_leap_out_without_bench_stays(self):
        t = self.table()
        feebas = t.put(FEEBAS_SSP, P1, 'active')
        t.energy(feebas, W)
        await t.attack(feebas, 'Leap Out')
        self.assertIs(t.active(P1), feebas)

    # --- Feebas (SIT 39) -----------------------------------------------------
    async def test_feebas_ascension_evolves_into_milotic(self):
        t = self.table()
        feebas = t.put(FEEBAS_SIT, P1, 'active')
        t.energy(feebas, W)
        t.deck(P1, [MILOTIC, ROSERADE])
        await t.attack(feebas, 'Ascension')
        self.assertEqual(name(t.active(P1)), 'Milotic')
        self.assertIn('Roserade', t.names(t.zone(P1, 'deck')))

    async def test_feebas_ascension_ignores_non_evolutions(self):
        t = self.table()
        feebas = t.put(FEEBAS_SIT, P1, 'active')
        t.energy(feebas, W)
        t.deck(P1, [ROSERADE, PALAFIN])
        await t.attack(feebas, 'Ascension')
        self.assertIs(t.active(P1), feebas)
        self.assertIn('Palafin', t.names(t.zone(P1, 'deck')))

    # --- Sableye (GRI 80) ----------------------------------------------------
    async def test_sableye_limitation_blocks_opponent_supporters_next_turn(self):
        t = self.table()
        sab = t.put(SABLEYE_GRI, P1, 'active')
        t.energy(sab, D)
        judge = t.put(JUDGE, P2, 'hand')
        item = t.put(self.item, P2, 'hand')
        await t.attack(sab, 'Limitation')
        t.next_turn()
        self.assertFalse(t.can(judge, 'UseTrainerCard', P2))
        self.assertTrue(t.can(item, 'UseTrainerCard', P2))
        t.next_turn()
        # its own controller is not limited
        mine = t.put(JUDGE, P1, 'hand')
        self.assertTrue(t.can(mine, 'UseTrainerCard', P1))
        t.next_turn()
        self.assertTrue(t.can(judge, 'UseTrainerCard', P2))

    # --- Sableye (CES 88) ----------------------------------------------------
    async def test_sableye_excavate_discard_or_keep(self):
        for discard in (True, False):
            t = self.table()
            sab = t.put(SABLEYE_CES, P1, 'active')
            top = t.deck(P1, [DODUO])[0]
            t.yes = discard
            await t.use(sab, 'Excavate')
            with self.subTest(discard=discard):
                if discard:
                    self.assertIn(top, t.zone(P1, 'discard'))
                else:
                    self.assertIs(t.zone(P1, 'deck')[-1], top)
                    self.assertNotIn(top, t.zone(P1, 'discard'))
                # once per turn
                self.assertIsNone(t.ability_offer(sab, 'Excavate'))

    async def test_sableye_disable_blocks_chosen_attack_next_turn(self):
        t = self.table()
        sab = t.put(SABLEYE_CES, P1, 'active')
        t.energy(sab, D)
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        target = t.put(SABLEYE_GRI, P2, 'active')
        self.neutral(target)
        t.energy(target, D, 2)
        t.picks = lambda cards, count, prompt, display: [
            c for c in cards if 'Limitation' in str(getattr(c, 'title', c))][:count] or cards[:count]
        await t.attack(sab, 'Disable')
        self.assertEqual(400 - t.hp(target), 10)
        t.next_turn()
        self.assertIsNone(t.attack_offer(target, 'Limitation', P2))
        self.assertIsNotNone(t.attack_offer(target, 'Scratch', P2))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(target, 'Limitation', P2))

    # --- Milotic (FLF 23) ----------------------------------------------------
    async def test_milotic_energy_grace_kos_self_and_attaches_3(self):
        t = self.table()
        active = t.put(self.filler, P1, 'active')
        milotic = t.put(MILOTIC, P1, 'bench')
        energies = [t.put(t.basic_energy(W), P1, 'discard') for _ in range(4)]
        special = t.put(MEDICAL, P1, 'discard')
        await t.use(milotic, 'Energy Grace')
        self.assertNotIn(milotic, t.board.pokemon_in_play(P1))
        attached = [c for c in active.children if c in energies]
        self.assertEqual(len(attached), 3)
        self.assertNotIn(special, active.children)
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)   # opponent took a Prize

    async def test_milotic_energy_grace_without_energy_does_not_ko(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        milotic = t.put(MILOTIC, P1, 'bench')
        t.put(MEDICAL, P1, 'discard')    # Special Energy only
        entry = t.ability_offer(milotic, 'Energy Grace')
        if entry is not None:
            await t.do(entry)
        self.assertIn(milotic, t.board.pokemon_in_play(P1))
        self.assertEqual(len(t.zone(P2, 'prizes')), 6)

    # --- Taillow (VIV 133) ---------------------------------------------------
    async def test_taillow_double_peck(self):
        for heads, dmg in ((True, 40), (False, 0)):
            t = self.table()
            bird = t.put(TAILLOW, P1, 'active')
            t.energy(bird, W, 2)
            t.heads = heads
            await t.attack(bird, 'Double Peck')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Golbat (CRI 50) -----------------------------------------------------
    async def test_golbat_covert_flight_prevents_basic_attackers_only(self):
        for attacker_spec, prevented in ((None, True), (ROSERADE, False)):
            t = self.table()
            bat = t.put(GOLBAT_CRI, P1, 'active')
            self.neutral(bat)
            t.energy(bat, D)
            attacker = self.opp
            if attacker_spec is not None:
                t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
                attacker = t.put(attacker_spec, P2, 'active')
                self.neutral(attacker)
            t.energy(attacker, W, 4)
            await t.attack(bat, 'Covert Flight')
            self.assertEqual(400 - t.hp(attacker), 30)
            t.next_turn()
            title = self.filler_attack() if attacker_spec is None else 'Bind Down'
            await t.attack(attacker, title, pid=P2)
            with self.subTest(attacker=attacker_spec):
                if prevented:
                    self.assertEqual(t.hp(bat), 400)
                else:
                    self.assertEqual(400 - t.hp(bat), 70)

    # --- Jirachi (VIV 119) ---------------------------------------------------
    async def test_jirachi_dreamy_revelation_active_only(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        bench = t.put(JIRACHI, P1, 'bench')
        self.assertIsNone(t.ability_offer(bench, 'Dreamy Revelation'))

    async def test_jirachi_dreamy_revelation_takes_1_returns_1(self):
        t = self.table()
        jira = t.put(JIRACHI, P1, 'active')
        a, b = t.deck(P1, [DODUO, TAILLOW])          # b is top
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is a][:1] or cards[:1]
        await t.use(jira, 'Dreamy Revelation')
        hand = t.zone(P1, 'hand')
        self.assertIn(a, hand)
        self.assertIs(t.zone(P1, 'deck')[-1], b)
        self.assertEqual(len(t.zone(P1, 'deck')), 31)
        self.assertIsNone(t.ability_offer(jira, 'Dreamy Revelation'))

    async def test_jirachi_amazing_star_basic_energy_only(self):
        t = self.table()
        jira = t.put(JIRACHI, P1, 'active')
        self.neutral(jira, hp=None)
        t.energy(jira, P); t.energy(jira, F); t.energy(jira, M)
        other = t.put(self.filler, P1, 'bench')
        basics = t.deck(P1, [t.basic_energy(W), t.basic_energy(G)])
        special = t.deck(P1, [MEDICAL])[0]
        await t.attack(jira, 'Amazing Star')
        attached = [c for p in (jira, other) for c in p.children]
        for e in basics:
            self.assertIn(e, attached)
        self.assertNotIn(special, attached)
        self.assertIn(special, t.zone(P1, 'deck'))

    # --- Crobat (BST 91) -----------------------------------------------------
    async def test_crobat_drastic_draw_on_evolve(self):
        for yes, drawn in ((True, 3), (False, 0)):
            t = self.table()
            bat = t.put(GOLBAT_BST, P1, 'active')
            crobat = t.put(CROBAT, P1, 'hand')
            t.yes = yes
            before = len(t.zone(P1, 'hand'))
            await t.play(crobat, targets=[bat.entity_id])
            with self.subTest(yes=yes):
                self.assertEqual(name(t.active(P1)), 'Crobat')
                self.assertEqual(len(t.zone(P1, 'hand')), before - 1 + drawn)

    async def test_crobat_put_in_play_without_evolving_from_hand_no_draw(self):
        # Already-evolved Crobat does not get to draw again on later turns
        t = self.table()
        bat = t.put(GOLBAT_BST, P1, 'active')
        crobat = t.put(CROBAT, P1, 'hand')
        await t.play(crobat, targets=[bat.entity_id])
        evolved = t.active(P1)
        self.assertIsNone(t.ability_offer(evolved, 'Drastic Draw'))

    # --- Doduo (MEW 84) ------------------------------------------------------
    async def test_doduo_reckless_charge_self_damage(self):
        t = self.table()
        doduo = t.put(DODUO, P1, 'active')
        self.neutral(doduo, hp=None)
        t.energy(doduo, W)
        await t.attack(doduo, 'Reckless Charge')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertEqual(t.damage(doduo), 10)


if __name__ == '__main__':
    unittest.main()
