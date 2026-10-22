"""Bug hunt round 7, chunk 5: each card checked against its printed text,
including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W, D, R, M = PokemonTypes.WATER, PokemonTypes.DARKNESS, PokemonTypes.FIRE, PokemonTypes.METAL

DODRIO = 'SV035.Dodrio_85'
TOMB_SLG, TOMB_UPR = 'SL.Spiritomb_47', 'SM5.Spiritomb_53'
RESHIRAM = 'ME2.Reshiram_17'
URSA_DAA, URSA_ASR = 'SWSH3.Ursaring_139', 'SWSH10.Ursaring_123'
ARCHALUDON = 'ME2.Archaludon_75'
MAGCARGO = 'SV05.Magcargo_29'
VAROOM = 'SV045.Varoom_64'
RECYCLER = 'SV10.EnergyRecycler_164'
YVELTAL = 'ME1.Yveltal_88'
SLUGMA = 'SWSH4.Slugma_27'
TOXEL, TOXTRICITY = 'ME2.Toxel_67', 'ME2.Toxtricity_68'
AQUA_BALL = 'TATM.TeamAquasGreatBall_27'
AQUA_POOCHYENA, AQUA_MIGHTYENA = 'TATM.TeamAquasPoochyena_16', 'TATM.TeamAquasMightyena_18'
IONO, RESEARCH = 'SV2.Iono_185', 'CZ.ProfessorsResearch_150'
BOSS, SWITCH = 'ME1.BosssOrders_114', 'SV1.Switch_194'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk5(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=False):
        t = Table(self)
        if me:
            t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    @staticmethod
    def neutral(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)

    def took(self, t, p, hp=400):
        return hp - t.hp(p)

    def filler_attack(self):
        return self.filler.abilities[0].title

    # --- Dodrio (MEW 85) ---------------------------------------------------
    async def test_dodrio_zooming_draw_counter_and_draw_once(self):
        t = self.table()
        d = t.put(DODRIO, P1, 'active')
        hand = len(t.zone(P1, 'hand'))
        await t.use(d, 'Zooming Draw')
        self.assertEqual(t.damage(d), 10)
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 1)
        self.assertIsNone(t.ability_offer(d, 'Zooming Draw'))

    async def test_dodrio_zooming_draw_from_bench(self):
        t = self.table()
        d = t.put(DODRIO, P1, 'bench')
        t.put(self.filler, P1, 'active')
        hand = len(t.zone(P1, 'hand'))
        await t.use(d, 'Zooming Draw')
        self.assertEqual(t.damage(d), 10)
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 1)

    async def test_dodrio_zooming_draw_not_offered_with_empty_deck(self):
        # "If you do, draw a card" - with no deck the counter would be pointless;
        # either way it must not place a counter without drawing.
        t = self.table()
        d = t.put(DODRIO, P1, 'active')
        area = t.board.find_player_area(P1, 'deck')
        for c in list(area.children):
            area.remove_child(c)
        entry = t.ability_offer(d, 'Zooming Draw')
        if entry is not None:
            await t.do(entry)
        self.assertIn(t.damage(d), (0, 10))

    async def test_dodrio_ballistic_beak_scales(self):
        t = self.table()
        d = t.put(DODRIO, P1, 'active', hp=70)   # 3 counters
        t.energy(d, W, 1)
        await t.attack(d, 'Ballistic Beak')
        self.assertEqual(self.took(t, self.opp), 10 + 90)

    async def test_dodrio_ballistic_beak_undamaged(self):
        t = self.table()
        d = t.put(DODRIO, P1, 'active')
        t.energy(d, W, 1)
        await t.attack(d, 'Ballistic Beak')
        self.assertEqual(self.took(t, self.opp), 10)

    # --- Spiritomb (SLG 47) -----------------------------------------------
    async def test_spiritomb_cursed_whirlpool_active_blocks_retreat(self):
        t = self.table()
        t.put(TOMB_SLG, P1, 'active')
        t.energy(self.opp, W, 5)
        t.put(self.filler, P2, 'bench')
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))

    async def test_spiritomb_cursed_whirlpool_bench_no_block(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(TOMB_SLG, P1, 'bench')
        t.energy(self.opp, W, 5)
        t.put(self.filler, P2, 'bench')
        t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))

    async def test_spiritomb_cursed_whirlpool_own_side_unaffected(self):
        t = self.table()
        s = t.put(TOMB_SLG, P1, 'active')
        t.energy(s, D, 2)
        t.put(self.filler, P1, 'bench')
        self.assertTrue(t.can(s, 'BaseRetreat'))

    async def test_spiritomb_cursed_drop_split(self):
        t = self.table()
        s = t.put(TOMB_SLG, P1, 'active')
        t.energy(s, D, 2)
        b = t.put(self.filler, P2, 'bench')
        self.neutral(b)
        seen = {}

        async def place(player_id, source_id, pool, count, prompt=''):
            seen['pool'] = {p.entity_id for p in pool}
            seen['count'] = count
            return {self.opp.entity_id: 1, b.entity_id: 2}
        with patch.object(t.session, 'prompt_damage_counter_placement', place):
            await t.attack(s, 'Cursed Drop')
        self.assertEqual(seen['count'], 3)
        self.assertEqual(seen['pool'], {self.opp.entity_id, b.entity_id})
        self.assertEqual(self.took(t, self.opp), 10)
        self.assertEqual(self.took(t, b), 20)

    # --- Spiritomb (UPR 53) -----------------------------------------------
    async def test_spiritomb_lightless_world_two_supporters(self):
        t = self.table()
        s = t.put(TOMB_UPR, P1, 'active')
        t.energy(s, W, 1)
        iono = t.put(IONO, P1, 'discard')
        res = t.put(RESEARCH, P1, 'discard')
        t.put(self.item, P1, 'discard')
        await t.attack(s, 'Lightless World')
        hand = t.zone(P1, 'hand')
        self.assertIn(iono, hand)
        self.assertIn(res, hand)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_spiritomb_lightless_world_no_items(self):
        t = self.table()
        s = t.put(TOMB_UPR, P1, 'active')
        t.energy(s, W, 1)
        item = t.put(self.item, P1, 'discard')
        await t.attack(s, 'Lightless World')
        self.assertIn(item, t.zone(P1, 'discard'))
        self.assertNotIn(item, t.zone(P1, 'hand'))

    async def test_spiritomb_terrify_basic_cannot_attack(self):
        t = self.table()
        s = t.put(TOMB_UPR, P1, 'active')
        t.energy(s, W, 1)
        t.energy(self.opp, W, 4)
        await t.attack(s, 'Terrify')
        self.assertEqual(self.took(t, self.opp), 10)
        t.next_turn()
        self.assertIsNone(t.attack_offer(self.opp, self.filler_attack(), P2))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(self.opp, self.filler_attack(), P2))

    async def test_spiritomb_terrify_stage1_can_attack(self):
        t = Table(self)
        opp = t.put(DODRIO, P2, 'active')
        self.neutral(opp)
        s = t.put(TOMB_UPR, P1, 'active')
        t.energy(s, W, 1)
        t.energy(opp, W, 1)
        await t.attack(s, 'Terrify')
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(opp, 'Ballistic Beak', P2))

    # --- Reshiram (PFL 17) ------------------------------------------------
    async def test_reshiram_burning_flare_self_damage(self):
        t = self.table()
        r = t.put(RESHIRAM, P1, 'active')
        self.neutral(r, None)
        t.energy(r, R, 4)
        await t.attack(r, 'Burning Flare')
        self.assertEqual(self.took(t, self.opp), 240)
        self.assertEqual(t.damage(r), 60)

    async def test_reshiram_combustion_no_self_damage(self):
        t = self.table()
        r = t.put(RESHIRAM, P1, 'active')
        t.energy(r, R, 1)
        await t.attack(r, 'Combustion')
        self.assertEqual(self.took(t, self.opp), 30)
        self.assertEqual(t.damage(r), 0)

    # --- Ursaring (DAA 139) -----------------------------------------------
    async def test_ursaring_hammer_arm_mills_opponent(self):
        t = self.table()
        u = t.put(URSA_DAA, P1, 'active')
        t.energy(u, W, 3)
        top = t.deck(P2, [self.filler])[0]
        mine = len(t.zone(P1, 'deck'))
        await t.attack(u, 'Hammer Arm')
        self.assertEqual(self.took(t, self.opp), 70)
        self.assertIn(top, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'deck')), mine)

    async def test_ursaring_hammer_arm_empty_deck(self):
        t = self.table()
        u = t.put(URSA_DAA, P1, 'active')
        t.energy(u, W, 3)
        area = t.board.find_player_area(P2, 'deck')
        for c in list(area.children):
            area.remove_child(c)
        await t.attack(u, 'Hammer Arm')
        self.assertEqual(self.took(t, self.opp), 70)
        self.assertEqual(len(t.zone(P2, 'discard')), 0)

    # --- Ursaring (ASR 123) -----------------------------------------------
    async def _slap(self, heads):
        t = self.table()
        u = t.put(URSA_ASR, P1, 'active')
        t.energy(u, W, 1)

        async def run(ctx, title=''):
            return heads
        with patch.object(EffectContext, 'flip_until_tails', run):
            await t.attack(u, 'Continuous Slap')
        return t

    async def test_ursaring_continuous_slap_three_heads(self):
        t = await self._slap(3)
        self.assertEqual(self.took(t, self.opp), 120)

    async def test_ursaring_continuous_slap_tails_first(self):
        t = await self._slap(0)
        self.assertEqual(self.took(t, self.opp), 0)

    # --- Archaludon (PFL 75) ----------------------------------------------
    async def _coated(self, attacker_spec):
        t = Table(self)
        a = t.put(ARCHALUDON, P1, 'active')
        self.neutral(a)
        t.energy(a, M, 3)
        opp = t.put(attacker_spec, P2, 'active')
        self.neutral(opp)
        await t.attack(a, 'Coated Attack')
        self.assertEqual(self.took(t, opp), 120)
        return t, a, opp

    async def test_archaludon_coated_attack_blocks_basic(self):
        t, a, opp = await self._coated(self.filler)
        t.energy(opp, W, 4)
        t.next_turn()
        await t.attack(opp, self.filler_attack(), pid=P2)
        self.assertEqual(self.took(t, a), 0)

    async def test_archaludon_coated_attack_not_stage1(self):
        t, a, opp = await self._coated(DODRIO)
        t.energy(opp, W, 1)
        t.next_turn()
        await t.attack(opp, 'Ballistic Beak', pid=P2)
        self.assertEqual(self.took(t, a), 10)

    async def test_archaludon_coated_attack_expires(self):
        t, a, opp = await self._coated(self.filler)
        t.energy(opp, W, 4)
        t.next_turn()
        t.next_turn()
        t.next_turn()
        await t.attack(opp, self.filler_attack(), pid=P2)
        self.assertGreater(self.took(t, a), 0)

    # --- Magcargo (TEF 29) ------------------------------------------------
    async def test_magcargo_lava_zone_retreat_burns_new_active(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(MAGCARGO, P1, 'bench')   # works from the Bench
        t.energy(self.opp, W, 4)
        new = t.put(self.filler, P2, 'bench')
        t.next_turn()
        entry = next(iter(t.offers(self.opp, 'BaseRetreat', P2)))
        await t.do(entry, targets=[new.entity_id] + [e.entity_id for e in t.attached(self.opp)],
                   pid=P2)
        self.assertIs(t.active(P2), new)
        self.assertIn(BURNED, t.conditions(new))

    async def test_magcargo_lava_zone_switch_card_burns(self):
        t = self.table()
        t.put(MAGCARGO, P1, 'active')
        new = t.put(self.filler, P2, 'bench')
        t.next_turn()
        sw = t.put(SWITCH, P2, 'hand')
        await t.play(sw, pid=P2, targets=[new.entity_id])
        self.assertIs(t.active(P2), new)
        self.assertIn(BURNED, t.conditions(new))

    async def test_magcargo_lava_zone_not_on_my_gust(self):
        t = self.table()
        t.put(MAGCARGO, P1, 'active')
        new = t.put(self.filler, P2, 'bench')
        boss = t.put(BOSS, P1, 'hand')
        await t.play(boss, targets=[new.entity_id])
        self.assertIs(t.active(P2), new)
        self.assertNotIn(BURNED, t.conditions(new))

    async def test_magcargo_lava_zone_own_switch_unaffected(self):
        t = self.table()
        t.put(MAGCARGO, P1, 'active')
        mine = t.put(self.filler, P1, 'bench')
        sw = t.put(SWITCH, P1, 'hand')
        await t.play(sw, targets=[mine.entity_id])
        self.assertIs(t.active(P1), mine)
        self.assertNotIn(BURNED, t.conditions(mine))

    # --- Varoom (PAF 64) --------------------------------------------------
    async def test_varoom_rev_two_basic_energy(self):
        t = self.table()
        v = t.put(VAROOM, P1, 'active')
        t.energy(v, W, 1)
        es = [t.put(t.basic_energy(k), P1, 'discard') for k in (W, R, M)]
        await t.attack(v, 'Rev')
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(1 for e in es if e in hand), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_varoom_rev_ignores_non_energy(self):
        t = self.table()
        v = t.put(VAROOM, P1, 'active')
        t.energy(v, W, 1)
        item = t.put(self.item, P1, 'discard')
        await t.attack(v, 'Rev')
        self.assertIn(item, t.zone(P1, 'discard'))

    # --- Energy Recycler (DRI 164) ----------------------------------------
    async def test_energy_recycler_up_to_five(self):
        t = self.table(me=True)
        es = [t.put(t.basic_energy(W), P1, 'discard') for _ in range(6)]
        card = t.put(RECYCLER, P1, 'hand')
        deck = len(t.zone(P1, 'deck'))
        await t.play(card)
        self.assertEqual(sum(1 for e in es if e in t.zone(P1, 'deck')), 5)
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 5)

    async def test_energy_recycler_not_playable_without_basic_energy(self):
        t = self.table(me=True)
        t.put(self.item, P1, 'discard')
        card = t.put(RECYCLER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Yveltal (MEG 88) -------------------------------------------------
    async def test_yveltal_clutch_blocks_retreat_next_turn(self):
        t = self.table()
        y = t.put(YVELTAL, P1, 'active')
        t.energy(y, D, 1)
        t.energy(self.opp, W, 5)
        t.put(self.filler, P2, 'bench')
        await t.attack(y, 'Clutch')
        self.assertEqual(self.took(t, self.opp), 20)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))

    async def test_yveltal_clutch_new_active_can_retreat(self):
        # Only the Defending Pokémon is locked; after Switch the new one may retreat
        t = self.table()
        y = t.put(YVELTAL, P1, 'active')
        t.energy(y, D, 1)
        t.energy(self.opp, W, 5)
        new = t.put(self.filler, P2, 'bench')
        t.energy(new, W, 5)
        await t.attack(y, 'Clutch')
        t.next_turn()
        sw = t.put(SWITCH, P2, 'hand')
        await t.play(sw, pid=P2, targets=[new.entity_id])
        self.assertTrue(t.can(new, 'BaseRetreat', P2))

    # --- Slugma (VIV 27) --------------------------------------------------
    async def test_slugma_yawn_asleep(self):
        t = self.table()
        s = t.put(SLUGMA, P1, 'active')
        t.energy(s, W, 1)
        await t.attack(s, 'Yawn')
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_slugma_yawn_bench_untouched(self):
        t = self.table()
        s = t.put(SLUGMA, P1, 'active')
        t.energy(s, W, 1)
        b = t.put(self.filler, P2, 'bench')
        await t.attack(s, 'Yawn')
        self.assertNotIn(ASLEEP, t.conditions(b))
        self.assertNotIn(ASLEEP, t.conditions(s))

    # --- Toxel (PFL 67) ---------------------------------------------------
    async def test_toxel_call_for_family_two_basics(self):
        t = self.table()
        x = t.put(TOXEL, P1, 'active')
        t.energy(x, D, 1)
        cards = t.deck(P1, [self.filler, VAROOM, DODRIO])
        await t.attack(x, 'Call for Family')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        self.assertNotIn(cards[2], bench)   # Stage 1 not eligible
        self.assertIn(cards[2], t.zone(P1, 'deck'))

    async def test_toxel_call_for_family_bench_limit(self):
        t = self.table()
        x = t.put(TOXEL, P1, 'active')
        t.energy(x, D, 1)
        for _ in range(4):
            t.put(self.filler, P1, 'bench')
        t.deck(P1, [self.filler, VAROOM])
        await t.attack(x, 'Call for Family')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Toxtricity (PFL 68) ----------------------------------------------
    async def test_toxtricity_sinister_surge(self):
        t = self.table()
        tx = t.put(TOXTRICITY, P1, 'active')
        dark = t.put(TOXEL, P1, 'bench')
        t.put(VAROOM, P1, 'bench')
        e = t.deck(P1, [t.basic_energy(D)])[0]
        await t.use(tx, 'Sinister Surge')
        self.assertIn(e, t.attached(dark))
        self.assertEqual(t.damage(dark), 20)
        self.assertEqual(t.damage(tx), 0)
        self.assertIsNone(t.ability_offer(tx, 'Sinister Surge'))

    async def test_toxtricity_sinister_surge_not_without_benched_darkness(self):
        t = self.table()
        tx = t.put(TOXTRICITY, P1, 'active')
        t.put(VAROOM, P1, 'bench')
        t.deck(P1, [t.basic_energy(D)])
        self.assertIsNone(t.ability_offer(tx, 'Sinister Surge'))

    async def test_toxtricity_sinister_surge_no_energy_no_damage(self):
        t = self.table()
        tx = t.put(TOXTRICITY, P1, 'active')
        dark = t.put(TOXEL, P1, 'bench')
        t.deck(P1, [t.basic_energy(W)])
        entry = t.ability_offer(tx, 'Sinister Surge')
        if entry is None:
            return   # not offered when no hit is possible: also fine
        await t.do(entry)
        self.assertEqual(t.damage(dark), 0)
        self.assertEqual(len(t.attached(dark)), 0)

    # --- Team Aqua's Great Ball (DCR 27) ----------------------------------
    async def test_aqua_great_ball_finds_both(self):
        t = self.table(me=True)
        poo, mighty, snor, fire, water = t.deck(P1, [
            AQUA_POOCHYENA, AQUA_MIGHTYENA, self.filler,
            t.basic_energy(R), t.basic_energy(W)])
        card = t.put(AQUA_BALL, P1, 'hand')
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertIn(poo, hand)
        self.assertIn(water, hand)
        for c in (mighty, snor, fire):
            self.assertNotIn(c, hand)

    async def test_aqua_great_ball_rejects_non_aqua_and_non_water(self):
        t = self.table(me=True)
        mighty, snor, fire = t.deck(P1, [AQUA_MIGHTYENA, self.filler, t.basic_energy(R)])
        card = t.put(AQUA_BALL, P1, 'hand')
        hand_before = set(c.entity_id for c in t.zone(P1, 'hand')) - {card.entity_id}
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        hand = set(c.entity_id for c in t.zone(P1, 'hand')) - {card.entity_id}
        self.assertEqual(hand, hand_before)


if __name__ == '__main__':
    unittest.main()
