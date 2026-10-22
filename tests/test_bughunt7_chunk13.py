"""Bug hunt round 7, chunk 13: Wobbuffet, Flash Energy, Centiskorch x2,
Type: Null, Silvally, Cleffa, Dialga, Dipplin, Festival Grounds, Cape of
Toughness, Virbank City Gym, Defiance Vest, Quilladin -- each checked against
its printed text, including the cases where it should NOT work.
(Sizzlipede MEG 29 is vanilla: Ram / Combustion, skipped.)"""
import unittest
from unittest.mock import patch, AsyncMock

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, BURNED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, def_for
from spirit.tools.effect_smoke import P1, P2

PSY, WATER, FIRE, GRASS, LIGHT = (PokemonTypes.PSYCHIC, PokemonTypes.WATER, PokemonTypes.FIRE,
                                  PokemonTypes.GRASS, PokemonTypes.LIGHTNING)
METAL = PokemonTypes.METAL

WOBBUFFET = 'XY4.Wobbuffet_36'
FLASH = 'XY7.FlashEnergy_83'
CENTI_SSP, CENTI_BST = 'SV08.Centiskorch_28', 'SWSH5.Centiskorch_30'
TYPE_NULL, SILVALLY = 'SM11.TypeNull_183', 'ME5.Silvally_70'
CLEFFA, DIALGA = 'SM10.Cleffa_131', 'SV08.Dialga_135'
DIPPLIN, FESTIVAL = 'SV06.Dipplin_18', 'SV06.FestivalGrounds_149'
CAPE, VIRBANK, VEST = 'SWSH3.CapeofToughness_160', 'BW8.VirbankCityGym_126', 'SV4.DefianceVest_162'
SIZZLI_BST, QUILLADIN = 'SWSH5.Sizzlipede_29', 'ME4.Quilladin_6'
PIKACHU, LILLIE = 'SWSH1.Pikachu_65', 'SM1.Lillie_122'
MISMAGIUS = 'SM10.Mismagius_78'


