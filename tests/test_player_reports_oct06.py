"""Player reports: Tyrantrum's Wreak Havoc, Raging Bolt's Thunderburst Storm,
Klara/Dawn in one screen, Aqua Storm mill shown before damage."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.data_utils import CARD_DEFS_BY_GUID
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2


class PlayerReportTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def attack_of(self, path, title):
        return next(a for a in fixtures.definition(path).abilities if a.title == title)

    async def test_wreak_havoc_mills_one_per_heads(self):
        rig, e = self.rig('ME3.Tyrantrum_45')
        attack = self.attack_of('ME3.Tyrantrum_45', 'Wreak Havoc')
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        ctx.flip_until_tails = AsyncMock(return_value=4)
        deck = rig.board.find_player_area(P2, 'deck')
        before = len(deck.children)
        await attack.effect(ctx)
        ctx.flip_until_tails.assert_awaited_once()
        self.assertEqual(before - len(deck.children), 4)

    async def test_thunderburst_storm_counts_every_energy_unit(self):
        rig, e = self.rig('SV07.RagingBolt_111')
        bolt = e['target']
        attack = self.attack_of('SV07.RagingBolt_111', 'Thunderburst Storm')
        dte = next(d for d in CARD_DEFS_BY_GUID.values()
                   if d.display_name == 'Double Turbo Energy')
        rig.attach(self.add(rig, dte, P1, 'hand'), bolt)
        ctx = EffectContext(rig.session, P1, bolt, attack)
        from spirit.game.card_effects.bw_era import _energy_count
        units = _energy_count(ctx, bolt)
        cards = len(ctx.attached_energies(bolt))
        self.assertEqual(units, cards + 1)               # Double Turbo counts 2
        dealt = []
        original = ctx.deal_damage
        async def record(amount=None, *args, **kwargs):
            dealt.append(amount)
            return await original(amount, *args, **kwargs)
        ctx.deal_damage = record
        rig.board.active_pokemon(P2).set_attribute(AttrID.HP, 5000)
        await attack.effect(ctx)
        self.assertEqual(dealt[0], 30 * units)

    async def test_klara_is_two_picks(self):
        # Oct 9: the combined browser hid slots, so Klara is back to two picks:
        # up to 2 Pokémon, then up to 2 basic Energy.
        from spirit.game.session.effects import is_pokemon_card
        from spirit.game.card_effects.trainers import is_basic_energy_card
        rig, e = self.rig('SWSH6.Klara_145', 'trainer')
        for _ in range(3):
            self.add(rig, fixtures.definition('SM1.Pikipek_106'), P1, 'discard')
        hand = rig.board.find_player_area(P1, 'hand')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        calls = []

        async def choose(cards, n, minimum=0, prompt=''):
            calls.append((list(cards), n, minimum))
            return list(cards)[:n]

        ctx.choose_cards = choose
        ctx.choose_card_groups = AsyncMock()
        # Oct 12: "Choose 1 or both" -- option(s) first, then 1+ per option.
        ctx.choose = AsyncMock(return_value=2)          # "Both"
        await fixtures.definition('SWSH6.Klara_145').effect(ctx)
        ctx.choose_card_groups.assert_not_awaited()
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(is_pokemon_card(c) for c in calls[0][0]))
        self.assertTrue(all(is_basic_energy_card(c) for c in calls[1][0]))
        self.assertTrue(all(n <= 2 and minimum == 1 for _, n, minimum in calls))
        for cards, n, _ in calls:
            for card in cards[:n]:
                self.assertIn(card, hand.children)

    async def test_dawn_is_one_browser(self):
        rig, e = self.rig('ME2.Dawn_87', 'trainer')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        ctx.search_deck = AsyncMock(return_value=[])
        ctx.search_deck_groups = AsyncMock(return_value=[[], [], []])
        await fixtures.definition('ME2.Dawn_87').effect(ctx)
        ctx.search_deck_groups.assert_awaited_once()
        ctx.search_deck.assert_not_awaited()

    async def test_aqua_storm_shows_the_mill_first(self):
        rig, e = self.rig('CEL25.Kyogre_3')
        attack = self.attack_of('CEL25.Kyogre_3', 'Aqua Storm')
        ctx = EffectContext(rig.session, P1, e['target'], attack)
        order = []
        flush = ctx.flush_choreography
        async def flushed():
            order.append('flush')
            await flush()
        async def choose(*args, **kwargs):
            order.append('choose')
            return []
        ctx.flush_choreography = flushed
        ctx.choose_cards = choose
        await attack.effect(ctx)
        self.assertEqual(order[:2], ['flush', 'choose'])

    async def test_bench_shrink_keeps_u_turn_board(self):
        # Parallel City discards Benched Pokemon; U-Turn Board still goes to hand.
        rig, e = self.rig('BW7.Charmander_18')
        benched = rig.board.find_player_area(P1, 'bench').children[0]
        board = self.add(rig, fixtures.definition('SM11.UTurnBoard_211'), P1, 'hand')
        rig.attach(board, benched)
        await rig.session._discard_bench_stack(P1, benched)
        self.assertIs(board.parent, rig.board.find_player_area(P1, 'hand'))
        self.assertIs(benched.parent, rig.board.find_player_area(P1, 'discard'))

    async def test_gladion_uses_the_prize_fan(self):
        rig, e = self.rig('SM4.Gladion_109', 'trainer')
        gladion = e['target']
        prizes = rig.board.find_player_area(P1, 'prizePile')
        hand = rig.board.find_player_area(P1, 'hand')
        before = list(prizes.children)
        ctx = EffectContext(rig.session, P1, gladion, None)
        with patch.object(rig.session, 'prompt_prize_reveal_pick',
                          AsyncMock(return_value=before[2].entity_id)) as fan:
            await fixtures.definition('SM4.Gladion_109').effect(ctx)
        self.assertTrue(fan.await_args.kwargs['forced'])
        self.assertIs(before[2].parent, hand)
        self.assertIs(gladion.parent, prizes)
        self.assertEqual(len(prizes.children), len(before))

    def evolve_offered(self, rig, card, target):
        from spirit.game.session.legal_actions import compute_legal_actions
        return any(target.entity_id in (t.get('validTargets') or [])
                   for e in compute_legal_actions(rig.board, rig.session.turn_state, P1,
                                                  rig.session.game_id)
                   if e['entityID'] == card.entity_id
                   for t in e['targetInfoLst'])

    async def test_no_second_evolution_after_devolution_spray(self):
        rig, e = self.rig('BW7.Charmander_18')
        ts = rig.session.turn_state
        ts.begin_turn(P2); ts.begin_turn(P1)
        charmander = rig.board.find_player_area(P1, 'bench').children[0]
        charmeleon = self.add(rig, fixtures.definition('BW7.Charmeleon_19'), P1, 'hand')
        self.assertTrue(self.evolve_offered(rig, charmeleon, charmander))
        await rig.session.perform_evolution(P1, charmeleon, charmander)
        ctx = EffectContext(rig.session, P1, charmeleon, None)
        await ctx.devolve_pokemon(charmeleon, 1, destination='hand')
        self.assertIs(charmeleon.parent, rig.board.find_player_area(P1, 'hand'))
        # Evolved this turn already: Devolution Spray doesn't allow it again.
        self.assertFalse(self.evolve_offered(rig, charmeleon, charmander))
        ts.begin_turn(P2); ts.begin_turn(P1)
        self.assertTrue(self.evolve_offered(rig, charmeleon, charmander))

    async def test_scoop_up_net_replay_cannot_evolve_this_turn(self):
        rig, e = self.rig('BW7.Charmander_18')
        ts = rig.session.turn_state
        ts.begin_turn(P2); ts.begin_turn(P1)
        charmander = self.add(rig, fixtures.definition('BW7.Charmander_18'), P1, 'hand')
        await rig.session._execute_play_basic(P1, charmander)
        charmeleon = self.add(rig, fixtures.definition('BW7.Charmeleon_19'), P1, 'hand')
        self.assertFalse(self.evolve_offered(rig, charmeleon, charmander))


if __name__ == "__main__":
    unittest.main()
