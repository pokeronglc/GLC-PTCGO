"""Bug hunt round 7, chunk 33: Lileep, Cradily, Great Tusk, Slither Wing,
Grimmsnarl, Porygon2, Beartic, Goldeen, Seaking, Rotom, Thundurus, Lady, Ryme,
Infernape, Talonflame -- each checked against its printed text, including the
cases where it should NOT work."""
import unittest
from unittest.mock import patch, AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.models.board import EnergyEntity
from spirit.tools.effect_smoke import P1, P2

GRASS, WATER, FIRE, FIGHT, LIGHT, DARK = (
    PokemonTypes.GRASS, PokemonTypes.WATER, PokemonTypes.FIRE,
    PokemonTypes.FIGHTING, PokemonTypes.LIGHTNING, PokemonTypes.DARKNESS)

LILEEP = 'SM12.Lileep_10'
CRADILY = 'BW10.Cradily_4'
GREAT_TUSK = 'SV05.GreatTusk_97'
SLITHER = 'SV4.SlitherWing_107'
GRIMMSNARL = 'SV07.Grimmsnarl_96'
PORYGON2 = 'SV4.Porygon2_143'
BEARTIC = 'SWSH9.Beartic_43'
GOLDEEN = 'SWSH1.Goldeen_46'
SEAKING = 'SV085.Seaking_21'
ROTOM = 'SV08.Rotom_61'
THUNDURUS = 'SM11.Thundurus_68'
LADY = 'SWSH11.Lady_159'
RYME = 'SV3.Ryme_194'
INFERNAPE = 'SV06.Infernape_33'
TALONFLAME = 'SV07.Talonflame_123'

TORNADUS = 'BW2.Tornadus_89'
EXPLORER = 'SV05.ExplorersGuidance_147'      # Ancient Supporter
LILLIE = 'SM1.Lillie_122'                    # non-Ancient Supporter
FESTIVAL = 'SV06.FestivalGrounds_149'
ROCKY = 'ME3.RockyFightingEnergy_87'         # Special Energy
PAN = 'SM6.MetalFryingPan_112'               # Tool
SWITCH = 'SM1.Switch_132'                    # Item


def name(card):
    return def_for(card.archetype_id).display_name


def neutral(p, hp=400):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.set_attribute(AttrID.HP, hp)
    return p


