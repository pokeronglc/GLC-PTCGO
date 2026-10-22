"""Oct 16 (owner): the game log never showed Trainer cards played.  The
owner's TrainerCard bracket wraps the ->activeTrainer move so the client's
move logger skips it, and Stadium moves are never logged.  The server now
sends an AbilityPlayedEffect for the card (pie-src L.o logs PlayTrainer)."""
import unittest
from unittest.mock import patch

from tests.test_untested_trainers import Base
from tests.bughunt_table import Table
from spirit.game.session.game_session import GameSession
from spirit.tools.effect_smoke import P1, P2


def _walk(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _walk(v)


class TrainerGameLog(Base):
    async def played(self, play):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        sent = []
        real = GameSession.send_game_sequence

        async def record(session, players, name, inner):
            ids = {pid for pid, p in session.players.items() if p in players}
            if str(getattr(name, 'value', name)) != 'SerialSequence':
                return await real(session, players, name, inner)
            for m in _walk(inner):
                if m.get('eID') and m.get('abilityType') == 'Attack':
                    sent.append((frozenset(ids), m['eID'], m['abilityTitle']['id']))
            return await real(session, players, name, inner)
        with patch.object(GameSession, 'send_game_sequence', record):
            card = await play(t)
        return card, sent

    async def test_item_logged_for_its_player(self):
        async def play(t):
            card = t.put('SM3.Guzma_115', P1, 'hand')
            t.picks = lambda cards, count, prompt, shown: list(cards)[:count]
            t.pokemon = lambda cands, prompt: cands[0] if cands else None
            t.put(self.filler, P2, 'bench')
            await t.play(card)
            return card
        card, sent = await self.played(play)
        self.assertIn((frozenset({P1}), card.entity_id, 'Guzma'), sent)
        self.assertIn((frozenset({P2}), card.entity_id, 'Guzma'), sent)

    async def test_stadium_logged_for_both(self):
        async def play(t):
            card = t.put('SV2.Artazon_171', P1, 'hand')
            await t.play(card)
            return card
        card, sent = await self.played(play)
        self.assertIn((frozenset({P1}), card.entity_id, 'Artazon'), sent)
        self.assertIn((frozenset({P2}), card.entity_id, 'Artazon'), sent)


if __name__ == '__main__':
    unittest.main()
