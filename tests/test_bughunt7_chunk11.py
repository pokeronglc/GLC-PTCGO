"""Bug hunt round 7, chunk 11: Oddish/Gloom, Pignite x2, Team Rocket's
Watchtower, Meditite x2/Medicham, Yamask/Cofagrigus, Brock's Grit,
Pokemon League Headquarters, Gouging Fire, Meowth/Persian -- each card
checked against its text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED, BURNED, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

GRASS, FIRE, WATER = PokemonTypes.GRASS, PokemonTypes.FIRE, PokemonTypes.WATER
FIGHT, PSY = PokemonTypes.FIGHTING, PokemonTypes.PSYCHIC

ODDISH, GLOOM = 'SM10.Oddish_5', 'SV035.Gloom_44'
PIGNITE_BCR, PIGNITE_ASC = 'BW7.Pignite_25', 'ME2PT5.Pignite_30'
WATCHTOWER = 'SV10.TeamRocketsWatchtower_180'
MEDITITE_UNM, MEDITITE_ASC, MEDICHAM = 'SM11.Meditite_109', 'ME2PT5.Meditite_103', 'XY5.Medicham_81'
YAMASK, COFAGRIGUS = 'SM8.Yamask_99', 'SV08.Cofagrigus_83'
BROCKS_GRIT = 'SM9.BrocksGrit_135'
LEAGUE_HQ = 'SV3.PokmonLeagueHeadquarters_192'
GOUGING_FIRE = 'SV08.GougingFire_38'
MEOWTH, PERSIAN = 'SM10.Meowth_147', 'SM9.Persian_126'
BIBAREL = 'SWSH9.Bibarel_121'          # Colorless, activated Ability
MISMAGIUS = 'SM10.Mismagius_78'        # Psychic, activated Ability


class Chunk11(unittest.IsolatedAsyncioTestCase):
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

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    def is_basic_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    # --- Oddish UNB 5: Stun Spore -------------------------------------------
    async def test_oddish_stun_spore(self):
        for heads in (True, False):
            t = self.table()
            oddish = self.mine(t, ODDISH, GRASS, 1)
            t.heads = heads
            await t.attack(oddish, 'Stun Spore')
            with self.subTest(heads=heads):
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)
                self.assertEqual(self.dealt(), 0)

    # --- Gloom MEW 44: Semi-Blooming Energy ---------------------------------
    async def test_gloom_semi_blooming_attaches_basic_energy_from_top3(self):
        t = self.table()
        oddish = self.mine(t, ODDISH)
        bench = self.mine(t, self.filler, zone='bench')
        top = t.deck(P1, [t.basic_energy(GRASS), self.item, t.basic_energy(WATER)])
        gloom = t.put(GLOOM, P1, 'hand')
        t.yes = True
        t.picks = lambda cards, count, prompt, display: [c for c in cards if self.is_basic_energy(c)]
        t.pokemon = lambda cands, prompt: next((c for c in cands if c is bench), cands[0])
        await t.play(gloom, targets=[oddish.entity_id])
        self.assertIs(t.active(P1), gloom)
        attached = [c for p in (gloom, bench) for c in p.children if self.is_basic_energy(c)]
        self.assertEqual(len(attached), 2)
        self.assertNotIn(top[0], t.zone(P1, 'deck'))
        self.assertNotIn(top[2], t.zone(P1, 'deck'))
        self.assertIn(top[1], t.zone(P1, 'deck'))       # non-Energy shuffled back
        self.assertEqual(len(t.zone(P1, 'deck')), 31)

    async def test_gloom_semi_blooming_only_sees_top_three(self):
        t = self.table()
        oddish = self.mine(t, ODDISH)
        # Energy 4th from the top must not be found.
        e4 = t.deck(P1, [t.basic_energy(GRASS), self.item, self.item, self.item])[0]
        gloom = t.put(GLOOM, P1, 'hand')
        t.yes = True
        t.picks = lambda cards, count, prompt, display: [c for c in cards if self.is_basic_energy(c)]
        await t.play(gloom, targets=[oddish.entity_id])
        self.assertEqual([c for c in gloom.children if self.is_basic_energy(c)], [])
        self.assertIn(e4, t.zone(P1, 'deck'))

    async def test_gloom_not_triggered_when_benched_directly(self):
        """Gloom is a Stage 1; it can't be put in play without evolving, and
        moving it into play by other means must not fire the evolve trigger."""
        t = self.table()
        gloom = t.put(GLOOM, P1, 'hand')
        self.assertFalse(t.can(gloom, 'DefaultPokemonPlayAbility'))

    # --- Pignite BCR 25: Firebreathing --------------------------------------
    async def test_pignite_bcr_firebreathing(self):
        for heads, expected in ((True, 60), (False, 40)):
            t = self.table()
            pig = self.mine(t, PIGNITE_BCR, FIRE, 3)
            t.heads = heads
            await t.attack(pig, 'Firebreathing')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), expected)

    # --- Pignite ASC 30: Super Singe ----------------------------------------
    async def test_pignite_asc_super_singe_burns(self):
        t = self.table()
        pig = self.mine(t, PIGNITE_ASC, FIRE, 3)
        await t.attack(pig, 'Super Singe')
        self.assertEqual(self.dealt(), 70)
        self.assertIn(BURNED, t.conditions(self.opp))
        self.assertNotIn(BURNED, t.conditions(pig))

    async def test_pignite_asc_super_singe_needs_two_fire(self):
        t = self.table()
        pig = self.mine(t, PIGNITE_ASC, FIRE, 1)
        t.energy(pig, WATER, 2)
        self.assertIsNone(t.attack_offer(pig, 'Super Singe'))

    # --- Team Rocket's Watchtower DRI 180 -----------------------------------
    async def test_watchtower_removes_colorless_abilities_both_sides(self):
        t = self.table()
        bib = self.mine(t, BIBAREL, zone='bench')
        self.assertIsNotNone(t.ability_offer(bib, 'Industrious Incisors'))
        t.stadium(WATCHTOWER, P2)
        self.assertIsNone(t.ability_offer(bib, 'Industrious Incisors'))
        # Opponent's Colorless Pokémon too (even when P1 owns the Stadium).
        t2 = self.table()
        t2.stadium(WATCHTOWER, P1)
        opp_bib = self.mine(t2, BIBAREL, zone='bench', pid=P2)
        t2.next_turn()
        self.assertIsNone(t2.ability_offer(opp_bib, 'Industrious Incisors', pid=P2))

    async def test_watchtower_leaves_non_colorless_abilities(self):
        t = self.table()
        t.stadium(WATCHTOWER, P1)
        mis = self.mine(t, MISMAGIUS, zone='bench')
        self.assertIsNotNone(t.ability_offer(mis, 'Mysterious Message'))

    # --- Meditite UNM 109: Spirited Headbutt --------------------------------
    async def test_meditite_spirited_headbutt_locked_next_turn_only(self):
        t = self.table()
        med = self.mine(t, MEDITITE_UNM, FIGHT, 1)
        await t.attack(med, 'Spirited Headbutt')
        self.assertEqual(self.dealt(), 40)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(med, 'Spirited Headbutt'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(med, 'Spirited Headbutt'))

    # --- Meditite ASC 103: Collect ------------------------------------------
    async def test_meditite_asc_collect_draws_one(self):
        t = self.table()
        med = self.mine(t, MEDITITE_ASC, FIGHT, 1)
        top = t.deck(P1, [self.filler])[0]
        await t.attack(med, 'Collect')
        self.assertEqual(t.zone(P1, 'hand'), [top])
        self.assertEqual(self.dealt(), 0)

    # --- Medicham PRC 81 ------------------------------------------------------
    async def test_medicham_calm_mind_heals_30(self):
        t = self.table()
        m = self.mine(t, MEDICHAM, FIGHT, 1)
        m.set_attribute(AttrID.HP, 40)               # 50 damage
        await t.attack(m, 'Calm Mind')
        self.assertEqual(t.damage(m), 20)
        self.assertEqual(self.dealt(), 0)

    async def test_medicham_yoga_kick_ignores_weakness_resistance(self):
        for attr, value in ((AttrID.WEAKNESS_TYPES, [FIGHT.value]),
                            (AttrID.RESISTANCE_TYPES, FIGHT.value)):
            t = self.table()
            self.opp.set_attribute(attr, value)
            m = self.mine(t, MEDICHAM, FIGHT, 2)
            await t.attack(m, 'Yoga Kick')
            with self.subTest(attr=attr):
                self.assertEqual(self.dealt(), 30)

    async def test_medicham_may_attack_twice_but_not_three_times(self):
        t = self.table()
        m = self.mine(t, MEDICHAM, FIGHT, 2)
        ends = await t.attack(m, 'Yoga Kick')      # True = the turn ends
        self.assertFalse(ends)
        self.assertIsNotNone(t.attack_offer(m, 'Yoga Kick'))
        ends = await t.attack(m, 'Yoga Kick')
        self.assertEqual(self.dealt(), 60)
        self.assertTrue(ends)

    async def test_meditite_does_not_attack_twice(self):
        t = self.table()
        med = self.mine(t, MEDITITE_ASC, FIGHT, 2)
        ends = await t.attack(med, 'Gentle Slap')
        self.assertTrue(ends)

    # --- Yamask LOT 99: Haunt -------------------------------------------------
    async def test_yamask_haunt_counter_ignores_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [PSY.value])
        y = self.mine(t, YAMASK, PSY, 1)
        await t.attack(y, 'Haunt')
        self.assertEqual(self.dealt(), 10)

    # --- Cofagrigus SSP 83: Law of the Underworld ----------------------------
    async def test_cofagrigus_law_hits_every_ability_pokemon_both_sides(self):
        t = self.table()
        cof = self.mine(t, COFAGRIGUS, PSY, 1)
        my_bib = self.mine(t, BIBAREL, zone='bench')
        my_plain = self.mine(t, self.filler, zone='bench')
        opp_mis = self.mine(t, MISMAGIUS, zone='bench', pid=P2)
        opp_mis.set_attribute(AttrID.HP, 300)
        my_bib.set_attribute(AttrID.HP, 300)
        await t.attack(cof, 'Law of the Underworld')
        self.assertEqual(300 - t.hp(my_bib), 60)
        self.assertEqual(300 - t.hp(opp_mis), 60)
        self.assertEqual(t.damage(my_plain), 0)
        self.assertEqual(self.dealt(), 0)           # filler has no Ability
        self.assertEqual(t.damage(cof), 0)


    # BUG: Cofagrigus reads raw PIE_ABILITIES, so Pokémon that "have no Abilities" (Watchtower/Path/Hex) are still hit
    async def test_cofagrigus_law_ignores_ability_lost_to_watchtower(self):
        """Watchtower: Colorless Pokémon 'have no Abilities' -> Bibarel is not hit."""
        t = self.table()
        t.stadium(WATCHTOWER, P2)
        cof = self.mine(t, COFAGRIGUS, PSY, 1)
        my_bib = self.mine(t, BIBAREL, zone='bench')
        my_bib.set_attribute(AttrID.HP, 300)
        await t.attack(cof, 'Law of the Underworld')
        self.assertEqual(300 - t.hp(my_bib), 0)

    # --- Brock's Grit TEU 135 ------------------------------------------------
    async def test_brocks_grit_shuffles_six_pokemon_and_basic_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mons = [t.put(self.filler, P1, 'discard') for _ in range(4)]
        ens = [t.put(t.basic_energy(WATER), P1, 'discard') for _ in range(3)]
        item = t.put(self.item, P1, 'discard')
        grit = t.put(BROCKS_GRIT, P1, 'hand')
        self.assertTrue(t.can(grit, 'UseTrainerCard'))
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.append((list(cards), count)), list(cards)[:6])[1]
        await t.play(grit)
        disc = t.zone(P1, 'discard')
        self.assertIn(item, disc)
        self.assertEqual(sum(1 for c in mons + ens if c in disc), 1)
        self.assertNotIn(item, [c for cards, _ in offered for c in cards])
        self.assertEqual(len(t.zone(P1, 'deck')), 30 + 6)

    async def test_brocks_grit_no_targets_not_playable(self):
        t = self.table()
        t.put(self.item, P1, 'discard')
        grit = t.put(BROCKS_GRIT, P1, 'hand')
        self.assertFalse(t.can(grit, 'UseTrainerCard'))

    # --- Pokémon League Headquarters OBF 192 ---------------------------------
    async def test_league_hq_basic_attacks_cost_one_more_both_sides(self):
        t = self.table()
        t.stadium(LEAGUE_HQ, P2)
        med = self.mine(t, MEDITITE_ASC, FIGHT, 1)
        self.assertIsNone(t.attack_offer(med, 'Gentle Slap'))
        t.energy(med, WATER, 1)
        self.assertIsNotNone(t.attack_offer(med, 'Gentle Slap'))
        # Opponent's Basic too, with P1 owning the Stadium.
        t2 = Table(self)
        t2.put(self.filler, P1, 'active')
        t2.stadium(LEAGUE_HQ, P1)
        oddish = self.mine(t2, ODDISH, GRASS, 1, pid=P2)
        t2.next_turn()
        self.assertIsNone(t2.attack_offer(oddish, 'Stun Spore', pid=P2))
        t2.energy(oddish, GRASS, 1)
        self.assertIsNotNone(t2.attack_offer(oddish, 'Stun Spore', pid=P2))

    async def test_league_hq_does_not_affect_evolved(self):
        t = self.table()
        t.stadium(LEAGUE_HQ, P1)
        m = self.mine(t, MEDICHAM, FIGHT, 1)
        self.assertIsNotNone(t.attack_offer(m, 'Calm Mind'))

    # --- Gouging Fire SSP 38: Blazing Charge ---------------------------------
    async def test_gouging_fire_blazing_charge_prize_boundary(self):
        for prizes, expected in ((4, 170), (5, 100)):
            t = self.table()
            t.set_prizes(P2, prizes)
            gf = self.mine(t, GOUGING_FIRE, FIRE, 3)
            await t.attack(gf, 'Blazing Charge')
            with self.subTest(prizes=prizes):
                self.assertEqual(self.dealt(), expected)

    async def test_gouging_fire_counts_opponent_prizes_not_mine(self):
        t = self.table()
        t.set_prizes(P1, 1)
        t.set_prizes(P2, 6)
        gf = self.mine(t, GOUGING_FIRE, FIRE, 3)
        await t.attack(gf, 'Blazing Charge')
        self.assertEqual(self.dealt(), 100)

    # --- Meowth UNB 147: Caturday ---------------------------------------------
    async def test_meowth_caturday_draws_two_then_asleep(self):
        t = self.table()
        m = self.mine(t, MEOWTH, WATER, 1)
        await t.attack(m, 'Caturday')
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertIn(ASLEEP, t.conditions(m))
        self.assertNotIn(ASLEEP, t.conditions(self.opp))

    async def test_meowth_caturday_empty_deck_no_sleep(self):
        t = self.table()
        m = self.mine(t, MEOWTH, WATER, 1)
        deck = t.board.find_player_area(P1, 'deck')
        for c in list(deck.children):
            deck.remove_child(c)
        await t.attack(m, 'Caturday')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertNotIn(ASLEEP, t.conditions(m))

    # --- Persian TEU 126 -------------------------------------------------------
    async def test_persian_make_em_pay_discards_down_to_four(self):
        t = self.table()
        hand = [t.put(self.item, P2, 'hand') for _ in range(7)]
        p = self.mine(t, PERSIAN, WATER, 1)
        await t.attack(p, "Make 'Em Pay")
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)
        self.assertEqual(sum(1 for c in hand if c in t.zone(P2, 'discard')), 3)

    async def test_persian_make_em_pay_small_hand_untouched(self):
        for size in (4, 3):
            t = self.table()
            for _ in range(size):
                t.put(self.item, P2, 'hand')
            p = self.mine(t, PERSIAN, WATER, 1)
            await t.attack(p, "Make 'Em Pay")
            with self.subTest(size=size):
                self.assertEqual(len(t.zone(P2, 'hand')), size)
                self.assertEqual(len(t.zone(P2, 'discard')), 0)
                self.assertEqual(self.dealt(), 20)

    async def test_persian_sharp_claws(self):
        for heads, expected in ((True, 90), (False, 30)):
            t = self.table()
            p = self.mine(t, PERSIAN, WATER, 2)
            t.heads = heads
            await t.attack(p, 'Sharp Claws')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(), expected)


if __name__ == '__main__':
    unittest.main()
