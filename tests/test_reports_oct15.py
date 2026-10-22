"""Owner reports, Oct 15 (overnight)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.untested_trainer_kit import D, find, named
from spirit.game.attributes import AttrID
from spirit.game.session.effects import EffectContext
from spirit.network.message_names import OutboundMsg
from spirit.tools.effect_smoke import P1, P2

RESET = OutboundMsg.ATTRIBUTES_RESET.value


class Base(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def board(self):
        t = Table(self)
        me = t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        return t, me


class GameLogPrivacy(Base):
    """'KlikiAvenir drew VS Seeker': cards the clients had seen kept their
    faces after being shuffled back, so the opponent's log named the draw."""

    def resets(self, ctx):
        return {m['value']['entityID'] for _, m, _ in ctx._messages
                if isinstance(m, dict) and m.get('name') == RESET}

    async def test_shuffle_into_deck_rehides_every_deck_card(self):
        t, me = self.board()
        known = [t.put('SWSH1.QuickBall_216', P1, 'discard') for _ in range(2)]
        ctx = EffectContext(t.session, P1, me, None)
        await t._run(lambda: ctx.shuffle_into_deck(known))
        deck_ids = {c.entity_id for c in t.zone(P1, 'deck')}
        self.assertTrue(set(c.entity_id for c in known) <= deck_ids)
        self.assertEqual(self.resets(ctx), deck_ids)

    async def test_plain_shuffle_rehides(self):
        t, me = self.board()
        ctx = EffectContext(t.session, P1, me, None)
        await t._run(lambda: ctx.shuffle_deck())
        self.assertEqual(self.resets(ctx), {c.entity_id for c in t.zone(P1, 'deck')})

    async def test_hand_to_bottom_rehides_the_moved_hand(self):
        t, me = self.board()
        hand = [t.put('SWSH1.QuickBall_216', P1, 'hand') for _ in range(3)]
        ctx = EffectContext(t.session, P1, me, None)
        await t._run(lambda: ctx.hand_to_bottom_of_deck())
        self.assertTrue({c.entity_id for c in hand} <= self.resets(ctx))


class LarrysKomala(Base):
    async def test_only_onto_an_active_larrys_pokemon(self):
        t, me = self.board()
        k = t.put('ME2PT5.LarrysKomala_175', P1, 'bench')
        t.put(t.basic_energy(D), P1, 'hand')
        self.assertIsNone(t.ability_offer(k, 'Lethargic Charge'), 'Active is not a Larry\'s Pokemon')
        t2 = Table(self)
        larry = t2.put(find(name=lambda n: n.startswith("Larry's ") and n != "Larry's Komala", quiet=False), P1, 'active')
        t2.put(self.filler, P2, 'active')
        k2 = t2.put('ME2PT5.LarrysKomala_175', P1, 'bench')
        other = t2.put(self.filler, P1, 'bench')
        e = t2.put(t2.basic_energy(D), P1, 'hand')
        self.assertIsNotNone(t2.ability_offer(k2, 'Lethargic Charge'))
        await t2.use(k2, 'Lethargic Charge')
        self.assertIn(e, t2.attached(larry))
        self.assertNotIn(e, t2.attached(other))


class Evosoda(Base):
    async def test_only_pokemon_that_can_still_evolve(self):
        t = Table(self)
        dig = t.put('SM1.AlolanDiglett_86', P1, 'active')
        t.put(self.filler, P2, 'active')
        from spirit.game.glc import _evolutions_of
        from tests.untested_trainer_kit import M
        lone = find(types=M, pred=lambda d: not _evolutions_of(
            d.extra_attributes[str(AttrID.EVOLUTION_LOGIC_NAME.value)]['value'])
            and d.display_name != 'Alolan Dugtrio')
        dug = t.put(lone, P1, 'bench')                # a Metal Pokemon nothing evolves from
        t.deck(P1, ['SM1.AlolanDugtrio_87'])
        card = t.put('XY1.Evosoda_116', P1, 'hand')
        seen = []
        t.pokemon = lambda cands, prompt: seen.extend(cands) or cands[0]
        await t.play(card)
        self.assertIn(dig, seen)
        self.assertNotIn(dug, seen, 'Alolan Dugtrio has no evolution')


class PicnicBasket(Base):
    def test_needs_damage_somewhere(self):
        t, me = self.board()
        c = t.put('SV1.PicnicBasket_184', P1, 'hand')
        self.assertFalse(t.offers(c))
        opp = t.active(P2)
        opp.set_attribute(AttrID.HP, opp.get_attribute(AttrID.HP) - 10)
        self.assertTrue(t.offers(c), "the opponent's damaged Pokemon counts")


if __name__ == '__main__':
    unittest.main()


class ConcedeDuringOpponentPrompt(Base):
    """PlayerA vs PlayerB (Oct 15 03:09): PlayerB conceded during
    Skyla's search; PlayerA still had the 'opponent is deciding' banner and his
    screen stayed on the board. The banner must be closed BEFORE the result."""

    async def test_banner_closed_before_game_completed(self):
        import types
        from unittest.mock import patch
        from tests.test_prompt_timeouts import net_player
        from spirit.game.session.game_session import GameSession, GameOver
        from spirit.game.session.constants import GamePhase
        t, me = self.board()
        s = t.session
        watcher = net_player(P1, 'PlayerA')
        s.players[P1] = watcher
        s.game_phase = GamePhase.TURN_LOOP
        s.end_game = types.MethodType(GameSession.end_game, s)
        await s._send_pause_prompt(watcher, 'Opponent is deciding')
        watcher.client_handler.send_packet.reset_mock()
        with patch('spirit.game.session.game_session.run_db', new=lambda *a, **k: _noop()), \
                patch.object(s, '_record_tournament_results', new=lambda *a: _noop()), \
                patch.object(s, '_record_legacy_tournament_result', new=lambda *a: _noop()), \
                patch.object(s, '_record_player_stats', new=lambda *a: _noop()), \
                patch.object(s, '_push_wallet_updates', new=lambda *a: _noop()), \
                patch.object(s, '_push_account_updates', new=lambda *a: _noop()), \
                patch.object(s, '_all_time_points', new=lambda *a: _noop({})):
            try:
                await s.end_game(P1, 'PlayerB conceded')
            except GameOver:
                pass
        sent = [str(c.args) for c in watcher.client_handler.send_packet.await_args_list]
        close_at = next(i for i, x in enumerate(sent) if 'ClosePauseOnPrompt' in x)
        done_at = next(i for i, x in enumerate(sent) if 'GameCompleted' in x)
        self.assertLess(close_at, done_at)


async def _noop(value=None):
    return value
