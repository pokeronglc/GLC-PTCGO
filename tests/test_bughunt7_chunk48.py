"""Bug hunt round 7, chunk 48: Treasure Energy, Beach Court, Maxie's Hidden
Ball Trick, Cassiopeia, Torkoal, Boomerang Energy, Venipede line, Jellicent,
Tentacool/Tentacruel, Lumineon, Alolan Grimer -- each checked against its
printed text, including the cases where it should NOT work.
(Antique Old Amber is already covered by tests/test_antique_fossil_abilities.py.)"""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED, PARALYZED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, DARK = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.DARKNESS
LIGHTNING, METAL = PokemonTypes.LIGHTNING, PokemonTypes.METAL

TREASURE, BOOMERANG = 'SWSH7.TreasureEnergy_165', 'SV06.BoomerangEnergy_166'
BEACH = 'SV1.BeachCourt_167'
MAXIE, CASSIOPEIA = 'XY5.MaxiesHiddenBallTrick_133', 'SV065.Cassiopeia_56'
TORKOAL = 'SV1.Torkoal_35'
VENIPEDE, WHIRLIPEDE, SCOLIPEDE = 'SWSH6.Venipede_105', 'ZSV10PT5.Whirlipede_55', 'SV06.Scolipede_117'
JELLICENT = 'BW7.Jellicent_45'
TENTACOOL, TENTACRUEL = 'SM2.Tentacool_23', 'SM10.Tentacruel_41'
LUMINEON, AGRIMER = 'SM11.Lumineon_40', 'SM11.AlolanGrimer_127'
ZERAORA, EXCADRILL = 'SV05.Zeraora_57', 'SWSH4.Excadrill_122'
KLAWF, POTION = 'SV1.Klawf_122', 'SV1.Potion_188'


