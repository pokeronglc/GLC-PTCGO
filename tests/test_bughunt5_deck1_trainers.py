"""Bug hunt round 5, deck 1 (Lost Zone Psychic): Supporters, Items and
Horror Psychic Energy, through the real play executor."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

PSY, F, W = PokemonTypes.PSYCHIC, PokemonTypes.FIGHTING, PokemonTypes.WATER
SHUPPET, BANETTE, COMFEY = 'SV1.Shuppet_87', 'SWSH11.Banette_73', 'SWSH11.Comfey_79'
SKYLA, COLRESS = 'SWSH2.Skyla_166', 'SWSH11.ColresssExperiment_155'
RECEIVER, SCOOP = 'XY10.RandomReceiver_109', 'SM7.SuperScoopUp_146'
BLENDER, HORN = 'SM8.LostBlender_181', 'SWSH6.EchoingHorn_136'
PUFF, REVIVE = 'XY11.CaptivatingPokPuff_99', 'XY12.Revive_85'
HORROR = 'SWSH2.HorrorPsychicEnergy_172'
HITMONLEE = 'XY3.Hitmonlee_47'
HARD_CHARM = 'XY1.HardCharm_119'


def name(card):
    return def_for(card.archetype_id).display_name


class Deck1Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=None, opp=None):
        t = Table(self)
        self.me = t.put(me or self.filler, P1, 'active')
        self.opp = t.put(opp or self.filler, P2, 'active')
        for p in (self.me, self.opp):
            p.set_attribute(AttrID.WEAKNESS_TYPES, [])
            p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    # --- Skyla (RCL 166) ---------------------------------------------------
    async def test_skyla_finds_only_trainers(self):
        t = self.table()
        t.deck(P1, [COMFEY, HARD_CHARM])
        energy = t.put(t.basic_energy(PSY), P1, 'deck')
        seen = []

        def picks(cards, count, prompt, display):
            seen.extend(cards)
            return [c for c in cards if name(c) == 'Hard Charm'][:1]
        t.picks = picks
        await t.play(t.put(SKYLA, P1, 'hand'))
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Hard Charm'])
        self.assertTrue(seen)
        self.assertFalse(any(name(c) == 'Comfey' for c in seen))
        self.assertNotIn(energy, seen)

    # --- Colress's Experiment (LOR 155) -----------------------------------
    async def test_colress_experiment_3_to_hand_2_lost(self):
        t = self.table()
        top5 = t.deck(P1, [COMFEY, SKYLA, HARD_CHARM, BANETTE, SHUPPET])
        await t.play(t.put(COLRESS, P1, 'hand'))
        hand, lost = t.zone(P1, 'hand'), t.zone(P1, 'lostZone')
        self.assertEqual(len(hand), 3)
        self.assertEqual(len(lost), 2)
        self.assertEqual(set(hand) | set(lost), set(top5))

    async def test_colress_experiment_short_deck_and_empty_deck(self):
        t = Table(self, filler_deck=0)
        t.put(self.filler, P1, 'active'); t.put(self.filler, P2, 'active')
        card = t.put(COLRESS, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        a, b = t.deck(P1, [COMFEY, SKYLA])
        await t.play(card)
        self.assertEqual(set(t.zone(P1, 'hand')), {a, b})
        self.assertEqual(t.zone(P1, 'lostZone'), [])

    # --- Random Receiver (FCO 109) ----------------------------------------
    async def test_random_receiver_finds_supporter(self):
        t = self.table()
        t.deck(P1, [SKYLA, HARD_CHARM, COMFEY])   # Skyla is 3rd from top
        size = len(t.zone(P1, 'deck'))
        await t.play(t.put(RECEIVER, P1, 'hand'))
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Skyla'])
        self.assertEqual(len(t.zone(P1, 'deck')), size - 1)

    async def test_random_receiver_no_supporter(self):
        t = self.table()
        size = len(t.zone(P1, 'deck'))
        await t.play(t.put(RECEIVER, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), size)

    # --- Super Scoop Up (CES 146) -----------------------------------------
    async def test_super_scoop_up_heads_returns_with_attachments(self):
        t = self.table()
        bench = t.put(COMFEY, P1, 'bench')
        energy = t.energy(bench, PSY)
        t.heads = True
        t.pokemon = lambda c, p: bench
        await t.play(t.put(SCOOP, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertIn(bench, hand)
        self.assertIn(energy, hand)
        self.assertEqual(t.zone(P1, 'bench'), [])

    async def test_super_scoop_up_tails_nothing(self):
        t = self.table()
        bench = t.put(COMFEY, P1, 'bench')
        t.heads = False
        await t.play(t.put(SCOOP, P1, 'hand'))
        self.assertIn(bench, t.zone(P1, 'bench'))
        self.assertEqual(t.zone(P1, 'hand'), [])

    async def test_super_scoop_up_active_promotes(self):
        t = self.table()
        bench = t.put(COMFEY, P1, 'bench')
        t.heads = True
        t.pokemon = lambda c, p: self.me if self.me in c else c[0]
        await t.play(t.put(SCOOP, P1, 'hand'))
        self.assertIn(self.me, t.zone(P1, 'hand'))
        self.assertIs(t.active(P1), bench)

    # --- Lost Blender (LOT 181) -------------------------------------------
    async def test_lost_blender_two_to_lost_draw_one(self):
        t = self.table()
        a, b = t.put(COMFEY, P1, 'hand'), t.put(SKYLA, P1, 'hand')
        top = t.deck(P1, [HARD_CHARM])[0]
        blender = t.put(BLENDER, P1, 'hand')
        await t.play(blender)
        self.assertEqual(set(t.zone(P1, 'lostZone')), {a, b})
        self.assertEqual(t.zone(P1, 'hand'), [top])
        self.assertIn(blender, t.zone(P1, 'discard'))

    async def test_lost_blender_needs_two_other_cards(self):
        t = self.table()
        t.put(COMFEY, P1, 'hand')
        blender = t.put(BLENDER, P1, 'hand')
        self.assertFalse(t.can(blender, 'UseTrainerCard'))

    # --- Echoing Horn (CRE 136) -------------------------------------------
    async def test_echoing_horn_benches_opponent_basic(self):
        t = self.table()
        target = t.put(COMFEY, P2, 'discard')
        await t.play(t.put(HORN, P1, 'hand'))
        self.assertIn(target, t.zone(P2, 'bench'))
        self.assertEqual(t.zone(P1, 'bench'), [])

    async def test_echoing_horn_not_playable(self):
        t = self.table()
        t.put(COMFEY, P1, 'discard')            # my own discard does not count
        t.put(BANETTE, P2, 'discard')           # a Stage 1 does not count
        horn = t.put(HORN, P1, 'hand')
        self.assertFalse(t.can(horn, 'UseTrainerCard'))
        t.put(SHUPPET, P2, 'discard')
        self.assertTrue(t.can(horn, 'UseTrainerCard'))
        for _ in range(5):
            t.put(self.filler, P2, 'bench')
        self.assertFalse(t.can(horn, 'UseTrainerCard'))

    # --- Captivating Poké Puff (STS 99) -----------------------------------
    async def test_poke_puff_benches_all_basics(self):
        t = self.table()
        a, b = t.put(COMFEY, P2, 'hand'), t.put(SHUPPET, P2, 'hand')
        stage1 = t.put(BANETTE, P2, 'hand')
        await t.play(t.put(PUFF, P1, 'hand'))
        self.assertEqual(set(t.zone(P2, 'bench')), {a, b})
        self.assertIn(stage1, t.zone(P2, 'hand'))

    async def test_poke_puff_any_number_includes_zero(self):
        t = self.table()
        a = t.put(COMFEY, P2, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        await t.play(t.put(PUFF, P1, 'hand'))
        self.assertIn(a, t.zone(P2, 'hand'))
        self.assertEqual(t.zone(P2, 'bench'), [])

    # --- Revive (EVO 85) --------------------------------------------------
    async def test_revive_basic_to_bench(self):
        t = self.table()
        basic = t.put(COMFEY, P1, 'discard')
        await t.play(t.put(REVIVE, P1, 'hand'))
        self.assertIn(basic, t.zone(P1, 'bench'))

    async def test_revive_not_stage1_or_full_bench(self):
        t = self.table()
        t.put(BANETTE, P1, 'discard')
        revive = t.put(REVIVE, P1, 'hand')
        self.assertFalse(t.can(revive, 'UseTrainerCard'))
        t.put(COMFEY, P1, 'discard')
        self.assertTrue(t.can(revive, 'UseTrainerCard'))
        for _ in range(5):
            t.put(self.filler, P1, 'bench')
        self.assertFalse(t.can(revive, 'UseTrainerCard'))

    # --- Horror Psychic Energy (RCL 172) ----------------------------------
    def horror_table(self, holder_spec=COMFEY, on_bench=False):
        t = self.table(opp=HITMONLEE)
        if on_bench:
            holder = t.put(holder_spec, P1, 'bench')
        else:
            t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
            holder = t.put(holder_spec, P1, 'active')
            t.put(self.filler, P1, 'bench')
        for p in (holder,):
            p.set_attribute(AttrID.WEAKNESS_TYPES, [])
            p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        t.energy(self.opp, F, 2)
        return t, holder

    async def test_horror_active_psychic_hit_retaliates(self):
        t, holder = self.horror_table()
        await t.play(t.put(HORROR, P1, 'hand'), targets=[holder.entity_id])
        t.next_turn()
        before = t.hp(self.opp)
        await t.attack(self.opp, 'Spiral Kick', pid=P2)
        self.assertEqual(t.damage(holder), 30)
        self.assertEqual(before - t.hp(self.opp), 20)

    async def test_horror_retaliates_even_if_knocked_out(self):
        t, holder = self.horror_table()
        await t.play(t.put(HORROR, P1, 'hand'), targets=[holder.entity_id])
        holder.set_attribute(AttrID.HP, 30)
        t.next_turn()
        before = t.hp(self.opp)
        await t.attack(self.opp, 'Spiral Kick', pid=P2)
        self.assertNotIn(holder, t.zone(P1, 'active') + t.zone(P1, 'bench'))
        self.assertEqual(before - t.hp(self.opp), 20)

    async def test_horror_non_psychic_holder_no_retaliation(self):
        t, holder = self.horror_table(holder_spec=self.filler)
        await t.play(t.put(HORROR, P1, 'hand'), targets=[holder.entity_id])
        t.next_turn()
        before = t.hp(self.opp)
        await t.attack(self.opp, 'Spiral Kick', pid=P2)
        self.assertEqual(t.damage(holder), 30)
        self.assertEqual(before - t.hp(self.opp), 0)

    # FIXED (was BUG): Horror Psychic Energy retaliates when its holder is hit on the Bench (card says "is in the Active Spot")
    async def test_horror_benched_holder_no_retaliation(self):
        t, holder = self.horror_table(on_bench=True)
        await t.play(t.put(HORROR, P1, 'hand'), targets=[holder.entity_id])
        t.next_turn()
        t.pokemon = lambda c, p: holder
        t.picks = lambda cards, count, prompt, display: [holder]
        before = t.hp(self.opp)
        await t.attack(self.opp, 'Stretch Kick', pid=P2)
        self.assertEqual(t.damage(holder), 30)
        self.assertEqual(before - t.hp(self.opp), 0)


if __name__ == '__main__':
    unittest.main()
