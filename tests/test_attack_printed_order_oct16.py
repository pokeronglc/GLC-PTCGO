"""Oct 16: the client re-sorts a Pokemon's attacks (Abilities, then cost,
then HIGHER damage first) unless each PIE_ABILITIES row carries `sortOrder`
-- Froslass SM11 showed Spiteful Sigh (printed first, 20x) below Icy Wind
(40).  Every row is now numbered in printed order."""
import json
import unittest

from tests.test_untested_trainers import Base
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID
from spirit.game.data_utils import CARD_DEFS_BY_GUID, def_for, with_printed_order
from spirit.tools.effect_smoke import P1, P2


def rows(defn):
    return json.loads(defn.extra_attributes[str(AttrID.PIE_ABILITIES.value)]["value"])


class PrintedOrder(Base):
    async def test_froslass_rows_numbered_in_printed_order(self):
        t = Table(self)
        f = t.put('SM11.Froslass_38', P1, 'active')
        entries = rows(def_for(f.archetype_id))
        self.assertEqual([e["title"]["id"] for e in entries], ["Spiteful Sigh", "Icy Wind"])
        self.assertEqual([e["sortOrder"] for e in entries], [0, 1])

    async def test_every_card_row_is_numbered(self):
        Table(self)
        for d in CARD_DEFS_BY_GUID.values():
            raw = d.extra_attributes.get(str(AttrID.PIE_ABILITIES.value))
            if raw:
                entries = json.loads(raw["value"])
                self.assertEqual([e.get("sortOrder") for e in entries],
                                 list(range(len(entries))), d.guid)

    async def test_runtime_rows_are_numbered_and_not_shared(self):
        t = Table(self)
        f = t.put('SM11.Froslass_38', P1, 'active')
        t.put(self.filler, P2, 'active')
        session = t.session
        sent = []

        async def capture(*a, **k):
            sent.append(a)
        session.broadcast_packet = capture
        shared = {"abilityType": "PokeAbility", "title": {"id": "X"}, "gameText": {"id": ""}}
        entries = list(f.get_attribute(AttrID.PIE_ABILITIES)) + [shared]
        await session._broadcast_entity_attribute(f, AttrID.PIE_ABILITIES, entries)
        self.assertEqual([e["sortOrder"] for e in f.get_attribute(AttrID.PIE_ABILITIES)], [0, 1, 2])
        self.assertNotIn("sortOrder", shared)
        self.assertEqual([e["sortOrder"] for e in session._pie_ability_entries(f)], [0, 1])

    def test_helper(self):
        self.assertEqual(with_printed_order([{}, "x", {}]), [{"sortOrder": 0}, "x", {"sortOrder": 2}])


if __name__ == '__main__':
    unittest.main()


class PeoniaOneSpotAtATime(Base):
    async def test_each_card_fills_the_next_gap_in_pick_order(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        pile = t.board.find_player_area(P1, 'prizePile')
        keep = list(pile.children)[3:]
        mine = [t.put('SM3.Guzma_115', P1, 'hand') for _ in range(3)]
        prompts, order = [], []

        def picks(cards, count, prompt, shown):
            prompts.append(prompt)
            if 'came from' in prompt:
                card = next(c for c in mine if c in cards)
                order.append(card)
                return [card]
            return list(cards)[:count]
        t.picks = picks
        await t.play(t.put('SWSH6.Peonia_149', P1, 'hand'))
        spot_prompts = [p for p in prompts if 'came from' in p]
        self.assertEqual(len(spot_prompts), 3)
        self.assertIn('(1 of 3)', spot_prompts[0])
        self.assertIn('(3 of 3)', spot_prompts[2])
        self.assertEqual([c.board_slot for c in order], [0, 1, 2])
        self.assertEqual([c.board_slot for c in keep], [3, 4, 5])
