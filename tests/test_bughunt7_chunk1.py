"""Bug hunt round 7, chunk 1: Oranguru SSH 148 / SSP 156, Remoraid BKT 32,
Octillery PAR 34, Trumbeak LOT 165 / VIV 144, Snom SHF 29, Hawlucha POR 46,
Greedent SVI 152, Marshadow PBL 40, Lucario BRS 79 / 30C 83, Riolu MEG 76 /
PRE 50, Purrloin UNM 135."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, F, D, P, G = (PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.DARKNESS,
                 PokemonTypes.PSYCHIC, PokemonTypes.GRASS)
ORANGURU_SSH, ORANGURU_SSP = 'SWSH1.Oranguru_148', 'SV08.Oranguru_156'
REMORAID, OCTILLERY = 'XY8.Remoraid_32', 'SV4.Octillery_34'   # PAR = SV4 (not SV09)
PIKIPEK = 'SM8.Pikipek_163'
TRUMBEAK_LOT, TRUMBEAK_VIV = 'SM8.Trumbeak_165', 'SWSH4.Trumbeak_144'
SNOM, HAWLUCHA, GREEDENT = 'SWSH45.Snom_29', 'ME3.Hawlucha_46', 'SV1.Greedent_152'
SKWOVET = 'SV1.Skwovet_151'
MARSHADOW = 'ME5.Marshadow_40'
LUCARIO_BRS, LUCARIO_30C = 'SWSH9.Lucario_79', 'ME55.Lucario_83'
RIOLU_MEG, RIOLU_PRE = 'ME1.Riolu_76', 'SV085.Riolu_50'
PURRLOIN = 'SM11.Purrloin_135'
ARTAZON, FLOAT_STONE, HAU = 'SV2.Artazon_171', 'XY8.FloatStone_137', 'SM1.Hau_120'
SABLEYE = 'SV2.Sableye_136'                 # Unseen Claw 20 for [D]


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk1Round7(unittest.IsolatedAsyncioTestCase):
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

    # --- Oranguru SSH: Primate Wisdom --------------------------------------
    async def test_primate_wisdom_swaps_hand_card_with_top(self):
        t = self.table()
        ora = t.put(ORANGURU_SSH, P1, 'active')
        mine = t.put(HAU, P1, 'hand')
        top = t.deck(P1, [ARTAZON])[0]          # last child = top of deck
        await t.use(ora, 'Primate Wisdom')
        self.assertIn(top, t.zone(P1, 'hand'))
        self.assertNotIn(mine, t.zone(P1, 'hand'))
        self.assertIs(t.zone(P1, 'deck')[-1], mine)

    async def test_primate_wisdom_once_per_turn(self):
        t = self.table()
        ora = t.put(ORANGURU_SSH, P1, 'active')
        t.put(HAU, P1, 'hand')
        await t.use(ora, 'Primate Wisdom')
        self.assertIsNone(t.ability_offer(ora, 'Primate Wisdom'))

    # --- Oranguru SSP: Now You're in My Power -------------------------------
    async def _power_board(self):
        t = Table(self)
        ora = t.put(ORANGURU_SSP, P1, 'active')
        t.energy(ora, W, 3)
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        opp.set_attribute(AttrID.HP, 400)
        opp._start_hp = 400
        await t.attack(ora, "Now You're in My Power")
        return t, ora, opp

    async def test_now_youre_in_my_power_colorless_weakness_next_turn(self):
        t, ora, opp = await self._power_board()
        t.next_turn(); t.next_turn()
        await t.attack(ora, 'Smack')
        self.assertEqual(self.took(t, opp), 160)

    async def test_now_youre_in_my_power_expires(self):
        t, ora, opp = await self._power_board()
        for _ in range(4):
            t.next_turn()
        await t.attack(ora, 'Smack')
        self.assertEqual(self.took(t, opp), 80)

    # --- Remoraid BKT: Ion Pool ---------------------------------------------
    async def test_ion_pool_discards_any_stadium(self):
        for owner in (P1, P2):
            t = self.table()
            rem = t.put(REMORAID, P1, 'active')
            t.energy(rem, W)
            st = t.stadium(ARTAZON, owner)
            await t.attack(rem, 'Ion Pool')
            with self.subTest(owner=owner):
                self.assertIn(st, t.zone(owner, 'discard'))
                self.assertFalse(t.board.find_global_area('activeStadium').children)
                self.assertEqual(self.took(t, self.opp), 0)

    async def test_ion_pool_without_stadium_is_harmless(self):
        t = self.table()
        rem = t.put(REMORAID, P1, 'active')
        t.energy(rem, W)
        await t.attack(rem, 'Ion Pool')
        self.assertEqual(self.took(t, self.opp), 0)
        self.assertEqual(t.zone(P1, 'discard'), [])

    # --- Octillery PAR: Suction Cup Draw / Smokescreen Shot ----------------
    async def test_suction_cup_draw_on_evolve(self):
        t = self.table()
        rem = t.put(REMORAID, P1, 'active')
        octi = t.put(OCTILLERY, P1, 'hand')
        await t.play(octi, targets=[rem.entity_id])
        self.assertIs(rem.parent, octi)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_suction_cup_draw_may_decline(self):
        t = self.table()
        rem = t.put(REMORAID, P1, 'active')
        octi = t.put(OCTILLERY, P1, 'hand')
        t.yes = False
        await t.play(octi, targets=[rem.entity_id])
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def _smokescreen(self, heads):
        t = Table(self)
        octi = self.neutral(t.put(OCTILLERY, P1, 'active'), 110)
        t.energy(octi, W, 2)
        sab = self.neutral(t.put(SABLEYE, P2, 'active'), 400)
        t.energy(sab, D)
        await t.attack(octi, 'Smokescreen Shot')
        self.assertEqual(self.took(t, sab), 60)
        t.next_turn()
        # the pre-attack Smokescreen flip is a session coin, not EffectContext
        with patch.object(t.session, '_attack_attempt_coins',
                          lambda pid, count: [heads] * count):
            await t.attack(sab, 'Unseen Claw', pid=P2)
        return t, octi

    async def test_smokescreen_tails_attack_fails(self):
        t, octi = await self._smokescreen(False)
        self.assertEqual(self.took(t, octi), 0)

    async def test_smokescreen_heads_attack_happens(self):
        t, octi = await self._smokescreen(True)
        self.assertEqual(self.took(t, octi), 20)

    # --- Trumbeak LOT: Mountain Pass ----------------------------------------
    async def test_mountain_pass_supporter_to_lost_zone(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        tb = t.put(TRUMBEAK_LOT, P1, 'hand')
        sup = t.deck(P2, [HAU])[0]
        await t.use(tb, 'Mountain Pass')
        self.assertIn(tb, t.zone(P1, 'lostZone'))
        self.assertIn(sup, t.zone(P2, 'lostZone'))
        self.assertNotIn(sup, t.zone(P2, 'deck'))

    async def test_mountain_pass_non_supporter_stays(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        tb = t.put(TRUMBEAK_LOT, P1, 'hand')
        top = t.deck(P2, [ARTAZON])[0]
        await t.use(tb, 'Mountain Pass')
        self.assertIn(tb, t.zone(P1, 'lostZone'))
        self.assertIn(top, t.zone(P2, 'deck'))
        self.assertEqual(t.zone(P2, 'lostZone'), [])

    async def test_mountain_pass_not_with_empty_opponent_deck(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        tb = t.put(TRUMBEAK_LOT, P1, 'hand')
        area = t.board.find_player_area(P2, 'deck')
        for c in list(area.children):
            area.remove_child(c)
        self.assertIsNone(t.ability_offer(tb, 'Mountain Pass'))

    # --- Trumbeak VIV: Charging Trumpet -------------------------------------
    async def test_charging_trumpet_attaches_basic_energy_from_top_three(self):
        t = self.table()
        pik = t.put(PIKIPEK, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        e3 = t.put(t.basic_energy(G), P1, 'deck')   # 4th from top: not looked at
        item = t.put(self.item, P1, 'deck')
        e1 = t.put(t.basic_energy(W), P1, 'deck')
        e2 = t.put(t.basic_energy(F), P1, 'deck')    # top
        tb = t.put(TRUMBEAK_VIV, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in (e1, e2)]
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        await t.play(tb, targets=[pik.entity_id])
        self.assertIs(pik.parent, tb)
        attached = [c for c in list(tb.children) + list(bench.children) if c in (e1, e2, e3)]
        self.assertEqual(set(attached), {e1, e2})
        self.assertIn(e3, t.zone(P1, 'deck'))
        self.assertIn(item, t.zone(P1, 'deck'))

    async def test_charging_trumpet_may_attach_none(self):
        # "any number": choosing none attaches nothing and keeps the deck size
        t = self.table()
        pik = t.put(PIKIPEK, P1, 'active')
        e = t.deck(P1, [t.basic_energy(W)])[0]
        before = len(t.zone(P1, 'deck'))
        tb = t.put(TRUMBEAK_VIV, P1, 'hand')
        t.yes = False
        t.picks = lambda cards, count, prompt, display: []
        await t.play(tb, targets=[pik.entity_id])
        self.assertIs(pik.parent, tb)
        self.assertNotIn(e, tb.children)
        self.assertIn(e, t.zone(P1, 'deck'))
        self.assertEqual(len(t.zone(P1, 'deck')), before)

    # --- Snom SHF: Call for Family ------------------------------------------
    async def test_call_for_family_benches_one_basic(self):
        t = self.table()
        snom = t.put(SNOM, P1, 'active')
        t.energy(snom, W)
        t.deck(P1, [RIOLU_PRE, LUCARIO_30C])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.attack(snom, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual([name(c) for c in bench], ['Riolu'])
        self.assertNotIn('Lucario', [name(c) for c in seen])

    async def test_call_for_family_full_bench_benches_nothing(self):
        t = self.table()
        snom = t.put(SNOM, P1, 'active')
        t.energy(snom, W)
        for _ in range(5):
            t.put(self.filler, P1, 'bench')
        riolu = t.deck(P1, [RIOLU_PRE])[0]
        await t.attack(snom, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)
        self.assertIn(riolu, t.zone(P1, 'deck'))

    # --- Hawlucha POR: Vengeful Kick ----------------------------------------
    async def test_vengeful_kick_with_damaged_bench(self):
        t = self.table()
        h = t.put(HAWLUCHA, P1, 'active')
        t.energy(h, F)
        b = t.put(self.filler, P1, 'bench')
        b.set_attribute(AttrID.HP, t.hp(b) - 10)
        await t.attack(h, 'Vengeful Kick')
        self.assertEqual(self.took(t, self.opp), 90)

    async def test_vengeful_kick_ignores_opponent_bench_and_self(self):
        t = self.table()
        h = t.put(HAWLUCHA, P1, 'active', hp=40)
        t.energy(h, F)
        t.put(self.filler, P1, 'bench')
        ob = t.put(self.filler, P2, 'bench')
        ob.set_attribute(AttrID.HP, t.hp(ob) - 30)
        await t.attack(h, 'Vengeful Kick')
        self.assertEqual(self.took(t, self.opp), 30)

    # --- Greedent SVI: Enhanced Fang ----------------------------------------
    async def test_enhanced_fang_with_tool(self):
        t = self.table()
        g = t.put(GREEDENT, P1, 'active')
        t.energy(g, W, 3)
        t.attach(FLOAT_STONE, g)
        await t.attack(g, 'Enhanced Fang')
        self.assertEqual(self.took(t, self.opp), 160)

    async def test_enhanced_fang_without_tool(self):
        t = self.table()
        g = t.put(GREEDENT, P1, 'active')
        t.energy(g, W, 3)
        t.attach(FLOAT_STONE, self.opp)          # opponent's tool doesn't count
        await t.attack(g, 'Enhanced Fang')
        self.assertEqual(self.took(t, self.opp), 80)

    # --- Marshadow PBL: Shadowy Knot ----------------------------------------
    async def test_shadowy_knot_counts_retreat_cost(self):
        t = self.table()
        m = t.put(MARSHADOW, P1, 'active')
        t.energy(m, P)
        cost = t.retreat(self.opp)
        self.assertGreater(cost, 0)
        await t.attack(m, 'Shadowy Knot')
        self.assertEqual(self.took(t, self.opp), 30 * cost)

    async def test_shadowy_knot_zero_retreat(self):
        t = Table(self)
        m = t.put(MARSHADOW, P1, 'active')
        t.energy(m, P)
        h = self.neutral(t.put(HAWLUCHA, P2, 'active'), 400)   # retreat 0
        await t.attack(m, 'Shadowy Knot')
        self.assertEqual(self.took(t, h), 0)

    async def test_shadowy_knot_uses_modified_retreat(self):
        t = self.table()
        m = t.put(MARSHADOW, P1, 'active')
        t.energy(m, P)
        t.attach(FLOAT_STONE, self.opp)
        self.assertEqual(t.retreat(self.opp), 0)
        await t.attack(m, 'Shadowy Knot')
        self.assertEqual(self.took(t, self.opp), 0)

    # --- Lucario BRS: Roaring Resolve / Aura Sphere Volley ------------------
    async def test_roaring_resolve_counters_and_attach(self):
        t = self.table()
        luc = t.put(LUCARIO_BRS, P1, 'active')
        e = t.deck(P1, [t.basic_energy(F)])[0]
        await t.use(luc, 'Roaring Resolve')
        self.assertEqual(t.damage(luc), 20)
        self.assertIn(e, luc.children)
        self.assertIsNone(t.ability_offer(luc, 'Roaring Resolve'))

    async def test_roaring_resolve_no_reconfirm(self):
        # Oct 13 owner ruling: clicking the Ability is the "you may"; no
        # second yes/no before the 2 damage counters.
        t = self.table()
        luc = t.put(LUCARIO_BRS, P1, 'bench')
        t.put(self.filler, P1, 'active')
        e = t.deck(P1, [t.basic_energy(F)])[0]
        asked = []
        t.yes = lambda prompt: asked.append(prompt) or False
        await t.use(luc, 'Roaring Resolve')
        self.assertEqual(asked, [])
        self.assertEqual(t.damage(luc), 20)
        self.assertIn(e, luc.children)

    async def test_roaring_resolve_only_fighting_energy(self):
        t = self.table()
        luc = t.put(LUCARIO_BRS, P1, 'active')
        w = t.deck(P1, [t.basic_energy(W)])[0]
        await t.use(luc, 'Roaring Resolve')
        self.assertEqual(t.damage(luc), 20)
        self.assertNotIn(w, luc.children)

    async def test_aura_sphere_volley_discards_only_fighting(self):
        t = self.table()
        luc = t.put(LUCARIO_BRS, P1, 'active')
        fs = t.energy(luc, F, 3)
        w = t.energy(luc, W)
        await t.attack(luc, 'Aura Sphere Volley')
        self.assertEqual(self.took(t, self.opp), 190)
        for e in fs:
            self.assertIn(e, t.zone(P1, 'discard'))
        self.assertIn(w, luc.children)

    # --- Lucario 30C: Aura Sphere -------------------------------------------
    async def test_aura_sphere_hits_bench_without_weakness(self):
        t = self.table()
        luc = t.put(LUCARIO_30C, P1, 'active')
        t.energy(luc, F, 3)
        b = t.put(self.filler, P2, 'bench')
        b.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        b.set_attribute(AttrID.HP, 300)
        b._start_hp = 300
        mine = self.neutral(t.put(self.filler, P1, 'bench'))
        await t.attack(luc, 'Aura Sphere')
        self.assertEqual(self.took(t, self.opp), 100)
        self.assertEqual(self.took(t, b), 60)
        self.assertEqual(self.took(t, mine), 0)

    async def test_aura_sphere_no_bench(self):
        t = self.table()
        luc = t.put(LUCARIO_30C, P1, 'active')
        t.energy(luc, F, 3)
        await t.attack(luc, 'Aura Sphere')
        self.assertEqual(self.took(t, self.opp), 100)

    # --- Riolu MEG: Accelerating Stab ---------------------------------------
    async def test_accelerating_stab_locks_next_turn_only(self):
        t = self.table()
        r = t.put(RIOLU_MEG, P1, 'active')
        t.energy(r, F)
        await t.attack(r, 'Accelerating Stab')
        self.assertEqual(self.took(t, self.opp), 30)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(r, 'Accelerating Stab'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(r, 'Accelerating Stab'))

    # --- Riolu PRE: Quick Attack --------------------------------------------
    async def test_quick_attack_heads_and_tails(self):
        for heads, dmg in ((True, 30), (False, 10)):
            t = self.table()
            r = t.put(RIOLU_PRE, P1, 'active')
            t.energy(r, F)
            t.heads = heads
            await t.attack(r, 'Quick Attack')
            with self.subTest(heads=heads):
                self.assertEqual(self.took(t, self.opp), dmg)

    # --- Purrloin UNM: Cleaning Up ------------------------------------------
    async def test_cleaning_up_discards_opponent_bench_tool(self):
        t = self.table()
        p = t.put(PURRLOIN, P1, 'active')
        t.energy(p, W)
        ob = t.put(self.filler, P2, 'bench')
        tool = t.attach(FLOAT_STONE, ob)
        own = t.attach(FLOAT_STONE, p)
        t.pokemon = lambda cands, prompt: ob if ob in cands else cands[0]
        t.picks = lambda cards, count, prompt, display: [tool] if tool in cards else cards[:count]
        await t.attack(p, 'Cleaning Up')
        self.assertIn(tool, t.zone(P2, 'discard'))
        self.assertIn(own, p.children)

    async def test_cleaning_up_no_tools_only_own_tool(self):
        t = self.table()
        p = t.put(PURRLOIN, P1, 'active')
        t.energy(p, W)
        own = t.attach(FLOAT_STONE, p)
        await t.attack(p, 'Cleaning Up')
        self.assertIn(own, p.children)
        self.assertEqual(self.took(t, self.opp), 0)


if __name__ == '__main__':
    unittest.main()
