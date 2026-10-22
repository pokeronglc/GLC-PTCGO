"""Bug hunt round 2, deck 7 (Fighting): Binacle, Barbaracle, Focus Sash, Luminous Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2

F, W, D, L = PokemonTypes.FIGHTING, PokemonTypes.WATER, PokemonTypes.DARKNESS, PokemonTypes.LIGHTNING
BINACLE, BARBARACLE = 'ME3.Binacle_42', 'ME3.Barbaracle_43'
SASH, LUMINOUS = 'XY3.FocusSash_91', 'SV2.LuminousEnergy_191'
PALAFIN = 'SV05.Palafin_49'          # Vanguard Punch: 130 for [W]
SABLEYE = 'SV2.Sableye_136'          # Unseen Claw [D]
MAREEP = 'ME4.Mareep_27'             # Thunder Wave [L][C]
SHIELD = 'XY5.ShieldEnergy_143'      # another Special Energy (only valid on Metal)
DOUBLE_TURBO = 'SWSH9.DoubleTurboEnergy_151'


class Deck7Cards(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    # --- Binacle: Double Draw -----------------------------------------------
    async def test_double_draw(self):
        t = self.table()
        bin_ = t.put(BINACLE, P1, 'active')
        t.energy(bin_, F)
        await t.attack(bin_, 'Double Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Barbaracle: Stone Arms ---------------------------------------------
    async def test_stone_arms_attaches_basic_fighting_to_fighting(self):
        t = self.table()
        barb = t.put(BARBARACLE, P1, 'bench')
        binacle = t.put(BINACLE, P1, 'active')
        t.put(self.filler, P1, 'bench')
        energy = t.put(t.basic_energy(F), P1, 'hand')
        offered = []
        t.pokemon = lambda c, p: (offered.extend(c), binacle)[1]
        await t.use(barb, 'Stone Arms')
        self.assertIn(energy, list(t.board.attached_energies(binacle)))
        self.assertTrue(offered and all(p in (barb, binacle) for p in offered), offered)
        self.assertIsNone(t.ability_offer(barb, 'Stone Arms'))

    async def test_stone_arms_needs_basic_fighting_in_hand(self):
        t = self.table()
        barb = t.put(BARBARACLE, P1, 'active')
        t.put(t.basic_energy(W), P1, 'hand')
        t.put(LUMINOUS, P1, 'hand')         # Special Energy doesn't count
        self.assertIsNone(t.ability_offer(barb, 'Stone Arms'))

    async def test_stone_arms_doesnt_use_energy_attachment(self):
        t = self.table()
        barb = t.put(BARBARACLE, P1, 'active')
        t.put(t.basic_energy(F), P1, 'hand')
        second = t.put(t.basic_energy(F), P1, 'hand')
        t.pokemon = lambda c, p: barb
        await t.use(barb, 'Stone Arms')
        self.assertTrue(t.can(second, 'DefaultEnergyPlayAbility'))

    # --- Focus Sash -------------------------------------------------------
    async def _hit(self, spec, full=True, sash=True):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        attacker = t.put(PALAFIN, P2, 'active')
        t.energy(attacker, W)
        target = t.put(spec, P1, 'active')
        target.set_attribute(AttrID.WEAKNESS_TYPES, [])
        target.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if not full:
            target.set_attribute(AttrID.HP, t.hp(target) - 10)
        t.put(self.filler, P1, 'bench')
        tool = None
        if sash:
            tool = t.put(SASH, P1, 'hand')
            await t.play(tool, targets=[target.entity_id])
        t.next_turn()
        await t.attack(attacker, 'Vanguard Punch', pid=P2)
        return t, target, tool

    async def test_focus_sash_survives_at_10_and_discards(self):
        t, binacle, sash = await self._hit(BINACLE)
        self.assertIn(binacle, t.board.pokemon_in_play(P1))
        self.assertEqual(t.hp(binacle), 10)
        self.assertIn(sash, t.zone(P1, 'discard'))
        self.assertEqual(t.board.prizes_taken(P2), 0)

    async def test_focus_sash_needs_full_hp(self):
        t, binacle, sash = await self._hit(BINACLE, full=False)
        self.assertNotIn(binacle, t.board.pokemon_in_play(P1))

    async def test_focus_sash_fighting_only(self):
        t, sab, sash = await self._hit(SABLEYE)
        self.assertNotIn(sab, t.board.pokemon_in_play(P1))

    # --- Luminous Energy ----------------------------------------------------
    async def test_luminous_provides_any_type_one_at_a_time(self):
        t = self.table()
        mareep = t.put(MAREEP, P1, 'active')
        await t.play(t.put(LUMINOUS, P1, 'hand'), targets=[mareep.entity_id])
        # [L][C]: Luminous alone is only 1 Energy
        self.assertIsNone(t.attack_offer(mareep, 'Thunder Wave'))
        t.energy(mareep, W)
        self.assertIsNotNone(t.attack_offer(mareep, 'Thunder Wave'))   # Luminous pays [L]
        sab = t.put(SABLEYE, P1, 'bench')
        t.attach(LUMINOUS, sab)
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(mareep)
        t.board.find_player_area(P1, 'bench').remove_child(sab)
        t.board.add_card_to_area(sab, t.board.find_player_area(P1, 'activePokemonArea'))
        self.assertIsNotNone(t.attack_offer(sab, 'Unseen Claw'))        # pays [D]

    async def test_luminous_colorless_with_other_special(self):
        t = self.table()
        mareep = t.put(MAREEP, P1, 'active')
        await t.play(t.put(LUMINOUS, P1, 'hand'), targets=[mareep.entity_id])
        t.attach(DOUBLE_TURBO, mareep)
        # Luminous now provides [C] only; Double Turbo gives [C][C]: no [L]
        self.assertIsNone(t.attack_offer(mareep, 'Thunder Wave'))


if __name__ == "__main__":
    unittest.main()
