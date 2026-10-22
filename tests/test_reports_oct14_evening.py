"""Owner reports, Oct 14 (evening)."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.untested_trainer_kit import D, M, neutral
from spirit.game.attributes import AttrID
from spirit.game.session.effects import EffectContext
from spirit.network.message_names import OutboundMsg
from spirit.tools.effect_smoke import P1, P2

COIN = OutboundMsg.MULTIPLE_COIN_FLIP_WITH_CONTEXT_EFFECT.value


class Base(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add


class StealyClaws(Base):
    """Galarian Perrserker SWSH4 113: the coins must be shown BEFORE the
    opponent's hand is revealed and the discard is picked."""

    async def test_coins_shown_before_reveal_and_pick(self):
        t = Table(self)
        me = neutral(t.put('SWSH4.GalarianPerrserker_113', P1, 'active'))
        t.energy(me, M)
        neutral(t.put(self.filler, P2, 'active'), 400)
        for _ in range(3):
            t.put('SWSH1.QuickBall_216', P2, 'hand')
        events = []
        session = t.session
        real_send = session.send_game_sequence

        async def send(players, name, msgs, *a, **k):
            for m in msgs or []:
                if isinstance(m, dict) and m.get('name') == COIN:
                    events.append('coins')
            return await real_send(players, name, msgs, *a, **k)

        async def pick(pid, source_id, cards, count, *a, **k):
            events.append('pick')
            return [c.entity_id for c in list(cards)[:count]]

        async def view(*a, **k):
            events.append('reveal')

        entry = t.attack_offer(me, 'Stealy Claws')
        with patch.object(session, 'send_game_sequence', send), \
                patch.object(session, 'prompt_card_chooser', pick, create=True), \
                patch.object(session, 'prompt_view_cards', view, create=True), \
                patch('spirit.game.session.effects.random.choice', lambda seq: 0):   # heads
            await session._apply_player_action(P1, entry, [], None)
        self.assertEqual(events[:3], ['coins', 'reveal', 'pick'])
        self.assertEqual(len(t.zone(P2, 'hand')), 0, '3 heads: 3 Trainers discarded')


if __name__ == '__main__':
    unittest.main()
