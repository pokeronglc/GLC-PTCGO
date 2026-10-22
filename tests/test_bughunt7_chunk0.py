"""Bug hunt round 7, chunk 0: Ralts/Kirlia, Natu, Sobble, Deoxys, Bidoof,
Minccino/Cinccino, Frillish -- each attack checked against its text,
including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

PSY, WATER, COL = PokemonTypes.PSYCHIC, PokemonTypes.WATER, PokemonTypes.COLORLESS
FAIRY = PokemonTypes.FAIRY

RALTS_PLS, RALTS_LTR, RALTS_ASR = 'BW8.Ralts_59', 'BW11.Ralts_59', 'SWSH10.Ralts_60'
KIRLIA = 'SM8.Kirlia_140'
NATU_PAR, NATU_PGO = 'SV4.Natu_71', 'PGO.Natu_32'
SOBBLE_CRE, SOBBLE_3, SOBBLE_73 = 'SWSH6.Sobble_41', 'Promo_SWSH.Sobble_3', 'Promo_SWSH.Sobble_73'
DEOXYS_34, DEOXYS_31 = 'ME4.Deoxys_34', 'ME4.Deoxys_31'
BIDOOF = 'XY5.Bidoof_116'
MINCCINO_BLK, MINCCINO_SSH, CINCCINO = 'ZSV10PT5.Minccino_75', 'SWSH1.Minccino_145', 'SV05.Cinccino_137'
FRILLISH = 'XY4.Frillish_20'
SHINX_RS, MIENFOO_RS = 'SWSH5.Shinx_46', 'SWSH5.Mienfoo_76'     # Basic Rapid Strike
THERAPEUTIC, MIST = 'SV2.TherapeuticEnergy_193', 'SV05.MistEnergy_161'


class Chunk0(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind, count, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def filler_attack(self):
        """The filler's first damaging attack: (title, damage)."""
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    async def opp_hits(self, t):
        title, dmg = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        return dmg

    def is_energy_of(self, t, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    # --- Ralts PLS 59: Psy Bolt --------------------------------------------
    async def test_ralts_pls_psy_bolt(self):
        for heads in (True, False):
            t = self.table()
            ralts = self.mine(t, RALTS_PLS, WATER, 1)
            t.heads = heads
            await t.attack(ralts, 'Psy Bolt')
            with self.subTest(heads=heads):
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)
                self.assertEqual((400 - t.hp(self.opp)), 0)

    # --- Ralts (BW11 59, the naive path): Mind Bend ------------------------
    async def test_ralts_ltr_mind_bend(self):
        for heads in (True, False):
            t = self.table()
            ralts = self.mine(t, RALTS_LTR, PSY, 2)
            t.heads = heads
            await t.attack(ralts, 'Mind Bend')
            with self.subTest(heads=heads):
                self.assertEqual(CONFUSED in t.conditions(self.opp), heads)
                self.assertEqual((400 - t.hp(self.opp)), 10)

    # --- Ralts ASR 60: Teleportation Burst ---------------------------------
    async def test_ralts_teleportation_burst_switches(self):
        t = self.table()
        ralts = self.mine(t, RALTS_ASR, PSY, 1)
        bench = t.put(self.filler, P1, 'bench')
        await t.attack(ralts, 'Teleportation Burst')
        self.assertEqual((400 - t.hp(self.opp)), 10)
        self.assertIs(t.active(P1), bench)
        self.assertIn(ralts, t.zone(P1, 'bench'))

    async def test_ralts_teleportation_burst_no_bench_still_damages(self):
        t = self.table()
        ralts = self.mine(t, RALTS_ASR, PSY, 1)
        await t.attack(ralts, 'Teleportation Burst')
        self.assertEqual((400 - t.hp(self.opp)), 10)
        self.assertIs(t.active(P1), ralts)

    # --- Kirlia LOT 140: Disarming Voice -----------------------------------
    async def test_kirlia_disarming_voice(self):
        t = self.table()
        kirlia = self.mine(t, KIRLIA, FAIRY, 3)
        await t.attack(kirlia, 'Disarming Voice')
        self.assertEqual((400 - t.hp(self.opp)), 50)
        self.assertIn(CONFUSED, t.conditions(self.opp))
        self.assertNotIn(CONFUSED, t.conditions(kirlia))

    async def test_kirlia_beat_no_condition(self):
        t = self.table()
        kirlia = self.mine(t, KIRLIA, FAIRY, 3)
        await t.attack(kirlia, 'Beat')
        self.assertEqual((400 - t.hp(self.opp)), 20)
        self.assertEqual(t.conditions(self.opp), set())

    # --- Natu PAR 71: Triple Strike ----------------------------------------
    async def test_natu_triple_strike(self):
        for pattern, expected in (([True] * 3, 30), ([True, False, True], 20), ([False] * 3, 0)):
            t = self.table()
            natu = self.mine(t, NATU_PAR, PSY, 1)
            flips = iter(pattern)
            t.heads = lambda title: next(flips)
            await t.attack(natu, 'Triple Strike')
            with self.subTest(pattern=pattern):
                self.assertEqual((400 - t.hp(self.opp)), expected)

    # --- Natu PGO 32: Nap ----------------------------------------------------
    async def test_natu_nap_heals_20_only(self):
        t = self.table()
        natu = self.mine(t, NATU_PGO, PSY, 1)
        natu.set_attribute(AttrID.HP, 20)            # 30 damage
        await t.attack(natu, 'Nap')
        self.assertEqual(t.damage(natu), 10)
        self.assertEqual((400 - t.hp(self.opp)), 0)

    async def test_natu_nap_does_not_overheal(self):
        t = self.table()
        natu = self.mine(t, NATU_PGO, PSY, 1)
        natu.set_attribute(AttrID.HP, 40)            # 10 damage
        await t.attack(natu, 'Nap')
        self.assertEqual(t.damage(natu), 0)
        self.assertEqual(t.hp(natu), 50)

    # --- Sobble CRE 41: Keep Calling / Double Spin -------------------------
    async def test_sobble_keep_calling_only_basic_rapid_strike(self):
        t = self.table()
        sobble = self.mine(t, SOBBLE_CRE, WATER, 1)
        t.deck(P1, [SHINX_RS, MIENFOO_RS, SOBBLE_CRE, SOBBLE_3, RALTS_ASR])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['names'] = t.names(cards)
            seen['count'] = count
            return cards[:count]
        t.picks = picks
        await t.attack(sobble, 'Keep Calling')
        self.assertEqual(seen['count'], 3)
        self.assertEqual(seen['names'], ['Mienfoo', 'Shinx', 'Sobble'])
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Mienfoo', 'Shinx', 'Sobble'])
        bench_sobble = next(c for c in t.zone(P1, 'bench') if t.names([c]) == ['Sobble'])
        self.assertEqual(def_for(bench_sobble.archetype_id).set_code, 'SWSH6')

    async def test_sobble_keep_calling_respects_bench_space(self):
        t = self.table()
        sobble = self.mine(t, SOBBLE_CRE, WATER, 1)
        for _ in range(4):
            t.put(self.filler, P1, 'bench')
        t.deck(P1, [SHINX_RS, MIENFOO_RS, SOBBLE_CRE])
        await t.attack(sobble, 'Keep Calling')
        self.assertEqual(len(t.zone(P1, 'bench')), 5)

    async def test_sobble_double_spin(self):
        for heads, expected in ((True, 40), (False, 0)):
            t = self.table()
            sobble = self.mine(t, SOBBLE_CRE, WATER, 2)
            t.heads = heads
            await t.attack(sobble, 'Double Spin')
            with self.subTest(heads=heads):
                self.assertEqual((400 - t.hp(self.opp)), expected)

    # --- Sobble SWSH003: Bind ------------------------------------------------
    async def test_sobble_bind(self):
        for heads in (True, False):
            t = self.table()
            sobble = self.mine(t, SOBBLE_3, WATER, 2)
            t.heads = heads
            await t.attack(sobble, 'Bind')
            with self.subTest(heads=heads):
                self.assertEqual((400 - t.hp(self.opp)), 20)
                self.assertEqual(PARALYZED in t.conditions(self.opp), heads)

    # --- Sobble SWSH073: Growl ----------------------------------------------
    async def test_sobble_growl_reduces_defending_attack(self):
        t = self.table()
        sobble = self.mine(t, SOBBLE_73, WATER, 1)
        sobble.set_attribute(AttrID.HP, 300)
        await t.attack(sobble, 'Growl')
        self.assertEqual((400 - t.hp(self.opp)), 0)
        dmg = await self.opp_hits(t)
        self.assertEqual(300 - t.hp(sobble), max(dmg - 20, 0))

    async def test_sobble_growl_expires_after_opponents_turn(self):
        t = self.table()
        sobble = self.mine(t, SOBBLE_73, WATER, 1)
        sobble.set_attribute(AttrID.HP, 300)
        await t.attack(sobble, 'Growl')
        t.next_turn()          # opponent's turn passes without attacking
        t.next_turn()          # my turn
        dmg = await self.opp_hits(t)
        self.assertEqual(300 - t.hp(sobble), dmg)

    async def test_sobble_growl_only_the_defending_pokemon(self):
        t = self.table()
        sobble = self.mine(t, SOBBLE_73, WATER, 1)
        sobble.set_attribute(AttrID.HP, 300)
        await t.attack(sobble, 'Growl')
        # opponent switches in a fresh Pokémon, which is not affected
        first = self.opp
        fresh = t.put(self.filler, P2, 'bench')
        fresh.set_attribute(AttrID.HP, 400)
        t.board.move_card(first.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(fresh.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        self.opp = fresh
        dmg = await self.opp_hits(t)
        self.assertEqual(300 - t.hp(sobble), dmg)

    # --- Deoxys CRI 34: Psyspeed ----------------------------------------------
    async def test_deoxys_psyspeed_draws_to_five(self):
        t = self.table()
        deoxys = self.mine(t, DEOXYS_34, PSY, 1)
        t.put(self.item, P1, 'hand')
        t.put(self.item, P1, 'hand')
        await t.attack(deoxys, 'Psyspeed')
        self.assertEqual((400 - t.hp(self.opp)), 30)
        self.assertEqual(len(t.zone(P1, 'hand')), 5)

    async def test_deoxys_psyspeed_may_decline_and_full_hand(self):
        t = self.table()
        deoxys = self.mine(t, DEOXYS_34, PSY, 1)
        t.put(self.item, P1, 'hand')
        t.yes = False
        await t.attack(deoxys, 'Psyspeed')
        self.assertEqual((400 - t.hp(self.opp)), 30)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        # 6 cards already: draws nothing
        t2 = self.table()
        deoxys2 = self.mine(t2, DEOXYS_34, PSY, 1)
        for _ in range(6):
            t2.put(self.item, P1, 'hand')
        await t2.attack(deoxys2, 'Psyspeed')
        self.assertEqual(len(t2.zone(P1, 'hand')), 6)

    # --- Deoxys CRI 31: Genome Charge / Psychic -------------------------------
    async def test_deoxys_genome_charge_only_basic_psychic(self):
        t = self.table()
        deoxys = self.mine(t, DEOXYS_31, WATER, 1)
        t.deck(P1, [t.basic_energy(PSY), t.basic_energy(WATER), t.basic_energy(PSY),
                    t.basic_energy(PSY)])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['ok'] = all(self.is_energy_of(t, c, PSY) for c in cards)
            seen['count'] = count
            return cards[:count]
        t.picks = picks
        await t.attack(deoxys, 'Genome Charge')
        self.assertTrue(seen.get('ok'))
        self.assertEqual(seen['count'], 2)
        attached = t.board.attached_energies(deoxys)
        self.assertEqual(sum(self.is_energy_of(t, c, PSY) for c in attached), 2)
        self.assertEqual(len(attached), 3)
        self.assertEqual((400 - t.hp(self.opp)), 0)

    async def test_deoxys_genome_charge_empty_deck_search(self):
        t = self.table()
        deoxys = self.mine(t, DEOXYS_31, WATER, 1)
        t.deck(P1, [t.basic_energy(WATER)])
        await t.attack(deoxys, 'Genome Charge')
        self.assertEqual(len(t.board.attached_energies(deoxys)), 1)

    async def test_deoxys_psychic_counts_opponent_energy(self):
        for opp_energy, expected in ((0, 80), (3, 140)):
            t = self.table()
            deoxys = self.mine(t, DEOXYS_31, PSY, 3)
            if opp_energy:
                t.energy(self.opp, WATER, opp_energy)
            await t.attack(deoxys, 'Psychic')
            with self.subTest(opp_energy=opp_energy):
                self.assertEqual((400 - t.hp(self.opp)), expected)

    async def test_deoxys_psychic_ignores_own_and_bench_energy(self):
        t = self.table()
        deoxys = self.mine(t, DEOXYS_31, PSY, 3)
        t.energy(deoxys, PSY, 2)
        bench = t.put(self.filler, P2, 'bench')
        t.energy(bench, WATER, 2)
        await t.attack(deoxys, 'Psychic')
        self.assertEqual((400 - t.hp(self.opp)), 80)

    # --- Bidoof PRC 116: Scrunch ---------------------------------------------
    async def test_bidoof_scrunch_heads_prevents_damage(self):
        t = self.table()
        bidoof = self.mine(t, BIDOOF, WATER, 2)
        bidoof.set_attribute(AttrID.HP, 300)
        t.heads = True
        await t.attack(bidoof, 'Scrunch')
        self.assertEqual((400 - t.hp(self.opp)), 0)
        await self.opp_hits(t)
        self.assertEqual(t.hp(bidoof), 300)

    async def test_bidoof_scrunch_tails_no_protection(self):
        t = self.table()
        bidoof = self.mine(t, BIDOOF, WATER, 2)
        bidoof.set_attribute(AttrID.HP, 300)
        t.heads = False
        await t.attack(bidoof, 'Scrunch')
        dmg = await self.opp_hits(t)
        self.assertEqual(300 - t.hp(bidoof), dmg)

    async def test_bidoof_scrunch_expires(self):
        t = self.table()
        bidoof = self.mine(t, BIDOOF, WATER, 2)
        bidoof.set_attribute(AttrID.HP, 300)
        t.heads = True
        await t.attack(bidoof, 'Scrunch')
        t.next_turn(); t.next_turn()
        dmg = await self.opp_hits(t)
        self.assertEqual(300 - t.hp(bidoof), dmg)

    # --- Minccino BLK 75: Tail Slap -------------------------------------------
    async def test_minccino_blk_tail_slap(self):
        for pattern, expected in (([True, True], 40), ([True, False], 20), ([False, False], 0)):
            t = self.table()
            m = self.mine(t, MINCCINO_BLK, WATER, 1)
            flips = iter(pattern)
            t.heads = lambda title: next(flips)
            await t.attack(m, 'Tail Slap')
            with self.subTest(pattern=pattern):
                self.assertEqual((400 - t.hp(self.opp)), expected)

    # --- Minccino SSH 145: Glance / Tail Slap -----------------------------------
    async def test_minccino_glance_shows_opponents_top_card(self):
        t = self.table()
        m = self.mine(t, MINCCINO_SSH, WATER, 1)
        top = t.deck(P2, [self.filler])[0]
        shown = []

        async def present(ctx, card, prompt, buttons, player_id=None):
            shown.append((card, player_id or ctx.player_id))
            return 0
        deck_before = list(t.zone(P2, 'deck'))
        with patch.object(EffectContext, 'present_card_choice', present):
            await t.attack(m, 'Glance')
        self.assertEqual(len(shown), 1)
        self.assertEqual(shown[0][1], P1)
        self.assertIs(shown[0][0], top)
        self.assertEqual(list(t.zone(P2, 'deck')), deck_before)   # nothing moved
        self.assertEqual((400 - t.hp(self.opp)), 0)

    async def test_minccino_ssh_tail_slap(self):
        t = self.table()
        m = self.mine(t, MINCCINO_SSH, WATER, 2)
        flips = iter([False, True])
        t.heads = lambda title: next(flips)
        await t.attack(m, 'Tail Slap')
        self.assertEqual((400 - t.hp(self.opp)), 20)

    # --- Cinccino TEF 137: Special Roll ------------------------------------------
    async def test_cinccino_special_roll_counts_special_energy(self):
        t = self.table()
        c = self.mine(t, CINCCINO, WATER, 1)
        t.attach(THERAPEUTIC, c)
        t.attach(MIST, c)
        await t.attack(c, 'Special Roll')
        self.assertEqual((400 - t.hp(self.opp)), 140)

    async def test_cinccino_special_roll_basic_energy_does_nothing(self):
        t = self.table()
        c = self.mine(t, CINCCINO, WATER, 3)
        await t.attack(c, 'Special Roll')
        self.assertEqual((400 - t.hp(self.opp)), 0)

    # --- Frillish PHF 20: Confuse Ray ---------------------------------------------
    async def test_frillish_confuse_ray(self):
        t = self.table()
        f = self.mine(t, FRILLISH, WATER, 1)
        bench = t.put(self.filler, P2, 'bench')
        await t.attack(f, 'Confuse Ray')
        self.assertIn(CONFUSED, t.conditions(self.opp))
        self.assertEqual(t.conditions(bench), set())
        self.assertEqual((400 - t.hp(self.opp)), 0)


if __name__ == '__main__':
    unittest.main()
