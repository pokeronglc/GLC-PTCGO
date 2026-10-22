"""Bug hunt, deck 6 (Lightning): Supporters, Items, Tool and Special Energy."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

L, W = PokemonTypes.LIGHTNING, PokemonTypes.WATER
BLITZLE, ZEBSTRIKA, MAREEP = 'SV08.Blitzle_62', 'SM8.Zebstrika_82', 'SM8.Mareep_76'
TYNAMO, MORPEKO, REGIELEKI = 'ME2PT5.Tynamo_59', 'SWSH2.Morpeko_73', 'SWSH7.Regieleki_60'
SOBBLE = 'SWSH1.Sobble_55'
CANARI, GREEN, VOLKNER = 'ME2PT5.Canari_185', 'SM10.GreensExploration_175', 'SM5.Volkner_135'
ELECTROPOWER, ROD, PAL_PAD = 'SM8.Electropower_172', 'SWSH1.OrdinaryRod_171', 'SV1.PalPad_182'
COUNTER_GAIN = 'SV08.CounterGain_169'
SPEED, VOLTAIC = 'SWSH2.SpeedLightningEnergy_173', 'ME5.VoltaicLightningEnergy_84'
NEST, FLOAT = 'SV1.NestBall_181', 'XY8.FloatStone_137'


class Deck6Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, active=None):
        t = Table(self)
        self.me = t.put(active or self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        for attr in (AttrID.WEAKNESS_TYPES, AttrID.RESISTANCE_TYPES):
            self.opp.set_attribute(attr, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    # --- Canari ---------------------------------------------------------
    async def test_canari_discard_then_up_to_four_lightning(self):
        t = self.table()
        t.deck(P1, [BLITZLE, ZEBSTRIKA, MAREEP, TYNAMO, MORPEKO, SOBBLE])
        junk = t.put(self.item, P1, 'hand')
        seen = {}

        def picks(cards, count, prompt, display):
            if 'iscard' in prompt:
                return [junk]
            seen['names'], seen['count'] = t.names(cards), count
            return cards[:count]
        t.picks = picks
        await t.play(t.put(CANARI, P1, 'hand'))
        self.assertIn(junk, t.zone(P1, 'discard'))
        self.assertEqual(seen['count'], 4)
        self.assertNotIn('Sobble', seen['names'])
        self.assertEqual(len(t.zone(P1, 'hand')), 4)

    async def test_canari_needs_another_card(self):
        t = self.table()
        card = t.put(CANARI, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Green's Exploration ---------------------------------------------
    async def test_greens_exploration_two_trainers(self):
        t = self.table()
        t.put(ZEBSTRIKA, P2, 'bench')                    # opponent's Abilities don't matter
        t.deck(P1, [NEST, FLOAT, BLITZLE, t.basic_energy(L)])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (
            seen.setdefault('n', (t.names(cards), count)), [c for c in cards if def_for(c.archetype_id).display_name in ('Nest Ball', 'Float Stone')])[1]
        card = t.put(GREEN, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        names, count = seen['n']
        self.assertEqual(count, 2)
        self.assertNotIn('Blitzle', names)
        self.assertEqual(self.hand_names(t), ['Float Stone', 'Nest Ball'])

    async def test_greens_exploration_blocked_by_own_ability_pokemon(self):
        t = self.table()
        t.put(ZEBSTRIKA, P1, 'bench')
        card = t.put(GREEN, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Volkner -------------------------------------------------------
    async def test_volkner_item_and_lightning_energy(self):
        t = self.table()
        _, lightning, water, _ = t.deck(P1, [NEST, t.basic_energy(L), t.basic_energy(W), FLOAT])
        seen = []

        async def groups(pid, source_id, specs, prompt, display_cards=None, total=None, any_of=False):
            out = []
            for spec in specs:
                seen.append(t.names(spec['cards']))
                pref = [c for c in spec['cards'] if def_for(c.archetype_id).display_name != 'Pokégear 3.0']
                out.append([c.entity_id for c in (pref + list(spec['cards']))[:spec['count']]])
            return out
        with patch.object(t.session, 'prompt_card_chooser_groups', groups):
            await t.play(t.put(VOLKNER, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertIn('Nest Ball', t.names(hand))
        self.assertIn(lightning, hand)
        self.assertNotIn(water, hand)
        for names in seen:
            self.assertNotIn('Float Stone', names)        # a Tool isn't an Item card

    # --- Electropower --------------------------------------------------
    async def test_electropower_plus_30_lightning_to_active_this_turn(self):
        t = self.table(BLITZLE)
        t.energy(self.me, L, 2)
        await t.play(t.put(ELECTROPOWER, P1, 'hand'))
        await t.attack(self.me, 'Static Shock')
        self.assertEqual(400 - t.hp(self.opp), 50)

    async def test_electropower_not_for_non_lightning_or_next_turn(self):
        t = self.table(SOBBLE)
        t.energy(self.me, W, 2)
        await t.play(t.put(ELECTROPOWER, P1, 'hand'))
        await t.attack(self.me, 'Water Gun')
        self.assertEqual(400 - t.hp(self.opp), 20)
        # next own turn: the bonus is gone
        t = self.table(BLITZLE)
        t.energy(self.me, L, 2)
        await t.play(t.put(ELECTROPOWER, P1, 'hand'))
        t.next_turn(); t.next_turn()
        await t.attack(self.me, 'Static Shock')
        self.assertEqual(400 - t.hp(self.opp), 20)

    # --- Ordinary Rod ----------------------------------------------------
    async def test_ordinary_rod_pokemon_and_basic_energy(self):
        t = self.table()
        for spec in (BLITZLE, MAREEP, TYNAMO):
            t.put(spec, P1, 'discard')
        for _ in range(3):
            t.put(t.basic_energy(L), P1, 'discard')
        t.put(SPEED, P1, 'discard')
        deck = len(t.zone(P1, 'deck'))
        # Oct 12: "Choose 1 or both" asks for the option(s) first.
        from unittest.mock import patch
        from spirit.game.session.effects import EffectContext

        async def both(ctx, prompt, buttons, *a, **k):
            return buttons.index('Both')
        with patch.object(EffectContext, 'choose', both):
            await t.play(t.put(ROD, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 4)
        self.assertIn('Speed Lightning Energy', t.names(t.zone(P1, 'discard')))

    async def test_ordinary_rod_needs_pokemon_or_basic_energy(self):
        t = self.table()
        t.put(SPEED, P1, 'discard')
        t.put(NEST, P1, 'discard')
        rod = t.put(ROD, P1, 'hand')
        self.assertFalse(t.can(rod, 'UseTrainerCard'))

    # --- Pal Pad -----------------------------------------------------------
    async def test_pal_pad_up_to_two_supporters(self):
        t = self.table()
        for spec in (CANARI, VOLKNER, GREEN, NEST):
            t.put(spec, P1, 'discard')
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', (t.names(cards), count)), cards[:count])[1]
        deck = len(t.zone(P1, 'deck'))
        await t.play(t.put(PAL_PAD, P1, 'hand'))
        names, count = seen['n']
        self.assertEqual(count, 2)
        self.assertNotIn('Nest Ball', names)
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 2)

    async def test_pal_pad_needs_supporter_in_discard(self):
        t = self.table()
        t.put(NEST, P1, 'discard')
        pad = t.put(PAL_PAD, P1, 'hand')
        self.assertFalse(t.can(pad, 'UseTrainerCard'))

    # --- Counter Gain --------------------------------------------------
    async def test_counter_gain_one_colorless_less_when_behind(self):
        for mine, theirs, offered in ((4, 3, True), (3, 3, False), (3, 4, False)):
            t = self.table(ZEBSTRIKA)          # Head Bolt: [L][C]
            t.energy(self.me, L)
            t.attach(COUNTER_GAIN, self.me)
            t.set_prizes(P1, mine); t.set_prizes(P2, theirs)
            with self.subTest(mine=mine, theirs=theirs):
                self.assertEqual(t.attack_offer(self.me, 'Head Bolt') is not None, offered)

    async def test_counter_gain_cannot_reduce_typed_cost(self):
        t = self.table(BLITZLE)               # Static Shock: [L][C]
        t.energy(self.me, W)                  # wrong type
        t.attach(COUNTER_GAIN, self.me)
        t.set_prizes(P1, 5); t.set_prizes(P2, 2)
        self.assertIsNone(t.attack_offer(self.me, 'Static Shock'))

    # --- Speed Lightning Energy -------------------------------------------
    async def test_speed_lightning_draws_two_on_lightning(self):
        t = self.table(BLITZLE)
        energy = t.put(SPEED, P1, 'hand')
        await t.play(energy, targets=[self.me.entity_id])
        self.assertIn(energy, self.me.children)
        self.assertEqual(len(t.zone(P1, 'hand')), 2)
        t.energy(self.me, PokemonTypes.FIRE)
        self.assertIsNotNone(t.attack_offer(self.me, 'Static Shock'))   # provides [L]

    async def test_speed_lightning_no_draw_on_other_types(self):
        t = self.table(SOBBLE)
        energy = t.put(SPEED, P1, 'hand')
        await t.play(energy, targets=[self.me.entity_id])
        self.assertIn(energy, self.me.children)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    # --- Voltaic Lightning Energy -----------------------------------------
    async def test_voltaic_plus_20_for_lightning_to_active(self):
        t = self.table(BLITZLE)
        t.energy(self.me, PokemonTypes.FIRE)
        t.attach(VOLTAIC, self.me)
        await t.attack(self.me, 'Static Shock')       # [L] paid by Voltaic
        self.assertEqual(400 - t.hp(self.opp), 40)

    async def test_voltaic_no_bonus_for_non_lightning(self):
        t = self.table(SOBBLE)
        t.energy(self.me, W)
        t.attach(VOLTAIC, self.me)
        await t.attack(self.me, 'Water Gun')
        self.assertEqual(400 - t.hp(self.opp), 20)

    async def test_voltaic_no_bonus_on_bench_damage(self):
        t = self.table(MORPEKO)
        t.energy(self.me, L)
        t.attach(VOLTAIC, self.me)
        bench = t.put(self.filler, P2, 'bench')
        before = t.hp(bench)
        await t.attack(self.me, 'Spark')
        self.assertEqual(400 - t.hp(self.opp), 70)
        self.assertEqual(before - t.hp(bench), 20)


if __name__ == "__main__":
    unittest.main()
