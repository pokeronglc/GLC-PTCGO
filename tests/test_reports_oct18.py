"""Oct 18 player reports (owner list)."""
import os
import unittest
from unittest.mock import patch

from tests.test_untested_trainers import Base
from tests.bughunt_table import Table
from tests.untested_card_index import card as ci
from tests.untested_trainer_kit import C, R, W, board, strike, big
from spirit.tools.effect_smoke import P1, P2
from spirit.game.attributes import AttrID
from spirit.game.session.effects import EffectContext
from spirit.game.session.passives import ability_locked
from spirit import config


class Reports(Base):
    async def test_shuckle_fermented_juice_with_energy_attached_from_hand(self):
        # "if THIS Pokémon has any Grass Energy" was read as a filter on the
        # healed Pokémon: hidden unless a damaged Pokémon had Grass Energy.
        for energy in ('CZ.GrassEnergy_152', 'ME3.GrowingGrassEnergy_86'):
            t = Table(self)
            s = t.put('ME1.Shuckle_11', P1, 'active')
            t.put(self.filler, P1, 'bench', hp=10)
            t.put(self.filler, P2, 'active')
            e = t.put(energy, P1, 'hand')
            await t.play(e, targets=[s.entity_id])
            self.assertIsNotNone(t.ability_offer(s, 'Fermented Juice'), energy)

    async def test_archeops_doesnt_stop_evolving_from_the_deck(self):
        with patch.object(config, 'GLC_ONLY', False):
            t = Table(self)
            a = t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            t.put('BW3.Archeops_67', P2, 'bench')
            b = t.put(ci('Charmander'), P1, 'bench')
            t.deck(P1, [ci('Charmeleon')])
            t.state.turn_number = 5
            t.pokemon = lambda c, p: b if b in c else c[0]
            soda = t.put('XY1.Evosoda_116', P1, 'hand')
            self.assertTrue(t.can(soda, 'UseTrainerCard'))
            await t.play(soda)
            self.assertEqual(t.names(t.zone(P1, 'bench')), ['Charmeleon'])
            # ... but evolving from the hand is still stopped.
            b2 = t.put(ci('Charmander'), P1, 'bench')
            t.state.entered_play_turn.pop(b2.entity_id, None)
            evo = t.put(ci('Charmeleon'), P1, 'hand')
            self.assertFalse(list(t.offers(evo, None, P1)))

    async def test_tm_evolution_under_archeops(self):
        with patch.object(config, 'GLC_ONLY', False):
            t = Table(self)
            a = t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            t.put('BW3.Archeops_67', P2, 'bench')
            b = t.put(ci('Charmander'), P1, 'bench')
            t.deck(P1, [ci('Charmeleon')])
            t.state.turn_number = 5
            t.attach('SV4.TechnicalMachineEvolution_178', a)
            t.energy(a, R, 1)
            await t.session.refresh_granted_abilities(a)
            t.pokemon = lambda c, p: b if b in c else c[0]
            await t.attack(a, 'Evolution')
            self.assertEqual(t.names(t.zone(P1, 'bench')), ['Charmeleon'])

    async def test_discarded_pokemon_loses_boosted_max_hp_display(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.put('SWSH10.Kricketune_10', P1, 'bench')
        g = t.put(ci('Bulbasaur'), P1, 'bench')
        sent = []

        async def bp(name, env, *a, **k):
            sent.append(env)
        t.session.broadcast_packet = bp
        await t.session.resync_effective_max_hp()
        await EffectContext(t.session, P1, g, None).discard_cards([g])
        sent.clear()
        await t.session._sync_left_play_hp()
        attrs = [m['msg']['value']['attribute'] for m in sent]
        printed = g.attribute_originals[AttrID.HP.value]
        self.assertEqual([(a['value'], a['originalValue']) for a in attrs], [(printed, printed)])

    async def test_ribombee_keeps_hex_maniac_off_fairy_pokemon(self):
        for with_rib in (True, False):
            t = Table(self)
            t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            if with_rib:
                t.put('SM8.Ribombee_146', P2, 'bench')
            fairy = t.put('XY0.Snubbull_22', P2, 'bench')
            other = t.put(ci('Pikachu'), P2, 'bench')
            await t.play(t.put('XY7.HexManiac_75', P1, 'hand'))
            later = t.put('XY0.Snubbull_22', P2, 'bench')
            t.next_turn()
            self.assertEqual(ability_locked(t.board, fairy), not with_rib)
            self.assertTrue(ability_locked(t.board, other))
            self.assertTrue(ability_locked(t.board, later))

    async def test_exp_share_gone_with_its_knocked_out_holder(self):
        for second_share in (False, True):
            t, a, d = board(self, big(C), hp=10)
            t.energy(d, W, 1)
            sob = t.put(ci('Sobble'), P2, 'bench', hp=10)
            t.attach('SWSH5.ExpShare_126', sob)
            await t.session.refresh_granted_abilities(sob)
            ctx = EffectContext(t.session, P1, a, None)
            await ctx.deal_damage(50, target=sob)
            await t.knockouts(ctx)
            t.board.move_card(sob.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
            if second_share:
                z = t.put(self.filler, P2, 'bench')
                t.attach('SWSH5.ExpShare_126', z)
                await t.session.refresh_granted_abilities(z)
            t.yes = True
            n = len(t.prompts)
            await strike(t, a, d)
            asked = [p for p in t.prompts[n:] if 'Exp. Share' in p]
            self.assertEqual(bool(asked), second_share)

    async def test_deduction_kit_can_shuffle_onto_the_bottom(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        cards = t.deck(P1, [ci('Switch'), ci('Potion'), ci('Nest Ball')])

        async def choose(ctx, prompt, buttons, *a, **k):
            return 1
        with patch.object(EffectContext, 'choose', choose):
            await t.play(t.put('SV08.DeductionKit_171', P1, 'hand'))
        deck = t.board.find_player_area(P1, 'deck').children
        self.assertEqual(set(deck[:3]), set(cards))

    async def test_freezing_shroud_skips_tool_effects(self):
        t = Table(self)
        fro = t.put('SV06.Froslass_53', P1, 'active')
        z = t.put('CZ.Zamazenta_97', P2, 'active')
        holder = t.put(self.filler, P2, 'bench')
        t.attach('SWSH5.ExpShare_126', holder)
        await t.session.refresh_granted_abilities(holder)
        before = {x.entity_id: t.hp(x) for x in (z, holder)}
        await t.checkup()
        self.assertEqual(before[z.entity_id] - t.hp(z), 10)        # has an Ability
        self.assertEqual(before[holder.entity_id] - t.hp(holder), 0)  # Exp. Share isn't one


    async def test_searching_for_a_kind_of_card_shows_it_to_the_opponent(self):
        from spirit.game.session.effects import is_pokemon_card
        from spirit.game.session.game_session import GameSession

        def walk(x):
            if isinstance(x, dict):
                yield x
                for v in x.values():
                    yield from walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    yield from walk(v)
        for predicate, shown in ((None, 0), (is_pokemon_card, 1)):
            t = Table(self)
            src = t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            t.deck(P1, [ci('Pikachu'), ci('Switch')])
            seen = []
            real = GameSession.send_game_sequence

            async def rec(session, players, name, inner):
                if any(p is session.players[P2] for p in players):
                    seen.extend(m for m in walk(inner)
                                if m.get('name') == 'RevealCardToAllEffect')
                return await real(session, players, name, inner)
            t.picks = lambda c, n, p, s: [x for x in c if is_pokemon_card(x)][:n]

            async def run():
                ctx = EffectContext(t.session, P1, src, None)
                picks = await ctx.search_deck(predicate, 1)
                await ctx.put_in_hand(picks, reveal=False)
                await t.session._flush_effect_runs(ctx)
            with patch.object(GameSession, 'send_game_sequence', rec):
                await t._run(run)
            self.assertEqual(len(seen), shown)


    async def test_open_picker_closed_when_the_opponent_concedes(self):
        import asyncio
        import types
        from tests.test_prompt_timeouts import net_player
        from spirit.game.session.game_session import GameSession, GameOver
        from spirit.game.session.constants import GamePhase
        from spirit.network.message_names import OutboundMsg

        async def _noop(value=None):
            return value
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        s = t.session
        searcher = net_player(P1, 'Searcher')
        s.players[P1] = searcher
        s.game_phase = GamePhase.TURN_LOOP
        s.end_game = types.MethodType(GameSession.end_game, s)
        searcher.pending_choice_future = asyncio.get_running_loop().create_future()
        searcher.client_handler.send_packet.reset_mock()
        with patch('spirit.game.session.game_session.run_db', new=lambda *a, **k: _noop()), \
                patch.object(s, '_record_tournament_results', new=lambda *a: _noop()), \
                patch.object(s, '_record_legacy_tournament_result', new=lambda *a: _noop()), \
                patch.object(s, '_record_player_stats', new=lambda *a: _noop()), \
                patch.object(s, '_push_wallet_updates', new=lambda *a: _noop()), \
                patch.object(s, '_push_account_updates', new=lambda *a: _noop()), \
                patch.object(s, '_all_time_points', new=lambda *a: _noop({})):
            try:
                await s.end_game(P1, 'opponent conceded')
            except GameOver:
                pass
        sent = [str(c.args) for c in searcher.client_handler.send_packet.await_args_list]
        close_at = next(i for i, x in enumerate(sent)
                        if OutboundMsg.FORCE_SELECTION_FINISHED.value in x)
        done_at = next(i for i, x in enumerate(sent) if 'GameCompleted' in x)
        self.assertLess(close_at, done_at)
        searcher.pending_choice_future.cancel()

    async def test_recon_directive_animates_the_bottom_card(self):
        from spirit.game.attributes import GameSequence
        t = Table(self)
        d = t.put('SV06.Drakloak_129', P1, 'active')
        t.put(self.filler, P2, 'active')
        t.deck(P1, [ci('Switch'), ci('Potion'), ci('Nest Ball')])
        names = []
        real = type(t.session).send_game_sequence

        async def rec(session, players, name, inner):
            names.append(str(name))
            names.extend(str(getattr(m, 'name', '')) for m in inner if not isinstance(m, dict))
            return await real(session, players, name, inner)
        t.picks = lambda c, n, p, s: [c[1]]
        with patch.object(type(t.session), 'send_game_sequence', rec):
            await t.use(d, 'Recon Directive')
        deck = t.board.find_player_area(P1, 'deck').children
        self.assertEqual(t.names([deck[0]]), ['Nest Ball'])
        self.assertTrue(any(GameSequence.MOVE_FROM_TOP_OF_DECK.value in n for n in names), names)


    async def reveals_to_opponent(self, ref, setup):
        from spirit.game.session.game_session import GameSession

        def walk(x):
            if isinstance(x, dict):
                yield x
                for v in x.values():
                    yield from walk(v)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    yield from walk(v)
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        cards = setup(t)
        seen = []
        real = GameSession.send_game_sequence

        async def rec(session, players, name, inner):
            if any(p is session.players[P2] for p in players):
                seen.extend(m['value'].get('entityID') for m in walk(inner)
                            if m.get('name') == 'RevealCardToAllEffect')
            return await real(session, players, name, inner)
        with patch.object(GameSession, 'send_game_sequence', rec):
            await t.play(t.put(ref, P1, 'hand'))
        return cards, seen

    async def test_cards_leaving_the_discard_are_revealed(self):
        def to_hand(t):
            return [t.put(t.basic_energy(R), P1, 'discard') for _ in range(2)]
        cards, seen = await self.reveals_to_opponent('CZ.EnergyRetrieval_127', to_hand)
        self.assertTrue({c.entity_id for c in cards} <= set(seen))

        def to_deck(t):
            return [t.put(ci('Pikachu'), P1, 'discard'), t.put(t.basic_energy(R), P1, 'discard')]
        cards, seen = await self.reveals_to_opponent('BW3.SuperRod_95', to_deck)
        self.assertTrue(set(seen) & {c.entity_id for c in cards})


    async def test_nothing_reaches_the_winner_after_the_result(self):
        """Oct 19: A conceded inside Raihan's card choice; B stayed on the
        board -- the unwinding prompt sent ClosePauseOnPrompt AFTER
        GameCompleted."""
        import asyncio
        import types
        from tests.test_prompt_timeouts import net_player
        from spirit.game.session.game_session import GameSession
        from spirit.game.session.constants import GamePhase

        async def _noop(value=None):
            return value
        t = Table(self)
        src = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        cards = [t.put(t.basic_energy(R), P1, 'discard') for _ in range(2)]
        s = t.session
        a, b = net_player(P1, 'A'), net_player(P2, 'B')
        s.players[P1], s.players[P2] = a, b
        s.game_phase = GamePhase.TURN_LOOP
        s.end_game = types.MethodType(GameSession.end_game, s)
        s.concede = types.MethodType(GameSession.concede, s)
        with patch('spirit.game.session.game_session.run_db', new=lambda *x, **k: _noop()), \
                patch.object(s, '_record_tournament_results', new=lambda *x: _noop()), \
                patch.object(s, '_record_legacy_tournament_result', new=lambda *x: _noop()), \
                patch.object(s, '_record_player_stats', new=lambda *x: _noop()), \
                patch.object(s, '_push_wallet_updates', new=lambda *x: _noop()), \
                patch.object(s, '_push_account_updates', new=lambda *x: _noop()), \
                patch.object(s, '_all_time_points', new=lambda *x: _noop({})):
            task = asyncio.ensure_future(s.prompt_card_chooser(
                P1, src.entity_id, cards, 1, minimum=1, prompt='Choose'))
            await asyncio.sleep(0.3)
            await s.concede(P1)
            try:
                await asyncio.wait_for(task, 5)
            except BaseException:
                pass
        sent = [str(c.args) for c in b.client_handler.send_packet.await_args_list]
        done = max(i for i, x in enumerate(sent) if 'GameCompleted' in x)
        self.assertEqual(sent[done + 1:], [])


    async def test_guzma_sends_the_gust_and_restamp_before_the_second_pick(self):
        """Oct 19 (PlayerA overlap / PlayerB freeze): the gusted
        client could lose the outgoing Active's Bench stamp. The swap is now
        flushed before the player's own pick and followed by a re-stamp."""
        from spirit.game.attributes import GameSequence
        from spirit.game.session.game_session import GameSession
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P1, 'bench')
        old = t.put(self.filler, P2, 'active')
        t.put(self.filler, P2, 'bench')
        target = t.put(self.filler, P2, 'bench')
        log = []
        real = GameSession.send_game_sequence

        async def rec(session, players, name, inner):
            if any(p is session.players[P2] for p in players):
                for m in inner:
                    v = m.get('value', {}) if isinstance(m, dict) else {}
                    log.append((str(name), v.get('entityID'), v.get('targetEntityID',
                                v.get('parentEntityID'))))
            return await real(session, players, name, inner)
        calls = []

        def pick(c, p):
            calls.append(len(log))
            return target if target in c else c[0]
        t.pokemon = pick
        with patch.object(GameSession, 'send_game_sequence', rec):
            await t.play(t.put(ci('Guzma'), P1, 'hand'))
        self.assertIs(t.zone(P2, 'active')[0], target)
        brackets = [n for n, _, _ in log]
        retreat = brackets.index(GameSequence.RETREAT.value)
        restamp = [i for i, (n, e, _) in enumerate(log)
                   if i > retreat and n == GameSequence.GROUPED_MOVE.value
                   and e == old.entity_id]
        self.assertTrue(restamp, log)
        # Both reached the gusted player before the Guzma player's own pick.
        self.assertEqual(len(calls), 2, calls)
        self.assertLessEqual(restamp[0] + 1, calls[1], (log, calls))


if __name__ == '__main__':
    unittest.main()
