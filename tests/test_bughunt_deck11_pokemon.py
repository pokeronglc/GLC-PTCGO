"""Bug hunt, deck 11 (Grass): every Pokémon with text, checked against its
printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

G = PokemonTypes.GRASS
D = PokemonTypes.DARKNESS
CHERUBI, CHERRIM = 'ME55.Cherubi_6', 'SWSH5.Cherrim_8'
WURMPLE, SILCOON, BEAUTIFLY = 'ME2PT5.Wurmple_11', 'XY6.Silcoon_4', 'SWSH11.Beautifly_8'
EXEGGCUTE, A_EXEGGUTOR = 'ME1.Exeggcute_4', 'ME55.AlolanExeggutor_2'
TURTWIG, GROTLE, TORTERRA = 'SM5.Turtwig_6', 'SWSH9.Grotle_7', 'SWSH9.Torterra_8'
ROSELIA, ROSERADE = 'SWSH11.Roselia_14', 'BW6.Roserade_15'
CHIKORITA, BAYLEEF, MEGANIUM = 'ME1.Chikorita_8', 'XY9.Bayleef_2', 'ME1.Meganium_10'
TROPIUS, SHAYMIN, BUDEW = 'SWSH7.Tropius_6', 'SV10.Shaymin_10', 'ME2PT5.Budew_16'
SABLEYE = 'SV2.Sableye_136'          # P2 attacker: Night Eyes (Asleep), Unseen Claw (20)
CHIMCHAR = 'SWSH9.Chimchar_24'       # a non-Grass Basic
NET_BALL = 'SM8.NetBall_187'


def as_rule_box(card):
    """No Rule Box Pokémon exist in this card pool: mark one card's archetype
    as a Pokémon V for the duration of a test."""
    import spirit.game.data_utils as du
    original = du.subtypes_for
    return patch.object(du, 'subtypes_for', lambda a: list(original(a) or []) + (
        ['V'] if a == card.archetype_id else []))


def advance(t):
    """next_turn that also prunes expired temporary passives, as the real
    session does (begin_turn with the board)."""
    other = P2 if t.state.active_player_id == P1 else P1
    t.state.begin_turn(other, t.board)


class Deck11Pokemon(unittest.IsolatedAsyncioTestCase):
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

    def name(self, card):
        return def_for(card.archetype_id).display_name

    # --- Cherubi (30C): Hide ----------------------------------------------
    async def test_cherubi_hide_heads_prevents_damage_and_effects(self):
        t = self.table(SABLEYE)
        t.energy(self.opp, D, 2)
        cherubi = t.put(CHERUBI, P1, 'active')
        t.energy(cherubi, G)
        t.heads = True
        await t.attack(cherubi, 'Hide')
        advance(t)
        await t.attack(self.opp, 'Night Eyes', pid=P2)
        self.assertNotIn(ASLEEP, t.conditions(cherubi))
        advance(t); advance(t)
        hp = t.hp(cherubi)
        await t.attack(self.opp, 'Unseen Claw', pid=P2)    # shield lasted only one turn
        self.assertEqual(hp - t.hp(cherubi), 20)

    async def test_cherubi_hide_heads_blocks_damage_tails_does_not(self):
        for heads, taken in ((True, 0), (False, 20)):
            t = self.table(SABLEYE)
            t.energy(self.opp, D, 2)
            cherubi = t.put(CHERUBI, P1, 'active')
            t.energy(cherubi, G)
            t.heads = heads
            await t.attack(cherubi, 'Hide')
            t.next_turn()
            await t.attack(self.opp, 'Unseen Claw', pid=P2)
            with self.subTest(heads=heads):
                self.assertEqual(effective_max_hp(t.board, cherubi) - t.hp(cherubi), taken)

    # --- Cherrim (BST): Spring Bloom rule-box / hand restrictions ---------
    async def test_spring_bloom_needs_grass_energy_in_hand(self):
        t = self.table()
        cherrim = t.put(CHERRIM, P1, 'active')
        t.put(t.basic_energy(PokemonTypes.FIRE), P1, 'hand')
        self.assertIsNone(t.ability_offer(cherrim, 'Spring Bloom'))
        t.put(t.basic_energy(G), P1, 'hand')
        self.assertIsNotNone(t.ability_offer(cherrim, 'Spring Bloom'))

    async def test_spring_bloom_never_targets_rule_box(self):
        t = self.table()
        cherrim = t.put(CHERRIM, P1, 'active')
        boxed = t.put(CHIMCHAR, P1, 'bench')
        t.put(t.basic_energy(G), P1, 'hand')
        seen = {}

        def pick_pokemon(candidates, prompt):
            seen['c'] = list(candidates)
            return candidates[0]
        t.pokemon = pick_pokemon
        once = iter([True])
        t.picks = lambda cards, count, prompt, display: cards[:1] if next(once, False) else []
        with as_rule_box(boxed):
            await t.use(cherrim, 'Spring Bloom')
        self.assertTrue(seen.get('c'))
        self.assertNotIn(boxed, seen.get('c', []))
        self.assertEqual(len(t.board.attached_energies(boxed)), 0)

    # --- Silcoon: String Shot -------------------------------------------
    async def test_silcoon_string_shot(self):
        for heads in (True, False):
            t = self.table()
            silcoon = t.put(SILCOON, P1, 'active')
            t.energy(silcoon, G)
            t.heads = heads
            await t.attack(silcoon, 'String Shot')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 10)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    # --- Beautifly: Stoked Straw / Mega Drain ---------------------------
    async def test_stoked_straw_draws_to_six_once(self):
        t = self.table()
        beautifly = t.put(BEAUTIFLY, P1, 'bench')
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P1, 'hand'); t.put(self.filler, P1, 'hand')
        await t.use(beautifly, 'Stoked Straw')
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        for _ in range(3):
            t.board.move_card(t.zone(P1, 'hand')[0].entity_id,
                              t.board.find_player_area(P1, 'discard').entity_id)
        self.assertIsNone(t.ability_offer(beautifly, 'Stoked Straw'))   # once per turn

    async def test_stoked_straw_not_with_six_in_hand(self):
        t = self.table()
        beautifly = t.put(BEAUTIFLY, P1, 'active')
        for _ in range(6):
            t.put(self.filler, P1, 'hand')
        self.assertIsNone(t.ability_offer(beautifly, 'Stoked Straw'))

    async def test_beautifly_mega_drain(self):
        t = self.table()
        beautifly = t.put(BEAUTIFLY, P1, 'active', hp=60)
        t.energy(beautifly, G, 2)
        await t.attack(beautifly, 'Mega Drain')
        self.assertEqual(400 - t.hp(self.opp), 70)
        self.assertEqual(t.hp(beautifly), 90)

    # --- Exeggcute (MEG): Jam-Packed ------------------------------------
    async def test_jam_packed_attaches_basic_grass_to_self(self):
        t = self.table()
        egg = t.put(EXEGGCUTE, P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.energy(egg, D)
        fire, grass = t.deck(P1, [t.basic_energy(PokemonTypes.FIRE), t.basic_energy(G)])
        await t.attack(egg, 'Jam-Packed')
        attached = t.board.attached_energies(egg)
        self.assertEqual(len(attached), 2)
        self.assertIn(grass, attached)
        self.assertNotIn(fire, attached)

    async def test_jam_packed_ignores_other_energy(self):
        t = self.table()
        egg = t.put(EXEGGCUTE, P1, 'active')
        t.energy(egg, D)
        t.deck(P1, [t.basic_energy(PokemonTypes.FIRE)])
        await t.attack(egg, 'Jam-Packed')
        self.assertEqual(len(t.board.attached_energies(egg)), 1)

    # --- Alolan Exeggutor (30C): Scale Up / Mega Drain ------------------
    async def test_scale_up_six_grass_energy(self):
        for count, bonus in ((5, 0), (6, 250)):
            t = self.table()
            ex = t.put(A_EXEGGUTOR, P1, 'active')
            t.energy(ex, G, count)
            with self.subTest(count=count):
                self.assertEqual(effective_max_hp(t.board, ex), 150 + bonus)

    async def test_scale_up_non_grass_energy_does_not_count(self):
        t = self.table()
        ex = t.put(A_EXEGGUTOR, P1, 'active')
        t.energy(ex, G, 5)
        t.energy(ex, D, 1)
        self.assertEqual(effective_max_hp(t.board, ex), 150)

    async def test_scale_up_counts_meganium_doubled_grass(self):
        # 3 Basic Grass Energy under Wild Growth provide 6 Grass Energy.
        t = self.table()
        ex = t.put(A_EXEGGUTOR, P1, 'active')
        t.put(MEGANIUM, P1, 'bench')
        t.energy(ex, G, 3)
        self.assertEqual(effective_max_hp(t.board, ex), 400)

    async def test_alolan_exeggutor_mega_drain_heals_50(self):
        t = self.table()
        ex = t.put(A_EXEGGUTOR, P1, 'active', hp=50)
        t.energy(ex, G, 4)
        await t.attack(ex, 'Mega Drain')
        self.assertEqual(400 - t.hp(self.opp), 150)
        self.assertEqual(t.hp(ex), 100)

    # --- Turtwig (UPR): Synthesis ---------------------------------------
    async def test_synthesis_attaches_grass_to_benched(self):
        t = self.table()
        turtwig = t.put(TURTWIG, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.energy(turtwig, G)
        fire, grass = t.deck(P1, [t.basic_energy(PokemonTypes.FIRE), t.basic_energy(G)])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'] = list(cards)
            return [c for c in cards if c is grass][:count] or cards[:count]
        t.picks = picks
        await t.attack(turtwig, 'Synthesis')
        self.assertEqual(t.board.attached_energies(bench), [grass])
        self.assertNotIn(fire, seen.get('cards', []))

    # --- Grotle: Sun-Drenched Shell -------------------------------------
    async def test_sun_drenched_shell_grass_pokemon_once(self):
        t = self.table()
        grotle = t.put(GROTLE, P1, 'active')
        t.deck(P1, [CHIMCHAR, TORTERRA])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'] = t.names(cards)
            return cards[:count]
        t.picks = picks
        await t.use(grotle, 'Sun-Drenched Shell')
        self.assertNotIn('Chimchar', seen['names'])
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Torterra'])
        self.assertIsNone(t.ability_offer(grotle, 'Sun-Drenched Shell'))

    # --- Torterra: Evopress ----------------------------------------------
    async def test_evopress_counts_own_evolution_pokemon(self):
        t = self.table()
        torterra = t.put(TORTERRA, P1, 'active')
        t.energy(torterra, G, 2)
        t.put(GROTLE, P1, 'bench')
        t.put(TURTWIG, P1, 'bench')          # Basic: doesn't count
        t.put(GROTLE, P2, 'bench')           # opponent's: doesn't count
        await t.attack(torterra, 'Evopress')
        self.assertEqual(400 - t.hp(self.opp), 100)

    # --- Roselia: Soothing Scent ----------------------------------------
    async def test_soothing_scent_asleep(self):
        t = self.table()
        roselia = t.put(ROSELIA, P1, 'active')
        t.energy(roselia, G)
        await t.attack(roselia, 'Soothing Scent')
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertEqual(t.hp(self.opp), 400)

    # --- Roserade (DRX): Le Parfum / Squeeze ----------------------------
    async def test_le_parfum_searches_any_card_on_evolve_from_hand(self):
        t = self.table()
        roselia = t.put(ROSELIA, P1, 'active')
        t.state.entered_play_turn[roselia.entity_id] = 1
        t.deck(P1, [CHIMCHAR])
        roserade = t.put(ROSERADE, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [
            c for c in cards if self.name(c) == 'Chimchar'][:1]
        await t.play(roserade, targets=[roselia.entity_id])
        self.assertIs(t.active(P1), roserade)
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Chimchar'])

    async def test_le_parfum_is_optional(self):
        t = self.table()
        roselia = t.put(ROSELIA, P1, 'active')
        t.deck(P1, [CHIMCHAR])
        roserade = t.put(ROSERADE, P1, 'hand')
        t.yes = False
        t.picks = lambda cards, count, prompt, display: []
        await t.play(roserade, targets=[roselia.entity_id])
        self.assertEqual(t.zone(P1, 'hand'), [])

    async def test_squeeze(self):
        for heads, dmg in ((True, 50), (False, 30)):
            t = self.table()
            roserade = t.put(ROSERADE, P1, 'active')
            t.energy(roserade, G, 2)
            t.heads = heads
            await t.attack(roserade, 'Squeeze')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    # --- Bayleef (BKP): Body Slam ---------------------------------------
    async def test_bayleef_body_slam(self):
        for heads in (True, False):
            t = self.table()
            bayleef = t.put(BAYLEEF, P1, 'active')
            t.energy(bayleef, G)
            t.heads = heads
            await t.attack(bayleef, 'Body Slam')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 20)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    # --- Meganium (MEG): Wild Growth ------------------------------------
    async def test_wild_growth_pays_solar_beam_with_two_grass(self):
        t = self.table()
        meganium = t.put(MEGANIUM, P1, 'active')
        t.energy(meganium, G, 2)
        self.assertIsNotNone(t.attack_offer(meganium, 'Solar Beam'))
        await t.attack(meganium, 'Solar Beam')
        self.assertEqual(400 - t.hp(self.opp), 140)

    async def test_wild_growth_on_bench_powers_active(self):
        t = self.table()
        tropius = t.put(TROPIUS, P1, 'active')
        t.put(MEGANIUM, P1, 'bench')
        t.energy(tropius, G, 2)       # GG -> GGGG covers Solar Beam GGC
        self.assertIsNotNone(t.attack_offer(tropius, 'Solar Beam'))

    async def test_wild_growth_needs_meganium_and_only_mine(self):
        t = self.table()
        tropius = t.put(TROPIUS, P1, 'active')
        t.energy(tropius, G, 2)
        self.assertIsNone(t.attack_offer(tropius, 'Solar Beam'))
        t.put(MEGANIUM, P2, 'bench')    # opponent's Meganium does nothing for me
        self.assertIsNone(t.attack_offer(tropius, 'Solar Beam'))

    async def test_wild_growth_does_not_stack(self):
        t = self.table()
        meganium = t.put(MEGANIUM, P1, 'active')
        t.put(MEGANIUM, P1, 'bench')
        t.energy(meganium, G, 1)        # GG, not GGGG
        self.assertIsNone(t.attack_offer(meganium, 'Solar Beam'))

    # --- Tropius: Rally Back ---------------------------------------------
    async def test_rally_back_after_attack_knockout(self):
        t = self.table(SABLEYE)
        t.energy(self.opp, D, 2)
        t.put(self.filler, P1, 'active', hp=10)
        tropius = t.put(TROPIUS, P1, 'bench')
        t.energy(tropius, G, 2)
        t.next_turn()
        await t.attack(self.opp, 'Unseen Claw', pid=P2)
        self.assertIs(t.active(P1), tropius)
        t.next_turn()
        hp = t.hp(self.opp)
        await t.attack(tropius, 'Rally Back')
        self.assertEqual(hp - t.hp(self.opp), 120)

    async def test_rally_back_without_knockout(self):
        t = self.table(SABLEYE)
        t.energy(self.opp, D, 2)
        t.put(self.filler, P1, 'active')
        tropius = t.put(TROPIUS, P1, 'bench')
        t.energy(tropius, G, 2)
        t.next_turn()
        await t.attack(self.opp, 'Unseen Claw', pid=P2)
        t.next_turn()
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(t.active(P1))
        t.board.move_card(tropius.entity_id,
                          t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        hp = t.hp(self.opp)
        await t.attack(tropius, 'Rally Back')
        self.assertEqual(hp - t.hp(self.opp), 30)

    # --- Shaymin (DRI): Flower Curtain ----------------------------------
    async def test_flower_curtain_protects_bench_without_rule_box(self):
        from tests.test_bughunt_deck10_pokemon import CROBAT
        t = self.table(CROBAT)
        t.energy(self.opp, D, 3)
        t.put(SHAYMIN, P1, 'active')
        plain = t.put(self.filler, P1, 'bench')
        plain.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.pokemon = lambda c, p: plain if plain in c else c[0]
        t.next_turn()
        await t.attack(self.opp, 'Critical Bite', pid=P2)
        self.assertEqual(t.damage(plain), 0)

    async def test_flower_curtain_not_for_rule_box(self):
        from tests.test_bughunt_deck10_pokemon import CROBAT
        t = self.table(CROBAT)
        t.energy(self.opp, D, 3)
        active = t.put(SHAYMIN, P1, 'active')
        active.set_attribute(AttrID.WEAKNESS_TYPES, [])
        boxed = t.put(CHIMCHAR, P1, 'bench')
        boxed.set_attribute(AttrID.WEAKNESS_TYPES, [])
        boxed.set_attribute(AttrID.RESISTANCE_TYPES, [])
        boxed.set_attribute(AttrID.HP, 300)
        t.pokemon = lambda c, p: boxed if boxed in c else c[0]
        t.next_turn()
        with as_rule_box(boxed):
            await t.attack(self.opp, 'Critical Bite', pid=P2)
        self.assertEqual(300 - t.hp(boxed), 30)

    async def test_flower_curtain_does_not_protect_active(self):
        t = self.table(SABLEYE)
        t.energy(self.opp, D, 2)
        shaymin = t.put(SHAYMIN, P1, 'active')
        shaymin.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.next_turn()
        await t.attack(self.opp, 'Unseen Claw', pid=P2)
        self.assertEqual(t.damage(shaymin), 20)

    # --- Budew (ASC): Itchy Pollen --------------------------------------
    async def test_itchy_pollen_locks_opponent_items_next_turn(self):
        t = self.table()
        budew = t.put(BUDEW, P1, 'active')
        await t.attack(budew, 'Itchy Pollen')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.put(TURTWIG, P2, 'deck')
        item = t.put(NET_BALL, P2, 'hand')
        mine = t.put(NET_BALL, P1, 'hand')
        t.next_turn()
        self.assertFalse(t.can(item, 'UseTrainerCard', P2))
        t.next_turn()
        t.put(TURTWIG, P1, 'deck')
        self.assertTrue(t.can(mine, 'UseTrainerCard', P1))   # attacker's side unaffected
        t.next_turn()
        t.put(TURTWIG, P2, 'deck')
        self.assertTrue(t.can(item, 'UseTrainerCard', P2))   # lock is over


if __name__ == "__main__":
    unittest.main()
