"""Bug hunt round 7, chunk 7: Mareep x2, Slowpoke, Hustle Belt, Garbodor x2,
Terrakion x2, Entei, Slowking x2, Applin, Redeemable Ticket, Dudunsparce,
Trubbish -- each card checked against its text, including the cases where it
should NOT work."""
import unittest
from unittest.mock import patch, AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import is_pokemon_card
from spirit.tools.effect_smoke import P1, P2

PSY, WATER, FIRE, FIGHT = (PokemonTypes.PSYCHIC, PokemonTypes.WATER,
                           PokemonTypes.FIRE, PokemonTypes.FIGHTING)
LIGHT, M = PokemonTypes.LIGHTNING, PokemonTypes.METAL

MAREEP_LOT, MAREEP_STS = 'SM8.Mareep_75', 'XY11.Mareep_38'
SLOWPOKE = 'ME5.Slowpoke_29'
HUSTLE_BELT = 'SM7.HustleBelt_134'
GARBODOR_GRI, GARBODOR_LTR = 'SM2.Garbodor_51', 'BW11.Garbodor_68'
TERRAKION_WHT, TERRAKION_SIT = 'RSV10PT5.Terrakion_54', 'SWSH12.Terrakion_97'
ENTEI = 'SV3.Entei_30'
SLOWKING_SCR, SLOWKING_BKP = 'SV07.Slowking_58', 'XY9.Slowking_21'
APPLIN = 'SV06.Applin_126'
TICKET = 'SV09.RedeemableTicket_156'
DUDUNSPARCE = 'SV05.Dudunsparce_129'
TRUBBISH = 'XY9.Trubbish_56'      # BKP 56 (chunk path ME4.Trubbish_56 is a Darkness reprint)
DURALUDON = 'SWSH2.Duraludon_138'   # Power Beam [M][M][C] 110
BRONZOR = 'SV3.Bronzor_144'         # Speed Dive [M][M] 30
SUPPORTER = 'SV1.ProfessorsResearchProfessorSada_189'


