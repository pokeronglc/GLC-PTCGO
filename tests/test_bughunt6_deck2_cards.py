"""Bug hunt round 6, deck 2 (Metal): Beldum SIT 117, Metang TEF 114,
Bronzor TEU 100, Cufant PAL 149 (vanilla), Copperajah SFA 42, Varoom OBF 154,
Heatran BRS 100, Mela PAR 167, Bravery Charm PAL 173."""
import glob
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

M, R, W = PokemonTypes.METAL, PokemonTypes.FIRE, PokemonTypes.WATER
BELDUM, METANG = 'SWSH12.Beldum_117', 'SV05.Metang_114'
BRONZOR = 'SM9.Bronzor_100'
CUFANT, COPPERAJAH = 'SV2.Cufant_149', 'SV065.Copperajah_42'
VAROOM = 'SV3.Varoom_154'
HEATRAN = 'SWSH9.Heatran_100'
MELA = 'SV4.Mela_167'
CHARM = 'SV2.BraveryCharm_173'
STADIUM = 'SV1.Mesagoza_178'
HOP = 'CZ.Hop_133'


class Deck2Cards(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    @staticmethod
    def neutral(pokemon, hp=400):
        pokemon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        pokemon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        pokemon.set_attribute(AttrID.HP, hp)

    # --- Beldum: Magnetic Lift -------------------------------------------------
    async def test_magnetic_lift_puts_chosen_card_on_top(self):
        t = self.table()
        b = t.put(BELDUM, P1, 'active')
        t.energy(b, W)
        wanted = t.deck(P1, [HOP], top=False)[0]      # buried at the bottom
        t.picks = lambda cards, count, prompt, display: [wanted]
        size = len(t.zone(P1, 'deck'))
        await t.attack(b, 'Magnetic Lift')
        deck = t.zone(P1, 'deck')
        self.assertIs(deck[-1], wanted)
        self.assertEqual(len(deck), size)
        self.assertNotIn(wanted, t.zone(P1, 'hand'))
        self.assertEqual(t.hp(self.opp), 400)

    # --- Metang: Metal Maker ----------------------------------------------------
    async def test_metal_maker_attaches_only_basic_metal_rest_to_bottom(self):
        t = self.table()
        metang = t.put(METANG, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        top4 = t.deck(P1, [t.basic_energy(M), t.basic_energy(R), HOP, t.basic_energy(M)])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['offered'] = list(cards)
            seen['shown'] = len(display or [])
            return list(cards)
        t.picks = picks
        t.pokemon = lambda cands, prompt: bench
        await t.use(metang, 'Metal Maker')
        metals = [top4[0], top4[3]]
        self.assertEqual(sorted(map(id, seen['offered'])), sorted(map(id, metals)))
        self.assertEqual(seen['shown'], 4)
        for e in metals:
            self.assertIn(e, bench.children)
        self.assertNotIn(top4[1], metang.children + bench.children)
        deck = t.zone(P1, 'deck')
        self.assertEqual({id(c) for c in deck[:2]}, {id(top4[1]), id(top4[2])},
                         'the other cards go to the bottom')
        self.assertIsNone(t.ability_offer(metang, 'Metal Maker'), 'once per turn')

    async def test_metal_maker_no_metal_found_all_to_bottom(self):
        t = self.table()
        metang = t.put(METANG, P1, 'active')
        top4 = t.deck(P1, [t.basic_energy(R), HOP, HOP, HOP])
        await t.use(metang, 'Metal Maker')
        self.assertEqual(metang.children, [])
        deck = t.zone(P1, 'deck')
        self.assertEqual({id(c) for c in deck[:4]}, {id(c) for c in top4})

    # --- Bronzor: Evolutionary Advantage ---------------------------------------
    async def test_bronzor_evolves_only_on_second_players_first_turn(self):
        bronzong = sorted(p.split('cards/')[1][:-3].replace('/', '.')
                          for p in glob.glob('spirit/game/scripts/cards/SM9/Bronzong_*.py'))[0]
        for turn, legal in ((1, False), (2, True)):
            with self.subTest(turn=turn):
                t = Table(self)
                t.state.turn_number = turn
                bronzor = t.put(BRONZOR, P1, 'active')
                t.state.entered_play_turn[bronzor.entity_id] = turn
                t.put(self.filler, P2, 'active')
                card = t.put(bronzong, P1, 'hand')
                self.assertEqual(t.can(card, 'EvolvePokemonPlayAbility'), legal)

    async def test_plain_basic_cannot_evolve_turn_two(self):
        # control: Cufant (no Ability) can't evolve on turn 2 the turn it was played
        t = Table(self)
        t.state.turn_number = 2
        cufant = t.put(CUFANT, P1, 'active')
        t.state.entered_play_turn[cufant.entity_id] = 2
        t.put(self.filler, P2, 'active')
        card = t.put(COPPERAJAH, P1, 'hand')
        self.assertFalse(t.can(card, 'EvolvePokemonPlayAbility'))

    # --- Copperajah: Massive Body ----------------------------------------------
    async def test_massive_body_active_blocks_opponent_stadium(self):
        t = Table(self)
        t.put(COPPERAJAH, P1, 'active')
        t.put(self.filler, P2, 'active')
        mine = t.put(STADIUM, P1, 'hand')
        theirs = t.put(STADIUM, P2, 'hand')
        self.assertTrue(t.can(mine, 'DefaultStadiumPlayAbility'), 'own Stadiums are fine')
        t.next_turn()
        self.assertFalse(t.can(theirs, 'DefaultStadiumPlayAbility', pid=P2))

    async def test_massive_body_on_bench_does_nothing(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(COPPERAJAH, P1, 'bench')
        t.put(self.filler, P2, 'active')
        theirs = t.put(STADIUM, P2, 'hand')
        t.next_turn()
        self.assertTrue(t.can(theirs, 'DefaultStadiumPlayAbility', pid=P2))

    # --- Copperajah: Nasal Lariat -----------------------------------------------
    # FIXED (was BUG): Nasal Lariat never offers the optional +100 (always 130 damage).
    async def test_nasal_lariat_extra_damage_locks_next_turn(self):
        t = self.table()
        c = t.put(COPPERAJAH, P1, 'active')
        self.neutral(c, 200)
        t.energy(c, M, 4)
        t.yes = True
        await t.attack(c, 'Nasal Lariat')
        self.assertEqual(400 - t.hp(self.opp), 230)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(c, 'Nasal Lariat'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(c, 'Nasal Lariat'))

    # FIXED (was BUG): Nasal Lariat always locks attacks next turn, even without the +100.
    async def test_nasal_lariat_decline_base_damage_no_lock(self):
        t = self.table()
        c = t.put(COPPERAJAH, P1, 'active')
        self.neutral(c, 200)
        t.energy(c, M, 4)
        t.yes = False
        await t.attack(c, 'Nasal Lariat')
        self.assertEqual(400 - t.hp(self.opp), 130)
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(c, 'Nasal Lariat'))

    # --- Varoom: Spinning Draw ----------------------------------------------------
    async def test_spinning_draw_damage_and_one_card(self):
        t = self.table()
        v = t.put(VAROOM, P1, 'active')
        t.energy(v, M)
        top = t.deck(P1, [HOP])[0]
        await t.attack(v, 'Spinning Draw')
        self.assertEqual(400 - t.hp(self.opp), 10)
        self.assertEqual(t.zone(P1, 'hand'), [top])

    # --- Heatran: Guard Claw / Iron Hammer ---------------------------------------
    async def test_guard_claw_reduces_next_turn_damage_by_30(self):
        t = Table(self)
        h = t.put(HEATRAN, P1, 'active')
        self.neutral(h, 140)
        t.energy(h, M, 2)
        opp = t.put(HEATRAN, P2, 'active')
        self.neutral(opp)
        t.energy(opp, M, 3)
        await t.attack(h, 'Guard Claw')
        self.assertEqual(400 - t.hp(opp), 30)
        t.next_turn()
        await t.attack(opp, 'Iron Hammer', pid=P2)
        self.assertEqual(140 - t.hp(h), 50)

    async def test_guard_claw_expires_after_opponents_turn(self):
        t = Table(self)
        h = t.put(HEATRAN, P1, 'active')
        self.neutral(h, 140)
        t.energy(h, M, 2)
        opp = t.put(HEATRAN, P2, 'active')
        self.neutral(opp)
        t.energy(opp, M, 3)
        await t.attack(h, 'Guard Claw')
        t.next_turn(); t.next_turn(); t.next_turn()
        await t.attack(opp, 'Iron Hammer', pid=P2)
        self.assertEqual(140 - t.hp(h), 80)

    async def test_iron_hammer_fire_bonus(self):
        for fire, dealt in ((True, 160), (False, 80)):
            with self.subTest(fire=fire):
                t = self.table()
                h = t.put(HEATRAN, P1, 'active')
                t.energy(h, M, 2)
                t.energy(h, R if fire else W)
                await t.attack(h, 'Iron Hammer')
                self.assertEqual(400 - t.hp(self.opp), dealt)

    # --- Mela -------------------------------------------------------------------
    def mela_table(self, ko_last_turn):
        t = self.table()
        mine = t.put(self.filler, P1, 'active')
        if ko_last_turn:
            t.state.kos_suffered_last_turn = {P1: [{'archetype_id': mine.archetype_id}]}
        return t, mine

    # FIXED (was BUG): Mela attaches the Fire Energy but never draws up to 6 cards.
    async def test_mela_attaches_fire_from_discard_and_draws_to_six(self):
        t, mine = self.mela_table(True)
        bench = t.put(self.filler, P1, 'bench')
        fire = t.put(t.basic_energy(R), P1, 'discard')
        water = t.put(t.basic_energy(W), P1, 'discard')
        seen = {}

        def picks(cards, count, prompt, display):
            seen['offered'] = list(cards)
            return [fire]
        t.picks = picks
        t.pokemon = lambda cands, prompt: bench
        for _ in range(2):
            t.put(self.item, P1, 'hand')
        card = t.put(MELA, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertIn(fire, bench.children)
        self.assertNotIn(water, seen.get('offered', []))
        self.assertIn(water, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 6)

    async def test_mela_not_playable_without_knockout(self):
        t, _ = self.mela_table(False)
        t.put(t.basic_energy(R), P1, 'discard')
        card = t.put(MELA, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_mela_no_fire_in_discard_draws_nothing(self):
        t, _ = self.mela_table(True)
        t.put(t.basic_energy(W), P1, 'discard')
        card = t.put(MELA, P1, 'hand')
        if not t.can(card, 'UseTrainerCard'):
            return                      # also acceptable: unplayable with no Fire Energy
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 0, '"If you do" - no attach, no draw')

    # --- Bravery Charm ----------------------------------------------------------
    async def test_bravery_charm_basic_gets_50_hp(self):
        t = self.table()
        c = t.put(CUFANT, P1, 'active')
        await t.play(t.put(CHARM, P1, 'hand'), targets=[c.entity_id])
        self.assertEqual(effective_max_hp(t.board, c), 150)
        self.assertEqual(t.hp(c), 150)

    async def test_bravery_charm_stage1_no_bonus(self):
        t = self.table()
        c = t.put(COPPERAJAH, P1, 'active')
        await t.play(t.put(CHARM, P1, 'hand'), targets=[c.entity_id])
        self.assertEqual(effective_max_hp(t.board, c), 200)


if __name__ == '__main__':
    unittest.main()