class Chunk33(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = neutral(t.put(opp or self.filler, P2, 'active'))
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=400):
        p = neutral(t.put(spec, P1, zone), hp)
        if count:
            t.energy(p, kind, count)
        return p

    def dealt(self, p=None):
        return 400 - (p or self.opp).get_attribute(AttrID.HP, 0)

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, {'hand': 'hand', 'deck': 'deck'}[zone])
        for c in list(area.children):
            area.remove_child(c)

    # --- Lileep CEC 10 -------------------------------------------------------
    async def test_lileep_confuse_ray(self):
        t = self.table()
        lil = self.mine(t, LILEEP, GRASS, 1)
        await t.attack(lil, 'Confuse Ray')
        self.assertEqual(t.conditions(self.opp), {CONFUSED})
        self.assertEqual(self.dealt(), 0)
        self.assertEqual(t.conditions(lil), set())

    # --- Cradily PLB 4 -------------------------------------------------------
    async def test_cradily_lifesplosion_one_stage2_per_energy(self):
        t = self.table()
        cr = self.mine(t, CRADILY, GRASS, 2)
        deck_cards = t.deck(P1, [INFERNAPE, GRIMMSNARL, TALONFLAME, GOLDEEN, SEAKING])
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.attack(cr, 'Lifesplosion')
        bench = t.zone(P1, 'bench')
        self.assertEqual(len(bench), 2)
        self.assertTrue(all(name(c) in ('Infernape', 'Grimmsnarl', 'Talonflame') for c in bench))
        self.assertNotIn(deck_cards[3], offered)          # Basic not choosable
        self.assertNotIn(deck_cards[4], offered)          # Stage 1 not choosable
        self.assertEqual(self.dealt(), 0)

    async def test_cradily_spiral_drain_heals_20(self):
        t = self.table()
        cr = self.mine(t, CRADILY, GRASS, 3, hp=60)   # 120 max HP
        await t.attack(cr, 'Spiral Drain')
        self.assertEqual(self.dealt(), 60)
        self.assertEqual(t.hp(cr), 80)

    # --- Great Tusk TEF 97 ---------------------------------------------------
    async def test_great_tusk_land_collapse_plain_discards_one(self):
        t = self.table()
        gt = self.mine(t, GREAT_TUSK, WATER, 2)
        lillie = t.put(LILLIE, P1, 'hand')
        await t.play(lillie)                              # non-Ancient Supporter
        before = len(t.zone(P2, 'deck'))
        await t.attack(gt, 'Land Collapse')
        self.assertEqual(before - len(t.zone(P2, 'deck')), 1)
        self.assertEqual(len(t.zone(P2, 'discard')), 1)

    # BUG: Land Collapse ignores "played an Ancient Supporter this turn" (always discards 1)
    async def test_great_tusk_land_collapse_after_ancient_supporter(self):
        t = self.table()
        gt = self.mine(t, GREAT_TUSK, WATER, 2)
        await t.play(t.put(EXPLORER, P1, 'hand'))
        before = len(t.zone(P2, 'deck'))
        await t.attack(gt, 'Land Collapse')
        self.assertEqual(before - len(t.zone(P2, 'deck')), 4)

    # --- Slither Wing PAR 107 ------------------------------------------------
    async def test_slither_wing_stomp_off(self):
        t = self.table()
        sw = self.mine(t, SLITHER, FIGHT, 1)
        before = len(t.zone(P2, 'deck'))
        await t.attack(sw, 'Stomp Off')
        self.assertEqual(before - len(t.zone(P2, 'deck')), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 0)    # my deck untouched (no discards)

    async def test_slither_wing_burning_turbulence(self):
        t = self.table()
        sw = self.mine(t, SLITHER, FIGHT, 2)
        await t.attack(sw, 'Burning Turbulence')
        self.assertEqual(self.dealt(), 120)
        self.assertEqual(self.dealt(sw), 90)
        self.assertEqual(t.conditions(self.opp), {BURNED})
        self.assertEqual(t.conditions(sw), set())

    # --- Grimmsnarl SCR 96 ---------------------------------------------------
    async def test_grimmsnarl_goad_n_grab_hits_new_active(self):
        t = self.table()
        gr = self.mine(t, GRIMMSNARL, DARK, 2)
        old = self.opp
        new = neutral(t.put(self.filler, P2, 'bench'))
        await t.attack(gr, "Goad 'n' Grab")
        self.assertIs(t.active(P2), new)
        self.assertIn(old, t.zone(P2, 'bench'))
        self.assertEqual(self.dealt(new), 160)
        self.assertEqual(self.dealt(old), 0)

    async def test_grimmsnarl_goad_n_grab_no_bench_no_damage(self):
        t = self.table()
        gr = self.mine(t, GRIMMSNARL, DARK, 2)
        await t.attack(gr, "Goad 'n' Grab")
        self.assertIs(t.active(P2), self.opp)
        self.assertEqual(self.dealt(), 0)

    async def test_grimmsnarl_knuckle_sandwich_discards_two(self):
        t = self.table()
        gr = self.mine(t, GRIMMSNARL, DARK, 3)
        await t.attack(gr, 'Knuckle Sandwich')
        self.assertEqual(self.dealt(), 160)
        self.assertEqual(len([c for c in gr.children if isinstance(c, EnergyEntity)]), 1)

    # --- Porygon2 PAR 143 ----------------------------------------------------
    async def test_porygon2_powered_ball(self):
        t = self.table()
        p2 = self.mine(t, PORYGON2, WATER, 2)
        await t.attack(p2, 'Powered Ball')
        self.assertEqual(self.dealt(), 50)
        self.assertEqual(len([c for c in p2.children if isinstance(c, EnergyEntity)]), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    # --- Beartic BRS 43 ------------------------------------------------------
    async def test_beartic_sheer_cold_locks_defender_next_turn_only(self):
        t = self.table()
        b = self.mine(t, BEARTIC, WATER, 2)
        t.energy(self.opp, WATER, 4)
        await t.attack(b, 'Sheer Cold')
        self.assertEqual(self.dealt(), 40)
        t.next_turn()
        self.assertFalse(t.offers(self.opp, 'UsePokemonAttack', P2))
        t.next_turn()
        t.next_turn()
        self.assertTrue(t.offers(self.opp, 'UsePokemonAttack', P2))

    async def test_beartic_lock_ends_if_defender_switched(self):
        t = self.table()
        b = self.mine(t, BEARTIC, WATER, 2)
        t.energy(self.opp, WATER, 4)
        other = neutral(t.put(self.filler, P2, 'bench'))
        t.energy(other, WATER, 4)
        await t.attack(b, 'Sheer Cold')
        t.next_turn()
        sw = t.put(SWITCH, P2, 'hand')
        t.pokemon = lambda c, p: other if other in c else c[0]
        await t.play(sw, pid=P2)
        self.assertIs(t.active(P2), other)
        self.assertTrue(t.offers(other, 'UsePokemonAttack', P2))

    # --- Goldeen SSH 46 ------------------------------------------------------
    async def test_goldeen_collect_draws_one(self):
        t = self.table()
        g = self.mine(t, GOLDEEN, WATER, 1)
        self.clear(t, P1, 'hand')
        await t.attack(g, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(self.dealt(), 0)

    # --- Seaking PRE 21 ------------------------------------------------------
    async def test_seaking_rapid_draw_once_without_festival(self):
        t = self.table()
        s = self.mine(t, SEAKING, WATER, 1)
        self.clear(t, P1, 'hand')
        ended = await t.attack(s, 'Rapid Draw')
        self.assertTrue(ended)
        self.assertEqual(self.dealt(), 60)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)

    async def test_seaking_festival_lead_attacks_twice(self):
        t = self.table()
        s = self.mine(t, SEAKING, WATER, 1)
        self.clear(t, P1, 'hand')
        t.stadium(FESTIVAL, P2)
        with patch.object(t.session, 'prompt_player_choice', AsyncMock(return_value=0)):
            ended = await t.attack(s, 'Rapid Draw')
            self.assertFalse(ended)
            ended = await t.attack(s, 'Rapid Draw')
        self.assertTrue(ended)
        self.assertEqual(self.dealt(), 120)
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    # --- Rotom SSP 61 --------------------------------------------------------
    # BUG: Crushing Pulse discards Items but leaves Pokemon Tool cards in the hand
    async def test_rotom_crushing_pulse_discards_items_and_tools_only(self):
        t = self.table()
        r = self.mine(t, ROTOM, LIGHT, 1)
        self.clear(t, P2, 'hand')
        item = t.put(SWITCH, P2, 'hand')
        tool = t.put(PAN, P2, 'hand')
        sup = t.put(LILLIE, P2, 'hand')
        mon = t.put(GOLDEEN, P2, 'hand')
        await t.attack(r, 'Crushing Pulse')
        self.assertEqual(set(t.zone(P2, 'hand')), {sup, mon})
        self.assertEqual(set(t.zone(P2, 'discard')), {item, tool})

    async def test_rotom_energy_short_counts_opponent_energy(self):
        t = self.table()
        r = self.mine(t, ROTOM, LIGHT, 1)
        t.energy(self.opp, WATER, 3)
        await t.attack(r, 'Energy Short')
        self.assertEqual(self.dealt(), 60)

    async def test_rotom_energy_short_zero_energy(self):
        t = self.table()
        r = self.mine(t, ROTOM, LIGHT, 2)                 # my own Energy doesn't count
        await t.attack(r, 'Energy Short')
        self.assertEqual(self.dealt(), 0)

    # --- Thundurus UNM 68 ----------------------------------------------------
    async def test_thundurus_thunderous_gale_with_benched_tornadus(self):
        t = self.table()
        th = self.mine(t, THUNDURUS, LIGHT, 2)
        self.mine(t, TORNADUS, zone='bench')
        await t.attack(th, 'Thunderous Gale')
        self.assertEqual(self.dealt(), 70)

    async def test_thundurus_thunderous_gale_without_tornadus(self):
        t = self.table()
        th = self.mine(t, THUNDURUS, LIGHT, 2)
        self.mine(t, self.filler, zone='bench')
        t.put(TORNADUS, P2, 'bench')                      # opponent's Tornadus doesn't count
        await t.attack(th, 'Thunderous Gale')
        self.assertEqual(self.dealt(), 20)

    async def test_thundurus_raging_thunder_hits_own_bench(self):
        t = self.table()
        th = self.mine(t, THUNDURUS, LIGHT, 3)
        bench = self.mine(t, self.filler, zone='bench')
        obench = neutral(t.put(self.filler, P2, 'bench'))
        await t.attack(th, 'Raging Thunder')
        self.assertEqual(self.dealt(), 120)
        self.assertEqual(self.dealt(bench), 40)
        self.assertEqual(self.dealt(obench), 0)
        self.assertEqual(self.dealt(th), 0)

    # --- Lady LOR 159 --------------------------------------------------------
    async def test_lady_searches_up_to_four_basic_energy(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        basics = [t.put(t.basic_energy(k), P1, 'deck') for k in (FIRE, WATER, GRASS, FIGHT, LIGHT)]
        rocky = t.put(ROCKY, P1, 'deck')
        offered = []
        t.picks = lambda cards, count, prompt, display: (
            offered.extend(cards), list(cards)[:count])[1]
        await t.play(t.put(LADY, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 4)
        self.assertTrue(all(c in basics for c in hand))
        self.assertNotIn(rocky, offered)
        self.assertIn(rocky, t.zone(P1, 'deck'))

    # --- Ryme OBF 194 --------------------------------------------------------
    async def test_ryme_draws_three_and_switches_opponent(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        old = self.opp
        new = neutral(t.put(self.filler, P2, 'bench'))
        await t.play(t.put(RYME, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertIs(t.active(P2), new)
        self.assertIn(old, t.zone(P2, 'bench'))

    async def test_ryme_without_opponent_bench_still_draws(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        card = t.put(RYME, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertIs(t.active(P2), self.opp)

    # --- Infernape TWM 33 ----------------------------------------------------
    async def test_infernape_pyro_dance_fire_and_fighting(self):
        t = self.table()
        inf = self.mine(t, INFERNAPE)
        bench = self.mine(t, self.filler, zone='bench')
        self.clear(t, P1, 'hand')
        fire = t.put(t.basic_energy(FIRE), P1, 'hand')
        fight = t.put(t.basic_energy(FIGHT), P1, 'hand')
        water = t.put(t.basic_energy(WATER), P1, 'hand')
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return [c for c in cards if c in (fire, fight)][:count]
        t.picks = picks
        targets = iter([inf, bench, inf, bench])
        t.pokemon = lambda c, p: next(targets)
        await t.use(inf, 'Pyro Dance')
        self.assertNotIn(water, offered)
        attached = [c for c in inf.children + bench.children if c in (fire, fight)]
        self.assertEqual(set(attached), {fire, fight})
        self.assertIn(water, t.zone(P1, 'hand'))
        self.assertIsNone(t.ability_offer(inf, 'Pyro Dance'))     # once per turn

    async def test_infernape_pyro_dance_not_two_fire(self):
        t = self.table()
        inf = self.mine(t, INFERNAPE)
        self.clear(t, P1, 'hand')
        f1 = t.put(t.basic_energy(FIRE), P1, 'hand')
        f2 = t.put(t.basic_energy(FIRE), P1, 'hand')
        t.picks = lambda cards, count, prompt, display: list(cards)[:count]
        await t.use(inf, 'Pyro Dance')
        on = [c for c in inf.children if c in (f1, f2)]
        self.assertEqual(len(on), 1)

    # --- Talonflame SCR 123 --------------------------------------------------
    async def test_talonflame_aero_chase_retreat_two_or_more(self):
        t = self.table()                                  # Snorlax filler, big retreat
        self.assertGreaterEqual(t.retreat(self.opp), 2)
        tf = self.mine(t, TALONFLAME, WATER, 2)
        await t.attack(tf, 'Aero Chase')
        self.assertEqual(self.dealt(), 220)

    async def test_talonflame_aero_chase_retreat_one(self):
        t = self.table(GOLDEEN)
        self.assertEqual(t.retreat(self.opp), 1)
        tf = self.mine(t, TALONFLAME, WATER, 2)
        await t.attack(tf, 'Aero Chase')
        self.assertEqual(self.dealt(), 110)


if __name__ == '__main__':
    unittest.main()