class Chunk7(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    @staticmethod
    def neutral(p):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.neutral(self.opp)
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = t.put(spec, P1, zone)
        self.neutral(p)
        if count:
            t.energy(p, kind, count)
        return p

    def swap_opp(self, t, spec):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        self.opp = t.put(spec, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.neutral(self.opp)
        return self.opp

    async def opp_power_beam(self, t, defender):
        """P2 (Duraludon) Power Beams P1's Active; returns damage dealt."""
        att = self.swap_opp(t, DURALUDON)
        t.energy(att, M, 3)
        t.next_turn()
        before = t.hp(defender)
        await t.attack(att, 'Power Beam', pid=P2)
        return before - t.hp(defender)

    # --- Mareep LOT 75: Fluffy Pillow ---------------------------------------
    async def test_fluffy_pillow_active_once_per_turn(self):
        t = self.table()
        mareep = self.mine(t, MAREEP_LOT)
        await t.use(mareep, 'Fluffy Pillow')
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertIsNone(t.ability_offer(mareep, 'Fluffy Pillow'))

    async def test_fluffy_pillow_not_from_bench(self):
        t = self.table()
        self.mine(t, self.filler)
        mareep = self.mine(t, MAREEP_LOT, zone='bench')
        self.assertIsNone(t.ability_offer(mareep, 'Fluffy Pillow'))

    # --- Mareep STS 38: Thunder Wave -----------------------------------------
    async def test_thunder_wave(self):
        for heads in (True, False):
            t = self.table()
            mareep = self.mine(t, MAREEP_STS, WATER, 1)
            t.heads = heads
            await t.attack(mareep, 'Thunder Wave')
            with self.subTest(heads=heads):
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)
                self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Slowpoke PBL 29: All-You-Can-Yeet -----------------------------------
    async def test_all_you_can_yeet_discards_chosen(self):
        t = self.table()
        sp = self.mine(t, SLOWPOKE, PSY, 1)
        hand = [t.put(self.item, P1, 'hand') for _ in range(3)]
        t.picks = lambda cards, count, prompt, display: cards[:2]
        await t.attack(sp, 'All-You-Can-Yeet')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 2)
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_all_you_can_yeet_may_discard_none(self):
        t = self.table()
        sp = self.mine(t, SLOWPOKE, PSY, 1)
        for _ in range(3):
            t.put(self.item, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(sp, 'All-You-Can-Yeet')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 0)

    # --- Hustle Belt CES 134 --------------------------------------------------
    async def test_hustle_belt_boundary(self):
        for remaining, dmg in ((30, 90), (40, 30)):
            t = self.table()
            br = self.mine(t, BRONZOR, M, 2)
            belt = t.put(HUSTLE_BELT, P1, 'hand')
            await t.play(belt, targets=[br.entity_id])
            self.assertIn(belt, br.children)
            br.set_attribute(AttrID.HP, remaining)
            await t.attack(br, 'Speed Dive')
            with self.subTest(remaining=remaining):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Garbodor GRI 51: Trashalanche / Acid Spray --------------------------
    async def test_trashalanche_counts_only_opponents_items(self):
        t = self.table()
        g = self.mine(t, GARBODOR_GRI, PSY, 1)
        for _ in range(3):
            t.put(self.item, P2, 'discard')
        t.put(SUPPORTER, P2, 'discard')
        t.put(self.filler, P2, 'discard')
        for _ in range(4):
            t.put(self.item, P1, 'discard')      # my own Items don't count
        await t.attack(g, 'Trashalanche')
        self.assertEqual(400 - t.hp(self.opp), 60)

    async def test_trashalanche_no_items_no_damage(self):
        t = self.table()
        g = self.mine(t, GARBODOR_GRI, PSY, 1)
        t.put(SUPPORTER, P2, 'discard')
        await t.attack(g, 'Trashalanche')
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_garbodor_acid_spray(self):
        for heads in (True, False):
            t = self.table()
            g = self.mine(t, GARBODOR_GRI, PSY, 3)
            e = t.energy(self.opp, WATER, 1)
            t.heads = heads
            await t.attack(g, 'Acid Spray')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 70)
                self.assertEqual(e in t.zone(P2, 'discard'), heads)
                self.assertEqual(e in self.opp.children, not heads)

    # --- Garbodor LTR 68: Garbotoxin -----------------------------------------
    async def test_garbotoxin_only_with_tool(self):
        t = self.table()
        mareep = self.mine(t, MAREEP_LOT)
        garb = t.put(GARBODOR_LTR, P2, 'bench')
        self.assertIsNotNone(t.ability_offer(mareep, 'Fluffy Pillow'))
        t.attach(HUSTLE_BELT, garb)
        self.assertIsNone(t.ability_offer(mareep, 'Fluffy Pillow'))

    async def test_garbotoxin_locks_owners_abilities_too(self):
        t = self.table()
        mareep = self.mine(t, MAREEP_LOT)
        garb = self.mine(t, GARBODOR_LTR, zone='bench')
        t.attach(HUSTLE_BELT, garb)
        self.assertIsNone(t.ability_offer(mareep, 'Fluffy Pillow'))

    # --- Terrakion WHT 54: Retaliate -----------------------------------------
    async def ko_my_active_on_their_turn(self, t):
        victim = t.put(self.filler, P1, 'active', hp=10)
        att = self.swap_opp(t, BRONZOR)
        t.energy(att, M, 2)
        t.next_turn()
        await t.attack(att, 'Speed Dive', pid=P2)
        assert victim not in t.board.pokemon_in_play(P1), 'setup: victim not KOd'
        t.next_turn()

    async def test_retaliate_after_knockout(self):
        t = self.table()
        terr = self.mine(t, TERRAKION_WHT, FIGHT, 2, zone='bench')
        await self.ko_my_active_on_their_turn(t)
        self.assertIs(t.active(P1), terr)
        await t.attack(terr, 'Retaliate')
        self.assertEqual(400 - t.hp(self.opp), 130)

    async def test_retaliate_knockout_two_turns_ago_does_not_count(self):
        t = self.table()
        terr = self.mine(t, TERRAKION_WHT, FIGHT, 2, zone='bench')
        await self.ko_my_active_on_their_turn(t)
        t.next_turn()      # opponent's turn, no Knock Out
        t.next_turn()
        await t.attack(terr, 'Retaliate')
        self.assertEqual(400 - t.hp(self.opp), 50)

    async def test_retaliate_without_knockout(self):
        t = self.table()
        terr = self.mine(t, TERRAKION_WHT, FIGHT, 2)
        await t.attack(terr, 'Retaliate')
        self.assertEqual(400 - t.hp(self.opp), 50)

    # --- Terrakion SIT 97: Cavern Tackle -------------------------------------
    async def test_cavern_tackle_prevents_damage(self):
        t = self.table()
        terr = self.mine(t, TERRAKION_SIT, FIGHT, 3)
        await t.attack(terr, 'Cavern Tackle')
        self.assertEqual(400 - t.hp(self.opp), 120)
        self.assertEqual(await self.opp_power_beam(t, terr), 0)

    # BUG: "this attack can't be used" is not recognised as a usage restriction, so Cavern Tackle can be used every turn

    async def test_cavern_tackle_cannot_be_used_twice_in_a_row(self):
        t = self.table()
        terr = self.mine(t, TERRAKION_SIT, FIGHT, 3)
        await t.attack(terr, 'Cavern Tackle')
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(terr, 'Cavern Tackle'))

    async def test_cavern_tackle_usable_again_after_a_gap(self):
        t = self.table()
        terr = self.mine(t, TERRAKION_SIT, FIGHT, 3)
        await t.attack(terr, 'Cavern Tackle')
        for _ in range(4):
            t.next_turn()
        self.assertIsNotNone(t.attack_offer(terr, 'Cavern Tackle'))

    async def test_cavern_tackle_protection_expires(self):
        t = self.table()
        terr = self.mine(t, TERRAKION_SIT, FIGHT, 3)
        await t.attack(terr, 'Cavern Tackle')
        t.next_turn()
        t.next_turn()   # my next turn: protection is over
        self.assertEqual(await self.opp_power_beam(t, terr), 110)

    # --- Entei OBF 30: Pressure / Blaze Ball ---------------------------------
    async def test_pressure_active_reduces_20(self):
        t = self.table()
        entei = self.mine(t, ENTEI)
        self.assertEqual(await self.opp_power_beam(t, entei), 90)

    async def test_pressure_not_from_bench(self):
        t = self.table()
        mon = self.mine(t, self.filler)
        mon.set_attribute(AttrID.HP, 400)
        self.mine(t, ENTEI, zone='bench')
        self.assertEqual(await self.opp_power_beam(t, mon), 110)

    async def test_blaze_ball_counts_only_fire(self):
        for fire, other, dmg in ((3, 0, 120), (2, 1, 100)):
            t = self.table()
            entei = self.mine(t, ENTEI, FIRE, fire)
            if other:
                t.energy(entei, WATER, other)
            await t.attack(entei, 'Blaze Ball')
            with self.subTest(fire=fire):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Slowking SCR 58: Seek Inspiration -----------------------------------
    async def test_seek_inspiration_copies_pokemon_attack(self):
        t = self.table()
        sk = self.mine(t, SLOWKING_SCR, PSY, 2)
        top = t.deck(P1, [DURALUDON])[0]
        seen = {}

        async def pick(pid, source, candidates, prompt):
            seen['titles'] = [a.title for _, a in candidates]
            return seen['titles'].index('Power Beam')

        with patch.object(t.session, 'prompt_attack_selection', pick):
            await t.attack(sk, 'Seek Inspiration')
        self.assertIn(top, t.zone(P1, 'discard'))
        self.assertEqual(seen['titles'], ['Metal Sharpener', 'Power Beam'])
        self.assertEqual(400 - t.hp(self.opp), 110)

    async def test_seek_inspiration_non_pokemon_does_nothing(self):
        t = self.table()
        sk = self.mine(t, SLOWKING_SCR, PSY, 2)
        mock = AsyncMock(return_value=0)
        with patch.object(t.session, 'prompt_attack_selection', mock):
            await t.attack(sk, 'Seek Inspiration')
        mock.assert_not_called()
        self.assertEqual(len(t.zone(P1, 'discard')), 1)
        self.assertEqual(len(t.zone(P1, 'deck')), 29)
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- Slowking BKP 21: Royal Flash / Psych Up -----------------------------
    # BUG: Royal Flash is only offered if the Slowking player has a Benched Pokemon ("his or her Benched" resolved to your own Bench)

    async def test_royal_flash_offered_without_own_bench(self):
        t = self.table()
        sk = self.mine(t, SLOWKING_BKP)
        t.put(self.filler, P2, 'bench')
        t.energy(self.opp, WATER, 1)
        self.assertIsNotNone(t.ability_offer(sk, 'Royal Flash'))

    async def test_royal_flash_heads_moves_energy(self):
        t = self.table()
        sk = self.mine(t, SLOWKING_BKP)
        mine = self.mine(t, self.filler, zone='bench')    # works around the bug above
        bench = t.put(self.filler, P2, 'bench')
        e = t.energy(self.opp, WATER, 1)
        t.heads = True
        await t.use(sk, 'Royal Flash')
        self.assertIn(e, bench.children)
        self.assertNotIn(e, self.opp.children)
        self.assertEqual(len(mine.children), 0)
        self.assertIsNone(t.ability_offer(sk, 'Royal Flash'))

    async def test_royal_flash_tails_and_conditions(self):
        t = self.table()
        sk = self.mine(t, SLOWKING_BKP)
        self.mine(t, self.filler, zone='bench')           # works around the bug above
        e = t.energy(self.opp, WATER, 1)
        self.assertIsNone(t.ability_offer(sk, 'Royal Flash'))   # no opposing Bench
        bench = t.put(self.filler, P2, 'bench')
        t.heads = False
        await t.use(sk, 'Royal Flash')
        self.assertIn(e, self.opp.children)
        self.assertNotIn(e, bench.children)
        self.assertIsNone(t.ability_offer(sk, 'Royal Flash'))   # once per turn

    async def test_royal_flash_needs_energy_on_active(self):
        t = self.table()
        sk = self.mine(t, SLOWKING_BKP)
        self.mine(t, self.filler, zone='bench')           # works around the bug above
        b = t.put(self.filler, P2, 'bench')
        t.energy(b, WATER, 1)      # Energy only on the Bench
        self.assertIsNone(t.ability_offer(sk, 'Royal Flash'))

    async def test_psych_up_boost_next_turn_only(self):
        t = self.table()
        sk = self.mine(t, SLOWKING_BKP, WATER, 2)
        await t.attack(sk, 'Psych Up')
        self.assertEqual(400 - t.hp(self.opp), 40)
        t.next_turn(); t.next_turn()
        await t.attack(sk, 'Psych Up')
        self.assertEqual(400 - t.hp(self.opp), 40 + 80)
        t.next_turn(); t.next_turn()
        t.next_turn(); t.next_turn()     # a turn without Psych Up in between
        before = t.hp(self.opp)
        await t.attack(sk, 'Psych Up')
        self.assertEqual(before - t.hp(self.opp), 40)

    # --- Applin TWM 126: Find a Friend ---------------------------------------
    async def test_find_a_friend_searches_pokemon_only(self):
        t = self.table()
        ap = self.mine(t, APPLIN, WATER, 1)
        mon, nrg = t.deck(P1, [BRONZOR, t.basic_energy(WATER)])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'] = cards
            return [c for c in cards if c is mon][:count]
        t.picks = picks
        await t.attack(ap, 'Find a Friend')
        self.assertTrue(all(is_pokemon_card(c) for c in seen['cards']))
        self.assertIn(mon, t.zone(P1, 'hand'))
        self.assertIn(nrg, t.zone(P1, 'deck'))
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_find_a_friend_no_pokemon_in_deck(self):
        t = self.table()
        ap = self.mine(t, APPLIN, WATER, 1)
        await t.attack(ap, 'Find a Friend')
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Redeemable Ticket JTG 156 -------------------------------------------
    async def test_redeemable_ticket_swaps_prizes_with_top_of_deck(self):
        for n in (3, 1):
            t = self.table()
            self.mine(t, self.filler)
            t.set_prizes(P1, 0)
            old = [t.put(BRONZOR, P1, 'prizes') for _ in range(n)]
            top = t.deck(P1, [DURALUDON] * n)
            ticket = t.put(TICKET, P1, 'hand')
            await t.play(ticket)
            prizes = t.zone(P1, 'prizePile')
            deck = t.zone(P1, 'deck')
            with self.subTest(n=n):
                self.assertEqual(len(prizes), n)
                self.assertEqual(set(map(id, prizes)), set(map(id, top)))
                self.assertEqual(set(map(id, deck[:n])), set(map(id, old)))  # bottom
                self.assertEqual(len(deck), 30 + n)
                self.assertIn(ticket, t.zone(P1, 'discard'))

    # --- Dudunsparce TEF 129: Run Away Draw ----------------------------------
    async def test_run_away_draw_from_active(self):
        t = self.table()
        dud = self.mine(t, DUDUNSPARCE, WATER, 2)
        energies = list(dud.children)
        bench = t.put(self.filler, P1, 'bench')
        await t.use(dud, 'Run Away Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        deck = t.zone(P1, 'deck')
        self.assertIn(dud, deck)
        for e in energies:
            self.assertIn(e, deck)
        self.assertEqual(len(deck), 30 - 3 + 3)
        self.assertIs(t.active(P1), bench)

    async def test_run_away_draw_empty_deck_keeps_pokemon(self):
        t = Table(self, filler_deck=0)
        self.opp = t.put(self.filler, P2, 'active')
        t.put(self.filler, P1, 'active')
        dud = self.mine(t, DUDUNSPARCE, zone='bench')
        entry = t.ability_offer(dud, 'Run Away Draw')
        if entry is not None:
            await t.do(entry)
        self.assertIn(dud, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Trubbish BKP 56 (XY9): Acid Spray -----------------------------------
    async def test_trubbish_acid_spray(self):
        for heads in (True, False):
            t = self.table()
            tr = self.mine(t, TRUBBISH, PSY, 1)
            e = t.energy(self.opp, WATER, 1)
            t.heads = heads
            await t.attack(tr, 'Acid Spray')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 10)
                self.assertEqual(e in self.opp.children, not heads)


if __name__ == '__main__':
    unittest.main()
