"""Player reports, Oct 13.

* Devolution Ray / Devolution Spray did nothing on a Stage 2 that was
  evolved with Rare Candy (no Stage 1 underneath) -- now devolves to the Basic.
  Same for Devolution Spray Z and Technical Machine: Devolution.
* Togekiss XY6 (Delta Evolution) may evolve the Togetic that Devolution Spray
  just devolved; ordinary evolutions stay locked that turn.
* Frozen City / Buddy Pulse also see Energy attached from hand by an Ability
  (Xatu's Clairvoyant Sense), not attachments from the discard pile.
* Delinquent: an opponent with 3 or fewer cards discards them all with no
  prompt (there is no choice to make).
* Green's Exploration is playable when your Pokémon's Abilities are switched
  off (Hex Maniac).
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

PSY, WATER = PokemonTypes.PSYCHIC, PokemonTypes.WATER
AERODACTYL = 'SV035.Aerodactyl_142'
RHYHORN, RHYDON, RHYPERIOR = 'SWSH1.Rhyhorn_96', 'SWSH1.Rhydon_98', 'SWSH1.Rhyperior_99'
SPRAYS = ('BW6.DevolutionSpray_113', 'XY10.DevolutionSpray_95', 'XY12.DevolutionSpray_76')
TOGEPI, TOGETIC = 'XY6.Togepi_43', 'XY6.Togetic_44'
TOGEKISS_DELTA, TOGEKISS_PLAIN = 'XY6.Togekiss_46', 'XY6.Togekiss_45'
FROZEN_CITY, XATU = 'BW9.FrozenCity_100', 'SV4.Xatu_72'
MINUN, PLUSLE = 'SV4.Minun_61', 'SV4.Plusle_60'
GREENS, RAIHAN = 'SM10.GreensExploration_175', 'SWSH7.Raihan_152'


class PlayerReportsOct13(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_active=True):
        t = Table(self)
        for pid in (P1, P2):
            t.put(self.filler, pid, 'bench').set_attribute(AttrID.HP, 400)
        if opp_active:
            t.put(self.filler, P2, 'active').set_attribute(AttrID.HP, 400)
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    async def evolve(self, t, pid, base, spec):
        card = t.put(spec, pid, 'hand')
        await t._run(lambda: t.session.perform_evolution(pid, card, base))
        return card

    # --- Rare Candy stacks -------------------------------------------------
    async def candy_rhyperior(self, t, pid):
        base = t.put(RHYHORN, pid, 'active')
        top = await self.evolve(t, pid, base, RHYPERIOR)      # Rare Candy shape
        top.set_attribute(AttrID.HP, 400)
        return top

    async def test_devolution_ray_on_rare_candy_stage2(self):
        t = self.table(opp_active=False)
        aero = t.put(AERODACTYL, P1, 'active')
        t.energy(aero, WATER, 2)
        await self.candy_rhyperior(t, P2)
        await t.attack(aero, 'Devolution Ray')
        self.assertEqual(self.name(t.active(P2)), 'Rhyhorn')
        self.assertEqual(t.names(t.zone(P2, 'hand')), ['Rhyperior'])

    async def test_devolution_ray_normal_stage1_still_works(self):
        t = self.table(opp_active=False)
        aero = t.put(AERODACTYL, P1, 'active')
        t.energy(aero, WATER, 2)
        base = t.put(RHYHORN, P2, 'active')
        (await self.evolve(t, P2, base, RHYDON)).set_attribute(AttrID.HP, 400)
        await t.attack(aero, 'Devolution Ray')
        self.assertEqual(self.name(t.active(P2)), 'Rhyhorn')
        self.assertEqual(t.names(t.zone(P2, 'hand')), ['Rhydon'])

    async def test_devolution_spray_on_rare_candy_stage2(self):
        for spray in SPRAYS:
            with self.subTest(spray=spray):
                t = self.table()
                await self.candy_rhyperior(t, P1)
                t.next_turn(); t.next_turn()
                card = t.put(spray, P1, 'hand')
                self.assertTrue(t.can(card, 'UseTrainerCard'))
                await t.play(card)
                self.assertEqual(self.name(t.active(P1)), 'Rhyhorn')
                self.assertIn('Rhyperior', t.names(t.zone(P1, 'hand')))

    # --- Delta Evolution after Devolution Spray ----------------------------
    async def sprayed_togekiss(self, t, togekiss):
        base = t.put(TOGEPI, P1, 'active')
        mid = await self.evolve(t, P1, base, TOGETIC)
        await self.evolve(t, P1, mid, togekiss)
        t.next_turn(); t.next_turn()
        await t.play(t.put('XY10.DevolutionSpray_95', P1, 'hand'))
        self.assertEqual(self.name(t.active(P1)), 'Togetic')
        return next(c for c in t.zone(P1, 'hand') if self.name(c) == 'Togekiss')

    async def test_delta_evolution_togekiss_reevolves_after_spray(self):
        t = self.table()
        togekiss = await self.sprayed_togekiss(t, TOGEKISS_DELTA)
        self.assertTrue(t.can(togekiss, 'EvolvePokemonPlayAbility'))
        await t.play(togekiss, targets=[t.active(P1).entity_id])
        self.assertEqual(self.name(t.active(P1)), 'Togekiss')

    async def test_plain_togekiss_stays_locked_after_spray(self):
        t = self.table()
        togekiss = await self.sprayed_togekiss(t, TOGEKISS_PLAIN)
        self.assertFalse(t.can(togekiss, 'EvolvePokemonPlayAbility'))
        delta = t.put(TOGEKISS_DELTA, P1, 'hand')
        self.assertTrue(t.can(delta, 'EvolvePokemonPlayAbility'))

    # --- Attaching from hand with an Ability -------------------------------
    async def xatu_attach(self, t):
        xatu = t.put(XATU, P1, 'active')
        bench = t.zone(P1, 'bench')[0]
        before = t.hp(bench)
        t.put(t.basic_energy(PSY), P1, 'hand')
        await t.use(xatu, 'Clairvoyant Sense')
        self.assertEqual(len(bench.children), 1)
        return before - t.hp(bench)

    async def test_frozen_city_sees_ability_attach_from_hand(self):
        t = self.table()
        t.stadium(FROZEN_CITY, P2)
        self.assertEqual(await self.xatu_attach(t), 20)

    async def test_buddy_pulse_sees_ability_attach_from_hand(self):
        for plusle in (True, False):
            with self.subTest(plusle=plusle):
                t = self.table(opp_active=False)
                t.put(MINUN, P2, 'active')
                if plusle:
                    t.put(PLUSLE, P2, 'bench')
                self.assertEqual(await self.xatu_attach(t), 20 if plusle else 0)

    async def test_frozen_city_ignores_attach_from_discard(self):
        t = self.table()
        t.stadium(FROZEN_CITY, P2)
        mon = t.put(self.filler, P1, 'active')
        mon.set_attribute(AttrID.HP, 300)
        before = t.hp(mon)
        t.put(t.basic_energy(WATER), P1, 'discard')
        raihan = t.put(RAIHAN, P1, 'hand')
        t.next_turn()
        t.state.kos_suffered = {P1: [{'archetype_id': 'x', 'subtypes': [], 'pokemon_types': []}]}
        t.next_turn()
        t.pokemon = lambda candidates, prompt: mon
        await t.play(raihan)
        self.assertEqual(len(mon.children), 1)
        self.assertEqual(t.hp(mon), before)

    # --- Green's Exploration under an Ability lock -------------------------
    async def test_greens_exploration_under_hex_maniac(self):
        t = self.table()
        t.put(XATU, P1, 'active')
        greens = t.put(GREENS, P1, 'hand')
        self.assertFalse(t.can(greens, 'UseTrainerCard'))
        t.state.abilities_disabled_through_turn = t.state.turn_number + 1
        self.assertTrue(t.can(greens, 'UseTrainerCard'))
        t.deck(P1, ['BW6.DevolutionSpray_113'])
        t.picks = lambda cards, count, prompt, shown: [
            c for c in cards if self.name(c) == 'Devolution Spray'][:count]
        await t.play(greens)
        self.assertIn('Devolution Spray', t.names(t.zone(P1, 'hand')))

    # --- Delinquent with a small opposing hand ------------------------------
    async def test_delinquent_auto_discards_small_hand(self):
        for size, prompted in ((0, False), (2, False), (3, False), (5, True)):
            with self.subTest(size=size):
                t = self.table()
                t.put(self.filler, P1, 'active')
                t.stadium(FROZEN_CITY, P2)
                for _ in range(size):
                    t.put(self.item, P2, 'hand')
                card = t.put('XY9.Delinquent_98', P1, 'hand')
                await t.play(card)
                self.assertEqual(len(t.zone(P2, 'hand')), max(0, size - 3))
                self.assertEqual('Choose cards to discard' in t.prompts, prompted)

    async def test_devolution_spray_z_on_rare_candy_stage2(self):
        t = self.table()
        await self.candy_rhyperior(t, P1)
        t.next_turn(); t.next_turn()
        card = t.put('SM10.DevolutionSprayZ_166', P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertEqual(self.name(t.active(P1)), 'Rhyhorn')
        self.assertIn('Rhyperior', t.names(t.zone(P1, 'deck')))

    async def test_tm_devolution_on_rare_candy_stage2s(self):
        t = self.table(opp_active=False)
        me = t.put(self.filler, P1, 'active')
        t.energy(me, WATER, 1)
        await t.play(t.put('SV4.TechnicalMachineDevolution_177', P1, 'hand'),
                     targets=[me.entity_id])
        await self.candy_rhyperior(t, P2)
        bench = t.put(RHYHORN, P2, 'bench')
        await self.evolve(t, P2, bench, RHYPERIOR)
        await t.attack(me, 'Devolution')
        self.assertEqual(sorted(self.name(p) for p in t.board.pokemon_in_play(P2)),
                         ['Rhyhorn', 'Rhyhorn', 'Snorlax'])
        self.assertEqual(t.names(t.zone(P2, 'hand')), ['Rhyperior', 'Rhyperior'])

    # --- Owner ruling: Gapejaw Bog hits a doll/fossil played to the Bench ---
    async def test_gapejaw_bog_hits_doll_played_to_bench(self):
        for spec, hp in (('SM12.LilliesPokDoll_197', 30), ('SWSH10.UnidentifiedFossil_157', 60)):
            with self.subTest(spec=spec):
                t = self.table()
                t.put(self.filler, P1, 'active')
                t.stadium('SWSH10.GapejawBog_142', P2)
                doll = t.put(spec, P1, 'hand')
                await t.play(doll)
                self.assertIn(doll, t.zone(P1, 'bench'))
                self.assertEqual(t.hp(doll), hp - 20)       # 2 damage counters

    # --- Owner ruling: Delta Evolution onto a Pokémon that evolved this turn ---
    async def test_delta_evolution_onto_pokemon_evolved_this_turn(self):
        t = self.table()
        togepi = t.put(TOGEPI, P1, 'active')
        t.next_turn(); t.next_turn()                     # Togepi from an earlier turn
        togetic = t.put(TOGETIC, P1, 'hand')
        await t.play(togetic, targets=[togepi.entity_id])
        self.assertEqual(self.name(t.active(P1)), 'Togetic')
        plain = t.put(TOGEKISS_PLAIN, P1, 'hand')
        self.assertFalse(t.can(plain, 'EvolvePokemonPlayAbility'))
        delta = t.put(TOGEKISS_DELTA, P1, 'hand')
        self.assertTrue(t.can(delta, 'EvolvePokemonPlayAbility'))
        await t.play(delta, targets=[t.active(P1).entity_id])
        self.assertEqual(self.name(t.active(P1)), 'Togekiss')

    # --- Dragon's Wish: no attach prompt during the attack -------------------
    async def test_dragons_wish_only_affects_next_turn(self):
        t = self.table()
        dragonair = t.put('SM1.Dragonair_95', P1, 'active')
        t.energy(dragonair, WATER, 1)
        for _ in range(3):
            t.put(t.basic_energy(WATER), P1, 'hand')
        await t.attack(dragonair, "Dragon's Wish")
        self.assertEqual(t.prompts, [])                 # nothing attached now
        self.assertEqual(len(dragonair.children), 1)
        t.next_turn(); t.next_turn()
        for energy in list(t.zone(P1, 'hand')):
            self.assertTrue(t.can(energy, 'DefaultEnergyPlayAbility'))
            await t.play(energy, targets=[dragonair.entity_id])
        self.assertEqual(len(dragonair.children), 4)


if __name__ == '__main__':
    unittest.main()
