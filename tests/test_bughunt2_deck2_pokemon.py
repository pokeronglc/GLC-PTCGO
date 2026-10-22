"""Bug hunt round 2, deck 2 (Psychic): Natu, Smoochum, Zacian."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

P = PokemonTypes.PSYCHIC
NATU, SMOOCHUM, ZACIAN = 'SM12.Natu_78', 'SV08.Smoochum_75', 'ME2.Zacian_45'
GUZMA, N, NEST, ARTAZON = 'SM3.Guzma_115', 'XY10.N_105', 'SV1.NestBall_181', 'SV2.Artazon_171'
SABLEYE = 'SV2.Sableye_136'


class Deck2Pokemon(unittest.IsolatedAsyncioTestCase):
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

    # --- Natu: Future Sight --------------------------------------------------
    async def _future_sight(self, t, natu, side):
        """Run Future Sight choosing `side` (0 = mine, 1 = opponent's) and
        reversing the shown cards; returns what the chooser saw."""
        from unittest.mock import patch
        from spirit.game.session.effects import EffectContext
        seen = {}

        async def choose(ctx, prompt, buttons, *a, **k):
            seen['menu'] = list(buttons)
            return side

        async def chooser(player_id, source_id, cards, count, minimum=None, prompt='', ordered=False, **k):
            seen['cards'] = list(cards)
            seen['chooser'] = player_id
            return [c.entity_id for c in reversed(list(cards))]
        with patch.object(EffectContext, 'choose', choose), \
                patch.object(t.session, 'prompt_card_chooser', chooser):
            await t.attack(natu, 'Future Sight')
        return seen

    async def test_future_sight_reorders_my_top_four(self):
        t = self.table()
        natu = t.put(NATU, P1, 'active')
        t.energy(natu, P)
        tops = t.deck(P1, [GUZMA, N, NEST, ARTAZON])      # ARTAZON is the top card
        seen = await self._future_sight(t, natu, 0)
        self.assertEqual(len(seen['cards']), 4)
        deck = t.zone(P1, 'deck')
        self.assertEqual(len(deck), 34)
        # chooser's first pick (old bottom-most of the 4, Guzma) is the new top
        self.assertEqual([id(c) for c in deck[-4:]], [id(c) for c in tops][::-1])
        self.assertEqual(len(t.zone(P2, 'deck')), 30)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)
        self.assertEqual(400 - t.hp(self.opp), 0)

    async def test_future_sight_on_opponents_deck(self):
        t = self.table()
        natu = t.put(NATU, P1, 'active')
        t.energy(natu, P)
        tops = t.deck(P2, [GUZMA, N, NEST, ARTAZON])
        seen = await self._future_sight(t, natu, 1)
        self.assertEqual(seen['chooser'], P1)
        self.assertEqual({id(c) for c in seen['cards']}, {id(c) for c in tops})
        deck = t.zone(P2, 'deck')
        self.assertEqual(len(deck), 34)
        self.assertEqual([id(c) for c in deck[-4:]], [id(c) for c in tops][::-1])

    # --- Smoochum: Delightful Kiss ------------------------------------------
    async def test_delightful_kiss_two_psychic_to_one_benched(self):
        t = self.table()
        smoo = t.put(SMOOCHUM, P1, 'active')
        bench = t.put(SABLEYE, P1, 'bench')
        t.deck(P1, [t.basic_energy(P), t.basic_energy(P), t.basic_energy(P),
                    t.basic_energy(PokemonTypes.WATER)])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('c', (len(cards), count)), cards[:count])[1]
        await t.attack(smoo, 'Delightful Kiss')    # costs nothing
        self.assertEqual(seen['c'][1], 2)
        energies = t.board.attached_energies(bench)
        self.assertEqual(len(energies), 2)
        for e in energies:
            self.assertIn(P.value, e.get_attribute(AttrID.POKEMON_TYPES) or [])
        self.assertEqual(t.board.attached_energies(smoo), [])

    async def test_delightful_kiss_never_to_active_or_other_types(self):
        t = self.table()
        smoo = t.put(SMOOCHUM, P1, 'active')
        t.deck(P1, [t.basic_energy(PokemonTypes.WATER)])
        bench = t.put(SABLEYE, P1, 'bench')
        await t.attack(smoo, 'Delightful Kiss')
        self.assertEqual(t.board.attached_energies(bench), [])
        # Psychic Energy, but no Benched Pokémon: nothing goes to the Active
        t = self.table()
        smoo = t.put(SMOOCHUM, P1, 'active')
        t.deck(P1, [t.basic_energy(P)])
        await t.attack(smoo, 'Delightful Kiss')
        self.assertEqual(t.board.attached_energies(smoo), [])

    # --- Zacian: Limit Break --------------------------------------------------
    async def test_limit_break_bonus_at_three_prizes(self):
        for prizes, dmg in ((4, 50), (3, 140), (1, 140)):
            t = self.table()
            zac = t.put(ZACIAN, P1, 'active')
            t.energy(zac, P, 2)
            t.set_prizes(P2, prizes)
            t.set_prizes(P1, 6)
            await t.attack(zac, 'Limit Break')
            with self.subTest(prizes=prizes):
                self.assertEqual(400 - t.hp(self.opp), dmg)

    async def test_limit_break_counts_opponents_prizes_not_mine(self):
        t = self.table()
        zac = t.put(ZACIAN, P1, 'active')
        t.energy(zac, P, 2)
        t.set_prizes(P1, 2)
        await t.attack(zac, 'Limit Break')
        self.assertEqual(400 - t.hp(self.opp), 50)


if __name__ == "__main__":
    unittest.main()
