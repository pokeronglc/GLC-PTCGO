"""Bug hunt round 7, chunk 19: Victini (SIT 23 / GRI 10), Unown 30C 72, Alolan
Meowth, Mist Energy, Veluza, Peony, Togepi, Togekiss, Munchlax, Firebreather,
Axew, Fraxure, Haxorus -- each checked against its printed text, including the
cases where it should NOT work.  (Fairy Energy TEU is a basic Energy: skipped.)"""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, PSY = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.PSYCHIC
GRASS, FIGHT, METAL = PokemonTypes.GRASS, PokemonTypes.FIGHTING, PokemonTypes.METAL

VICTINI_SIT = 'SWSH12.Victini_23'     # chunk path said BW11.Victini_23 (wrong printing)
VICTINI_GRI = 'SM2.Victini_10'
UNOWN = 'ME55.Unown_72'
MEOWTH = 'SM8.AlolanMeowth_118'
MIST = 'SV05.MistEnergy_161'
VELUZA = 'SV4.Veluza_54'
PEONY = 'SWSH6.Peony_150'
TOGEPI = 'SV3.Togepi_83'
TOGEKISS = 'SV08.Togekiss_72'
MUNCHLAX = 'SM11.Munchlax_173'
FIREBREATHER = 'ME2.Firebreather_89'
AXEW, FRAXURE, HAXORUS = 'SWSH9.Axew_110', 'SV065.Fraxure_45', 'SV065.Haxorus_46'
EXEGGUTOR = 'BW9.Exeggutor_5'          # Blockade 10 [C]; Stomp 60 (+30 on heads)
MISDREAVUS = 'SM4.Misdreavus_39'       # Confuse Ray
WEEZING = 'SWSH2.GalarianWeezing_113'
BOSS = 'ME1.BosssOrders_114'
THERAPEUTIC = 'SV2.TherapeuticEnergy_193'


class RealCoinTable(Table):
    """Coin flips go through the real EffectContext.flip_coins (so Victory
    Star re-flip prompts happen); the RNG is scripted via `self.rng`."""

    def __init__(self, test):
        super().__init__(test)
        self.rng = []

    def _patches(self):
        table = self
        kept = [p for p in super()._patches() if p.attribute != 'flip_coins']

        def choice(options):
            return 0 if table.rng.pop(0) else 1
        return kept + [patch('spirit.game.session.effects.random.choice', choice)]