class Chunk13(unittest.IsolatedAsyncioTestCase):
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

    def dealt(self, t):
        return 400 - t.hp(self.opp)

    # --- Wobbuffet PHF 36 ---------------------------------------------------
    async def test_wobbuffet_active_blocks_non_psychic_ability(self):
        t = self.table()
        self.mine(t, WOBBUFFET, PSY, 0)
        silv = self.mine(t, SILVALLY, WATER, 0, zone='bench')
        t.deck(P1, [LILLIE])
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertIsNone(t.ability_offer(silv, 'Call a Buddy'))

    async def test_wobbuffet_benched_does_not_block(self):
        t = self.table()
        self.mine(t, self.filler, WATER, 0)
        self.mine(t, WOBBUFFET, PSY, 0, zone='bench')
        silv = self.mine(t, SILVALLY, WATER, 0, zone='bench')
        t.deck(P1, [LILLIE])
        self.assertIsNotNone(t.ability_offer(silv, 'Call a Buddy'))

    async def test_wobbuffet_opponent_active_blocks_too(self):
        t = Table(self)
        t.put(WOBBUFFET, P2, 'active')
        self.mine(t, self.filler, WATER, 0)
        silv = self.mine(t, SILVALLY, WATER, 0, zone='bench')
        t.deck(P1, [LILLIE])
        self.assertIsNone(t.ability_offer(silv, 'Call a Buddy'))

    async def test_wobbuffet_psychic_assault(self):
        t = self.table()
        wob = self.mine(t, WOBBUFFET, PSY, 2)
        self.opp.set_attribute(AttrID.HP, t.hp(self.opp))
        from spirit.game.session.passives import effective_max_hp
        full = effective_max_hp(t.board, self.opp)
        self.opp.set_attribute(AttrID.HP, full - 30)  # 3 damage counters
        await t.attack(wob, 'Psychic Assault')
        self.assertEqual(full - 30 - t.hp(self.opp), 40)

    # --- Flash Energy AOR 83 -----------------------------------------------
    async def test_flash_energy_attach_lightning_only(self):
        t = self.table()
        pika = self.mine(t, PIKACHU, LIGHT, 0)
        snor = self.mine(t, self.filler, WATER, 0, zone='bench')
        flash = t.put(FLASH, P1, 'hand')
        targets = t.targets(flash, 'DefaultEnergyPlayAbility')
        self.assertIn(pika.entity_id, targets)
        self.assertNotIn(snor.entity_id, targets)

    async def test_flash_energy_removes_weakness(self):
        for with_flash in (True, False):
            t = self.table()
            _, base = self.filler_attack()
            pika = t.put(PIKACHU, P1, 'active')
            pika.set_attribute(AttrID.HP, 400)
            pika.set_attribute(AttrID.WEAKNESS_TYPES, [PokemonTypes.COLORLESS])
            pika.set_attribute(AttrID.RESISTANCE_TYPES, [])
            if with_flash:
                flash = t.put(FLASH, P1, 'hand')
                await t.play(flash, targets=[pika.entity_id])
                self.assertIn(flash, pika.children)
            await self.opp_hits(t)
            with self.subTest(flash=with_flash):
                self.assertEqual(400 - t.hp(pika), base if with_flash else base * 2)

    # --- Centiskorch SSP 28 ------------------------------------------------
    async def test_centiskorch_ssp_billowing_heat_wave(self):
        t = self.table()
        c = self.mine(t, CENTI_SSP, FIRE, 1)
        b1 = self.mine(t, self.filler, WATER, 0, zone='bench')
        b2 = self.mine(t, self.filler, WATER, 0, zone='bench')
        opp_bench = t.put(self.filler, P2, 'bench')
        await t.attack(c, 'Billowing Heat Wave')
        self.assertEqual(self.dealt(t), 130)
        self.assertEqual(t.damage(b1), 30)
        self.assertEqual(t.damage(b2), 30)
        self.assertEqual(t.damage(opp_bench), 0)
        self.assertEqual(t.damage(c), 0)

    # --- Centiskorch BST 30 ------------------------------------------------
    async def test_centiskorch_bst_bursting_inferno_burns(self):
        t = self.table()
        c = self.mine(t, CENTI_BST, FIRE, 4)
        await t.attack(c, 'Bursting Inferno')
        self.assertEqual(self.dealt(t), 130)
        self.assertIn(BURNED, t.conditions(self.opp))

    async def test_centiskorch_overheater_opponent_stays_burned(self):
        t = self.table()
        self.mine(t, CENTI_BST, FIRE, 0, zone='bench')
        self.mine(t, self.filler, WATER, 0)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        t.heads = True
        await t.checkup()
        self.assertIn(BURNED, t.conditions(self.opp))

    async def test_centiskorch_overheater_own_pokemon_recover(self):
        t = self.table()
        self.mine(t, CENTI_BST, FIRE, 0, zone='bench')
        me = self.mine(t, self.filler, WATER, 0)
        me.set_attribute(AttrID.HP, 300)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        t.heads = True
        # The burn checkup flip is game_session._checkup_burn's own
        # random.choice([0, 1]) (0 = heads), not the Table's coin hook.
        from spirit.game.session import game_session
        with patch.object(game_session.random, 'choice', side_effect=lambda seq: seq[0]):
            await t.checkup()
        self.assertNotIn(BURNED, t.conditions(me))

    # --- Type: Null UNM 183: Quick Blow ------------------------------------
    async def test_type_null_quick_blow(self):
        for heads in (True, False):
            t = self.table()
            tn = self.mine(t, TYPE_NULL, WATER, 2)
            t.heads = heads
            await t.attack(tn, 'Quick Blow')
            with self.subTest(heads=heads):
                self.assertEqual(self.dealt(t), 60 if heads else 30)

    # --- Silvally PBL 70 ---------------------------------------------------
    async def test_silvally_call_a_buddy_finds_supporter(self):
        t = self.table()
        silv = self.mine(t, SILVALLY, WATER, 0)
        lillie, pika = t.deck(P1, [LILLIE, PIKACHU])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), [lillie])[1]
        await t.use(silv, 'Call a Buddy')
        self.assertEqual(t.zone(P1, 'hand'), [lillie])
        self.assertNotIn(pika, seen)
        self.assertIsNone(t.ability_offer(silv, 'Call a Buddy'))   # once per turn... and hand not empty

    async def test_silvally_call_a_buddy_needs_empty_hand(self):
        t = self.table()
        silv = self.mine(t, SILVALLY, WATER, 0)
        t.deck(P1, [LILLIE])
        t.put(self.item, P1, 'hand')
        self.assertIsNone(t.ability_offer(silv, 'Call a Buddy'))

    async def test_silvally_air_slash_discards_one_energy(self):
        t = self.table()
        silv = self.mine(t, SILVALLY, WATER, 3)
        await t.attack(silv, 'Air Slash')
        self.assertEqual(self.dealt(t), 130)
        self.assertEqual(len(silv.children), 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 1)

    # --- Cleffa UNB 131 -----------------------------------------------------
    async def test_cleffa_heads_shuffles_and_draws_six_turn_ends(self):
        t = self.table()
        cleffa = self.mine(t, CLEFFA, WATER, 0)
        for _ in range(2):
            t.put(self.item, P1, 'hand')
        t.heads = True
        ended = await t.use(cleffa, 'Excitable Draw')
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        self.assertTrue(ended)

    async def test_cleffa_tails_keeps_hand_turn_ends(self):
        t = self.table()
        cleffa = self.mine(t, CLEFFA, WATER, 0)
        hand = [t.put(self.item, P1, 'hand') for _ in range(2)]
        t.heads = False
        ended = await t.use(cleffa, 'Excitable Draw')
        self.assertEqual(t.zone(P1, 'hand'), hand)
        self.assertTrue(ended)

    # --- Dialga SSP 135: Time Manipulation ---------------------------------
    async def test_dialga_time_manipulation_puts_two_on_top(self):
        t = self.table()
        d = self.mine(t, DIALGA, WATER, 1)
        a, b = t.deck(P1, [LILLIE, PIKACHU], top=False)        # buried at the bottom
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in (a, b)][:count] \
            if count >= 2 else [c for c in cards if c in (a, b)][:count]
        deck_size = len(t.zone(P1, 'deck'))
        await t.attack(d, 'Time Manipulation')
        self.assertEqual(len(t.zone(P1, 'deck')), deck_size)
        self.assertEqual(self.dealt(t), 0)
        t.board.draw_cards(P1, 2)
        self.assertEqual(set(t.zone(P1, 'hand')), {a, b})

    # --- Dipplin TWM 18 + Festival Grounds TWM 149 -------------------------
    async def test_dipplin_do_the_wave(self):
        t = self.table()
        d = self.mine(t, DIPPLIN, GRASS, 1)
        for _ in range(3):
            self.mine(t, self.filler, WATER, 0, zone='bench')
        ended = await t.attack(d, 'Do the Wave')
        self.assertEqual(self.dealt(t), 60)
        self.assertTrue(ended)                       # no Festival Grounds: one attack

    async def test_dipplin_festival_lead_attacks_twice(self):
        t = self.table()
        d = self.mine(t, DIPPLIN, GRASS, 1)
        self.mine(t, self.filler, WATER, 0, zone='bench')
        t.stadium(FESTIVAL, P2)                      # any player's Festival Grounds counts
        with patch.object(t.session, 'prompt_player_choice', AsyncMock(return_value=0)):
            ended = await t.attack(d, 'Do the Wave')
            self.assertFalse(ended)
            ended = await t.attack(d, 'Do the Wave')
        self.assertTrue(ended)
        self.assertEqual(self.dealt(t), 40)

    async def test_festival_lead_only_for_dipplin_itself(self):
        t = self.table()
        self.mine(t, DIPPLIN, GRASS, 0, zone='bench')
        tn = self.mine(t, TYPE_NULL, WATER, 1)
        t.stadium(FESTIVAL, P1)
        with patch.object(t.session, 'prompt_player_choice', AsyncMock(return_value=0)):
            ended = await t.attack(tn, 'Smash Kick')
        self.assertTrue(ended)

    async def test_festival_grounds_energy_blocks_conditions(self):
        for opp_energy in (True, False):
            t = self.table()
            t.stadium(FESTIVAL, P1)
            s = self.mine(t, SIZZLI_BST, FIRE, 2)
            if opp_energy:
                t.energy(self.opp, WATER, 1)
            await t.attack(s, 'Searing Flame')
            with self.subTest(opp_energy=opp_energy):
                self.assertEqual(self.dealt(t), 20)
                self.assertEqual(BURNED in t.conditions(self.opp), not opp_energy)

    # --- Cape of Toughness DAA 160 -----------------------------------------
    async def test_cape_of_toughness_basic_gets_50(self):
        t = self.table()
        tn = self.mine(t, TYPE_NULL, WATER, 0)
        cape = t.put(CAPE, P1, 'hand')
        await t.play(cape, targets=[tn.entity_id])
        self.assertIn(cape, tn.children)
        self.assertEqual(t.hp(tn), 150)
        self.assertEqual(t.damage(tn), 0)

    async def test_cape_of_toughness_not_on_stage1(self):
        t = self.table()
        silv = self.mine(t, SILVALLY, WATER, 0)
        cape = t.put(CAPE, P1, 'hand')
        await t.play(cape, targets=[silv.entity_id])
        self.assertIn(cape, silv.children)
        self.assertEqual(t.hp(silv), 140)

    # --- Virbank City Gym PLS 126 ------------------------------------------
    async def test_virbank_poison_counters_both_sides(self):
        for stadium in (True, False):
            t = self.table()
            me = self.mine(t, self.filler, WATER, 0)
            me.set_attribute(AttrID.HP, 300)
            if stadium:
                t.stadium(VIRBANK, P2)
            me.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
            self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
            await t.checkup()
            want = 30 if stadium else 10
            with self.subTest(stadium=stadium):
                self.assertEqual(300 - t.hp(me), want)
                self.assertEqual(self.dealt(t), want)

    # --- Defiance Vest PAR 162 ---------------------------------------------
    async def test_defiance_vest_more_prizes_reduces_40(self):
        for mine_prizes, opp_prizes, reduced in ((4, 3, True), (3, 3, False), (2, 3, False)):
            t = self.table()
            me = self.mine(t, self.filler, WATER, 0)
            me.set_attribute(AttrID.HP, 400)
            vest = t.put(VEST, P1, 'hand')
            await t.play(vest, targets=[me.entity_id])
            self.assertIn(vest, me.children)
            t.set_prizes(P1, mine_prizes)
            t.set_prizes(P2, opp_prizes)
            dmg = await self.opp_hits(t)
            with self.subTest(mine=mine_prizes, opp=opp_prizes):
                self.assertEqual(400 - t.hp(me), max(0, dmg - 40) if reduced else dmg)

    # --- Quilladin CRI 6: Leafy Charge -------------------------------------
    async def test_quilladin_leafy_charge_attaches_basic_grass(self):
        t = self.table()
        q = self.mine(t, QUILLADIN, GRASS, 1)
        grass = t.put(t.basic_energy(GRASS), P1, 'deck')
        water = t.put(t.basic_energy(WATER), P1, 'deck')
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), [grass])[1]
        await t.attack(q, 'Leafy Charge')
        self.assertEqual(self.dealt(t), 20)
        self.assertIn(grass, q.children)
        self.assertNotIn(water, seen)
        self.assertIn(water, t.zone(P1, 'deck'))

    async def test_quilladin_leafy_charge_no_grass_still_damages(self):
        t = self.table()
        q = self.mine(t, QUILLADIN, GRASS, 1)
        t.put(t.basic_energy(WATER), P1, 'deck')
        await t.attack(q, 'Leafy Charge')
        self.assertEqual(self.dealt(t), 20)
        self.assertEqual(len(q.children), 1)


if __name__ == '__main__':
    unittest.main()
