"""Bug hunt round 7, chunk 44: Team Rocket's Energy, Jynx, Dwebble, Crustle,
Poltchageist, Sinistcha, Team Rocket's Ariana, Snivy, Serperior, Scyther,
Heracross, Pinsir, Dhelmise, Brave Bangle, Fuecoco -- each checked against
its printed text, including the cases where it should NOT work.

Path corrections: the chunk listed Dwebble/Crustle as SWSH7 and
Heracross/Pinsir as BW7/XY8; the printed DRI/TWM cards are SV10 and SV06.
"""
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED, PARALYZED
from spirit.game import data_utils
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.passives import energy_provided_options
from spirit.tools.effect_smoke import P1, P2

GRASS, WATER, PSY, FIRE = (PokemonTypes.GRASS, PokemonTypes.WATER,
                           PokemonTypes.PSYCHIC, PokemonTypes.FIRE)

TR_ENERGY = 'SV10.TeamRocketsEnergy_182'
TR_MURKROW, TR_DROWZEE = 'SV10.TeamRocketsMurkrow_127', 'SV10.TeamRocketsDrowzee_79'
JYNX = 'ME1.Jynx_57'
DWEBBLE, CRUSTLE = 'SV10.Dwebble_11', 'SV10.Crustle_12'
POLTCHAGEIST, SINISTCHA = 'SV06.Poltchageist_20', 'SV06.Sinistcha_22'
ARIANA = 'SV10.TeamRocketsAriana_171'
SNIVY, SERVINE, SERPERIOR = 'ME3.Snivy_4', 'ME3.Servine_5', 'ME3.Serperior_6'
ROSA = 'ME3.RosasEncouragement_84'
SCYTHER = 'SV05.Scyther_1'
HERACROSS = 'SV06.Heracross_8'
PINSIR = 'SV06.Pinsir_3'
DHELMISE = 'ME1.Dhelmise_18'
FACTORY = 'SV10.TeamRocketsFactory_173'
BANGLE = 'RSV10PT5.BraveBangle_80'
FUECOCO = 'SV08.Fuecoco_29'
KAKUNA = 'ME4.Kakuna_2'


def name(card):
    return def_for(card.archetype_id).display_name


@contextmanager
def as_ex(*pokemon):
    """Pretend the given Pokémon are Pokémon ex (the pool has none)."""
    ids = {p.archetype_id for p in pokemon}
    real = data_utils.subtypes_for

    def fake(archetype_id):
        base = list(real(archetype_id))
        return base + ['ex'] if archetype_id in ids else base
    with patch.object(data_utils, 'subtypes_for', fake):
        yield


