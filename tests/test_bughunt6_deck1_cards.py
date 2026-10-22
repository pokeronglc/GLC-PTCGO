"""Bug hunt round 6, deck 1 (Darkness): Purrloin DAA 106, Sneasel PAL 133,
Weavile UPR 74, Zorua LTR 89, Zoroark BKT 91, Guzzlord CEC 136,
Hoopa DAA 111, Spiritomb UNB 112, Beast Ring FLI 102."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

D, W, F = PokemonTypes.DARKNESS, PokemonTypes.WATER, PokemonTypes.FIRE
PURRLOIN, SNEASEL, WEAVILE = 'SWSH3.Purrloin_106', 'SV2.Sneasel_133', 'SM5.Weavile_74'
ZORUA, ZOROARK, GUZZLORD = 'BW11.Zorua_89', 'XY8.Zoroark_91', 'SM12.Guzzlord_136'
HOOPA, SPIRITOMB, BEASTRING = 'SWSH3.Hoopa_111', 'SM10.Spiritomb_112', 'SM6.BeastRing_102'


def name(card):
    return def_for(card.archetype_id).display_name


class Deck1Cards6(unittest.IsolatedAsyncioTestCase):
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

    # --- Purrloin: Fake Out -------------------------------------------------
    async def test_fake_out_heads_paralyzes(self):
        t = self.table()
        p = t.put(PURRLOIN, P1, 'active')
        t.energy(p, D, 2)
        t.heads = True
        await t.attack(p, 'Fake Out')
        self.assertEqual(self.took(t, self.opp), 20)
        self.assertIn(PARALYZED, t.conditions(self.opp))

    async def test_fake_out_tails_no_paralysis(self):
        t = self.table()
        p = t.put(PURRLOIN, P1, 'active')
        t.energy(p, D, 2)
        t.heads = False
        await t.attack(p, 'Fake Out')
        self.assertEqual(self.took(t, self.opp), 20)
        self.assertNotIn(PARALYZED, t.conditions(self.opp))

    # --- Weavile: Icy Wind / Evil Admonition ---------------------------------
    async def test_icy_wind_asleep(self):
        t = self.table()
        w = t.put(WEAVILE, P1, 'active')
        t.energy(w, D)
        await t.attack(w, 'Icy Wind')
        self.assertEqual(self.took(t, self.opp), 10)
        self.assertIn(ASLEEP, t.conditions(self.opp))

    async def test_evil_admonition_counts_opponent_ability_pokemon(self):
        t = self.table()
        w = t.put(WEAVILE, P1, 'active')
        t.energy(w, D)
        t.put(SPIRITOMB, P2, 'bench')          # has an Ability
        t.put(ZOROARK, P2, 'bench')            # has an Ability
        t.put(SNEASEL, P2, 'bench')            # no Ability
        t.put(SPIRITOMB, P1, 'bench')          # mine: must not count
        await t.attack(w, 'Evil Admonition')
        self.assertEqual(self.took(t, self.opp), 100)

    async def test_evil_admonition_counts_active_with_ability(self):
        t = Table(self)
        opp = self.neutral(t.put(ZOROARK, P2, 'active'), 400)
        w = t.put(WEAVILE, P1, 'active')
        t.energy(w, D)
        await t.attack(w, 'Evil Admonition')
        self.assertEqual(self.took(t, opp), 50)

    async def test_evil_admonition_zero_without_abilities(self):
        t = self.table()
        w = t.put(WEAVILE, P1, 'active')
        t.energy(w, D)
        t.put(SNEASEL, P2, 'bench')
        await t.attack(w, 'Evil Admonition')
        self.assertEqual(self.took(t, self.opp), 0)

    # --- Zorua: Ascension ---------------------------------------------------
    async def test_ascension_evolves_into_zoroark(self):
        t = self.table()
        z = t.put(ZORUA, P1, 'active')
        t.energy(z, D)
        zk = t.deck(P1, [ZOROARK])[0]
        await t.attack(z, 'Ascension')
        active = t.active(P1)
        self.assertEqual(name(active), 'Zoroark')
        self.assertIn(zk, [active] + list(active.children) + t.zone(P1, 'activePokemonArea'))
        self.assertNotIn(zk, t.zone(P1, 'deck'))
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_ascension_ignores_other_evolutions(self):
        t = self.table()
        z = t.put(ZORUA, P1, 'active')
        t.energy(z, D)
        wv = t.deck(P1, [WEAVILE])[0]
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return [c for c in cards if c is wv]
        t.picks = picks
        await t.attack(z, 'Ascension')
        self.assertNotIn(wv, seen)
        self.assertEqual(name(t.active(P1)), 'Zorua')
        self.assertIn(wv, t.zone(P1, 'deck'))

    # --- Zoroark: Stand In / Mind Jack --------------------------------------
    async def test_stand_in_switches_from_bench(self):
        t = self.table()
        a = t.put(self.filler, P1, 'active')
        zk = t.put(ZOROARK, P1, 'bench')
        self.assertIsNotNone(t.ability_offer(zk, 'Stand In'))
        await t.use(zk, 'Stand In')
        self.assertIs(t.active(P1), zk)
        self.assertIn(a, t.zone(P1, 'bench'))
        self.assertIsNone(t.ability_offer(zk, 'Stand In'))   # Active now

    async def test_stand_in_not_from_active(self):
        t = self.table()
        zk = t.put(ZOROARK, P1, 'active')
        t.put(self.filler, P1, 'bench')
        self.assertIsNone(t.ability_offer(zk, 'Stand In'))

    async def test_stand_in_once_per_turn_per_zoroark(self):
        # A second Zoroark may use its own Stand In; the first one, sent back
        # to the Bench, can't use Stand In again this turn.
        t = self.table()
        t.put(self.filler, P1, 'active')
        z1 = t.put(ZOROARK, P1, 'bench')
        z2 = t.put(ZOROARK, P1, 'bench')
        await t.use(z1, 'Stand In')
        self.assertIsNotNone(t.ability_offer(z2, 'Stand In'))
        await t.use(z2, 'Stand In')
        self.assertIs(t.active(P1), z2)
        self.assertIn(z1, t.zone(P1, 'bench'))
        self.assertIsNone(t.ability_offer(z1, 'Stand In'))

    async def test_stand_in_and_building_spite_blocked_by_ability_lock(self):
        t = Table(self)
        self.neutral(t.put('SWSH2.GalarianWeezing_113', P2, 'active'), 400)
        t.put(self.filler, P1, 'active')
        zk = t.put(ZOROARK, P1, 'bench')
        s = t.put(SPIRITOMB, P1, 'bench')
        self.assertIsNone(t.ability_offer(zk, 'Stand In'))
        self.assertIsNone(t.ability_offer(s, 'Building Spite'))

    async def test_mind_jack_counts_opponent_bench(self):
        t = self.table()
        zk = t.put(ZOROARK, P1, 'active')
        t.energy(zk, D, 2)
        for _ in range(3):
            t.put(self.filler, P2, 'bench')
        t.put(self.filler, P1, 'bench')        # my Bench does not count
        await t.attack(zk, 'Mind Jack')
        self.assertEqual(self.took(t, self.opp), 100)

    async def test_mind_jack_empty_bench_base_damage(self):
        t = self.table()
        zk = t.put(ZOROARK, P1, 'active')
        t.energy(zk, D, 2)
        await t.attack(zk, 'Mind Jack')
        self.assertEqual(self.took(t, self.opp), 10)

    # --- Guzzlord: Mountain Munch / Red Banquet -----------------------------
    async def test_mountain_munch_discards_opponent_top_card(self):
        t = self.table()
        g = t.put(GUZZLORD, P1, 'active')
        t.energy(g, D)
        top = t.deck(P2, [SNEASEL])[0]
        before_opp, before_me = len(t.zone(P2, 'deck')), len(t.zone(P1, 'deck'))
        await t.attack(g, 'Mountain Munch')
        self.assertIn(top, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P2, 'deck')), before_opp - 1)
        self.assertEqual(len(t.zone(P1, 'deck')), before_me)
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_red_banquet_ko_takes_extra_prize(self):
        t = Table(self)
        victim = self.neutral(t.put(self.filler, P2, 'active', hp=100))
        t.put(self.filler, P2, 'bench')
        g = t.put(GUZZLORD, P1, 'active')
        t.energy(g, D, 4)
        before = len(t.zone(P1, 'prizes'))
        await t.attack(g, 'Red Banquet')
        self.assertIn(victim, t.zone(P2, 'discard'))
        self.assertEqual(before - len(t.zone(P1, 'prizes')), 2)

    async def test_red_banquet_no_ko_no_prize(self):
        t = self.table()
        g = t.put(GUZZLORD, P1, 'active')
        t.energy(g, D, 4)
        before = len(t.zone(P1, 'prizes'))
        await t.attack(g, 'Red Banquet')
        self.assertEqual(self.took(t, self.opp), 120)
        self.assertEqual(len(t.zone(P1, 'prizes')), before)

    # --- Hoopa: Assault Gate ------------------------------------------------
    async def test_assault_gate_after_retreat_ignores_weakness(self):
        t = Table(self)
        opp = t.put(self.filler, P2, 'active')
        opp.set_attribute(AttrID.WEAKNESS_TYPES, [D.value])
        opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        opp.set_attribute(AttrID.HP, 400)
        start = t.hp(opp)
        a = t.put(self.filler, P1, 'active')
        t.energy(a, W, 3)
        h = t.put(HOOPA, P1, 'bench')
        t.energy(h, D)
        retreat = next(e for e in t.offers(a, None)
                       if e['selectableAction']['description'] == 'BaseRetreat')
        energies = [e.entity_id for e in a.children][:t.retreat(a)]
        await t.do(retreat, targets=[h.entity_id] + energies)
        self.assertIs(t.active(P1), h)
        await t.attack(h, 'Assault Gate')
        self.assertEqual(start - t.hp(opp), 90)

    async def test_assault_gate_does_nothing_if_already_active(self):
        t = self.table()
        h = t.put(HOOPA, P1, 'active')
        t.energy(h, D)
        await t.attack(h, 'Assault Gate')
        self.assertEqual(self.took(t, self.opp), 0)

    async def test_assault_gate_promoted_on_opponents_turn_does_nothing(self):
        t = Table(self)
        opp = self.neutral(t.put('SV2.Sableye_136', P2, 'active'), 400)
        t.energy(opp, D)
        victim = self.neutral(t.put(self.filler, P1, 'active', hp=10))
        h = self.neutral(t.put(HOOPA, P1, 'bench'))
        t.energy(h, D)
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertIn(victim, t.zone(P1, 'discard'))
        self.assertIs(t.active(P1), h)
        t.next_turn()
        await t.attack(h, 'Assault Gate')
        self.assertEqual(self.took(t, opp), 0)

    # --- Spiritomb: Building Spite / Anguish Cry ----------------------------
    async def test_building_spite_once_per_turn_and_anguish_cry(self):
        t = self.table()
        s = self.neutral(t.put(SPIRITOMB, P1, 'active'))
        t.energy(s, D)
        await t.use(s, 'Building Spite')
        self.assertEqual(t.damage(s), 10)
        self.assertIsNone(t.ability_offer(s, 'Building Spite'))
        await t.attack(s, 'Anguish Cry')
        self.assertEqual(self.took(t, self.opp), 40)

    async def test_building_spite_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        s = t.put(SPIRITOMB, P1, 'bench')
        self.assertIsNotNone(t.ability_offer(s, 'Building Spite'))
        await t.use(s, 'Building Spite')
        self.assertEqual(t.damage(s), 10)

    async def test_anguish_cry_no_counters(self):
        t = self.table()
        s = t.put(SPIRITOMB, P1, 'active')
        t.energy(s, D)
        await t.attack(s, 'Anguish Cry')
        self.assertEqual(self.took(t, self.opp), 10)

    async def test_anguish_cry_three_counters(self):
        t = self.table()
        s = t.put(SPIRITOMB, P1, 'active', hp=30)
        t.energy(s, D)
        await t.attack(s, 'Anguish Cry')
        self.assertEqual(self.took(t, self.opp), 100)

    # --- Beast Ring ---------------------------------------------------------
    def ring_board(self, opp_prizes):
        t = self.table()
        t.put(self.filler, P1, 'active')
        g = t.put(GUZZLORD, P1, 'bench')
        t.set_prizes(P2, opp_prizes)
        es = t.deck(P1, [t.basic_energy(D), t.basic_energy(F), t.basic_energy(W)])
        ring = t.put(BEASTRING, P1, 'hand')
        return t, g, es, ring

    async def test_beast_ring_attaches_two_to_ultra_beast(self):
        for prizes in (3, 4):
            with self.subTest(prizes=prizes):
                t, g, es, ring = self.ring_board(prizes)
                self.assertTrue(t.can(ring, 'UseTrainerCard'))
                await t.play(ring)
                self.assertEqual(len(t.board.attached_energies(g)), 2)
                self.assertEqual(len(t.board.attached_energies(t.active(P1))), 0)
                self.assertIn(ring, t.zone(P1, 'discard'))

    async def test_beast_ring_prize_boundaries(self):
        for prizes in (2, 5, 6):
            with self.subTest(prizes=prizes):
                t, g, es, ring = self.ring_board(prizes)
                self.assertFalse(t.can(ring, 'UseTrainerCard'))

    async def test_beast_ring_counts_opponent_prizes_not_mine(self):
        t, g, es, ring = self.ring_board(6)
        t.set_prizes(P1, 3)
        self.assertFalse(t.can(ring, 'UseTrainerCard'))

    async def test_beast_ring_only_basic_energy(self):
        t, g, es, ring = self.ring_board(4)
        special = t.deck(P1, ['ME3.GrowingGrassEnergy_86'])[0]
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return list(cards)[:count]
        t.picks = picks
        await t.play(ring)
        self.assertNotIn(special, seen)
        self.assertNotIn(special, list(g.children))

    async def test_beast_ring_needs_ultra_beast(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.set_prizes(P2, 4)
        t.deck(P1, [t.basic_energy(D)])
        ring = t.put(BEASTRING, P1, 'hand')
        self.assertFalse(t.can(ring, 'UseTrainerCard'))


if __name__ == '__main__':
    unittest.main()
