"""Bug hunt, deck 9 (Fire): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

R, M = PokemonTypes.FIRE, PokemonTypes.METAL
SALANDIT, SALAZZLE = 'CZ.Salandit_27', 'SM10.Salazzle_31'
SLUGMA, MAGCARGO = 'SM7.Slugma_23', 'SM7.Magcargo_24'
CHARMANDER, CHARMELEON, CHARIZARD = 'ME2.Charmander_11', 'SV045.Charmeleon_8', 'PGO.Charizard_10'
TORCHIC, COMBUSKEN, BLAZIKEN = 'XY5.Torchic_26', 'SWSH3.Combusken_23', 'SV10.Blaziken_42'
HEATMOR, CHIYU, MOLTRES, ENTEI = 'RSV10PT5.Heatmor_19', 'SV4.ChiYu_29', 'SV035.Moltres_146', 'SM12.Entei_28'
BRONZOR = 'SV3.Bronzor_144'
MAGNETIC = 'ME4.MagneticMetalEnergy_85'
NEST = 'SV1.NestBall_181'


def name(card):
    return def_for(card.archetype_id).display_name


class Deck9Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    def neutral(self, pokemon, hp=400):
        pokemon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        pokemon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            pokemon.set_attribute(AttrID.HP, hp)

    def swap_opp(self, t, spec):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = t.put(spec, P2, 'active')
        self.neutral(self.opp)
        return self.opp

    async def ko_my_active_on_their_turn(self, t):
        victim = t.put(self.filler, P1, 'active', hp=10)
        attacker = self.swap_opp(t, BRONZOR)
        t.energy(attacker, M, 2)
        t.next_turn()
        await t.attack(attacker, 'Speed Dive', pid=P2)
        assert victim not in t.board.pokemon_in_play(P1), 'setup: victim not KOd'
        t.next_turn()
        self.neutral(self.opp)

    # --- Salandit: Call for Family ----------------------------------------
    async def test_salandit_call_for_family_basic_only(self):
        t = self.table()
        sal = t.put(SALANDIT, P1, 'active')
        t.energy(sal, R)
        t.deck(P1, [SALAZZLE, SLUGMA])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:count])[1]
        await t.attack(sal, 'Call for Family')
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Slugma'])
        self.assertNotIn('Salazzle', seen.get('n', []))

    # --- Salazzle: Roast Reveal --------------------------------------------
    async def test_roast_reveal_discard_fire_draw_three(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        salazzle = t.put(SALAZZLE, P1, 'bench')
        fire = t.put(t.basic_energy(R), P1, 'hand')
        await t.use(salazzle, 'Roast Reveal')
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        t.put(t.basic_energy(R), P1, 'hand')
        self.assertIsNone(t.ability_offer(salazzle, 'Roast Reveal'))

    async def test_roast_reveal_needs_fire_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        salazzle = t.put(SALAZZLE, P1, 'bench')
        t.put(t.basic_energy(M), P1, 'hand')
        self.assertIsNone(t.ability_offer(salazzle, 'Roast Reveal'))

    # --- Slugma: Magma Ring ---------------------------------------------------
    async def test_magma_ring_blocks_retreat_next_turn(self):
        t = self.table()
        slugma = t.put(SLUGMA, P1, 'active')
        t.energy(slugma, R)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, M, 4)
        await t.attack(slugma, 'Magma Ring')
        self.assertEqual(400 - t.hp(self.opp), 10)
        t.next_turn()
        self.assertFalse(t.can(self.opp, 'BaseRetreat', P2))
        t.next_turn(); t.next_turn()
        self.assertTrue(t.can(self.opp, 'BaseRetreat', P2))

    # --- Magcargo: Smooth Over -------------------------------------------
    async def test_smooth_over_puts_chosen_card_on_top(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mag = t.put(MAGCARGO, P1, 'bench')
        target = t.deck(P1, [NEST], top=False)[0]          # bottom of the deck
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is target][:1] or cards[:count]
        hand = len(t.zone(P1, 'hand'))
        await t.use(mag, 'Smooth Over')
        deck = t.zone(P1, 'deck')
        self.assertIn(target, deck)
        self.assertIs(deck[-1], target, 'chosen card should be on top')
        self.assertEqual(len(t.zone(P1, 'hand')), hand)
        self.assertIsNone(t.ability_offer(mag, 'Smooth Over'))

    # --- Charmander: Agile ---------------------------------------------------
    async def test_agile_free_retreat_only_without_energy(self):
        t = self.table()
        ch = t.put(CHARMANDER, P1, 'active')
        self.assertEqual(t.retreat(ch), 0)
        t.energy(ch, R)
        self.assertEqual(t.retreat(ch), 2)

    # --- Charmeleon: Flare Veil ----------------------------------------------
    async def test_flare_veil_prevents_attack_effects_not_damage(self):
        t = self.table()
        chm = t.put(CHARMELEON, P1, 'active')
        self.neutral(chm)
        attacker = self.swap_opp(t, COMBUSKEN)
        t.energy(attacker, R, 3)
        t.next_turn()
        await t.attack(attacker, 'Heat Beak', pid=P2)
        self.assertEqual(400 - t.hp(chm), 40)
        self.assertNotIn(BURNED, t.conditions(chm))

    async def test_without_flare_veil_heat_beak_burns(self):
        t = self.table()
        mine = t.put(CHARMANDER, P1, 'active')
        self.neutral(mine)
        attacker = self.swap_opp(t, COMBUSKEN)
        t.energy(attacker, R, 3)
        t.next_turn()
        await t.attack(attacker, 'Heat Beak', pid=P2)
        self.assertIn(BURNED, t.conditions(mine))

    # --- Charizard (PGO): Flare Blitz with Burn Brightly ---------------------
    async def test_charizard_flare_blitz_two_fire_pay_and_discard_fire_only(self):
        t = self.table()
        zard = t.put(CHARIZARD, P1, 'active')
        fires = t.energy(zard, R, 2)                     # 2 x RR via Burn Brightly = 4
        self.assertIsNotNone(t.attack_offer(zard, 'Flare Blitz'))
        metal = t.energy(zard, M)
        await t.attack(zard, 'Flare Blitz')
        self.assertEqual(400 - t.hp(self.opp), 170)
        for f in fires:
            self.assertIn(f, t.zone(P1, 'discard'))
        self.assertIn(metal, zard.children)

    async def test_charizard_one_fire_not_enough(self):
        t = self.table()
        zard = t.put(CHARIZARD, P1, 'active')
        t.energy(zard, R, 1)
        self.assertIsNone(t.attack_offer(zard, 'Flare Blitz'))

    # --- Torchic: Ω Barrage / Flare Bonus / Claw ----------------------------
    async def test_torchic_flare_bonus_then_attacks_again(self):
        t = self.table()
        torchic = t.put(TORCHIC, P1, 'active')
        t.energy(torchic, R)
        fire = t.put(t.basic_energy(R), P1, 'hand')
        ended = await t.attack(torchic, 'Flare Bonus')
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertFalse(ended, 'Ω Barrage: the first attack keeps the turn')
        self.assertIsNotNone(t.attack_offer(torchic, 'Claw'))
        t.heads = True
        ended = await t.attack(torchic, 'Claw')
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertTrue(ended, 'the second attack ends the turn')

    async def test_torchic_flare_bonus_no_fire_no_draw_and_claw_tails(self):
        t = self.table()
        torchic = t.put(TORCHIC, P1, 'active')
        t.energy(torchic, R)
        t.put(t.basic_energy(M), P1, 'hand')
        await t.attack(torchic, 'Flare Bonus')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        t.heads = False
        await t.attack(torchic, 'Claw')
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Combusken: Heat Beak ------------------------------------------------
    async def test_heat_beak_burns(self):
        t = self.table()
        c = t.put(COMBUSKEN, P1, 'active')
        t.energy(c, R, 3)
        await t.attack(c, 'Heat Beak')
        self.assertEqual(400 - t.hp(self.opp), 40)
        self.assertIn(BURNED, t.conditions(self.opp))

    # --- Blaziken: Inferno Kick Flurry ----------------------------------------
    async def test_inferno_kick_flurry_active_and_bench(self):
        t = self.table()
        blaz = t.put(BLAZIKEN, P1, 'active')
        t.energy(blaz, R, 3)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [R.value])
        bench.set_attribute(AttrID.HP, 400)
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(blaz, 'Inferno Kick Flurry')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertEqual(400 - t.hp(bench), 120)          # no Weakness on the Bench
        self.assertEqual(len(t.board.attached_energies(blaz)), 1)

    async def test_inferno_kick_flurry_no_bench(self):
        t = self.table()
        blaz = t.put(BLAZIKEN, P1, 'active')
        t.energy(blaz, R, 3)
        await t.attack(blaz, 'Inferno Kick Flurry')
        self.assertEqual(400 - t.hp(self.opp), 120)

    # --- Heatmor: Licking Catch ------------------------------------------------
    async def test_licking_catch_fire_pokemon_and_basic_fire_energy(self):
        t = self.table()
        heat = t.put(HEATMOR, P1, 'active')
        t.energy(heat, R)
        cards = t.deck(P1, [SLUGMA, t.basic_energy(R), BRONZOR, t.basic_energy(M), NEST, TORCHIC])
        metal = cards[3]
        seen = {}

        def picks(cards, count, prompt, display):
            seen['n'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        await t.attack(heat, 'Licking Catch')
        self.assertEqual(seen['count'], 3)
        self.assertNotIn('Bronzor', seen['n'])
        self.assertNotIn('Nest Ball', seen['n'])
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertNotIn('Bronzor', t.names(hand))
        self.assertNotIn(metal, hand)

    # --- Chi-Yu: Flare Bringer / Megafire of Envy ----------------------------
    async def test_flare_bringer_two_basic_fire_from_discard(self):
        t = self.table()
        chi = t.put(CHIYU, P1, 'active')
        t.energy(chi, R)
        bench = t.put(self.filler, P1, 'bench')
        for _ in range(3):
            t.put(t.basic_energy(R), P1, 'discard')
        metal = t.put(t.basic_energy(M), P1, 'discard')
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(chi, 'Flare Bringer')
        self.assertEqual(len(t.board.attached_energies(bench)), 2)
        self.assertIn(metal, t.zone(P1, 'discard'))

    async def test_megafire_of_envy(self):
        t = self.table()
        chi = t.put(CHIYU, P1, 'active')
        t.energy(chi, R, 2)
        await t.attack(chi, 'Megafire of Envy')
        self.assertEqual(400 - t.hp(self.opp), 50)
        t = self.table()
        chi = t.put(CHIYU, P1, 'bench')
        t.energy(chi, R, 2)
        await self.ko_my_active_on_their_turn(t)
        await t.attack(chi, 'Megafire of Envy')
        self.assertEqual(400 - t.hp(self.opp), 140)

    # --- Moltres (MEW): Flare Float / Blazing Flight ---------------------------
    async def test_flare_float(self):
        t = self.table()
        mol = t.put(MOLTRES, P1, 'active')
        self.assertEqual(t.retreat(mol), 2)
        t.energy(mol, M)
        self.assertEqual(t.retreat(mol), 2)
        t.energy(mol, R)
        self.assertEqual(t.retreat(mol), 0)

    async def test_blazing_flight_bench_only(self):
        t = self.table()
        mol = t.put(MOLTRES, P1, 'active')
        t.energy(mol, R, 3)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 400)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [R.value])
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(mol, 'Blazing Flight')
        self.assertEqual(400 - t.hp(bench), 120)
        self.assertEqual(400 - t.hp(self.opp), 0)
        self.assertEqual(len(t.board.attached_energies(mol)), 1)

    # --- Entei: Rally Back ------------------------------------------------------
    async def test_rally_back(self):
        t = self.table()
        entei = t.put(ENTEI, P1, 'active')
        t.energy(entei, R, 2)
        await t.attack(entei, 'Rally Back')
        self.assertEqual(400 - t.hp(self.opp), 30)
        t = self.table()
        entei = t.put(ENTEI, P1, 'bench')
        t.energy(entei, R, 2)
        await self.ko_my_active_on_their_turn(t)
        await t.attack(entei, 'Rally Back')
        self.assertEqual(400 - t.hp(self.opp), 120)


if __name__ == "__main__":
    unittest.main()
