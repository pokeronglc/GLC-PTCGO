"""Bug hunt, deck 2 (Psychic): every Pokémon, checked against its text,
including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

P, D, G = PokemonTypes.PSYCHIC, PokemonTypes.DARKNESS, PokemonTypes.GRASS
RALTS, KIRLIA, GARDEVOIR = 'ME2PT5.Ralts_87', 'SWSH12.Kirlia_68', 'BW4.Gardevoir_57'
NATU, XATU = 'SWSH2.Natu_76', 'SV045.Xatu_26'
ABRA, KADABRA, ALAKAZAM = 'ME1.Abra_54', 'ME1.Kadabra_55', 'ME1.Alakazam_56'
INKAY, MALAMAR = 'SM6.Inkay_50', 'SM6.Malamar_51'
GIRATINA, DEOXYS, MEW = 'SM8.Giratina_97', 'ME4.Deoxys_32', 'CEL25.Mew_11'
MUNKIDORI, BLACEPHALON = 'SV085.Munkidori_44', 'Promo_SM.Blacephalon_221'
GOLBAT = 'SWSH5.Golbat_90'          # a non-Psychic Pokémon with a [C][C] attack
GUZMA = 'SM3.Guzma_115'


class Deck2Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def hand(self, t, pid=P1):
        return len(t.zone(pid, 'hand'))

    # --- Ralts: Collect / Natu: Me First ------------------------------------
    async def test_ralts_collect_and_natu_me_first_draw_one(self):
        for spec, title in ((RALTS, 'Collect'), (NATU, 'Me First')):
            t = self.table()
            mon = t.put(spec, P1, 'active')
            t.energy(mon, P)
            await t.attack(mon, title)
            with self.subTest(card=spec):
                self.assertEqual(self.hand(t), 1)
                self.assertEqual(t.hp(self.opp), 400)

    # --- Kirlia: Refinement -------------------------------------------------
    async def test_kirlia_refinement_discard_one_draw_two_once(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        kirlia = t.put(KIRLIA, P1, 'bench')
        t.put(self.item, P1, 'hand')
        await t.use(kirlia, 'Refinement')
        self.assertEqual(len(t.zone(P1, 'discard')), 1)
        self.assertEqual(self.hand(t), 2)
        self.assertIsNone(t.ability_offer(kirlia, 'Refinement'))

    async def test_kirlia_refinement_needs_card_to_discard(self):
        t = self.table()
        kirlia = t.put(KIRLIA, P1, 'active')
        self.assertIsNone(t.ability_offer(kirlia, 'Refinement'))

    # --- Gardevoir: Psychic Mirage / Mind Shock ----------------------------
    async def test_psychic_mirage_doubles_basic_psychic_on_psychic_pokemon(self):
        # Deoxys's Psyspear costs [P][P][P]; 2 basic Psychic only pay it with Mirage.
        for with_gardevoir in (False, True):
            t = self.table()
            deoxys = t.put(DEOXYS, P1, 'active')
            t.energy(deoxys, P, 2)
            if with_gardevoir:
                t.put(GARDEVOIR, P1, 'bench')
            with self.subTest(gardevoir=with_gardevoir):
                self.assertEqual(t.attack_offer(deoxys, 'Psyspear') is not None, with_gardevoir)

    async def test_psychic_mirage_does_not_stack(self):
        # 1 basic Psychic + 2 Gardevoir = [P][P], not [P][P][P].
        t = self.table()
        deoxys = t.put(DEOXYS, P1, 'active')
        t.energy(deoxys, P, 1)
        t.put(GARDEVOIR, P1, 'bench')
        t.put(GARDEVOIR, P1, 'bench')
        self.assertIsNone(t.attack_offer(deoxys, 'Psyspear'))

    async def test_psychic_mirage_not_for_non_psychic_pokemon(self):
        # Golbat (Darkness) Air Slash [C][C]: 1 basic Psychic stays 1 Energy.
        t = self.table()
        golbat = t.put(GOLBAT, P1, 'active')
        t.energy(golbat, P, 1)
        t.put(GARDEVOIR, P1, 'bench')
        self.assertIsNone(t.attack_offer(golbat, 'Air Slash'))

    async def test_mind_shock_ignores_weakness_and_resistance(self):
        for attr in (AttrID.WEAKNESS_TYPES, AttrID.RESISTANCE_TYPES):
            t = self.table()
            self.opp.set_attribute(attr, [P.value])
            gard = t.put(GARDEVOIR, P1, 'active')
            t.energy(gard, P, 4)
            await t.attack(gard, 'Mind Shock')
            with self.subTest(attr=attr):
                self.assertEqual(400 - t.hp(self.opp), 60)

    # --- Xatu: Clairvoyant Sense ---------------------------------------------
    async def test_clairvoyant_sense_attach_to_bench_and_draw_two(self):
        t = self.table()
        xatu = t.put(XATU, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        energy = t.put(t.basic_energy(P), P1, 'hand')
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.use(xatu, 'Clairvoyant Sense')
        self.assertIn(energy, bench.children)
        self.assertEqual(self.hand(t), 2)
        self.assertIsNone(t.ability_offer(xatu, 'Clairvoyant Sense'))

    async def test_clairvoyant_sense_no_psychic_energy_no_draw(self):
        t = self.table()
        xatu = t.put(XATU, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        grass = t.put(t.basic_energy(G), P1, 'hand')
        entry = t.ability_offer(xatu, 'Clairvoyant Sense')
        if entry is not None:
            await t.do(entry)
        self.assertNotIn(grass, bench.children)
        self.assertEqual(self.hand(t), 1)

    async def test_clairvoyant_sense_not_to_active(self):
        t = self.table()
        xatu = t.put(XATU, P1, 'active')
        energy = t.put(t.basic_energy(P), P1, 'hand')
        offered = []
        t.pokemon = lambda c, p: (offered.extend(c), c[0])[1]
        entry = t.ability_offer(xatu, 'Clairvoyant Sense')
        if entry is not None:
            await t.do(entry)
        self.assertNotIn(energy, xatu.children)
        self.assertNotIn(xatu, offered)

    # --- Abra: Teleportation Attack -----------------------------------------
    async def test_abra_teleportation_attack_switches(self):
        t = self.table()
        abra = t.put(ABRA, P1, 'active')
        t.energy(abra, P)
        bench = t.put(self.filler, P1, 'bench')
        await t.attack(abra, 'Teleportation Attack')
        self.assertEqual(400 - t.hp(self.opp), 10)
        self.assertIs(t.active(P1), bench)

    # --- Kadabra / Alakazam: Psychic Draw ----------------------------------
    async def test_psychic_draw_on_evolve_from_hand(self):
        for base, evo, drawn in ((ABRA, KADABRA, 2), (KADABRA, ALAKAZAM, 3)):
            t = self.table()
            t.put(self.filler, P1, 'active')
            lower = t.put(base, P1, 'bench')
            card = t.put(evo, P1, 'hand')
            await t.play(card, targets=[lower.entity_id])
            with self.subTest(card=evo):
                self.assertEqual(self.hand(t), drawn)

    async def test_psychic_draw_optional(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        abra = t.put(ABRA, P1, 'bench')
        t.yes = False
        await t.play(t.put(KADABRA, P1, 'hand'), targets=[abra.entity_id])
        self.assertEqual(self.hand(t), 0)

    async def test_alakazam_powerful_hand_two_counters_per_card(self):
        for cards in (0, 3):
            t = self.table()
            ala = t.put(ALAKAZAM, P1, 'active')
            t.energy(ala, P)
            for _ in range(cards):
                t.put(self.item, P1, 'hand')
            self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [P.value])  # counters ignore Weakness
            await t.attack(ala, 'Powerful Hand')
            with self.subTest(cards=cards):
                self.assertEqual(400 - t.hp(self.opp), 20 * cards)

    # --- Inkay (FLI): Hypnosis ----------------------------------------------
    async def test_inkay_hypnosis(self):
        t = self.table()
        inkay = t.put(INKAY, P1, 'active')
        t.energy(inkay, P)
        await t.attack(inkay, 'Hypnosis')
        self.assertIn(ASLEEP, t.conditions(self.opp))

    # --- Malamar (FLI): Psychic Recharge ------------------------------------
    async def test_psychic_recharge_discard_to_bench_once(self):
        t = self.table()
        mal = t.put(MALAMAR, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        energy = t.put(t.basic_energy(P), P1, 'discard')
        t.put(t.basic_energy(P), P1, 'discard')
        offered = []
        t.pokemon = lambda c, p: (offered.extend(c), bench if bench in c else c[0])[1]
        await t.use(mal, 'Psychic Recharge')
        self.assertEqual(len(t.board.attached_energies(bench)), 1)
        self.assertNotIn(mal, offered)                       # Benched only
        self.assertEqual(len(t.board.attached_energies(mal)), 0)
        self.assertIsNone(t.ability_offer(mal, 'Psychic Recharge'))

    async def test_psychic_recharge_only_psychic_energy(self):
        t = self.table()
        mal = t.put(MALAMAR, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.put(t.basic_energy(G), P1, 'discard')
        entry = t.ability_offer(mal, 'Psychic Recharge')
        if entry is not None:
            await t.do(entry)
        self.assertEqual(len(t.board.attached_energies(bench)), 0)

    # --- Giratina: Distortion Door / Shadow Impact ------------------------
    async def test_distortion_door_from_discard(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        gira = t.put(GIRATINA, P1, 'discard')
        b1, b2, b3 = (t.put(self.filler, P2, 'bench') for _ in range(3))
        t.picks = lambda cards, count, prompt, display: [b1, b3]
        await t.use(gira, 'Distortion Door')
        self.assertIn(gira, t.zone(P1, 'bench'))
        self.assertEqual([t.damage(b) for b in (b1, b2, b3)], [10, 0, 10])
        self.assertEqual(t.hp(self.opp), 400)

    async def test_distortion_door_not_from_hand_or_full_bench(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        gira = t.put(GIRATINA, P1, 'hand')
        self.assertIsNone(t.ability_offer(gira, 'Distortion Door'))
        t = self.table()
        t.put(self.filler, P1, 'active')
        for _ in range(5):
            t.put(self.filler, P1, 'bench')
        gira = t.put(GIRATINA, P1, 'discard')
        self.assertIsNone(t.ability_offer(gira, 'Distortion Door'))

    async def test_shadow_impact_four_counters_on_own_pokemon(self):
        t = self.table()
        gira = t.put(GIRATINA, P1, 'active')
        bench = t.put(self.filler, P1, 'bench')
        t.energy(gira, P, 3)
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.attack(gira, 'Shadow Impact')
        self.assertEqual(400 - t.hp(self.opp), 130)
        self.assertEqual(t.damage(bench), 40)
        self.assertEqual(t.damage(gira), 0)

    # --- Deoxys: Psyspear -----------------------------------------------------
    async def test_psyspear_two_extra_energy_hits_bench(self):
        for extra, bench_dmg in ((1, 0), (2, 120)):
            t = self.table()
            deoxys = t.put(DEOXYS, P1, 'active')
            t.energy(deoxys, P, 3 + extra)
            bench = t.put(self.filler, P2, 'bench')
            bench.set_attribute(AttrID.HP, 400)
            bench.set_attribute(AttrID.WEAKNESS_TYPES, [P.value])
            t.pokemon = lambda c, p: bench if bench in c else c[0]
            await t.attack(deoxys, 'Psyspear')
            with self.subTest(extra=extra):
                self.assertEqual(400 - t.hp(self.opp), 120)
                self.assertEqual(400 - t.hp(bench), bench_dmg)

    # --- Mew (CEL): Mysterious Tail ------------------------------------------
    async def test_mysterious_tail_item_from_top_six_active_only(self):
        t = self.table()
        mew = t.put(MEW, P1, 'active')
        t.deck(P1, [GUZMA, 'SV1.NestBall_181'])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', t.names(cards)), cards[:1])[1]
        await t.use(mew, 'Mysterious Tail')
        self.assertNotIn('Guzma', seen['n'])
        self.assertEqual(t.shown[-1], 6)
        self.assertEqual(self.hand(t), 1)
        self.assertIsNone(t.ability_offer(mew, 'Mysterious Tail'))
        t = self.table()
        t.put(self.filler, P1, 'active')
        mew = t.put(MEW, P1, 'bench')
        self.assertIsNone(t.ability_offer(mew, 'Mysterious Tail'))

    # --- Munkidori (PRE): Adrena-Brain / Mind Bend ---------------------------
    async def test_adrena_brain_needs_darkness_energy(self):
        t = self.table()
        munk = t.put(MUNKIDORI, P1, 'active')
        t.energy(munk, P)
        self.assertIsNone(t.ability_offer(munk, 'Adrena-Brain'))

    async def test_adrena_brain_moves_up_to_three(self):
        t = self.table()
        munk = t.put(MUNKIDORI, P1, 'active')
        t.energy(munk, D)
        hurt = t.put(self.filler, P1, 'bench')
        hurt.set_attribute(AttrID.HP, t.hp(hurt) - 50)
        order = iter([hurt, self.opp])
        t.pokemon = lambda c, p: next(order)
        from spirit.game.session.effects import EffectContext
        from unittest.mock import patch

        async def choose(ctx, prompt, options, *a, **k):
            return len(options) - 1          # the most it offers
        with patch.object(EffectContext, 'choose', choose):
            await t.use(munk, 'Adrena-Brain')
        self.assertEqual(t.damage(hurt), 20)
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertIsNone(t.ability_offer(munk, 'Adrena-Brain'))

    async def test_mind_bend_confuses(self):
        t = self.table()
        munk = t.put(MUNKIDORI, P1, 'active')
        t.energy(munk, P, 2)
        await t.attack(munk, 'Mind Bend')
        self.assertEqual(400 - t.hp(self.opp), 60)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    # --- Blacephalon (SMP 221): Fireworks Bomb -------------------------------
    async def test_fireworks_bomb_four_or_twelve_counters(self):
        for prizes, counters in ((4, 4), (3, 12), (2, 4)):
            t = self.table()
            t.set_prizes(P2, prizes)
            blace = t.put(BLACEPHALON, P1, 'active')
            t.energy(blace, P, 2)
            bench = t.put(self.filler, P2, 'bench')
            bench.set_attribute(AttrID.HP, 400)
            await t.attack(blace, 'Fireworks Bomb')
            with self.subTest(prizes=prizes):
                self.assertEqual((800 - t.hp(self.opp) - t.hp(bench)) // 10, counters)


if __name__ == "__main__":
    unittest.main()
