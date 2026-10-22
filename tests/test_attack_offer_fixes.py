"""Attacks that were never offered (overnight offer sweep).

* Absol's Dark Ambition (a Retreat Cost passive) was read as Slaking's
  "can't attack" lock, so Absol could never attack a Basic Active.
* Attacks with no printed usage restriction can always be declared, even if
  their effect would find nothing (Slowpoke's Ideal Fishing Day)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.data_utils import ABILITIES_BY_ID
from spirit.game.session.legal_actions import _attack_entries, attack_has_usage_restriction
from spirit.tools.effect_smoke import P1, P2


class AttackOfferTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig

    def offered(self, rig):
        return [ABILITIES_BY_ID[x['selectableAction']['actionID']].title
                for x in _attack_entries(rig.board, rig.session.turn_state, P1,
                                         rig.session.game_id)]

    def test_absol_attacks_a_basic_active(self):
        rig, _ = self.rig('SM9.Absol_88')
        self.assertIn('Shadow Seeker', self.offered(rig))

    def test_slaking_still_cannot_attack_a_basic_active(self):
        rig, _ = self.rig('BW6.Slaking_103')
        self.assertNotIn('Crushing Blow', self.offered(rig))

    def test_empty_discard_does_not_hide_an_attack(self):
        rig, _ = self.rig('PGO.Slowpoke_19')
        for pid in (P1, P2):
            discard = rig.board.find_player_area(pid, 'discard')
            lost = rig.board.find_player_area(pid, 'lostZone')
            for card in list(discard.children):
                rig.board.move_card(card.entity_id, lost.entity_id)
        self.assertIn('Ideal Fishing Day', self.offered(rig))

    def test_printed_restrictions_still_apply(self):
        for path, title in (('SWSH10.Shaymin_14', 'Encouraging Gift'),
                            ('SV2.Pincurchin_73', 'Follow-Up Kerzap')):
            attack = next(a for a in fixtures.definition(path).abilities if a.title == title)
            self.assertTrue(attack_has_usage_restriction(attack), path)


if __name__ == "__main__":
    unittest.main()
