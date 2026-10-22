"""Bug hunt round 7, chunk 22: Frozen City, Mountain Ring, Charcadet, Blowtorch,
Temple of Sinnoh, Armarouge (SVI/SSP), Waitress, Staryu, Starmie, Tyrogue,
Lively Stadium, Surfer, Hassel, Morty's Conviction -- each checked against its
printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
LIGHTNING = PokemonTypes.LIGHTNING

FROZEN_CITY = 'BW9.FrozenCity_100'
MOUNTAIN_RING = 'XY3.MountainRing_97'
CHARCADET = 'ME2.Charcadet_19'
BLOWTORCH = 'ME2.Blowtorch_86'
TEMPLE = 'SWSH10.TempleofSinnoh_155'
ARMAROUGE_SVI = 'SV1.Armarouge_41'
WAITRESS = 'ME2PT5.Waitress_215'
STARYU = 'SV035.Staryu_120'
STARMIE = 'XY12.Starmie_31'
TYROGUE = 'ME1.Tyrogue_71'
LIVELY = 'SV08.LivelyStadium_180'
ARMAROUGE_SSP = 'SV08.Armarouge_34'
SURFER = 'SV08.Surfer_187'
HASSEL = 'SV06.Hassel_151'
MORTY = 'SV05.MortysConviction_155'

SABLEYE_PLASMA = 'BW9.Sableye_49'       # Basic, Team Plasma
EMOLGA = 'SV06.Emolga_69'               # Sky Wave: 10 to each Benched (both sides)
LUMINOUS = 'SV2.LuminousEnergy_191'
THERAPEUTIC = 'SV2.TherapeuticEnergy_193'
BRAVERY_CHARM = 'SV2.BraveryCharm_173'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk22(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def table(self):
        t = Table(self)
        self.opp = self.neutral(t.put(self.filler, P2, 'active'))
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def is_basic(self, card, kind=None):
        aid = card.archetype_id.lower()
        if kind is not None:
            return aid == self.energies[kind.value].lower()
        return aid in {g.lower() for g in self.energies.values()}

    def hand_energy(self, t, kind, pid=P1):
        return t.put(t.basic_energy(kind), pid, 'hand')

    # --- Frozen City BW9 100 -----------------------------------------------
    async def test_frozen_city_attach_from_hand(self):
        t = self.table()
        t.stadium(FROZEN_CITY, P2)
        char = self.mine(t, CHARCADET, zone='active')
        sab = self.mine(t, SABLEYE_PLASMA, zone='bench')
        e1 = self.hand_energy(t, FIRE)
        await t.play(e1, targets=[char.entity_id])
        self.assertIn(e1, list(char.children))
        self.assertEqual(t.damage(char), 20, 'non-Plasma Pokémon gets 2 counters')
        # Team Plasma Pokémon is excluded
        t.state.energy_attached_this_turn = False
        t.next_turn(); t.next_turn()
        e2 = self.hand_energy(t, PSY)
        await t.play(e2, targets=[sab.entity_id])
        self.assertIn(e2, list(sab.children))
        self.assertEqual(t.damage(sab), 0, 'Team Plasma Pokémon takes no counters')

    async def test_frozen_city_affects_opponent_too(self):
        t = self.table()
        t.stadium(FROZEN_CITY, P1)
        t.next_turn()
        e = self.hand_energy(t, WATER, pid=P2)
        before = t.hp(self.opp)
        await t.play(e, pid=P2, targets=[self.opp.entity_id])
        self.assertEqual(before - t.hp(self.opp), 20)

    async def test_frozen_city_not_from_effect_attach(self):
        # Waitress attaches from the deck, not from hand: no counters.
        t = self.table()
        t.stadium(FROZEN_CITY, P2)
        char = self.mine(t, CHARCADET)
        t.deck(P1, [t.basic_energy(FIRE)])
        w = t.put(WAITRESS, P1, 'hand')
        await t.play(w)
        self.assertEqual(len(char.children), 1)
        self.assertEqual(t.damage(char), 0)

    # --- Mountain Ring XY3 97 ----------------------------------------------
    async def test_mountain_ring_prevents_bench_damage_both_sides(self):
        for ring in (False, True):
            t = self.table()
            if ring:
                t.stadium(MOUNTAIN_RING, P2)
            emolga = self.mine(t, EMOLGA, WATER, 1)
            my_bench = self.mine(t, self.filler, zone='bench')
            opp_bench = self.neutral(t.put(self.filler, P2, 'bench'))
            await t.attack(emolga, 'Sky Wave')
            with self.subTest(ring=ring):
                self.assertEqual(400 - t.hp(self.opp), 10, 'Active still damaged')
                self.assertEqual(t.damage(my_bench), 0 if ring else 10)
                self.assertEqual(400 - t.hp(opp_bench), 0 if ring else 10)

    async def test_mountain_ring_blocks_crimson_blaster(self):
        t = self.table()
        t.stadium(MOUNTAIN_RING, P1)
        arm = self.mine(t, ARMAROUGE_SSP, FIRE, 3)
        opp_bench = self.neutral(t.put(self.filler, P2, 'bench'))
        await t.attack(arm, 'Crimson Blaster')
        self.assertEqual(400 - t.hp(opp_bench), 0)

    # --- Charcadet PFL 19: Gather Strength ---------------------------------
    async def test_charcadet_gather_strength(self):
        t = self.table()
        char = self.mine(t, CHARCADET, FIRE, 1)
        t.deck(P1, [t.basic_energy(FIRE), LUMINOUS, t.basic_energy(WATER),
                    t.basic_energy(PSY), CHARCADET])
        offered = []

        def picks(cards, count, prompt, display):
            offered.append((list(cards), count))
            return list(cards)[:count]
        t.picks = picks
        hand0 = len(t.zone(P1, 'hand'))
        await t.attack(char, 'Gather Strength')
        cards, count = offered[0]
        self.assertEqual(count, 2)
        self.assertTrue(all(self.is_basic(c) for c in cards), [name(c) for c in cards])
        self.assertEqual(len(cards), 3, 'only the three basic Energy are eligible')
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand) - hand0, 2)
        self.assertTrue(all(self.is_basic(c) for c in hand[-2:]))

    # --- Blowtorch PFL 86 --------------------------------------------------
    async def test_blowtorch_discards_opponent_tool(self):
        t = self.table()
        self.mine(t, CHARCADET)
        tool = t.attach(BRAVERY_CHARM, self.opp)
        my_tool = t.attach(BRAVERY_CHARM, t.active(P1))
        fire = self.hand_energy(t, FIRE)
        bt = t.put(BLOWTORCH, P1, 'hand')
        seen = []

        def picks(cards, count, prompt, display):
            seen.append(list(cards))
            if any(c is fire for c in cards):
                return [fire]
            return [tool]
        t.picks = picks
        self.assertTrue(t.can(bt, 'UseTrainerCard'))
        await t.play(bt)
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertIn(tool, t.zone(P2, 'discard'))
        self.assertIn(my_tool, list(t.active(P1).children))
        self.assertFalse(any(my_tool in s for s in seen), 'own Tool is not a target')

    async def test_blowtorch_discards_stadium(self):
        t = self.table()
        self.mine(t, CHARCADET)
        st = t.stadium(LIVELY, P1)        # "a Stadium in play" - even your own
        self.hand_energy(t, FIRE)
        bt = t.put(BLOWTORCH, P1, 'hand')
        await t.play(bt)
        self.assertIn(st, t.zone(P1, 'discard'))

    async def test_blowtorch_not_playable(self):
        t = self.table()
        self.mine(t, CHARCADET)
        t.attach(BRAVERY_CHARM, self.opp)
        bt = t.put(BLOWTORCH, P1, 'hand')
        self.hand_energy(t, WATER)
        t.put(LUMINOUS, P1, 'hand')   # Special, not basic Fire
        self.assertFalse(t.can(bt, 'UseTrainerCard'), 'no basic Fire Energy in hand')
        # basic Fire present but nothing to discard
        t2 = self.table()
        self.mine(t2, CHARCADET)
        t2.attach(BRAVERY_CHARM, t2.active(P1))   # only your own Tool
        self.hand_energy(t2, FIRE)
        bt2 = t2.put(BLOWTORCH, P1, 'hand')
        self.assertFalse(t2.can(bt2, 'UseTrainerCard'), 'no target')

    # --- Temple of Sinnoh ASR 155 ------------------------------------------
    async def test_temple_luminous_only_colorless(self):
        for temple in (False, True):
            t = self.table()
            if temple:
                t.stadium(TEMPLE, P2)
            arm = self.mine(t, ARMAROUGE_SVI, FIRE, 1)
            t.energy(arm, WATER, 1)
            t.attach(LUMINOUS, arm)
            with self.subTest(temple=temple):
                offer = t.attack_offer(arm, 'Flame Cannon')
                if temple:
                    self.assertIsNone(offer, 'Luminous provides only [C] under Temple')
                else:
                    self.assertIsNotNone(offer)

    async def test_temple_basic_energy_unaffected(self):
        t = self.table()
        t.stadium(TEMPLE, P1)
        arm = self.mine(t, ARMAROUGE_SVI, FIRE, 3)
        self.assertIsNotNone(t.attack_offer(arm, 'Flame Cannon'))

    async def test_temple_therapeutic_has_no_other_effect(self):
        for temple in (False, True):
            t = self.table()
            if temple:
                t.stadium(TEMPLE, P1)
            t.attach(THERAPEUTIC, self.opp)
            starmie = self.mine(t, STARMIE, WATER, 2)
            t.heads = True
            await t.attack(starmie, 'Star Freeze')
            with self.subTest(temple=temple):
                self.assertEqual(PARALYZED in t.conditions(self.opp), temple)

    # --- Armarouge SVI 41 --------------------------------------------------
    async def test_armarouge_fire_off(self):
        t = self.table()
        arm = self.mine(t, ARMAROUGE_SVI, zone='active')
        bench = self.mine(t, CHARCADET, zone='bench')
        fires = t.energy(bench, FIRE, 2)
        water = t.energy(bench, WATER, 1)
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [c for c in cards if self.is_basic(c, FIRE)][:1]
        t.picks = picks
        await t.use(arm, 'Fire Off')
        if t.ability_offer(arm, 'Fire Off') is not None:     # one Energy per use
            await t.use(arm, 'Fire Off')
        self.assertEqual(sorted(id(c) for c in fires),
                         sorted(id(c) for c in arm.children if self.is_basic(c, FIRE)))
        self.assertIn(water, list(bench.children))
        self.assertNotIn(water, offered, 'Water Energy must not be movable')
        self.assertIsNone(t.ability_offer(arm, 'Fire Off'),
                          'only non-Fire Energy left on the Bench')

    async def test_armarouge_fire_off_from_bench_armarouge(self):
        # Armarouge itself on the Bench can still use it; Active's Energy can't go back.
        t = self.table()
        active = self.mine(t, self.filler, FIRE, 2)
        arm = self.mine(t, ARMAROUGE_SVI, zone='bench')
        self.assertIsNone(t.ability_offer(arm, 'Fire Off'),
                          'no Fire Energy on the Bench to move')
        f = t.energy(arm, FIRE, 1)
        await t.use(arm, 'Fire Off')
        self.assertIn(f, list(active.children))

    async def test_armarouge_flame_cannon(self):
        t = self.table()
        arm = self.mine(t, ARMAROUGE_SVI, FIRE, 3)
        await t.attack(arm, 'Flame Cannon')
        self.assertEqual(400 - t.hp(self.opp), 90)
        self.assertIn(BURNED, t.conditions(self.opp))

    # --- Waitress ASC 215 --------------------------------------------------
    async def test_waitress_attaches_from_top6(self):
        t = self.table()
        self.mine(t, CHARCADET)
        bench = self.mine(t, self.filler, zone='bench')
        fire = t.deck(P1, [t.basic_energy(FIRE)] + [self.item] * 5)[0]   # 6th from top
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        w = t.put(WAITRESS, P1, 'hand')
        deck0 = len(t.zone(P1, 'deck'))
        await t.play(w)
        self.assertIn(fire, list(bench.children))
        self.assertEqual(len(t.zone(P1, 'deck')), deck0 - 1, 'others shuffled back')

    async def test_waitress_seventh_card_out_of_reach(self):
        t = self.table()
        char = self.mine(t, CHARCADET)
        fire = t.deck(P1, [t.basic_energy(FIRE)] + [self.item] * 6)[0]   # 7th from top
        t.deck(P1, [LUMINOUS])   # special Energy in top 6 doesn't count either
        w = t.put(WAITRESS, P1, 'hand')
        if t.can(w, 'UseTrainerCard'):
            await t.play(w)
        self.assertEqual(len(char.children), 0)
        self.assertIn(fire, t.zone(P1, 'deck'))

    # --- Staryu MEW 120: Swift ---------------------------------------------
    async def test_staryu_swift_ignores_weakness_resistance(self):
        for attr, val in ((AttrID.WEAKNESS_TYPES, [WATER.value]),
                          (AttrID.RESISTANCE_TYPES, WATER.value)):
            t = self.table()
            self.opp.set_attribute(attr, val)
            staryu = self.mine(t, STARYU, WATER, 2)
            await t.attack(staryu, 'Swift')
            with self.subTest(attr=attr):
                self.assertEqual(400 - t.hp(self.opp), 30)

    async def test_staryu_swift_ignores_defender_effects(self):
        # Turtwig TEF 10 Solid Shell: takes 20 less damage from attacks.
        t = Table(self)
        turtwig = self.neutral(t.put('SV05.Turtwig_10', P2, 'active'))
        char = self.mine(t, CHARCADET, FIRE, 1)
        await t.attack(char, 'Chop')                      # control: 10 - 20 -> 0
        self.assertEqual(400 - t.hp(turtwig), 0)
        t2 = Table(self)
        turtwig = self.neutral(t2.put('SV05.Turtwig_10', P2, 'active'))
        staryu = self.mine(t2, STARYU, WATER, 2)
        await t2.attack(staryu, 'Swift')
        self.assertEqual(400 - t2.hp(turtwig), 30)

    # --- Starmie EVO 31 ----------------------------------------------------
    async def test_starmie_space_beacon(self):
        t = self.table()
        starmie = self.mine(t, STARMIE)
        junk = t.put(self.item, P1, 'hand')
        es = [t.put(t.basic_energy(k), P1, 'discard') for k in (FIRE, WATER, PSY)]
        t.put(LUMINOUS, P1, 'discard')
        offered = []

        def picks(cards, count, prompt, display):
            offered.append(list(cards))
            if any(c is junk for c in cards):
                return [junk]
            return list(cards)[:count]
        t.picks = picks
        await t.use(starmie, 'Space Beacon')
        hand = t.zone(P1, 'hand')
        self.assertIn(junk, t.zone(P1, 'discard'))
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(self.is_basic(c) for c in hand))
        self.assertTrue(all(self.is_basic(c) for c in offered[-1]), 'Luminous not eligible')
        # once per turn
        t.put(self.item, P1, 'hand')
        self.assertIsNone(t.ability_offer(starmie, 'Space Beacon'))

    # BUG: Space Beacon lets you take back the card just discarded for its cost
    async def test_starmie_space_beacon_cannot_take_back_discarded(self):
        t = self.table()
        starmie = self.mine(t, STARMIE)
        fire = self.hand_energy(t, FIRE)
        water = t.put(t.basic_energy(WATER), P1, 'discard')
        offered = []

        def picks(cards, count, prompt, display):
            offered.append(list(cards))
            return list(cards)[:count]
        t.picks = picks
        if t.ability_offer(starmie, 'Space Beacon') is not None:
            await t.use(starmie, 'Space Beacon')
        self.assertIn(fire, t.zone(P1, 'discard'), "the discarded card can't be returned")
        self.assertNotIn(fire, t.zone(P1, 'hand'))

    async def test_starmie_space_beacon_needs_hand_card(self):
        t = self.table()
        starmie = self.mine(t, STARMIE)
        for k in (FIRE, WATER):
            t.put(t.basic_energy(k), P1, 'discard')
        self.assertIsNone(t.ability_offer(starmie, 'Space Beacon'), 'empty hand')

    async def test_starmie_star_freeze_tails(self):
        t = self.table()
        starmie = self.mine(t, STARMIE, WATER, 2)
        t.heads = False
        await t.attack(starmie, 'Star Freeze')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertNotIn(PARALYZED, t.conditions(self.opp))

    # --- Tyrogue MEG 71: Pow-Pow Punching ----------------------------------
    async def test_tyrogue_pow_pow_punching(self):
        for heads in (0, 3):
            t = self.table()
            ty = self.mine(t, TYROGUE)

            async def until_tails(ctx, title=''):
                return heads
            with patch.object(EffectContext, 'flip_until_tails', until_tails):
                await t.attack(ty, 'Pow-Pow Punching')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 10 + 30 * heads)

    # --- Lively Stadium SSP 180 --------------------------------------------
    async def test_lively_stadium_basics_both_sides(self):
        t = Table(self)
        mine = t.put(CHARCADET, P1, 'active')
        theirs = t.put(STARYU, P2, 'active')
        stage1 = t.put(ARMAROUGE_SVI, P1, 'bench')
        base = [effective_max_hp(t.board, p) for p in (mine, theirs, stage1)]
        t.stadium(LIVELY, P2)
        after = [effective_max_hp(t.board, p) for p in (mine, theirs, stage1)]
        self.assertEqual(base, [70, 60, 130])
        self.assertEqual(after, [100, 90, 130])

    # --- Armarouge SSP 34: Crimson Blaster ---------------------------------
    async def test_armarouge_crimson_blaster(self):
        t = self.table()
        arm = self.mine(t, ARMAROUGE_SSP, FIRE, 2)
        water = t.energy(arm, WATER, 1)
        target = t.put(self.filler, P2, 'bench')
        target.set_attribute(AttrID.HP, 400)
        target.set_attribute(AttrID.WEAKNESS_TYPES, [FIRE.value])   # not applied on Bench
        target.set_attribute(AttrID.RESISTANCE_TYPES, [])
        await t.attack(arm, 'Crimson Blaster')
        self.assertEqual(400 - t.hp(target), 180)
        self.assertEqual(400 - t.hp(self.opp), 0, 'no damage to the Active')
        self.assertEqual(list(arm.children), [water], 'only Fire Energy discarded')

    # --- Surfer SSP 187 ----------------------------------------------------
    async def test_surfer_switch_and_draw(self):
        t = self.table()
        a = self.mine(t, CHARCADET)
        b = self.mine(t, STARYU, zone='bench')
        t.put(self.item, P1, 'hand')
        s = t.put(SURFER, P1, 'hand')
        await t.play(s)
        self.assertIs(t.active(P1), b)
        self.assertIn(a, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 5)

    async def test_surfer_not_playable_without_bench(self):
        t = self.table()
        self.mine(t, CHARCADET)
        s = t.put(SURFER, P1, 'hand')
        self.assertFalse(t.can(s, 'UseTrainerCard'))

    async def test_surfer_full_hand_draws_nothing(self):
        t = self.table()
        self.mine(t, CHARCADET)
        self.mine(t, STARYU, zone='bench')
        for _ in range(6):
            t.put(self.item, P1, 'hand')
        s = t.put(SURFER, P1, 'hand')
        await t.play(s)
        self.assertEqual(len(t.zone(P1, 'hand')), 6)

    # --- Hassel TWM 151 ----------------------------------------------------
    async def _ko_my_active(self, t):
        """P2 knocks out P1's Active during P2's turn, then hand back to P1."""
        from spirit.game.data_utils import Attack
        title = next(a.title for a in def_for(self.opp.archetype_id).abilities
                     if isinstance(a, Attack) and a.damage)
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        t.next_turn()

    async def test_hassel_after_knockout(self):
        t = self.table()
        victim = self.mine(t, STARYU)
        victim.set_attribute(AttrID.HP, 10)
        self.mine(t, CHARCADET, zone='bench')
        await self._ko_my_active(t)
        self.assertIn(victim, t.zone(P1, 'discard'))
        t.deck(P1, [CHARCADET] * 8)
        h = t.put(HASSEL, P1, 'hand')
        self.assertTrue(t.can(h, 'UseTrainerCard'))
        hand0 = len(t.zone(P1, 'hand')) - 1
        await t.play(h)
        self.assertEqual(t.shown[-1], 8)
        self.assertEqual(len(t.zone(P1, 'hand')), hand0 + 3)

    async def test_hassel_not_playable_without_knockout(self):
        t = self.table()
        self.mine(t, STARYU)
        t.next_turn(); t.next_turn()
        h = t.put(HASSEL, P1, 'hand')
        self.assertFalse(t.can(h, 'UseTrainerCard'))

    # --- Morty's Conviction TEF 155 ----------------------------------------
    async def test_mortys_conviction(self):
        t = self.table()
        self.mine(t, CHARCADET)
        for _ in range(3):
            t.put(self.filler, P2, 'bench')
        junk = t.put(self.item, P1, 'hand')
        m = t.put(MORTY, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [junk] if junk in cards else list(cards)[:count]
        await t.play(m)
        self.assertIn(junk, t.zone(P1, 'discard'))
        self.assertIn(m, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_mortys_conviction_needs_other_card(self):
        t = self.table()
        self.mine(t, CHARCADET)
        t.put(self.filler, P2, 'bench')
        m = t.put(MORTY, P1, 'hand')
        self.assertFalse(t.can(m, 'UseTrainerCard'))

    async def test_mortys_conviction_counts_opponent_bench_only(self):
        t = self.table()
        self.mine(t, CHARCADET)
        for _ in range(2):
            self.mine(t, STARYU, zone='bench')
        t.put(self.filler, P2, 'bench')
        t.put(self.item, P1, 'hand')
        m = t.put(MORTY, P1, 'hand')
        await t.play(m)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)


if __name__ == '__main__':
    unittest.main()
