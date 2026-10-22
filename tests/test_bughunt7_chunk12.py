"""Bug hunt round 7, chunk 12: Meowth (SFA/MEW), Ethan's Pichu, Bayleef,
Dragonite (UNM), Silcoon (ASC), Luxray (PAL), Yamask, Dratini, Sudowoodo,
Dialga (MEG), Thwackey (TWM/CRE/SHF), Sacred Ash -- each checked against its
printed text, including the cases where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, LIGHT, GRASS, METAL, PSY, FIGHT = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.LIGHTNING,
    PokemonTypes.GRASS, PokemonTypes.METAL, PokemonTypes.PSYCHIC,
    PokemonTypes.FIGHTING)

MEOWTH_SFA, MEOWTH_MEW = 'SV065.Meowth_48', 'SV035.Meowth_52'
PICHU, BAYLEEF, DRAGONITE = 'SV10.EthansPichu_71', 'SM8.Bayleef_7', 'SM11.Dragonite_151'
WURMPLE, SILCOON, CASCOON = 'ME2PT5.Wurmple_11', 'ME2PT5.Silcoon_12', 'ME2PT5.Cascoon_14'
LUXRAY, YAMASK, DRATINI = 'SV2.Luxray_71', 'RSV10PT5.Yamask_39', 'SWSH12.Dratini_129'
SUDOWOODO, DIALGA = 'XY9.Sudowoodo_67', 'ME1.Dialga_95'
THW_TWM, THW_CRE, THW_SHF = 'SV06.Thwackey_15', 'SWSH6.Thwackey_17', 'SWSH45.Thwackey_12'
DIPPLIN = 'SV06.Dipplin_18'                    # has Festival Lead
SACRED_ASH = 'SV10.SacredAsh_168'
CAGE = 'ME2.BattleCage_85'


class Chunk12(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.neutral(self.opp)
        return t

    def neutral(self, p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return p

    def mine(self, t, spec, kind=None, count=0, zone='active'):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def is_def(self, card, spec):
        d = fixtures.definition(spec) if isinstance(spec, str) else spec
        return card.archetype_id.lower() == d.guid.lower()

    def is_energy_of(self, card, kind):
        return card.archetype_id.lower() == self.energies[kind.value].lower()

    def filler_attack(self):
        for a in def_for(self.opp.archetype_id).abilities:
            if isinstance(a, Attack) and a.damage:
                return a.title, a.damage
        raise AssertionError('filler has no damaging attack')

    def coins(self, t, seq):
        it = iter(seq)
        t.heads = lambda title: next(it)

    # --- Meowth SFA 48: Fury Swipes ------------------------------------------
    async def test_meowth_sfa_fury_swipes(self):
        for seq, dmg in (([False, True, True], 40), ([False] * 3, 0)):
            t = self.table()
            m = self.mine(t, MEOWTH_SFA, WATER, 2)
            self.coins(t, seq)
            await t.attack(m, 'Fury Swipes')
            with self.subTest(seq=seq):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Ethan's Pichu DRI 71: Zapping Draw ----------------------------------
    async def test_ethans_pichu_zapping_draw(self):
        t = self.table()
        p = self.mine(t, PICHU)
        self.assertIsNotNone(t.attack_offer(p, 'Zapping Draw'))   # no Energy needed
        deck0 = len(t.zone(P1, 'deck'))
        await t.attack(p, 'Zapping Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P1, 'deck')), deck0 - 1)
        self.assertEqual(400 - t.hp(self.opp), 30)

    # --- Bayleef LOT 7: Soothing Scent ---------------------------------------
    async def test_bayleef_soothing_scent(self):
        t = self.table()
        b = self.mine(t, BAYLEEF, GRASS, 1)
        await t.attack(b, 'Soothing Scent')
        self.assertEqual(400 - t.hp(self.opp), 20)
        self.assertIn(ASLEEP, t.conditions(self.opp))
        self.assertNotIn(ASLEEP, t.conditions(b))

    # --- Dragonite UNM 151: Hurricane Charge / Dragon Impact -----------------
    async def test_dragonite_hurricane_charge_one_of_each(self):
        t = self.table()
        d = self.mine(t, DRAGONITE)
        other = self.mine(t, self.filler, zone='bench')
        w = t.put(t.basic_energy(WATER), P1, 'hand')
        l = t.put(t.basic_energy(LIGHT), P1, 'hand')
        f = t.put(t.basic_energy(FIRE), P1, 'hand')
        targets = iter([d, other])
        t.pokemon = lambda cands, prompt: next(targets)
        await t.use(d, 'Hurricane Charge')
        attached = t.board.attached_energies(d) + t.board.attached_energies(other)
        self.assertIn(w, attached)
        self.assertIn(l, attached)
        self.assertNotIn(f, attached)
        self.assertIn(f, t.zone(P1, 'hand'))
        self.assertIsNone(t.ability_offer(d, 'Hurricane Charge'))   # once per turn

    async def test_dragonite_hurricane_charge_wrong_energy(self):
        t = self.table()
        d = self.mine(t, DRAGONITE)
        t.put(t.basic_energy(FIRE), P1, 'hand')
        t.put(t.basic_energy(GRASS), P1, 'hand')
        self.assertIsNone(t.ability_offer(d, 'Hurricane Charge'))

    async def test_dragonite_dragon_impact(self):
        t = self.table()
        d = self.mine(t, DRAGONITE)
        t.energy(d, WATER, 3)
        t.energy(d, LIGHT, 2)
        await t.attack(d, 'Dragon Impact')
        self.assertEqual(400 - t.hp(self.opp), 170)
        self.assertEqual(len(t.board.attached_energies(d)), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 3)

    # --- Silcoon ASC 12: Multiplying Cocoon ----------------------------------
    async def test_silcoon_multiplying_cocoon_on_evolve(self):
        t = self.table()
        self.mine(t, self.filler)
        wurm = self.mine(t, WURMPLE, zone='bench')
        sil = t.put(SILCOON, P1, 'hand')
        cas, = t.deck(P1, [CASCOON])
        t.yes = True
        await t.play(sil, targets=[wurm.entity_id])
        bench = t.zone(P1, 'bench')
        self.assertIn(cas, bench)
        self.assertEqual(len(bench), 2)

    async def test_silcoon_multiplying_cocoon_only_silcoon_or_cascoon(self):
        t = self.table()
        self.mine(t, self.filler)
        w1 = self.mine(t, WURMPLE, zone='bench')
        w2 = self.mine(t, WURMPLE, zone='bench')
        s1 = t.put(SILCOON, P1, 'hand')
        s2 = t.put(SILCOON, P1, 'hand')
        wurm_deck, cas, sil_deck = t.deck(P1, [WURMPLE, CASCOON, SILCOON])
        seen = []
        t.picks = lambda cards, count, prompt, disp: (seen.append(list(cards)) or
                                                       [c for c in cards if c is cas][:count])
        await t.play(s1, targets=[w1.entity_id])
        self.assertTrue(seen)
        self.assertNotIn(wurm_deck, seen[-1])
        self.assertIn(cas, t.zone(P1, 'bench'))
        n = len(seen)
        # "Once during your turn" is per Pokémon: a different Silcoon may use its own.
        t.picks = lambda cards, count, prompt, disp: (seen.append(list(cards)) or
                                                       [c for c in cards if c is sil_deck][:count])
        await t.play(s2, targets=[w2.entity_id])
        self.assertEqual(len(seen), n + 1)
        self.assertNotIn(wurm_deck, seen[-1])
        self.assertIn(sil_deck, t.zone(P1, 'bench'))

    async def test_silcoon_multiplying_cocoon_not_from_bench(self):
        # Only "when you play this Pokémon from your hand to evolve".
        t = self.table()
        self.mine(t, self.filler)
        sil = self.mine(t, SILCOON, zone='bench')
        t.deck(P1, [CASCOON])
        self.assertIsNone(t.ability_offer(sil, 'Multiplying Cocoon'))

    # --- Luxray PAL 71: Swelling Flash / Wild Charge -------------------------
    async def test_luxray_swelling_flash_behind_on_prizes(self):
        t = self.table()
        self.mine(t, self.filler)
        lux = t.put(LUXRAY, P1, 'hand')
        t.set_prizes(P2, 5)
        await t.use(lux, 'Swelling Flash')
        self.assertIn(lux, t.zone(P1, 'bench'))

    async def test_luxray_swelling_flash_not_when_tied_or_ahead(self):
        for mine_p, opp_p in ((5, 5), (4, 5)):
            t = self.table()
            self.mine(t, self.filler)
            lux = t.put(LUXRAY, P1, 'hand')
            t.set_prizes(P1, mine_p)
            t.set_prizes(P2, opp_p)
            with self.subTest(mine=mine_p, opp=opp_p):
                self.assertIsNone(t.ability_offer(lux, 'Swelling Flash'))

    async def test_luxray_swelling_flash_not_in_play(self):
        t = self.table()
        lux = self.mine(t, LUXRAY)
        t.set_prizes(P2, 5)
        self.assertIsNone(t.ability_offer(lux, 'Swelling Flash'))

    async def test_luxray_wild_charge(self):
        t = self.table()
        lux = self.mine(t, LUXRAY, LIGHT, 3)
        await t.attack(lux, 'Wild Charge')
        self.assertEqual(400 - t.hp(self.opp), 180)
        self.assertEqual(t.damage(lux), 20)

    # --- Yamask WHT 39: Focused Wish -----------------------------------------
    async def test_yamask_focused_wish(self):
        for heads, dmg in ((True, 40), (False, 20)):
            t = self.table()
            y = self.mine(t, YAMASK, PSY, 2)
            t.heads = heads
            await t.attack(y, 'Focused Wish')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Dratini SIT 129: Slam -----------------------------------------------
    async def test_dratini_slam(self):
        for seq, dmg in (([True, True], 60), ([True, False], 30), ([False, False], 0)):
            t = self.table()
            d = self.mine(t, DRATINI, WATER, 2)
            self.coins(t, seq)
            await t.attack(d, 'Slam')
            with self.subTest(seq=seq):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    # --- Meowth MEW 52: Come Here Right Meow ---------------------------------
    async def test_meowth_mew_come_here_right_meow(self):
        for heads in (True, False):
            t = self.table()
            m = self.mine(t, MEOWTH_MEW, WATER, 1)
            b1 = self.neutral(t.put(self.filler, P2, 'bench'))
            b2 = self.neutral(t.put(self.filler, P2, 'bench'))
            t.pokemon = lambda cands, prompt: b2 if b2 in cands else cands[0]
            t.heads = heads
            await t.attack(m, 'Come Here Right Meow')
            with self.subTest(heads=heads):
                self.assertIs(t.active(P2), b2 if heads else self.opp)
                self.assertEqual(t.hp(self.opp), 400)
                self.assertIs(t.active(P1), m)

    # --- Sudowoodo BKP 67: Watch and Learn -----------------------------------
    async def test_sudowoodo_watch_and_learn(self):
        t = self.table()
        sudo = self.mine(t, SUDOWOODO, FIGHT, 2)
        sudo.set_attribute(AttrID.HP, 300)
        title, dmg = self.filler_attack()
        t.energy(self.opp, WATER, 5)
        t.next_turn()
        await t.attack(self.opp, title, pid=P2)
        t.next_turn()
        await t.attack(sudo, 'Watch and Learn')
        self.assertEqual(400 - t.hp(self.opp), dmg)

    async def test_sudowoodo_watch_and_learn_nothing_to_copy(self):
        t = self.table()
        sudo = self.mine(t, SUDOWOODO, FIGHT, 2)
        t.next_turn()
        t.next_turn()          # opponent passed without attacking
        offer = t.attack_offer(sudo, 'Watch and Learn')
        if offer is not None:
            await t.do(offer)
        self.assertEqual(t.hp(self.opp), 400)

    # --- Dialga MEG 95: Chrono Burst -----------------------------------------
    async def test_dialga_chrono_burst_shuffle(self):
        t = self.table()
        d = self.mine(t, DIALGA, METAL, 3)
        deck0 = len(t.zone(P1, 'deck'))
        t.yes = True
        await t.attack(d, 'Chrono Burst')
        self.assertEqual(400 - t.hp(self.opp), 160)
        self.assertEqual(t.board.attached_energies(d), [])
        self.assertEqual(len(t.zone(P1, 'deck')), deck0 + 3)
        self.assertEqual(len(t.zone(P1, 'discard')), 0)

    async def test_dialga_chrono_burst_decline(self):
        t = self.table()
        d = self.mine(t, DIALGA, METAL, 3)
        t.yes = False
        await t.attack(d, 'Chrono Burst')
        self.assertEqual(400 - t.hp(self.opp), 80)
        self.assertEqual(len(t.board.attached_energies(d)), 3)

    # --- Thwackey TWM 15: Boom Boom Groove -----------------------------------
    async def test_thwackey_twm_boom_boom_groove(self):
        t = self.table()
        self.mine(t, DIPPLIN)
        thw = self.mine(t, THW_TWM, zone='bench')
        target, = t.deck(P1, [SACRED_ASH])
        t.picks = lambda cards, count, prompt, disp: [target]
        await t.use(thw, 'Boom Boom Groove')
        self.assertEqual(t.zone(P1, 'hand'), [target])
        self.assertIsNone(t.ability_offer(thw, 'Boom Boom Groove'))   # once per turn

    async def test_thwackey_twm_needs_festival_lead_active(self):
        t = self.table()
        self.mine(t, self.filler)
        self.mine(t, DIPPLIN, zone='bench')          # Festival Lead on the Bench only
        thw = self.mine(t, THW_TWM, zone='bench')
        self.assertIsNone(t.ability_offer(thw, 'Boom Boom Groove'))

    # --- Thwackey CRE 17: Knock Off ------------------------------------------
    async def test_thwackey_cre_knock_off(self):
        t = self.table()
        thw = self.mine(t, THW_CRE, GRASS, 2)
        for _ in range(3):
            t.put(self.item, P2, 'hand')
        mine_hand = t.put(self.item, P1, 'hand')
        await t.attack(thw, 'Knock Off')
        self.assertEqual(400 - t.hp(self.opp), 30)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)
        self.assertEqual(len(t.zone(P2, 'discard')), 1)
        self.assertEqual(t.zone(P1, 'hand'), [mine_hand])

    async def test_thwackey_cre_knock_off_empty_hand(self):
        t = self.table()
        thw = self.mine(t, THW_CRE, GRASS, 2)
        await t.attack(thw, 'Knock Off')
        self.assertEqual(400 - t.hp(self.opp), 30)

    # --- Thwackey SHF 12: Lay of the Land ------------------------------------
    async def test_thwackey_shf_lay_of_the_land(self):
        cases = ((None, 2), (P1, 0), (P2, 2))
        for owner, cost in cases:
            t = self.table()
            thw = self.mine(t, THW_SHF)
            other = self.mine(t, self.filler, zone='bench')
            if owner is not None:
                t.stadium(CAGE, owner)
            with self.subTest(owner=owner):
                self.assertEqual(t.retreat(thw), cost)
                if owner == P1:     # only Thwackey itself loses its cost
                    self.assertNotEqual(t.retreat(other), 0)

    # --- Sacred Ash DRI 168 --------------------------------------------------
    async def test_sacred_ash_up_to_five(self):
        t = self.table()
        self.mine(t, self.filler)
        mons = [t.put(self.filler, P1, 'discard') for _ in range(6)]
        energy = t.put(t.basic_energy(WATER), P1, 'discard')
        offered = []
        t.picks = lambda cards, count, prompt, disp: (offered.append((list(cards), count))
                                                       or cards[:count])
        deck0 = len(t.zone(P1, 'deck'))
        ash = t.put(SACRED_ASH, P1, 'hand')
        await t.play(ash)
        self.assertEqual(offered[-1][1], 5)
        self.assertNotIn(energy, offered[-1][0])
        self.assertEqual(len(t.zone(P1, 'deck')), deck0 + 5)
        discard = t.zone(P1, 'discard')
        self.assertEqual(sum(1 for c in mons if c in discard), 1)
        self.assertIn(energy, discard)

    async def test_sacred_ash_no_pokemon_in_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(t.basic_energy(WATER), P1, 'discard')
        ash = t.put(SACRED_ASH, P1, 'hand')
        self.assertFalse(t.can(ash, 'UseTrainerCard'))


if __name__ == '__main__':
    unittest.main()
