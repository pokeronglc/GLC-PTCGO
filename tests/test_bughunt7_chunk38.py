"""Bug hunt round 7, chunk 38: Clive, Keldeo, Accompanying Flute, Iron Treads,
Orthworm, Mankey, Primeape, Annihilape, Caitlin, Jaw Fossil, Memory Capsule,
Devoured Field, Pyukumuku, Rocky Helmet, Glastrier -- each checked against its
printed text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.passives import effective_pokemon_types
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT, METAL, DARK, PSY = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.METAL,
    PokemonTypes.DARKNESS, PokemonTypes.PSYCHIC)

CLIVE = 'SV045.Clive_78'
KELDEO = 'ME4.Keldeo_19'
FLUTE = 'SV06.AccompanyingFlute_142'
TREADS = 'SV05.IronTreads_118'
CAPSULE_FB = 'SV05.FutureBoosterEnergyCapsule_149'
ORTHWORM = 'SV4.Orthworm_138'
MANKEY, PRIMEAPE, ANNIHILAPE = 'SV1.Mankey_107', 'SV10.Primeape_91', 'SV10.Annihilape_92'
CAITLIN = 'SWSH6.Caitlin_132'
JAW = 'XY3.JawFossil_94'
TYRUNT = 'XY3.Tyrunt_61'
MEMORY = 'SWSH4.MemoryCapsule_155'
DEVOURED = 'SM4.DevouredField_93'
PYUKU = 'SM1.Pyukumuku_47'
HELMET = 'SV1.RockyHelmet_193'
GLASTRIER = 'ME2PT5.Glastrier_54'
PURRLOIN = 'SWSH3.Purrloin_106'      # Darkness, Dig Claws 10 (D)
LATIAS = 'Promo_XY.Latias_78'        # Dragon, Speed Wing 60 (PCC)
SUPPORTER = 'SWSH6.Caitlin_132'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk38(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None, filler_deck=30):
        t = Table(self, filler_deck=filler_deck)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.big(self.opp)
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

    # --- Clive PAF 78 ----------------------------------------------------------
    async def test_clive_draws_two_per_opponent_supporter(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        for spec in (SUPPORTER, SUPPORTER, self.item, self.filler):
            t.put(spec, P2, 'hand')
        card = t.put(CLIVE, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)

    async def test_clive_no_opponent_supporter_draws_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        t.put(self.item, P2, 'hand')
        card = t.put(CLIVE, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertEqual([c for c in t.zone(P1, 'hand') if c is not card], [])

    # --- Keldeo CRI 19 ---------------------------------------------------------
    async def test_keldeo_shoot_through_hits_bench_without_weakness(self):
        t = self.table()
        me = self.mine(t, KELDEO, WATER, 1)
        b1 = self.mine(t, self.filler, zone='bench', pid=P2, hp=400)
        b2 = self.mine(t, self.filler, zone='bench', pid=P2, hp=400)
        b2.set_attribute(AttrID.WEAKNESS_TYPES, [WATER])
        t.pokemon = lambda cands, prompt: b2
        t.picks = lambda cards, count, prompt, display: [b2]   # browser-chosen target
        await t.attack(me, 'Shoot Through')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(self.dealt(b2), 20)
        self.assertEqual(self.dealt(b1), 0)

    async def test_keldeo_reflect_energy_moves_one_energy(self):
        t = self.table()
        me = self.mine(t, KELDEO, WATER, 2)
        bench = self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Reflect Energy')
        self.assertEqual(self.dealt(), 70)
        self.assertEqual(len(me.children), 1)
        self.assertEqual(len(bench.children), 1)

    async def test_keldeo_reflect_energy_no_bench_keeps_energy(self):
        t = self.table()
        me = self.mine(t, KELDEO, WATER, 2)
        await t.attack(me, 'Reflect Energy')
        self.assertEqual(self.dealt(), 70)
        self.assertEqual(len(me.children), 2)

    # --- Accompanying Flute TWM 142 --------------------------------------------
    async def test_flute_benches_opponent_basics_from_top_5(self):
        t = self.table()
        self.mine(t, self.filler)
        deep = t.deck(P2, [self.filler])[0]               # 6th from top
        a, evo, b = t.deck(P2, [self.filler, PRIMEAPE, self.filler])
        t.deck(P2, [self.item, self.item])
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), list(cards))[1]
        card = t.put(FLUTE, P1, 'hand')
        await t.play(card)
        bench = t.zone(P2, 'bench')
        self.assertIn(a, bench)
        self.assertIn(b, bench)
        self.assertNotIn(evo, bench)
        self.assertNotIn(deep, bench)
        self.assertNotIn(evo, offered)
        self.assertIn(evo, t.zone(P2, 'deck'))
        self.assertEqual(t.zone(P1, 'bench'), [])

    async def test_flute_respects_opponent_bench_limit(self):
        t = self.table()
        self.mine(t, self.filler)
        for _ in range(4):
            t.put(self.filler, P2, 'bench')
        t.deck(P2, [self.filler, self.filler, self.filler])
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        card = t.put(FLUTE, P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P2, 'bench')), 5)

    # --- Iron Treads TEF 118 ---------------------------------------------------
    # BUG: bw_era._BWTextPassive.modify_pokemon_types looks for the Capsule via
    # _attached(), which only returns Energy cards, so the Tool is never found.
    async def test_iron_treads_dual_core_with_capsule(self):
        t = self.table()
        me = self.mine(t, TREADS)
        self.assertEqual(set(effective_pokemon_types(t.board, me)), {METAL})
        cap = t.put(CAPSULE_FB, P1, 'hand')
        await t.play(cap, targets=[me.entity_id])
        self.assertIn(cap, me.children)
        self.assertEqual(set(effective_pokemon_types(t.board, me)), {METAL, FIGHT})

    async def test_iron_treads_wheel_pass_moves_energy(self):
        t = self.table()
        me = self.mine(t, TREADS, METAL, 2)
        bench = self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Wheel Pass')
        self.assertEqual(self.dealt(), 60)
        self.assertEqual(len(me.children), 1)
        self.assertEqual(len(bench.children), 1)

    # --- Orthworm PAR 138 ------------------------------------------------------
    async def test_orthworm_punch_and_draw(self):
        t = self.table()
        me = self.mine(t, ORTHWORM, METAL, 1)
        self.clear_hand(t)
        await t.attack(me, 'Punch and Draw')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    async def test_orthworm_crunch_time_rush_3_cards(self):
        t = self.table(filler_deck=3)
        me = self.mine(t, ORTHWORM, METAL, 3)
        self.assertEqual(len(t.zone(P1, 'deck')), 3)
        await t.attack(me, 'Crunch-Time Rush')
        self.assertEqual(self.dealt(), 240)

    async def test_orthworm_crunch_time_rush_4_cards(self):
        t = self.table(filler_deck=4)
        me = self.mine(t, ORTHWORM, METAL, 3)
        await t.attack(me, 'Crunch-Time Rush')
        self.assertEqual(self.dealt(), 90)

    # --- Mankey SVI 107 --------------------------------------------------------
    async def test_mankey_monkey_beatdown_recoil(self):
        t = self.table()
        me = self.mine(t, MANKEY, FIGHT, 1)
        await t.attack(me, 'Monkey Beatdown')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.damage(me), 10)

    # --- Primeape DRI 91 -------------------------------------------------------
    async def test_primeape_drag_off_switches_and_hits_new_active(self):
        t = self.table()
        me = self.mine(t, PRIMEAPE, FIGHT, 1)
        b1 = self.mine(t, self.filler, zone='bench', pid=P2, hp=400)
        b2 = self.mine(t, self.filler, zone='bench', pid=P2, hp=400)
        t.pokemon = lambda cands, prompt: b2
        await t.attack(me, 'Drag Off')
        self.assertIs(t.active(P2), b2)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertEqual(self.dealt(b2), 30)
        self.assertEqual(self.dealt(), 0)
        self.assertEqual(self.dealt(b1), 0)

    # --- Annihilape DRI 92 -----------------------------------------------------
    async def test_annihilape_lose_cool_with_two_counters(self):
        t = self.table()
        me = self.mine(t, ANNIHILAPE, FIGHT, 2)
        me.set_attribute(AttrID.HP, 130)                  # 2 damage counters
        await t.attack(me, 'Impact Blow')
        self.assertEqual(self.dealt(), 280)

    async def test_annihilape_lose_cool_one_counter_no_bonus(self):
        t = self.table()
        me = self.mine(t, ANNIHILAPE, FIGHT, 2)
        me.set_attribute(AttrID.HP, 140)                  # 1 damage counter
        await t.attack(me, 'Impact Blow')
        self.assertEqual(self.dealt(), 160)

    async def test_annihilape_impact_blow_locked_next_turn(self):
        t = self.table()
        me = self.mine(t, ANNIHILAPE, FIGHT, 2)
        await t.attack(me, 'Impact Blow')
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(me, 'Impact Blow'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(me, 'Impact Blow'))

    # --- Caitlin CRE 132 -------------------------------------------------------
    async def test_caitlin_bottoms_cards_and_draws_that_many(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        x = t.put(self.filler, P1, 'hand')
        y = t.put(PRIMEAPE, P1, 'hand')
        keep = t.put(MANKEY, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [x, y]
        card = t.put(CAITLIN, P1, 'hand')
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertIn(keep, hand)
        self.assertNotIn(x, hand)
        self.assertNotIn(y, hand)
        self.assertEqual(len(hand), 3)
        deck = t.zone(P1, 'deck')
        self.assertEqual({deck[0], deck[1]}, {x, y})     # bottom of deck

    async def test_caitlin_not_playable_with_empty_hand(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        card = t.put(CAITLIN, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Jaw Fossil FFI 94 -----------------------------------------------------
    async def test_jaw_fossil_benches_tyrunt_from_bottom_7(self):
        t = self.table()
        self.mine(t, self.filler)
        ty = t.deck(P1, [TYRUNT], top=False)[0]
        for _ in range(6):
            t.deck(P1, [self.item], top=False)            # Tyrunt is 7th from bottom
        card = t.put(JAW, P1, 'hand')
        await t.play(card)
        self.assertIn(ty, t.zone(P1, 'bench'))
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_jaw_fossil_misses_tyrunt_8th_from_bottom(self):
        t = self.table()
        self.mine(t, self.filler)
        ty = t.deck(P1, [TYRUNT], top=False)[0]
        for _ in range(7):
            t.deck(P1, [self.item], top=False)
        card = t.put(JAW, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertNotIn(ty, t.zone(P1, 'bench'))
        self.assertIn(ty, t.zone(P1, 'deck'))

    # --- Memory Capsule VIV 155 ------------------------------------------------
    async def evolved_annihilape(self, t):
        me = self.mine(t, MANKEY, FIGHT, 2)
        t.state.entered_play_turn[me.entity_id] = 0
        primeape = t.put(PRIMEAPE, P1, 'hand')
        await t.play(primeape, targets=[me.entity_id])
        p = t.active(P1)
        self.assertEqual(name(p), 'Primeape')
        # allow the second evolution (a later turn)
        t.state.entered_play_turn[p.entity_id] = 0
        for attr in ('evolved_this_turn', 'evolved_pokemon'):
            s = getattr(t.state, attr, None)
            if isinstance(s, (set, dict)):
                s.clear()
        ape = t.put(ANNIHILAPE, P1, 'hand')
        await t.play(ape, targets=[p.entity_id])
        a = t.active(P1)
        self.assertEqual(name(a), 'Annihilape')
        return a

    async def test_memory_capsule_grants_previous_evolution_attacks(self):
        t = self.table()
        a = await self.evolved_annihilape(t)
        self.assertIsNone(t.attack_offer(a, 'Drag Off'))
        tool = t.put(MEMORY, P1, 'hand')
        await t.play(tool, targets=[a.entity_id])
        self.assertIn(tool, a.children)
        self.assertIsNotNone(t.attack_offer(a, 'Drag Off'))
        self.assertIsNotNone(t.attack_offer(a, 'Monkey Beatdown'))
        await t.attack(a, 'Monkey Beatdown')
        self.assertEqual(self.dealt(), 30)

    async def test_memory_capsule_basic_gets_nothing(self):
        t = self.table()
        me = self.mine(t, MANKEY, FIGHT, 2)
        tool = t.put(MEMORY, P1, 'hand')
        await t.play(tool, targets=[me.entity_id])
        titles = set()
        from spirit.game.data_utils import ABILITIES_BY_ID
        for e in t.offers(me, 'UsePokemonAttack'):
            titles.add(ABILITIES_BY_ID[e['selectableAction']['actionID']].title)
        self.assertEqual(titles, {'Monkey Beatdown'})

    # --- Devoured Field CIN 93 -------------------------------------------------
    async def test_devoured_field_darkness_plus_10(self):
        t = self.table()
        me = self.mine(t, PURRLOIN, DARK, 1)
        t.stadium(DEVOURED, P2)
        await t.attack(me, 'Dig Claws')
        self.assertEqual(self.dealt(), 20)

    async def test_devoured_field_dragon_plus_10(self):
        t = self.table()
        me = self.mine(t, LATIAS, PSY, 3)
        t.stadium(DEVOURED, P1)
        await t.attack(me, 'Speed Wing')
        self.assertEqual(self.dealt(), 70)

    async def test_devoured_field_colorless_no_bonus(self):
        t = self.table()
        me = self.mine(t, self.filler, WATER, 3)
        t.stadium(DEVOURED, P1)
        await t.attack(me, 'Heavy Impact')
        self.assertEqual(self.dealt(), 80)

    # --- Pyukumuku SUM 47 ------------------------------------------------------
    async def pyuku_board(self):
        t = Table(self)
        pyu = self.mine(t, PYUKU)
        self.mine(t, self.filler, zone='bench')
        attacker = t.put(self.filler, P2, 'active')
        self.big(attacker)
        t.energy(attacker, WATER, 3)
        t.next_turn()
        return t, pyu, attacker

    async def test_pyukumuku_innards_out_on_ko(self):
        t, pyu, attacker = await self.pyuku_board()
        await t.attack(attacker, 'Heavy Impact', pid=P2)
        self.assertNotIn(pyu, t.board.pokemon_in_play(P1))
        self.assertEqual(self.dealt(attacker), 60)

    async def test_pyukumuku_survives_no_counters(self):
        t, pyu, attacker = await self.pyuku_board()
        pyu.set_attribute(AttrID.HP, 200)
        await t.attack(attacker, 'Heavy Impact', pid=P2)
        self.assertIn(pyu, t.board.pokemon_in_play(P1))
        self.assertEqual(self.dealt(attacker), 0)

    # --- Rocky Helmet SVI 193 --------------------------------------------------
    async def test_rocky_helmet_active_counters_attacker(self):
        t = Table(self)
        me = self.mine(t, self.filler, hp=300)
        helmet = t.put(HELMET, P1, 'hand')
        await t.play(helmet, targets=[me.entity_id])
        attacker = t.put(self.filler, P2, 'active')
        self.big(attacker)
        t.energy(attacker, WATER, 3)
        t.next_turn()
        await t.attack(attacker, 'Heavy Impact', pid=P2)
        self.assertEqual(self.dealt(attacker), 20)

    async def test_rocky_helmet_benched_no_counters(self):
        t = Table(self)
        self.mine(t, self.filler, hp=300)
        holder = self.mine(t, self.filler, zone='bench', hp=300)
        helmet = t.put(HELMET, P1, 'hand')
        await t.play(helmet, targets=[holder.entity_id])
        attacker = t.put(KELDEO, P2, 'active')
        self.big(attacker)
        t.energy(attacker, WATER, 1)
        t.next_turn()
        t.pokemon = lambda cands, prompt: holder
        await t.attack(attacker, 'Shoot Through', pid=P2)
        self.assertEqual(300 - t.hp(holder), 20)          # bench was hit
        self.assertEqual(self.dealt(attacker), 0)

    # --- Glastrier ASC 54 ------------------------------------------------------
    async def test_glastrier_ice_shot_hits_bench(self):
        t = self.table()
        me = self.mine(t, GLASTRIER, WATER, 1)
        b = self.mine(t, self.filler, zone='bench', pid=P2, hp=400)
        await t.attack(me, 'Ice Shot')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(self.dealt(b), 20)

    async def test_glastrier_frosty_typhoon_locked_next_turn(self):
        t = self.table()
        me = self.mine(t, GLASTRIER, WATER, 3)
        await t.attack(me, 'Frosty Typhoon')
        self.assertEqual(self.dealt(), 130)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(me, 'Frosty Typhoon'))
        self.assertIsNotNone(t.attack_offer(me, 'Ice Shot'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(me, 'Frosty Typhoon'))


if __name__ == '__main__':
    unittest.main()
