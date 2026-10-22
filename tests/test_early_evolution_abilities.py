"""Pokémon whose own Ability lets them evolve early, checked against the
normal turn gates (played this turn / either player's first turn)."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.data_utils import def_for
from spirit.game.scripts.cards import loader
from spirit.game.session.legal_actions import compute_legal_actions
from spirit.tools.effect_smoke import P1, P2

ADAPTIVE = ['SWSH2.Caterpie_1', 'SWSH2.Metapod_2', 'XY2.Caterpie_1', 'XY2.Metapod_2',
            'SV1.Scatterbug_8', 'SV1.Spewpa_9']
GO_SECOND = ['SV035.Spearow_21', 'SM9.Bronzor_100', 'SM7.Clamperl_41', 'SM5.Shinx_45',
             'SM6.Flabb_83']
PARTNER = {'ZSV10PT5.Karrablast_9': 'RSV10PT5.Shelmet_8',
           'RSV10PT5.Shelmet_8': 'ZSV10PT5.Karrablast_9'}


def _evolution(definition):
    name = loader.cards_by_guid[definition.guid.lower()].get_attribute_value(AttrID.EVOLUTION_LOGIC_NAME)
    options = [c for c in loader.cards if c.get_attribute_value(AttrID.EVOLUTION_LOGIC_FROM) == name]
    same = [c for c in options if def_for(c.guid).set_code == definition.set_code]
    return def_for((same or options)[0].guid)


class EarlyEvolutionTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def scenario(self, path, when, extra=None):
        """when: 'played_now' (turn 3+), 'second_first' (turn 2), 'first_first' (turn 1)."""
        rig, _ = self.rig('SM9.Moltres_19')
        ts = rig.session.turn_state
        definition = fixtures.definition(path)
        basic = self.add(rig, definition, P1, 'bench')
        if when == 'played_now':
            ts.mark_entered_play(basic.entity_id)
        else:
            ts.entered_play_turn[basic.entity_id] = 0
            ts.turn_number = 2 if when == 'second_first' else 1
        if extra:
            self.add(rig, fixtures.definition(extra), P1, 'bench')
        evolution = self.add(rig, _evolution(definition), P1, 'hand')
        return any(basic.entity_id in info.get('validTargets', [])
                   for entry in compute_legal_actions(rig.board, ts, P1, rig.session.game_id)
                   if entry['entityID'] == evolution.entity_id
                   and entry['selectableAction']['description'] == 'EvolvePokemonPlayAbility'
                   for info in entry['targetInfoLst'])

    def test_adaptive_evolution_always(self):
        for path in ADAPTIVE:
            for when in ('played_now', 'second_first', 'first_first'):
                with self.subTest(path=path, when=when):
                    self.assertTrue(self.scenario(path, when))

    def test_go_second_first_turn_only(self):
        for path in GO_SECOND:
            with self.subTest(path=path):
                self.assertTrue(self.scenario(path, 'second_first'))
                self.assertFalse(self.scenario(path, 'first_first'))
                self.assertFalse(self.scenario(path, 'played_now'))

    def test_partner_in_play_required(self):
        for path, partner in PARTNER.items():
            with self.subTest(path=path):
                self.assertFalse(self.scenario(path, 'played_now'))
                self.assertTrue(self.scenario(path, 'played_now', extra=partner))
                self.assertTrue(self.scenario(path, 'first_first', extra=partner))

    def test_opponent_active_conditions(self):
        import spirit.game.card_effects.bw_era as bw
        self.assertFalse(self.scenario('ME3.Luxio_27', 'played_now'))
        self.assertFalse(self.scenario('SM12.Hakamoo_162', 'played_now'))
        original = bw.subtypes_for
        with patch.object(bw, 'subtypes_for',
                          lambda a: list(original(a) or []) + ['ex', 'GX']):
            self.assertTrue(self.scenario('ME3.Luxio_27', 'played_now'))
            self.assertTrue(self.scenario('ME3.Luxio_27', 'first_first'))
            self.assertTrue(self.scenario('SM12.Hakamoo_162', 'played_now'))
            # Hakamo-o's text is "the turn you play it" only, not the first turn.
            self.assertFalse(self.scenario('SM12.Hakamoo_162', 'first_first'))


if __name__ == "__main__":
    unittest.main()
