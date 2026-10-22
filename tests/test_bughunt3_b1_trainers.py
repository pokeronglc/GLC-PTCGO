"""Bug hunt round 3, batch 1: Items, Supporters, Stadium and Special Energy,
through the real play executor (so play conditions apply)."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W, F, R, G = PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.FIRE, PokemonTypes.GRASS
HAMMER, RAFT, TIMER = 'CZ.CrushingHammer_125', 'DM.SwitchRaft_62', 'SM1.TimerBall_134'
SHOES, GHETSIS, MFS = 'CZ.TrekkingShoes_145', 'BW9.Ghetsis_101', 'SWSH11.MissFortuneSisters_164'
WASH, COMPRESSOR = 'SWSH4.WashWaterEnergy_165', 'XY4.BattleCompressorTeamFlareGear_92'
SCORCHED, CLAY = 'XY10.ScorchedEarth_110', 'SM12.Clay_188'
GUIDANCE, THORTON = 'SV085.ExplorersGuidance_107', 'SWSH11.Thorton_167'
HORSEA, SEADRA, MARILL, BONSLY = 'SWSH45.Horsea_20', 'SWSH11.Seadra_36', 'SM3.Marill_34', 'SV3.Bonsly_110'
DEERLING, SAWSBUCK, MACHOKE = 'XY10.Deerling_8', 'SM12.Sawsbuck_16', 'SM2.Machoke_64'
GUZMA, NEST = 'SM3.Guzma_115', 'SV1.NestBall_181'


class B1Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, p):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, 400)
        return p

    def table(self, me=None, opp=None):
        t = Table(self)
        self.me = t.put(me or self.filler, P1, 'active')
        self.opp = self.neutral(t.put(opp or self.filler, P2, 'active'))
        return t

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Crushing Hammer ------------------------------------------------------
    async def test_crushing_hammer_heads_discards_opponent_energy(self):
        t = self.table()
        e = t.energy(self.opp, W)
        mine = t.energy(self.me, W)
        t.heads = True
        await t.play(t.put(HAMMER, P1, 'hand'))
        self.assertIn(e, t.zone(P2, 'discard'))
        self.assertIn(mine, t.board.attached_energies(self.me))

    async def test_crushing_hammer_tails_nothing(self):
        t = self.table()
        e = t.energy(self.opp, W)
        t.heads = False
        await t.play(t.put(HAMMER, P1, 'hand'))
        self.assertIn(e, t.board.attached_energies(self.opp))

    async def test_crushing_hammer_needs_opponent_energy(self):
        t = self.table()
        t.energy(self.me, W)
        self.assertFalse(t.can(t.put(HAMMER, P1, 'hand'), 'UseTrainerCard'))

    # --- Switch Raft ------------------------------------------------------------
    async def test_switch_raft_heals_the_water_pokemon_moved_to_bench(self):
        t = Table(self)
        horsea = t.put(SEADRA, P1, 'active', hp=30)         # 50 damage
        new = t.put(self.filler, P1, 'bench')
        self.neutral(t.put(self.filler, P2, 'active'))
        await t.play(t.put(RAFT, P1, 'hand'))
        self.assertIs(t.active(P1), new)
        self.assertEqual(t.damage(horsea), 20)

    async def test_switch_raft_needs_a_water_active(self):
        t = self.table()                                     # Colorless Active
        t.put(SEADRA, P1, 'bench')
        self.assertFalse(t.can(t.put(RAFT, P1, 'hand'), 'UseTrainerCard'))

    async def test_switch_raft_needs_a_bench(self):
        t = self.table(me=SEADRA)
        self.assertFalse(t.can(t.put(RAFT, P1, 'hand'), 'UseTrainerCard'))

    # --- Timer Ball ---------------------------------------------------------------
    async def test_timer_ball_one_evolution_per_heads(self):
        for heads, expected in ((True, 2), (False, 0)):
            t = self.table()
            t.deck(P1, [SEADRA, SAWSBUCK, MACHOKE, HORSEA, DEERLING])
            t.heads = heads
            await t.play(t.put(TIMER, P1, 'hand'))
            hand = t.zone(P1, 'hand')
            with self.subTest(heads=heads):
                self.assertEqual(len(hand), expected)
                self.assertFalse({'Horsea', 'Deerling'} & set(t.names(hand)))

    # --- Trekking Shoes --------------------------------------------------------------
    def _choice(self, index):
        async def present(ctx, card, prompt, buttons, player_id=None):
            return index
        return patch.object(EffectContext, 'present_card_choice', present)

    async def test_trekking_shoes_keep_top_card(self):
        t = self.table()
        top = t.deck(P1, [GUZMA])[0]
        with self._choice(0):
            await t.play(t.put(SHOES, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [top])
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    async def test_trekking_shoes_discard_then_draw(self):
        t = self.table()
        top = t.deck(P1, [GUZMA])[0]
        with self._choice(1):
            await t.play(t.put(SHOES, P1, 'hand'))
        self.assertIn(top, t.zone(P1, 'discard'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 1)
        self.assertNotIn(top, hand)
        self.assertEqual(len(t.zone(P1, 'deck')), 29)

    # --- Ghetsis -----------------------------------------------------------------------
    async def test_ghetsis_shuffles_opponent_items_and_i_draw_that_many(self):
        t = self.table()
        items = [t.put(NEST, P2, 'hand') for _ in range(3)]
        keep = t.put(GUZMA, P2, 'hand')
        await t.play(t.put(GHETSIS, P1, 'hand'))
        self.assertEqual(t.zone(P2, 'hand'), [keep])
        self.assertTrue(all(c in t.zone(P2, 'deck') for c in items))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_ghetsis_no_items_no_draw(self):
        t = self.table()
        t.put(GUZMA, P2, 'hand')
        await t.play(t.put(GHETSIS, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)

    # --- Miss Fortune Sisters ------------------------------------------------------------
    async def test_miss_fortune_sisters_discards_items_from_top_five(self):
        t = Table(self, filler_deck=0)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        deep = t.deck(P2, [NEST])                            # 6th from top: not looked at
        top = t.deck(P2, [NEST, GUZMA, NEST, HORSEA, GUZMA])
        await t.play(t.put(MFS, P1, 'hand'))
        discard = t.zone(P2, 'discard')
        self.assertEqual(len(discard), 2)
        self.assertTrue(all(self.name(c) == 'Nest Ball' for c in discard))
        self.assertIn(deep[0], t.zone(P2, 'deck'))
        self.assertEqual(len(t.zone(P2, 'deck')), 4)

    # --- Wash Water Energy ------------------------------------------------------------------
    async def _bonsly_hits(self, holder_spec):
        t = Table(self)
        holder = self.neutral(t.put(holder_spec, P1, 'active'))
        wash = t.put(WASH, P1, 'hand')
        await t.play(wash, targets=[holder.entity_id])
        bonsly = t.put(BONSLY, P2, 'active')
        t.next_turn()
        await t.attack(bonsly, 'Blubbering', pid=P2)
        return t, holder, wash

    async def test_wash_water_blocks_attack_effects_on_water_pokemon(self):
        t, holder, wash = await self._bonsly_hits(SEADRA)
        self.assertIn(wash, t.board.attached_energies(holder))
        self.assertEqual(400 - t.hp(holder), 10)            # damage is not an effect
        self.assertNotIn(CONFUSED, t.conditions(holder))

    async def test_wash_water_no_protection_on_non_water(self):
        t, holder, _ = await self._bonsly_hits(self.filler)
        self.assertIn(CONFUSED, t.conditions(holder))

    async def test_wash_water_provides_water(self):
        t = Table(self)
        seadra = t.put(SEADRA, P1, 'active')
        self.neutral(t.put(self.filler, P2, 'active'))
        await t.play(t.put(WASH, P1, 'hand'), targets=[seadra.entity_id])
        self.assertIsNotNone(t.attack_offer(seadra, 'Hydro Jet'))   # cost [W]

    # --- Battle Compressor Team Flare Gear (reprint-level check) --------------------------------
    async def test_battle_compressor_discards_up_to_three(self):
        t = self.table()
        await t.play(t.put(COMPRESSOR, P1, 'hand'))
        self.assertEqual(len([c for c in t.zone(P1, 'discard')
                              if self.name(c) != 'Battle Compressor Team Flare Gear']), 3)
        self.assertEqual(len(t.zone(P1, 'deck')), 27)

    # --- Scorched Earth ---------------------------------------------------------------------------
    def _stadium_entry(self, t, stadium, pid):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_scorched_earth_fire_or_fighting_energy_for_two_cards(self):
        t = self.table()
        stadium = t.stadium(SCORCHED, P2)                  # opponent's Stadium works for me
        fighting = t.put(t.basic_energy(F), P1, 'hand')
        entry = self._stadium_entry(t, stadium, P1)
        self.assertIsNotNone(entry)
        await t.do(entry, pid=P1)
        self.assertIn(fighting, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertIsNone(self._stadium_entry(t, stadium, P1), 'once per turn')
        t.next_turn()
        t.put(t.basic_energy(R), P2, 'hand')
        self.assertIsNotNone(self._stadium_entry(t, stadium, P2))

    async def test_scorched_earth_not_with_other_energy(self):
        t = self.table()
        stadium = t.stadium(SCORCHED, P1)
        t.put(t.basic_energy(W), P1, 'hand')
        t.put(GUZMA, P1, 'hand')
        self.assertIsNone(self._stadium_entry(t, stadium, P1))

    # --- Clay -------------------------------------------------------------------------------------
    async def test_clay_mills_seven_keeps_items(self):
        t = Table(self, filler_deck=0)
        self.me = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.deck(P1, [GUZMA] * 3)                            # below the top 7
        top = t.deck(P1, [NEST, GUZMA, NEST, HORSEA, GUZMA, NEST, GUZMA])
        await t.play(t.put(CLAY, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Nest Ball'] * 3)
        self.assertEqual(len(t.zone(P1, 'deck')), 3)
        self.assertEqual(len([c for c in t.zone(P1, 'discard') if c in top]), 4)

    # --- Explorer's Guidance (reprint) ----------------------------------------------------------------
    async def test_explorers_guidance_take_two_of_six_discard_rest(self):
        t = self.table()
        top = t.deck(P1, [GUZMA, HORSEA, NEST, GUZMA, HORSEA, MARILL])
        await t.play(t.put(GUIDANCE, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        self.assertEqual(len([c for c in t.zone(P1, 'discard') if c in top]), 4)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)

    # --- Thorton ----------------------------------------------------------------------------------------
    async def test_thorton_swaps_basic_keeping_damage_and_energy(self):
        t = Table(self)
        old = t.put(HORSEA, P1, 'active', hp=20)             # 20 damage
        e = t.energy(old, W)
        self.neutral(t.put(self.filler, P2, 'active'))
        new = t.put(MARILL, P1, 'discard')
        await t.play(t.put(THORTON, P1, 'hand'))
        active = t.active(P1)
        self.assertEqual(self.name(active), 'Marill')
        self.assertEqual(t.damage(active), 20)
        self.assertIn(e, t.board.attached_energies(active))
        self.assertIn('Horsea', t.names(t.zone(P1, 'discard')))

    async def test_thorton_needs_basic_in_discard_and_in_play(self):
        t = Table(self)
        t.put(SEADRA, P1, 'active')                          # Stage 1 only in play
        t.put(MARILL, P1, 'discard')
        self.assertFalse(t.can(t.put(THORTON, P1, 'hand'), 'UseTrainerCard'))
        t2 = Table(self)
        t2.put(HORSEA, P1, 'active')
        t2.put(SEADRA, P1, 'discard')                        # no Basic in discard
        self.assertFalse(t2.can(t2.put(THORTON, P1, 'hand'), 'UseTrainerCard'))


if __name__ == '__main__':
    unittest.main()
