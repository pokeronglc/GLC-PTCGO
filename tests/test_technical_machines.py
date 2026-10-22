"""Technical Machines grant their attack to any Pokémon they're attached to
(player report: TM Turbo Energize and TM Evolution attacks weren't offered).

The holder check read "The Pokémon this card is attached to" as a Pokémon
*named* "Pokémon", so no TM ever applied."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.data_utils import ABILITIES_BY_ID, CARD_DEFS_BY_GUID
from spirit.game.session.legal_actions import _attack_entries
from spirit.tools.effect_smoke import P1

TMS = {
    'SV4.TechnicalMachineTurboEnergize_179': 'Turbo Energize',
    'SV4.TechnicalMachineEvolution_178': 'Evolution',
    'SV4.TechnicalMachineDevolution_177': 'Devolution',
    'SV4.TechnicalMachineBlindside_176': 'Blindside',
    'SV045.TechnicalMachineCrisisPunch_90': 'Crisis Punch',
    'SV08.TechnicalMachineFluorite_188': 'Fluorite',
}


class TechnicalMachineTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_each_tm_attack_is_offered(self):
        for path, title in TMS.items():
            with self.subTest(tm=title):
                rig, e = self.rig('BW7.Charmander_18')
                holder = e['target']
                for kind in self.energies.values():
                    for _ in range(3):
                        energy = self.add(rig, CARD_DEFS_BY_GUID[kind.lower()], P1, 'hand')
                        rig.attach(energy, holder)
                tool = self.add(rig, fixtures.definition(path), P1, 'hand')
                await rig.session._execute_attach_tool(
                    P1, tool, {'targetInfoLst': [{'validTargets': [holder.entity_id]}]},
                    [holder.entity_id])
                rows = [r.get('title', {}).get('id')
                        for r in holder.get_attribute(AttrID.PIE_ABILITIES) or []]
                self.assertIn(title, rows)
                offered = []
                for entry in _attack_entries(rig.board, rig.session.turn_state, P1,
                                             rig.session.game_id):
                    ability = ABILITIES_BY_ID.get(entry['selectableAction']['actionID'])
                    offered.append(ability.title if ability else None)
                self.assertIn(title, offered)


if __name__ == "__main__":
    unittest.main()