class Chunk19(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, cls=Table, opp=None):
        t = cls(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def dealt(self, t):
        return 400 - t.hp(self.opp)

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, zone)
        for c in list(area.children):
            area.remove_child(c)

    def is_basic(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    # --- Victini SIT 23: Assisting Flame -----------------------------------
    async def test_victini_sit_assisting_flame_attaches_two_fire_from_discard(self):
        t = self.table()
        self.assertEqual(def_for(fixtures.definition(VICTINI_SIT).guid).set_code, 'SWSH12')
        v = self.mine(t, VICTINI_SIT, FIRE, 1)
        bench = self.mine(t, self.filler, zone='bench')
        fires = [t.put(t.basic_energy(FIRE), P1, 'discard') for _ in range(3)]
        water = t.put(t.basic_energy(WATER), P1, 'discard')
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return cards[:count]
        t.picks = picks
        targets = iter([v, bench])
        t.pokemon = lambda cands, prompt: next(targets)
        await t.attack(v, 'Assisting Flame')
        self.assertEqual(self.dealt(t), 20)
        self.assertNotIn(water, offered)
        self.assertEqual(sum(1 for f in fires if f in v.children), 1)
        self.assertEqual(sum(1 for f in fires if f in bench.children), 1)
        self.assertEqual(sum(1 for f in fires if f in t.zone(P1, 'discard')), 1)

    async def test_victini_sit_assisting_flame_no_fire_in_discard(self):
        t = self.table()
        v = self.mine(t, VICTINI_SIT, FIRE, 1)
        water = t.put(t.basic_energy(WATER), P1, 'discard')
        await t.attack(v, 'Assisting Flame')
        self.assertEqual(self.dealt(t), 20)
        self.assertIn(water, t.zone(P1, 'discard'))
        self.assertEqual(len(v.children), 1)

    # --- Victini GRI 10: Victory Star --------------------------------------
    async def test_victini_gri_victory_star_reflip_from_bench(self):
        t = self.table(RealCoinTable)
        ex = self.mine(t, EXEGGUTOR, GRASS, 3)
        self.mine(t, VICTINI_GRI, zone='bench')
        t.rng = [False, True]             # tails, then the re-flip is heads
        t.yes = True
        await t.attack(ex, 'Stomp')
        self.assertEqual(self.dealt(t), 90)
        self.assertTrue(t.state.attack_coin_reroll_used)

    async def test_victini_gri_opponents_victini_gives_no_reflip(self):
        t = self.table(RealCoinTable)
        ex = self.mine(t, EXEGGUTOR, GRASS, 3)
        self.mine(t, VICTINI_GRI, zone='bench', pid=P2)
        t.rng = [False, True]
        t.yes = True
        await t.attack(ex, 'Stomp')
        self.assertEqual(self.dealt(t), 60)
        self.assertFalse(any('flipping again' in (p or '') for p in t.prompts))

    async def test_victini_gri_victory_star_blocked_by_ability_lock(self):
        t = self.table(RealCoinTable, opp=WEEZING)    # Neutralizing Gas
        ex = self.mine(t, EXEGGUTOR, GRASS, 3)
        self.mine(t, VICTINI_GRI, zone='bench')
        t.rng = [False, True]
        t.yes = True
        await t.attack(ex, 'Stomp')
        self.assertEqual(self.dealt(t), 60)

    # --- Unown 30C 72: Mysterious Signal ------------------------------------
    async def test_unown_mysterious_signal_ko_takes_extra_prize(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        u = self.mine(t, UNOWN, PSY, 2)
        self.opp.set_attribute(AttrID.HP, 40)
        await t.attack(u, 'Mysterious Signal')
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 4)

    async def test_unown_mysterious_signal_no_ko_no_prize(self):
        t = self.table()
        u = self.mine(t, UNOWN, PSY, 2)
        await t.attack(u, 'Mysterious Signal')
        self.assertEqual(self.dealt(t), 40)
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)

    # --- Alolan Meowth LOT 118: Spoil the Fun -------------------------------
    async def test_alolan_meowth_spoil_the_fun_going_second_first_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        meowth = self.mine(t, MEOWTH, zone='bench', pid=P2)
        old = self.opp
        t.board.move_card(old.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(meowth.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        me = t.active(P1)
        self.big(me)
        t.state.turn_number = 1
        t.next_turn()                       # turn 2: P2's first turn (went second)
        self.assertEqual(t.state.turn_number, 2)
        await t.attack(meowth, 'Spoil the Fun', pid=P2)
        self.assertEqual(400 - t.hp(me), 70)

    async def test_alolan_meowth_spoil_the_fun_later_turn(self):
        t = self.table()
        m = self.mine(t, MEOWTH)
        await t.attack(m, 'Spoil the Fun')   # turn 3: P1 went first
        self.assertEqual(self.dealt(t), 10)

    # --- Mist Energy TEF 161 -----------------------------------------------
    async def _confuse_ray_on(self, mist):
        t = self.table(opp=MISDREAVUS)
        t.energy(self.opp, PSY, 1)
        me = self.mine(t, self.filler)
        self.big(me)
        if mist:
            await t.play(t.put(MIST, P1, 'hand'), targets=[me.entity_id])
        t.next_turn()
        t.heads = True
        await t.attack(self.opp, 'Confuse Ray', pid=P2)
        return t, me

    async def test_mist_energy_prevents_attack_effects(self):
        t, me = await self._confuse_ray_on(True)
        self.assertNotIn(CONFUSED, t.conditions(me))

    async def test_without_mist_energy_confuse_ray_works(self):
        t, me = await self._confuse_ray_on(False)
        self.assertIn(CONFUSED, t.conditions(me))

    async def test_mist_energy_does_not_prevent_damage(self):
        t = self.table(opp=EXEGGUTOR)
        t.energy(self.opp, GRASS, 1)
        me = self.mine(t, self.filler)
        self.big(me)
        await t.play(t.put(MIST, P1, 'hand'), targets=[me.entity_id])
        t.next_turn()
        await t.attack(self.opp, 'Blockade', pid=P2)
        self.assertEqual(400 - t.hp(me), 10)

    # --- Veluza PAR 54 -----------------------------------------------------
    async def test_veluza_hydro_pump_counts_water(self):
        t = self.table()
        v = self.mine(t, VELUZA, WATER, 3)
        t.energy(v, FIRE, 1)
        await t.attack(v, 'Hydro Pump')
        self.assertEqual(self.dealt(t), 60 + 3 * 20)

    async def _veluza_ko(self, active=True):
        t = self.table(opp=EXEGGUTOR)
        t.energy(self.opp, GRASS, 1)
        if active:
            v = self.mine(t, VELUZA, WATER, 2)
            bench = self.mine(t, self.filler, zone='bench')
        else:
            bench = self.mine(t, self.filler)
            v = self.mine(t, VELUZA, WATER, 2, zone='bench')
        waters = list(v.children)
        v.set_attribute(AttrID.HP, 10)
        return t, v, bench, waters

    async def test_veluza_fillet_memento_moves_water_on_active_ko(self):
        t, v, bench, waters = await self._veluza_ko()
        t.next_turn()
        await t.attack(self.opp, 'Blockade', pid=P2)
        self.assertIn(v, t.zone(P1, 'discard'))
        self.assertEqual(sum(1 for w in waters if w in bench.children), 2)

    async def test_veluza_fillet_memento_not_when_ko_by_checkup(self):
        t, v, bench, waters = await self._veluza_ko()
        v.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
        await t.checkup()
        self.assertNotIn(v, t.board.pokemon_in_play(P1))
        self.assertFalse(any(w in bench.children for w in waters))

    # --- Peony CRE 150 ------------------------------------------------------
    async def test_peony_discards_hand_and_takes_two_trainers(self):
        t = self.table()
        self.mine(t, self.filler)
        keep = t.put(self.filler, P1, 'hand')
        mon = t.deck(P1, [self.filler])[0]
        boss = t.deck(P1, [BOSS])[0]
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            self.assertEqual(count, 2)
            return [boss] + [c for c in cards if c is not boss][:1]
        t.picks = picks
        await t.play(t.put(PEONY, P1, 'hand'))
        self.assertIn(keep, t.zone(P1, 'discard'))
        self.assertNotIn(mon, offered)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertIn(boss, hand)

    async def test_peony_may_take_zero(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(self.item, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        await t.play(t.put(PEONY, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Togepi OBF 83: Whiny Voice ----------------------------------------
    async def test_togepi_whiny_voice_shuffles_random_card(self):
        t = self.table()
        tg = self.mine(t, TOGEPI, WATER, 1)
        card = t.put(BOSS, P2, 'hand')
        deck_before = len(t.zone(P2, 'deck'))
        await t.attack(tg, 'Whiny Voice')
        self.assertEqual(t.zone(P2, 'hand'), [])
        self.assertIn(card, t.zone(P2, 'deck'))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before + 1)

    async def test_togepi_whiny_voice_empty_hand_still_usable(self):
        t = self.table()
        tg = self.mine(t, TOGEPI, WATER, 1)
        deck_before = len(t.zone(P2, 'deck'))
        # An attack can always be declared even when its effect does nothing.
        self.assertIsNotNone(t.attack_offer(tg, 'Whiny Voice'))
        await t.attack(tg, 'Whiny Voice')
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before)

    # --- Togekiss SSP 72: Wonder Kiss --------------------------------------
    async def _togekiss_ko(self, heads, kisses=1, ko_bench=False):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        ex = self.mine(t, EXEGGUTOR, GRASS, 1)
        for _ in range(kisses):
            self.mine(t, TOGEKISS, zone='bench')
        self.opp.set_attribute(AttrID.HP, 10)
        t.heads = heads
        await t.attack(ex, 'Blockade')
        return t

    async def test_togekiss_wonder_kiss_heads_extra_prize(self):
        t = await self._togekiss_ko(True)
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 4)

    async def test_togekiss_wonder_kiss_tails_normal(self):
        t = await self._togekiss_ko(False)
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 5)

    async def test_togekiss_wonder_kiss_does_not_stack(self):
        t = await self._togekiss_ko(True, kisses=2)
        self.assertEqual(len(t.zone(P1, 'prizes')), 4)

    async def test_togekiss_wonder_kiss_not_for_own_active(self):
        t = self.table(opp=EXEGGUTOR)
        t.energy(self.opp, GRASS, 1)
        me = self.mine(t, self.filler)
        me.set_attribute(AttrID.HP, 10)
        t.put(self.filler, P1, 'bench')
        self.mine(t, TOGEKISS, zone='bench')
        t.next_turn()
        t.heads = True
        await t.attack(self.opp, 'Blockade', pid=P2)
        self.assertIn(me, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)

    # --- Munchlax UNM 173: Snack Search ------------------------------------
    async def test_munchlax_snack_search_heads_and_turn_ends(self):
        t = self.table()
        self.mine(t, self.filler)
        m = self.mine(t, MUNCHLAX, zone='bench')
        card = t.put(BOSS, P1, 'discard')
        t.heads = True
        ended = await t.use(m, 'Snack Search')
        self.assertIs(t.zone(P1, 'deck')[-1], card)        # top = last child
        self.assertNotIn(card, t.zone(P1, 'discard'))
        self.assertTrue(ended)          # the executor ends the turn on True

    async def test_munchlax_snack_search_tails_still_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        m = self.mine(t, MUNCHLAX, zone='bench')
        card = t.put(BOSS, P1, 'discard')
        t.heads = False
        ended = await t.use(m, 'Snack Search')
        self.assertIn(card, t.zone(P1, 'discard'))
        self.assertTrue(ended)          # the executor ends the turn on True

    async def test_munchlax_snack_search_empty_discard_not_offered(self):
        t = self.table()
        self.mine(t, self.filler)
        m = self.mine(t, MUNCHLAX, zone='bench')
        self.assertIsNone(t.ability_offer(m, 'Snack Search'))

    # --- Firebreather PFL 89 -----------------------------------------------
    async def test_firebreather_takes_basic_fire_only(self):
        t = self.table()
        self.mine(t, self.filler)
        fires = t.deck(P1, [t.basic_energy(FIRE)] * 8)
        water = t.deck(P1, [t.basic_energy(WATER)])[0]
        mist = t.deck(P1, [MIST])[0]
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            self.assertEqual(count, 7)
            return cards[:count]
        t.picks = picks
        await t.play(t.put(FIREBREATHER, P1, 'hand'))
        self.assertNotIn(water, offered)
        self.assertNotIn(mist, offered)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 7)
        self.assertTrue(all(c in fires for c in hand))

    # --- Axew BRS 110: Ultra Evolution -------------------------------------
    async def test_axew_ultra_evolution_heads_evolves_into_haxorus(self):
        t = self.table()
        a = self.mine(t, AXEW, WATER, 1)
        hax = t.deck(P1, [HAXORUS])[0]
        t.deck(P1, [FRAXURE])
        t.heads = True
        await t.attack(a, 'Ultra Evolution')
        self.assertIs(t.active(P1), hax)
        self.assertEqual(def_for(t.active(P1).archetype_id).display_name, 'Haxorus')

    async def test_axew_ultra_evolution_tails_nothing(self):
        t = self.table()
        a = self.mine(t, AXEW, WATER, 1)
        hax = t.deck(P1, [HAXORUS])[0]
        t.heads = False
        await t.attack(a, 'Ultra Evolution')
        self.assertIs(t.active(P1), a)
        self.assertIn(hax, t.zone(P1, 'deck'))

    async def test_axew_ultra_evolution_wont_take_fraxure(self):
        t = self.table()
        a = self.mine(t, AXEW, WATER, 1)
        frax = t.deck(P1, [FRAXURE])[0]
        offered = []

        def picks(cards, count, prompt, display):
            offered.extend(cards)
            return cards[:count]
        t.picks = picks
        t.heads = True
        await t.attack(a, 'Ultra Evolution')
        self.assertNotIn(frax, offered)
        self.assertIs(t.active(P1), a)

    # --- Fraxure SFA 45 -----------------------------------------------------
    async def test_fraxure_dragon_pulse_discards_top_card(self):
        t = self.table()
        f = self.mine(t, FRAXURE)
        t.energy(f, FIGHT, 1)
        t.energy(f, METAL, 1)
        top = t.zone(P1, 'deck')
        before = len(top)
        await t.attack(f, 'Dragon Pulse')
        self.assertEqual(self.dealt(t), 80)
        self.assertEqual(len(t.zone(P1, 'deck')), before - 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    # BUG: Unnerve ("Item or Supporter card") has no branch in bw_era BW text passive blocks_trainer_effects; Boss's Orders drags Fraxure
    async def test_fraxure_unnerve_blocks_opponents_boss_orders(self):
        t = self.table()
        f = self.mine(t, FRAXURE, zone='bench')
        self.mine(t, self.filler)
        t.next_turn()
        boss = t.put(BOSS, P2, 'hand')
        if t.can(boss, 'UseTrainerCard', pid=P2):
            await t.play(boss, pid=P2)
        self.assertIn(f, t.zone(P1, 'bench'))

    # --- Haxorus SFA 46 -----------------------------------------------------
    async def test_haxorus_bring_down_the_axe_kos_special_energy_holder(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        h = self.mine(t, HAXORUS, FIGHT, 1)
        t.attach(THERAPEUTIC, self.opp)
        await t.attack(h, 'Bring Down the Axe')
        self.assertIn(self.opp, t.zone(P2, 'discard'))
        self.assertEqual(len(t.zone(P1, 'prizes')), 5)

    async def test_haxorus_bring_down_the_axe_stopped_by_mist_energy(self):
        # Mist Energy is Special Energy, but it also prevents all attack
        # effects on its holder -- the Knock Out is an effect, so it fails.
        t = self.table()
        t.put(self.filler, P2, 'bench')
        h = self.mine(t, HAXORUS, FIGHT, 1)
        t.attach(MIST, self.opp)
        await t.attack(h, 'Bring Down the Axe')
        self.assertIs(t.active(P2), self.opp)

    async def test_haxorus_bring_down_the_axe_basic_energy_only(self):
        t = self.table()
        t.put(self.filler, P2, 'bench')
        h = self.mine(t, HAXORUS, FIGHT, 1)
        t.energy(self.opp, WATER, 2)
        await t.attack(h, 'Bring Down the Axe')
        self.assertIs(t.active(P2), self.opp)
        self.assertEqual(self.dealt(t), 0)

    async def test_haxorus_dragon_pulse_discards_three(self):
        t = self.table()
        h = self.mine(t, HAXORUS)
        t.energy(h, FIGHT, 1)
        t.energy(h, METAL, 1)
        before = len(t.zone(P1, 'deck'))
        await t.attack(h, 'Dragon Pulse')
        self.assertEqual(self.dealt(t), 230)
        self.assertEqual(len(t.zone(P1, 'deck')), before - 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 3)


if __name__ == '__main__':
    unittest.main()
