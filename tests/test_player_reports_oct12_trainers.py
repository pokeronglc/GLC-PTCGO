"""Player reports, Oct 12 (Trainers): Hisuian Heavy Ball prize shuffle,
Ordinary Rod / Klara "Choose 1 or both", Lillie's Poké Doll and Robo
Substitute clause-by-clause."""
import collections
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import EffectContext, is_pokemon_card
from spirit.game.session.game_session import GameOver
from spirit.tools.effect_smoke import P1, P2

W, D = PokemonTypes.WATER, PokemonTypes.DARKNESS
HEAVY_BALL = 'SWSH10.HisuianHeavyBall_146'
RODS = ('SWSH1.OrdinaryRod_171', 'SWSH1.OrdinaryRod_215')
KLARAS = ('SWSH6.Klara_145', 'SWSH6.Klara_194', 'SWSH6.Klara_217')
DOLL, ROBO = 'SM12.LilliesPokDoll_197', 'XY4.RoboSubstituteTeamFlareGear_102'
DOLL_ALT = 'SM12.LilliesPokDoll_267'
DOLL_TITLE, ROBO_TITLE = "Put Lillie's Poké Doll Away", 'Discard Robo Substitute'
DOLLS = ((DOLL, DOLL_TITLE), (DOLL_ALT, DOLL_TITLE), (ROBO, ROBO_TITLE))
PALAFIN = 'SV05.Palafin_49'          # Vanguard Punch: 130 for [W]
BOSS, SWITCH = 'SWSH45.BosssOrders_58', 'SWSH1.Switch_183'
VITALITY, QUICK = 'SWSH1.VitalityBand_185', 'SWSH1.QuickBall_179'
VILEPLUME = 'XY7.Vileplume_3'        # Irritating Pollen: no Items from hand


def pick_option(label):
    """Patch EffectContext.choose to press the button named `label`."""
    seen = []

    async def choose(ctx, prompt, buttons, *a, **k):
        seen.append(list(buttons))
        return buttons.index(label)
    return patch.object(EffectContext, 'choose', choose), seen