class Chunk48(unittest.IsolatedAsyncioTestCase):
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

    def mine(self, t, spec, kind=None, count=0, zone='active', pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if count:
            t.energy(p, kind, count)
        return p

    def dmg(self, p):
        return 400 - p.get_attribute(AttrID.HP, 0)

    def hand_only(self, t, spec, pid=P1):
        for c in t.zone(pid, 'hand'):
            t.board.find_player_area(pid, 'hand').remove_child(c)
        return t.put(spec, pid, 'hand')

    # --- Treasure Energy ---------------------------------------------------
    async def take_prize(self, t, card):
        area = t.board.find_player_area(P1, 'prizePile')
        area.children.remove(card)
        area.children.insert(0, card)          # first prize, whoever picks

        async def pick(player_id, ids, count, minimum=None):
            return [card.entity_id]
        with patch.object(t.session, '_prompt_prize_pick', pick):
            return await t._run(lambda: t.session._take_prizes(P1, 1))

    async def test_treasure_energy_attaches_when_taken_on_your_turn(self):
        t = self.table()
        me = self.mine(t, self.filler)
        t.set_prizes(P1, 3)
        treasure = t.put(TREASURE, P1, 'prizes')
        t.yes = True
        await self.take_prize(t, treasure)
        self.assertIs(treasure.parent, me)

    async def test_treasure_energy_declined_goes_to_hand(self):
        t = self.table()
        self.mine(t, self.filler)
        t.set_prizes(P1, 3)
        treasure = t.put(TREASURE, P1, 'prizes')
        t.yes = False
        await self.take_prize(t, treasure)
        self.assertIn(treasure, t.zone(P1, 'hand'))

    async def test_treasure_energy_not_offered_on_opponents_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        t.set_prizes(P1, 3)
        treasure = t.put(TREASURE, P1, 'prizes')
        t.next_turn()
        t.yes = True
        await self.take_prize(t, treasure)
        self.assertIn(treasure, t.zone(P1, 'hand'))

    # --- Beach Court -------------------------------------------------------
    async def test_beach_court_basic_both_sides_but_not_stage1(self):
        t = self.table()
        me = self.mine(t, TORKOAL)                       # Basic, retreat 3
        whirl = self.mine(t, WHIRLIPEDE, zone='bench')  # Stage 1, retreat 3
        opp_base = t.retreat(self.opp)
        t.stadium(BEACH, P1)
        self.assertEqual(t.retreat(me), 2)
        self.assertEqual(t.retreat(whirl), 3)
        self.assertEqual(t.retreat(self.opp), max(0, opp_base - 1))

    # --- Maxie's Hidden Ball Trick ----------------------------------------
    async def test_maxie_benches_fighting_and_draws_5(self):
        t = self.table()
        self.mine(t, self.filler)
        klawf = t.put(KLAWF, P1, 'discard')
        maxie = self.hand_only(t, MAXIE)
        self.assertTrue(t.can(maxie, 'UseTrainerCard'))
        await t.play(maxie)
        self.assertIn(klawf, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 5)

    async def test_maxie_not_last_card_or_no_fighting(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(KLAWF, P1, 'discard')
        maxie = self.hand_only(t, MAXIE)
        t.put(self.item, P1, 'hand')
        self.assertFalse(t.can(maxie, 'UseTrainerCard'))
        t2 = self.table()
        self.mine(t2, self.filler)
        t2.put(TENTACOOL, P1, 'discard')                # Water, not Fighting
        maxie2 = self.hand_only(t2, MAXIE)
        self.assertFalse(t2.can(maxie2, 'UseTrainerCard'))

    # --- Cassiopeia --------------------------------------------------------
    async def test_cassiopeia_last_card_searches_2(self):
        t = self.table()
        self.mine(t, self.filler)
        a, b = t.deck(P1, [TORKOAL, KLAWF])
        cass = self.hand_only(t, CASSIOPEIA)
        self.assertTrue(t.can(cass, 'UseTrainerCard'))
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in (a, b)][:count]
        await t.play(cass)
        hand = t.zone(P1, 'hand')
        self.assertIn(a, hand)
        self.assertIn(b, hand)
        self.assertEqual(len(hand), 2)

    # BUG: standard_trainer_condition only knows "play this card only when" / "use this card only if"; Cassiopeia's "use this card only when" wording is ignored
    async def test_cassiopeia_not_playable_with_other_cards(self):
        t = self.table()
        self.mine(t, self.filler)
        cass = self.hand_only(t, CASSIOPEIA)
        t.put(self.item, P1, 'hand')
        self.assertFalse(t.can(cass, 'UseTrainerCard'))

    # --- Torkoal -----------------------------------------------------------
    async def test_torkoal_concentrated_fire_flips_per_fire_energy(self):
        t = self.table()
        me = self.mine(t, TORKOAL, FIRE, 2)
        t.energy(me, WATER, 1)
        flips = []
        t.heads = lambda title: flips.append(title) or True
        await t.attack(me, 'Concentrated Fire')
        self.assertEqual(len(flips), 2)
        self.assertEqual(self.dmg(self.opp), 160)

    async def test_torkoal_concentrated_fire_tails_does_nothing(self):
        t = self.table()
        me = self.mine(t, TORKOAL, FIRE, 3)
        t.heads = False
        await t.attack(me, 'Concentrated Fire')
        self.assertEqual(self.dmg(self.opp), 0)

    # --- Boomerang Energy --------------------------------------------------
    async def test_boomerang_reattaches_after_own_attack_discards_it(self):
        t = self.table()
        me = self.mine(t, ZERAORA, LIGHTNING, 2)
        boom = t.put(BOOMERANG, P1, 'hand')
        await t.play(boom, targets=[me.entity_id])
        self.assertIs(boom.parent, me)
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is boom][:1] or cards[:count]
        await t.attack(me, 'Strong Volt')
        self.assertEqual(self.dmg(self.opp), 120)
        self.assertIs(boom.parent, me)

    async def test_boomerang_stays_discarded_by_opponents_attack(self):
        t = self.table()
        me = self.mine(t, self.filler)
        me.set_attribute(AttrID.HP, 400)
        boom = t.put(BOOMERANG, P1, 'hand')
        await t.play(boom, targets=[me.entity_id])
        t.next_turn()
        exc = self.mine(t, EXCADRILL, METAL, 2, zone='bench', pid=P2)
        bench = t.board.find_player_area(P2, 'bench')
        active = t.board.find_player_area(P2, 'activePokemonArea')
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        t.board.move_card(exc.entity_id, active.entity_id)
        await t.attack(exc, 'Drill Run', pid=P2)
        self.assertIn(boom, t.zone(P1, 'discard'))

    # --- Venipede / Whirlipede / Scolipede --------------------------------
    async def test_venipede_poison_sting(self):
        t = self.table()
        me = self.mine(t, VENIPEDE, DARK, 1)
        await t.attack(me, 'Poison Sting')
        self.assertIn(POISONED, t.conditions(self.opp))
        self.assertEqual(self.dmg(self.opp), 10)

    async def test_whirlipede_venoshock(self):
        t = self.table()
        me = self.mine(t, WHIRLIPEDE, DARK, 1)
        await t.attack(me, 'Venoshock')
        self.assertEqual(self.dmg(self.opp), 30)
        t2 = self.table()
        me2 = self.mine(t2, WHIRLIPEDE, DARK, 1)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t2.attack(me2, 'Venoshock')
        self.assertEqual(self.dmg(self.opp), 90)

    async def test_scolipede_dastardly_jab_leaves_10_ignores_weakness(self):
        t = self.table()
        me = self.mine(t, SCOLIPEDE, DARK, 2)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [DARK.value])
        self.opp.set_attribute(AttrID.HP, 350)
        await t.attack(me, 'Dastardly Jab')
        self.assertEqual(t.hp(self.opp), 10)
        self.assertIn(self.opp, t.zone(P2, 'active'))

    async def test_scolipede_dastardly_jab_at_10_does_nothing(self):
        t = self.table()
        me = self.mine(t, SCOLIPEDE, DARK, 2)
        self.opp.set_attribute(AttrID.HP, 10)
        await t.attack(me, 'Dastardly Jab')
        self.assertEqual(t.hp(self.opp), 10)
        self.assertIn(self.opp, t.zone(P2, 'active'))

    # --- Jellicent ---------------------------------------------------------
    async def test_jellicent_stickiness_opponent_only(self):
        t = self.table()
        me = self.mine(t, TORKOAL)
        base_opp, base_me = t.retreat(self.opp), t.retreat(me)
        self.mine(t, JELLICENT, zone='bench')
        self.assertEqual(t.retreat(self.opp), base_opp + 1)
        self.assertEqual(t.retreat(me), base_me)

    async def test_jellicent_eerie_light(self):
        t = self.table()
        me = self.mine(t, JELLICENT, WATER, 3)
        t.heads = True
        await t.attack(me, 'Eerie Light')
        self.assertIn(CONFUSED, t.conditions(self.opp))
        self.assertEqual(self.dmg(self.opp), 40)
        t2 = self.table()
        me2 = self.mine(t2, JELLICENT, WATER, 3)
        t2.heads = False
        await t2.attack(me2, 'Eerie Light')
        self.assertNotIn(CONFUSED, t2.conditions(self.opp))

    # --- Tentacool ---------------------------------------------------------
    # BUG: Sludge Shock's "can't be healed during your opponent's next turn" is not implemented (standard_attack does only the 10 damage)
    async def test_tentacool_sludge_shock_blocks_healing_next_turn(self):
        t = self.table()
        self.opp.set_attribute(AttrID.HP, t.damage(self.opp) + t.hp(self.opp))  # real max HP
        me = self.mine(t, TENTACOOL, WATER, 1)
        await t.attack(me, 'Sludge Shock')
        self.assertEqual(t.damage(self.opp), 10)
        t.next_turn()
        potion = t.put(POTION, P2, 'hand')
        if t.can(potion, 'UseTrainerCard', pid=P2):
            await t.play(potion, pid=P2)
        self.assertEqual(t.damage(self.opp), 10)

    async def test_tentacool_heal_block_expires(self):
        t = self.table()
        self.opp.set_attribute(AttrID.HP, t.damage(self.opp) + t.hp(self.opp))  # real max HP
        me = self.mine(t, TENTACOOL, WATER, 1)
        await t.attack(me, 'Sludge Shock')
        t.next_turn()
        t.next_turn()
        t.next_turn()          # opponent's turn after next: healing allowed
        potion = t.put(POTION, P2, 'hand')
        self.assertTrue(t.can(potion, 'UseTrainerCard', pid=P2))
        await t.play(potion, pid=P2)
        self.assertEqual(t.damage(self.opp), 0)

    # --- Tentacruel --------------------------------------------------------
    async def test_tentacruel_wicked_tentacles_moves_and_places_counters(self):
        t = self.table()
        me = self.mine(t, TENTACRUEL, WATER, 1)
        energy = t.energy(self.opp, WATER, 1)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 400)
        t.picks = lambda cards, count, prompt, display: cards[:count]
        t.pokemon = lambda cands, prompt: bench if bench in cands else cands[0]
        await t.attack(me, 'Wicked Tentacles')
        self.assertIs(energy.parent, bench)
        self.assertEqual(400 - t.hp(bench), 30)
        self.assertEqual(self.dmg(self.opp), 0)

    async def test_tentacruel_wicked_tentacles_no_energy_no_counters(self):
        t = self.table()
        me = self.mine(t, TENTACRUEL, WATER, 1)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 400)
        await t.attack(me, 'Wicked Tentacles')
        self.assertEqual(t.hp(bench), 400)
        self.assertEqual(self.dmg(self.opp), 0)
        self.assertEqual(len(me.children), 1)          # own Energy untouched

    async def test_tentacruel_wrap(self):
        t = self.table()
        me = self.mine(t, TENTACRUEL, WATER, 3)
        t.heads = True
        await t.attack(me, 'Wrap')
        self.assertIn(PARALYZED, t.conditions(self.opp))
        self.assertEqual(self.dmg(self.opp), 60)
        t2 = self.table()
        me2 = self.mine(t2, TENTACRUEL, WATER, 3)
        t2.heads = False
        await t2.attack(me2, 'Wrap')
        self.assertNotIn(PARALYZED, t2.conditions(self.opp))

    # --- Lumineon ----------------------------------------------------------
    async def test_lumineon_neon_trickery_may_move(self):
        for yes in (True, False):
            with self.subTest(yes=yes):
                t = self.table()
                me = self.mine(t, LUMINEON, WATER, 2)
                energy = t.energy(self.opp, WATER, 1)
                bench = t.put(self.filler, P2, 'bench')
                t.yes = yes
                t.picks = (lambda cards, count, prompt, display: cards[:count]) if yes \
                    else (lambda cards, count, prompt, display: [])
                await t.attack(me, 'Neon Trickery')
                self.assertEqual(self.dmg(self.opp), 50)
                self.assertIs(energy.parent, bench if yes else self.opp)

    # --- Alolan Grimer -----------------------------------------------------
    async def test_alolan_grimer_collect_draws_2(self):
        t = self.table()
        me = self.mine(t, AGRIMER)
        before = len(t.zone(P1, 'hand'))
        self.assertIsNotNone(t.attack_offer(me, 'Collect'))
        await t.attack(me, 'Collect')
        self.assertEqual(len(t.zone(P1, 'hand')), before + 2)
        self.assertEqual(self.dmg(self.opp), 0)


if __name__ == '__main__':
    unittest.main()
