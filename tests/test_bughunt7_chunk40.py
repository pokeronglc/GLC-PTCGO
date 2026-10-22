"""Bug hunt round 7, chunk 40: Impidimp, Plusle, Raikou, Chansey, Blissey,
Slakoth, Vigoroth, Slaking, Komala, Galarian Zigzagoon, Ceruledge, Ethan's
Magcargo, Ethan's Cyndaquil, Ethan's Quilava, Ethan's Adventure -- each
checked against its printed text, including the cases where it should NOT
work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, ASLEEP, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session import game_session as gs_mod
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, LIGHT, DARK = (PokemonTypes.FIRE, PokemonTypes.WATER,
                            PokemonTypes.LIGHTNING, PokemonTypes.DARKNESS)

IMPIDIMP = 'SWSH9.Impidimp_92'
PLUSLE, MINUN = 'BW11.Plusle_47', 'BW11.Minun_48'
RAIKOU = 'XY8.Raikou_55'
CHANSEY, BLISSEY = 'SV035.Chansey_113', 'SV1.Blissey_145'
SLAKOTH, VIGOROTH, SLAKING = 'SV2.Slakoth_160', 'SV2.Vigoroth_161', 'SV2.Slaking_162'
KOMALA = 'SV09.Komala_129'
ZIGZAGOON = 'SWSH1.GalarianZigzagoon_117'
CERULEDGE = 'ME2.Ceruledge_20'
MAGCARGO = 'SV10.EthansMagcargo_36'
CYNDAQUIL, QUILAVA = 'SV10.EthansCyndaquil_32', 'SV10.EthansQuilava_33'
ADVENTURE = 'SV10.EthansAdventure_165'
SLUGMA = 'ME2PT5.EthansSlugma_23'
CHARCADET = 'ME2.Charcadet_19'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk40(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None, hp=400):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.big(self.opp, hp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None, base=400):
        return base - (target or self.opp).get_attribute(AttrID.HP)

    def set_asleep(self, p):
        p.set_attribute(AttrID.SPECIAL_CONDITIONS, [ASLEEP])

    # --- Impidimp BRS 92: Call for Family --------------------------------------
    async def test_impidimp_call_for_family_benches_a_basic(self):
        t = self.table()
        imp = self.mine(t, IMPIDIMP, DARK, 1)
        t.deck(P1, [VIGOROTH, CHARCADET])
        await t.attack(imp, 'Call for Family')
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Charcadet'])
        self.assertEqual(self.dealt(), 0)

    async def test_impidimp_call_for_family_never_benches_a_stage1(self):
        t = self.table()
        imp = self.mine(t, IMPIDIMP, DARK, 1)
        t.deck(P1, [VIGOROTH])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.attack(imp, 'Call for Family')
        self.assertEqual(t.zone(P1, 'bench'), [])
        self.assertNotIn('Vigoroth', [name(c) for c in seen])

    # --- Galarian Zigzagoon SSH 117: Headbutt Tantrum --------------------------
    async def test_zigzagoon_played_from_hand_places_one_counter(self):
        t = self.table()
        self.mine(t, self.filler)
        benched_opp = self.mine(t, self.filler, zone='bench', hp=300, pid=P2)
        zig = t.put(ZIGZAGOON, P1, 'hand')
        with patch.object(t.session, 'prompt_damage_counter_placement',
                          create=True) as placer:
            async def place(pid, src, pool, count, prompt=''):
                self.assertEqual(count, 1)
                return {benched_opp.entity_id: 1}
            placer.side_effect = place
            await t.play(zig)
        self.assertIn(zig, t.zone(P1, 'bench'))
        self.assertEqual(300 - t.hp(benched_opp), 10)

    async def test_zigzagoon_benched_by_effect_does_not_trigger(self):
        t = self.table()
        imp = self.mine(t, IMPIDIMP, DARK, 1)
        t.deck(P1, [ZIGZAGOON])
        calls = []

        async def place(*a, **k):
            calls.append(a)
            return {self.opp.entity_id: 1}
        with patch.object(t.session, 'prompt_damage_counter_placement', place, create=True):
            await t.attack(imp, 'Call for Family')
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Galarian Zigzagoon'])
        self.assertEqual(calls, [])
        self.assertEqual(self.dealt(), 0)

    async def test_zigzagoon_declined_places_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        zig = t.put(ZIGZAGOON, P1, 'hand')
        t.yes = False
        calls = []

        async def place(*a, **k):
            calls.append(a)
            return {self.opp.entity_id: 1}
        with patch.object(t.session, 'prompt_damage_counter_placement', place, create=True):
            await t.play(zig)
        self.assertEqual(calls, [])
        self.assertEqual(self.dealt(), 0)

    # --- Plusle LTR 47: Tag Draw ----------------------------------------------
    async def test_plusle_tag_draw_without_minun_draws_4(self):
        t = self.table()
        plusle = self.mine(t, PLUSLE, WATER, 1)
        self.clear_hand(t)
        for _ in range(6):
            t.put(self.item, P1, 'hand')
        await t.attack(plusle, 'Tag Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    async def test_plusle_tag_draw_with_minun_on_bench_draws_8(self):
        t = self.table()
        plusle = self.mine(t, PLUSLE, WATER, 1)
        self.mine(t, MINUN, zone='bench')
        self.clear_hand(t)
        t.put(self.item, P1, 'hand')
        await t.attack(plusle, 'Tag Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 8)

    async def test_plusle_tag_draw_minun_in_hand_does_not_count(self):
        t = self.table()
        plusle = self.mine(t, PLUSLE, WATER, 1)
        self.clear_hand(t)
        t.put(MINUN, P1, 'hand')
        await t.attack(plusle, 'Tag Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    async def test_plusle_positive_ion_heads_and_tails(self):
        for heads, want in ((True, 30), (False, 20)):
            t = self.table()
            plusle = self.mine(t, PLUSLE, LIGHT, 1)
            t.heads = heads
            await t.attack(plusle, 'Positive Ion')
            self.assertEqual(self.dealt(), want, heads)

    # --- Raikou BKT 55 --------------------------------------------------------
    async def raikou_hit(self, kinds):
        t = Table(self)
        raikou = self.mine(t, RAIKOU, hp=300)
        for k in kinds:
            t.energy(raikou, k, 1)
        attacker = t.put(self.filler, P2, 'active')
        self.big(attacker)
        t.energy(attacker, WATER, 3)
        t.next_turn()
        await t.attack(attacker, 'Heavy Impact', pid=P2)
        return 300 - t.hp(raikou)

    async def test_raikou_shining_body_reduces_with_lightning(self):
        self.assertEqual(await self.raikou_hit([LIGHT]), 60)

    async def test_raikou_shining_body_no_reduction_without_lightning(self):
        self.assertEqual(await self.raikou_hit([WATER]), 80)

    async def test_raikou_thunder_lance_counts_only_lightning(self):
        t = self.table()
        raikou = self.mine(t, RAIKOU)
        t.energy(raikou, LIGHT, 2)
        t.energy(raikou, WATER, 1)
        await t.attack(raikou, 'Thunder Lance')
        self.assertEqual(self.dealt(), 90)

    # --- Chansey MEW 113: Lucky Bonus -----------------------------------------
    async def lucky_board(self, bench_count, heads):
        t = self.table(hp=10)
        bench_opp = self.mine(t, self.filler, zone='bench', pid=P2)
        attacker = self.mine(t, SLAKING, WATER, 3, hp=300)
        for _ in range(bench_count):
            self.mine(t, self.filler, zone='bench')
        prizes = t.board.find_player_area(P1, 'prizePile')
        prizes.remove_child(prizes.children[0])
        chansey = t.put(CHANSEY, P1, 'prizes')
        prizes.children.remove(chansey)       # the auto prize pick takes the first card
        prizes.children.insert(0, chansey)
        t.heads = heads

        async def pick(player_id, prize_ids, count, *a, **k):
            ids = [chansey.entity_id] + [i for i in prize_ids if i != chansey.entity_id]
            return ids[:count]
        t.pokemon = lambda c, p: bench_opp
        rnd = [0 if heads else 1] * 10
        with patch.object(t.session, '_prompt_prize_pick', pick), \
                patch.object(gs_mod.random, 'choice', lambda seq: rnd.pop()):
            await t.attack(attacker, "Slacker's Headstrike")
        return t, chansey

    async def test_chansey_lucky_bonus_bench_and_heads_extra_prize(self):
        t, chansey = await self.lucky_board(0, True)
        self.assertNotIn(self.opp, t.board.pokemon_in_play(P2))
        self.assertIn(chansey, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 4)

    async def test_chansey_lucky_bonus_tails_no_extra_prize(self):
        t, chansey = await self.lucky_board(0, False)
        self.assertIn(chansey, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 5)

    async def test_chansey_lucky_bonus_full_bench_stays_in_hand(self):
        t, chansey = await self.lucky_board(5, True)
        self.assertIn(chansey, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 5)

    # --- Blissey SVI 145 ------------------------------------------------------
    async def test_blissey_busybody_nurse_clears_active_conditions(self):
        t = self.table()
        active = self.mine(t, self.filler)
        active.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED, CONFUSED])
        blissey = self.mine(t, BLISSEY, zone='bench')
        await t.use(blissey, 'Busybody Nurse')
        self.assertEqual(t.conditions(active), set())
        self.assertIsNone(t.ability_offer(blissey, 'Busybody Nurse'))   # once per turn

    async def test_blissey_busybody_nurse_not_offered_without_conditions(self):
        t = self.table()
        self.mine(t, self.filler)
        blissey = self.mine(t, BLISSEY, zone='bench')
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        self.assertIsNone(t.ability_offer(blissey, 'Busybody Nurse'))
        self.assertEqual(t.conditions(self.opp), {POISONED})

    async def test_blissey_happy_cyclone_moves_all_energy_to_bench(self):
        t = self.table()
        blissey = self.mine(t, BLISSEY, WATER, 2)
        t.energy(blissey, FIRE, 1)
        bench = self.mine(t, self.filler, zone='bench')
        t.pokemon = lambda c, p: bench
        await t.attack(blissey, 'Happy Cyclone')
        self.assertEqual(self.dealt(), 150)
        self.assertEqual(t.board.attached_energies(blissey), [])
        self.assertEqual(len(t.board.attached_energies(bench)), 3)

    # --- Slakoth PAL 160: Yawn ------------------------------------------------
    async def test_slakoth_yawn_puts_opponent_asleep(self):
        t = self.table()
        slakoth = self.mine(t, SLAKOTH, WATER, 2)
        await t.attack(slakoth, 'Yawn')
        self.assertEqual(t.conditions(self.opp), {ASLEEP})
        self.assertEqual(t.conditions(slakoth), set())
        self.assertEqual(self.dealt(), 0)

    # --- Vigoroth PAL 161: Sharp Claws ----------------------------------------
    async def test_vigoroth_sharp_claws_heads_and_tails(self):
        for heads, want in ((True, 120), (False, 60)):
            t = self.table()
            vig = self.mine(t, VIGOROTH, WATER, 3)
            t.heads = heads
            await t.attack(vig, 'Sharp Claws')
            self.assertEqual(self.dealt(), want, heads)

    # --- Slaking PAL 162 ------------------------------------------------------
    async def test_slaking_headstrike_240_and_self_asleep(self):
        t = self.table()
        slaking = self.mine(t, SLAKING, WATER, 3)
        await t.attack(slaking, "Slacker's Headstrike")
        self.assertEqual(self.dealt(), 240)
        self.assertEqual(t.conditions(slaking), {ASLEEP})
        self.assertEqual(t.conditions(self.opp), set())

    async def sleep_check(self, spec, flips):
        t = self.table()
        p = self.mine(t, spec)
        self.set_asleep(p)
        seq = list(flips)
        used = []

        def choice(options):
            used.append(1)
            return seq.pop(0) if seq else 1
        with patch.object(gs_mod.random, 'choice', choice):
            await t.checkup()
        return t, p, len(used)

    async def test_slaking_stir_and_snooze_flips_two_heads_heads_wakes(self):
        t, p, n = await self.sleep_check(SLAKING, [0, 0])
        self.assertEqual(n, 2)
        self.assertEqual(t.conditions(p), set())

    async def test_slaking_stir_and_snooze_one_tails_stays_asleep(self):
        t, p, n = await self.sleep_check(SLAKING, [0, 1])
        self.assertEqual(n, 2)
        self.assertEqual(t.conditions(p), {ASLEEP})

    async def test_slaking_stir_and_snooze_benched_slaking_does_not_affect_active(self):
        t = self.table()
        p = self.mine(t, self.filler)
        self.mine(t, SLAKING, zone='bench')
        self.set_asleep(p)
        used = []

        def choice(options):
            used.append(1)
            return 0
        with patch.object(gs_mod.random, 'choice', choice):
            await t.checkup()
        self.assertEqual(len(used), 1)
        self.assertEqual(t.conditions(p), set())

    # --- Komala JTG 129: Slumbering Smack -------------------------------------
    # BUG: "During your next turn, attacks used by this Pokémon do 100 more damage" is never registered (no parser for this wording)
    async def test_komala_both_asleep_then_100_more_next_turn(self):
        t = self.table()
        komala = self.mine(t, KOMALA, WATER, 1)
        await t.attack(komala, 'Slumbering Smack')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.conditions(komala), {ASLEEP})
        self.assertEqual(t.conditions(self.opp), {ASLEEP})
        t.next_turn()
        t.next_turn()
        komala.set_attribute(AttrID.SPECIAL_CONDITIONS, [])    # woke up
        self.opp.set_attribute(AttrID.HP, 400)
        await t.attack(komala, 'Slumbering Smack')
        self.assertEqual(self.dealt(), 130)

    async def test_komala_bonus_expires_after_next_turn(self):
        t = self.table()
        komala = self.mine(t, KOMALA, WATER, 1)
        await t.attack(komala, 'Slumbering Smack')
        for _ in range(4):
            t.next_turn()
        komala.set_attribute(AttrID.SPECIAL_CONDITIONS, [])
        self.opp.set_attribute(AttrID.HP, 400)
        await t.attack(komala, 'Slumbering Smack')
        self.assertEqual(self.dealt(), 30)

    # --- Ceruledge PFL 20: Infernal Slash -------------------------------------
    async def test_ceruledge_discards_4_basic_fire_for_220(self):
        t = self.table()
        ced = self.mine(t, CERULEDGE, FIRE, 1)
        self.clear_hand(t)
        fires = [t.put(t.basic_energy(FIRE), P1, 'hand') for _ in range(5)]
        await t.attack(ced, 'Infernal Slash')
        self.assertEqual(self.dealt(), 220)
        self.assertEqual(len([c for c in fires if c in t.zone(P1, 'discard')]), 4)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    async def test_ceruledge_with_3_fire_does_nothing(self):
        t = self.table()
        ced = self.mine(t, CERULEDGE, FIRE, 1)
        self.clear_hand(t)
        for _ in range(3):
            t.put(t.basic_energy(FIRE), P1, 'hand')
        t.put(t.basic_energy(WATER), P1, 'hand')
        await t.attack(ced, 'Infernal Slash')
        self.assertEqual(self.dealt(), 0)

    # --- Ethan's Magcargo DRI 36 ----------------------------------------------
    async def test_magcargo_melt_away_free_retreat_without_energy(self):
        t = self.table()
        mag = self.mine(t, MAGCARGO)
        self.assertEqual(t.retreat(mag), 0)
        t.energy(mag, FIRE, 1)
        self.assertEqual(t.retreat(mag), 3)

    async def test_magcargo_lava_burst_discard_chosen_fire(self):
        t = self.table()
        mag = self.mine(t, MAGCARGO, FIRE, 4)
        t.energy(mag, WATER, 1)
        t.picks = lambda cards, count, prompt, display: cards[:2]
        await t.attack(mag, 'Lava Burst')
        self.assertEqual(self.dealt(), 140)
        left = t.board.attached_energies(mag)
        self.assertEqual(len(left), 3)

    async def test_magcargo_lava_burst_only_fire_offered(self):
        t = self.table()
        mag = self.mine(t, MAGCARGO, FIRE, 3)
        water = t.energy(mag, WATER, 2)
        t.picks = lambda cards, count, prompt, display: cards
        await t.attack(mag, 'Lava Burst')
        self.assertEqual(self.dealt(), 210)
        self.assertTrue(all(w in t.attached(mag) for w in water))

    # --- Ethan's Cyndaquil DRI 32: Ember --------------------------------------
    async def test_cyndaquil_ember_discards_one_energy(self):
        t = self.table()
        cyn = self.mine(t, CYNDAQUIL, FIRE, 2)
        await t.attack(cyn, 'Ember')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(len(t.board.attached_energies(cyn)), 1)

    # --- Ethan's Quilava DRI 33: Bonded by the Journey ------------------------
    async def test_quilava_finds_ethans_adventure(self):
        t = self.table()
        self.mine(t, self.filler)
        qui = self.mine(t, QUILAVA, zone='bench')
        t.deck(P1, [ADVENTURE, CYNDAQUIL])
        self.clear_hand(t)
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.use(qui, 'Bonded by the Journey')
        self.assertEqual(t.names(t.zone(P1, 'hand')), ["Ethan's Adventure"])
        self.assertNotIn("Ethan's Cyndaquil", [name(c) for c in seen])
        self.assertIsNone(t.ability_offer(qui, 'Bonded by the Journey'))

    # --- Ethan's Adventure DRI 165 --------------------------------------------
    async def test_ethans_adventure_takes_ethans_pokemon_and_basic_fire(self):
        t = self.table()
        self.mine(t, self.filler)
        t.deck(P1, [CYNDAQUIL, SLUGMA, t.basic_energy(FIRE), CHARCADET,
                    t.basic_energy(WATER)])
        card = t.put(ADVENTURE, P1, 'hand')
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return cards[:count]
        t.picks = picks
        await t.play(card)
        hand = [c for c in t.zone(P1, 'hand') if c is not card]
        self.assertEqual(len(hand), 3)
        names = [name(c) for c in seen]
        self.assertNotIn('Charcadet', names)
        self.assertIn("Ethan's Cyndaquil", names)
        hand_names = sorted(name(c) or '?' for c in hand)
        self.assertNotIn('Charcadet', hand_names)
        water_guid = t.basic_energy(WATER).guid.lower()
        self.assertNotIn(water_guid, [def_for(c.archetype_id).guid.lower() for c in seen])
        self.assertEqual(len(seen), 3)     # 2 Ethan's Pokemon + Fire offered, Water/Charcadet not

