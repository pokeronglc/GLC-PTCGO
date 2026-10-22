"""Bug hunt round 7, chunk 27: Spiky Energy, Regigigas, Steven's Resolve,
Team Skull Grunt, Great Ball, Levincia, Calamitous Snowy Mountain, Jamming Tower,
Metal Core Barrier, Jessie & James, Trick Shovel, Barboach, Whiscash, Phanpy,
Donphan -- each checked against its printed text, including the cases where it
should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT, LIGHTNING = (PokemonTypes.FIRE, PokemonTypes.WATER,
                                 PokemonTypes.FIGHTING, PokemonTypes.LIGHTNING)

SPIKY = 'SV09.SpikyEnergy_159'
REGIGIGAS = 'SM4.Regigigas_84'
REGIS = ['SM4.Regice_28', 'SM4.Regirock_53', 'SM4.Registeel_68']
STEVEN = 'SM7.StevensResolve_145'
GRUNT = 'SM1.TeamSkullGrunt_133'
GREAT_BALL = 'SV2.GreatBall_183'
LEVINCIA = 'SV09.Levincia_150'
SNOWY = 'SV2.CalamitousSnowyMountain_174'
JAMMING = 'SV06.JammingTower_153'
MCB = 'SM10.MetalCoreBarrier_180'
JJ = 'HF.JessieJames_58'
SHOVEL = 'XY2.TrickShovel_98'
BARBOACH, WHISCASH = 'SV3.Barboach_108', 'SV3.Whiscash_109'
PHANPY, DONPHAN = 'SWSH12.Phanpy_91', 'SV045.Donphan_49'
AGGRON = 'SM10.Aggron_125'          # Metal Stage 2
ALOMOMOLA = 'SV1.Alomomola_48'      # Water Basic


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk27(unittest.IsolatedAsyncioTestCase):
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

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None):
        p = t.put(spec, P1, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def is_energy(self, card):
        return card.archetype_id.lower() in {g.lower() for g in self.energies.values()}

    def dealt(self):
        return 400 - self.opp.get_attribute(AttrID.HP)

    async def opp_hits(self, t, target_hp=None):
        """P2's Snorlax uses Heavy Impact (80) on P1's Active."""
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)

    # --- Spiky Energy JTG 159 -------------------------------------------------
    async def test_spiky_energy_active_hit_puts_2_counters_on_attacker(self):
        t = self.table()
        me = self.mine(t, self.filler, hp=300)
        await t.play(t.put(SPIKY, P1, 'hand'), targets=[me.entity_id])
        await self.opp_hits(t)
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(me.get_attribute(AttrID.HP), 220)

    async def test_spiky_energy_triggers_even_if_knocked_out(self):
        t = self.table()
        me = self.mine(t, self.filler, hp=50)
        self.mine(t, self.filler, zone='bench')
        await t.play(t.put(SPIKY, P1, 'hand'), targets=[me.entity_id])
        await self.opp_hits(t)
        self.assertIn(me, t.zone(P1, 'discard'))
        self.assertEqual(self.dealt(), 20)

    async def test_spiky_energy_not_on_own_attack(self):
        # Attacking with the Spiky Energy Pokémon does nothing to the opponent extra.
        t = self.table()
        me = self.mine(t, self.filler, WATER, 3)
        await t.play(t.put(SPIKY, P1, 'hand'), targets=[me.entity_id])
        await t.attack(me, 'Heavy Impact')
        self.assertEqual(self.dealt(), 80)
        self.assertEqual(t.damage(me), 0)

    # --- Regigigas CIN 84 ----------------------------------------------------
    async def test_regigigas_cannot_attack_without_all_three_regis(self):
        t = self.table()
        gigas = self.mine(t, REGIGIGAS, WATER, 5)
        for spec in REGIS[:2]:
            self.mine(t, spec, zone='bench')
        self.assertIsNone(t.attack_offer(gigas, 'Giant Stomp'))

    async def test_regigigas_regis_in_hand_dont_count(self):
        t = self.table()
        gigas = self.mine(t, REGIGIGAS, WATER, 5)
        for spec in REGIS[:2]:
            self.mine(t, spec, zone='bench')
        t.put(REGIS[2], P1, 'hand')
        self.assertIsNone(t.attack_offer(gigas, 'Giant Stomp'))

    async def test_regigigas_giant_stomp_discards_stadium(self):
        t = self.table()
        gigas = self.mine(t, REGIGIGAS, WATER, 5)
        for spec in REGIS:
            self.mine(t, spec, zone='bench')
        stadium = t.stadium(JAMMING, P2)
        await t.attack(gigas, 'Giant Stomp')
        self.assertEqual(self.dealt(), 160)
        self.assertIn(stadium, t.zone(P2, 'discard'))
        self.assertEqual(list(t.board.find_global_area('activeStadium').children), [])

    # --- Steven's Resolve CES 145 --------------------------------------------
    async def test_stevens_resolve_takes_three_and_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        wanted = t.deck(P1, [GRUNT, LEVINCIA, PHANPY, BARBOACH])
        self.clear_hand(t)
        card = t.put(STEVEN, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c in wanted][:count]
        ended = await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertTrue(all(c in wanted for c in hand))
        self.assertTrue(ended)

    async def test_stevens_resolve_may_take_zero_still_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        deck_before = len(t.zone(P1, 'deck'))
        card = t.put(STEVEN, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        ended = await t.play(card)
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before)
        self.assertTrue(ended)

    # --- Team Skull Grunt SUM 133 --------------------------------------------
    async def test_team_skull_grunt_discards_two_energy_only(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t, P2)
        e = [t.put(t.basic_energy(k), P2, 'hand') for k in (FIRE, WATER, FIGHT)]
        other = t.put(self.item, P2, 'hand')
        await t.play(t.put(GRUNT, P1, 'hand'))
        disc = t.zone(P2, 'discard')
        self.assertEqual(sum(1 for c in e if c in disc), 2)
        self.assertIn(other, t.zone(P2, 'hand'))
        self.assertEqual(len(t.zone(P2, 'hand')), 2)

    async def test_team_skull_grunt_no_energy_discards_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t, P2)
        cards = [t.put(self.item, P2, 'hand'), t.put(PHANPY, P2, 'hand')]
        grunt = t.put(GRUNT, P1, 'hand')
        if t.can(grunt, 'UseTrainerCard'):
            await t.play(grunt)
        self.assertEqual(t.zone(P2, 'hand'), cards)
        self.assertEqual(t.zone(P2, 'discard'), [])

    # --- Great Ball PAL 183 --------------------------------------------------
    async def test_great_ball_finds_pokemon_in_top_seven(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.deck(P1, [PHANPY])                 # top card
        t.deck(P1, [self.item] * 6)          # 6 more on top -> Phanpy is 7th
        await t.play(t.put(GREAT_BALL, P1, 'hand'))
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Phanpy'])

    async def test_great_ball_misses_eighth_card(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.deck(P1, [PHANPY])
        t.deck(P1, [self.item] * 7)          # Phanpy is 8th
        await t.play(t.put(GREAT_BALL, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertIn(7, t.shown)

    # --- Levincia JTG 150 ----------------------------------------------------
    async def _levincia(self, t, pid=P1):
        stadium = t.board.find_global_area('activeStadium').children[0]
        entries = t.offers(stadium, None, pid)
        if not entries:
            return False
        await t.do(entries[0], pid=pid)
        return True

    # BUG: Levincia's Stadium Effect does nothing (no handler for "that player may put up to 2 Basic Lightning Energy ... into their hand")
    async def test_levincia_two_basic_lightning_from_discard(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        t.stadium(LEVINCIA, P2)
        lights = [t.put(t.basic_energy(LIGHTNING), P1, 'discard') for _ in range(3)]
        fire = t.put(t.basic_energy(FIRE), P1, 'discard')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.extend(cards), list(cards)[:count])[1]
        self.assertTrue(await self._levincia(t))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(c in lights for c in hand))
        self.assertNotIn(fire, offered)
        self.assertFalse(await self._levincia(t))    # once per turn

    async def test_levincia_not_offered_without_lightning(self):
        t = self.table()
        self.mine(t, self.filler)
        t.stadium(LEVINCIA, P1)
        t.put(t.basic_energy(FIRE), P1, 'discard')
        self.assertFalse(await self._levincia(t))

    async def test_levincia_opponent_can_use_too(self):
        t = self.table()
        self.mine(t, self.filler)
        t.stadium(LEVINCIA, P1)
        t.next_turn()
        self.clear_hand(t, P2)
        t.put(t.basic_energy(LIGHTNING), P2, 'discard')
        stadium = t.board.find_global_area('activeStadium').children[0]
        self.assertTrue(t.offers(stadium, None, P2))     # offered to either player

    # --- Calamitous Snowy Mountain PAL 174 -----------------------------------
    async def test_snowy_mountain_basic_non_water_takes_20(self):
        t = self.table()
        me = self.mine(t, self.filler)
        t.stadium(SNOWY, P2)
        await t.play(t.put(t.basic_energy(FIRE), P1, 'hand'), targets=[me.entity_id])
        self.assertEqual(t.damage(me), 20)

    async def test_snowy_mountain_water_and_evolved_unaffected(self):
        t = self.table()
        water = self.mine(t, ALOMOMOLA)
        aggron = self.mine(t, AGGRON, zone='bench')
        t.stadium(SNOWY, P1)
        await t.play(t.put(t.basic_energy(FIRE), P1, 'hand'), targets=[water.entity_id])
        self.assertEqual(t.damage(water), 0)
        t.state.energy_attached_this_turn = False
        if hasattr(t.state, 'energy_attachments_this_turn'):
            t.state.energy_attachments_this_turn = 0
        t.attach(t.basic_energy(FIRE), aggron)    # not from hand via play: no trigger expected
        self.assertEqual(t.damage(aggron), 0)

    async def test_snowy_mountain_stage2_attach_from_hand_no_damage(self):
        t = self.table()
        aggron = self.mine(t, AGGRON)
        t.stadium(SNOWY, P1)
        await t.play(t.put(t.basic_energy(FIRE), P1, 'hand'), targets=[aggron.entity_id])
        self.assertEqual(len([c for c in aggron.children if self.is_energy(c)]), 1)
        self.assertEqual(t.damage(aggron), 0)

    # --- Metal Core Barrier UNB 180 / Jamming Tower TWM 153 -------------------
    async def test_metal_core_barrier_minus_70_on_metal(self):
        t = self.table()
        aggron = self.mine(t, AGGRON)
        await t.play(t.put(MCB, P1, 'hand'), targets=[aggron.entity_id])
        await self.opp_hits(t)
        self.assertEqual(t.damage(aggron), 10)

    async def test_metal_core_barrier_non_metal_full_damage(self):
        t = self.table()
        me = self.mine(t, self.filler, hp=300)
        await t.play(t.put(MCB, P1, 'hand'), targets=[me.entity_id])
        await self.opp_hits(t)
        self.assertEqual(me.get_attribute(AttrID.HP), 220)

    async def test_metal_core_barrier_discarded_end_of_opponents_turn_only(self):
        t = self.table()
        aggron = self.mine(t, AGGRON)
        tool = t.put(MCB, P1, 'hand')
        await t.play(tool, targets=[aggron.entity_id])
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        self.assertIn(tool, aggron.children)          # end of MY turn: stays
        t.next_turn()
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P2))
        self.assertIn(tool, t.zone(P1, 'discard'))

    async def test_jamming_tower_disables_metal_core_barrier(self):
        t = self.table()
        aggron = self.mine(t, AGGRON)
        await t.play(t.put(MCB, P1, 'hand'), targets=[aggron.entity_id])
        t.stadium(JAMMING, P2)
        await self.opp_hits(t)
        self.assertEqual(t.damage(aggron), 80)

    async def test_jamming_tower_removed_tool_works_again(self):
        t = self.table()
        aggron = self.mine(t, AGGRON)
        await t.play(t.put(MCB, P1, 'hand'), targets=[aggron.entity_id])
        st = t.stadium(JAMMING, P2)
        area = t.board.find_global_area('activeStadium')
        area.remove_child(st)
        await self.opp_hits(t)
        self.assertEqual(t.damage(aggron), 10)

    # --- Jessie & James HIF 58 -----------------------------------------------
    async def test_jessie_james_each_discards_two_opponent_first(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        mine = [t.put(self.item, P1, 'hand') for _ in range(3)]
        theirs = [t.put(PHANPY, P2, 'hand') for _ in range(3)]
        order = []
        orig = EffectContext.discard_cards

        async def discard(ctx, cards, *a, **k):
            order.extend(c.owning_player_id for c in cards)
            return await orig(ctx, cards, *a, **k)
        with patch.object(EffectContext, 'discard_cards', discard):
            await t.play(t.put(JJ, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P2, 'hand')), 1)
        self.assertEqual(sum(1 for c in mine if c in t.zone(P1, 'discard')), 2)
        self.assertEqual(sum(1 for c in theirs if c in t.zone(P2, 'discard')), 2)
        self.assertEqual(order[:2], [P2, P2])

    async def test_jessie_james_short_hands_discard_what_they_have(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear_hand(t)
        self.clear_hand(t, P2)
        one = t.put(PHANPY, P2, 'hand')
        await t.play(t.put(JJ, P1, 'hand'))
        self.assertIn(one, t.zone(P2, 'discard'))
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Trick Shovel FLF 98 -------------------------------------------------
    async def _shovel(self, t, deck_label, discard):
        async def choose(ctx, prompt, buttons, *a, **k):
            if 'Yes' in buttons or 'No' in buttons or len(buttons) == 2 and 'deck' not in ' '.join(buttons).lower():
                return 0 if discard else 1
            return next(i for i, b in enumerate(buttons) if deck_label in b.lower())
        t.yes = discard
        with patch.object(EffectContext, 'choose', choose):
            await t.play(t.put(SHOVEL, P1, 'hand'))

    async def test_trick_shovel_discard_opponents_top(self):
        t = self.table()
        self.mine(t, self.filler)
        top = t.deck(P2, [PHANPY])[0]
        await self._shovel(t, 'opponent', True)
        self.assertIn(top, t.zone(P2, 'discard'))

    async def test_trick_shovel_keep_own_top(self):
        t = self.table()
        self.mine(t, self.filler)
        top = t.deck(P1, [PHANPY])[0]
        await self._shovel(t, 'your', False)
        self.assertIs(t.zone(P1, 'deck')[-1], top)
        self.assertNotIn(top, t.zone(P1, 'discard'))
        self.assertEqual(t.names(t.zone(P1, 'discard')), ['Trick Shovel'])

    # --- Barboach OBF 108: Hide ----------------------------------------------
    async def test_barboach_hide_heads_prevents_damage(self):
        t = self.table()
        b = self.mine(t, BARBOACH, FIGHT, 1)
        t.heads = True
        await t.attack(b, 'Hide')
        await self.opp_hits(t)
        self.assertEqual(t.damage(b), 0)
        self.assertIn(b, t.zone(P1, 'active'))

    async def test_barboach_hide_tails_no_protection(self):
        t = self.table()
        b = self.mine(t, BARBOACH, FIGHT, 1)
        self.mine(t, self.filler, zone='bench')
        t.heads = False
        await t.attack(b, 'Hide')
        await self.opp_hits(t)
        self.assertIn(b, t.zone(P1, 'discard'))     # 80 >= 70 HP

    # --- Whiscash OBF 109: Raging and Rocking --------------------------------
    # BUG: "For each Fighting Energy attached" multiplier ignored -- always mills 1 (bw_era.bw_legacy_attack)
    async def test_whiscash_mills_one_per_fighting_energy(self):
        t = self.table()
        w = self.mine(t, WHISCASH, FIGHT, 3)
        t.energy(w, WATER, 2)
        before = len(t.zone(P2, 'deck'))
        await t.attack(w, 'Raging and Rocking')
        self.assertEqual(len(t.zone(P2, 'deck')), before - 3)
        self.assertEqual(len(t.zone(P2, 'discard')), 3)
        self.assertEqual(self.dealt(), 0)

    # BUG: Dig Out branch misfires on "attached ... Energy": Whiscash also discards the top card of its OWN deck
    async def test_whiscash_own_deck_untouched(self):
        t = self.table()
        w = self.mine(t, WHISCASH, FIGHT, 1)
        before = len(t.zone(P1, 'deck'))
        await t.attack(w, 'Raging and Rocking')
        self.assertEqual(len(t.zone(P1, 'deck')), before)
        self.assertEqual(len(t.zone(P2, 'discard')), 1)

    # --- Phanpy SIT 91: Knock Away -------------------------------------------
    async def test_phanpy_knock_away_heads_30_tails_10(self):
        t = self.table()
        p = self.mine(t, PHANPY, FIGHT, 1)
        t.heads = True
        await t.attack(p, 'Knock Away')
        self.assertEqual(self.dealt(), 30)
        t2 = self.table()
        p2 = self.mine(t2, PHANPY, FIGHT, 1)
        t2.heads = False
        await t2.attack(p2, 'Knock Away')
        self.assertEqual(self.dealt(), 10)

    # --- Donphan PAF 49 ------------------------------------------------------
    async def test_donphan_cragalanche_mills_two(self):
        t = self.table()
        d = self.mine(t, DONPHAN, WATER, 2)
        before = len(t.zone(P2, 'deck'))
        await t.attack(d, 'Cragalanche')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(len(t.zone(P2, 'deck')), before - 2)
        self.assertEqual(len(t.zone(P1, 'discard')), 0)

    async def test_donphan_powerful_spin_locks_next_turn_only(self):
        t = self.table()
        d = self.mine(t, DONPHAN, FIGHT, 3)
        await t.attack(d, 'Powerful Spin')
        self.assertEqual(self.dealt(), 160)
        t.next_turn()
        t.next_turn()
        self.assertIsNone(t.attack_offer(d, 'Powerful Spin'))
        self.assertIsNone(t.attack_offer(d, 'Cragalanche'))
        t.next_turn()
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(d, 'Powerful Spin'))


if __name__ == '__main__':
    unittest.main()
