"""Bug hunt, deck 5 (Dragon): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, L, F, R, P, D, C = (PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.FIGHTING,
                       PokemonTypes.FIRE, PokemonTypes.PSYCHIC, PokemonTypes.DARKNESS,
                       PokemonTypes.COLORLESS)
DREEPY, DRAKLOAK = 'SV06.Dreepy_128', 'SV06.Drakloak_129'
GIBLE, GABITE, GARCHOMP = 'SM5.Gible_96', 'BW6.Gabite_89', 'SWSH9.Garchomp_109'
DRATINI, DRAGONAIR, DRAGONITE = 'SM9.Dratini_117', 'ME2PT5.Dragonair_151', 'SV035.Dragonite_149'
DRUDDIGON, BOLT, RAYQUAZA = 'SWSH9.Druddigon_113', 'SV07.RagingBolt_111', 'ME2PT5.Rayquaza_153'
TATSUGIRI, KYUREM = 'SV06.Tatsugiri_131', 'SV065.Kyurem_47'
TINGLU, CROBAT = 'SV06.TingLu_110', 'SWSH12.Crobat_105'
COLRESS, BOSS, SWITCH = 'BW8.Colress_118', 'SWSH2.BosssOrders_154', 'BW1.Switch_104'
NEST = 'SV1.NestBall_181'


class Deck5Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    def neutral(self, p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        return p

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def replace_opp_active(self, t, spec):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = t.put(spec, P2, 'active')
        self.neutral(self.opp)
        return self.opp

    def evolved(self, t, pid, name):
        return next(p for p in t.board.pokemon_in_play(pid) if self.name(p) == name)

    # --- Drakloak: Recon Directive -------------------------------------------
    async def test_recon_directive_one_to_hand_other_to_bottom_once(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        drak = t.put(DRAKLOAK, P1, 'bench')
        top = t.deck(P1, [BOSS, NEST])     # NEST ends on top
        t.picks = lambda cards, count, prompt, display: [c for c in cards if self.name(c) == "Boss's Orders"]
        await t.use(drak, 'Recon Directive')
        self.assertEqual(t.names(t.zone(P1, 'hand')), ["Boss's Orders"])
        deck = t.zone(P1, 'deck')
        nest = next(c for c in top if self.name(c) == 'Nest Ball')
        self.assertIs(deck[0], nest)            # index 0 is the bottom (see Table.deck)
        self.assertIsNone(t.ability_offer(drak, 'Recon Directive'))

    # --- Gible: Ascension -------------------------------------------------------
    async def test_gible_ascension(self):
        t = self.table()
        gible = t.put(GIBLE, P1, 'active')
        t.energy(gible, F)
        t.deck(P1, [GARCHOMP, GABITE])
        await t.attack(gible, 'Ascension')
        self.assertEqual(self.name(t.active(P1)), 'Gabite')
        t = self.table()
        gible = t.put(GIBLE, P1, 'active')
        t.energy(gible, F)
        t.deck(P1, [GARCHOMP])                  # a Stage 2 doesn't evolve from Gible
        await t.attack(gible, 'Ascension')
        self.assertIs(t.active(P1), gible)

    # --- Gabite: Dragon Call ------------------------------------------------------
    async def test_dragon_call_dragon_pokemon_only_once(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        gabite = t.put(GABITE, P1, 'bench')
        t.deck(P1, [TINGLU, self.filler, DRATINI])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:count])[1]
        await t.use(gabite, 'Dragon Call')
        self.assertEqual(seen['n'], ['Dratini'])
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Dratini'])
        self.assertIsNone(t.ability_offer(gabite, 'Dragon Call'))

    # --- Garchomp ---------------------------------------------------------------------
    async def _sonic_slip(self, accept):
        t = self.table()
        gabite = t.put(GABITE, P1, 'active')
        t.put(self.filler, P1, 'bench')
        attacker = self.replace_opp_active(t, TINGLU)
        t.energy(attacker, F, 3)
        t.yes = accept
        await t.play(t.put(GARCHOMP, P1, 'hand'), targets=[gabite.entity_id])
        chomp = t.active(P1)
        self.assertEqual(self.name(chomp), 'Garchomp')
        self.neutral(chomp, hp=None)
        t.next_turn()
        before = t.hp(chomp)
        await t.attack(attacker, 'Hammer In', pid=P2)
        return before - t.hp(chomp)

    async def test_sonic_slip_prevents_next_turn(self):
        self.assertEqual(await self._sonic_slip(True), 0)

    async def test_sonic_slip_declined(self):
        self.assertEqual(await self._sonic_slip(False), 110)

    async def test_dragonblade_mills_own_two(self):
        t = self.table()
        chomp = t.put(GARCHOMP, P1, 'active')
        t.energy(chomp, W); t.energy(chomp, F)
        deck = len(t.zone(P1, 'deck'))
        opp_deck = len(t.zone(P2, 'deck'))
        await t.attack(chomp, 'Dragonblade')
        self.assertEqual(400 - t.hp(self.opp), 160)
        self.assertEqual(len(t.zone(P1, 'deck')), deck - 2)
        self.assertEqual(len(t.zone(P2, 'deck')), opp_deck)

    # --- Dratini: Defensive Scales -------------------------------------------------------
    async def test_defensive_scales_blocks_effects_not_damage(self):
        # (Galarian Weezing would lock the Ability; Crobat's Venomous Fang is
        # 50 damage + Poisoned.)
        for spec, protected in ((DRATINI, True), (self.filler, False)):
            t = self.table()
            mine = t.put(spec, P1, 'active', hp=300)
            self.neutral(mine, hp=None)
            t.put(self.filler, P1, 'bench')
            crobat = self.replace_opp_active(t, CROBAT)
            t.energy(crobat, D)
            t.next_turn()
            before = t.hp(mine)
            await t.attack(crobat, 'Venomous Fang', pid=P2)
            with self.subTest(card=spec):
                self.assertEqual(POISONED in t.conditions(mine), not protected)
                self.assertEqual(before - t.hp(mine), 50)

    # --- Dragonair: Evolutionary Guidance ----------------------------------------------------
    async def test_evolutionary_guidance_needs_energy_evolution_only(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        air = t.put(DRAGONAIR, P1, 'bench')
        t.deck(P1, [DRATINI, DRAGONITE, GABITE])
        self.assertIsNone(t.ability_offer(air, 'Evolutionary Guidance'))
        t.energy(air, W)
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:count])[1]
        await t.use(air, 'Evolutionary Guidance')
        self.assertEqual(seen['n'], ['Dragonite', 'Gabite'])
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertIsNone(t.ability_offer(air, 'Evolutionary Guidance'))

    # --- Dragonite -------------------------------------------------------------------------------
    async def test_jet_cruise_your_pokemon_only(self):
        t = self.table()
        heavy = t.put(TINGLU, P1, 'active')
        self.assertGreater(t.retreat(heavy), 0)
        opp_base = t.retreat(self.opp)
        t.put(DRAGONITE, P1, 'bench')
        self.assertEqual(t.retreat(heavy), 0)
        self.assertEqual(t.retreat(self.opp), opp_base)

    async def test_dragon_pulse_discards_own_top_two(self):
        t = self.table()
        nite = t.put(DRAGONITE, P1, 'active')
        t.energy(nite, W); t.energy(nite, L)
        deck = len(t.zone(P1, 'deck'))
        await t.attack(nite, 'Dragon Pulse')
        self.assertEqual(400 - t.hp(self.opp), 180)
        self.assertEqual(len(t.zone(P1, 'deck')), deck - 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 2)

    # --- Druddigon: Revenge ------------------------------------------------------------------------
    async def _revenge(self, ko):
        t = self.table()
        victim = t.put(self.filler, P1, 'active', hp=10 if ko else 300)
        self.neutral(victim, hp=None)
        drudd = t.put(DRUDDIGON, P1, 'bench')
        t.energy(drudd, R); t.energy(drudd, W)
        attacker = self.replace_opp_active(t, TINGLU)
        t.energy(attacker, F, 3)
        t.next_turn()
        await t.attack(attacker, 'Hammer In', pid=P2)
        t.next_turn()
        if not ko:
            await t.play(t.put(SWITCH, P1, 'hand'))
        self.assertIs(t.active(P1), drudd)
        before = t.hp(attacker)
        await t.attack(drudd, 'Revenge')
        return before - t.hp(attacker)

    async def test_revenge_after_ko(self):
        self.assertEqual(await self._revenge(True), 160)

    async def test_revenge_without_ko(self):
        self.assertEqual(await self._revenge(False), 40)

    # --- Raging Bolt: Thunderburst Storm -------------------------------------------------------------
    async def test_thunderburst_storm_30_per_energy_any_target(self):
        t = self.table()
        bolt = t.put(BOLT, P1, 'active')
        t.energy(bolt, L); t.energy(bolt, F); t.energy(bolt, W)
        bench = self.neutral(t.put(self.filler, P2, 'bench'), hp=None)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [PokemonTypes.DRAGON.value])
        t.picks = lambda cards, count, prompt, display: [bench]
        await t.attack(bolt, 'Thunderburst Storm')
        self.assertEqual(t.damage(bench), 90)          # no Weakness on the Bench
        self.assertEqual(t.hp(self.opp), 400)

    # --- Rayquaza: Breakthrough Assault ---------------------------------------------------------------
    async def test_breakthrough_assault_after_moving_up(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        ray = t.put(RAYQUAZA, P1, 'bench')
        t.energy(ray, L); t.energy(ray, W)
        t.pokemon = lambda c, p: ray if ray in c else c[0]
        await t.play(t.put(SWITCH, P1, 'hand'))
        self.assertIs(t.active(P1), ray)
        await t.attack(ray, 'Breakthrough Assault')
        self.assertEqual(400 - t.hp(self.opp), 110)

    async def test_breakthrough_assault_already_active(self):
        t = self.table()
        ray = t.put(RAYQUAZA, P1, 'active')
        t.energy(ray, L); t.energy(ray, W)
        await t.attack(ray, 'Breakthrough Assault')
        self.assertEqual(400 - t.hp(self.opp), 20)

    # --- Tatsugiri: Attract Customers -------------------------------------------------------------------
    async def test_attract_customers_active_only_supporter_from_top_six(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        bench_tatsu = t.put(TATSUGIRI, P1, 'bench')
        self.assertIsNone(t.ability_offer(bench_tatsu, 'Attract Customers'))
        t = self.table()
        tatsu = t.put(TATSUGIRI, P1, 'active')
        t.deck(P1, [BOSS], top=False)                     # buried: not in the top 6
        t.deck(P1, [COLRESS, NEST])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', (t.names(cards), len(display or []))), cards[:count])[1]
        await t.use(tatsu, 'Attract Customers')
        names, shown = seen['n']
        self.assertEqual(names, ['Colress'])
        self.assertEqual(shown, 6)
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Colress'])
        self.assertIsNone(t.ability_offer(tatsu, 'Attract Customers'))

    # --- Kyurem: Plasma Bane / Trifrost -------------------------------------------------------------------
    async def test_plasma_bane_colorless_cost_with_colress(self):
        t = self.table()
        ky = t.put(KYUREM, P1, 'active')
        t.energy(ky, W)
        self.assertIsNone(t.attack_offer(ky, 'Trifrost'))
        t.put(COLRESS, P1, 'discard')                       # MY Colress doesn't count
        self.assertIsNone(t.attack_offer(ky, 'Trifrost'))
        t.put(COLRESS, P2, 'discard')
        self.assertIsNotNone(t.attack_offer(ky, 'Trifrost'))

    async def test_trifrost_discards_all_energy_110_to_three(self):
        t = self.table()
        ky = t.put(KYUREM, P1, 'active')
        t.energy(ky, W, 3); t.energy(ky, PokemonTypes.METAL, 2)
        b1 = self.neutral(t.put(self.filler, P2, 'bench'), hp=None)
        b2 = self.neutral(t.put(self.filler, P2, 'bench'), hp=None)
        b3 = self.neutral(t.put(self.filler, P2, 'bench'), hp=None)
        await t.attack(ky, 'Trifrost')
        self.assertEqual(len(t.board.attached_energies(ky)), 0)
        hit = [400 - t.hp(self.opp)] + [t.damage(b) for b in (b1, b2, b3)]
        self.assertEqual(sorted(hit), [0, 110, 110, 110])


if __name__ == "__main__":
    unittest.main()
