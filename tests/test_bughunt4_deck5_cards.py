"""Bug hunt round 4, deck 5: Feebas / Milotic / Wiglett / Devolution Spray
checked against their printed text, including the should-NOT-work cases."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W = PokemonTypes.WATER
FEEBAS, MILOTIC = 'DM.Feebas_28', 'XY5.Milotic_44'
WIGLETT, SPRAY = 'SV1.Wiglett_56', 'XY12.DevolutionSpray_76'
MUDKIP, MARSHTOMP, SWAMPERT = 'SM7.Mudkip_33', 'SM7.Marshtomp_34', 'SM7.Swampert_35'
FROSMOTH = 'ME1.Frosmoth_43'


class Bughunt4Deck5(unittest.IsolatedAsyncioTestCase):
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

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def opp_attacker(self, t, spec):
        old = t.active(P2)
        mon = t.put(spec, P2, 'bench')
        t.board.move_card(old.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(mon.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        return mon

    async def test_set_codes(self):
        for path, code in ((FEEBAS, 'DM'), (MILOTIC, 'XY5'), (WIGLETT, 'SV1'), (SPRAY, 'XY12')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Feebas (DRM 28): Submerge -----------------------------------------
    async def test_submerge_prevents_opponent_spread_on_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        fee = t.put(FEEBAS, P1, 'bench')
        other = t.put(self.filler, P1, 'bench')
        t.next_turn()
        fm = self.opp_attacker(t, FROSMOTH)
        t.energy(fm, W)
        await t.attack(fm, 'Chilling Wings', pid=P2)
        self.assertEqual(t.damage(fee), 0)
        self.assertIn(fee, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(other), 20)

    async def test_submerge_not_while_active(self):
        t = self.table()
        fee = t.put(FEEBAS, P1, 'active')
        t.next_turn()
        fm = self.opp_attacker(t, FROSMOTH)
        t.energy(fm, W)
        await t.attack(fm, 'Chilling Wings', pid=P2)
        self.assertEqual(t.damage(fee), 20)

    # --- Milotic (PRC 44): Sparkling Ripples / Aqua Swirl -----------------
    async def test_sparkling_ripples_returns_card_from_discard_on_evolve(self):
        t = self.table()
        fee = t.put(FEEBAS, P1, 'active')
        mil = t.put(MILOTIC, P1, 'hand')
        gone = t.put(MUDKIP, P1, 'discard')
        t.put(self.item, P1, 'discard')
        t.picks = lambda cards, n, pr, d: [gone] if gone in cards else cards[:n]
        await t.play(mil, targets=[fee.entity_id])
        self.assertIs(t.active(P1), mil)
        self.assertIn(gone, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    async def test_sparkling_ripples_is_optional(self):
        t = self.table()
        fee = t.put(FEEBAS, P1, 'active')
        mil = t.put(MILOTIC, P1, 'hand')
        gone = t.put(MUDKIP, P1, 'discard')
        t.yes = False
        await t.play(mil, targets=[fee.entity_id])
        self.assertIs(t.active(P1), mil)
        self.assertIn(gone, t.zone(P1, 'discard'))

    async def test_sparkling_ripples_not_when_already_in_play(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mil = t.put(MILOTIC, P1, 'bench')
        t.put(MUDKIP, P1, 'discard')
        self.assertIsNone(t.ability_offer(mil, 'Sparkling Ripples'))

    async def test_aqua_swirl_yes_opponent_switches(self):
        t = self.table()
        mil = t.put(MILOTIC, P1, 'active')
        t.energy(mil, W, 3)
        b = t.put(self.filler, P2, 'bench')
        self.big(b)
        await t.attack(mil, 'Aqua Swirl')
        self.assertEqual(400 - t.hp(self.opp), 60)        # damage first, then switch
        self.assertIs(t.active(P2), b)
        self.assertIn(self.opp, t.zone(P2, 'bench'))

    async def test_aqua_swirl_may_decline(self):
        t = self.table()
        mil = t.put(MILOTIC, P1, 'active')
        t.energy(mil, W, 3)
        b = t.put(self.filler, P2, 'bench')
        self.big(b)
        t.yes = False
        await t.attack(mil, 'Aqua Swirl')
        self.assertIs(t.active(P2), self.opp)
        self.assertEqual(400 - t.hp(self.opp), 60)

    # --- Wiglett (SVI 56): Dig a Little -----------------------------------
    async def test_dig_a_little_heads_mills_opponent_one(self):
        t = self.table()
        wig = t.put(WIGLETT, P1, 'active')
        t.energy(wig, W)
        top = t.zone(P2, 'deck')[-1]
        await t.attack(wig, 'Dig a Little')
        self.assertEqual(len(t.zone(P2, 'discard')), 1)
        self.assertEqual(len(t.zone(P2, 'deck')), 29)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)
        self.assertEqual(t.hp(self.opp), 400)
        self.assertNotIn(top, t.zone(P2, 'deck'))

    async def test_dig_a_little_tails_nothing(self):
        t = self.table()
        wig = t.put(WIGLETT, P1, 'active')
        t.energy(wig, W)
        t.heads = False
        await t.attack(wig, 'Dig a Little')
        self.assertEqual(len(t.zone(P2, 'deck')), 30)
        self.assertEqual(len(t.zone(P2, 'discard')), 0)

    # --- Devolution Spray (EVO 76) ----------------------------------------
    async def _stage2(self, t, zone='active'):
        mud = t.put(MUDKIP, P1, zone)
        marsh = t.put(MARSHTOMP, P1, 'hand')
        await t.play(marsh, targets=[mud.entity_id])
        t.state.entered_play_turn[marsh.entity_id] = 0
        swamp = t.put(SWAMPERT, P1, 'hand')
        await t.play(swamp, targets=[marsh.entity_id])
        return mud, marsh, swamp

    async def test_devolution_spray_removes_only_top_stage_keeps_damage(self):
        t = self.table()
        t.state.turn_number = 5
        mud, marsh, swamp = await self._stage2(t)
        self.assertIs(t.active(P1), swamp)
        swamp.set_attribute(AttrID.HP, 160 - 30)
        swamp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        spray = t.put(SPRAY, P1, 'hand')
        await t.play(spray)
        self.assertIn(swamp, t.zone(P1, 'hand'))
        self.assertIs(t.active(P1), marsh)
        self.assertIn(mud, marsh.children)
        self.assertEqual(t.damage(marsh), 30)
        self.assertEqual(t.conditions(marsh), set())      # devolving clears conditions
        self.assertIn(spray, t.zone(P1, 'discard'))

    async def test_devolution_spray_not_playable_with_only_basics(self):
        t = self.table()
        t.put(MUDKIP, P1, 'active')
        spray = t.put(SPRAY, P1, 'hand')
        self.assertFalse(t.can(spray, 'UseTrainerCard'))

    async def test_devolution_spray_cannot_touch_opponent(self):
        t = self.table()
        t.put(MUDKIP, P1, 'active')
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        omud = t.put(MUDKIP, P2, 'active')
        omarsh = t.put(MARSHTOMP, P2, 'hand')
        spray = t.put(SPRAY, P1, 'hand')
        # Opponent's evolved Pokémon must not make Spray playable.
        t.next_turn()
        await t.play(omarsh, pid=P2, targets=[omud.entity_id])
        t.next_turn()
        self.assertEqual(self.name(t.active(P2)), 'Marshtomp')
        self.assertFalse(t.can(spray, 'UseTrainerCard'))


if __name__ == '__main__':
    unittest.main()
