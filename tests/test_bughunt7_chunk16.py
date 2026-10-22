"""Bug hunt round 7, chunk 16: Cheren's Care, Rose Tower, Prism Tower, Delphox
(FLI 17 / CRI 13), Magikarp, Turbo Patch, Espurr, Meowstic, Unown HAND, Zarude,
Tyrunt, Tyrantrum, Antique Jaw Fossil, Duskull -- each checked against its
printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
GRASS, FIGHT, DARK = PokemonTypes.GRASS, PokemonTypes.FIGHTING, PokemonTypes.DARKNESS

CHEREN = 'SWSH9.CherensCare_134'
ROSE, PRISM = 'SWSH3.RoseTower_169', 'ME4.PrismTower_80'
DELPHOX_FLI, DELPHOX_CRI = 'SM6.Delphox_17', 'ME4.Delphox_13'
MAGIKARP = 'SV035.Magikarp_129'
TURBO = 'SWSH3.TurboPatch_172'
ESPURR, MEOWSTIC = 'SM10.Espurr_79', 'SM3.Meowstic_60'
UNOWN = 'SM8.Unown_91'
ZARUDE = 'SV08.Zarude_11'
TYRUNT, TYRANTRUM, JAW = 'ME3.Tyrunt_44', 'ME3.Tyrantrum_45', 'ME3.AntiqueJawFossil_68'
DUSKULL = 'SV085.Duskull_35'
THERAPEUTIC = 'SV2.TherapeuticEnergy_193'


class Chunk16(unittest.IsolatedAsyncioTestCase):
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

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def fill_hand(self, t, n, pid=P1):
        for _ in range(n):
            t.put(self.item, pid, 'hand')

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Cheren's Care BRS 134 ---------------------------------------------
    async def test_cherens_care_returns_damaged_colorless_and_attachments(self):
        t = self.table()
        snorlax = self.mine(t, self.filler, WATER, 2)
        snorlax.set_attribute(AttrID.HP, snorlax.get_attribute(AttrID.HP) - 30)
        bench = self.mine(t, ESPURR, zone='bench')
        card = t.put(CHEREN, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertIn(snorlax, hand)
        self.assertEqual(sum(1 for c in hand if self.is_energy(c)), 2)
        self.assertIs(t.active(P1), bench)

    async def test_cherens_care_only_offers_damaged_colorless(self):
        t = self.table()
        active = self.mine(t, self.filler)                 # undamaged Colorless
        hurt = self.mine(t, self.filler, WATER, 1, zone='bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 10)
        psychic = self.mine(t, ESPURR, zone='bench')
        psychic.set_attribute(AttrID.HP, 30)
        seen = []
        t.pokemon = lambda c, p: (seen.extend(c), c[0])[1]
        await t.play(t.put(CHEREN, P1, 'hand'))
        self.assertEqual(seen, [hurt])
        self.assertIn(hurt, t.zone(P1, 'hand'))
        self.assertIs(t.active(P1), active)
        self.assertIn(psychic, t.zone(P1, 'bench'))

    async def test_cherens_care_not_playable_without_damaged_colorless(self):
        t = self.table()
        self.mine(t, self.filler)                          # undamaged Colorless
        espurr = self.mine(t, ESPURR, zone='bench')        # damaged Psychic
        espurr.set_attribute(AttrID.HP, 30)
        card = t.put(CHEREN, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Rose Tower DAA 169 --------------------------------------------------
    async def test_rose_tower_draws_to_three_for_both_players(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(ROSE, P1)
        self.clear_hand(t)
        self.fill_hand(t, 1)
        await t.do(next(iter(t.offers(stadium, None, P1))))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(t.offers(stadium, None, P1), [])       # once per turn
        t.next_turn()
        self.clear_hand(t, P2)
        await t.do(next(iter(t.offers(stadium, None, P2))), pid=P2)
        self.assertEqual(len(t.zone(P2, 'hand')), 3)

    async def test_rose_tower_not_offered_with_three_cards(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(ROSE, P2)
        self.clear_hand(t)
        self.fill_hand(t, 3)
        self.assertEqual(t.offers(stadium, None, P1), [])

    # --- Prism Tower CRI 80 --------------------------------------------------
    async def test_prism_tower_discard_two_draw_one(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(PRISM, P2)
        self.clear_hand(t)
        self.fill_hand(t, 3)
        discard_before = len(t.zone(P1, 'discard'))
        deck_before = len(t.zone(P1, 'deck'))
        await t.do(next(iter(t.offers(stadium, None, P1))))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(len(t.zone(P1, 'discard')) - discard_before, 2)
        self.assertEqual(deck_before - len(t.zone(P1, 'deck')), 1)
        self.assertEqual(t.offers(stadium, None, P1), [])

    async def test_prism_tower_needs_two_cards(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(PRISM, P1)
        self.clear_hand(t)
        self.fill_hand(t, 1)
        self.assertEqual(t.offers(stadium, None, P1), [])

    # --- Delphox FLI 17: Mystical Torch / Fire Spin --------------------------
    async def test_delphox_mystical_torch_burns_once_per_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        delphox = self.mine(t, DELPHOX_FLI, zone='bench')     # works from the Bench
        await t.use(delphox, 'Mystical Torch')
        self.assertIn(BURNED, t.conditions(self.opp))
        self.assertIsNone(t.ability_offer(delphox, 'Mystical Torch'))
        self.assertEqual(t.conditions(t.active(P1)), set())

    async def test_delphox_fire_spin_discards_two(self):
        t = self.table()
        delphox = self.mine(t, DELPHOX_FLI, FIRE, 4)
        await t.attack(delphox, 'Fire Spin')
        self.assertEqual(self.dealt(), 150)
        self.assertEqual(len([c for c in delphox.children if self.is_energy(c)]), 2)

    # --- Delphox CRI 13: Flaring Magic / Energized Storm ---------------------
    async def test_delphox_flaring_magic_draws_to_seven(self):
        t = self.table()
        self.mine(t, self.filler)
        delphox = self.mine(t, DELPHOX_CRI, zone='bench')
        self.clear_hand(t)
        fire = t.put(t.basic_energy(FIRE), P1, 'hand')
        self.fill_hand(t, 2)
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is fire][:count]
        await t.use(delphox, 'Flaring Magic')
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_delphox_flaring_magic_needs_basic_fire(self):
        t = self.table()
        self.mine(t, self.filler)
        delphox = self.mine(t, DELPHOX_CRI, zone='bench')
        self.clear_hand(t)
        t.put(t.basic_energy(WATER), P1, 'hand')
        self.fill_hand(t, 2)
        self.assertIsNone(t.ability_offer(delphox, 'Flaring Magic'))

    async def test_delphox_energized_storm_counts_all_pokemon(self):
        t = self.table()
        delphox = self.mine(t, DELPHOX_CRI, FIRE, 2)
        bench = self.mine(t, self.filler, WATER, 1, zone='bench')
        t.energy(self.opp, WATER, 2)
        opp_bench = t.put(self.filler, P2, 'bench')
        t.energy(opp_bench, WATER, 1)
        await t.attack(delphox, 'Energized Storm')
        self.assertEqual(self.dealt(), 30 * 6)

    # --- Magikarp MEW 129: Splashy Splash ------------------------------------
    async def test_magikarp_splashy_splash_draws_per_heads(self):
        for heads in (2, 0):
            t = self.table()
            karp = self.mine(t, MAGIKARP, WATER, 1)
            self.clear_hand(t)
            with patch.object(EffectContext, 'flip_until_tails', AsyncMock(return_value=heads)):
                await t.attack(karp, 'Splashy Splash')
            with self.subTest(heads=heads):
                self.assertEqual(len(t.zone(P1, 'hand')), heads)
                self.assertEqual(self.dealt(), 0)

    # --- Turbo Patch DAA 172 -------------------------------------------------
    async def test_turbo_patch_heads_attaches_basic_energy_to_basic(self):
        for heads in (True, False):
            t = self.table()
            espurr = self.mine(t, ESPURR)
            energy = t.put(t.basic_energy(PSY), P1, 'discard')
            card = t.put(TURBO, P1, 'hand')
            t.heads = heads
            await t.play(card)
            with self.subTest(heads=heads):
                self.assertEqual(energy in espurr.children, heads)
                self.assertEqual(energy in t.zone(P1, 'discard'), not heads)

    async def test_turbo_patch_not_playable_without_basic_or_energy(self):
        t = self.table()
        self.mine(t, MEOWSTIC)                     # Stage 1 only
        t.put(t.basic_energy(PSY), P1, 'discard')
        card = t.put(TURBO, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        t2 = self.table()
        self.mine(t2, ESPURR)                      # Basic, but no energy in discard
        card2 = t2.put(TURBO, P1, 'hand')
        self.assertFalse(t2.can(card2, 'UseTrainerCard'))

    # --- Espurr UNB 79: Caturday / Ear Kinesis -------------------------------
    async def test_espurr_caturday_draws_and_sleeps(self):
        t = self.table()
        espurr = self.mine(t, ESPURR, PSY, 1)
        self.clear_hand(t)
        await t.attack(espurr, 'Caturday')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertIn(ASLEEP, t.conditions(espurr))

    async def test_espurr_caturday_empty_deck_no_sleep(self):
        t = self.table()
        espurr = self.mine(t, ESPURR, PSY, 1)
        deck = t.board.find_player_area(P1, 'deck')
        for c in list(deck.children):
            deck.remove_child(c)
        self.clear_hand(t)
        await t.attack(espurr, 'Caturday')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertNotIn(ASLEEP, t.conditions(espurr))

    async def test_espurr_ear_kinesis_hits_damaged_bench(self):
        t = self.table()
        espurr = self.mine(t, ESPURR, PSY, 3)
        self.opp.set_attribute(AttrID.HP, 370)          # 3 counters on the Active
        target = t.put(self.filler, P2, 'bench')
        target.set_attribute(AttrID.HP, t.hp(target) - 30)       # 3 counters
        t.put(self.filler, P2, 'bench')                          # undamaged decoy
        t.pokemon = lambda c, p: target if target in c else c[0]
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is target][:count] or cards[:count]
        await t.attack(espurr, 'Ear Kinesis')
        self.assertEqual(t.damage(target), 30 + 60)
        self.assertEqual(t.hp(self.opp), 370)

    # --- Meowstic BUS 60: Allure / Hand Kinesis ------------------------------
    async def test_meowstic_allure_draws_three(self):
        t = self.table()
        m = self.mine(t, MEOWSTIC, PSY, 1)
        self.clear_hand(t)
        await t.attack(m, 'Allure')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_meowstic_hand_kinesis_counts_hand(self):
        for n in (4, 0):
            t = self.table()
            m = self.mine(t, MEOWSTIC, PSY, 2)
            self.clear_hand(t)
            self.fill_hand(t, n)
            await t.attack(m, 'Hand Kinesis')
            with self.subTest(hand=n):
                self.assertEqual(self.dealt(), 10 * n)

    # --- Unown LOT 91: HAND --------------------------------------------------
    async def test_unown_hand_wins_with_35_active(self):
        t = self.table()
        unown = self.mine(t, UNOWN)
        self.clear_hand(t)
        self.fill_hand(t, 35)
        t.session.end_game = AsyncMock()
        self.assertIsNotNone(t.ability_offer(unown, 'HAND'))
        await t.use(unown, 'HAND')
        t.session.end_game.assert_awaited()
        self.assertEqual(t.session.end_game.await_args.args[0], P1)

    async def test_unown_hand_not_on_bench_or_34_cards(self):
        t = self.table()
        self.mine(t, self.filler)
        unown = self.mine(t, UNOWN, zone='bench')
        self.clear_hand(t)
        self.fill_hand(t, 35)
        self.assertIsNone(t.ability_offer(unown, 'HAND'))
        t2 = self.table()
        unown2 = self.mine(t2, UNOWN)
        self.clear_hand(t2)
        self.fill_hand(t2, 34)
        self.assertIsNone(t2.ability_offer(unown2, 'HAND'))

    # --- Zarude SSP 11: Leaf Drain / Jungle Whip -----------------------------
    async def test_zarude_leaf_drain_heals_20(self):
        t = self.table()
        z = self.mine(t, ZARUDE, GRASS, 1)
        z.set_attribute(AttrID.HP, t.hp(z) - 50)
        await t.attack(z, 'Leaf Drain')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(t.damage(z), 30)

    async def test_zarude_jungle_whip_optional_bonus(self):
        for yes, dealt in ((True, 160), (False, 80)):
            t = self.table()
            z = self.mine(t, ZARUDE, GRASS, 3)
            self.clear_hand(t)
            t.yes = yes
            await t.attack(z, 'Jungle Whip')
            with self.subTest(yes=yes):
                self.assertEqual(self.dealt(), dealt)
                energies = [c for c in z.children if self.is_energy(c)]
                self.assertEqual(len(energies), 0 if yes else 3)
                self.assertEqual(len(t.zone(P1, 'hand')), 3 if yes else 0)

    # --- Tyrunt POR 44: Get Angry --------------------------------------------
    async def test_tyrunt_get_angry_scales_with_counters(self):
        for counters in (3, 0):
            t = self.table()
            ty = self.mine(t, TYRUNT, FIGHT, 2)
            ty.set_attribute(AttrID.HP, t.hp(ty) - 10 * counters)
            await t.attack(ty, 'Get Angry')
            with self.subTest(counters=counters):
                self.assertEqual(self.dealt(), 20 * counters)

    # --- Tyrantrum POR 45: Tyrannically Gutsy / Wreak Havoc ------------------
    async def test_tyrantrum_gutsy_only_with_special_energy(self):
        t = self.table()
        ty = self.mine(t, TYRANTRUM)
        from spirit.game.session.passives import effective_max_hp
        t.energy(ty, FIGHT, 1)
        self.assertEqual(effective_max_hp(t.board, ty), 180)
        special = t.put(THERAPEUTIC, P1, 'hand')
        await t.play(special, targets=[ty.entity_id])
        self.assertIn(special, ty.children)
        self.assertEqual(effective_max_hp(t.board, ty), 330)

    async def test_tyrantrum_wreak_havoc_mills_per_heads(self):
        for heads in (2, 0):
            t = self.table()
            ty = self.mine(t, TYRANTRUM, FIGHT, 2)
            before = len(t.zone(P2, 'deck'))
            with patch.object(EffectContext, 'flip_until_tails', AsyncMock(return_value=heads)):
                await t.attack(ty, 'Wreak Havoc')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), 160)
                self.assertEqual(before - len(t.zone(P2, 'deck')), heads)

    # --- Antique Jaw Fossil POR 68: Intimidating Jaw -------------------------
    async def test_jaw_fossil_reduces_only_when_active(self):
        for active in (True, False):
            t = self.table()
            title, dmg = self.filler_attack()
            wall = self.mine(t, self.filler)
            wall.set_attribute(AttrID.HP, 500)
            card = t.put(JAW, P1, 'hand')
            await t.play(card)
            fossil = next(p for p in t.zone(P1, 'bench')
                          if def_for(p.archetype_id).display_name == 'Antique Jaw Fossil')
            if active:
                await t._run(lambda: EffectContext(t.session, P1, fossil, None)
                             .switch_active(P1, fossil))
                fossil.set_attribute(AttrID.WEAKNESS_TYPES, [])
                fossil.set_attribute(AttrID.RESISTANCE_TYPES, [])
            victim = t.active(P1)
            before = t.hp(victim)
            t.energy(self.opp, WATER, 5)
            t.next_turn()
            await t.attack(self.opp, title, pid=P2)
            with self.subTest(active=active, dmg=dmg):
                self.assertIn(victim, t.board.pokemon_in_play(P1))
                self.assertEqual(before - t.hp(victim), dmg - 30 if active else dmg)

    # --- Duskull PRE 35: Come and Get You ------------------------------------
    async def test_duskull_benches_up_to_three(self):
        t = self.table()
        d = self.mine(t, DUSKULL, PSY, 1)
        for _ in range(4):
            t.put(DUSKULL, P1, 'discard')
        await t.attack(d, 'Come and Get You')
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Duskull'] * 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_duskull_respects_bench_space(self):
        t = self.table()
        d = self.mine(t, DUSKULL, PSY, 1)
        for _ in range(4):
            self.mine(t, self.filler, zone='bench')
        for _ in range(3):
            t.put(DUSKULL, P1, 'discard')
        await t.attack(d, 'Come and Get You')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)
        self.assertEqual(t.names(t.zone(P1, 'discard')).count('Duskull'), 2)


if __name__ == '__main__':
    unittest.main()
