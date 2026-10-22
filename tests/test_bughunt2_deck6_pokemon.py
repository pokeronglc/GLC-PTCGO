"""Bug hunt round 2, deck 6 (Metal): the Pokémon."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

M, W, D = PokemonTypes.METAL, PokemonTypes.WATER, PokemonTypes.DARKNESS
MEOWTH, PERRSERKER = 'SWSH2.GalarianMeowth_126', 'SWSH4.GalarianPerrserker_113'
DIALGA, DURANT, KLEFKI = 'CEL25.Dialga_20', 'XY2.Durant_61', 'ME3.Klefki_59'
PALAFIN = 'SV05.Palafin_49'          # two attacks: Vanguard Punch [W], Double Hit [W][C][C]
NEST, FLOAT = 'SV1.NestBall_181', 'XY8.FloatStone_137'


class RecordingTable(Table):
    """Also records which player each card chooser was shown to."""
    def _patches(self):
        patches = super()._patches()
        table = self
        table.choosers = []
        inner = patches[0].new

        async def choose_cards(ctx, cards, count, minimum=None, prompt='', player_id=None, **k):
            table.choosers.append(player_id or ctx.player_id)
            return await inner(ctx, cards, count, minimum, prompt, player_id, **k)
        patches[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
        return patches


class Deck6Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, cls=Table):
        t = cls(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    # --- Galarian Meowth: Evolution Roar --------------------------------
    async def test_evolution_roar_discards_two_and_finds_perrserker(self):
        t = self.table()
        meowth = t.put(MEOWTH, P1, 'bench')
        t.put(self.filler, P1, 'active')
        t.put(self.item, P1, 'hand'); t.put(self.item, P1, 'hand')
        t.deck(P1, [PERRSERKER, DIALGA])
        await t.use(meowth, 'Evolution Roar')
        self.assertEqual(len(t.zone(P1, 'discard')), 2)
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Galarian Perrserker'])
        self.assertIsNone(t.ability_offer(meowth, 'Evolution Roar'))

    async def test_evolution_roar_needs_two_cards(self):
        t = self.table()
        meowth = t.put(MEOWTH, P1, 'active')
        t.put(self.item, P1, 'hand')
        self.assertIsNone(t.ability_offer(meowth, 'Evolution Roar'))

    # --- Galarian Perrserker: Stealy Claws ---------------------------------
    async def test_stealy_claws_discards_trainers_per_heads(self):
        for heads, discarded in ((True, 2), (False, 0)):
            t = self.table()
            perr = t.put(PERRSERKER, P1, 'active')
            t.energy(perr, M)
            for spec in (NEST, FLOAT, DIALGA, DURANT):
                t.put(spec, P2, 'hand')
            t.heads = heads
            await t.attack(perr, 'Stealy Claws')
            with self.subTest(heads=heads):
                self.assertEqual(400 - t.hp(self.opp), 20)
                self.assertEqual(len(t.zone(P2, 'discard')), discarded)
                self.assertIn('Dialga', t.names(t.zone(P2, 'hand')))
                self.assertIn('Durant', t.names(t.zone(P2, 'hand')))

    # Was a bug (fixed Oct 10): Stealy Claws lets the OPPONENT pick which Trainer to discard (discard_from_hand player_id=opponent)
    async def test_stealy_claws_attacker_chooses(self):
        t = self.table(RecordingTable)
        perr = t.put(PERRSERKER, P1, 'active')
        t.energy(perr, M)
        t.put(NEST, P2, 'hand'); t.put(FLOAT, P2, 'hand')
        flips = iter([True, False, False])
        t.heads = lambda title: next(flips)
        await t.attack(perr, 'Stealy Claws')
        self.assertEqual(len(t.zone(P2, 'discard')), 1)
        self.assertEqual(t.choosers, [P1])

    # --- Dialga ----------------------------------------------------------
    async def test_temporal_backflow_recovers_a_card(self):
        t = self.table()
        dialga = t.put(DIALGA, P1, 'active')
        t.energy(dialga, M)
        nest = t.put(NEST, P1, 'discard')
        await t.attack(dialga, 'Temporal Backflow')
        self.assertIn(nest, t.zone(P1, 'hand'))
        self.assertEqual(t.hp(self.opp), 400)

    async def test_temporal_backflow_empty_discard(self):
        # An attack may be used even when its effect does nothing; it must not
        # take a card from the opponent's discard pile.
        t = self.table()
        dialga = t.put(DIALGA, P1, 'active')
        t.energy(dialga, M)
        theirs = t.put(NEST, P2, 'discard')
        await t.attack(dialga, 'Temporal Backflow')
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertIn(theirs, t.zone(P2, 'discard'))

    async def test_metal_blast_counts_metal_only(self):
        t = self.table()
        dialga = t.put(DIALGA, P1, 'active')
        t.energy(dialga, M, 2)
        t.energy(dialga, W, 1)
        await t.attack(dialga, 'Metal Blast')
        self.assertEqual(400 - t.hp(self.opp), 100)

    # --- Durant: Chip Off --------------------------------------------------
    async def test_chip_off_to_four(self):
        for size, left in ((7, 4), (4, 4), (2, 2)):
            t = self.table()
            durant = t.put(DURANT, P1, 'active')
            t.energy(durant, M)
            for _ in range(size):
                t.put(self.item, P2, 'hand')
            await t.attack(durant, 'Chip Off')
            with self.subTest(size=size):
                self.assertEqual(len(t.zone(P2, 'hand')), left)
                self.assertEqual(len(t.zone(P2, 'discard')), size - left)

    # --- Klefki: Memory Lock --------------------------------------------
    async def test_memory_lock_blocks_chosen_attack_only(self):
        t = self.table()
        klefki = t.put(KLEFKI, P1, 'active')
        t.energy(klefki, M)
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        palafin = t.put(PALAFIN, P2, 'active')
        palafin.set_attribute(AttrID.WEAKNESS_TYPES, [])
        palafin.set_attribute(AttrID.RESISTANCE_TYPES, [])
        t.energy(palafin, W, 3)
        offered = []

        async def pick(ctx, candidates, prompt=''):
            offered.extend(a.title for _, a in candidates)
            return next(c for c in candidates if c[1].title == 'Double Hit')
        before = t.hp(palafin)
        with patch.object(EffectContext, 'choose_attack_to_copy', pick):
            await t.attack(klefki, 'Memory Lock')
        self.assertEqual(before - t.hp(palafin), 30)
        self.assertEqual(sorted(offered), ['Double Hit', 'Vanguard Punch'])
        t.next_turn()
        self.assertIsNone(t.attack_offer(palafin, 'Double Hit', P2))
        self.assertIsNotNone(t.attack_offer(palafin, 'Vanguard Punch', P2))
        # Klefki itself is not locked on its next turn
        t.next_turn()
        self.assertIsNotNone(t.attack_offer(klefki, 'Memory Lock'))


if __name__ == "__main__":
    unittest.main()