class Chunk44(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None, hp=400):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.big(self.opp, hp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None, base=400):
        return base - (target or self.opp).get_attribute(AttrID.HP)

    # --- Team Rocket's Energy DRI 182 -------------------------------------------
    async def test_tr_energy_attaches_only_to_team_rockets_pokemon(self):
        t = self.table()
        murkrow = self.mine(t, TR_MURKROW)
        snorlax = self.mine(t, self.filler, zone='bench')
        energy = t.put(TR_ENERGY, P1, 'hand')
        targets = t.targets(energy, 'DefaultEnergyPlayAbility')
        self.assertIn(murkrow.entity_id, targets)
        self.assertNotIn(snorlax.entity_id, targets)

    async def test_tr_energy_pays_dark_colorless_cost(self):
        t = self.table()
        murkrow = self.mine(t, TR_MURKROW)
        energy = t.put(TR_ENERGY, P1, 'hand')
        self.assertIsNone(t.attack_offer(murkrow, 'Torment'))
        await t.play(energy, targets=[murkrow.entity_id])
        self.assertIn(energy, t.attached(murkrow))
        self.assertIsNotNone(t.attack_offer(murkrow, 'Torment'))

    async def test_tr_energy_pays_psychic_cost(self):
        t = self.table()
        drowzee = self.mine(t, TR_DROWZEE)
        energy = t.put(TR_ENERGY, P1, 'hand')
        await t.play(energy, targets=[drowzee.entity_id])
        self.assertIsNotNone(t.attack_offer(drowzee, 'Hypnotic Ray'))

    async def test_tr_energy_on_non_team_rocket_provides_nothing(self):
        t = self.table()
        snorlax = self.mine(t, self.filler)
        energy = t.attach(TR_ENERGY, snorlax)
        self.assertEqual(energy_provided_options(t.board, energy), [])

    # --- Jynx MEG 57: Psychic ---------------------------------------------------
    async def test_jynx_psychic_counts_opponent_energy(self):
        t = self.table()
        t.energy(self.opp, WATER, 2)
        jynx = self.mine(t, JYNX, PSY, 2)
        await t.attack(jynx, 'Psychic')
        self.assertEqual(self.dealt(), 90)

    async def test_jynx_psychic_ignores_own_and_bench_energy(self):
        t = self.table()
        bench = self.mine(t, self.filler, WATER, 2, zone='bench', pid=P2)
        jynx = self.mine(t, JYNX, PSY, 3)
        await t.attack(jynx, 'Psychic')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.damage(bench), 0)

    # --- Dwebble DRI 11: Ascension ----------------------------------------------
    async def test_dwebble_ascension_evolves_into_crustle(self):
        t = self.table()
        dwebble = self.mine(t, DWEBBLE, WATER, 1)
        t.deck(P1, [CRUSTLE])
        await t.attack(dwebble, 'Ascension')
        self.assertEqual(name(t.active(P1)), 'Crustle')
        self.assertEqual(self.dealt(), 0)

    async def test_dwebble_ascension_ignores_other_stage1(self):
        t = self.table()
        dwebble = self.mine(t, DWEBBLE, WATER, 1)
        t.deck(P1, [SINISTCHA])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.attack(dwebble, 'Ascension')
        self.assertEqual(name(t.active(P1)), 'Dwebble')
        self.assertNotIn('Sinistcha', [name(c) for c in seen])

    # --- Crustle DRI 12 -----------------------------------------------------------
    async def _opp_snivy_hits_crustle(self, ex):
        t = self.table()
        crustle = self.mine(t, CRUSTLE, hp=150)
        snivy = self.mine(t, SNIVY, GRASS, 1, pid=P2, zone='bench')
        # make Snivy P2's Active
        t.board.move_card(self.opp.entity_id,
                          t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(snivy.entity_id,
                          t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        t.next_turn()
        if ex:
            with as_ex(snivy):
                await t.attack(snivy, 'Reckless Charge', pid=P2)
        else:
            await t.attack(snivy, 'Reckless Charge', pid=P2)
        return t.damage(crustle)

    async def test_crustle_rock_inn_prevents_damage_from_ex(self):
        self.assertEqual(await self._opp_snivy_hits_crustle(ex=True), 0)

    async def test_crustle_rock_inn_does_not_stop_non_ex(self):
        self.assertEqual(await self._opp_snivy_hits_crustle(ex=False), 30)

    async def test_crustle_superb_scissors_ignores_defender_ability(self):
        t = self.table(KAKUNA)
        crustle = self.mine(t, CRUSTLE, GRASS, 3)
        await t.attack(crustle, 'Superb Scissors')
        self.assertEqual(self.dealt(), 120)

    async def test_kakuna_baseline_reduces_normal_attack(self):
        # control for the test above: Kakuna's -20 does work on other attacks
        t = self.table(KAKUNA)
        snivy = self.mine(t, SNIVY, GRASS, 1)
        await t.attack(snivy, 'Reckless Charge')
        self.assertEqual(self.dealt(), 10)

    # --- Poltchageist TWM 20: Storehouse Hideaway --------------------------------
    async def test_poltchageist_on_bench_ignores_attack_counters(self):
        t = self.table()
        polt = self.mine(t, POLTCHAGEIST, zone='bench', pid=P2)
        sin = self.mine(t, SINISTCHA, GRASS, 1)

        calls = []

        async def place(pid, src, pool, count, prompt=''):
            calls.append(count)
            return {polt.entity_id: count}
        with patch.object(t.session, 'prompt_damage_counter_placement', place, create=True):
            await t.attack(sin, 'Cursed Drop')
        self.assertEqual(calls, [4])
        self.assertIn(polt, t.zone(P2, 'bench'))
        self.assertEqual(t.damage(polt), 0)

    async def test_poltchageist_active_is_not_protected(self):
        t = self.table(POLTCHAGEIST, hp=30)
        snivy = self.mine(t, SNIVY, GRASS, 1)
        bench = self.mine(t, self.filler, zone='bench', pid=P2)
        await t.attack(snivy, 'Reckless Charge')
        self.assertNotIn(self.opp, t.zone(P2, 'active'))
        self.assertIn(bench, t.zone(P2, 'active') + t.zone(P2, 'bench'))

    # --- Sinistcha TWM 22 ---------------------------------------------------------
    async def test_sinistcha_cursed_drop_splits_four_counters(self):
        t = self.table()
        bench = self.mine(t, self.filler, zone='bench', pid=P2, hp=300)
        sin = self.mine(t, SINISTCHA, GRASS, 1)
        seen = {}

        async def place(pid, src, pool, count, prompt=''):
            seen['count'] = count
            seen['pool'] = {p.entity_id if hasattr(p, 'entity_id') else p for p in pool}
            return {self.opp.entity_id: 1, bench.entity_id: 3}
        with patch.object(t.session, 'prompt_damage_counter_placement', place, create=True):
            await t.attack(sin, 'Cursed Drop')
        self.assertEqual(seen['count'], 4)
        self.assertNotIn(sin.entity_id, seen['pool'])
        self.assertEqual(self.dealt(), 10)
        self.assertEqual(300 - t.hp(bench), 30)

    async def test_sinistcha_spill_the_tea_discards_up_to_three_grass(self):
        t = self.table()
        sin = self.mine(t, SINISTCHA, GRASS, 2, hp=70)
        water = t.energy(sin, WATER, 1)
        helper = self.mine(t, self.filler, GRASS, 2, zone='bench')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.attack(sin, 'Spill the Tea')
        self.assertEqual(self.dealt(), 210)
        self.assertNotIn(water, offered)
        self.assertIn(water, t.attached(sin))
        left = [c for c in t.attached(sin) + t.attached(helper) if c is not water]
        self.assertEqual(len(left), 1)

    async def test_sinistcha_spill_the_tea_zero_discarded_zero_damage(self):
        t = self.table()
        sin = self.mine(t, SINISTCHA, GRASS, 1)
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(sin, 'Spill the Tea')
        self.assertEqual(self.dealt(), 0)
        self.assertEqual(len(t.attached(sin)), 1)

    # --- Team Rocket's Ariana DRI 171 ---------------------------------------------
    def _ariana_board(self, all_tr, extra_hand=2):
        t = self.table()
        if all_tr:
            self.mine(t, TR_MURKROW)
            self.mine(t, TR_DROWZEE, zone='bench')
        else:
            self.mine(t, TR_MURKROW)
            self.mine(t, self.filler, zone='bench')
        self.clear_hand(t)
        ariana = t.put(ARIANA, P1, 'hand')
        for _ in range(extra_hand):
            t.put(self.item, P1, 'hand')
        return t, ariana

    async def test_ariana_draws_to_five_with_mixed_board(self):
        t, ariana = self._ariana_board(all_tr=False)
        await t.play(ariana)
        self.assertEqual(len(t.zone(P1, 'hand')), 5)

    async def test_ariana_draws_to_eight_when_all_team_rocket(self):
        t, ariana = self._ariana_board(all_tr=True)
        await t.play(ariana)
        self.assertEqual(len(t.zone(P1, 'hand')), 8)

    async def test_ariana_unplayable_at_five_unless_all_team_rocket(self):
        t, ariana = self._ariana_board(all_tr=False, extra_hand=5)
        self.assertFalse(t.can(ariana, 'UseTrainerCard'))
        t2, ariana2 = self._ariana_board(all_tr=True, extra_hand=5)
        self.assertTrue(t2.can(ariana2, 'UseTrainerCard'))

    # --- Snivy POR 4: Reckless Charge ---------------------------------------------
    async def test_snivy_reckless_charge_hurts_itself(self):
        t = self.table()
        snivy = self.mine(t, SNIVY, GRASS, 1)
        await t.attack(snivy, 'Reckless Charge')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.damage(snivy), 10)

    # --- Serperior POR 6 ----------------------------------------------------------
    async def test_serperior_regal_command_counts_only_your_pokemon(self):
        t = self.table()
        serp = self.mine(t, SERPERIOR, GRASS, 1)
        self.mine(t, self.filler, zone='bench')
        self.mine(t, self.filler, zone='bench')
        self.mine(t, self.filler, zone='bench', pid=P2)
        await t.attack(serp, 'Regal Command')
        self.assertEqual(self.dealt(), 60)

    async def test_serperior_solar_coiling_with_rosa_in_discard(self):
        t = self.table()
        serp = self.mine(t, SERPERIOR, GRASS, 3)
        t.put(ROSA, P1, 'discard')
        await t.attack(serp, 'Solar Coiling')
        self.assertEqual(self.dealt(), 250)

    async def test_serperior_solar_coiling_without_rosa(self):
        t = self.table()
        serp = self.mine(t, SERPERIOR, GRASS, 3)
        t.put(ROSA, P2, 'discard')      # opponent's discard does not count
        t.put(ROSA, P1, 'hand')
        await t.attack(serp, 'Solar Coiling')
        self.assertEqual(self.dealt(), 100)

    # --- Scyther TEF 1: Slashing Strike -------------------------------------------
    async def test_scyther_slashing_strike_locked_next_turn_only(self):
        t = self.table()
        scyther = self.mine(t, SCYTHER, GRASS, 2)
        await t.attack(scyther, 'Slashing Strike')
        self.assertEqual(self.dealt(), 60)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(scyther, 'Slashing Strike'))
        self.assertIsNotNone(t.attack_offer(scyther, 'Cut Up'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(scyther, 'Slashing Strike'))

    # --- Heracross TWM 8: Body Slam -----------------------------------------------
    async def test_heracross_body_slam_heads_paralyzes(self):
        t = self.table()
        hera = self.mine(t, HERACROSS, GRASS, 3)
        t.heads = True
        await t.attack(hera, 'Body Slam')
        self.assertEqual(self.dealt(), 60)
        self.assertIn(PARALYZED, t.conditions(self.opp))

    async def test_heracross_body_slam_tails_no_paralysis(self):
        t = self.table()
        hera = self.mine(t, HERACROSS, GRASS, 3)
        t.heads = False
        await t.attack(hera, 'Body Slam')
        self.assertEqual(self.dealt(), 60)
        self.assertNotIn(PARALYZED, t.conditions(self.opp))

    # --- Pinsir TWM 3: Slow Crunch ------------------------------------------------
    async def test_pinsir_slow_crunch_kos_at_end_of_opponents_turn(self):
        t = self.table()
        self.mine(t, self.filler, zone='bench', pid=P2)
        pinsir = self.mine(t, PINSIR, GRASS, 2)
        await t.attack(pinsir, 'Slow Crunch')
        self.assertEqual(t.attached(pinsir), [])
        self.assertEqual(self.dealt(), 0)
        await t.checkup()                       # end of my turn: not yet
        self.assertIn(self.opp, t.zone(P2, 'active'))
        t.next_turn()
        await t.checkup()                       # end of opponent's next turn
        self.assertNotIn(self.opp, t.zone(P2, 'active') + t.zone(P2, 'bench'))

    async def test_pinsir_slow_crunch_dropped_if_defender_retreats(self):
        t = self.table()
        other = self.mine(t, self.filler, zone='bench', pid=P2)
        pinsir = self.mine(t, PINSIR, GRASS, 2)
        await t.attack(pinsir, 'Slow Crunch')
        await t.checkup()
        t.next_turn()
        t.board.move_card(self.opp.entity_id,
                          t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(other.entity_id,
                          t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        await t.checkup()
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIn(other, t.zone(P2, 'active'))

    # --- Dhelmise MEG 18: Earthen Power -------------------------------------------
    async def test_dhelmise_bonus_with_your_stadium(self):
        t = self.table()
        dhel = self.mine(t, DHELMISE, GRASS, 2)
        t.stadium(FACTORY, P1)
        await t.attack(dhel, 'Earthen Power')
        self.assertEqual(self.dealt(), 80)

    async def test_dhelmise_no_bonus_with_opponents_stadium(self):
        t = self.table()
        dhel = self.mine(t, DHELMISE, GRASS, 2)
        t.stadium(FACTORY, P2)
        await t.attack(dhel, 'Earthen Power')
        self.assertEqual(self.dealt(), 30)

    async def test_dhelmise_no_bonus_without_stadium(self):
        t = self.table()
        dhel = self.mine(t, DHELMISE, GRASS, 2)
        await t.attack(dhel, 'Earthen Power')
        self.assertEqual(self.dealt(), 30)

    # --- Brave Bangle WHT 80 ------------------------------------------------------
    async def _bangle_attack(self, opp_ex, holder_ex=False):
        t = self.table()
        snivy = self.mine(t, SNIVY, GRASS, 1)
        await t.play(t.put(BANGLE, P1, 'hand'), targets=[snivy.entity_id])
        exs = ([self.opp] if opp_ex else []) + ([snivy] if holder_ex else [])
        with as_ex(*exs):
            await t.attack(snivy, 'Reckless Charge')
        return self.dealt(), t.damage(snivy)

    async def test_brave_bangle_plus_30_against_ex(self):
        dealt, self_damage = await self._bangle_attack(opp_ex=True)
        self.assertEqual(dealt, 60)
        self.assertEqual(self_damage, 10)    # self-damage isn't boosted

    async def test_brave_bangle_no_bonus_against_non_ex(self):
        dealt, _ = await self._bangle_attack(opp_ex=False)
        self.assertEqual(dealt, 30)

    async def test_brave_bangle_no_bonus_for_rule_box_holder(self):
        dealt, _ = await self._bangle_attack(opp_ex=True, holder_ex=True)
        self.assertEqual(dealt, 30)

    # --- Fuecoco SSP 29: Heat Burn ------------------------------------------------
    async def test_fuecoco_heat_burn_burns(self):
        t = self.table()
        fue = self.mine(t, FUECOCO, FIRE, 2)
        await t.attack(fue, 'Heat Burn')
        self.assertEqual(self.dealt(), 20)
        self.assertIn(BURNED, t.conditions(self.opp))


if __name__ == '__main__':
    unittest.main()
