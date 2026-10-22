"""Bug hunt round 7, chunk 45: Crocalor, Avalugg, Iron Valiant, Cranidos, Rampardos,
Antique Skull Fossil, Spoink, Grumpig, Mawile, Sigilyph, Emma, Skarmory,
Rotom Phone, Gwynn, Calamitous Wasteland -- each checked against its printed
text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes, SpecialConditions
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

WATER, FIRE, PSY, FIGHT, METAL, DARK = (
    PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.PSYCHIC,
    PokemonTypes.FIGHTING, PokemonTypes.METAL, PokemonTypes.DARKNESS)

CROCALOR = 'SV08.Crocalor_30'
AVALUGG = 'ME4.Avalugg_24'
VALIANT = 'SV05.IronValiant_79'
CRANIDOS = 'ME5.Cranidos_44'
RAMPARDOS = 'SWSH10.Rampardos_77'
SKULL = 'ME5.AntiqueSkullFossil_73'
SPOINK, GRUMPIG = 'ME1.Spoink_62', 'ME1.Grumpig_63'
MAWILE = 'ME3.Mawile_32'
SIGILYPH = 'SV08.Sigilyph_81'
EMMA = 'ME4.Emma_77'
SKARMORY = 'SWSH3.Skarmory_120'
ROTOM = 'SWSH35.RotomPhone_64'
GWYNN = 'ME5.Gwynn_78'
WASTELAND = 'SV2.CalamitousWasteland_175'
CROBAT = 'SWSH12.Crobat_105'
BOSS = 'ME1.BosssOrders_114'
SAWK = 'BW1.Sawk_62'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk45(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None, opp_hp=400):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, opp_hp)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, {'hand': 'hand', 'deck': 'deck'}[zone])
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None, base=400):
        return base - (target or self.opp).get_attribute(AttrID.HP)

    # --- Crocalor SSP 30: Heat Breath ---------------------------------------
    async def test_crocalor_heat_breath_heads(self):
        t = self.table()
        me = self.mine(t, CROCALOR, FIRE, 2)
        t.heads = True
        await t.attack(me, 'Heat Breath')
        self.assertEqual(self.dealt(), 80)

    async def test_crocalor_heat_breath_tails(self):
        t = self.table()
        me = self.mine(t, CROCALOR, FIRE, 2)
        t.heads = False
        await t.attack(me, 'Heat Breath')
        self.assertEqual(self.dealt(), 30)

    # --- Avalugg CRI 24: Iceberg Breaker ------------------------------------
    async def test_avalugg_iceberg_breaker_counts_basic_water_in_top6(self):
        t = self.table()
        me = self.mine(t, AVALUGG, WATER, 1)
        # top 6: 2 Water, 1 Fire, 3 filler; the 7th card (Water) must stay
        t.deck(P1, [t.basic_energy(WATER)])
        top = t.deck(P1, [t.basic_energy(WATER), t.basic_energy(FIRE), self.item,
                          t.basic_energy(WATER), self.item, self.item])
        deck_before = len(t.zone(P1, 'deck'))
        await t.attack(me, 'Iceberg Breaker')
        self.assertEqual(self.dealt(), 120)
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before - 6)
        for c in top:
            self.assertIn(c, t.zone(P1, 'discard'))

    async def test_avalugg_iceberg_breaker_no_water_does_nothing(self):
        t = self.table()
        me = self.mine(t, AVALUGG, WATER, 1)
        t.deck(P1, [t.basic_energy(FIRE)] * 2)
        await t.attack(me, 'Iceberg Breaker')
        self.assertEqual(self.dealt(), 0)
        self.assertEqual(len(t.zone(P1, 'discard')), 6)

    # --- Iron Valiant TEF 79 ------------------------------------------------
    async def test_iron_valiant_gemini_laser_hits_bench(self):
        t = self.table()
        bench = self.mine(t, self.filler, zone='bench', pid=P2, hp=200)
        other = self.mine(t, self.filler, zone='bench', pid=P2, hp=200)
        me = self.mine(t, VALIANT, PSY, 1)
        mine_bench = self.mine(t, self.filler, zone='bench', hp=200)
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        await t.attack(me, 'Gemini Laser')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(self.dealt(bench, 200), 20)
        self.assertEqual(self.dealt(other, 200), 0)
        self.assertEqual(self.dealt(mine_bench, 200), 0)

    async def test_iron_valiant_gemini_laser_bench_ignores_weakness(self):
        t = self.table()
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 200)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [PSY])
        me = self.mine(t, VALIANT, PSY, 1)
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        await t.attack(me, 'Gemini Laser')
        self.assertEqual(self.dealt(bench, 200), 20)

    async def test_iron_valiant_zen_blade_locked_next_turn(self):
        t = self.table()
        me = self.mine(t, VALIANT, PSY, 3)
        await t.attack(me, 'Zen Blade')
        self.assertEqual(self.dealt(), 120)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(me, 'Zen Blade'))
        self.assertIsNotNone(t.attack_offer(me, 'Gemini Laser'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(me, 'Zen Blade'))

    # --- Cranidos PBL 44: Push Down ------------------------------------------
    async def test_cranidos_push_down_opponent_chooses_new_active(self):
        t = self.table()
        b1 = self.mine(t, self.filler, zone='bench', pid=P2)
        b2 = self.mine(t, self.filler, zone='bench', pid=P2)
        me = self.mine(t, CRANIDOS, FIGHT, 2)
        asked = []

        def choose(cands, prompt):
            asked.append(list(cands))
            return b2 if b2 in cands else cands[0]
        t.pokemon = choose
        await t.attack(me, 'Push Down')
        self.assertEqual(self.dealt(), 70)
        self.assertIs(t.active(P2), b2)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIs(t.active(P1), me)

    async def test_cranidos_push_down_no_bench_just_damage(self):
        t = self.table()
        me = self.mine(t, CRANIDOS, FIGHT, 2)
        await t.attack(me, 'Push Down')
        self.assertEqual(self.dealt(), 70)
        self.assertIs(t.active(P2), self.opp)

    # --- Rampardos ASR 77: Jurassic Hammer ----------------------------------
    async def test_rampardos_jurassic_hammer_with_4_cards(self):
        t = self.table()
        me = self.mine(t, RAMPARDOS, FIGHT, 2)
        self.clear(t, P2, 'hand')
        for _ in range(4):
            t.put(self.item, P2, 'hand')
        await t.attack(me, 'Jurassic Hammer')
        self.assertEqual(self.dealt(), 240)

    async def test_rampardos_jurassic_hammer_with_3_cards_does_nothing(self):
        t = self.table()
        me = self.mine(t, RAMPARDOS, FIGHT, 2)
        self.clear(t, P2, 'hand')
        for _ in range(3):
            t.put(self.item, P2, 'hand')
        await t.attack(me, 'Jurassic Hammer')
        self.assertEqual(self.dealt(), 0)

    # --- Antique Skull Fossil PBL 73 ----------------------------------------
    async def _fossil(self, t, active):
        t.put(self.filler, P1, 'active')
        card = t.put(SKULL, P1, 'hand')
        await t.play(card)
        fossil = next(p for p in t.board.pokemon_in_play(P1) if name(p) == 'Antique Skull Fossil')
        if active:
            await t._run(lambda: EffectContext(t.session, P1, fossil, None).switch_active(P1, fossil))
        return fossil

    async def test_skull_fossil_spiny_skull_not_on_bench(self):
        t = Table(self)
        fossil = await self._fossil(t, active=False)
        self.assertIn(fossil, t.zone(P1, 'bench'))
        crobat = t.put(CROBAT, P2, 'active')
        t.energy(crobat, DARK, 3)
        before = t.hp(crobat)
        t.next_turn()
        t.pokemon = lambda c, p: fossil if fossil in c else c[0]
        await t.attack(crobat, 'Critical Bite', pid=P2)
        self.assertEqual(t.hp(crobat), before)

    async def test_skull_fossil_spiny_skull_even_when_knocked_out(self):
        t = Table(self)
        fossil = await self._fossil(t, active=True)
        fossil.set_attribute(AttrID.HP, 10)
        t.put(self.filler, P2, 'bench')    # not needed, keep P2 alive
        crobat = t.put(CROBAT, P2, 'active')
        t.energy(crobat, DARK, 1)
        before = t.hp(crobat)
        t.next_turn()
        await t.attack(crobat, 'Venomous Fang', pid=P2)
        self.assertNotIn(fossil, t.board.pokemon_in_play(P1))
        self.assertEqual(before - t.hp(crobat), 30)

    async def test_skull_fossil_no_retreat_and_no_conditions(self):
        t = Table(self)
        fossil = await self._fossil(t, active=True)
        self.assertTrue(t.zone(P1, 'bench'))
        self.assertFalse(t.can(fossil, 'BaseRetreat'))
        t.energy(fossil, DARK, 2)                       # even with Energy to pay
        self.assertFalse(t.can(fossil, 'BaseRetreat'))
        ctx = EffectContext(t.session, P2, t.active(P2) or fossil, None)
        await t._run(lambda: ctx.apply_special_condition(fossil, SpecialConditions.PARALYZED))
        self.assertNotIn(PARALYZED, t.conditions(fossil))

    async def test_skull_fossil_control_normal_active_can_retreat(self):
        t = Table(self)
        me = self.mine(t, SPOINK, PSY, 1)
        self.mine(t, self.filler, zone='bench')
        self.assertTrue(t.can(me, 'BaseRetreat'))

    # --- Spoink MEG 62: Triple Spin -----------------------------------------
    async def test_spoink_triple_spin_counts_heads(self):
        t = self.table()
        me = self.mine(t, SPOINK, PSY, 1)
        seq = iter([True, False, True])
        t.heads = lambda title: next(seq)
        await t.attack(me, 'Triple Spin')
        self.assertEqual(self.dealt(), 20)

    async def test_spoink_triple_spin_all_tails(self):
        t = self.table()
        me = self.mine(t, SPOINK, PSY, 1)
        t.heads = False
        await t.attack(me, 'Triple Spin')
        self.assertEqual(self.dealt(), 0)

    # --- Grumpig MEG 63: Energized Steps ------------------------------------
    async def test_grumpig_energized_steps_attaches_basic_energy_from_top4(self):
        t = self.table()
        spoink = self.mine(t, SPOINK)
        bench = self.mine(t, self.filler, zone='bench')
        water5 = t.deck(P1, [t.basic_energy(WATER)])[0]          # 5th card: out of reach
        top = t.deck(P1, [t.basic_energy(PSY), self.item, t.basic_energy(FIRE), self.item])
        grumpig = t.put(GRUMPIG, P1, 'hand')
        t.yes = True
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        await t.play(grumpig, targets=[spoink.entity_id])
        if t.ability_offer(grumpig, 'Energized Steps') is not None:
            await t.use(grumpig, 'Energized Steps')
        energies = [top[0], top[2]]
        attached = [c for p in t.board.pokemon_in_play(P1) for c in p.children if c in energies]
        self.assertEqual(len(attached), 2)
        self.assertNotIn(water5, [c for p in t.board.pokemon_in_play(P1) for c in p.children])
        self.assertIn(top[1], t.zone(P1, 'deck'))
        self.assertIn(top[3], t.zone(P1, 'deck'))
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_grumpig_energized_steps_not_offered_when_already_in_play(self):
        t = self.table()
        grumpig = self.mine(t, GRUMPIG)
        t.deck(P1, [t.basic_energy(PSY)])
        self.assertIsNone(t.ability_offer(grumpig, 'Energized Steps'))

    # --- Mawile POR 32: Double Eater ----------------------------------------
    # BUG: Double Eater offers (and pays 60 for) non-Energy hand cards; "2 Energy cards" predicate falls back to "any card"
    async def test_mawile_double_eater_discards_2_energy(self):
        t = self.table()
        me = self.mine(t, MAWILE, PSY, 2)
        self.clear(t, P1, 'hand')
        es = [t.put(t.basic_energy(WATER), P1, 'hand') for _ in range(3)]
        item = t.put(self.item, P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.attack(me, 'Double Eater')
        self.assertEqual(self.dealt(), 120)
        self.assertEqual(sum(1 for e in es if e in t.zone(P1, 'discard')), 2)
        self.assertNotIn(item, offered)
        self.assertIn(item, t.zone(P1, 'hand'))

    # BUG: same root cause -- discarding an Item to Double Eater deals 60
    async def test_mawile_double_eater_item_does_not_count(self):
        t = self.table()
        me = self.mine(t, MAWILE, PSY, 2)
        self.clear(t, P1, 'hand')
        item = t.put(self.item, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is item]
        await t.attack(me, 'Double Eater')
        self.assertEqual(self.dealt(), 0)
        self.assertIn(item, t.zone(P1, 'hand'))

    async def test_mawile_double_eater_choose_zero(self):
        t = self.table()
        me = self.mine(t, MAWILE, PSY, 2)
        self.clear(t, P1, 'hand')
        e = t.put(t.basic_energy(WATER), P1, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(me, 'Double Eater')
        self.assertEqual(self.dealt(), 0)
        self.assertIn(e, t.zone(P1, 'hand'))

    # --- Sigilyph SSP 81 ----------------------------------------------------
    async def test_sigilyph_double_draw(self):
        t = self.table()
        me = self.mine(t, SIGILYPH, PSY, 1)
        self.clear(t, P1, 'hand')
        await t.attack(me, 'Double Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(self.dealt(), 0)

    async def test_sigilyph_psy_bolt(self):
        for heads in (True, False):
            with self.subTest(heads=heads):
                t = self.table()
                me = self.mine(t, SIGILYPH, PSY, 3)
                t.heads = heads
                await t.attack(me, 'Psy Bolt')
                self.assertEqual(self.dealt(), 60)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)
                self.assertNotIn(PARALYZED, t.conditions(me))

    # --- Emma CRI 77 --------------------------------------------------------
    async def test_emma_draws_one_per_pokemon_in_opponent_hand(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        self.clear(t, P2, 'hand')
        t.put(self.filler, P2, 'hand')
        t.put(SPOINK, P2, 'hand')
        t.put(self.item, P2, 'hand')
        t.put(t.basic_energy(WATER), P2, 'hand')
        emma = t.put(EMMA, P1, 'hand')
        await t.play(emma)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(len(t.zone(P2, 'hand')), 4)

    async def test_emma_no_pokemon_draws_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        self.clear(t, P2, 'hand')
        t.put(self.item, P2, 'hand')
        # my own Pokémon in hand must not count
        t.put(self.filler, P1, 'hand')
        emma = t.put(EMMA, P1, 'hand')
        await t.play(emma)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    # --- Skarmory DAA 120: Metal Arms ---------------------------------------
    async def test_skarmory_metal_arms_with_tool(self):
        t = self.table()
        me = self.mine(t, SKARMORY, METAL, 1)
        t.attach(self._tool_spec(), me)
        await t.attack(me, 'Metal Arms')
        self.assertEqual(self.dealt(), 50)

    async def test_skarmory_metal_arms_without_tool(self):
        t = self.table()
        me = self.mine(t, SKARMORY, METAL, 1)
        await t.attack(me, 'Metal Arms')
        self.assertEqual(self.dealt(), 10)

    def _tool_spec(self):
        return 'SWSH1.AirBalloon_156'

    # --- Rotom Phone CPA 64 -------------------------------------------------
    async def test_rotom_phone_puts_chosen_top5_card_on_top(self):
        t = self.table()
        self.mine(t, self.filler)
        sixth = t.deck(P1, [SPOINK])[0]
        top = t.deck(P1, [self.item, self.item, GRUMPIG, self.item, self.item])
        offered = []

        def pick(cards, count, prompt, display):
            offered.extend(cards)
            return [top[2]]
        t.picks = pick
        phone = t.put(ROTOM, P1, 'hand')
        deck_before = len(t.zone(P1, 'deck'))
        await t.play(phone)
        deck = t.zone(P1, 'deck')
        self.assertEqual(len(deck), deck_before)
        self.assertIs(deck[-1], top[2])   # deck top = last child (Table.deck appends to top)
        self.assertNotIn(sixth, offered)
        self.assertEqual(len(offered), 5)
        self.assertIn(phone, t.zone(P1, 'discard'))

    async def test_rotom_phone_not_playable_with_empty_deck(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'deck')
        phone = t.put(ROTOM, P1, 'hand')
        self.assertFalse(t.can(phone, 'UseTrainerCard'))

    # --- Gwynn PBL 78 -------------------------------------------------------
    async def test_gwynn_discard_2_pokemon_draw_6(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        mons = [t.put(SPOINK, P1, 'hand'), t.put(self.filler, P1, 'hand')]
        item = t.put(self.item, P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        gwynn = t.put(GWYNN, P1, 'hand')
        await t.play(gwynn)
        for m in mons:
            self.assertIn(m, t.zone(P1, 'discard'))
        self.assertNotIn(item, offered)
        self.assertEqual(len(t.zone(P1, 'hand')), 1 + 6)

    async def test_gwynn_one_pokemon_draws_3(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        t.put(SPOINK, P1, 'hand')
        gwynn = t.put(GWYNN, P1, 'hand')
        await t.play(gwynn)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_gwynn_not_playable_without_pokemon_in_hand(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        t.put(self.item, P1, 'hand')
        gwynn = t.put(GWYNN, P1, 'hand')
        self.assertFalse(t.can(gwynn, 'UseTrainerCard'))

    # --- Calamitous Wasteland PAL 175 ---------------------------------------
    async def test_wasteland_basic_non_fighting_both_sides(self):
        for owner in (P1, P2):
            with self.subTest(owner=owner):
                t = self.table()
                mine = self.mine(t, SPOINK)            # Basic Psychic, retreat 1
                base_opp = t.retreat(self.opp)
                t.stadium(WASTELAND, owner)
                self.assertEqual(t.retreat(mine), 2)
                self.assertEqual(t.retreat(self.opp), base_opp + 1)

    async def test_wasteland_not_fighting_or_evolved(self):
        t = self.table()
        sawk = self.mine(t, SAWK, zone='bench')               # Basic Fighting
        valiant = self.mine(t, VALIANT)                       # Basic Psychic control
        grumpig = self.mine(t, GRUMPIG, zone='bench')         # Stage 1
        cranidos = self.mine(t, CRANIDOS, zone='bench')       # Stage 1 Fighting
        before = (t.retreat(grumpig), t.retreat(cranidos), t.retreat(valiant), t.retreat(sawk))
        t.stadium(WASTELAND, P1)
        self.assertEqual(t.retreat(grumpig), before[0])
        self.assertEqual(t.retreat(cranidos), before[1])
        self.assertEqual(t.retreat(valiant), before[2] + 1)
        self.assertEqual(t.retreat(sawk), before[3])


if __name__ == "__main__":
    unittest.main()
