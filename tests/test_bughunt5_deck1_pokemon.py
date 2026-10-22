"""Bug hunt round 5, deck 1 (Lost Zone Psychic): Pokémon."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

PSY = PokemonTypes.PSYCHIC
W = PokemonTypes.WATER
SHUPPET, BANETTE = 'SV1.Shuppet_87', 'SWSH11.Banette_73'
MEWTWO, GENGAR = 'SM10.Mewtwo_75', 'SWSH11.Gengar_66'
SABLEYE, COMFEY = 'SWSH11.Sableye_70', 'SWSH11.Comfey_79'
SKYLA, COLRESS = 'SWSH2.Skyla_166', 'SWSH11.ColresssExperiment_155'
HARD_CHARM, REVIVE = 'XY1.HardCharm_119', 'XY12.Revive_85'


class Deck1Pokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, me=None):
        t = Table(self)
        self.me = t.put(me or self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        self.opp.set_attribute(AttrID.HP, 400)
        return t

    def lost(self, t, pid=P1):
        return t.zone(pid, 'lostZone')

    # --- Shuppet (SVI 87): Enveloping Shadow -----------------------------
    async def test_shuppet_heads_item_lock_next_turn(self):
        t = self.table(SHUPPET)
        t.energy(self.me, PSY)
        before = t.hp(self.opp)
        t.heads = True
        await t.attack(self.me, 'Enveloping Shadow')
        self.assertEqual(before - t.hp(self.opp), 10)
        item = t.put(self.item, P2, 'hand')
        t.next_turn()
        self.assertFalse(t.can(item, 'UseTrainerCard', pid=P2))
        t.next_turn()   # lock is over after their turn
        mine = t.put(self.item, P1, 'hand')
        self.assertTrue(t.can(mine, 'UseTrainerCard', pid=P1))
        t.next_turn()
        self.assertTrue(t.can(item, 'UseTrainerCard', pid=P2))

    async def test_shuppet_tails_no_lock(self):
        t = self.table(SHUPPET)
        t.energy(self.me, PSY)
        t.heads = False
        await t.attack(self.me, 'Enveloping Shadow')
        item = t.put(self.item, P2, 'hand')
        t.next_turn()
        self.assertTrue(t.can(item, 'UseTrainerCard', pid=P2))

    # --- Banette (LOR 73): Puppet Offering -------------------------------
    async def test_banette_supporter_to_hand_and_lost_zone(self):
        t = self.table()
        banette = t.put(BANETTE, P1, 'bench')
        energy = t.energy(banette, PSY)
        t.put(SKYLA, P1, 'discard')
        await t.use(banette, 'Puppet Offering')
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Skyla'])
        self.assertIn(banette, self.lost(t))
        self.assertIn(energy, t.zone(P1, 'discard'))
        self.assertEqual(t.zone(P1, 'bench'), [])

    async def test_banette_needs_supporter_in_discard(self):
        t = self.table()
        banette = t.put(BANETTE, P1, 'bench')
        t.put(self.item, P1, 'discard')
        self.assertIsNone(t.ability_offer(banette, 'Puppet Offering'))

    # --- Mewtwo (UNB 75): Mind Report / Psyshock -------------------------
    async def test_mewtwo_mind_report_on_bench_from_hand(self):
        t = self.table()
        t.put(SKYLA, P1, 'discard')
        mewtwo = t.put(MEWTWO, P1, 'hand')
        await t.play(mewtwo)
        self.assertIn(mewtwo, t.zone(P1, 'bench'))
        top = t.zone(P1, 'deck')[-1]
        self.assertEqual(def_for(top.archetype_id).display_name, 'Skyla')
        self.assertEqual(t.zone(P1, 'discard'), [])

    async def test_mewtwo_mind_report_may_decline(self):
        t = self.table()
        skyla = t.put(SKYLA, P1, 'discard')
        t.yes = False
        t.picks = lambda cards, count, prompt, display: []
        await t.play(t.put(MEWTWO, P1, 'hand'))
        self.assertIn(skyla, t.zone(P1, 'discard'))

    async def test_mewtwo_mind_report_not_from_revive(self):
        t = self.table()
        t.put(SKYLA, P1, 'discard')
        mewtwo = t.put(MEWTWO, P1, 'discard')
        await t.play(t.put(REVIVE, P1, 'hand'))
        self.assertIn(mewtwo, t.zone(P1, 'bench'))
        self.assertEqual(t.names([c for c in t.zone(P1, 'discard')
                                  if def_for(c.archetype_id).display_name == 'Skyla']), ['Skyla'])

    async def test_mewtwo_psyshock_ignores_defender_effects(self):
        t = self.table(MEWTWO)
        t.energy(self.me, PSY, 3)
        t.attach(HARD_CHARM, self.opp)
        before = t.hp(self.opp)
        await t.attack(self.me, 'Psyshock')
        self.assertEqual(before - t.hp(self.opp), 70)

    async def test_mewtwo_psyshock_still_applies_weakness(self):
        t = self.table(MEWTWO)
        t.energy(self.me, PSY, 3)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [PSY.value])
        before = t.hp(self.opp)
        await t.attack(self.me, 'Psyshock')
        self.assertEqual(before - t.hp(self.opp), 140)

    # --- Gengar (LOR 66): Netherworld Gate / Screaming Circle -------------
    async def test_gengar_netherworld_gate_from_discard(self):
        t = self.table()
        gengar = t.put(GENGAR, P1, 'discard')
        await t.use(gengar, 'Netherworld Gate')
        self.assertIn(gengar, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(gengar), 30)

    async def test_gengar_gate_not_from_hand_or_play_or_full_bench(self):
        t = self.table()
        in_hand = t.put(GENGAR, P1, 'hand')
        self.assertIsNone(t.ability_offer(in_hand, 'Netherworld Gate'))
        benched = t.put(GENGAR, P1, 'bench')
        self.assertIsNone(t.ability_offer(benched, 'Netherworld Gate'))
        for _ in range(4):
            t.put(self.filler, P1, 'bench')
        in_discard = t.put(GENGAR, P1, 'discard')
        self.assertIsNone(t.ability_offer(in_discard, 'Netherworld Gate'))

    async def test_gengar_screaming_circle(self):
        t = self.table(GENGAR)
        t.energy(self.me, PSY)
        for _ in range(3):
            t.put(self.filler, P2, 'bench')
        before = t.hp(self.opp)
        await t.attack(self.me, 'Screaming Circle')
        self.assertEqual(before - t.hp(self.opp), 60)

    # --- Sableye (LOR 70): Lost Mine --------------------------------------
    def _fill_lost(self, t, n):
        for _ in range(n):
            t.put(self.item, P1, 'lostZone')

    async def test_sableye_lost_mine_needs_10(self):
        t = self.table(SABLEYE)
        t.energy(self.me, PSY)
        self._fill_lost(t, 9)
        self.assertIsNone(t.attack_offer(self.me, 'Lost Mine'))
        self._fill_lost(t, 1)
        self.assertIsNotNone(t.attack_offer(self.me, 'Lost Mine'))

    async def test_sableye_lost_mine_places_12_counters(self):
        t = self.table(SABLEYE)
        t.energy(self.me, PSY)
        self._fill_lost(t, 10)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 400)
        seen = {}

        async def placement(pid, source_id, pool, count, prompt=''):
            seen['pool'] = {p.entity_id for p in pool}
            seen['count'] = count
            return {self.opp.entity_id: 7, bench.entity_id: 5}

        a, b = t.hp(self.opp), t.hp(bench)
        with patch.object(t.session, 'prompt_damage_counter_placement', placement):
            await t.attack(self.me, 'Lost Mine')
        self.assertEqual(seen['count'], 12)
        self.assertEqual(seen['pool'], {self.opp.entity_id, bench.entity_id})
        self.assertEqual(a - t.hp(self.opp), 70)
        self.assertEqual(b - t.hp(bench), 50)

    # --- Comfey (LOR 79): Flower Selecting --------------------------------
    async def test_comfey_flower_selecting_active(self):
        t = self.table(COMFEY)
        skyla, colress = t.deck(P1, [SKYLA, COLRESS])
        t.picks = lambda cards, count, prompt, display: [colress]
        await t.use(self.me, 'Flower Selecting')
        self.assertEqual(t.zone(P1, 'hand'), [colress])
        self.assertEqual(self.lost(t), [skyla])
        self.assertIsNone(t.ability_offer(self.me, 'Flower Selecting'))   # once per turn

    async def test_comfey_flower_selecting_not_on_bench(self):
        t = self.table()
        comfey = t.put(COMFEY, P1, 'bench')
        self.assertIsNone(t.ability_offer(comfey, 'Flower Selecting'))


if __name__ == '__main__':
    unittest.main()
