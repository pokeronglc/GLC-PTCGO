"""Bug hunt round 2, deck 5 (Water): Tate & Liza, Aqua Patch, Surfing Beach."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W, D = PokemonTypes.WATER, PokemonTypes.DARKNESS
TATE_LIZA, AQUA_PATCH, SURFING_BEACH = 'SM7.TateLiza_148', 'SM2.AquaPatch_119', 'ME1.SurfingBeach_129'
STARYU, MANAPHY, SABLEYE = 'SV10.MistysStaryu_46', 'SWSH9.Manaphy_41', 'SV2.Sableye_136'


class Deck5Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, active=None):
        t = Table(self)
        self.me = t.put(active or self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def choosing(self, index):
        seen = []

        async def choose(ctx, prompt, buttons, *a, **k):
            seen.append(list(buttons))
            return index
        return patch.object(EffectContext, 'choose', choose), seen

    # --- Tate & Liza ---------------------------------------------------------
    async def test_tate_liza_shuffle_draw_5(self):
        t = self.table()
        for _ in range(3):
            t.put(self.filler, P1, 'hand')
        card = t.put(TATE_LIZA, P1, 'hand')
        p, seen = self.choosing(0)
        with p:
            await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 5)
        self.assertIn(card, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'deck')), 30 + 3 - 5)

    async def test_tate_liza_switch(self):
        t = self.table()
        bench = t.put(SABLEYE, P1, 'bench')
        t.put(self.filler, P1, 'hand')
        card = t.put(TATE_LIZA, P1, 'hand')
        p, seen = self.choosing(1)
        with p:
            await t.play(card)
        self.assertIs(t.active(P1), bench)
        self.assertIn(self.me, t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)       # no draw on the switch mode

    async def test_tate_liza_no_bench_still_playable_for_draw(self):
        t = self.table()
        card = t.put(TATE_LIZA, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))

    # --- Aqua Patch ----------------------------------------------------------
    async def test_aqua_patch_attaches_to_benched_water(self):
        t = self.table()
        staryu = t.put(STARYU, P1, 'bench')
        energy = t.put(t.basic_energy(W), P1, 'discard')
        card = t.put(AQUA_PATCH, P1, 'hand')
        self.assertEqual(t.targets(card, 'UseTrainerCard') - {staryu.entity_id}, set())
        await t.play(card, targets=[staryu.entity_id])
        self.assertIn(energy, list(t.board.attached_energies(staryu)))

    async def test_aqua_patch_not_active_or_non_water(self):
        # Only a Water Pokémon on the Active Spot + a non-Water Benched one:
        t = self.table(active=STARYU)
        t.put(SABLEYE, P1, 'bench')
        t.put(t.basic_energy(W), P1, 'discard')
        card = t.put(AQUA_PATCH, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    async def test_aqua_patch_needs_water_energy_in_discard(self):
        t = self.table()
        t.put(STARYU, P1, 'bench')
        t.put(t.basic_energy(D), P1, 'discard')
        card = t.put(AQUA_PATCH, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Surfing Beach --------------------------------------------------------
    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_surfing_beach_water_to_water_once(self):
        t = self.table(active=STARYU)
        manaphy = t.put(MANAPHY, P1, 'bench')
        t.put(SABLEYE, P1, 'bench')
        beach = t.stadium(SURFING_BEACH, P2)        # either player's Stadium
        entry = self.stadium_action(t, beach)
        self.assertIsNotNone(entry)
        t.pokemon = lambda c, p: manaphy if manaphy in c else c[0]
        await t.do(entry)
        self.assertIs(t.active(P1), manaphy)
        self.assertIsNone(self.stadium_action(t, beach))

    async def test_surfing_beach_only_benched_water_offered(self):
        t = self.table(active=STARYU)
        t.put(MANAPHY, P1, 'bench')
        t.put(SABLEYE, P1, 'bench')
        beach = t.stadium(SURFING_BEACH, P1)
        offered = []
        t.pokemon = lambda c, p: (offered.extend(c), c[0])[1]
        await t.do(self.stadium_action(t, beach))
        from spirit.game.data_utils import def_for
        self.assertEqual([def_for(x.archetype_id).display_name for x in offered], ['Manaphy'])

    async def test_surfing_beach_not_offered_non_water(self):
        t = self.table()                            # Snorlax Active
        t.put(MANAPHY, P1, 'bench')
        beach = t.stadium(SURFING_BEACH, P1)
        self.assertIsNone(self.stadium_action(t, beach))
        t = self.table(active=STARYU)
        t.put(SABLEYE, P1, 'bench')                 # no Water on the Bench
        beach = t.stadium(SURFING_BEACH, P1)
        self.assertIsNone(self.stadium_action(t, beach))

    async def test_surfing_beach_opponent_can_use_on_their_turn(self):
        t = self.table()
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        t.put(STARYU, P2, 'active')
        t.put(MANAPHY, P2, 'bench')
        beach = t.stadium(SURFING_BEACH, P1)
        t.next_turn()
        self.assertIsNotNone(self.stadium_action(t, beach, P2))


if __name__ == "__main__":
    unittest.main()
