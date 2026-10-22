"""Bug hunt round 7, chunk 39: Cosmog/Cosmoem/Lunala, Azelf, Mina, Eternatus,
N's Reshiram, Miraidon, Team Magma's Secret Base, Bouffalant, Treecko (PLF),
Grovyle, Phantump, Camping Gear, Herbal Energy -- each checked against its
printed text, including the cases where it should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

PSY, WATER, GRASS, FIRE = PokemonTypes.PSYCHIC, PokemonTypes.WATER, PokemonTypes.GRASS, PokemonTypes.FIRE
DARK, LIGHT, FAIRY, FIGHT = PokemonTypes.DARKNESS, PokemonTypes.LIGHTNING, PokemonTypes.FAIRY, PokemonTypes.FIGHTING

COSMOG, COSMOEM, LUNALA = 'SM9.Cosmog_69', 'CEL25.Cosmoem_14', 'CEL25.Lunala_15'
AZELF, MINA, ETERNATUS = 'Promo_XY.Azelf_142', 'SM8.Mina_183', 'SV08.Eternatus_141'
NS_RESHIRAM, MIRAIDON = 'SV09.NsReshiram_116', 'SV05.Miraidon_121'
MAGMA_BASE, MAGMA_NUMEL = 'TATM.TeamMagmasSecretBase_32', 'TATM.TeamMagmasNumel_1'
BOUFFALANT = 'SWSH11.Bouffalant_148'
TREECKO_PLF, TREECKO_PRC = 'BW9.Treecko_6', 'XY5.Treecko_6'
GROVYLE, PHANTUMP = 'SM8.Grovyle_21', 'XY1.Phantump_54'
CAMPING_GEAR, HERBAL = 'SWSH5.CampingGear_122', 'XY3.HerbalEnergy_103'
IRON_HANDS = 'SV05.IronHands_61'          # Future Basic
BOLDORE = 'BW6.Boldore_66'                # Earthquake: 10 to each of your Benched
OTHER_STADIUM = 'SV2.Artazon_171'


class Chunk39(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, big=True):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        if big:
            self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def is_energy_of(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    def counters(self, t, p):
        return t.damage(p) // 10

    def filler_attack(self):
        for a in self.filler.abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    # --- Cosmog TEU 69: Cosmic Guard --------------------------------------------
    async def test_cosmog_benched_takes_no_damage_from_opponent_attack(self):
        t = self.table()
        lunala = self.mine(t, LUNALA, PSY, 3)
        cosmog = self.mine(t, COSMOG, zone='bench', pid=P2)
        t.pokemon = lambda cands, prompt: cosmog
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is cosmog][:count] or cards[:count]
        await t.attack(lunala, 'Psychic Shot')
        self.assertEqual(400 - t.hp(self.opp), 130)
        self.assertIn(cosmog, t.zone(P2, 'bench'))
        self.assertEqual(t.damage(cosmog), 0)

    async def test_psychic_shot_control_hits_plain_bench(self):
        t = self.table()
        lunala = self.mine(t, LUNALA, PSY, 3)
        other = self.mine(t, self.filler, zone='bench', pid=P2)
        await t.attack(lunala, 'Psychic Shot')
        self.assertEqual(t.damage(other), 30)

    async def test_cosmog_benched_takes_no_damage_from_own_attack(self):
        t = self.table()
        boldore = self.mine(t, BOLDORE, FIGHT, 3)
        cosmog = self.mine(t, COSMOG, zone='bench')
        other = self.mine(t, self.filler, zone='bench')
        await t.attack(boldore, 'Earthquake')
        self.assertEqual(t.damage(other), 10, 'control: other benched Pokémon is hit')
        self.assertEqual(t.damage(cosmog), 0)

    async def test_cosmog_active_is_not_protected(self):
        t = self.table()
        boldore = self.mine(t, BOLDORE, FIGHT, 3)
        cosmog = self.mine(t, COSMOG, zone='active', pid=P2)
        board_active = t.zone(P2, 'active')
        for c in board_active:
            if c is not cosmog:
                t.board.move_card(c.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        cosmog.set_attribute(AttrID.HP, 400)
        await t.attack(boldore, 'Earthquake')
        self.assertEqual(400 - t.hp(cosmog), 60)

    # --- Cosmoem CEL 14: Star Protection ---------------------------------------
    async def test_cosmoem_star_protection(self):
        title, dmg = self.filler_attack()
        for heads in (True, False):
            t = self.table()
            cosmoem = self.mine(t, COSMOEM, PSY, 1)
            cosmoem.set_attribute(AttrID.HP, 400)
            t.heads = heads
            await t.attack(cosmoem, 'Star Protection')
            t.energy(self.opp, WATER, 5)
            t.next_turn()
            await t.attack(self.opp, title, pid=P2)
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(cosmoem), 0 if heads else dmg)

    # --- Lunala CEL 15 ------------------------------------------------------
    async def test_lunala_lunar_pain_doubles_counters(self):
        t = self.table(big=False)
        mx = effective_max_hp(t.board, self.opp)
        self.opp.set_attribute(AttrID.HP, mx - 30)
        b1 = self.mine(t, self.filler, zone='bench', pid=P2)
        b1.set_attribute(AttrID.HP, effective_max_hp(t.board, b1) - 20)
        b2 = self.mine(t, self.filler, zone='bench', pid=P2)
        mine_b = self.mine(t, self.filler, zone='bench')
        mine_b.set_attribute(AttrID.HP, effective_max_hp(t.board, mine_b) - 20)
        lunala = self.mine(t, LUNALA, PSY, 2)
        await t.attack(lunala, 'Lunar Pain')
        self.assertEqual(self.counters(t, self.opp), 6)
        self.assertEqual(self.counters(t, b1), 4)
        self.assertEqual(self.counters(t, b2), 0)
        self.assertEqual(self.counters(t, mine_b), 2, 'own Pokémon untouched')

    # --- Azelf XYP 142 ------------------------------------------------------
    async def test_azelf_shining_eyes_only_damaged_pokemon(self):
        t = self.table(big=False)
        self.opp.set_attribute(AttrID.HP, effective_max_hp(t.board, self.opp) - 10)
        b1 = self.mine(t, self.filler, zone='bench', pid=P2)
        b1.set_attribute(AttrID.HP, effective_max_hp(t.board, b1) - 30)
        b2 = self.mine(t, self.filler, zone='bench', pid=P2)
        mine_b = self.mine(t, self.filler, zone='bench')
        mine_b.set_attribute(AttrID.HP, effective_max_hp(t.board, mine_b) - 10)
        azelf = self.mine(t, AZELF, PSY, 1)
        await t.attack(azelf, 'Shining Eyes')
        self.assertEqual(self.counters(t, self.opp), 3)
        self.assertEqual(self.counters(t, b1), 5)
        self.assertEqual(self.counters(t, b2), 0)
        self.assertEqual(self.counters(t, mine_b), 1)

    async def test_azelf_mind_bend_confuses(self):
        t = self.table()
        azelf = self.mine(t, AZELF, PSY, 3)
        await t.attack(azelf, 'Mind Bend')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertIn(CONFUSED, t.conditions(self.opp))

    # --- Mina LOT 183 -------------------------------------------------------
    async def test_mina_attaches_fairy_energy_from_deck(self):
        t = self.table()
        self.mine(t, self.filler)
        bench = self.mine(t, self.filler, zone='bench')
        t.deck(P1, [t.basic_energy(WATER), t.basic_energy(FAIRY)])
        mina = t.put(MINA, P1, 'hand')
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        t.picks = lambda cards, count, prompt, display: [c for c in cards if self.is_energy_of(c, FAIRY)][:count]
        await t.play(mina)
        attached = [c for c in t.attached(bench)]
        self.assertEqual(len(attached), 1)
        self.assertTrue(self.is_energy_of(attached[0], FAIRY))
        self.assertEqual(sum(1 for c in t.zone(P1, 'deck') if self.is_energy_of(c, WATER)), 1)

    async def test_mina_cannot_take_non_fairy(self):
        t = self.table()
        active = self.mine(t, self.filler)
        t.deck(P1, [t.basic_energy(WATER)])
        mina = t.put(MINA, P1, 'hand')
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        if t.can(mina, 'UseTrainerCard'):
            await t.play(mina)
        self.assertEqual(t.attached(active), [])
        self.assertFalse(any(self.is_energy_of(c, WATER) for c in seen))

    # --- Eternatus SSP 141 --------------------------------------------------
    async def test_eternatus_dyna_blast_vs_non_ex(self):
        t = self.table()
        e = self.mine(t, ETERNATUS, DARK, 1)
        await t.attack(e, 'Dyna-Blast')
        self.assertEqual(400 - t.hp(self.opp), 10)

    async def test_eternatus_dyna_blast_vs_ex(self):
        t = self.table()
        e = self.mine(t, ETERNATUS, DARK, 1)
        d = def_for(self.opp.archetype_id)
        with patch.object(d, 'subtypes', list(d.subtypes) + ['ex']):
            await t.attack(e, 'Dyna-Blast')
        self.assertEqual(400 - t.hp(self.opp), 90)

    async def test_eternatus_world_ender_discards_stadium(self):
        for owner in (P1, P2):
            t = self.table()
            e = self.mine(t, ETERNATUS, DARK, 2)
            t.energy(e, FIRE, 1)
            st = t.stadium(OTHER_STADIUM, owner)
            await t.attack(e, 'World Ender')
            with self.subTest(owner=owner):
                self.assertEqual(400 - t.hp(self.opp), 230)
                self.assertEqual(list(t.board.find_global_area('activeStadium').children), [])
                self.assertIn(st, t.zone(owner, 'discard'))

    # BUG: World Ender does 230 even with no Stadium in play ("If you can't, this attack does nothing" ignored)
    async def test_eternatus_world_ender_without_stadium_does_nothing(self):
        t = self.table()
        e = self.mine(t, ETERNATUS, DARK, 2)
        t.energy(e, FIRE, 1)
        entry = t.attack_offer(e, 'World Ender')
        if entry is not None:
            await t.do(entry)
        self.assertEqual(400 - t.hp(self.opp), 0)

    # --- N's Reshiram JTG 116: Powerful Rage ------------------------------------
    async def test_ns_reshiram_powerful_rage(self):
        for counters in (0, 3):
            t = self.table()
            r = self.mine(t, NS_RESHIRAM, FIRE, 1)
            t.energy(r, LIGHT, 1)
            r.set_attribute(AttrID.HP, effective_max_hp(t.board, r) - counters * 10)
            await t.attack(r, 'Powerful Rage')
            with self.subTest(counters=counters):
                self.assertEqual(400 - t.hp(self.opp), 20 * counters)

    # --- Miraidon TEF 121: Peak Acceleration -------------------------------------
    # BUG: Peak Acceleration offers non-Future Pokémon as attach targets (no Future filter in bw_legacy_attack)
    async def test_miraidon_peak_acceleration_to_future_only(self):
        t = self.table()
        m = self.mine(t, MIRAIDON, WATER, 1)
        hands = self.mine(t, IRON_HANDS, zone='bench')
        plain = self.mine(t, self.filler, zone='bench')
        t.deck(P1, [t.basic_energy(LIGHT), t.basic_energy(PSY)])
        offered = []

        def choose(cands, prompt):
            offered.append(list(cands))
            return hands if hands in cands else cands[0]
        t.pokemon = choose
        await t.attack(m, 'Peak Acceleration')
        self.assertEqual(400 - t.hp(self.opp), 40)
        self.assertEqual(len(t.attached(hands)), 2)
        self.assertEqual(t.attached(plain), [])
        for cands in offered:
            self.assertNotIn(plain, cands)

    # --- Team Magma's Secret Base DCR 32 -------------------------------------
    async def test_magma_base_counters_on_benched_basic(self):
        for owner in (P1, P2):
            t = self.table()
            self.mine(t, self.filler)
            t.stadium(MAGMA_BASE, owner)
            card = t.put(TREECKO_PLF, P1, 'hand')
            await t.play(card)
            with self.subTest(stadium_owner=owner):
                self.assertIn(card, t.zone(P1, 'bench'))
                self.assertEqual(t.damage(card), 20)

    # BUG: Team Magma's Secret Base puts 2 counters on Team Magma's Numel (team is only in the name, handler checks subtypes)
    async def test_magma_base_spares_team_magma_and_evolution(self):
        t = self.table()
        self.mine(t, self.filler)
        t.stadium(MAGMA_BASE, P1)
        numel = t.put(MAGMA_NUMEL, P1, 'hand')
        await t.play(numel)
        self.assertIn(numel, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(numel), 0)
        treecko = self.mine(t, TREECKO_PLF, zone='bench')
        grovyle = t.put(GROVYLE, P1, 'hand')
        await t.play(grovyle, targets=[treecko.entity_id])
        self.assertIn(grovyle, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(grovyle), 0)

    # --- Bouffalant LOR 148: Lost Headbutt ----------------------------------
    async def test_bouffalant_lost_headbutt(self):
        t = self.table()
        b = self.mine(t, BOUFFALANT, WATER, 3)
        e = t.energy(self.opp, FIRE, 1)
        await t.attack(b, 'Lost Headbutt')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertEqual(t.attached(self.opp), [])
        self.assertIn(e, t.zone(P2, 'lostZone'))

    async def test_bouffalant_lost_headbutt_no_energy(self):
        t = self.table()
        b = self.mine(t, BOUFFALANT, WATER, 3)
        bench = self.mine(t, self.filler, zone='bench', pid=P2)
        be = t.energy(bench, FIRE, 1)
        await t.attack(b, 'Lost Headbutt')
        self.assertEqual(400 - t.hp(self.opp), 50)
        self.assertIn(be, t.attached(bench), 'bench Energy untouched')

    # --- Treecko PLF 6 (chunk path XY5 is PRC 6) ------------------------------
    async def test_treecko_plf_reckless_charge(self):
        t = self.table()
        tr = self.mine(t, TREECKO_PLF, GRASS, 2)
        await t.attack(tr, 'Reckless Charge')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertEqual(t.damage(tr), 10)

    # --- Grovyle LOT 21: Sunshine Grace ---------------------------------------
    async def test_grovyle_sunshine_grace(self):
        t = self.table()
        self.mine(t, self.filler)
        g = self.mine(t, GROVYLE, zone='bench')
        t.deck(P1, [self.filler, TREECKO_PLF])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.use(g, 'Sunshine Grace')
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Treecko'])
        self.assertFalse(any(def_for(c.archetype_id).display_name == def_for(self.opp.archetype_id).display_name
                             for c in seen), 'non-Grass Pokémon not selectable')
        self.assertIsNone(t.ability_offer(g, 'Sunshine Grace'), 'once per turn')

    # --- Phantump XY 54: Astonish ----------------------------------------------
    async def test_phantump_astonish(self):
        t = self.table()
        p = self.mine(t, PHANTUMP, PSY, 1)
        card = t.put(GROVYLE, P2, 'hand')
        deck_before = len(t.zone(P2, 'deck'))
        await t.attack(p, 'Astonish')
        self.assertEqual(t.zone(P2, 'hand'), [])
        self.assertIn(card, t.zone(P2, 'deck'))
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before + 1)
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_phantump_astonish_empty_hand(self):
        t = self.table()
        p = self.mine(t, PHANTUMP, PSY, 1)
        deck_before = len(t.zone(P2, 'deck'))
        await t.attack(p, 'Astonish')
        self.assertEqual(len(t.zone(P2, 'deck')), deck_before)

    # --- Camping Gear BST 122 ---------------------------------------------
    async def test_camping_gear_searches_and_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        t.deck(P1, [GROVYLE])
        gear = t.put(CAMPING_GEAR, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if def_for(c.archetype_id).display_name == 'Grovyle'][:count]
        over = await t.play(gear)
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Grovyle'])
        self.assertTrue(over, 'Camping Gear ends the turn')

    async def test_camping_gear_not_playable_with_empty_deck(self):
        t = self.table()
        self.mine(t, self.filler)
        area = t.board.find_player_area(P1, 'deck')
        for c in list(area.children):
            area.remove_child(c)
        gear = t.put(CAMPING_GEAR, P1, 'hand')
        self.assertFalse(t.can(gear, 'UseTrainerCard'))

    # --- Herbal Energy FFI 103 -------------------------------------------
    async def test_herbal_energy_heals_grass_on_attach(self):
        t = self.table()
        tr = self.mine(t, TREECKO_PLF)
        tr.set_attribute(AttrID.HP, effective_max_hp(t.board, tr) - 40)
        herb = t.put(HERBAL, P1, 'hand')
        await t.play(herb, targets=[tr.entity_id])
        self.assertIn(herb, t.attached(tr))
        self.assertEqual(t.damage(tr), 10)

    async def test_herbal_energy_only_grass(self):
        t = self.table()
        tr = self.mine(t, TREECKO_PLF, zone='bench')
        plain = self.mine(t, self.filler)
        herb = t.put(HERBAL, P1, 'hand')
        targets = set()
        for e in t.offers(herb, None):
            for info in e.get('targetInfoLst') or []:
                targets.update(info.get('validTargets') or [])
        self.assertIn(tr.entity_id, targets)
        self.assertNotIn(plain.entity_id, targets)

    async def test_herbal_energy_provides_grass_for_attack(self):
        t = self.table()
        tr = self.mine(t, TREECKO_PLF, GRASS, 1)
        t.attach(HERBAL, tr)
        self.assertIsNotNone(t.attack_offer(tr, 'Reckless Charge'))


if __name__ == '__main__':
    unittest.main()
