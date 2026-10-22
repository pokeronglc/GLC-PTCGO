"""Bug hunt round 7, chunk 32: Shopping Center, Thundurus (OBF 70), Future Booster
Energy Capsule, Alolan Sandshrew, Alolan Sandslash, Grimsley, Audino (JTG 124),
Apricorn Maker, Darumaka/Darmanitan (PFL), Metal Frying Pan, Full Metal Lab,
Misty's Favor, Bill's Analysis, Mars -- each checked against its printed text,
including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, METAL, DARK = (PokemonTypes.FIRE, PokemonTypes.WATER,
                            PokemonTypes.METAL, PokemonTypes.DARKNESS)

SHOPPING = 'SWSH7.ShoppingCenter_157'
THUNDURUS = 'SV3.Thundurus_70'
CAPSULE = 'SV05.FutureBoosterEnergyCapsule_149'
SANDSHREW = 'SM2.AlolanSandshrew_19'
SANDSLASH = 'SM5.AlolanSandslash_29'
GRIMSLEY = 'SM11.Grimsley_199'
AUDINO = 'SV09.Audino_124'
APRICORN = 'SM7.ApricornMaker_124'
DARUMAKA = 'ME2.Darumaka_15'
DARMANITAN = 'ME2.Darmanitan_16'
PAN = 'SM6.MetalFryingPan_112'
LAB = 'SV05.FullMetalLab_148'
MISTY = 'SM11.MistysFavor_202'
BILL = 'SM9.BillsAnalysis_133'
MARS = 'SM5.Mars_128'

WEEZING = 'SV035.Weezing_110'        # Spinning Fumes: 50 + 10 to each opposing Benched
IRON_TREADS = 'SV05.IronTreads_118'  # Future, Metal; Wheel Pass 60
BELDUM = 'SV05.Beldum_113'           # Metal, not Future; Dig Claws 10
GREAT_BALL, POKE_BALL, ULTRA_BALL = 'SM1.GreatBall_119', 'SM1.PokBall_125', 'SM1.UltraBall_135'
POTION, SWITCH = 'SM1.Potion_127', 'SM1.Switch_132'
CYNTHIA, LILLIE = 'SM5.Cynthia_119', 'SM1.Lillie_122'


def name(card):
    return def_for(card.archetype_id).display_name


def neutral(p, hp=400):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.set_attribute(AttrID.HP, hp)
    return p


class Chunk32(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = neutral(t.put(opp or self.filler, P2, 'active'))
        return t

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, {'hand': 'hand', 'deck': 'deck',
                                              'discard': 'discard'}[zone])
        for c in list(area.children):
            area.remove_child(c)

    async def weezing_hits(self, t):
        """P2's Active Weezing uses Spinning Fumes (50 Active + 10 each Benched)."""
        t.energy(self.opp, WATER, 2)
        t.next_turn()
        await t.attack(self.opp, 'Spinning Fumes', pid=P2)

    # --- Shopping Center EVS 157 ---------------------------------------------
    async def test_shopping_center_returns_own_tool_once_per_turn(self):
        t = self.table()
        me = neutral(t.put(self.filler, P1, 'active'))
        bench = neutral(t.put(self.filler, P1, 'bench'))
        pan1, pan2 = t.attach(PAN, me), t.attach(PAN, bench)
        stadium = t.stadium(SHOPPING, P2)          # opponent's Stadium: still usable
        offers = t.offers(stadium, None, P1)
        self.assertTrue(offers)
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is pan2]
        await t.do(offers[0])
        self.assertIn(pan2, t.zone(P1, 'hand'))
        self.assertIn(pan1, me.children)
        self.assertFalse(t.offers(stadium, None, P1))   # once during each player's turn
        # the opponent has no Tools: nothing to do on their turn, and never mine
        t.next_turn()
        self.assertFalse(t.offers(stadium, None, P2))

    async def test_shopping_center_not_offered_for_opponents_tool_only(self):
        t = self.table()
        neutral(t.put(self.filler, P1, 'active'))
        t.attach(PAN, self.opp)
        stadium = t.stadium(SHOPPING, P1)
        self.assertFalse(t.offers(stadium, None, P1))
        t.next_turn()
        self.assertTrue(t.offers(stadium, None, P2))     # opponent may use it on their turn

    # --- Thundurus OBF 70 ----------------------------------------------------
    async def test_thundurus_adverse_weather_active_protects_bench(self):
        t = self.table(WEEZING)
        th = neutral(t.put(THUNDURUS, P1, 'active'))
        bench = neutral(t.put(self.filler, P1, 'bench'))
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(th), 50)
        self.assertEqual(400 - t.hp(bench), 0)

    # BUG: Adverse Weather still protects the Bench while Thundurus is itself Benched
    async def test_thundurus_adverse_weather_off_when_benched(self):
        t = self.table(WEEZING)
        neutral(t.put(self.filler, P1, 'active'))
        th = neutral(t.put(THUNDURUS, P1, 'bench'))
        bench = neutral(t.put(self.filler, P1, 'bench'))
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(th), 10)
        self.assertEqual(400 - t.hp(bench), 10)

    async def test_thundurus_gigantic_bolt_self_damage(self):
        t = self.table()
        th = neutral(t.put(THUNDURUS, P1, 'active'), hp=None)
        t.energy(th, PokemonTypes.LIGHTNING, 2)
        await t.attack(th, 'Gigantic Bolt')
        self.assertEqual(400 - t.hp(self.opp), 140)
        self.assertEqual(t.damage(th), 90)

    # --- Future Booster Energy Capsule TEF 149 --------------------------------
    # BUG: Capsule's "no Retreat Cost" never applies (text mis-read as an opponent-wide passive)
    async def test_capsule_on_future_pokemon(self):
        t = self.table()
        treads = neutral(t.put(IRON_TREADS, P1, 'active'))
        t.energy(treads, METAL, 2)
        self.assertEqual(t.retreat(treads), 2)
        await t.play(t.put(CAPSULE, P1, 'hand'), targets=[treads.entity_id])
        self.assertEqual(t.retreat(treads), 0)
        await t.attack(treads, 'Wheel Pass')
        self.assertEqual(400 - t.hp(self.opp), 80)

    async def test_capsule_on_non_future_pokemon_does_nothing(self):
        t = self.table()
        beldum = neutral(t.put(BELDUM, P1, 'active'))
        t.energy(beldum, METAL, 1)
        await t.play(t.put(CAPSULE, P1, 'hand'), targets=[beldum.entity_id])
        self.assertIn('Future Booster Energy Capsule', [name(c) for c in beldum.children])
        self.assertEqual(t.retreat(beldum), 1)
        await t.attack(beldum, 'Dig Claws')
        self.assertEqual(400 - t.hp(self.opp), 10)

    # --- Alolan Sandshrew GRI 19 ---------------------------------------------
    async def test_sandshrew_defense_curl(self):
        for heads, expected in ((True, 0), (False, 50)):
            t = self.table(WEEZING)
            shrew = neutral(t.put(SANDSHREW, P1, 'active'))
            t.heads = heads
            await t.attack(shrew, 'Defense Curl')
            await self.weezing_hits(t)
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(shrew), expected)

    # --- Alolan Sandslash UPR 29 ---------------------------------------------
    async def test_sandslash_spike_armor_counters_attacker(self):
        t = self.table(WEEZING)
        slash = neutral(t.put(SANDSLASH, P1, 'active'))
        await t.attack(slash, 'Spike Armor')
        self.assertEqual(400 - t.hp(self.opp), 30)
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(slash), 50)
        self.assertEqual(400 - t.hp(self.opp), 30 + 60)

    async def test_sandslash_spike_armor_expires(self):
        t = self.table(WEEZING)
        slash = neutral(t.put(SANDSLASH, P1, 'active'))
        await t.attack(slash, 'Spike Armor')
        t.next_turn()          # opponent's turn passes without attacking
        t.next_turn()          # my turn
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(slash), 50)
        self.assertEqual(400 - t.hp(self.opp), 30)

    # --- Grimsley UNM 199 ----------------------------------------------------
    async def test_grimsley_moves_up_to_3_counters_between_opponents(self):
        t = Table(self)
        neutral(t.put(self.filler, P1, 'active'))
        src = t.put(self.filler, P2, 'active')
        maxhp = effective_max_hp(t.board, src)
        src.set_attribute(AttrID.HP, maxhp - 50)
        dst = t.put(self.filler, P2, 'bench')
        card = t.put(GRIMSLEY, P1, 'hand')
        t.pokemon = lambda cands, prompt: src if 'damage' in prompt.lower() and src in cands else dst
        buttons = []

        async def choose(ctx, prompt, options, *a, **k):
            buttons.append(list(options))
            return len(options) - 1
        with patch.object(EffectContext, 'choose', choose):
            await t.play(card)
        self.assertEqual(buttons, [['1', '2', '3']])
        self.assertEqual(t.damage(src), 20)
        self.assertEqual(t.damage(dst), 30)

    async def test_grimsley_not_playable_without_opponent_damage(self):
        t = Table(self)
        mine = t.put(self.filler, P1, 'active')
        t.put(self.filler, P1, 'bench')
        mine.set_attribute(AttrID.HP, effective_max_hp(t.board, mine) - 50)
        t.put(self.filler, P2, 'active')
        t.put(self.filler, P2, 'bench')
        card = t.put(GRIMSLEY, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        # only 1 opposing Pokémon (damaged): nowhere to move counters
        t2 = Table(self)
        t2.put(self.filler, P1, 'active')
        lone = t2.put(self.filler, P2, 'active')
        lone.set_attribute(AttrID.HP, effective_max_hp(t2.board, lone) - 50)
        card2 = t2.put(GRIMSLEY, P1, 'hand')
        self.assertFalse(t2.can(card2, 'UseTrainerCard'))

    # --- Audino JTG 124 ------------------------------------------------------
    async def test_audino_beckon_supporter_from_discard(self):
        t = self.table()
        audino = neutral(t.put(AUDINO, P1, 'active'))
        t.energy(audino, WATER, 1)
        self.clear(t, P1, 'hand')
        mars = t.put(MARS, P1, 'discard')
        potion = t.put(POTION, P1, 'discard')
        await t.attack(audino, 'Beckon')
        self.assertEqual(t.zone(P1, 'hand'), [mars])
        self.assertIn(potion, t.zone(P1, 'discard'))

    async def test_audino_beckon_ignores_items(self):
        t = self.table()
        audino = neutral(t.put(AUDINO, P1, 'active'))
        t.energy(audino, WATER, 1)
        self.clear(t, P1, 'hand')
        potion = t.put(POTION, P1, 'discard')
        await t.attack(audino, 'Beckon')
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertIn(potion, t.zone(P1, 'discard'))

    # --- Apricorn Maker CES 124 ----------------------------------------------
    async def test_apricorn_maker_only_ball_items_up_to_2(self):
        t = self.table()
        neutral(t.put(self.filler, P1, 'active'))
        self.clear(t, P1, 'hand')
        balls = t.deck(P1, [GREAT_BALL, POKE_BALL, ULTRA_BALL])
        t.deck(P1, [POTION, SWITCH])
        t.deck(P1, [self.filler])
        seen = []

        def picks(cards, count, prompt, display):
            seen.append((sorted(name(c) for c in cards), count))
            return cards[:count]
        t.picks = picks
        card = t.put(APRICORN, P1, 'hand')
        await t.play(card)
        pool, count = seen[0]
        self.assertEqual(count, 2)
        self.assertEqual(pool, sorted(name(c) for c in balls))
        hand = [c for c in t.zone(P1, 'hand')]
        self.assertEqual(len(hand), 2)
        self.assertTrue(all('Ball' in name(c) for c in hand))

    # --- Darumaka / Darmanitan PFL 15 / 16 -------------------------------------
    async def test_darumaka_blaze_ball_counts_fire_only(self):
        for fire, other, expected in ((2, 1, 50), (0, 3, 10)):
            t = self.table()
            d = neutral(t.put(DARUMAKA, P1, 'active'))
            if fire:
                t.energy(d, FIRE, fire)
            t.energy(d, WATER, other)
            await t.attack(d, 'Blaze Ball')
            with self.subTest(fire=fire):
                self.assertEqual(400 - t.hp(self.opp), expected)

    async def test_darmanitan_blaze_ball_counts_fire_only(self):
        for fire, other, expected in ((3, 1, 160), (0, 4, 40)):
            t = self.table()
            d = neutral(t.put(DARMANITAN, P1, 'active'))
            if fire:
                t.energy(d, FIRE, fire)
            t.energy(d, WATER, other)
            await t.attack(d, 'Blaze Ball')
            with self.subTest(fire=fire):
                self.assertEqual(400 - t.hp(self.opp), expected)

    # --- Metal Frying Pan FLI 112 ----------------------------------------------
    async def test_metal_frying_pan_metal_minus_30_and_no_weakness(self):
        t = self.table(WEEZING)
        beldum = neutral(t.put(BELDUM, P1, 'active'))
        beldum.set_attribute(AttrID.WEAKNESS_TYPES, [DARK])
        await t.play(t.put(PAN, P1, 'hand'), targets=[beldum.entity_id])
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(beldum), 20)    # 50, no Weakness, -30

    async def test_metal_frying_pan_non_metal_unaffected(self):
        t = self.table(WEEZING)
        me = neutral(t.put(self.filler, P1, 'active'))
        await t.play(t.put(PAN, P1, 'hand'), targets=[me.entity_id])
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(me), 50)

    # --- Full Metal Lab TEF 148 ------------------------------------------------
    async def test_full_metal_lab_reduces_damage_to_metal_both_sides(self):
        t = self.table(WEEZING)
        t.stadium(LAB, P1)
        beldum = neutral(t.put(BELDUM, P1, 'active'))
        bench_beldum = neutral(t.put(BELDUM, P1, 'bench'))
        bench_other = neutral(t.put(self.filler, P1, 'bench'))
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(beldum), 20)
        self.assertEqual(400 - t.hp(bench_beldum), 0)
        self.assertEqual(400 - t.hp(bench_other), 10)
        # opponent's Metal Pokémon too
        t2 = self.table(BELDUM)
        t2.stadium(LAB, P2)
        d = neutral(t2.put(DARMANITAN, P1, 'active'))
        t2.energy(d, WATER, 4)
        await t2.attack(d, 'Blaze Ball')
        self.assertEqual(400 - t2.hp(self.opp), 10)

    async def test_full_metal_lab_non_metal_unaffected(self):
        t = self.table(WEEZING)
        t.stadium(LAB, P2)
        me = neutral(t.put(self.filler, P1, 'active'))
        await self.weezing_hits(t)
        self.assertEqual(400 - t.hp(me), 50)

    # --- Misty's Favor UNM 202 -------------------------------------------------
    async def test_mistys_favor_up_to_3_supporters(self):
        t = self.table()
        neutral(t.put(self.filler, P1, 'active'))
        self.clear(t, P1, 'hand')
        sups = t.deck(P1, [MARS, GRIMSLEY, CYNTHIA, LILLIE])
        t.deck(P1, [POTION, GREAT_BALL])
        seen = []

        def picks(cards, count, prompt, display):
            seen.append((sorted(name(c) for c in cards), count))
            return cards[:count]
        t.picks = picks
        await t.play(t.put(MISTY, P1, 'hand'))
        pool, count = seen[0]
        self.assertEqual(count, 3)
        self.assertEqual(pool, sorted(name(c) for c in sups))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertTrue(all(c in sups for c in hand))

    # --- Bill's Analysis TEU 133 -----------------------------------------------
    async def test_bills_analysis_top_7_up_to_2_trainers(self):
        t = self.table()
        neutral(t.put(self.filler, P1, 'active'))
        self.clear(t, P1, 'hand')
        self.clear(t, P1, 'deck')
        deep = t.deck(P1, [GREAT_BALL])[0]                 # 8th from the top
        t.deck(P1, [self.filler] * 4)
        potion, switch, ball = t.deck(P1, [POTION, SWITCH, POKE_BALL])  # within top 7
        seen = []

        def picks(cards, count, prompt, display):
            seen.append(([name(c) for c in cards], count))
            return [c for c in cards if c in (potion, switch)]
        t.picks = picks
        await t.play(t.put(BILL, P1, 'hand'))
        pool, count = seen[0]
        self.assertEqual(count, 2)
        self.assertNotIn(deep, [c for c in t.zone(P1, 'hand')])
        self.assertEqual(sorted(pool), sorted(['Potion', 'Switch', 'Poké Ball']))
        self.assertEqual(sorted(name(c) for c in t.zone(P1, 'hand')), ['Potion', 'Switch'])
        self.assertEqual(len(t.zone(P1, 'deck')), 6)

    # --- Mars UPR 128 ----------------------------------------------------------
    async def test_mars_draws_2_and_discards_random_opponent_card(self):
        t = self.table()
        neutral(t.put(self.filler, P1, 'active'))
        self.clear(t, P1, 'hand')
        self.clear(t, P2, 'hand')
        opp_hand = [t.put(POTION, P2, 'hand') for _ in range(3)]
        await t.play(t.put(MARS, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)
        self.assertEqual(len([c for c in t.zone(P2, 'discard') if c in opp_hand]), 1)

    async def test_mars_opponent_empty_hand_still_draws(self):
        t = self.table()
        neutral(t.put(self.filler, P1, 'active'))
        self.clear(t, P1, 'hand')
        self.clear(t, P2, 'hand')
        card = t.put(MARS, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(t.zone(P2, 'discard'), [])


if __name__ == '__main__':
    unittest.main()
