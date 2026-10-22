"""Oct 20 player reports (owner list)."""
import unittest

from tests.test_untested_trainers import Base
from tests.bughunt_table import Table
from tests.untested_card_index import card as ci
from tests.untested_trainer_kit import R, W
from spirit.tools.effect_smoke import P1, P2


class Reports(Base):
    async def test_crobat_needs_janines_secret_art_this_turn(self):
        # "You can draw 8 cards every turn without having played Janine's
        # Secret Arts": the "if you played X from your hand this turn" gate
        # was never checked.
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        crobat = t.put('SV065.Crobat_29', P1, 'bench')
        t.deck(P1, [ci('Switch')] * 10)
        self.assertIsNone(t.ability_offer(crobat, 'Shadowy Envoy'))
        # Another Supporter doesn't count.
        t.state.trainers_played.append(('x', "Professor's Research", 1))
        self.assertIsNone(t.ability_offer(crobat, 'Shadowy Envoy'))
        t.state.trainers_played.append(('y', "Janine's Secret Art", 1))
        self.assertIsNotNone(t.ability_offer(crobat, 'Shadowy Envoy'))

    async def test_turbo_energize_names_each_energy(self):
        # PlayerA: no way to tell which Energy the Pokémon pick is for.
        t = Table(self)
        a = t.put(self.filler, P1, 'active')
        b1 = t.put(self.filler, P1, 'bench')
        b2 = t.put(self.filler, P1, 'bench')
        t.put(self.filler, P2, 'active')
        t.deck(P1, [t.basic_energy(R), t.basic_energy(W), ci('Switch')])
        t.attach('SV4.TechnicalMachineTurboEnergize_179', a)
        t.energy(a, R, 1)
        t.state.turn_number = 5
        await t.session.refresh_granted_abilities(a)
        t.picks = lambda c, n, p, s: list(c)[:n]
        order = iter([b2, b1])
        t.pokemon = lambda c, p: next(order)
        await t.attack(a, 'Turbo Energize')
        picks = [p for p in t.prompts if p.startswith('Choose a Pokémon to attach')]
        self.assertEqual(len(picks), 2, t.prompts)
        self.assertTrue(all('Energy to' in p and 'the Energy' not in p for p in picks), picks)


    async def test_answer_racing_a_concede_sends_no_more_prompts(self):
        """PlayerA (game 76cc6be5, Oct 18): PlayerB conceded while he
        answered Mallow & Lana's Yes; the Yes landed while end_game was still
        in its DB awaits (phase not yet GAME_OVER) and the discard picker was
        sent on top of the result."""
        import asyncio
        import types
        from tests.test_prompt_timeouts import net_player
        from spirit.game.session.game_session import GameSession
        from spirit.game.session.constants import GamePhase
        from unittest.mock import patch

        async def _noop(value=None):
            return value
        t = Table(self)
        src = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        hand = [t.put(t.basic_energy(R), P1, 'hand') for _ in range(3)]
        s = t.session
        a, b = net_player(P1, 'A'), net_player(P2, 'B')
        s.players[P1], s.players[P2] = a, b
        s.game_phase = GamePhase.TURN_LOOP
        s.end_game = types.MethodType(GameSession.end_game, s)
        s.concede = types.MethodType(GameSession.concede, s)
        s.prompt_selection_message = types.MethodType(GameSession.prompt_selection_message, s)

        async def yes_lands_mid_end_game(*_):
            fut = a.pending_choice_future
            if fut is not None and not fut.done():
                fut.set_result({'selection': 0, 'counter': fut_counter[0]})
            await asyncio.sleep(0.2)
            return {}
        fut_counter = [None]
        real_choice = GameSession.prompt_player_choice

        async def flow():
            if await real_choice(s, P1, 'Discard?', ['Yes', 'No']) == 0:
                await s.prompt_card_chooser(P1, src.entity_id, hand, 2, minimum=2,
                                            prompt='Choose 2 cards to discard')
        with patch('spirit.game.session.game_session.run_db', new=lambda *x, **k: _noop()), \
                patch.object(s, '_record_tournament_results', new=lambda *x: _noop()), \
                patch.object(s, '_record_legacy_tournament_result', new=lambda *x: _noop()), \
                patch.object(s, '_record_player_stats', new=lambda *x: _noop()), \
                patch.object(s, '_push_wallet_updates', new=lambda *x: _noop()), \
                patch.object(s, '_push_account_updates', new=lambda *x: _noop()), \
                patch.object(s, '_all_time_points', new=yes_lands_mid_end_game):
            task = asyncio.ensure_future(flow())
            await asyncio.sleep(0.3)
            fut_counter[0] = s._selection_counters.get(P1) if hasattr(s, '_selection_counters') else None
            try:
                await s.concede(P2)
            except BaseException:
                pass
            try:
                await asyncio.wait_for(task, 5)
            except BaseException:
                pass
        sent = [str(c.args) for c in a.client_handler.send_packet.await_args_list]
        self.assertFalse(any('Choose 2 cards to discard' in x for x in sent), sent)


    async def test_tm_evolution_needs_at_least_one_pokemon(self):
        # Player report (game 5ab2159d): confirmed "Choose Pokémon to evolve" with
        # nothing selected. Owner rule: the pick now needs at least 1.
        from unittest.mock import patch
        from spirit import config
        from spirit.game.session.effects import EffectContext
        with patch.object(config, 'GLC_ONLY', False):
            t = Table(self)
            a = t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            b = t.put(ci('Charmander'), P1, 'bench')
            t.deck(P1, [ci('Charmeleon')])
            t.state.turn_number = 5
            t.attach('SV4.TechnicalMachineEvolution_178', a)
            t.energy(a, R, 1)
            await t.session.refresh_granted_abilities(a)
            seen = []
            base = t._patches

            def patches():
                ps = base()
                inner = ps[0].new

                async def choose_cards(ctx, cards, count, minimum=None, prompt='', *x, **k):
                    seen.append((prompt, minimum))
                    return await inner(ctx, cards, count, minimum, prompt, *x, **k)
                ps[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
                return ps
            t._patches = patches
            await t.attack(a, 'Evolution')
            self.assertIn(('Choose Pokémon to evolve', 1), seen)
            self.assertEqual(t.names(t.zone(P1, 'bench')), ['Charmeleon'])


if __name__ == '__main__':
    unittest.main()
