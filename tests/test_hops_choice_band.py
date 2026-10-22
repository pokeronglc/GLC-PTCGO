"""Hop's Choice Band: attacks of the Hop's Pokémon it's attached to cost one
Colorless less (player report: Hop's Snorlax with Double Turbo couldn't attack)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.data_utils import def_for
from spirit.game.session.legal_actions import _attack_entries
from spirit.game.session.passives import compute_damage
from spirit.tools.effect_smoke import P1, P2


class HopsChoiceBandTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def snorlax(self, band=True):
        rig, e = self.rig('SV09.HopsSnorlax_117')
        snorlax = e['target']
        for energy in list(rig.board.attached_energies(snorlax)):
            rig.to_area(energy, P1, 'discard')
        if band:
            rig.attach(self.add(rig, fixtures.definition('SV09.HopsChoiceBand_148'), P1, 'hand'), snorlax)
        rig.attach(self.add(rig, fixtures.definition('SWSH9.DoubleTurboEnergy_151'), P1, 'hand'), snorlax)
        return rig, snorlax

    def attacks(self, rig):
        return _attack_entries(rig.board, rig.session.turn_state, P1, rig.session.game_id)

    async def test_double_turbo_and_band_pay_dynamic_press(self):
        rig, _ = self.snorlax(band=True)
        self.assertEqual(len(self.attacks(rig)), 1)

    async def test_double_turbo_alone_is_not_enough(self):
        rig, _ = self.snorlax(band=False)
        self.assertEqual(self.attacks(rig), [])

    async def test_band_adds_30_damage(self):
        with_band, a = self.snorlax(band=True)
        without, b = self.snorlax(band=False)
        dealt = lambda rig, p: compute_damage(rig.board, p, rig.board.active_pokemon(P2), 100,
                                             ignore_weakness=True).amount
        self.assertEqual(dealt(with_band, a) - dealt(without, b), 30)

    async def test_dynamic_press_damages_itself(self):
        from spirit.game.attributes import AttrID
        from spirit.game.session.effects import EffectContext
        from spirit.game.session.passives import effective_max_hp
        rig, snorlax = self.snorlax(band=False)
        snorlax.set_attribute(AttrID.HP, effective_max_hp(rig.board, snorlax))
        attack = next(a for a in fixtures.definition('SV09.HopsSnorlax_117').abilities
                      if a.title == 'Dynamic Press')
        ctx = EffectContext(rig.session, P1, snorlax, attack)
        before = snorlax.get_attribute(AttrID.HP)
        await attack.effect(ctx)
        for action in list(ctx.deferred_actions):
            await action()
        self.assertEqual(before - snorlax.get_attribute(AttrID.HP), 80)


if __name__ == "__main__":
    unittest.main()