class Oct12Trainers(unittest.IsolatedAsyncioTestCase):
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

    def zone_name(self, card):
        return card.parent.get_attribute(AttrID.NAME) if card.parent else None

    # ================================================================
    # 1. Hisuian Heavy Ball: the face-down Prizes are shuffled afterwards
    # ================================================================
    def heavy_ball_table(self, slot):
        t = self.table()
        t.put(self.filler, P1, 'active')
        prizes = t.board.find_player_area(P1, 'prizePile')
        for i, card in enumerate(prizes.children):
            card.board_slot = i
        prizes.remove_child(prizes.children[slot])
        basic = t.put(self.filler, P1, 'hand')
        t.board.move_card(basic.entity_id, prizes.entity_id, slot)
        basic.board_slot = slot
        return t, prizes, basic

    async def play_heavy_ball(self, t, pick):
        ball = t.put(HEAVY_BALL, P1, 'hand')
        sent = []
        real = t.session.send_game_sequence

        async def record(players, bracket, msgs):
            sent.append((list(players), list(msgs)))
            return await real(players, bracket, msgs)

        async def prize_pick(*a, **k):
            return pick.entity_id if pick is not None else None
        with patch.object(t.session, 'prompt_prize_reveal_pick', prize_pick), \
                patch.object(t.session, 'send_game_sequence', record):
            await t.play(ball)
        return ball, sent

    def prize_shuffle_messages(self, sent, prizes):
        """(players told about a Shuffled prize pile, EntityMoved into it after)."""
        told, moves, after = set(), [], False
        for players, msgs in sent:
            for m in msgs:
                name = m.get('name') if isinstance(m, dict) else None
                value = m.get('value', {}) if isinstance(m, dict) else {}
                if name == 'Shuffled' and value.get('entityID') == prizes.entity_id:
                    after = True
                    told.update(id(p) for p in players)
                elif after and name == 'EntityMoved' \
                        and value.get('destinationID') == prizes.entity_id:
                    moves.append(value)
        return told, moves

    async def test_heavy_ball_shuffles_prizes_after_taking_basic(self):
        t, prizes, basic = self.heavy_ball_table(5)
        before = [c.entity_id for c in prizes.children]
        ball, sent = await self.play_heavy_ball(t, basic)
        self.assertIn(basic, t.zone(P1, 'hand'))
        self.assertIn(ball, t.zone(P1, 'prizes'))
        self.assertEqual(len(prizes.children), 6)
        told, moves = self.prize_shuffle_messages(sent, prizes)
        # both players are told, and the cards get new grid slots
        self.assertEqual(told, {id(p) for p in t.session.players.values()})
        self.assertTrue(moves)
        slots = [c.board_slot for c in prizes.children]
        self.assertEqual(sorted(slots), list(range(6)))
        self.assertNotEqual(
            {e: c.board_slot for e, c in zip(before, prizes.children)}, {})

    async def test_heavy_ball_shuffles_prizes_when_declined(self):
        t, prizes, basic = self.heavy_ball_table(2)
        ball, sent = await self.play_heavy_ball(t, None)
        self.assertIn(basic, t.zone(P1, 'prizes'))
        self.assertIn(ball, t.zone(P1, 'discard'))
        told, moves = self.prize_shuffle_messages(sent, prizes)
        self.assertEqual(told, {id(p) for p in t.session.players.values()})
        self.assertTrue(moves)

    async def test_heavy_ball_lands_in_random_slot(self):
        landed = collections.Counter()
        for n in range(24):
            t, prizes, basic = self.heavy_ball_table(n % 6)
            ball, _ = await self.play_heavy_ball(t, basic)
            landed[ball.board_slot] += 1
        # not always the vacated slot: it is spread over the grid
        self.assertGreater(len(landed), 2)

    # ================================================================
    # 2. Ordinary Rod / Klara: choose the option(s) first
    # ================================================================
    def discard_mix(self, t):
        mons = [t.put(self.filler, P1, 'discard') for _ in range(3)]
        energy = [t.put(t.basic_energy(W), P1, 'discard') for _ in range(3)]
        return mons, energy

    async def run_choice(self, spec, label, picks=None):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mons, energy = self.discard_mix(t)
        mins = []
        real_choose_cards = None

        def record(cards, count, prompt, display):
            mins.append((t.names(cards), count))
            return (picks or (lambda c, n: c[:n]))(cards, count)
        t.picks = record
        patcher, buttons = pick_option(label)
        deck, hand = len(t.zone(P1, 'deck')), len(t.zone(P1, 'hand'))
        with patcher:
            await t.play(t.put(spec, P1, 'hand'))
        return t, mons, energy, buttons, mins, deck, hand

    async def test_ordinary_rod_pokemon_only_never_asks_for_energy(self):
        for spec in RODS:
            with self.subTest(spec=spec):
                t, mons, energy, buttons, mins, deck, _ = await self.run_choice(spec, 'Pokémon')
                self.assertEqual(buttons, [['Pokémon', 'Basic Energy', 'Both']])
                self.assertEqual(len(mins), 1)
                self.assertNotIn('?', mins[0][0])          # Pokémon browser only
                self.assertEqual(len(t.zone(P1, 'deck')), deck + 2)
                for card in energy:
                    self.assertIn(card, t.zone(P1, 'discard'))

    async def test_ordinary_rod_energy_only_and_both(self):
        for spec in RODS:
            with self.subTest(spec=spec, option='energy'):
                t, mons, energy, _, mins, deck, _ = await self.run_choice(spec, 'Basic Energy')
                self.assertEqual(len(mins), 1)
                self.assertEqual(len(t.zone(P1, 'deck')), deck + 2)
                for card in mons:
                    self.assertIn(card, t.zone(P1, 'discard'))
            with self.subTest(spec=spec, option='both'):
                t, mons, energy, _, mins, deck, _ = await self.run_choice(spec, 'Both')
                self.assertEqual(len(mins), 2)
                self.assertEqual(len(t.zone(P1, 'deck')), deck + 4)

    async def test_ordinary_rod_each_chosen_option_takes_at_least_one(self):
        seen = []

        async def choose_cards(ctx, cards, count, minimum=None, **k):
            seen.append(minimum)
            return list(cards)[:1]
        for spec in RODS:
            t = self.table()
            t.put(self.filler, P1, 'active')
            self.discard_mix(t)
            patcher, _ = pick_option('Both')
            with patcher, patch.object(EffectContext, 'choose_cards', choose_cards):
                card = t.put(spec, P1, 'hand')
                await fixtures.definition(spec).effect(
                    EffectContext(t.session, P1, card, None))
        self.assertEqual(seen, [1, 1, 1, 1])

    async def test_ordinary_rod_single_group_skips_the_menu(self):
        for spec in RODS:
            t = self.table()
            t.put(self.filler, P1, 'active')
            for _ in range(3):
                t.put(self.filler, P1, 'discard')
            asked = AsyncMock(side_effect=AssertionError('no menu expected'))
            deck = len(t.zone(P1, 'deck'))
            with patch.object(EffectContext, 'choose', asked):
                await t.play(t.put(spec, P1, 'hand'))
            self.assertEqual(len(t.zone(P1, 'deck')), deck + 2)

    async def test_klara_choose_one_or_both_all_printings(self):
        for spec in KLARAS:
            with self.subTest(spec=spec, option='Pokémon'):
                t, mons, energy, buttons, mins, _, hand = await self.run_choice(spec, 'Pokémon')
                self.assertEqual(buttons, [['Pokémon', 'Basic Energy', 'Both']])
                self.assertEqual(len(mins), 1)
                self.assertEqual(sum(c in t.zone(P1, 'hand') for c in mons), 2)
                self.assertFalse(any(c in t.zone(P1, 'hand') for c in energy))
            with self.subTest(spec=spec, option='Both'):
                t, mons, energy, _, mins, _, _ = await self.run_choice(spec, 'Both')
                self.assertEqual(len(mins), 2)
                self.assertEqual(sum(c in t.zone(P1, 'hand') for c in mons + energy), 4)

    # ================================================================
    # 3. Lillie's Poké Doll / Robo Substitute
    # ================================================================
    def opp_attacker(self, t):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        attacker = t.put(PALAFIN, P2, 'active')
        t.energy(attacker, W)
        return attacker

    async def test_doll_plays_to_bench_as_30hp_basic_colorless(self):
        for spec, _ in DOLLS:
            with self.subTest(spec=spec):
                t = self.table()
                t.put(self.filler, P1, 'active')
                doll = t.put(spec, P1, 'hand')
                self.assertFalse(is_pokemon_card(doll))       # an Item in hand
                await t.play(doll)
                self.assertIn(doll, t.zone(P1, 'bench'))
                self.assertTrue(is_pokemon_card(doll))        # a Pokémon in play
                self.assertEqual(t.hp(doll), 30)
                self.assertEqual(doll.get_attribute(AttrID.POKEMON_TYPES),
                                 [PokemonTypes.COLORLESS.value])
                self.assertFalse(doll.get_attribute(AttrID.WEAKNESS_TYPES))

    async def test_doll_respects_bench_limit_and_item_lock(self):
        for spec, _ in DOLLS:
            with self.subTest(spec=spec, case='full bench'):
                t = self.table()
                t.put(self.filler, P1, 'active')
                for _ in range(5):
                    t.put(self.filler, P1, 'bench')
                self.assertFalse(t.offers(t.put(spec, P1, 'hand')))
            with self.subTest(spec=spec, case='item lock'):
                t = self.table()
                t.put(self.filler, P1, 'active')
                t.put(VILEPLUME, P2, 'bench')
                self.assertFalse(t.offers(t.put(spec, P1, 'hand')))

    async def test_doll_is_not_a_pokemon_for_deck_searches(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.deck(P1, [DOLL, ROBO])
        t.put(self.item, P1, 'hand')
        offered = []
        t.picks = lambda cards, count, prompt, display: (offered.append(t.names(cards)), [])[1]
        await t.play(t.put(QUICK, P1, 'hand'))
        self.assertTrue(offered)
        for names in offered[1:]:
            self.assertNotIn("Lillie's Poké Doll", names)
            self.assertNotIn('Robo Substitute Team Flare Gear', names)

    async def test_doll_cannot_retreat_but_can_be_switched(self):
        for spec, _ in DOLLS:
            with self.subTest(spec=spec):
                t = self.table()
                doll = t.put(spec, P1, 'active')
                bench = t.put(self.filler, P1, 'bench')
                t.energy(doll, W, 2)
                self.assertFalse(t.can(doll, 'BaseRetreat'))
                await t.play(t.put(SWITCH, P1, 'hand'))
                self.assertIs(t.active(P1), bench)
                self.assertIn(doll, t.zone(P1, 'bench'))

    async def test_doll_can_be_gusted_and_hold_tools_and_energy(self):
        for spec, _ in DOLLS:
            with self.subTest(spec=spec):
                t = self.table()
                t.put(self.filler, P1, 'active')
                doll = t.put(spec, P2, 'bench')
                t.pokemon = lambda c, p: doll if doll in c else c[0]
                await t.play(t.put(BOSS, P1, 'hand'))
                self.assertIs(t.active(P2), doll)
                t.next_turn()
                self.assertFalse(t.can(doll, 'BaseRetreat', pid=P2))
                tool = t.put(VITALITY, P2, 'hand')
                self.assertIn(doll.entity_id, t.targets(tool, 'DefaultToolPlayAbility', pid=P2))

    async def test_doll_knocked_out_gives_no_prize(self):
        for spec, _ in DOLLS:
            with self.subTest(spec=spec, how='attack'):
                t = self.table()
                attacker = self.opp_attacker(t)
                doll = t.put(spec, P1, 'active')
                t.put(self.filler, P1, 'bench')
                t.next_turn()
                await t.attack(attacker, 'Vanguard Punch', pid=P2)
                self.assertIn(doll, t.zone(P1, 'discard'))
                self.assertEqual(len(t.zone(P2, 'prizes')), 6)
                self.assertIsNotNone(t.active(P1))
            with self.subTest(spec=spec, how='poison'):
                t = self.table()
                t.put(self.filler, P1, 'bench')
                doll = t.put(spec, P1, 'active', hp=10)
                doll.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
                await t.checkup()
                self.assertIn(doll, t.zone(P1, 'discard'))
                self.assertEqual(len(t.zone(P2, 'prizes')), 6)

    async def test_doll_knocked_out_as_last_pokemon_loses(self):
        for spec, _ in DOLLS:
            with self.subTest(spec=spec):
                t = self.table()
                attacker = self.opp_attacker(t)
                t.put(spec, P1, 'active')
                t.next_turn()
                won = []

                async def end(winner, reason):
                    won.append(winner)
                    raise GameOver()
                with patch.object(t.session, 'end_game', end):
                    with self.assertRaises(GameOver):
                        await t.attack(attacker, 'Vanguard Punch', pid=P2)
                self.assertEqual(won, [P2])
                self.assertEqual(len(t.zone(P2, 'prizes')), 6)

    async def test_lillies_doll_put_away_only_when_active(self):
        for spec in (DOLL, DOLL_ALT):
            t = self.table()
            t.put(self.filler, P1, 'active')
            doll = t.put(spec, P1, 'bench')
            self.assertIsNone(t.ability_offer(doll, DOLL_TITLE))

    async def test_lillies_doll_put_away_discards_cards_and_goes_to_deck_bottom(self):
        for spec in (DOLL, DOLL_ALT):
            with self.subTest(spec=spec):
                t = self.table()
                doll = t.put(spec, P1, 'active', hp=10)
                energy = t.energy(doll, W)
                tool = t.attach(VITALITY, doll)
                new = t.put(self.filler, P1, 'bench')
                t.energy(new, W, 3)
                await t.use(doll, DOLL_TITLE)
                self.assertIs(t.zone(P1, 'deck')[0], doll)
                self.assertIn(energy, t.zone(P1, 'discard'))
                self.assertIn(tool, t.zone(P1, 'discard'))
                self.assertIs(t.active(P1), new)
                # the promoted Pokémon may still attack this turn
                self.assertTrue(t.offers(new, 'UsePokemonAttack'))
                # back in hand later it is a clean Item that benches at 30 HP
                t.board.move_card(doll.entity_id, t.board.find_player_area(P1, 'hand').entity_id)
                await t.play(doll)
                self.assertIn(doll, t.zone(P1, 'bench'))
                self.assertEqual(t.hp(doll), 30)

    async def test_robo_substitute_discards_from_active_or_bench(self):
        for zone in ('active', 'bench'):
            with self.subTest(zone=zone):
                t = self.table()
                if zone == 'bench':
                    t.put(self.filler, P1, 'active')
                robo = t.put(ROBO, P1, zone)
                energy = t.energy(robo, W)
                if zone == 'active':
                    new = t.put(self.filler, P1, 'bench')
                await t.use(robo, ROBO_TITLE)
                self.assertIn(robo, t.zone(P1, 'discard'))
                self.assertIn(energy, t.zone(P1, 'discard'))
                self.assertEqual(len(t.zone(P2, 'prizes')), 6)
                if zone == 'active':
                    self.assertIs(t.active(P1), new)

    async def test_doll_removal_not_blocked_by_conditions_or_item_lock(self):
        for spec, title in DOLLS:
            for case in (PARALYZED, 'item lock'):
                with self.subTest(spec=spec, case=case):
                    t = self.table()
                    doll = t.put(spec, P1, 'active')
                    t.put(self.filler, P1, 'bench')
                    if case == 'item lock':
                        t.put(VILEPLUME, P2, 'bench')
                    else:
                        doll.set_attribute(AttrID.SPECIAL_CONDITIONS, [case])
                    self.assertIsNotNone(t.ability_offer(doll, title))

    async def test_doll_removal_with_no_other_pokemon_loses(self):
        for spec, title in DOLLS:
            with self.subTest(spec=spec):
                t = self.table()
                doll = t.put(spec, P1, 'active')
                won = []

                async def end(winner, reason):
                    won.append(winner)
                    raise GameOver()
                with patch.object(t.session, 'end_game', end):
                    with self.assertRaises(GameOver):
                        await t.use(doll, title)
                self.assertEqual(won, [P2])

    async def test_doll_has_no_evolve_button_and_no_ability(self):
        from spirit.game.card_effects.bw_era import _pokemon_has_ability
        for spec, title in DOLLS:
            definition = fixtures.definition(spec)
            self.assertEqual([a.title for a in definition.abilities], [title])
            self.assertTrue(definition.abilities[0].is_rule_action)
            self.assertFalse(definition.setup_as_active)
            t = self.table()
            doll = t.put(spec, P1, 'bench')
            self.assertFalse(_pokemon_has_ability(doll))


if __name__ == '__main__':
    unittest.main()
