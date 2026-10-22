"""Bug hunt round 6, deck 4 (Fighting): Trainers and Special Energy checked
against their printed text, including the cases where they should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, F, R = PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.FIRE
GRANT, BRUSH = 'SWSH10.Grant_144', 'SM7.RainbowBrush_141'
ACUITY, STONE = 'SWSH11.LakeAcuity_160', 'SWSH4.StoneFightingEnergy_164'
RIOLU = 'SV1.Riolu_113'            # Punch [F] 10, Fighting
NACLSTACK = 'SV4.Naclstack_103'    # Rocky Tackle [FF] 80, 30 to itself
MARSHTOMP = 'SM7.Marshtomp_34'     # Water; Muddy Water hits a Benched Pokémon
PIDGEY = 'SM9.Pidgey_122'          # Quick Attack [C] 10+, Colorless
TIMBURR = 'BW1.Timburr_58'         # Pound [FF] 30, Fighting
ARTAZON = 'SV2.Artazon_171'


class Bughunt6Deck4Trainers(unittest.IsolatedAsyncioTestCase):
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

    def is_basic(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    async def test_set_codes(self):
        for path, code in ((GRANT, 'SWSH10'), (BRUSH, 'SM7'), (ACUITY, 'SWSH11'),
                           (STONE, 'SWSH4')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Grant (ASR 144) -----------------------------------------------------
    async def test_grant_fighting_attack_plus_30(self):
        t = self.table()
        r = t.put(RIOLU, P1, 'active')
        t.energy(r, F)
        grant = t.put(GRANT, P1, 'hand')
        await t.play(grant)
        self.assertIn(grant, t.zone(P1, 'discard'))
        await t.attack(r, 'Punch')
        self.assertEqual(self.lost(self.opp), 40)

    async def test_grant_before_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [F.value])
        r = t.put(RIOLU, P1, 'active')
        t.energy(r, F)
        await t.play(t.put(GRANT, P1, 'hand'))
        await t.attack(r, 'Punch')
        self.assertEqual(self.lost(self.opp), (10 + 30) * 2)

    async def test_grant_not_for_non_fighting(self):
        t = self.table()
        p = t.put(PIDGEY, P1, 'active')
        t.energy(p, W)
        t.heads = False
        await t.play(t.put(GRANT, P1, 'hand'))
        await t.attack(p, 'Quick Attack')
        self.assertEqual(self.lost(self.opp), 10)

    async def test_grant_expires_next_turn(self):
        t = self.table()
        r = t.put(RIOLU, P1, 'active')
        t.energy(r, F)
        await t.play(t.put(GRANT, P1, 'hand'))
        t.next_turn(); t.next_turn()
        await t.attack(r, 'Punch')
        self.assertEqual(self.lost(self.opp), 10)

    async def test_grant_recovery_from_discard_ignores_supporter_rule(self):
        t = self.table()
        t.put(RIOLU, P1, 'active')
        first = t.put(GRANT, P1, 'hand')
        await t.play(first)                       # Supporter for the turn used
        in_discard = t.put(GRANT, P1, 'discard')
        a = t.put(self.item, P1, 'hand')
        b = t.put(self.item, P1, 'hand')
        offer = t.ability_offer(in_discard, 'Grant')
        self.assertIsNotNone(offer)
        await t.do(offer)
        self.assertIn(in_discard, t.zone(P1, 'hand'))
        self.assertIn(a, t.zone(P1, 'discard'))
        self.assertIn(b, t.zone(P1, 'discard'))
        # Still only 1 Supporter per turn: the recovered Grant can't be played now.
        self.assertFalse(t.can(in_discard, 'UseTrainerCard'))

    async def test_grant_recovery_does_not_use_supporter(self):
        t = self.table()
        t.put(RIOLU, P1, 'active')
        g = t.put(GRANT, P1, 'discard')
        t.put(self.item, P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.do(t.ability_offer(g, 'Grant'))
        self.assertTrue(t.can(g, 'UseTrainerCard'))

    async def test_grant_recovery_needs_two_non_grant_cards(self):
        t = self.table()
        t.put(RIOLU, P1, 'active')
        g = t.put(GRANT, P1, 'discard')
        t.put(self.item, P1, 'hand')
        t.put(GRANT, P1, 'hand')                  # a Grant can't pay
        self.assertIsNone(t.ability_offer(g, 'Grant'))

    # --- Rainbow Brush (CES 141) --------------------------------------------
    async def test_rainbow_brush_switches_energy_with_deck(self):
        t = self.table()
        p = t.put(self.filler, P1, 'active')
        water = t.energy(p, W)
        fighting = t.deck(P1, [t.basic_energy(F)])[0]
        brush = t.put(BRUSH, P1, 'hand')
        await t.play(brush)
        self.assertEqual(t.board.attached_energies(p), [fighting])
        self.assertIn(water, t.zone(P1, 'deck'))
        self.assertIn(brush, t.zone(P1, 'discard'))

    async def test_rainbow_brush_can_switch_out_special_energy(self):
        t = self.table()
        p = t.put(self.filler, P1, 'active')
        stone = t.attach(STONE, p)
        fighting = t.deck(P1, [t.basic_energy(F)])[0]
        await t.play(t.put(BRUSH, P1, 'hand'))
        self.assertEqual(t.board.attached_energies(p), [fighting])
        self.assertIn(stone, t.zone(P1, 'deck'))

    async def test_rainbow_brush_only_basic_energy_from_deck(self):
        t = self.table()
        p = t.put(self.filler, P1, 'active')
        water = t.energy(p, W)
        stone = t.deck(P1, [STONE])[0]
        await t.play(t.put(BRUSH, P1, 'hand'))
        self.assertEqual(t.board.attached_energies(p), [water])
        self.assertIn(stone, t.zone(P1, 'deck'))

    async def test_rainbow_brush_not_playable_without_attached_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.deck(P1, [t.basic_energy(F)])
        brush = t.put(BRUSH, P1, 'hand')
        self.assertFalse(t.can(brush, 'UseTrainerCard'))

    async def test_rainbow_brush_ignores_opponents_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.energy(self.opp, W)
        t.deck(P1, [t.basic_energy(F)])
        brush = t.put(BRUSH, P1, 'hand')
        self.assertFalse(t.can(brush, 'UseTrainerCard'))

    # --- Lake Acuity (LOR 160) ----------------------------------------------
    async def _acuity_hit(self, defender_energy, owner=P1):
        t = self.table()
        t.stadium(ACUITY, owner)
        n = t.put(NACLSTACK, P1, 'active')
        t.energy(n, F, 2)
        if defender_energy is not None:
            t.energy(self.opp, defender_energy)
        await t.attack(n, 'Rocky Tackle')
        return t, n

    async def test_lake_acuity_reduces_for_fighting_or_water_energy(self):
        for kind in (F, W):
            for owner in (P1, P2):
                with self.subTest(kind=kind, owner=owner):
                    t, n = await self._acuity_hit(kind, owner)
                    self.assertEqual(self.lost(self.opp), 60)

    async def test_lake_acuity_no_reduction_other_energy(self):
        for kind in (None, R):
            with self.subTest(kind=kind):
                t, n = await self._acuity_hit(kind)
                self.assertEqual(self.lost(self.opp), 80)

    async def test_lake_acuity_does_not_reduce_self_damage(self):
        # Rocky Tackle's 30 to itself isn't from the opponent's Pokémon.
        t, n = await self._acuity_hit(F)
        self.assertEqual(t.damage(n), 30)

    async def test_lake_acuity_protects_both_sides(self):
        t = Table(self)
        t.stadium(ACUITY, P2)
        mine = t.put(self.filler, P1, 'active')
        self.big(mine)
        t.energy(mine, W)
        foe = t.put(TIMBURR, P2, 'active')
        self.big(foe)
        t.energy(foe, F, 2)
        t.next_turn()
        await t.attack(foe, 'Pound', pid=P2)
        self.assertEqual(self.lost(mine), 10)

    async def test_lake_acuity_special_fighting_counts(self):
        t = self.table()
        t.stadium(ACUITY, P1)
        t.attach(STONE, self.opp)                 # Colorless holder: Stone itself does nothing
        n = t.put(NACLSTACK, P1, 'active')
        t.energy(n, F, 2)
        await t.attack(n, 'Rocky Tackle')
        self.assertEqual(self.lost(self.opp), 60)

    # --- Stone Fighting Energy (VIV 164) ------------------------------------
    async def _stone_hit(self, holder_spec):
        t = Table(self)
        mine = t.put(holder_spec, P1, 'active')
        self.big(mine)
        stone = t.put(STONE, P1, 'hand')
        await t.play(stone, targets=[mine.entity_id])
        foe = t.put(TIMBURR, P2, 'active')
        self.big(foe)
        t.energy(foe, F, 2)
        t.next_turn()
        await t.attack(foe, 'Pound', pid=P2)
        return t, mine, stone

    async def test_stone_fighting_reduces_damage_on_fighting_pokemon(self):
        t, mine, stone = await self._stone_hit(RIOLU)
        self.assertIn(stone, mine.children)
        self.assertEqual(self.lost(mine), 10)

    async def test_stone_fighting_no_reduction_on_non_fighting(self):
        t, mine, stone = await self._stone_hit(self.filler)
        self.assertEqual(self.lost(mine), 30)

    async def test_stone_fighting_provides_fighting_energy(self):
        t = self.table()
        r = t.put(RIOLU, P1, 'active')
        t.attach(STONE, r)
        self.assertIsNotNone(t.attack_offer(r, 'Punch'))
        await t.attack(r, 'Punch')
        self.assertEqual(self.lost(self.opp), 10)

    async def test_stone_fighting_on_non_fighting_still_provides_energy(self):
        t = self.table()
        p = t.put(PIDGEY, P1, 'active')
        t.attach(STONE, p)
        t.heads = False
        self.assertIsNotNone(t.attack_offer(p, 'Quick Attack'))
        await t.attack(p, 'Quick Attack')
        self.assertEqual(self.lost(self.opp), 10)

    async def test_stone_fighting_reduction_not_on_own_damage(self):
        t = self.table()
        n = t.put(NACLSTACK, P1, 'active')
        t.attach(STONE, n)
        t.energy(n, F)
        await t.attack(n, 'Rocky Tackle')
        self.assertEqual(t.damage(n), 30)


if __name__ == '__main__':
    unittest.main()
