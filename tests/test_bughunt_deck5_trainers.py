"""Bug hunt, deck 5 (Dragon): Supporters, Items and the Stadium, through the
real play-trainer executor (so play conditions and once-per-turn rules apply)."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

W, L, F, R = PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.FIGHTING, PokemonTypes.FIRE
DRATINI, DRAGONITE, GIBLE = 'SM9.Dratini_117', 'SV035.Dragonite_149', 'SM5.Gible_96'
TINGLU, RAYQUAZA, TATSUGIRI = 'SV06.TingLu_110', 'ME2PT5.Rayquaza_153', 'SV06.Tatsugiri_131'
CRISPIN, LANCE = 'SV07.Crispin_133', 'SWSH12.Lance_159'
CHARGE, ROD, MAIL = 'XY11.SpecialCharge_105', 'SV2.SuperRod_188', 'XY6.TrainersMail_92'
STORMY = 'SWSH7.StormyMountains_161'
DDE, RAINBOW = 'XY6.DoubleDragonEnergy_97', 'SM7.RainbowEnergy_151'
BLEND = 'BW6.BlendEnergyWaterLightningFightingMetal_118'
BOSS, NEST = 'SWSH2.BosssOrders_154', 'SV1.NestBall_181'


class Deck5Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def spy(self, t, take=None):
        seen = {'calls': []}

        def picks(cards, count, prompt, display):
            seen['calls'].append((t.names(cards), count, prompt, cards))
            if take is not None:
                return take(cards, count, prompt)
            return cards[:count]
        t.picks = picks
        return seen

    def types(self, card):
        return card.get_attribute(AttrID.POKEMON_TYPES) or []

    # --- Crispin -------------------------------------------------------------
    async def test_crispin_two_types_one_to_hand_one_attached(self):
        t = self.table()
        bench = t.put(DRATINI, P1, 'bench')
        t.deck(P1, [t.basic_energy(W), t.basic_energy(W), t.basic_energy(L), DDE])
        seen = self.spy(t)
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.play(t.put(CRISPIN, P1, 'hand'))
        first = seen['calls'][0]
        self.assertEqual(first[1], 2)
        offered_types = sorted(self.types(c)[0] for c in first[3])
        self.assertEqual(len(offered_types), 2)                 # one Water + one Lightning, no DDE
        self.assertEqual(len(set(offered_types)), 2)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        attached = t.board.attached_energies(bench)
        self.assertEqual(len(attached), 1)
        self.assertNotEqual(self.types(attached[0]), self.types(t.zone(P1, 'hand')[0]))

    async def test_crispin_single_type_only_to_hand(self):
        t = self.table()
        t.deck(P1, [t.basic_energy(W), t.basic_energy(W)])
        seen = self.spy(t)
        await t.play(t.put(CRISPIN, P1, 'hand'))
        self.assertEqual(len(seen['calls'][0][3]), 1)           # only one Water offered
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(t.board.attached_energies(self.me), [])

    # --- Lance -------------------------------------------------------------------
    async def test_lance_up_to_three_dragons(self):
        t = self.table()
        t.deck(P1, [DRATINI, DRAGONITE, GIBLE, RAYQUAZA, TINGLU, self.filler])
        seen = self.spy(t)
        await t.play(t.put(LANCE, P1, 'hand'))
        names, count, _, _ = seen['calls'][0]
        self.assertEqual(count, 3)
        self.assertEqual(sorted(names), ['Dragonite', 'Dratini', 'Gible', 'Rayquaza'])
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    # --- Special Charge --------------------------------------------------------
    async def test_special_charge_two_special_energy(self):
        t = self.table()
        card = t.put(CHARGE, P1, 'hand')
        t.put(t.basic_energy(W), P1, 'discard')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        for spec in (DDE, RAINBOW, BLEND):
            t.put(spec, P1, 'discard')
        seen = self.spy(t)
        deck = len(t.zone(P1, 'deck'))
        await t.play(card)
        names, count, _, _ = seen['calls'][0]
        self.assertEqual(count, 2)
        self.assertEqual(len(names), 3)                         # the basic Water isn't offered
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 2)

    # --- Super Rod -------------------------------------------------------------
    async def test_super_rod_up_to_three_pokemon_or_basic_energy(self):
        t = self.table()
        card = t.put(ROD, P1, 'hand')
        t.put(DDE, P1, 'discard')
        t.put(BOSS, P1, 'discard')
        self.assertFalse(t.can(card, 'UseTrainerCard'))
        for spec in (DRATINI, GIBLE, t.basic_energy(W), t.basic_energy(L)):
            t.put(spec, P1, 'discard')
        seen = self.spy(t)
        deck = len(t.zone(P1, 'deck'))
        await t.play(card)
        names, count, _, _ = seen['calls'][0]
        self.assertEqual(count, 3)
        self.assertEqual(len(names), 4)
        self.assertNotIn('Double Dragon Energy', names)
        self.assertNotIn("Boss's Orders", names)
        self.assertEqual(len(t.zone(P1, 'deck')), deck + 3)

    # --- Trainers' Mail ----------------------------------------------------------
    async def test_trainers_mail_top_four_trainer_not_itself(self):
        t = self.table()
        t.deck(P1, [BOSS], top=False)                   # out of reach
        t.deck(P1, [MAIL, DRATINI, t.basic_energy(W), NEST])
        seen = self.spy(t)
        await t.play(t.put(MAIL, P1, 'hand'))
        names, count, _, _ = seen['calls'][0]
        self.assertEqual(names, ['Nest Ball'])
        self.assertEqual(t.shown[-1], 4)
        self.assertEqual(self.hand_names(t), ['Nest Ball'])

    # --- Stormy Mountains ---------------------------------------------------------
    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_stormy_mountains_basic_lightning_or_dragon_once(self):
        t = self.table()
        # GLC (Salvatore ruling): the visible Pokémon must allow a Dragon deck
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        t.put(RAYQUAZA, P1, 'active')
        mountains = t.stadium(STORMY, P2)
        t.deck(P1, [TINGLU, self.filler, DRATINI, DRAGONITE])
        seen = self.spy(t)
        entry = self.stadium_action(t, mountains)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(seen['calls'][0][0], ['Dratini'])
        self.assertEqual(t.names(t.zone(P1, 'bench')), ['Dratini'])
        self.assertIsNone(self.stadium_action(t, mountains))

    async def test_stormy_mountains_needs_bench_space(self):
        t = self.table()
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        t.put(RAYQUAZA, P1, 'active')
        for _ in range(5):
            t.put(DRATINI, P1, 'bench')
        mountains = t.stadium(STORMY, P1)
        t.deck(P1, [DRATINI])
        self.assertIsNone(self.stadium_action(t, mountains))


if __name__ == "__main__":
    unittest.main()
