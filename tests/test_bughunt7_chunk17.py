"""Bug hunt round 7, chunk 17: Dusclops / Dusknoir (PRE), Espurr BST 60,
Meowstic SIT 82, Gutsy Pickaxe, Hisuian Growlithe / Arcanine, Joltik SCR 50,
Tyrunt FLI 68, Lisia's Appeal, Handheld Fan, Duskull BRS 60, Dusknoir BCR 63,
Cramorant LOR 50, Zarude CRE 19 -- each checked against its printed text,
including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
GRASS, FIGHT, LIGHT = PokemonTypes.GRASS, PokemonTypes.FIGHTING, PokemonTypes.LIGHTNING

DUSCLOPS, DUSKNOIR = 'SV085.Dusclops_36', 'SV085.Dusknoir_37'
ESPURR, MEOWSTIC = 'SWSH5.Espurr_60', 'SWSH12.Meowstic_82'
PICKAXE = 'SWSH10.GutsyPickaxe_145'
GROWLITHE, ARCANINE = 'SV06.HisuianGrowlithe_99', 'SV06.HisuianArcanine_100'
JOLTIK = 'SV07.Joltik_50'          # chunk path said BW8.Joltik_50 (wrong printing)
TYRUNT = 'SM6.Tyrunt_68'
LISIA = 'SV08.LisiasAppeal_179'
FAN = 'SV06.HandheldFan_150'
DUSKULL = 'SWSH9.Duskull_60'
DUSKNOIR_BCR = 'BW7.Dusknoir_63'
CRAMORANT = 'SWSH11.Cramorant_50'
ZARUDE = 'SWSH6.Zarude_19'
WEEZING = 'SWSH2.GalarianWeezing_113'
AURORA = 'SWSH1.AuroraEnergy_186'
STADIUM = 'SWSH3.RoseTower_169'


class Chunk17(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def clear(self, t, zone, pid=P1):
        area = t.board.find_player_area(pid, zone)
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def energies_on(self, p):
        return [c for c in p.children if self.is_energy(c)]

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Dusclops PRE 36 / Dusknoir PRE 37: Cursed Blast ---------------------
    async def test_cursed_blast_counters_and_self_ko(self):
        for spec, counters, zone in ((DUSCLOPS, 5, 'bench'), (DUSKNOIR, 13, 'active')):
            t = self.table()
            if zone == 'bench':
                self.mine(t, self.filler)
            ghost = self.mine(t, spec, zone=zone)
            if zone == 'active':
                self.mine(t, self.filler, zone='bench')
            target = t.put(self.filler, P2, 'bench')
            target.set_attribute(AttrID.HP, 400)
            t.pokemon = lambda c, p: target if target in c else c[0]
            prizes = len(t.zone(P2, 'prizes'))
            self.assertIsNotNone(t.ability_offer(ghost, 'Cursed Blast'))
            await t.use(ghost, 'Cursed Blast')
            with self.subTest(card=spec):
                self.assertEqual(400 - t.hp(target), counters * 10)
                self.assertEqual(t.hp(self.opp), 400)
                self.assertIn(ghost, t.zone(P1, 'discard'))
                self.assertEqual(len(t.zone(P2, 'prizes')), prizes - 1)

    async def test_cursed_blast_blocked_by_neutralizing_gas(self):
        t = self.table()
        self.clear(t, 'activePokemonArea', P2)
        weezing = self.mine(t, WEEZING, pid=P2)
        weezing.set_attribute(AttrID.HP, 400)
        self.mine(t, self.filler)
        ghost = self.mine(t, DUSCLOPS, zone='bench')
        self.assertIsNone(t.ability_offer(ghost, 'Cursed Blast'))

    # --- Dusknoir PRE 37: Shadow Bind ----------------------------------------
    async def test_shadow_bind_locks_retreat_next_turn_only(self):
        t = self.table()
        d = self.mine(t, DUSKNOIR, PSY, 3)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, WATER, 4)
        await t.attack(d, 'Shadow Bind')
        self.assertEqual(self.dealt(), 150)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))

    # --- Espurr BST 60: Focused Wish ------------------------------------------
    async def test_espurr_focused_wish(self):
        for heads, dmg in ((True, 40), (False, 20)):
            t = self.table()
            e = self.mine(t, ESPURR, PSY, 2)
            t.heads = heads
            await t.attack(e, 'Focused Wish')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), dmg)

    # --- Meowstic SIT 82: Inviting Ears ---------------------------------------
    async def test_meowstic_inviting_ears_on_evolve(self):
        for yes in (True, False):
            t = self.table()
            self.mine(t, self.filler)
            espurr = self.mine(t, ESPURR, zone='bench')
            sups = t.deck(P1, [LISIA, LISIA, LISIA])
            self.clear(t, 'hand')
            card = t.put(MEOWSTIC, P1, 'hand')
            t.yes = yes
            await t.play(card, targets=[espurr.entity_id])
            hand = t.zone(P1, 'hand')
            with self.subTest(yes=yes):
                self.assertIn(card, t.zone(P1, 'bench') + [c for c in espurr.children])
                self.assertEqual(sum(1 for c in hand if c in sups), 2 if yes else 0)

    async def test_meowstic_inviting_ears_not_an_activated_ability(self):
        t = self.table()
        m = self.mine(t, MEOWSTIC)
        t.deck(P1, [LISIA])
        self.assertIsNone(t.ability_offer(m, 'Inviting Ears'))

    # --- Gutsy Pickaxe ASR 145 ------------------------------------------------
    async def test_gutsy_pickaxe_fighting_energy_to_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        top = t.deck(P1, [t.basic_energy(FIGHT)])[0]
        await t.play(t.put(PICKAXE, P1, 'hand'))
        self.assertIn(top, bench.children)

    async def test_gutsy_pickaxe_other_card_to_hand(self):
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        top = t.deck(P1, [t.basic_energy(WATER)])[0]
        await t.play(t.put(PICKAXE, P1, 'hand'))
        self.assertIn(top, t.zone(P1, 'hand'))
        self.assertEqual(bench.children and self.energies_on(bench), [])

    async def test_gutsy_pickaxe_special_energy_is_not_fighting_energy_card(self):
        # "If it's a [F] Energy card" means a Basic Fighting Energy card;
        # Aurora Energy (provides every type while attached) goes to the hand.
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        top = t.deck(P1, [AURORA])[0]
        await t.play(t.put(PICKAXE, P1, 'hand'))
        self.assertNotIn(top, bench.children)
        self.assertIn(top, t.zone(P1, 'hand'))

    async def test_gutsy_pickaxe_not_playable_with_empty_deck(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, 'deck')
        card = t.put(PICKAXE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Hisuian Growlithe TWM 99 --------------------------------------------
    async def test_growlithe_blazing_destruction_discards_any_stadium(self):
        for owner in (P1, P2):
            t = self.table()
            g = self.mine(t, GROWLITHE)
            st = t.stadium(STADIUM, owner)
            self.assertIsNotNone(t.attack_offer(g, 'Blazing Destruction'))
            await t.attack(g, 'Blazing Destruction')
            with self.subTest(owner=owner):
                self.assertEqual(list(t.board.find_global_area('activeStadium').children), [])
                self.assertIn(st, t.zone(owner, 'discard'))

    async def test_growlithe_blazing_destruction_no_stadium_is_harmless(self):
        t = self.table()
        g = self.mine(t, GROWLITHE)
        await t.attack(g, 'Blazing Destruction')
        self.assertEqual(self.dealt(), 0)
        self.assertIn(g, t.board.pokemon_in_play(P1))

    async def test_growlithe_take_down_recoil(self):
        t = self.table()
        g = self.mine(t, GROWLITHE, FIGHT, 2)
        await t.attack(g, 'Take Down')
        self.assertEqual(self.dealt(), 40)
        self.assertEqual(t.damage(g), 10)

    # --- Hisuian Arcanine TWM 100 --------------------------------------------
    async def test_arcanine_proud_fangs_needs_damaged_bench(self):
        for case, dmg in (('bench', 120), ('active_only', 30), ('none', 30)):
            t = self.table()
            a = self.mine(t, ARCANINE)
            b = self.mine(t, self.filler, zone='bench')
            if case == 'bench':
                b.set_attribute(AttrID.HP, t.hp(b) - 10)
            elif case == 'active_only':
                a.set_attribute(AttrID.HP, t.hp(a) - 50)
            await t.attack(a, 'Proud Fangs')
            with self.subTest(case=case):
                self.assertEqual(self.dealt(), dmg)

    async def test_arcanine_searing_flame_burns(self):
        t = self.table()
        a = self.mine(t, ARCANINE, FIGHT, 3)
        await t.attack(a, 'Searing Flame')
        self.assertEqual(self.dealt(), 90)
        self.assertIn(BURNED, t.conditions(self.opp))

    # --- Joltik SCR 50: Jolting Charge ---------------------------------------
    async def test_joltik_jolting_charge_two_of_each(self):
        t = self.table()
        j = self.mine(t, JOLTIK, WATER, 1)
        bench = self.mine(t, self.filler, zone='bench')
        gs = t.deck(P1, [t.basic_energy(GRASS)] * 3)
        ls = t.deck(P1, [t.basic_energy(LIGHT)] * 3)
        fs = t.deck(P1, [t.basic_energy(FIGHT)])
        seen = []

        async def groups(pid, source_id, specs, prompt, display_cards=None, total=None, any_of=False):
            seen.extend(specs)
            return [[c.entity_id for c in s['cards'][:s['count']]] for s in specs]

        t.pokemon = lambda c, p: bench if bench in c else c[0]
        with patch.object(t.session, 'prompt_card_chooser_groups', groups):
            await t.attack(j, 'Jolting Charge')
        self.assertEqual([s['count'] for s in seen], [2, 2])
        attached = [c for p in t.board.pokemon_in_play(P1) for c in p.children]
        self.assertEqual(sum(1 for c in gs if c in attached), 2)
        self.assertEqual(sum(1 for c in ls if c in attached), 2)
        self.assertFalse(any(c in attached for c in fs))
        self.assertFalse(any(c in s['cards'] for s in seen for c in fs))

    # --- Tyrunt FLI 68: Crunch ------------------------------------------------
    async def test_tyrunt_crunch_discards_on_heads(self):
        for heads in (True, False):
            t = self.table()
            ty = self.mine(t, TYRUNT, FIGHT, 1)
            e = t.energy(self.opp, WATER, 1)
            t.heads = heads
            await t.attack(ty, 'Crunch')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), 20)
                self.assertEqual(e in self.opp.children, not heads)
                self.assertEqual(e in t.zone(P2, 'discard'), heads)

    # --- Lisia's Appeal SSP 179 ----------------------------------------------
    async def test_lisias_appeal_switches_basic_and_confuses(self):
        t = self.table()
        self.mine(t, self.filler)
        evolved = self.mine(t, MEOWSTIC, zone='bench', pid=P2)
        basic = self.mine(t, ESPURR, zone='bench', pid=P2)
        seen = []
        t.pokemon = lambda c, p: (seen.extend(c), c[0])[1]
        card = t.put(LISIA, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertNotIn(evolved, seen)
        self.assertIs(t.active(P2), basic)
        self.assertIn(CONFUSED, t.conditions(basic))
        self.assertIn(self.opp, t.zone(P2, 'bench'))

    async def test_lisias_appeal_needs_benched_basic(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, MEOWSTIC, zone='bench', pid=P2)
        self.mine(t, ESPURR, zone='bench')          # my own Basic doesn't count
        card = t.put(LISIA, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Handheld Fan TWM 150 -------------------------------------------------
    async def _fan_scenario(self, t, holder_active=True, opp_bench=True):
        wall = self.mine(t, self.filler)
        wall.set_attribute(AttrID.HP, 500)
        holder = wall
        if not holder_active:
            holder = self.mine(t, self.filler, zone='bench')
        fan = t.put(FAN, P1, 'hand')
        await t.play(fan, targets=[holder.entity_id])
        self.assertIn(fan, holder.children)
        bench = t.put(self.filler, P2, 'bench') if opp_bench else None
        title, _ = self.filler_attack()
        es = t.energy(self.opp, WATER, 4)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return bench, es

    async def test_handheld_fan_moves_attacker_energy_to_bench(self):
        t = self.table()
        bench, es = await self._fan_scenario(t)
        self.assertEqual(len(self.energies_on(self.opp)), 3)
        self.assertEqual(len(self.energies_on(bench)), 1)

    async def test_handheld_fan_benched_holder_does_nothing(self):
        t = self.table()
        bench, es = await self._fan_scenario(t, holder_active=False)
        self.assertEqual(len(self.energies_on(self.opp)), 4)
        self.assertEqual(self.energies_on(bench), [])

    async def test_handheld_fan_no_opponent_bench(self):
        t = self.table()
        _, es = await self._fan_scenario(t, opp_bench=False)
        self.assertEqual(len(self.energies_on(self.opp)), 4)

    # --- Duskull BRS 60: Perplex ----------------------------------------------
    async def test_duskull_perplex(self):
        for heads in (True, False):
            t = self.table()
            d = self.mine(t, DUSKULL, PSY, 1)
            t.heads = heads
            await t.attack(d, 'Perplex')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), 10)
                self.assertEqual(CONFUSED in t.conditions(self.opp), heads)

    # --- Dusknoir BCR 63: Sinister Hand / Shadow Punch -----------------------
    async def test_dusknoir_bcr_sinister_hand_moves_opponent_damage(self):
        t = self.table()
        d = self.mine(t, DUSKNOIR_BCR)
        full = t.damage(self.opp) + t.hp(self.opp)     # printed max HP
        self.opp.set_attribute(AttrID.HP, full - 30)
        target = t.put(self.filler, P2, 'bench')
        hp = t.hp(target)
        t.pokemon = lambda c, p: (self.opp if self.opp in c else target) if 'from' in p else target
        self.assertIsNotNone(t.ability_offer(d, 'Sinister Hand'))

        async def placement(*a, **k):
            return {self.opp.entity_id: 2}
        with patch.object(t.session, 'prompt_damage_counter_placement', placement):
            await t.use(d, 'Sinister Hand')
        self.assertEqual(t.hp(self.opp), full - 10)
        self.assertEqual(hp - t.hp(target), 20)
        # still usable (as often as you like) while damage remains
        self.assertIsNotNone(t.ability_offer(d, 'Sinister Hand'))

    async def test_dusknoir_bcr_sinister_hand_needs_opponent_damage(self):
        t = self.table()
        d = self.mine(t, DUSKNOIR_BCR)
        t.put(self.filler, P2, 'bench')
        mine = self.mine(t, self.filler, zone='bench')
        mine.set_attribute(AttrID.HP, 50)              # my own damage doesn't count
        self.assertIsNone(t.ability_offer(d, 'Sinister Hand'))

    async def test_dusknoir_bcr_shadow_punch_ignores_resistance(self):
        t = self.table()
        d = self.mine(t, DUSKNOIR_BCR, PSY, 4)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, PSY.value)
        await t.attack(d, 'Shadow Punch')
        self.assertEqual(self.dealt(), 60)

    # --- Cramorant LOR 50: Lost Provisions / Spit Innocently -----------------
    async def test_cramorant_lost_provisions_threshold(self):
        for lost, offered in ((4, True), (3, False)):
            t = self.table()
            c = self.mine(t, CRAMORANT)
            for _ in range(lost):
                t.put(self.item, P1, 'lostZone')
            for _ in range(5):
                t.put(self.item, P2, 'lostZone')       # opponent's Lost Zone doesn't count
            with self.subTest(lost=lost):
                self.assertEqual(t.attack_offer(c, 'Spit Innocently') is not None, offered)

    async def test_cramorant_spit_innocently_ignores_weakness(self):
        t = self.table()
        c = self.mine(t, CRAMORANT, WATER, 3)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [WATER.value])
        await t.attack(c, 'Spit Innocently')
        self.assertEqual(self.dealt(), 110)

    # --- Zarude CRE 19: Pack Call / Repeated Whip ----------------------------
    async def _pack_call(self, first_player, turn):
        t = self.table()
        z = self.mine(t, ZARUDE, GRASS, 1)
        grass = t.deck(P1, [ZARUDE, ZARUDE, ZARUDE, ZARUDE])
        t.deck(P1, [ESPURR])
        t.session.first_player_id = first_player
        t.state.turn_number = turn
        self.clear(t, 'hand')
        await t.attack(z, 'Pack Call')
        hand = t.zone(P1, 'hand')
        return sum(1 for c in hand if c in grass), len(hand)

    async def test_zarude_pack_call_three_when_second_first_turn(self):
        got, total = await self._pack_call(P2, 2)
        self.assertEqual((got, total), (3, 3))

    async def test_zarude_pack_call_one_otherwise(self):
        for first, turn in ((P1, 3), (P2, 4)):
            got, total = await self._pack_call(first, turn)
            with self.subTest(first=first, turn=turn):
                self.assertEqual((got, total), (1, 1))

    async def test_zarude_repeated_whip_counts_grass_only(self):
        t = self.table()
        z = self.mine(t, ZARUDE, GRASS, 2)
        t.energy(z, WATER, 1)
        await t.attack(z, 'Repeated Whip')
        self.assertEqual(self.dealt(), 100)


if __name__ == '__main__':
    unittest.main()
