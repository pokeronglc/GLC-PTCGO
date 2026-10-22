"""Moltres (SM9) - Top Burner mills one card per Fire Energy discarded; with
Charizard (PGO) Burn Brightly each basic Fire Energy provides 2."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID
from spirit.game.session.effects import EffectContext
from spirit.game.card_effects.pokemon import energy_provides_type
from spirit.tools.effect_smoke import P1, P2

PATH = 'SM9.Moltres_19'


class TopBurnerTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _milled(self, charizard):
        rig, e = self.rig(PATH, 'pokemon')
        board = rig.board
        moltres = e['target']
        for card in list(board.attached_energies(moltres)):
            moltres.remove_child(card)
        fire_guid = self.energies[PokemonTypes.FIRE.value]
        for _ in range(2):
            energy = self.add(rig, CARD_DEFS_BY_GUID[fire_guid.lower()], P1, 'hand')
            board.attach_card(energy.entity_id, moltres.entity_id)
        if charizard:
            self.add(rig, fixtures.definition('PGO.Charizard_10'), P1, 'bench')
        deck = board.find_player_area(P2, 'deck')
        before = len(deck.children)
        attack = next(a for a in fixtures.definition(PATH).abilities if a.title == 'Top Burner')
        await attack.effect(EffectContext(rig.session, P1, moltres, attack))
        self.assertFalse([c for c in board.attached_energies(moltres)
                          if energy_provides_type(c, PokemonTypes.FIRE.value)])
        return before - len(deck.children)

    async def test_without_charizard(self):
        self.assertEqual(await self._milled(False), 2)

    async def test_with_burn_brightly(self):
        self.assertEqual(await self._milled(True), 4)


if __name__ == "__main__":
    unittest.main()
