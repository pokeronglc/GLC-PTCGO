"""Bug hunt, deck 5 (Dragon): Tools and Special Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2

W, L, F, R, M = (PokemonTypes.WATER, PokemonTypes.LIGHTNING, PokemonTypes.FIGHTING,
                 PokemonTypes.FIRE, PokemonTypes.METAL)
DRATINI, DRAGONAIR, DRUDDIGON = 'SM9.Dratini_117', 'ME2PT5.Dragonair_151', 'SWSH9.Druddigon_113'
GABITE, TINGLU, MAKUHITA = 'BW6.Gabite_89', 'SV06.TingLu_110', 'ME1.Makuhita_72'
CAPE, TM = 'SV4.LuxuriousCape_166', 'SV4.TechnicalMachineTurboEnergize_179'
DDE, RAINBOW = 'XY6.DoubleDragonEnergy_97', 'SM7.RainbowEnergy_151'
BLEND = 'BW6.BlendEnergyWaterLightningFightingMetal_118'


class Deck5Attachments(unittest.IsolatedAsyncioTestCase):
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

    # --- Luxurious Cape ------------------------------------------------------
    async def _cape_ko(self, caped):
        t = self.table()
        mine = t.put(DRATINI, P1, 'active')
        mine.set_attribute(AttrID.WEAKNESS_TYPES, [])
        t.put(self.filler, P1, 'bench')
        base = effective_max_hp(t.board, mine)
        if caped:
            await t.play(t.put(CAPE, P1, 'hand'), targets=[mine.entity_id])
            self.assertEqual(effective_max_hp(t.board, mine), base + 100)
            self.assertEqual(t.hp(mine), base + 100)
            mine.set_attribute(AttrID.HP, 10)
        else:
            mine.set_attribute(AttrID.HP, 10)
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        attacker = t.put(TINGLU, P2, 'active')
        t.energy(attacker, F, 3)
        t.next_turn()
        await t.attack(attacker, 'Hammer In', pid=P2)
        self.assertNotIn(mine, t.board.pokemon_in_play(P1))
        return t.board.prizes_taken(P2)

    async def test_luxurious_cape_hp_and_extra_prize(self):
        self.assertEqual(await self._cape_ko(True), 2)

    async def test_no_cape_one_prize(self):
        self.assertEqual(await self._cape_ko(False), 1)

    # --- Technical Machine: Turbo Energize ------------------------------------
    async def test_turbo_energize_attaches_two_basic_to_bench(self):
        t = self.table()
        active = t.put(DRATINI, P1, 'active')
        b1 = t.put(DRAGONAIR, P1, 'bench')
        b2 = t.put(DRUDDIGON, P1, 'bench')
        t.energy(active, W)
        tm = t.put(TM, P1, 'hand')
        await t.play(tm, targets=[active.entity_id])
        t.deck(P1, [t.basic_energy(R), DDE, t.basic_energy(L)])
        seen = {}
        t.picks = lambda cards, count, prompt, display: (seen.setdefault('n', (len(cards), count)), cards[:count])[1]
        order = iter([b1, b2, b1, b2])
        t.pokemon = lambda c, p: (lambda x: x if x in c else c[0])(next(order))
        self.assertIsNotNone(t.attack_offer(active, 'Turbo Energize'))
        await t.attack(active, 'Turbo Energize')
        self.assertEqual(seen['n'], (2, 2))                     # DDE is not offered
        attached = len(t.board.attached_energies(b1)) + len(t.board.attached_energies(b2))
        self.assertEqual(attached, 2)
        self.assertEqual(len(t.board.attached_energies(active)), 1)

    async def test_turbo_energize_discarded_end_of_turn(self):
        t = self.table()
        active = t.put(DRATINI, P1, 'active')
        tm = t.put(TM, P1, 'hand')
        await t.play(tm, targets=[active.entity_id])
        self.assertIn(tm, active.children)
        await t._run(lambda: t.session._fire_end_of_turn_triggers(P1))
        self.assertIn(tm, t.zone(P1, 'discard'))

    async def test_turbo_energize_needs_energy(self):
        t = self.table()
        active = t.put(DRATINI, P1, 'active')
        await t.play(t.put(TM, P1, 'hand'), targets=[active.entity_id])
        self.assertIsNone(t.attack_offer(active, 'Turbo Energize'))

    # --- Double Dragon Energy ---------------------------------------------------
    async def test_dde_dragon_only_two_of_any_type(self):
        t = self.table()
        gabite = t.put(GABITE, P1, 'active')            # Dragonslice [W][F]
        dde = t.put(DDE, P1, 'hand')
        ting = t.put(TINGLU, P1, 'bench')
        targets = t.targets(dde, 'DefaultEnergyPlayAbility')
        self.assertIn(gabite.entity_id, targets)
        self.assertNotIn(ting.entity_id, targets)
        await t.play(dde, targets=[gabite.entity_id])
        self.assertIsNotNone(t.attack_offer(gabite, 'Dragonslice'))

    async def test_dde_only_two(self):
        t = self.table()
        drudd = t.put(DRUDDIGON, P1, 'active')          # Dragon Claw [R][W][C]
        t.attach(DDE, drudd)
        self.assertIsNotNone(t.attack_offer(drudd, 'Revenge'))     # [R][W]
        self.assertIsNone(t.attack_offer(drudd, 'Dragon Claw'))

    # --- Rainbow Energy ------------------------------------------------------------
    async def test_rainbow_energy_any_type_one_counter_from_hand(self):
        t = self.table()
        gabite = t.put(GABITE, P1, 'active')
        t.energy(gabite, W)
        rainbow = t.put(RAINBOW, P1, 'hand')
        await t.play(rainbow, targets=[gabite.entity_id])
        self.assertEqual(t.damage(gabite), 10)
        self.assertIsNotNone(t.attack_offer(gabite, 'Dragonslice'))   # pays [F]

    async def test_rainbow_energy_one_at_a_time_no_counter_if_not_from_hand(self):
        t = self.table()
        gabite = t.put(GABITE, P1, 'active')
        t.attach(RAINBOW, gabite)
        self.assertEqual(t.damage(gabite), 0)
        self.assertIsNone(t.attack_offer(gabite, 'Dragonslice'))      # [W][F] needs 2

    # --- Blend Energy WLFM ----------------------------------------------------------
    async def test_blend_wlfm_pays_one_of_its_types(self):
        t = self.table()
        gabite = t.put(GABITE, P1, 'active')            # [W][F]
        t.attach(BLEND, gabite)
        t.energy(gabite, W)
        self.assertIsNotNone(t.attack_offer(gabite, 'Dragonslice'))
        t = self.table()
        gabite = t.put(GABITE, P1, 'active')
        t.attach(BLEND, gabite)
        self.assertIsNone(t.attack_offer(gabite, 'Dragonslice'))      # one at a time

    async def test_blend_wlfm_not_fire(self):
        t = self.table()
        drudd = t.put(DRUDDIGON, P1, 'active')          # Revenge [R][W]
        t.attach(BLEND, drudd)
        t.energy(drudd, W)
        self.assertIsNone(t.attack_offer(drudd, 'Revenge'))
        t.energy(drudd, R)
        self.assertIsNotNone(t.attack_offer(drudd, 'Revenge'))


if __name__ == "__main__":
    unittest.main()
