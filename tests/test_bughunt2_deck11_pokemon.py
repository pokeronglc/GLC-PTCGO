"""Bug hunt round 2, deck 11 (Fairy): Pokémon, checked against their printed
text, including the cases where they should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

Y, D, W = PokemonTypes.FAIRY, PokemonTypes.DARKNESS, PokemonTypes.WATER
FLABEBE, FLOETTE, FLORGES = 'SM12.Flabb_149', 'SM6.Floette_85', 'SM6.Florges_86'
CUTIEFLY, RIBOMBEE = 'SM3.Cutiefly_95', 'SM8.Ribombee_146'
SWIRLIX, SLURPUFF = 'SM12.Swirlix_153', 'XY4.Slurpuff_69'
MIME, XERNEAS, RALTS, KLEFKI = 'XY8.MrMime_97', 'SM4.Xerneas_73', 'SM8.Ralts_139', 'SM6.Klefki_89'
SABLEYE = 'SV2.Sableye_136'          # P2 attacker: Night Eyes (Asleep), Unseen Claw (20+)
GIBLE = 'BW6.Gible_86'               # Dragon attacker: Tackle 10
CROBAT = 'SWSH12.Crobat_105'         # Critical Bite: 30 to any 1 Pokémon
GUZMA = 'SM3.Guzma_115'
NEST = 'SV1.NestBall_181'


class Deck11Pokemon2(unittest.IsolatedAsyncioTestCase):
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

    def mine(self, t, spec, zone='active'):
        mon = t.put(spec, P1, zone)
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return mon

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Flabébé: Floral Invitation ---------------------------------------
    async def test_floral_invitation_up_to_two_fairy(self):
        t = self.table()
        flab = self.mine(t, FLABEBE)
        t.energy(flab, Y)
        t.deck(P1, [KLEFKI, RALTS, XERNEAS, SABLEYE])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        await t.attack(flab, 'Floral Invitation')
        self.assertEqual(seen['count'], 2)
        self.assertNotIn('Sableye', seen['names'])
        hand = self.hand_names(t)
        self.assertEqual(len(hand), 2)
        self.assertNotIn('Sableye', hand)

    # --- Florges: Wondrous Gift / Mist Guard ---------------------------------
    async def test_wondrous_gift_heads_item_to_top_once(self):
        t = self.table()
        florges = self.mine(t, FLORGES, 'bench')
        t.put(self.filler, P1, 'active')
        item = t.put(NEST, P1, 'discard')
        t.put(GUZMA, P1, 'discard')
        t.heads = True
        await t.use(florges, 'Wondrous Gift')
        self.assertIs(t.zone(P1, 'deck')[-1], item)
        self.assertIsNone(t.ability_offer(florges, 'Wondrous Gift'))

    async def test_wondrous_gift_tails_nothing(self):
        t = self.table()
        florges = self.mine(t, FLORGES)
        item = t.put(NEST, P1, 'discard')
        t.heads = False
        await t.use(florges, 'Wondrous Gift')
        self.assertIn(item, t.zone(P1, 'discard'))

    async def test_wondrous_gift_never_takes_a_supporter(self):
        t = self.table()
        florges = self.mine(t, FLORGES)
        sup = t.put(GUZMA, P1, 'discard')
        t.heads = True
        if t.ability_offer(florges, 'Wondrous Gift') is not None:
            await t.use(florges, 'Wondrous Gift')
        self.assertIn(sup, t.zone(P1, 'discard'))

    async def test_mist_guard_blocks_dragon_only(self):
        for attacker, title, energy, blocked in ((GIBLE, 'Tackle', W, True),
                                                 (SABLEYE, 'Unseen Claw', D, False)):
            t = self.table(attacker)
            t.energy(self.opp, energy)
            florges = self.mine(t, FLORGES)
            florges.set_attribute(AttrID.HP, 400)
            t.energy(florges, Y, 3)
            await t.attack(florges, 'Mist Guard')
            self.assertEqual(400 - t.hp(self.opp), 70)
            t.next_turn()
            await t.attack(self.opp, title, pid=P2)
            with self.subTest(attacker=attacker):
                self.assertEqual(t.hp(florges) == 400, blocked)

    # --- Ribombee: Mysterious Buzz ------------------------------------------
    # Was a bug (fixed Oct 10): BWLegacyPassive.blocks_trainer_effects has no branch for Ribombee's "done to your Fairy Pokémon in play"
    async def test_mysterious_buzz_guzma_cannot_pick_fairy(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        t.put(self.filler, P1, 'active')
        rib = self.mine(t, RIBOMBEE, 'bench')
        klefki = self.mine(t, KLEFKI, 'bench')
        plain = t.put(self.filler, P1, 'bench')
        t.next_turn()
        seen = []

        def pick(cands, prompt):
            seen.append(list(cands))
            return cands[0]
        t.pokemon = pick
        await t.play(t.put(GUZMA, P2, 'hand'), pid=P2)
        self.assertIs(t.active(P1), plain)
        self.assertIn(rib, t.zone(P1, 'bench'))
        self.assertIn(klefki, t.zone(P1, 'bench'))

    async def test_mysterious_buzz_not_while_active(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        self.mine(t, RIBOMBEE, 'active')
        klefki = self.mine(t, KLEFKI, 'bench')
        t.next_turn()
        t.pokemon = lambda c, p: klefki if klefki in c else c[0]
        await t.play(t.put(GUZMA, P2, 'hand'), pid=P2)
        self.assertIs(t.active(P1), klefki)

    async def test_mysterious_buzz_not_against_my_own_supporter(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        t.put(self.filler, P1, 'active')
        self.mine(t, RIBOMBEE, 'bench')
        klefki = self.mine(t, KLEFKI, 'bench')
        t.pokemon = lambda c, p: klefki if klefki in c else c[0]
        await t.play(t.put(GUZMA, P1, 'hand'))
        self.assertIs(t.active(P1), klefki)

    # --- Swirlix: Cotton Guard ----------------------------------------------
    async def test_cotton_guard_minus_10_next_turn_only(self):
        t = self.table(SABLEYE)
        t.energy(self.opp, D)
        swirlix = self.mine(t, SWIRLIX)
        swirlix.set_attribute(AttrID.HP, 400)
        t.energy(swirlix, Y)
        await t.attack(swirlix, 'Cotton Guard')
        t.next_turn()
        await t.attack(self.opp, 'Unseen Claw', pid=P2)
        self.assertEqual(400 - t.hp(swirlix), 10)
        t.next_turn(); t.next_turn()
        await t.attack(self.opp, 'Unseen Claw', pid=P2)
        self.assertEqual(400 - t.hp(swirlix), 30)

    # --- Slurpuff: Tasting / Light Pulse -------------------------------------
    # Was a bug (fixed Oct 10): bw_legacy_ability only knows "if this pokémon is in the active spot, draw 1 more"; Tasting's "is your Active Pokémon" wording draws 1
    async def test_tasting_draws_one_on_bench_two_active(self):
        for zone, drawn in (('bench', 1), ('active', 2)):
            t = self.table()
            if zone == 'bench':
                t.put(self.filler, P1, 'active')
            slurpuff = self.mine(t, SLURPUFF, zone)
            await t.use(slurpuff, 'Tasting')
            with self.subTest(zone=zone):
                self.assertEqual(len(t.zone(P1, 'hand')), drawn)
                self.assertIsNone(t.ability_offer(slurpuff, 'Tasting'))

    # Was a bug (fixed Oct 10): bw_legacy_attack protection_text misses "prevent all effects of your opponent's attacks" (Light Pulse does nothing)
    async def test_light_pulse_blocks_effects_not_damage(self):
        t = self.table(SABLEYE)
        t.energy(self.opp, D)
        slurpuff = self.mine(t, SLURPUFF)
        slurpuff.set_attribute(AttrID.HP, 400)
        t.energy(slurpuff, Y, 3)
        await t.attack(slurpuff, 'Light Pulse')
        self.assertEqual(400 - t.hp(self.opp), 60)
        t.next_turn()
        await t.attack(self.opp, 'Night Eyes', pid=P2)
        self.assertNotIn(ASLEEP, t.conditions(slurpuff))
        t.next_turn(); t.next_turn()
        await t.attack(self.opp, 'Night Eyes', pid=P2)
        self.assertIn(ASLEEP, t.conditions(slurpuff))

    # --- Floette: Swirling Petals --------------------------------------------
    async def test_swirling_petals_switches_both(self):
        t = self.table()
        opp_bench = t.put(self.filler, P2, 'bench')
        floette = self.mine(t, FLOETTE)
        t.energy(floette, Y)
        my_bench = t.put(self.filler, P1, 'bench')
        await t.attack(floette, 'Swirling Petals')
        self.assertIs(t.active(P2), opp_bench)
        self.assertIs(t.active(P1), my_bench)

    # Was a bug (fixed Oct 10): bw_legacy_attack self_switch ignores "If you do" and switches Floette even when no opponent switch happened
    async def test_swirling_petals_no_self_switch_without_opponent_bench(self):
        t = self.table()
        floette = self.mine(t, FLOETTE)
        t.energy(floette, Y)
        t.put(self.filler, P1, 'bench')
        await t.attack(floette, 'Swirling Petals')
        self.assertIs(t.active(P1), floette)

    # --- Mr. Mime: Bench Barrier / Juggling ---------------------------------
    async def test_bench_barrier_protects_my_bench_from_attacks(self):
        t = self.table(CROBAT)
        t.energy(self.opp, D, 3)
        t.put(self.filler, P1, 'active')
        self.mine(t, MIME, 'bench')
        victim = t.put(self.filler, P1, 'bench')
        before = t.hp(victim)
        t.next_turn()
        t.pokemon = lambda c, p: victim if victim in c else c[0]
        await t.attack(self.opp, 'Critical Bite', pid=P2)
        self.assertEqual(t.hp(victim), before)

    async def test_bench_barrier_not_for_active_or_opponent(self):
        t = self.table(CROBAT)
        t.energy(self.opp, D, 3)
        me = t.put(self.filler, P1, 'active')
        self.mine(t, MIME, 'bench')
        before = t.hp(me)
        t.next_turn()
        t.pokemon = lambda c, p: me if me in c else c[0]
        await t.attack(self.opp, 'Critical Bite', pid=P2)
        self.assertEqual(before - t.hp(me), 30)
        # my own attack into the opponent's bench is not stopped
        t2 = self.table()
        t2.put(MIME, P2, 'bench')
        crobat = t2.put(CROBAT, P1, 'active')
        t2.energy(crobat, D, 3)
        target = t2.put(self.filler, P2, 'bench')
        before = t2.hp(target)
        t2.pokemon = lambda c, p: target if target in c else c[0]
        await t2.attack(crobat, 'Critical Bite')
        self.assertEqual(before - t2.hp(target), 0)   # opponent's Mime protects THEIR bench

    async def test_juggling_counts_heads(self):
        for heads, dmg in ((True, 40), (False, 0)):
            t = self.table()
            mime = self.mine(t, MIME)
            t.energy(mime, Y, 2)
            t.heads = heads
            await t.attack(mime, 'Juggling')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Xerneas (CIN): Lead / Bright Horns -----------------------------------
    async def test_xerneas_lead(self):
        t = self.table()
        x = self.mine(t, XERNEAS)
        t.energy(x, Y)
        t.deck(P1, [GUZMA, NEST])
        await t.attack(x, 'Lead')
        self.assertEqual(self.hand_names(t), ['Guzma'])

    async def test_bright_horns_locked_next_turn(self):
        t = self.table()
        x = self.mine(t, XERNEAS)
        t.energy(x, Y, 3)
        await t.attack(x, 'Bright Horns')
        self.assertEqual(400 - t.hp(self.opp), 130)
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(x, 'Bright Horns'))
        self.assertIsNotNone(t.attack_offer(x, 'Lead'))
        t.next_turn(); t.next_turn()
        self.assertIsNotNone(t.attack_offer(x, 'Bright Horns'))

    # --- Ralts (LOT): Beckon --------------------------------------------------
    async def test_beckon_supporter_from_discard(self):
        t = self.table()
        ralts = self.mine(t, RALTS)
        t.energy(ralts, Y)
        sup = t.put(GUZMA, P1, 'discard')
        item = t.put(NEST, P1, 'discard')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is item] or cards[:count]
        await t.attack(ralts, 'Beckon')
        self.assertIn(sup, t.zone(P1, 'hand'))
        self.assertIn(item, t.zone(P1, 'discard'))

    # --- Klefki (FLI): Metal Sound / Fairy Lock --------------------------------
    async def test_metal_sound_confuses(self):
        t = self.table()
        k = self.mine(t, KLEFKI)
        t.energy(k, Y)
        await t.attack(k, 'Metal Sound')
        self.assertIn(CONFUSED, t.conditions(self.opp))

    async def test_fairy_lock_blocks_retreat_one_turn(self):
        t = self.table()
        k = self.mine(t, KLEFKI)
        t.energy(k, Y)
        t.energy(self.opp, W, 5)
        t.put(self.filler, P2, 'bench')
        await t.attack(k, 'Fairy Lock')
        self.assertEqual(400 - t.hp(self.opp), 20)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', pid=P2))


if __name__ == '__main__':
    unittest.main()
