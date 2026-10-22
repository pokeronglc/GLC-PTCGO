"""Bug hunt round 3, list 2: Pokémon, checked against their printed text
(unusual clauses only), including the cases where they should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

G, W, P, F = PokemonTypes.GRASS, PokemonTypes.WATER, PokemonTypes.PSYCHIC, PokemonTypes.FIGHTING
EXEGGCUTE, EXEGGUTOR = 'BW10.Exeggcute_102', 'BW9.Exeggutor_5'
GLOOM, VILEPLUME, ODDISH = 'SM10.Gloom_7', 'XY7.Vileplume_3', 'SV035.Oddish_43'
SHAYMIN = 'SV10.Shaymin_185'
VENONAT, VENOMOTH = 'SM10.Venonat_9', 'SV035.Venomoth_49'
ALOMOMOLA = 'ZSV10PT5.Alomomola_108'
MAGIKARP, GYARADOS = 'SM4.Magikarp_17', 'PGO.Gyarados_22'
MANAPHY = 'CZ.Manaphy_166'
DRIZZILE, INTELEON, SOBBLE = 'SWSH1.Drizzile_56', 'SWSH1.Inteleon_58', 'SWSH1.Sobble_54'
WIGLETT, WUGTRIO = 'SV1.Wiglett_206', 'SV045.Wugtrio_224'
ABRA, CLEFFA, DHELMISE = 'SV06.Abra_80', 'SV3.Cleffa_202', 'SM12.Dhelmise_98'
ELGYEM, FRILLISH, GOTHITA = 'ZSV10PT5.Elgyem_120', 'RSV10PT5.Frillish_126', 'SWSH3.Gothita_73'
MISDREAVUS, MISMAGIUS = 'SM4.Misdreavus_39', 'SM4.Mismagius_40'
TRUBBISH, GARBODOR = 'BW3.Trubbish_48', 'XY9.Garbodor_57'
EXCADRILL = 'BW2.Excadrill_57'          # Earthquake: 10 to each of YOUR Benched
GUZMA, NEST = 'SM3.Guzma_115', 'SV1.NestBall_181'
FLOAT = 'XY8.FloatStone_137'
GLIMWOOD = 'SWSH3.GlimwoodTangle_162'
AROMATIC = 'SWSH4.AromaticGrassEnergy_162'


def coins(*seq):
    """Patch the engine RNG (0 = heads) for flip_until_tails style runs."""
    it = iter(seq)
    return patch('spirit.game.session.effects.random.choice', lambda opts: next(it))


class Bughunt3B2Pokemon(unittest.IsolatedAsyncioTestCase):
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

    def new_opp_active(self, t, spec):
        """Bench the current opposing Active and put `spec` in the Active Spot."""
        old = t.active(P2)
        mon = t.put(spec, P2, 'bench')
        t.board.move_card(old.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(mon.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        return mon

    def name(self, card):
        return def_for(card.archetype_id).display_name

    # --- Exeggcute (PLB 102 = reprint of BW9 4): Propagation ---------------
    async def test_exeggcute_propagation_from_discard_only(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        egg = t.put(EXEGGCUTE, P1, 'discard')
        await t.use(egg, 'Propagation')
        self.assertIn(egg, t.zone(P1, 'hand'))
        self.assertIsNone(t.ability_offer(egg, 'Propagation'))     # not from hand

    # --- Exeggutor (PLF 5): Blockade ---------------------------------------
    async def test_blockade_stops_opponent_supporters_next_turn_only(self):
        t = self.table()
        exe = t.put(EXEGGUTOR, P1, 'active')
        t.energy(exe, G)
        t.put(self.filler, P1, 'bench')
        sup = t.put(GUZMA, P2, 'hand')
        item = t.put(NEST, P2, 'hand')
        await t.attack(exe, 'Blockade')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.next_turn()
        self.assertFalse(t.can(sup, 'UseTrainerCard', pid=P2))
        self.assertTrue(t.can(item, 'UseTrainerCard', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(sup, 'UseTrainerCard', pid=P2))

    async def test_blockade_does_not_stop_my_supporters(self):
        t = self.table()
        exe = t.put(EXEGGUTOR, P1, 'active')
        t.energy(exe, G)
        t.put(self.filler, P2, 'bench')
        await t.attack(exe, 'Blockade')
        t.next_turn(); t.next_turn()
        mine = t.put(GUZMA, P1, 'hand')
        self.assertTrue(t.can(mine, 'UseTrainerCard'))

    # --- Gloom (UNB 7): Irresistible Aroma ---------------------------------
    # Was a bug (fixed Oct 10): the shared interpreter only matches "...onto your opponent's Bench";
    # Gloom's "Put a Basic Pokémon you find there onto their Bench" does nothing.
    async def test_irresistible_aroma_heads_benches_opponent_basic(self):
        t = self.table()
        gloom = t.put(GLOOM, P1, 'active')
        basic = t.put(ODDISH, P2, 'hand')
        t.put(NEST, P2, 'hand')
        t.heads = True
        await t.use(gloom, 'Irresistible Aroma')
        self.assertIn(basic, t.zone(P2, 'bench'))
        self.assertIsNone(t.ability_offer(gloom, 'Irresistible Aroma'))   # once per turn

    async def test_irresistible_aroma_tails_does_nothing(self):
        t = self.table()
        gloom = t.put(GLOOM, P1, 'active')
        basic = t.put(ODDISH, P2, 'hand')
        t.heads = False
        await t.use(gloom, 'Irresistible Aroma')
        self.assertIn(basic, t.zone(P2, 'hand'))

    # Was a bug (fixed Oct 10): no legality gate for "if your opponent's Bench isn't full".
    async def test_irresistible_aroma_not_offered_when_opponent_bench_full(self):
        t = self.table()
        gloom = t.put(GLOOM, P1, 'active')
        for _ in range(5):
            t.put(self.filler, P2, 'bench')
        t.put(ODDISH, P2, 'hand')
        self.assertIsNone(t.ability_offer(gloom, 'Irresistible Aroma'))

    # --- Vileplume (AOR 3): Irritating Pollen ------------------------------
    async def test_irritating_pollen_locks_items_for_both_players_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(VILEPLUME, P1, 'bench')
        t.put(self.filler, P2, 'bench')
        mine = t.put(NEST, P1, 'hand')
        sup = t.put(GUZMA, P1, 'hand')
        self.assertFalse(t.can(mine, 'UseTrainerCard'))
        self.assertTrue(t.can(sup, 'UseTrainerCard'))              # Supporters fine
        t.next_turn()
        theirs = t.put(NEST, P2, 'hand')
        self.assertFalse(t.can(theirs, 'UseTrainerCard', pid=P2))

    async def test_items_playable_without_vileplume(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mine = t.put(NEST, P1, 'hand')
        self.assertTrue(t.can(mine, 'UseTrainerCard'))

    # --- Shaymin (DRI 185 = reprint of DRI 10): Flower Curtain -------------
    async def test_shaymin_flower_curtain_reprint_quick(self):
        for with_shaymin in (True, False):
            t = self.table()
            t.put(SHAYMIN if with_shaymin else self.filler, P1, 'active')
            benched = t.put(self.filler, P1, 'bench')
            self.big(benched)
            t.next_turn()
            iv = self.new_opp_active(t, 'SV05.IronValiant_79')   # Gemini Laser snipes
            t.energy(iv, P)
            t.pokemon = lambda c, p: benched if benched in c else c[0]
            await t.attack(iv, 'Gemini Laser', pid=P2)
            with self.subTest(with_shaymin=with_shaymin):
                self.assertEqual(t.hp(benched) == 400, with_shaymin)

    # --- Venonat (UNB 9): Radar Eyes ---------------------------------------
    async def test_radar_eyes_looks_at_seven_takes_one(self):
        t = self.table()
        ven = t.put(VENONAT, P1, 'active')
        t.energy(ven, G)
        seen = {}

        def picks(cards, count, prompt, display):
            seen['n'], seen['count'] = len(display or cards), count
            return list(cards)[:count]
        t.picks = picks
        await t.attack(ven, 'Radar Eyes')
        self.assertEqual(seen, {'n': 7, 'count': 1})
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P1, 'deck')), 29)

    # --- Venomoth (MEW 49): Perplexing Powder ------------------------------
    async def test_perplexing_powder_confuses_and_locks_items_next_turn(self):
        t = self.table()
        moth = t.put(VENOMOTH, P1, 'active')
        t.energy(moth, G)
        item = t.put(NEST, P2, 'hand')
        await t.attack(moth, 'Perplexing Powder')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertIn(CONFUSED, t.conditions(self.opp))
        t.next_turn()
        self.assertFalse(t.can(item, 'UseTrainerCard', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(item, 'UseTrainerCard', pid=P2))

    async def test_perplexing_powder_does_not_lock_my_items(self):
        t = self.table()
        moth = t.put(VENOMOTH, P1, 'active')
        t.energy(moth, G)
        await t.attack(moth, 'Perplexing Powder')
        t.next_turn(); t.next_turn()
        mine = t.put(NEST, P1, 'hand')
        self.assertTrue(t.can(mine, 'UseTrainerCard'))

    # --- Alomomola (BLK 108 = reprint of BLK 24): Gentle Fin ----------------
    async def test_gentle_fin_benches_small_basic_from_discard(self):
        t = self.table()
        alo = t.put(ALOMOMOLA, P1, 'active')
        small = t.put(ODDISH, P1, 'discard')          # 60 HP
        big = t.put(self.filler, P1, 'discard')       # too much HP
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'] = list(cards)
            return [c for c in cards if c is small][:count]
        t.picks = picks
        await t.use(alo, 'Gentle Fin')
        self.assertIn(small, t.zone(P1, 'bench'))
        self.assertNotIn(big, seen.get('cards', []))
        self.assertIsNone(t.ability_offer(alo, 'Gentle Fin'))

    async def test_gentle_fin_not_from_bench_or_for_big_basic(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        alo = t.put(ALOMOMOLA, P1, 'bench')
        t.put(ODDISH, P1, 'discard')
        self.assertIsNone(t.ability_offer(alo, 'Gentle Fin'))
        t2 = self.table()
        alo2 = t2.put(ALOMOMOLA, P1, 'active')
        t2.put(self.filler, P1, 'discard')
        if t2.ability_offer(alo2, 'Gentle Fin'):
            await t2.use(alo2, 'Gentle Fin')
        self.assertEqual(t2.zone(P1, 'bench'), [])

    # --- Magikarp (CIN 17): Submerge / Waterfall Evolution -----------------
    async def test_submerge_prevents_my_own_attack_damage_on_bench(self):
        t = self.table()
        ex = t.put(EXCADRILL, P1, 'active')
        t.energy(ex, F, 3)
        karp = t.put(MAGIKARP, P1, 'bench')
        other = t.put(self.filler, P1, 'bench')
        await t.attack(ex, 'Earthquake')
        self.assertEqual(t.damage(karp), 0)
        self.assertEqual(t.damage(other), 10)

    async def test_submerge_not_while_active(self):
        t = self.table()
        karp = t.put(MAGIKARP, P1, 'active')
        t.next_turn()
        fr = self.new_opp_active(t, FRILLISH)
        t.energy(fr, P)
        await t.attack(fr, 'Oceanic Gloom', pid=P2)
        self.assertEqual(t.hp(karp), 10)

    async def test_waterfall_evolution_evolves_from_deck(self):
        t = self.table()
        karp = t.put(MAGIKARP, P1, 'active')
        t.energy(karp, W, 3)
        gyara = t.deck(P1, [GYARADOS])[0]
        await t.attack(karp, 'Waterfall Evolution')
        self.assertIs(t.active(P1), gyara)
        self.assertEqual(self.name(t.active(P1)), 'Gyarados')
        self.assertIn(karp, gyara.children)

    async def test_waterfall_evolution_whiffs_without_evolution(self):
        t = self.table()
        karp = t.put(MAGIKARP, P1, 'active')
        t.energy(karp, W, 3)
        t.deck(P1, [DRIZZILE])
        await t.attack(karp, 'Waterfall Evolution')
        self.assertIs(t.active(P1), karp)

    # --- Gyarados (PGO 22): Wreak Havoc / Wild Splash ----------------------
    async def test_wreak_havoc_two_cards_per_heads(self):
        t = self.table()
        gy = t.put(GYARADOS, P1, 'active')
        t.energy(gy, W)
        with coins(0, 0, 1):
            await t.attack(gy, 'Wreak Havoc')
        self.assertEqual(len(t.zone(P2, 'discard')), 4)
        self.assertEqual(len(t.zone(P1, 'discard')), 0)

    async def test_wreak_havoc_immediate_tails_mills_nothing(self):
        t = self.table()
        gy = t.put(GYARADOS, P1, 'active')
        t.energy(gy, W)
        with coins(1):
            await t.attack(gy, 'Wreak Havoc')
        self.assertEqual(len(t.zone(P2, 'discard')), 0)

    async def test_wild_splash_mills_five_of_mine(self):
        t = self.table()
        gy = t.put(GYARADOS, P1, 'active')
        t.energy(gy, W, 4)
        await t.attack(gy, 'Wild Splash')
        self.assertEqual(400 - t.hp(self.opp), 230)
        self.assertEqual(len(t.zone(P1, 'discard')), 5)
        self.assertEqual(len(t.zone(P2, 'discard')), 0)

    # --- Manaphy (CRZ GG06 = reprint of BRS 41): Wave Veil ------------------
    async def test_manaphy_gallery_wave_veil_quick(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        man = t.put(MANAPHY, P1, 'bench')
        self.assertEqual(def_for(man.archetype_id).abilities[0].title, 'Wave Veil')
        from spirit.game.card_effects.pokemon import WaveVeilPassive
        self.assertIsInstance(def_for(man.archetype_id).abilities[0].passive, WaveVeilPassive)

    # --- Drizzile / Inteleon (SHF SV026/SV027 = SSH 56/58; not separately in
    #     the database, the SSH scripts are used) -----------------------------
    async def test_drizzile_shady_dealings_quick(self):
        t = self.table()
        sob = t.put(SOBBLE, P1, 'active')
        t.state.entered_play_turn[sob.entity_id] = 0
        driz = t.put(DRIZZILE, P1, 'hand')
        g = t.deck(P1, [GUZMA])[0]
        t.picks = lambda cards, count, prompt, display: [g]
        await t.play(driz, targets=[sob.entity_id])
        self.assertIn('Guzma', t.names(t.zone(P1, 'hand')))

    async def test_inteleon_shady_dealings_two_trainers_quick(self):
        t = self.table()
        driz = t.put(DRIZZILE, P1, 'active')
        intel = t.put(INTELEON, P1, 'hand')
        wanted = t.deck(P1, [GUZMA, NEST])
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in wanted][:count]
        await t.play(intel, targets=[driz.entity_id])
        hand = t.names(t.zone(P1, 'hand'))
        self.assertEqual(hand, ['Guzma', 'Nest Ball'])

    # --- Wiglett (SVI 206 = reprint of SVI 55): Twisting Strike -------------
    async def test_twisting_strike_heads_blocks_damage_and_effects(self):
        t = self.table()
        wig = t.put(WIGLETT, P1, 'active')
        t.energy(wig, W)
        t.heads = True
        await t.attack(wig, 'Twisting Strike')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.next_turn()
        moth = self.new_opp_active(t, VENOMOTH)
        t.energy(moth, G)
        await t.attack(moth, 'Perplexing Powder', pid=P2)
        self.assertEqual(t.damage(wig), 0)
        self.assertNotIn(CONFUSED, t.conditions(wig))

    async def test_twisting_strike_tails_no_protection(self):
        t = self.table()
        wig = t.put(WIGLETT, P1, 'active')
        self.big(wig)
        t.energy(wig, W)
        t.heads = False
        await t.attack(wig, 'Twisting Strike')
        t.next_turn()
        moth = self.new_opp_active(t, VENOMOTH)
        t.energy(moth, G)
        await t.attack(moth, 'Perplexing Powder', pid=P2)
        self.assertEqual(400 - t.hp(wig), 30)
        self.assertIn(CONFUSED, t.conditions(wig))

    # --- Wugtrio (PAF 224 = reprint of SVI 57): Undersea Tunnel ------------
    async def test_undersea_tunnel_mills_opponent_three_per_heads(self):
        for pattern, milled in (((True, False, True), 6), ((False, False, False), 0)):
            t = self.table()
            wug = t.put(WUGTRIO, P1, 'active')
            t.energy(wug, W, 3)
            it = iter(pattern)
            t.heads = lambda title: next(it)
            await t.attack(wug, 'Undersea Tunnel')
            with self.subTest(pattern=pattern):
                self.assertEqual(len(t.zone(P2, 'discard')), milled)
                self.assertEqual(len(t.zone(P1, 'discard')), 0)

    # --- Abra (TWM 80): Teleporter -----------------------------------------
    async def test_teleporter_shuffles_abra_and_attachments_into_deck(self):
        t = self.table()
        abra = t.put(ABRA, P1, 'active')
        e = t.energy(abra, P)
        bench = t.put(self.filler, P1, 'bench')
        await t.use(abra, 'Teleporter')
        deck = t.zone(P1, 'deck')
        self.assertIn(abra, deck)
        self.assertIn(e, deck)
        self.assertIs(t.active(P1), bench)

    async def test_teleporter_not_from_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        abra = t.put(ABRA, P1, 'bench')
        self.assertIsNone(t.ability_offer(abra, 'Teleporter'))

    # --- Cleffa (OBF 202 = reprint of OBF 80): Grasping Draw ---------------
    async def test_cleffa_grasping_draw_to_seven_quick(self):
        t = self.table()
        cl = t.put(CLEFFA, P1, 'active')
        for _ in range(3):
            t.put(NEST, P1, 'hand')
        await t.attack(cl, 'Grasping Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    # --- Dhelmise (CEC 98): Seaweed Grab / Buster Swing --------------------
    async def test_seaweed_grab_takes_a_trainer_only(self):
        t = self.table()
        dh = t.put(DHELMISE, P1, 'active')
        t.energy(dh, P)
        tr = t.put(GUZMA, P1, 'discard')
        mon = t.put(ODDISH, P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'] = list(cards)
            return [c for c in cards if c is tr][:count]
        t.picks = picks
        await t.attack(dh, 'Seaweed Grab')
        self.assertIn(tr, t.zone(P1, 'hand'))
        self.assertNotIn(mon, seen.get('cards', []))
        self.assertIn(mon, t.zone(P1, 'discard'))

    async def test_buster_swing_ignores_resistance(self):
        t = self.table()
        dh = t.put(DHELMISE, P1, 'active')
        t.energy(dh, P, 3)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, dh.get_attribute(AttrID.POKEMON_TYPES)[0])
        await t.attack(dh, 'Buster Swing')
        self.assertEqual(400 - t.hp(self.opp), 100)

    async def test_resistance_control_applies_to_other_psychic_attack(self):
        t = self.table()
        el = t.put(ELGYEM, P1, 'active')
        t.energy(el, P, 3)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, el.get_attribute(AttrID.POKEMON_TYPES)[0])
        await t.attack(el, 'Beam')
        self.assertLess(400 - t.hp(self.opp), 40)

    # --- Elgyem (BLK 120 = reprint of BLK 40): Slight Shift -----------------
    async def test_slight_shift_bench_to_active(self):
        t = self.table()
        el = t.put(ELGYEM, P1, 'active')
        t.energy(el, P)
        b = t.put(self.filler, P2, 'bench')
        e = t.energy(b, W)
        await t.attack(el, 'Slight Shift')
        self.assertIn(e, self.opp.children)

    # Was a bug (fixed Oct 10): Slight Shift only moves Benched -> Active; the printed text allows
    # moving from any of the opponent's Pokémon to another (e.g. Active -> Bench).
    async def test_slight_shift_active_to_bench(self):
        t = self.table()
        el = t.put(ELGYEM, P1, 'active')
        t.energy(el, P)
        b = t.put(self.filler, P2, 'bench')
        e = t.energy(self.opp, W)
        t.pokemon = lambda c, p: self.opp if self.opp in c else c[0]
        await t.attack(el, 'Slight Shift')
        self.assertIn(e, b.children)

    # --- Frillish (WHT 126 = reprint of WHT 44): Oceanic Gloom --------------
    async def test_oceanic_gloom_locks_opponent_items_next_turn(self):
        t = self.table()
        fr = t.put(FRILLISH, P1, 'active')
        t.energy(fr, P)
        item = t.put(NEST, P2, 'hand')
        await t.attack(fr, 'Oceanic Gloom')
        self.assertEqual(400 - t.hp(self.opp), 20)
        t.next_turn()
        self.assertFalse(t.can(item, 'UseTrainerCard', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(item, 'UseTrainerCard', pid=P2))

    # --- Gothita (DAA 73): Fortunate Eye -----------------------------------
    async def test_fortunate_eye_reorders_opponent_top_five(self):
        t = self.table()
        go = t.put(GOTHITA, P1, 'active')
        t.energy(go, P)
        seen = {}

        async def chooser(pid, src, cards, count, minimum=None, prompt='', ordered=False, **k):
            seen['pid'], seen['n'] = pid, len(cards)
            seen['owners'] = {c.owning_player_id for c in cards}
            return [c.entity_id for c in reversed(cards)]
        before = list(reversed(t.zone(P2, 'deck')))[:5]   # top first
        with patch.object(t.session, 'prompt_card_chooser', chooser):
            await t.attack(go, 'Fortunate Eye')
        self.assertEqual(seen['pid'], P1)
        self.assertEqual(seen['n'], 5)
        self.assertEqual(seen['owners'], {P2})
        after = list(reversed(t.zone(P2, 'deck')))[:5]
        self.assertEqual(after, list(reversed(before)))

    # --- Misdreavus (CIN 39): Confuse Ray (plain; sweep covers) -------------
    async def test_misdreavus_confuse_ray_quick(self):
        t = self.table()
        m = t.put(MISDREAVUS, P1, 'active')
        t.energy(m, P)
        await t.attack(m, 'Confuse Ray')
        self.assertIn(CONFUSED, t.conditions(self.opp))

    # --- Mismagius (CIN 40): Chaos Wheel / Dark Arts -----------------------
    async def test_chaos_wheel_blocks_tool_special_energy_stadium_only(self):
        t = self.table()
        mm = t.put(MISMAGIUS, P1, 'active')
        t.energy(mm, P)
        tool = t.put(FLOAT, P2, 'hand')
        special = t.put(AROMATIC, P2, 'hand')
        stadium = t.put(GLIMWOOD, P2, 'hand')
        item = t.put(NEST, P2, 'hand')
        await t.attack(mm, 'Chaos Wheel')
        self.assertEqual(400 - t.hp(self.opp), 30)
        t.next_turn()
        self.assertFalse(t.can(tool, None, pid=P2))
        self.assertFalse(t.can(special, None, pid=P2))
        self.assertFalse(t.can(stadium, None, pid=P2))
        self.assertTrue(t.can(item, 'UseTrainerCard', pid=P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(tool, None, pid=P2))
        self.assertTrue(t.can(stadium, None, pid=P2))

    async def test_dark_arts_counts_opponent_hand(self):
        for n in (0, 4):
            t = self.table()
            mm = t.put(MISMAGIUS, P1, 'active')
            t.energy(mm, P, 3)
            for _ in range(n):
                t.put(NEST, P2, 'hand')
            for _ in range(2):
                t.put(NEST, P1, 'hand')              # my hand must not count
            await t.attack(mm, 'Dark Arts')
            with self.subTest(n=n):
                self.assertEqual(400 - t.hp(self.opp), 20 * n)

    # --- Trubbish (NVI 48): Garbage Collection ------------------------------
    async def test_garbage_collection_puts_chosen_card_on_top(self):
        t = self.table()
        tr = t.put(TRUBBISH, P1, 'active')
        t.energy(tr, P)
        t.put(NEST, P1, 'discard')
        target = t.put(GUZMA, P1, 'discard')
        t.picks = lambda cards, count, prompt, display: [target]
        await t.attack(tr, 'Garbage Collection')
        self.assertIs(t.zone(P1, 'deck')[-1], target)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_garbage_collection_empty_discard_is_harmless(self):
        t = self.table()
        tr = t.put(TRUBBISH, P1, 'active')
        t.energy(tr, P)
        await t.attack(tr, 'Garbage Collection')
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Garbodor (BKP 57 = XY9 57; ME4 57 is a different card): Garbotoxin --
    async def test_garbotoxin_needs_a_tool_quick(self):
        t = self.table()
        alo = t.put(ALOMOMOLA, P1, 'active')
        t.put(ODDISH, P1, 'discard')
        garb = t.put(GARBODOR, P2, 'bench')
        self.assertIsNotNone(t.ability_offer(alo, 'Gentle Fin'))
        t.attach(FLOAT, garb)
        self.assertIsNone(t.ability_offer(alo, 'Gentle Fin'))


if __name__ == '__main__':
    unittest.main()
