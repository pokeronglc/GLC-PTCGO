"""Bug hunt round 2, deck 11 (Fairy): Tools, Stadiums, Special Energy and
Robo Substitute."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, CONFUSED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

Y, D, W, P = PokemonTypes.FAIRY, PokemonTypes.DARKNESS, PokemonTypes.WATER, PokemonTypes.PSYCHIC
HOOD, SCARF = 'SM10.StealthyHood_186', 'BW6.RescueScarf_115'
CAGE, SWELL, ARTAZON = 'ME2.BattleCage_85', 'SM12.ChaoticSwell_187', 'SV2.Artazon_171'
WONDER, ROBO = 'XY5.WonderEnergy_144', 'XY4.RoboSubstituteTeamFlareGear_102'
SLURPUFF, KLEFKI = 'XY4.Slurpuff_69', 'SM6.Klefki_89'
WEEZING = 'SWSH2.GalarianWeezing_113'   # Neutralizing Gas (Active): opponent has no Abilities
SABLEYE = 'SV2.Sableye_136'             # Night Eyes (Asleep), Unseen Claw 20 (+70 if conditioned)
HAUNTER = 'SM10.Haunter_69'             # Sinister Fog: Poison + 1 counter on each opp Benched
CROBAT = 'SWSH12.Crobat_105'            # Critical Bite: 30 damage to any 1 Pokémon


class Deck11Attachments2(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        return mon

    # --- Stealthy Hood -----------------------------------------------------
    async def test_stealthy_hood_shields_holder_from_ability_lock(self):
        t = Table(self)
        t.put(WEEZING, P2, 'active')
        slurpuff = t.put(SLURPUFF, P1, 'active')
        self.assertIsNone(t.ability_offer(slurpuff, 'Tasting'))      # locked without Hood
        await t.play(t.put(HOOD, P1, 'hand'), targets=[slurpuff.entity_id])
        self.assertIn(HOOD.split('.')[1].split('_')[0],
                      [def_for(c.archetype_id).display_name.replace(' ', '') for c in slurpuff.children])
        self.assertIsNotNone(t.ability_offer(slurpuff, 'Tasting'))

    async def test_stealthy_hood_does_not_stop_attack_effects(self):
        t = Table(self)
        opp = self.neutral(t.put(KLEFKI, P2, 'active'), 400)
        t.energy(opp, W)
        me = self.neutral(t.put(self.filler, P1, 'active'), 400)
        await t.play(t.put(HOOD, P1, 'hand'), targets=[me.entity_id])
        t.next_turn()
        await t.attack(opp, 'Metal Sound', pid=P2)
        self.assertIn(CONFUSED, t.conditions(me))

    # --- Rescue Scarf ------------------------------------------------------
    async def test_rescue_scarf_returns_pokemon_ko_by_attack(self):
        t = Table(self)
        opp = t.put(SABLEYE, P2, 'active')
        t.energy(opp, D)
        victim = self.neutral(t.put(KLEFKI, P1, 'active', hp=10))
        energy = t.energy(victim, Y)
        await t.play(t.put(SCARF, P1, 'hand'), targets=[victim.entity_id])
        scarf = next(c for c in victim.children if def_for(c.archetype_id).display_name == 'Rescue Scarf')
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertIn(victim, t.zone(P1, 'hand'))
        self.assertIn(scarf, t.zone(P1, 'discard'))
        self.assertIn(energy, t.zone(P1, 'discard'))

    # Was a bug (fixed Oct 10): rescue_scarf_trigger (bw_era.py) ignores ctx.ko_from_attack, so a Poison KO also returns the Pokémon
    async def test_rescue_scarf_not_for_poison_knockout(self):
        t = Table(self)
        t.put(self.filler, P2, 'active')
        victim = self.neutral(t.put(KLEFKI, P1, 'active', hp=10))
        await t.play(t.put(SCARF, P1, 'hand'), targets=[victim.entity_id])
        t.put(self.filler, P1, 'bench')
        victim.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.checkup()                          # Poison KO between turns
        self.assertNotIn(victim, t.zone(P1, 'active'))
        self.assertNotIn(victim, t.zone(P1, 'hand'))
        self.assertIn(victim, t.zone(P1, 'discard'))

    # --- Battle Cage --------------------------------------------------------
    async def test_battle_cage_blocks_counters_on_bench_from_attacks(self):
        for cage in (False, True):
            t = Table(self)
            opp = self.neutral(t.put(self.filler, P2, 'active'), 400)
            bench = t.put(self.filler, P2, 'bench')
            haunter = t.put(HAUNTER, P1, 'active')
            t.energy(haunter, P)
            if cage:
                t.stadium(CAGE, P2)
            before = t.hp(bench)
            await t.attack(haunter, 'Sinister Fog')
            with self.subTest(cage=cage):
                self.assertEqual(before - t.hp(bench), 0 if cage else 10)
                self.assertIn(POISONED, t.conditions(opp))       # Active still affected

    async def test_battle_cage_does_not_stop_attack_damage_to_bench(self):
        t = Table(self)
        self.neutral(t.put(self.filler, P2, 'active'), 400)
        bench = self.neutral(t.put(self.filler, P2, 'bench'))
        crobat = t.put(CROBAT, P1, 'active')
        t.energy(crobat, D, 3)
        t.stadium(CAGE, P1)
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        before = t.hp(bench)
        await t.attack(crobat, 'Critical Bite')
        self.assertEqual(before - t.hp(bench), 30)

    # --- Chaotic Swell -------------------------------------------------------
    async def test_chaotic_swell_discards_both_stadiums(self):
        for player in (P1, P2):
            t = Table(self)
            t.put(self.filler, P1, 'active'); t.put(self.filler, P2, 'active')
            swell = t.stadium(SWELL, P1)
            if player == P2:
                t.next_turn()
            new = t.put(ARTAZON, player, 'hand')
            await t.play(new, pid=player)
            stadium_area = t.board.find_global_area('activeStadium')
            with self.subTest(player=player):
                self.assertEqual(list(stadium_area.children), [])
                self.assertIn(swell, t.zone(P1, 'discard'))
                self.assertIn(new, t.zone(player, 'discard'))

    async def test_without_chaotic_swell_stadium_replaces_normally(self):
        t = Table(self)
        t.put(self.filler, P1, 'active'); t.put(self.filler, P2, 'active')
        cage = t.stadium(CAGE, P2)
        new = t.put(ARTAZON, P1, 'hand')
        await t.play(new)
        self.assertEqual(list(t.board.find_global_area('activeStadium').children), [new])
        self.assertIn(cage, t.zone(P2, 'discard'))

    # --- Wonder Energy -------------------------------------------------------
    async def test_wonder_energy_only_attaches_to_fairy(self):
        t = Table(self)
        t.put(self.filler, P2, 'active')
        klefki = t.put(KLEFKI, P1, 'active')
        plain = t.put(self.filler, P1, 'bench')
        card = t.put(WONDER, P1, 'hand')
        targets = t.targets(card, 'DefaultEnergyPlayAbility')
        self.assertIn(klefki.entity_id, targets)
        self.assertNotIn(plain.entity_id, targets)

    async def test_wonder_energy_blocks_effects_not_damage(self):
        t = Table(self)
        opp = t.put(SABLEYE, P2, 'active')
        t.energy(opp, D)
        klefki = self.neutral(t.put(KLEFKI, P1, 'active'), 400)
        await t.play(t.put(WONDER, P1, 'hand'), targets=[klefki.entity_id])
        self.assertIsNotNone(t.attack_offer(klefki, 'Metal Sound'))   # provides energy
        t.next_turn()
        await t.attack(opp, 'Night Eyes', pid=P2)
        self.assertNotIn(ASLEEP, t.conditions(klefki))
        t.next_turn(); t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertEqual(400 - t.hp(klefki), 20)

    # --- Robo Substitute (Team Flare Gear) -----------------------------------
    async def test_robo_substitute_benches_cannot_retreat(self):
        t = Table(self)
        t.put(self.filler, P2, 'active')
        t.put(self.filler, P1, 'active')
        robo = t.put(ROBO, P1, 'hand')
        await t.play(robo)
        self.assertIn(robo, t.zone(P1, 'bench'))
        self.assertEqual(t.hp(robo), 30)
        # put it Active with Energy and a Bench: still no Retreat
        t2 = Table(self)
        t2.put(self.filler, P2, 'active')
        robo2 = t2.put(ROBO, P1, 'active')
        t2.energy(robo2, W, 2)
        t2.put(self.filler, P1, 'bench')
        self.assertFalse(t2.can(robo2, 'BaseRetreat'))

    async def test_robo_substitute_ko_gives_no_prize(self):
        t = Table(self)
        opp = t.put(SABLEYE, P2, 'active')
        t.energy(opp, D)
        robo = t.put(ROBO, P1, 'active', hp=10)       # Unseen Claw does 20
        robo.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertIn(robo, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 6)
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    async def test_normal_knockout_gives_a_prize(self):
        t = Table(self)
        opp = t.put(SABLEYE, P2, 'active')
        t.energy(opp, D)
        victim = self.neutral(t.put(KLEFKI, P1, 'active', hp=10))
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertIn(victim, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 5)

    async def test_robo_substitute_discard_rule(self):
        t = Table(self)
        t.put(self.filler, P2, 'active')
        t.put(self.filler, P1, 'active')
        robo = t.put(ROBO, P1, 'bench')
        await t.use(robo, 'Discard Robo Substitute')
        self.assertIn(robo, t.zone(P1, 'discard'))


if __name__ == '__main__':
    unittest.main()
