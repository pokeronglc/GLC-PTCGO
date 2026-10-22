"""Bug hunt round 4, deck 4: Water deck cards checked against their printed
text, including the cases where they should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, R = PokemonTypes.WATER, PokemonTypes.FIRE
MUDKIP, MARSHTOMP, SWAMPERT = 'SM7.Mudkip_33', 'SM7.Marshtomp_34', 'SM7.Swampert_35'
SNORUNT, FROSLASS = 'ME2PT5.Snorunt_46', 'SV06.Froslass_53'
SOBBLE, INTELEON = 'ME1.Sobble_39', 'SWSH6.Inteleon_43'
SNOM, FROSMOTH = 'ME1.Snom_42', 'ME1.Frosmoth_43'
PALAFIN, CRYOGONAL = 'SV3.Palafin_62', 'ZSV10PT5.Cryogonal_27'
CYNTHIA, ROSA = 'SM5.Cynthia_119', 'SM12.Rosa_204'
SWITCH = 'SV1.Switch_194'


class Bughunt4Deck4(unittest.IsolatedAsyncioTestCase):
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

    def bench_big(self, t, pid, spec=None):
        mon = t.put(spec or self.filler, pid, 'bench')
        self.big(mon)
        return mon

    @staticmethod
    def lost(p, hp=400):
        return hp - p.get_attribute(AttrID.HP, 0)

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def sanity(self):
        for path, code in ((MUDKIP, 'SM7'), (MARSHTOMP, 'SM7'), (SWAMPERT, 'SM7'),
                           (SNORUNT, 'ME2PT5'), (FROSLASS, 'SV06'), (SOBBLE, 'ME1'),
                           (INTELEON, 'SWSH6'), (SNOM, 'ME1'), (FROSMOTH, 'ME1'),
                           (PALAFIN, 'SV3'), (CRYOGONAL, 'ZSV10PT5'), (CYNTHIA, 'SM5'),
                           (ROSA, 'SM12')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    async def test_set_codes(self):
        self.sanity()

    # --- Marshtomp (CES 34): Muddy Water -----------------------------------
    async def test_muddy_water_hits_bench_only(self):
        t = self.table()
        m = t.put(MARSHTOMP, P1, 'active')
        t.energy(m, W, 2)
        b = self.bench_big(t, P2)
        mine = t.put(self.filler, P1, 'bench')
        await t.attack(m, 'Muddy Water')
        self.assertEqual(self.lost(b), 20)
        # RULING?: the engine also deals the printed 20 to the Active (damage
        # column = 20); the text says only "does 20 damage to 1 of your
        # opponent's Benched Pokemon" (no "also"). Not asserted here.
        self.assertEqual(t.damage(mine), 0)

    # --- Swampert (CES 35): Power Draw / Hydro Pump ------------------------
    async def test_power_draw_discard_one_draw_three_once(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sw = t.put(SWAMPERT, P1, 'bench')
        junk = t.put(self.filler, P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.use(sw, 'Power Draw')
        self.assertIn(junk, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1 + 3)
        self.assertEqual(len(t.zone(P1, 'deck')), 27)
        self.assertIsNone(t.ability_offer(sw, 'Power Draw'))

    async def test_power_draw_needs_a_card_to_discard(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        sw = t.put(SWAMPERT, P1, 'bench')
        if t.ability_offer(sw, 'Power Draw'):
            await t.use(sw, 'Power Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    async def test_hydro_pump_counts_only_water_energy(self):
        t = self.table()
        sw = t.put(SWAMPERT, P1, 'active')
        t.energy(sw, W, 2)
        t.energy(sw, R, 1)
        await t.attack(sw, 'Hydro Pump')
        self.assertEqual(self.lost(self.opp), 80 + 2 * 20)

    # --- Froslass (TWM 53): Freezing Shroud --------------------------------
    async def test_freezing_shroud_hits_ability_pokemon_both_sides_not_froslass(self):
        t = self.table()
        fro = t.put(FROSLASS, P1, 'bench')                # works from the Bench
        t.put(self.filler, P1, 'active')
        sw = t.put(SWAMPERT, P1, 'bench')                 # has an Ability
        plain = t.put(MARSHTOMP, P1, 'bench')             # no Ability
        opp_int = t.put(INTELEON, P2, 'bench')            # opponent's Ability Pokémon
        await t.checkup()
        self.assertEqual(t.damage(sw), 10)
        self.assertEqual(t.damage(opp_int), 10)
        self.assertEqual(t.damage(plain), 0)
        self.assertEqual(t.damage(fro), 0)
        self.assertEqual(self.lost(self.opp), 0)

    async def test_freezing_shroud_two_froslass_stack(self):
        t = self.table()
        t.put(FROSLASS, P1, 'active')
        t.put(FROSLASS, P2, 'bench')
        sw = t.put(SWAMPERT, P1, 'bench')
        await t.checkup()
        self.assertEqual(t.damage(sw), 20)

    # --- Inteleon (CRE 43): Quick Shooting ---------------------------------
    async def test_quick_shooting_two_counters_on_benched_once_per_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        inte = t.put(INTELEON, P1, 'bench')
        b = self.bench_big(t, P2)
        t.pokemon = lambda c, p: b
        await t.use(inte, 'Quick Shooting')
        self.assertEqual(self.lost(b), 20)
        self.assertEqual(self.lost(self.opp), 0)
        self.assertIsNone(t.ability_offer(inte, 'Quick Shooting'))

    async def test_quick_shooting_cannot_target_my_pokemon(self):
        t = self.table()
        mine = t.put(self.filler, P1, 'active')
        inte = t.put(INTELEON, P1, 'bench')
        seen = []
        t.pokemon = lambda c, p: (seen.extend(c), c[0])[1]
        await t.use(inte, 'Quick Shooting')
        self.assertNotIn(mine, seen)
        self.assertNotIn(inte, seen)
        self.assertEqual(t.damage(mine), 0)

    # --- Sobble (MEG 39): Surprise Attack ----------------------------------
    async def test_surprise_attack_heads_and_tails(self):
        t = self.table()
        s = t.put(SOBBLE, P1, 'active')
        t.energy(s, W)
        t.heads = False
        await t.attack(s, 'Surprise Attack')
        self.assertEqual(self.lost(self.opp), 0)
        t2 = self.table()
        s2 = t2.put(SOBBLE, P1, 'active')
        t2.energy(s2, W)
        await t2.attack(s2, 'Surprise Attack')
        self.assertEqual(self.lost(self.opp), 30)

    # --- Snom (MEG 42): Hide ----------------------------------------------
    async def _hide(self, heads):
        t = self.table()
        snom = t.put(SNOM, P1, 'active')
        t.energy(snom, W)
        t.heads = heads
        await t.attack(snom, 'Hide')
        t.next_turn()
        old = t.active(P2)
        mud = t.put(MUDKIP, P2, 'bench')
        t.board.move_card(old.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(mud.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        t.energy(mud, W)
        await t.attack(mud, 'Tackle', pid=P2)
        return t, snom

    async def test_hide_heads_prevents_damage(self):
        t, snom = await self._hide(True)
        self.assertEqual(t.damage(snom), 0)

    async def test_hide_tails_no_protection(self):
        t, snom = await self._hide(False)
        self.assertEqual(t.damage(snom), 10)                # Mudkip Tackle; Snom is weak to Metal, not Water

    # --- Frosmoth (MEG 43): Chilling Wings --------------------------------
    async def test_chilling_wings_spreads_and_sleeps(self):
        t = self.table()
        fm = t.put(FROSMOTH, P1, 'active')
        t.energy(fm, W)
        b = self.bench_big(t, P2)
        mine = t.put(self.filler, P1, 'bench')
        await t.attack(fm, 'Chilling Wings')
        self.assertEqual(self.lost(self.opp), 20)
        self.assertEqual(self.lost(b), 20)
        self.assertEqual(t.damage(mine), 0)
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertNotIn(ASLEEP, t.conditions(b))

    # --- Palafin (OBF 62): Jet Punch / Justice Kick -----------------------
    async def test_jet_punch_active_and_one_bench(self):
        t = self.table()
        p = t.put(PALAFIN, P1, 'active')
        t.energy(p, W)
        b1, b2 = self.bench_big(t, P2), self.bench_big(t, P2)
        t.picks = lambda cards, n, pr, d: [b2] if b2 in cards else cards[:n]
        await t.attack(p, 'Jet Punch')
        self.assertEqual(self.lost(self.opp), 30)
        self.assertEqual(self.lost(b2), 30)
        self.assertEqual(self.lost(b1), 0)

    async def test_justice_kick_after_switching_in(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        p = t.put(PALAFIN, P1, 'bench')
        t.energy(p, W, 2)
        sw = t.put(SWITCH, P1, 'hand')
        t.pokemon = lambda c, pr: p
        await t.play(sw)
        self.assertIs(t.active(P1), p)
        self.assertEqual(t.state.became_active_turn.get(p.entity_id), t.state.turn_number)
        await t.attack(p, 'Justice Kick')
        self.assertEqual(self.lost(self.opp), 210)

    # Was a bug (fixed Oct 10): Justice Kick ignored its Bench->Active condition
    async def test_justice_kick_does_nothing_if_already_active(self):
        t = self.table()
        p = t.put(PALAFIN, P1, 'active')
        t.energy(p, W, 2)
        if t.attack_offer(p, 'Justice Kick'):
            await t.attack(p, 'Justice Kick')
        self.assertEqual(self.lost(self.opp), 0)

    # Was a bug (fixed Oct 10): Justice Kick ignored its Bench->Active condition
    async def test_justice_kick_last_turn_move_does_not_count(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        p = t.put(PALAFIN, P1, 'bench')
        t.energy(p, W, 2)
        sw = t.put(SWITCH, P1, 'hand')
        t.pokemon = lambda c, pr: p
        await t.play(sw)
        t.next_turn()
        t.next_turn()
        if t.attack_offer(p, 'Justice Kick'):
            await t.attack(p, 'Justice Kick')
        self.assertEqual(self.lost(self.opp), 0)

    # --- Cryogonal (BLK 27): Drag Off ---------------------------------------
    async def test_drag_off_gusts_then_hits_new_active(self):
        t = self.table()
        c = t.put(CRYOGONAL, P1, 'active')
        t.energy(c, W)
        b = self.bench_big(t, P2)
        t.pokemon = lambda cand, pr: b
        await t.attack(c, 'Drag Off')
        self.assertIs(t.active(P2), b)
        self.assertEqual(self.lost(b), 20)
        self.assertEqual(self.lost(self.opp), 0)
        self.assertIn(self.opp, t.zone(P2, 'bench'))

    # --- Cynthia (UPR 119) --------------------------------------------------
    async def test_cynthia_shuffles_hand_and_draws_six(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        cyn = t.put(CYNTHIA, P1, 'hand')
        keep = [t.put(MUDKIP, P1, 'hand') for _ in range(3)]
        await t.play(cyn)
        self.assertIn(cyn, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        self.assertEqual(len(t.zone(P1, 'deck')), 30 + 3 - 6)
        deck_or_hand = t.zone(P1, 'deck') + t.zone(P1, 'hand')
        for k in keep:
            self.assertIn(k, deck_or_hand)

    async def test_cynthia_only_one_supporter_per_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        a = t.put(CYNTHIA, P1, 'hand')
        await t.play(a)
        b = t.put(CYNTHIA, P1, 'hand')
        self.assertFalse(t.can(b, 'UseTrainerCard'))

    # --- Rosa (CEC 204) -----------------------------------------------------
    async def _ko_my_pokemon_on_opp_turn(self, t):
        victim = t.put(self.filler, P1, 'active', hp=10)
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        old = t.active(P2)
        mud = t.put(MUDKIP, P2, 'bench')
        t.board.move_card(old.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(mud.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        t.energy(mud, W)
        await t.attack(mud, 'Tackle', pid=P2)
        self.assertIn(victim, t.zone(P1, 'discard'))
        t.next_turn()

    async def test_rosa_after_ko_searches_pokemon_trainer_basic_energy(self):
        t = self.table()
        await self._ko_my_pokemon_on_opp_turn(t)
        if t.active(P1) is None:
            t.board.move_card(t.zone(P1, 'bench')[0].entity_id,
                              t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        rosa = t.put(ROSA, P1, 'hand')
        mon = t.deck(P1, [MUDKIP])[0]
        en = t.put(t.basic_energy(W), P1, 'deck')
        self.assertTrue(t.can(rosa, 'UseTrainerCard'))

        async def groups(pid, src, specs, prompt, **k):
            return [[s['cards'][0].entity_id] if s['cards'] else [] for s in specs]
        with patch.object(t.session, 'prompt_card_chooser_groups', groups, create=True):
            await t.play(rosa)
        hand = t.zone(P1, 'hand')
        self.assertIn(mon, hand)
        self.assertIn(en, hand)
        self.assertEqual(len(hand), 3)

    async def test_rosa_not_playable_without_ko(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        rosa = t.put(ROSA, P1, 'hand')
        self.assertFalse(t.can(rosa, 'UseTrainerCard'))

    async def test_rosa_not_playable_after_ko_on_my_own_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        # my own Pokémon was KO'd during MY previous turn (not the opponent's)
        t.state.kos_suffered[P1] = [{'archetype_id': self.filler.guid}]
        t.next_turn()
        t.next_turn()
        rosa = t.put(ROSA, P1, 'hand')
        self.assertFalse(t.can(rosa, 'UseTrainerCard'))


if __name__ == '__main__':
    unittest.main()
