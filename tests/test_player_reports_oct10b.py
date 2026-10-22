"""Player reports (Oct 10, evening): Call Bell / go-second Items, Recycle
Energy, Iron Bundle's Hyper Blower, Morty and every Trainer that looks at
the opponent's hand."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, D, P, G = PokemonTypes.WATER, PokemonTypes.DARKNESS, PokemonTypes.PSYCHIC, PokemonTypes.GRASS
SABLEYE = 'SV2.Sableye_136'            # Unseen Claw 20
RECYCLE = 'SM11.RecycleEnergy_212'
HOP = 'CZ.Hop_133'
HELMET, LAVENDER = 'SWSH6.RuggedHelmet_152', 'SM9.LavenderTown_147'
IRON_BUNDLES = ['SV4.IronBundle_56',   # SV06/SV08 printings have no Hyper Blower
                'SVP.IronBundle_58', 'SVP.IronBundle_66']
GO_SECOND_ITEMS = ['SV08.CallBell_165', 'SV08.ChillTeaserToy_166', 'SM8.WaitandSeeHammer_192']


def name(card):
    return def_for(card.archetype_id).display_name


class Reports(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def neutral(self, mon, hp=None):
        mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            mon.set_attribute(AttrID.HP, hp)
        return mon

    # --- Call Bell & co: only going second, only on your first turn ---------
    def _go_second_board(self, turn):
        t = Table(self)
        t.state.turn_number = turn
        opp = t.put(self.filler, P2, 'active')
        t.energy(opp, W)                     # Chill Teaser Toy / Hammer need an Energy
        t.put(self.filler, P1, 'active')
        t.deck(P1, [HOP])                    # Call Bell needs a Supporter to find
        return t

    async def test_go_second_items_only_on_turn_two(self):
        for spec in GO_SECOND_ITEMS:
            for turn, legal in ((1, False), (2, True), (3, False), (4, False)):
                with self.subTest(card=spec, turn=turn):
                    t = self._go_second_board(turn)
                    card = t.put(spec, P1, 'hand')
                    self.assertEqual(t.can(card, 'UseTrainerCard'), legal)

    # --- Recycle Energy: only itself returns to hand ------------------------
    async def test_recycle_energy_ko_returns_only_itself(self):
        t = Table(self)
        opp = t.put(SABLEYE, P2, 'active')
        t.energy(opp, D)
        victim = self.neutral(t.put(self.filler, P1, 'active', hp=10))
        recycle = t.attach(RECYCLE, victim)
        basics = [t.energy(victim, G), t.energy(victim, G)]
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        await t.attack(opp, 'Unseen Claw', pid=P2)
        self.assertIn(recycle, t.zone(P1, 'hand'))
        for energy in basics:
            self.assertIn(energy, t.zone(P1, 'discard'))
            self.assertNotIn(energy, t.zone(P1, 'hand'))

    # --- Iron Bundle: Hyper Blower discards Iron Bundle ---------------------
    async def test_hyper_blower_discards_iron_bundle(self):
        for spec in IRON_BUNDLES:
            with self.subTest(card=spec):
                t = Table(self)
                old_active = t.put(self.filler, P2, 'active')
                new_active = t.put(self.filler, P2, 'bench')
                t.put(self.filler, P1, 'active')
                bundle = t.put(spec, P1, 'bench')
                energy = t.energy(bundle, W)
                await t.use(bundle, 'Hyper Blower')
                self.assertIs(t.active(P2), new_active)
                self.assertIn(old_active, t.zone(P2, 'bench'))
                self.assertIn(bundle, t.zone(P1, 'discard'))
                self.assertIn(energy, t.zone(P1, 'discard'))
                self.assertNotIn(bundle, t.zone(P1, 'bench'))

    # --- Trainers that look at the opponent's hand --------------------------
    async def _hand_trainer(self, spec, opp_hand, *, my_hand=(), yes=True):
        t = Table(self)
        t.yes = yes
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        opp_cards = [t.put(c, P2, 'hand') for c in opp_hand]
        mine = [t.put(c, P1, 'hand') for c in my_hand]
        card = t.put(spec, P1, 'discard')     # resolving card is out of the hand
        before = {'my_hand': len(t.zone(P1, 'hand')),
                  'opp_deck': len(t.zone(P2, 'deck'))}
        await t.effect(spec, card)
        return t, opp_cards, mine, before

    def energy_def(self, t, kind=G):
        return t.basic_energy(kind)

    async def test_morty_shuffles_two_chosen_cards(self):
        t0 = Table(self)
        e = self.energy_def(t0)
        t, opp, _, before = await self._hand_trainer(
            'SM8.Morty_186', [self.item, self.filler, e])
        self.assertEqual(len(t.zone(P2, 'hand')), 1)
        self.assertEqual(len(t.zone(P2, 'deck')), before['opp_deck'] + 2)

    async def test_clive_draws_two_per_supporter(self):
        t, *_ , before = await self._hand_trainer('SV045.Clive_78', [HOP, HOP, self.item])
        self.assertEqual(len(t.zone(P1, 'hand')) - before['my_hand'], 4)

    async def test_emma_draws_one_per_pokemon(self):
        t, *_ , before = await self._hand_trainer('ME4.Emma_77', [self.filler, self.filler, self.item])
        self.assertEqual(len(t.zone(P1, 'hand')) - before['my_hand'], 2)

    async def test_acerolas_premonition_draws_per_trainer(self):
        t, *_ , before = await self._hand_trainer(
            'SWSH9.AcerolasPremonition_129', [self.item, HOP, self.filler])
        self.assertEqual(len(t.zone(P1, 'hand')) - before['my_hand'], 2)

    async def test_energy_swatter_energy_to_bottom(self):
        t0 = Table(self)
        t, opp, _, _ = await self._hand_trainer('ME3.EnergySwatter_73', [self.energy_def(t0), self.item])
        self.assertIs(t.zone(P2, 'deck')[0], opp[0])

    async def test_eri_discards_two_items(self):
        t, opp, _, _ = await self._hand_trainer('SV05.Eri_146', [self.item] * 3)
        self.assertEqual(len(t.zone(P2, 'discard')), 2)

    async def test_erikas_invitation_benches_and_switches(self):
        t, opp, _, _ = await self._hand_trainer('SV035.ErikasInvitation_160', [self.filler])
        self.assertIs(t.active(P2), opp[0])

    async def test_grabber_pokemon_to_bottom(self):
        t, opp, _, _ = await self._hand_trainer('SV035.Grabber_162', [self.item, self.filler])
        self.assertIs(t.zone(P2, 'deck')[0], opp[1])

    async def test_mars_discards_random_card(self):
        t, opp, _, before = await self._hand_trainer('SM5.Mars_128', [self.item] * 3)
        self.assertEqual(len(t.zone(P2, 'hand')), 2)
        self.assertEqual(len(t.zone(P2, 'discard')), 1)
        self.assertEqual(len(t.zone(P1, 'hand')) - before['my_hand'], 2)

    async def test_ortega_bottom_then_opponent_may_draw(self):
        t, opp, _, _ = await self._hand_trainer('SV085.Ortega_141', [self.filler])
        self.assertIs(t.zone(P2, 'deck')[0], opp[0])
        self.assertEqual(len(t.zone(P2, 'hand')), 1)

    async def test_team_skull_grunt_discards_two_energy(self):
        t0 = Table(self)
        e = self.energy_def(t0)
        t, opp, _, _ = await self._hand_trainer('SM1.TeamSkullGrunt_133', [e, e, self.item])
        self.assertEqual(sorted(c is opp[2] for c in t.zone(P2, 'hand')), [True])
        self.assertEqual(len(t.zone(P2, 'discard')), 2)

    async def test_tormenting_spray_discards_random_supporter(self):
        t, opp, _, _ = await self._hand_trainer('SM3.TormentingSpray_125', [HOP])
        self.assertIn(opp[0], t.zone(P2, 'discard'))

    async def test_sidney_discards_tool_and_stadium(self):
        t, opp, _, _ = await self._hand_trainer('SWSH8.Sidney_241', [HELMET, LAVENDER, self.item])
        self.assertEqual(len(t.zone(P2, 'discard')), 2)
        self.assertEqual([c is opp[2] for c in t.zone(P2, 'hand')], [True])

    async def test_oleana_trainer_to_bottom(self):
        t, opp, mine, _ = await self._hand_trainer(
            'SWSH2.Oleana_163', [self.filler, self.item], my_hand=[self.item, self.item])
        self.assertIs(t.zone(P2, 'deck')[0], opp[1])

    async def test_sabrinas_suggestion_copies_supporter(self):
        t, opp, _, before = await self._hand_trainer('SM9.SabrinasSuggestion_154', [HOP])
        self.assertEqual(len(t.zone(P1, 'hand')) - before['my_hand'], 3)   # Hop: draw 3

    async def test_peeking_red_card_reshuffles_their_hand(self):
        t, opp, _, before = await self._hand_trainer('SM4.PeekingRedCard_97', [self.filler] * 3)
        self.assertEqual(len(t.zone(P2, 'hand')), 3)
        self.assertEqual(len(t.zone(P2, 'deck')), before['opp_deck'])

    async def test_bother_bot_turns_prize_face_up(self):
        t, opp, _, _ = await self._hand_trainer('SV10.TeamRocketsBotherBot_172', [self.filler], yes=False)
        self.assertTrue(any(getattr(p, 'publicly_revealed', False) for p in t.zone(P2, 'prizes')))
        self.assertIn(opp[0], t.zone(P2, 'hand'))

    async def test_bother_bot_switch(self):
        t, opp, _, _ = await self._hand_trainer('SV10.TeamRocketsBotherBot_172', [self.filler], yes=True)
        self.assertIn(opp[0], t.zone(P2, 'prizes'))


if __name__ == "__main__":
    unittest.main()
