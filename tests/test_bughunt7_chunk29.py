"""Bug hunt round 7, chunk 29: Misty's Vitality, Glimmet, Glimmora, Lumiose City,
Powerglass, Rowlet, Dartrix, Decidueye, Galvantula, Patrat, Watchog, Latios,
Minun, Cascoon, Dustox -- each checked against its printed text, including the
cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
GRASS, FIGHT, LIGHT = PokemonTypes.GRASS, PokemonTypes.FIGHTING, PokemonTypes.LIGHTNING

MISTY = 'ME5.MistysVitality_80'
GLIMMET, GLIMMORA = 'SV06.Glimmet_108', 'SV08.Glimmora_115'
LUMIOSE = 'ME3.LumioseCity_77'
POWERGLASS = 'SV065.Powerglass_63'
ROWLET, DARTRIX, DECIDUEYE = 'ME3.Rowlet_10', 'SV065.Dartrix_4', 'SV065.Decidueye_5'
GALVANTULA = 'SV065.Galvantula_2'
PATRAT, WATCHOG = 'RSV10PT5.Patrat_72', 'BW2.Watchog_79'
LATIOS = 'SV08.Latios_77'
MINUN = 'BW11.Minun_48'
WURMPLE, SILCOON, CASCOON = 'ME2PT5.Wurmple_11', 'ME2PT5.Silcoon_12', 'SM8.Cascoon_27'
DUSTOX = 'XY6.Dustox_8'
MOLTRES = 'SV035.Moltres_146'      # Basic with an Ability (Flare Float)
POTION = 'SM1.Potion_127'


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk29(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.neutral(self.opp)
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def neutral(self, p):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = self.neutral(t.put(spec, P1, zone))
        if count:
            t.energy(p, kind, count)
        return p

    def opp_bench(self, t, spec=None):
        b = self.neutral(t.put(spec or self.filler, P2, 'bench'))
        b.set_attribute(AttrID.HP, 400)
        return b

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card, kind=None):
        if kind is not None:
            return card.archetype_id.lower() == self.energies[kind.value].lower()
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def energies_on(self, pokemon, kind=None):
        return [c for c in pokemon.children if self.is_energy(c, kind)]

    def dealt(self, p=None):
        return 400 - (p or self.opp).get_attribute(AttrID.HP)

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a
        raise AssertionError('filler has no damaging attack')

    # --- Misty's Vitality PBL 80 -------------------------------------------
    async def test_misty_vitality_attaches_up_to_4_water_to_one_and_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        target = self.mine(t, self.filler, zone='bench')
        t.deck(P1, [t.basic_energy(WATER)] * 5 + [t.basic_energy(FIRE)] * 2)
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        t.pokemon = lambda c, p: target if target in c else c[0]
        card = t.put(MISTY, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        ended = await t.play(card)
        self.assertEqual(len(self.energies_on(target, WATER)), 4)
        self.assertEqual(self.energies_on(target, FIRE), [])
        self.assertTrue(offered)
        self.assertTrue(all(self.is_energy(c, WATER) for c in offered))
        self.assertTrue(ended, 'Your turn ends')

    async def test_misty_vitality_no_water_attaches_nothing(self):
        t = self.table()
        act = self.mine(t, self.filler)
        t.deck(P1, [t.basic_energy(FIRE)] * 3)
        card = t.put(MISTY, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertEqual(self.energies_on(act), [])
        self.assertEqual(sum(1 for c in t.zone(P1, 'deck') if self.is_energy(c)), 3)

    # --- Glimmet TWM 108: Rock Shot ------------------------------------------
    async def test_glimmet_rock_shot_discards_one_energy(self):
        t = self.table()
        g = self.mine(t, GLIMMET, FIGHT, 2)
        await t.attack(g, 'Rock Shot')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(len(self.energies_on(g)), 1)
        self.assertEqual(sum(1 for c in t.zone(P1, 'discard') if self.is_energy(c)), 1)

    # --- Glimmora SSP 115: Corrosive Shards ----------------------------------
    # BUG: the 'Energy cards can't be attached from your opponent's hand' clause is never applied
    async def test_glimmora_corrosive_shards_poisons_and_blocks_energy_attach(self):
        t = self.table()
        g = self.mine(t, GLIMMORA, FIGHT, 1)
        bench = self.opp_bench(t)
        await t.attack(g, 'Corrosive Shards')
        self.assertEqual(self.dealt(), 20)
        self.assertIn(POISONED, t.conditions(self.opp))
        t.next_turn()
        e = t.put(t.basic_energy(WATER), P2, 'hand')
        tg = t.targets(e, 'DefaultEnergyPlayAbility', P2)
        self.assertNotIn(self.opp.entity_id, tg)
        self.assertIn(bench.entity_id, tg)                 # only "that Pokémon"

    async def test_glimmora_attach_block_expires_after_opponent_turn(self):
        t = self.table()
        g = self.mine(t, GLIMMORA, FIGHT, 1)
        await t.attack(g, 'Corrosive Shards')
        t.next_turn()
        t.next_turn()
        t.next_turn()                                      # opponent's following turn
        e = t.put(t.basic_energy(WATER), P2, 'hand')
        self.assertIn(self.opp.entity_id, t.targets(e, 'DefaultEnergyPlayAbility', P2))

    async def test_glimmora_attach_block_does_not_affect_attacker_side(self):
        t = self.table()
        g = self.mine(t, GLIMMORA, FIGHT, 1)
        await t.attack(g, 'Corrosive Shards')
        t.next_turn()
        t.next_turn()
        e = t.put(t.basic_energy(FIGHT), P1, 'hand')
        self.assertIn(g.entity_id, t.targets(e, 'DefaultEnergyPlayAbility', P1))

    # --- Lumiose City POR 77 -------------------------------------------------
    def stadium_entry(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_lumiose_city_benches_basic_ends_turn_once_per_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        rowlet = t.deck(P1, [ROWLET, DARTRIX])[0]
        stadium = t.stadium(LUMIOSE, P2)                   # either player's Stadium
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), [c for c in cards if c is rowlet][:count] or list(cards)[:count])[1]
        entry = self.stadium_entry(t, stadium)
        self.assertIsNotNone(entry)
        ended = await t.do(entry)
        self.assertIn(rowlet, t.zone(P1, 'bench'))
        self.assertTrue(all(name(c) != 'Dartrix' for c in offered))   # Basic only
        self.assertTrue(ended, 'their turn ends')

    async def test_lumiose_city_usable_by_opponent_on_their_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        stadium = t.stadium(LUMIOSE, P1)
        target = t.deck(P2, [ROWLET])[0]
        t.next_turn()
        entry = self.stadium_entry(t, stadium, P2)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P2)
        self.assertIn(target, t.zone(P2, 'bench'))

    async def test_lumiose_city_not_offered_with_full_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        for _ in range(5):
            self.mine(t, self.filler, zone='bench')
        t.deck(P1, [ROWLET])
        stadium = t.stadium(LUMIOSE, P1)
        self.assertIsNone(self.stadium_entry(t, stadium))

    # --- Powerglass SFA 63 ---------------------------------------------------
    async def test_powerglass_active_attaches_basic_energy_from_discard(self):
        t = self.table()
        p = self.mine(t, self.filler)
        tool = t.put(POWERGLASS, P1, 'hand')
        await t.play(tool, targets=[p.entity_id])
        e = t.put(t.basic_energy(GRASS), P1, 'discard')
        t.yes = True
        await t.checkup()
        self.assertIn(e, list(p.children))

    async def test_powerglass_on_bench_does_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        b = self.mine(t, self.filler, zone='bench')
        await t.play(t.put(POWERGLASS, P1, 'hand'), targets=[b.entity_id])
        e = t.put(t.basic_energy(GRASS), P1, 'discard')
        await t.checkup()
        self.assertNotIn(e, list(b.children))
        self.assertIn(e, t.zone(P1, 'discard'))

    async def test_powerglass_not_at_end_of_opponent_turn(self):
        t = self.table()
        p = self.mine(t, self.filler)
        await t.play(t.put(POWERGLASS, P1, 'hand'), targets=[p.entity_id])
        e = t.put(t.basic_energy(GRASS), P1, 'discard')
        t.next_turn()
        await t.checkup()
        self.assertIn(e, t.zone(P1, 'discard'))

    # --- Rowlet POR 10: Find a Friend ----------------------------------------
    async def test_rowlet_find_a_friend_takes_pokemon_only(self):
        t = self.table()
        r = self.mine(t, ROWLET, GRASS, 1)
        self.clear_hand(t)
        target = t.deck(P1, [DARTRIX, POTION])[0]
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), [c for c in cards if c is target][:count] or list(cards)[:count])[1]
        await t.attack(r, 'Find a Friend')
        self.assertIn(target, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertTrue(all(name(c) != 'Potion' for c in offered if c in t.zone(P1, 'deck')))

    # --- Dartrix SFA 4: United Wings -----------------------------------------
    # BUG: _has_attack_named compares lowercased text title to 'United Wings' case-sensitively -> always 0
    async def test_dartrix_united_wings_counts_discard_pokemon_with_attack(self):
        t = self.table()
        d = self.mine(t, DARTRIX, WATER, 1)
        for spec in (DARTRIX, DARTRIX, ROWLET, DECIDUEYE):
            t.put(spec, P1, 'discard')
        t.put(DARTRIX, P2, 'discard')                      # opponent's doesn't count
        await t.attack(d, 'United Wings')
        self.assertEqual(self.dealt(), 40)

    async def test_dartrix_united_wings_none_in_discard_zero(self):
        t = self.table()
        d = self.mine(t, DARTRIX, WATER, 1)
        t.put(ROWLET, P1, 'discard')
        await t.attack(d, 'United Wings')
        self.assertEqual(self.dealt(), 0)

    # --- Decidueye SFA 5 -----------------------------------------------------
    async def test_decidueye_stock_up_draws_to_seven(self):
        t = self.table()
        d = self.mine(t, DECIDUEYE, WATER, 1)
        self.clear_hand(t)
        for _ in range(3):
            t.put(self.item, P1, 'hand')
        await t.attack(d, 'Stock Up on Feathers')
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_decidueye_stock_up_with_seven_draws_none(self):
        t = self.table()
        d = self.mine(t, DECIDUEYE, WATER, 1)
        self.clear_hand(t)
        for _ in range(8):
            t.put(self.item, P1, 'hand')
        deck = len(t.zone(P1, 'deck'))
        await t.attack(d, 'Stock Up on Feathers')
        self.assertEqual(len(t.zone(P1, 'hand')), 8)
        self.assertEqual(len(t.zone(P1, 'deck')), deck)

    async def test_decidueye_power_shot_discards_grass_from_hand(self):
        t = self.table()
        d = self.mine(t, DECIDUEYE, GRASS, 1)
        self.clear_hand(t)
        g = t.put(t.basic_energy(GRASS), P1, 'hand')
        await t.attack(d, 'Power Shot')
        self.assertEqual(self.dealt(), 170)
        self.assertIn(g, t.zone(P1, 'discard'))

    async def test_decidueye_power_shot_without_grass_does_nothing(self):
        t = self.table()
        d = self.mine(t, DECIDUEYE, GRASS, 1)
        self.clear_hand(t)
        w = t.put(t.basic_energy(WATER), P1, 'hand')
        await t.attack(d, 'Power Shot')
        self.assertEqual(self.dealt(), 0)
        self.assertIn(w, t.zone(P1, 'hand'))

    # --- Galvantula SFA 2 ----------------------------------------------------
    async def test_galvantula_shocking_web_plus_80_with_lightning(self):
        t = self.table()
        g = self.mine(t, GALVANTULA, GRASS, 1)
        t.energy(g, LIGHT, 1)
        await t.attack(g, 'Shocking Web')
        self.assertEqual(self.dealt(), 130)

    async def test_galvantula_shocking_web_base_without_lightning(self):
        t = self.table()
        g = self.mine(t, GALVANTULA, GRASS, 2)
        await t.attack(g, 'Shocking Web')
        self.assertEqual(self.dealt(), 50)

    async def test_galvantula_compound_eyes_plus_50_vs_ability_active(self):
        t = self.table(opp=MOLTRES)
        g = self.mine(t, GALVANTULA, GRASS, 2)
        await t.attack(g, 'Shocking Web')
        self.assertEqual(self.dealt(), 100)

    async def test_galvantula_compound_eyes_ignores_benched_ability_pokemon(self):
        t = self.table()
        self.opp_bench(t, MOLTRES)
        g = self.mine(t, GALVANTULA, GRASS, 2)
        await t.attack(g, 'Shocking Web')
        self.assertEqual(self.dealt(), 50)

    # --- Patrat WHT 72: Procurement ------------------------------------------
    async def test_patrat_procurement_takes_item(self):
        t = self.table()
        p = self.mine(t, PATRAT, WATER, 1)
        self.clear_hand(t)
        t.deck(P1, [ROWLET, t.basic_energy(WATER)])
        target = t.deck(P1, [POTION])[0]
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), [c for c in cards if c is target][:count] or list(cards)[:count])[1]
        await t.attack(p, 'Procurement')
        self.assertIn(target, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertFalse(any(name(c) == 'Rowlet' or self.is_energy(c) for c in offered))

    # --- Watchog EPO 79 ------------------------------------------------------
    async def test_watchog_watcheck_reorders_top_five_of_opponent_deck(self):
        t = self.table()
        w = self.mine(t, WATCHOG, WATER, 1)
        top5 = t.deck(P2, [ROWLET, DARTRIX, POTION, PATRAT, LATIOS])   # last = top
        seen = []

        async def chooser(player_id, source_id, cards, count, *a, **k):
            seen.append((player_id, list(cards)))
            # new order, topmost first: the current bottom-most of the five
            return [c.entity_id for c in reversed(list(cards))]
        before = len(t.zone(P2, 'deck'))
        with patch.object(t.session, 'prompt_card_chooser', chooser):
            await t.attack(w, 'Watcheck')
        deck = t.zone(P2, 'deck')
        self.assertEqual(len(deck), before)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], P1)                           # attacker looks
        self.assertEqual(set(map(id, seen[0][1])), set(map(id, top5)))
        self.assertEqual(deck[-5:], top5[::-1])                    # reversed on top
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    async def test_watchog_quick_tail_smash_heads_80(self):
        t = self.table()
        w = self.mine(t, WATCHOG, WATER, 2)
        t.yes, t.heads = True, True
        await t.attack(w, 'Quick Tail Smash')
        self.assertEqual(self.dealt(), 80)

    async def test_watchog_quick_tail_smash_tails_does_nothing(self):
        t = self.table()
        w = self.mine(t, WATCHOG, WATER, 2)
        t.yes, t.heads = True, False
        await t.attack(w, 'Quick Tail Smash')
        self.assertEqual(self.dealt(), 0)

    async def test_watchog_quick_tail_smash_no_flip_20(self):
        t = self.table()
        w = self.mine(t, WATCHOG, WATER, 2)
        t.yes, t.heads = False, False
        await t.attack(w, 'Quick Tail Smash')
        self.assertEqual(self.dealt(), 20)

    # --- Latios SSP 77: Skill Dive -------------------------------------------
    async def test_latios_skill_dive_bench_no_weakness(self):
        t = self.table()
        l = self.mine(t, LATIOS, PSY, 2)
        b = self.opp_bench(t)
        b.set_attribute(AttrID.WEAKNESS_TYPES, [PSY.value])
        t.picks = lambda cards, count, prompt, display: [b] if b in cards else list(cards)[:count]
        await t.attack(l, 'Skill Dive')
        self.assertEqual(self.dealt(b), 50)
        self.assertEqual(self.dealt(), 0)

    async def test_latios_skill_dive_active_applies_weakness(self):
        t = self.table()
        l = self.mine(t, LATIOS, PSY, 2)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [PSY.value])
        self.opp_bench(t)
        t.picks = lambda cards, count, prompt, display: (
            [self.opp] if self.opp in cards else list(cards)[:count])
        await t.attack(l, 'Skill Dive')
        self.assertEqual(self.dealt(), 100)

    # --- Minun LTR 48 --------------------------------------------------------
    async def test_minun_negative_ion_reduces_next_attack_by_30(self):
        t = self.table()
        m = self.mine(t, MINUN, WATER, 1)
        m.set_attribute(AttrID.HP, 400)
        atk = self.filler_attack()
        await t.attack(m, 'Negative Ion')
        t.next_turn()
        t.energy(self.opp, WATER, sum(atk.cost.values()) if atk.cost else 0)
        await t.attack(self.opp, atk.title, pid=P2)
        self.assertEqual(400 - t.hp(m), max(0, atk.damage - 30))

    async def test_minun_negative_ion_expires_after_opponent_turn(self):
        t = self.table()
        m = self.mine(t, MINUN, WATER, 1)
        m.set_attribute(AttrID.HP, 400)
        atk = self.filler_attack()
        await t.attack(m, 'Negative Ion')
        t.next_turn()
        t.next_turn()
        t.next_turn()
        t.energy(self.opp, WATER, sum(atk.cost.values()) if atk.cost else 0)
        await t.attack(self.opp, atk.title, pid=P2)
        self.assertEqual(400 - t.hp(m), atk.damage)

    async def test_minun_electrishower_hits_each_opponent_pokemon(self):
        t = self.table()
        m = self.mine(t, MINUN, LIGHT, 1)
        b = self.opp_bench(t)
        b.set_attribute(AttrID.WEAKNESS_TYPES, [LIGHT.value])
        mb = self.mine(t, self.filler, zone='bench')
        await t.attack(m, 'Electrishower')
        self.assertEqual(self.dealt(), 10)
        self.assertEqual(self.dealt(b), 10)
        self.assertEqual(t.damage(mb), 0)

    # --- Cascoon LOT 27: Cocoon Collector ------------------------------------
    async def test_cascoon_cocoon_collector_benches_up_to_four(self):
        t = self.table()
        c = self.mine(t, CASCOON, WATER, 1)
        t.deck(P1, [SILCOON, CASCOON, SILCOON, CASCOON, CASCOON, WURMPLE, DUSTOX])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.attack(c, 'Cocoon Collector')
        bench = t.names(t.zone(P1, 'bench'))
        self.assertEqual(len(bench), 4)
        self.assertTrue(set(bench) <= {'Silcoon', 'Cascoon'})
        self.assertFalse(any(name(x) in ('Wurmple', 'Dustox') for x in offered))

    async def test_cascoon_cocoon_collector_respects_bench_space(self):
        t = self.table()
        c = self.mine(t, CASCOON, WATER, 1)
        for _ in range(3):
            self.mine(t, self.filler, zone='bench')
        t.deck(P1, [SILCOON, CASCOON, SILCOON, CASCOON])
        await t.attack(c, 'Cocoon Collector')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    # --- Dustox ROS 8 --------------------------------------------------------
    async def test_dustox_wind_shard_hits_benched_only(self):
        t = self.table()
        d = self.mine(t, DUSTOX, GRASS, 3)
        self.opp_bench(t)
        b = self.opp_bench(t)
        seen = []
        both = lambda c: (seen.extend(c), [b] if b in c else list(c)[:1])[1]
        t.pokemon = lambda c, p: both(c)[0]
        t.picks = lambda cards, count, prompt, display: both(cards)
        await t.attack(d, 'Wind Shard')
        self.assertEqual(self.dealt(b), 50)
        self.assertEqual(self.dealt(), 0)
        self.assertTrue(seen)
        self.assertNotIn(self.opp, seen)

    async def test_dustox_wind_shard_no_bench_does_nothing(self):
        t = self.table()
        d = self.mine(t, DUSTOX, GRASS, 3)
        await t.attack(d, 'Wind Shard')
        self.assertEqual(self.dealt(), 0)

    async def test_dustox_ko_takes_one_extra_prize(self):
        t = self.table()
        d = self.mine(t, DUSTOX, GRASS, 1)
        self.opp_bench(t)
        self.opp.set_attribute(AttrID.HP, 20)
        before = len(t.zone(P1, 'prizes'))
        await t.attack(d, 'Flap')
        self.assertNotIn(self.opp, t.zone(P2, 'active'))
        self.assertEqual(before - len(t.zone(P1, 'prizes')), 2)


if __name__ == '__main__':
    unittest.main()
