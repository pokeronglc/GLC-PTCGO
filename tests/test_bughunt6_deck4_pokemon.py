"""Bug hunt round 6, deck 4 (Fighting): every Pokémon, checked against its
printed text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, F, R = PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.FIRE
GIBLE_NAME = 'Gible'
GABITE, GARCHOMP = 'SM6.Gabite_61', 'SM11.Garchomp_114'
HGROWLITHE, HARCANINE = 'SWSH10.HisuianGrowlithe_70', 'SWSH10.HisuianArcanine_71'
NACLI, NACLSTACK, GARGANACL = 'SV2.Nacli_121', 'SV4.Naclstack_103', 'SV4.Garganacl_104'
RIOLU, LUCARIO = 'SV1.Riolu_113', 'SM5.Lucario_67'
GZAPDOS, GROUDON = 'SWSH7.GalarianZapdos_82', 'SV4.Groudon_93'
TIMBURR = 'BW1.Timburr_58'                 # vanilla Fighting attacker (Pound 30, FF)
STONE = 'SWSH4.StoneFightingEnergy_164'


class Bughunt6Deck4Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp=None):
        t = Table(self)
        self.opp = t.put(opp or self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    @staticmethod
    def lost(p, hp=400):
        return hp - p.get_attribute(AttrID.HP, 0)

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def is_basic(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    async def test_set_codes(self):
        for path, code in ((GABITE, 'SM6'), (GARCHOMP, 'SM11'), (HGROWLITHE, 'SWSH10'),
                           (HARCANINE, 'SWSH10'), (NACLI, 'SV2'), (NACLSTACK, 'SV4'),
                           (GARGANACL, 'SV4'), (RIOLU, 'SV1'), (LUCARIO, 'SM5'),
                           (GZAPDOS, 'SWSH7'), (GROUDON, 'SV4')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Gabite (FLI 61): Ascension -----------------------------------------
    async def test_ascension_evolves_into_garchomp_from_deck(self):
        t = self.table()
        g = t.put(GABITE, P1, 'active')
        t.energy(g, F)
        other = t.deck(P1, [GARGANACL])[0]      # Stage 2, but not from Gabite
        chomp = t.deck(P1, [GARCHOMP])[0]
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.attack(g, 'Ascension')
        self.assertNotIn(other, seen)
        self.assertIs(t.active(P1), chomp)
        self.assertEqual(self.name(t.active(P1)), 'Garchomp')
        self.assertIn(other, t.zone(P1, 'deck'))
        self.assertEqual(self.lost(self.opp), 0)

    async def test_ascension_no_evolution_in_deck_does_nothing(self):
        t = self.table()
        g = t.put(GABITE, P1, 'active')
        t.energy(g, F)
        t.deck(P1, [GARGANACL])
        await t.attack(g, 'Ascension')
        self.assertIs(t.active(P1), g)

    # --- Garchomp (UNM 114): Avenging Aura / Over Slice ---------------------
    async def _over_slice(self, my_prizes, opp_prizes, discard):
        t = self.table()
        c = t.put(GARCHOMP, P1, 'active')
        t.energy(c, F, 2)
        t.set_prizes(P1, my_prizes)
        t.set_prizes(P2, opp_prizes)
        t.yes = discard
        await t.attack(c, 'Over Slice')
        return t, c

    async def test_over_slice_plain_80(self):
        t, c = await self._over_slice(3, 3, False)
        self.assertEqual(self.lost(self.opp), 80)
        self.assertEqual(len(t.board.attached_energies(c)), 2)

    async def test_over_slice_discard_adds_40(self):
        t, c = await self._over_slice(3, 3, True)
        self.assertEqual(self.lost(self.opp), 120)
        self.assertEqual(len(t.board.attached_energies(c)), 1)

    async def test_avenging_aura_more_prizes_adds_80(self):
        t, c = await self._over_slice(4, 3, False)
        self.assertEqual(self.lost(self.opp), 160)

    async def test_avenging_aura_fewer_prizes_no_bonus(self):
        t, c = await self._over_slice(2, 3, False)
        self.assertEqual(self.lost(self.opp), 80)

    async def test_avenging_aura_before_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        c = t.put(GARCHOMP, P1, 'active')
        t.energy(c, F, 2)
        t.set_prizes(P1, 5)
        t.set_prizes(P2, 2)
        t.yes = False
        await t.attack(c, 'Over Slice')
        self.assertEqual(self.lost(self.opp), (80 + 80) * 2)

    # --- Hisuian Growlithe (ASR 70): Defensive Posture ----------------------
    async def _posture(self, heads):
        t = Table(self)
        g = t.put(HGROWLITHE, P1, 'active')
        g.set_attribute(AttrID.WEAKNESS_TYPES, [])
        foe = t.put(TIMBURR, P2, 'active')
        self.big(foe)
        t.energy(foe, F, 2)
        t.heads = heads
        await t.attack(g, 'Defensive Posture')
        t.next_turn()
        await t.attack(foe, 'Pound', pid=P2)
        return t, g

    async def test_defensive_posture_heads_prevents_damage(self):
        t, g = await self._posture(True)
        self.assertEqual(t.damage(g), 0)

    async def test_defensive_posture_tails_no_protection(self):
        t, g = await self._posture(False)
        self.assertEqual(t.damage(g), 30)

    async def test_defensive_posture_expires_after_opponents_turn(self):
        t, g = await self._posture(True)
        foe = t.active(P2)
        t.next_turn(); t.next_turn()
        await t.attack(foe, 'Pound', pid=P2)
        self.assertEqual(t.damage(g), 30)

    # --- Hisuian Arcanine (ASR 71): Scorching Horn --------------------------
    async def test_scorching_horn_with_fire_energy(self):
        t = self.table()
        a = t.put(HARCANINE, P1, 'active')
        t.energy(a, F, 2)
        t.energy(a, R)
        await t.attack(a, 'Scorching Horn')
        self.assertEqual(self.lost(self.opp), 160)
        self.assertIn(BURNED, t.conditions(self.opp))
        self.assertNotIn(BURNED, t.conditions(a))

    async def test_scorching_horn_without_fire_energy(self):
        t = self.table()
        a = t.put(HARCANINE, P1, 'active')
        t.energy(a, F, 3)
        await t.attack(a, 'Scorching Horn')
        self.assertEqual(self.lost(self.opp), 80)
        self.assertNotIn(BURNED, t.conditions(self.opp))

    async def test_hisuian_arcanine_evolves_from_hisuian_growlithe_only(self):
        t = self.table()
        g = t.put(HGROWLITHE, P1, 'bench')
        r = t.put(RIOLU, P1, 'bench')
        a = t.put(HARCANINE, P1, 'hand')
        targets = t.targets(a, 'EvolvePokemonPlayAbility')
        self.assertIn(g.entity_id, targets)
        self.assertNotIn(r.entity_id, targets)

    # --- Nacli (PAL 121): Salt Coating --------------------------------------
    async def test_salt_coating_heals_20_from_benched(self):
        t = self.table()
        n = t.put(NACLI, P1, 'active')
        t.energy(n, F)
        hurt = t.put(self.filler, P1, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 50)
        t.pokemon = lambda c, p: hurt if hurt in c else c[0]
        await t.attack(n, 'Salt Coating')
        self.assertEqual(t.damage(hurt), 30)
        self.assertEqual(self.lost(self.opp), 0)

    async def test_salt_coating_cannot_heal_opponent(self):
        t = self.table()
        n = t.put(NACLI, P1, 'active')
        t.energy(n, F)
        self.opp.set_attribute(AttrID.HP, 350)
        offered = []
        t.pokemon = lambda c, p: (offered.extend(c), c[0])[1]
        await t.attack(n, 'Salt Coating')
        self.assertNotIn(self.opp, offered)
        self.assertEqual(self.lost(self.opp), 50)

    # --- Naclstack (PAR 103): Rocky Tackle ----------------------------------
    async def test_rocky_tackle_damages_self_30(self):
        t = self.table()
        n = t.put(NACLSTACK, P1, 'active')
        t.energy(n, F, 2)
        await t.attack(n, 'Rocky Tackle')
        self.assertEqual(self.lost(self.opp), 80)
        self.assertEqual(t.damage(n), 30)

    # --- Garganacl (PAR 104): Energizing Rock Salt --------------------------
    async def test_rock_salt_attaches_basic_fighting_from_discard_and_heals(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        gar = t.put(GARGANACL, P1, 'bench')
        hurt = t.put(self.filler, P1, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 50)
        energy = t.put(t.basic_energy(F), P1, 'discard')
        t.pokemon = lambda c, p: hurt if hurt in c else c[0]
        await t.use(gar, 'Energizing Rock Salt')
        self.assertIn(energy, t.board.attached_energies(hurt))
        self.assertEqual(t.damage(hurt), 20)
        # Once during your turn.
        t.put(t.basic_energy(F), P1, 'discard')
        self.assertIsNone(t.ability_offer(gar, 'Energizing Rock Salt'))

    async def test_rock_salt_ignores_other_energy_in_discard(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        gar = t.put(GARGANACL, P1, 'bench')
        hurt = t.put(self.filler, P1, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 50)
        t.put(t.basic_energy(W), P1, 'discard')
        t.put(STONE, P1, 'discard')               # Special, not Basic
        if t.ability_offer(gar, 'Energizing Rock Salt') is not None:
            await t.use(gar, 'Energizing Rock Salt')
        self.assertEqual(t.board.attached_energies(hurt), [])
        self.assertEqual(t.damage(hurt), 50)       # no heal without an attach

    # --- Riolu (SVI 113): Reckless Charge -----------------------------------
    async def test_reckless_charge_damages_self_20(self):
        t = self.table()
        r = t.put(RIOLU, P1, 'active')
        t.energy(r, F, 2)
        await t.attack(r, 'Reckless Charge')
        self.assertEqual(self.lost(self.opp), 50)
        self.assertEqual(t.damage(r), 20)

    # --- Lucario (UPR 67): Precognitive Aura / Missile Jab ------------------
    async def test_precognitive_aura_with_garchomp_searches_any_card(self):
        t = self.table()
        t.put(GARCHOMP, P1, 'active')
        luc = t.put(LUCARIO, P1, 'bench')
        target = t.deck(P1, [NACLI])[0]
        t.picks = lambda cards, count, prompt, display: [target]
        await t.use(luc, 'Precognitive Aura')
        self.assertEqual(t.zone(P1, 'hand'), [target])
        self.assertIsNone(t.ability_offer(luc, 'Precognitive Aura'))

    # FIXED (was BUG): Precognitive Aura is offered (and searches) with no Garchomp of yours in play.
    async def test_precognitive_aura_needs_your_garchomp(self):
        t = self.table(opp=GARCHOMP)               # opponent's Garchomp doesn't count
        t.put(self.filler, P1, 'active')
        luc = t.put(LUCARIO, P1, 'bench')
        t.put(GABITE, P1, 'bench')
        self.assertIsNone(t.ability_offer(luc, 'Precognitive Aura'))

    # FIXED (was BUG): Precognitive Aura is offered (and searches) with no Garchomp in play at all.
    async def test_precognitive_aura_without_any_garchomp(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        luc = t.put(LUCARIO, P1, 'bench')
        target = t.deck(P1, [NACLI])[0]
        t.picks = lambda cards, count, prompt, display: [target]
        if t.ability_offer(luc, 'Precognitive Aura') is not None:
            await t.use(luc, 'Precognitive Aura')
        self.assertEqual(t.zone(P1, 'hand'), [])

    async def test_missile_jab_ignores_resistance(self):
        t = self.table()
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [F.value])
        luc = t.put(LUCARIO, P1, 'active')
        t.energy(luc, F, 2)
        await t.attack(luc, 'Missile Jab')
        self.assertEqual(self.lost(self.opp), 70)

    async def test_missile_jab_still_applies_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        luc = t.put(LUCARIO, P1, 'active')
        t.energy(luc, F, 2)
        await t.attack(luc, 'Missile Jab')
        self.assertEqual(self.lost(self.opp), 140)

    # --- Galarian Zapdos (EVS 82): Strong Legs Charge / Zapper Kick ---------
    async def test_strong_legs_charge_attaches_up_to_two_fighting(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        z = t.put(GZAPDOS, P1, 'hand')
        f1 = t.put(t.basic_energy(F), P1, 'hand')
        f2 = t.put(t.basic_energy(F), P1, 'hand')
        f3 = t.put(t.basic_energy(F), P1, 'hand')
        w = t.put(t.basic_energy(W), P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        await t.play(z)
        self.assertIn(z, t.zone(P1, 'bench'))
        self.assertNotIn(w, offered)
        self.assertEqual(len(t.board.attached_energies(z)), 2)
        self.assertEqual(len([e for e in (f1, f2, f3) if e in t.zone(P1, 'hand')]), 1)
        # Not the manual attachment for the turn.
        self.assertTrue(t.can(w, 'DefaultEnergyPlayAbility'))

    async def test_strong_legs_charge_not_when_evolved_or_from_effects(self):
        # Only "when you play this Pokémon from your hand onto your Bench":
        # a Zapdos benched by another effect (put straight onto the bench) gets nothing.
        t = self.table()
        t.put(self.filler, P1, 'active')
        z = t.put(GZAPDOS, P1, 'bench')
        t.put(t.basic_energy(F), P1, 'hand')
        self.assertEqual(t.board.attached_energies(z), [])
        self.assertIsNone(t.ability_offer(z, 'Strong Legs Charge'))

    async def test_zapper_kick_discard_all_paralyzes(self):
        t = self.table()
        z = t.put(GZAPDOS, P1, 'active')
        t.energy(z, F, 3)
        t.yes = True
        await t.attack(z, 'Zapper Kick')
        self.assertEqual(self.lost(self.opp), 70)
        self.assertEqual(t.board.attached_energies(z), [])
        self.assertIn(PARALYZED, t.conditions(self.opp))

    async def test_zapper_kick_decline_keeps_energy(self):
        t = self.table()
        z = t.put(GZAPDOS, P1, 'active')
        t.energy(z, F, 3)
        t.yes = False
        await t.attack(z, 'Zapper Kick')
        self.assertEqual(self.lost(self.opp), 70)
        self.assertEqual(len(t.board.attached_energies(z)), 3)
        self.assertNotIn(PARALYZED, t.conditions(self.opp))

    # --- Groudon (PAR 93): Swelling Power / Magma Purge ---------------------
    async def test_swelling_power_attaches_basic_fighting_from_hand(self):
        t = self.table()
        g = t.put(GROUDON, P1, 'active')
        t.energy(g, W)
        bench = t.put(self.filler, P1, 'bench')
        w = t.put(t.basic_energy(W), P1, 'hand')
        f = t.put(t.basic_energy(F), P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), cards[:count])[1]
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(g, 'Swelling Power')
        self.assertNotIn(w, offered)
        self.assertIn(f, t.board.attached_energies(bench))
        self.assertIn(w, t.zone(P1, 'hand'))
        self.assertEqual(self.lost(self.opp), 0)

    async def test_swelling_power_ignores_special_fighting(self):
        t = self.table()
        g = t.put(GROUDON, P1, 'active')
        t.energy(g, W)
        stone = t.put(STONE, P1, 'hand')
        await t.attack(g, 'Swelling Power')
        self.assertIn(stone, t.zone(P1, 'hand'))

    async def test_magma_purge_counts_discarded_up_to_four(self):
        t = self.table()
        g = t.put(GROUDON, P1, 'active')
        t.energy(g, F, 3)
        bench = t.put(self.filler, P1, 'bench')
        t.energy(bench, F, 3)
        t.picks = lambda cards, count, prompt, display: cards[:count]
        await t.attack(g, 'Magma Purge')
        remaining = len(t.board.attached_energies(g)) + len(t.board.attached_energies(bench))
        self.assertEqual(remaining, 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 4)
        self.assertEqual(self.lost(self.opp), 240)

    async def test_magma_purge_discard_two(self):
        t = self.table()
        g = t.put(GROUDON, P1, 'active')
        t.energy(g, F, 3)
        bench = t.put(self.filler, P1, 'bench')
        t.energy(bench, F, 2)
        t.picks = lambda cards, count, prompt, display: cards[:2]
        await t.attack(g, 'Magma Purge')
        self.assertEqual(len(t.zone(P1, 'discard')), 2)
        self.assertEqual(self.lost(self.opp), 120)


if __name__ == '__main__':
    unittest.main()
