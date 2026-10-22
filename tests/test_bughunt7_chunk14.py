"""Bug hunt round 7, chunk 14: Chespin line (Chesnaught CRI, Quilladin x3,
Chespin BKT), Oricorio x3, Pikachu/Raichu x2, Pokemon Catcher, Poke Ball,
Cheren, Iris's Fighting Spirit -- each checked against its printed text,
including the cases where it should NOT work.

Note: chunk path for Oricorio GRI 55 was SM7.Oricorio_55 (Celestial Storm
Zappy Pom-Poms Oricorio); GRI is SM2, so SM2.Oricorio_55 (Vital Dance) is tested.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, PARALYZED, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.tools.effect_smoke import P1, P2

G, W, L, R, P = (PokemonTypes.GRASS, PokemonTypes.WATER, PokemonTypes.LIGHTNING,
                 PokemonTypes.FIRE, PokemonTypes.PSYCHIC)

CHESNAUGHT = 'ME4.Chesnaught_7'
CHESPIN = 'XY8.Chespin_9'
QUILL_BKT, QUILL_XY, QUILL_KSS = 'XY8.Quilladin_10', 'XY1.Quilladin_13', 'XY0.Quilladin_4'
ORI_GRI, ORI_CES, ORI_SSP = 'SM2.Oricorio_55', 'SM7.Oricorio_30', 'SV08.Oricorio_89'
CATCHER = 'ME3.PokemonCatcher_82'
PIKACHU = 'SM12.Pikachu_66'
RAICHU_BUS, RAICHU_TEF = 'SM3.Raichu_41', 'SV05.Raichu_52'
IRIS = 'SV09.IrissFightingSpirit_149'
CHEREN = 'RSV10PT5.Cheren_81'
POKEBALL = 'ME3.PokBall_80'
THERAPEUTIC = 'SV2.TherapeuticEnergy_193'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk14(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=False, **kw):
        t = Table(self, **kw)
        if me:
            self.neutral(t.put(self.filler, P1, 'active'))
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        return t

    def neutral(self, p, hp=400):
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def mine(self, t, spec, kind, count, zone='active', hp=None):
        p = self.neutral(t.put(spec, P1, zone), hp)
        if count:
            t.energy(p, kind, count)
        return p

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        title, dmg = self.filler_attack()
        t.energy(self.opp, W, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    def is_energy_of(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    # --- Chesnaught CRI 7: Needly Armor -----------------------------------
    async def test_chesnaught_needly_armor_active(self):
        t = self.table()
        ches = self.mine(t, CHESNAUGHT, G, 2, hp=400)
        t.energy(ches, W, 1)                      # non-Grass doesn't count
        dmg = await self.opp_hits(t)
        self.assertEqual(400 - t.hp(ches), dmg)
        self.assertEqual(400 - t.hp(self.opp), 60)

    async def test_chesnaught_needly_armor_ko_still_triggers(self):
        t = self.table()
        ches = self.mine(t, CHESNAUGHT, G, 1, hp=10)
        t.put(self.filler, P1, 'bench')
        await self.opp_hits(t)
        self.assertNotIn(ches, t.zone(P1, 'active'))
        self.assertEqual(400 - t.hp(self.opp), 30)

    async def test_chesnaught_needly_armor_no_grass_no_counters(self):
        t = self.table()
        ches = self.mine(t, CHESNAUGHT, W, 2, hp=400)
        await self.opp_hits(t)
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_chesnaught_impound_blocks_retreat_next_turn(self):
        t = self.table()
        ches = self.mine(t, CHESNAUGHT, G, 3)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, W, 4)
        await t.attack(ches, 'Impound')
        self.assertEqual(400 - t.hp(self.opp), 160)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', pid=P2))
        # Expires: by P2's following turn it may retreat again
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', pid=P2))

    # --- Chespin BKT 9: Tree Climb -----------------------------------------
    async def test_chespin_tree_climb_grass_only(self):
        t = self.table()
        chespin = self.mine(t, CHESPIN, G, 1)
        t.deck(P1, [t.basic_energy(W), t.basic_energy(G)])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.attack(chespin, 'Tree Climb')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertTrue(self.is_energy_of(hand[0], G))
        self.assertTrue(all(self.is_energy_of(c, G) for c in seen))

    async def test_chespin_tree_climb_no_grass(self):
        t = self.table()
        chespin = self.mine(t, CHESPIN, G, 1)
        t.deck(P1, [t.basic_energy(W)])
        await t.attack(chespin, 'Tree Climb')
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Quilladin BKT 10: Pin Missile -------------------------------------
    async def test_quilladin_pin_missile(self):
        for pattern, expected in (([True] * 4, 160), ([True, False, True, False], 80),
                                  ([False] * 4, 0)):
            t = self.table()
            q = self.mine(t, QUILL_BKT, G, 3)
            flips = iter(pattern)
            t.heads = lambda title: next(flips)
            await t.attack(q, 'Pin Missile')
            with self.subTest(pattern=pattern):
                self.assertEqual(400 - t.hp(self.opp), expected)

    # --- Quilladin XY 13: Scrunch / Wood Hammer -----------------------------
    async def test_quilladin_scrunch_heads_prevents_damage(self):
        t = self.table()
        q = self.mine(t, QUILL_XY, G, 1, hp=90)
        t.heads = True
        await t.attack(q, 'Scrunch')
        self.assertEqual(400 - t.hp(self.opp), 0)
        await self.opp_hits(t)
        self.assertEqual(t.hp(q), 90)

    async def test_quilladin_scrunch_tails_no_protection(self):
        t = self.table()
        q = self.mine(t, QUILL_XY, G, 1, hp=400)
        t.heads = False
        await t.attack(q, 'Scrunch')
        dmg = await self.opp_hits(t)
        self.assertEqual(400 - t.hp(q), dmg)

    async def test_quilladin_wood_hammer_self_damage(self):
        t = self.table()
        q = self.mine(t, QUILL_XY, G, 3)
        await t.attack(q, 'Wood Hammer')
        self.assertEqual(400 - t.hp(self.opp), 70)
        self.assertEqual(t.damage(q), 10)

    # --- Quilladin KSS 4: Leech Seed ---------------------------------------
    async def test_quilladin_leech_seed_heals_10(self):
        t = self.table()
        q = self.mine(t, QUILL_KSS, G, 2, hp=None)
        q.set_attribute(AttrID.HP, 60)            # 30 damage
        await t.attack(q, 'Leech Seed')
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertEqual(t.damage(q), 20)

    async def test_quilladin_leech_seed_undamaged_stays_full(self):
        t = self.table()
        q = self.mine(t, QUILL_KSS, G, 2, hp=None)
        await t.attack(q, 'Leech Seed')
        self.assertEqual(t.damage(q), 0)

    # --- Oricorio GRI 55: Vital Dance ---------------------------------------
    async def test_oricorio_vital_dance_on_bench_from_hand(self):
        t = self.table()
        self.mine(t, self.filler, W, 0)
        ori = t.put(ORI_GRI, P1, 'hand')
        t.deck(P1, [t.basic_energy(W), THERAPEUTIC, t.basic_energy(P), t.basic_energy(G)])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.play(ori)
        self.assertIn(ori, t.zone(P1, 'bench'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertEqual(len(seen), 3)            # Special Energy not offered
        self.assertTrue(all(any(self.is_energy_of(c, k) for k in (W, P, G)) for c in hand))
        self.assertFalse(any(def_for(c.archetype_id).display_name == 'Therapeutic Energy'
                             for c in hand + seen))

    async def test_oricorio_vital_dance_may_decline(self):
        t = self.table()
        self.mine(t, self.filler, W, 0)
        ori = t.put(ORI_GRI, P1, 'hand')
        t.deck(P1, [t.basic_energy(W)])
        t.yes = False
        await t.play(ori)
        self.assertIn(ori, t.zone(P1, 'bench'))
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Oricorio CES 30: Captivating Salsa ---------------------------------
    async def test_oricorio_captivating_salsa(self):
        t = self.table()
        ori = self.mine(t, ORI_CES, R, 1)
        benched = self.neutral(t.put(self.filler, P2, 'bench'))
        await t.attack(ori, 'Captivating Salsa')
        self.assertIs(t.active(P2), benched)
        self.assertTrue({BURNED, CONFUSED} <= t.conditions(benched))
        self.assertEqual(t.conditions(self.opp), set())
        self.assertEqual(t.conditions(ori), set())

    async def test_oricorio_captivating_salsa_no_bench(self):
        t = self.table()
        ori = self.mine(t, ORI_CES, R, 1)
        await t.attack(ori, 'Captivating Salsa')
        self.assertIs(t.active(P2), self.opp)
        self.assertEqual(t.conditions(self.opp), set())

    # --- Oricorio SSP 89: Energy Assist / Dazzle Dance ----------------------
    async def test_oricorio_energy_assist(self):
        t = self.table()
        ori = self.mine(t, ORI_SSP, P, 1)
        bench = t.put(self.filler, P1, 'bench')
        e1 = t.put(t.basic_energy(W), P1, 'discard')
        e2 = t.put(t.basic_energy(G), P1, 'discard')
        e3 = t.put(t.basic_energy(L), P1, 'discard')
        sp = t.put(THERAPEUTIC, P1, 'discard')
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.attack(ori, 'Energy Assist')
        attached = t.attached(bench)
        self.assertEqual(len(attached), 2)
        self.assertNotIn(sp, seen)
        self.assertNotIn(sp, attached)
        self.assertEqual(len(t.attached(ori)), 1)

    async def test_oricorio_energy_assist_no_bench(self):
        t = self.table()
        ori = self.mine(t, ORI_SSP, P, 1)
        e1 = t.put(t.basic_energy(W), P1, 'discard')
        await t.attack(ori, 'Energy Assist')
        self.assertIn(e1, t.zone(P1, 'discard'))
        self.assertEqual(len(t.attached(ori)), 1)

    async def test_oricorio_dazzle_dance(self):
        t = self.table()
        ori = self.mine(t, ORI_SSP, P, 2)
        await t.attack(ori, 'Dazzle Dance')
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertIn(CONFUSED, t.conditions(self.opp))
        self.assertNotIn(CONFUSED, t.conditions(ori))

    # --- Pikachu CEC 66: Nuzzle / Volt Tackle -------------------------------
    async def test_pikachu_nuzzle(self):
        for heads in (True, False):
            t = self.table()
            pika = self.mine(t, PIKACHU, L, 1)
            t.heads = heads
            await t.attack(pika, 'Nuzzle')
            with self.subTest(heads=heads):
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)
                self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_pikachu_volt_tackle(self):
        t = self.table()
        pika = self.mine(t, PIKACHU, L, 3)
        await t.attack(pika, 'Volt Tackle')
        self.assertEqual(400 - t.hp(self.opp), 70)
        self.assertEqual(t.damage(pika), 10)

    # --- Raichu BUS 41: Evoshock / Volt Tackle ------------------------------
    async def test_raichu_evoshock_paralyzes(self):
        for yes in (True, False):
            t = self.table()
            pika = self.mine(t, PIKACHU, L, 0)
            raichu = t.put(RAICHU_BUS, P1, 'hand')
            t.yes = yes
            await t.play(raichu, targets=[pika.entity_id])
            with self.subTest(yes=yes):
                self.assertEqual(name(t.active(P1)), 'Raichu')
                self.assertEqual(PARALYZED in t.conditions(self.opp), yes)
                self.assertNotIn(PARALYZED, t.conditions(t.active(P1)))

    async def test_raichu_evoshock_not_usable_once_in_play(self):
        # Only on evolving from hand: never offered as a click Ability later
        t = self.table()
        raichu = self.mine(t, RAICHU_BUS, L, 0)
        self.assertIsNone(t.ability_offer(raichu, 'Evoshock'))
        self.assertEqual(t.conditions(self.opp), set())

    async def test_raichu_volt_tackle(self):
        t = self.table()
        raichu = self.mine(t, RAICHU_BUS, L, 3)
        await t.attack(raichu, 'Volt Tackle')
        self.assertEqual(400 - t.hp(self.opp), 130)
        self.assertEqual(t.damage(raichu), 30)

    # --- Raichu TEF 52: Collateral Bolts ------------------------------------
    async def test_raichu_collateral_bolts(self):
        t = Table(self)
        def hurt(p, n):
            self.neutral(p, None)
            p.set_attribute(AttrID.HP, t.hp(p) - n)
            return p
        self.opp = hurt(t.put(self.filler, P2, 'active'), 10)  # damaged Active
        raichu = hurt(t.put(RAICHU_TEF, P1, 'active'), 30)     # damaged itself
        t.energy(raichu, L, 2)
        my_hurt = hurt(t.put(self.filler, P1, 'bench'), 10)
        my_ok = t.put(self.filler, P1, 'bench')
        opp_hurt = hurt(t.put(self.filler, P2, 'bench'), 10)
        opp_ok = t.put(self.filler, P2, 'bench')
        await t.attack(raichu, 'Collateral Bolts')
        self.assertEqual(t.damage(self.opp), 60)
        self.assertEqual(t.damage(opp_hurt), 60)
        self.assertEqual(t.damage(my_hurt), 60)
        self.assertEqual(t.damage(opp_ok), 0)
        self.assertEqual(t.damage(my_ok), 0)
        self.assertEqual(t.damage(raichu), 30)

    async def test_raichu_collateral_bolts_nothing_damaged(self):
        t = self.table()
        raichu = self.mine(t, RAICHU_TEF, L, 2)
        self.opp.set_attribute(AttrID.HP, t.hp(t.put(self.filler, P2, 'bench')))
        await t.attack(raichu, 'Collateral Bolts')
        self.assertEqual(t.damage(self.opp), 0)

    # --- Pokemon Catcher POR 82 ---------------------------------------------
    async def test_pokemon_catcher(self):
        for heads in (True, False):
            t = self.table(me=True)
            benched = t.put(self.filler, P2, 'bench')
            card = t.put(CATCHER, P1, 'hand')
            t.heads = heads
            await t.play(card)
            with self.subTest(heads=heads):
                self.assertIs(t.active(P2), benched if heads else self.opp)
                self.assertIn(card, t.zone(P1, 'discard'))

    async def test_pokemon_catcher_needs_opponent_bench(self):
        t = self.table(me=True)
        t.put(self.filler, P1, 'bench')
        card = t.put(CATCHER, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Poke Ball POR 80 ---------------------------------------------------
    async def test_poke_ball(self):
        for heads in (True, False):
            t = self.table(me=True)
            t.deck(P1, [t.basic_energy(W), PIKACHU], top=False)
            card = t.put(POKEBALL, P1, 'hand')
            t.heads = heads
            await t.play(card)
            with self.subTest(heads=heads):
                hand = t.zone(P1, 'hand')
                self.assertEqual([name(c) for c in hand], ['Pikachu'] if heads else [])
                self.assertIn(card, t.zone(P1, 'discard'))

    # --- Cheren WHT 81 ------------------------------------------------------
    async def test_cheren_draws_3(self):
        t = self.table(me=True)
        card = t.put(CHEREN, P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_cheren_short_deck_draws_what_is_left(self):
        t = self.table(me=True, filler_deck=2)
        card = t.put(CHEREN, P1, 'hand')
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(t.zone(P1, 'deck'), [])

    # --- Iris's Fighting Spirit JTG 149 -------------------------------------
    async def test_iris_discards_one_then_draws_to_6(self):
        t = self.table(me=True)
        card = t.put(IRIS, P1, 'hand')
        a = t.put(self.item, P1, 'hand')
        b = t.put(PIKACHU, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is b][:count] or cards[:count]
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 6)
        self.assertIn(b, t.zone(P1, 'discard'))
        self.assertIn(a, hand)
        self.assertIn(card, t.zone(P1, 'discard'))

    async def test_iris_needs_another_card(self):
        t = self.table(me=True)
        card = t.put(IRIS, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t.put(self.item, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))


if __name__ == '__main__':
    unittest.main()
