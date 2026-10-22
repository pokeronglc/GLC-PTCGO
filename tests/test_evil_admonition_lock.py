"""Weavile / Hoopa - Evil Admonition counts the opponent's Pokémon that have
an Ability; under an Ability lock (Hex Maniac etc.) they have none."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.card_effects.bw_era import _pokemon_has_ability
from spirit.game.models.board import create_card_entity
from spirit.game.scripts.cards import loader
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P2

ABILITY_MON = 'Promo_SM.TapuLele_152'  # Wonder Tag


class EvilAdmonitionLockTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    async def _damage(self, path, hex_maniac):
        rig, e = self.rig(path, 'pokemon')
        board = rig.board
        bench = board.find_player_area(P2, 'bench')
        for child in list(bench.children):
            bench.remove_child(child)
        guid = fixtures.definition(ABILITY_MON).guid.lower()
        for _ in range(2):
            mon = create_card_entity(loader.cards_by_guid[guid], P2)
            mon.owning_player_id = P2
            board.add_card_to_area(mon, bench)
            self.assertTrue(_pokemon_has_ability(mon))
        defender = board.active_pokemon(P2)
        defender.set_attribute(AttrID.HP, 500)
        defender.set_attribute(AttrID.WEAKNESS_TYPES, [])
        defender.set_attribute(AttrID.RESISTANCE_TYPES, [])
        state = rig.session.turn_state
        if hex_maniac:
            state.abilities_disabled_through_turn = state.turn_number + 1
        attack = next(a for a in fixtures.definition(path).abilities
                      if getattr(a, 'title', '') == 'Evil Admonition')
        attacker = e['target']
        await attack.effect(EffectContext(rig.session, attacker.owning_player_id, attacker, attack))
        return 500 - defender.get_attribute(AttrID.HP, 0)

    async def test_weavile(self):
        self.assertEqual(await self._damage('SM5.Weavile_74', False), 100)
        self.assertEqual(await self._damage('SM5.Weavile_74', True), 0)

    async def test_hoopa(self):
        self.assertEqual(await self._damage('SM11.Hoopa_140', False), 50)
        self.assertEqual(await self._damage('SM11.Hoopa_140', True), 10)


if __name__ == "__main__":
    unittest.main()
