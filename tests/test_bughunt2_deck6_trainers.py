"""Bug hunt round 2, deck 6 (Metal): Plumeria, Lillie's Poké Doll, Metal Goggles,
Crystal Cave, Shield Energy."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

M, W, D = PokemonTypes.METAL, PokemonTypes.WATER, PokemonTypes.DARKNESS
DIALGA, DURANT = 'CEL25.Dialga_20', 'XY2.Durant_61'
PALAFIN = 'SV05.Palafin_49'          # Vanguard Punch: 130 for [W]
SWIRLIX = 'SV06.Swirlix_89'          # Sneaky Placement: put 2 damage counters on 1 of your opponent's Pokémon
PLUMERIA, DOLL = 'SM3.Plumeria_120', 'SM12.LilliesPokDoll_197'
GOGGLES, CAVE, SHIELD = 'SM9.MetalGoggles_148', 'SWSH7.CrystalCave_144', 'XY5.ShieldEnergy_143'


class Deck6Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def clean(self, pokemon, hp=None):
        pokemon.set_attribute(AttrID.WEAKNESS_TYPES, [])
        pokemon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp:
            pokemon.set_attribute(AttrID.HP, hp)
        return pokemon

    def opp_attacker(self, t, spec=PALAFIN, energy=W):
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        attacker = t.put(spec, P2, 'active')
        t.energy(attacker, energy, 1)
        return attacker

    # --- Plumeria ----------------------------------------------------------
    async def test_plumeria_discards_two_then_one_energy(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        bench = t.put(self.filler, P2, 'bench')
        e1 = t.energy(bench, W)
        t.put(self.item, P1, 'hand'); t.put(self.item, P1, 'hand'); t.put(self.item, P1, 'hand')
        card = t.put(PLUMERIA, P1, 'hand')
        t.pokemon = lambda c, p: bench if bench in c else c[0]
        await t.play(card)
        self.assertEqual(len(t.zone(P1, 'hand')), 1)
        self.assertEqual(len(t.zone(P1, 'discard')), 3)      # 2 + Plumeria
        self.assertIn(e1, t.zone(P2, 'discard'))

    async def test_plumeria_needs_two_other_cards(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.energy(self.opp, W)
        t.put(self.item, P1, 'hand')
        card = t.put(PLUMERIA, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Lillie's Poké Doll ---------------------------------------------
    async def test_poke_doll_bench_play_and_cant_retreat(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        doll = t.put(DOLL, P1, 'hand')
        await t.play(doll)
        self.assertIn(doll, t.zone(P1, 'bench'))
        self.assertEqual(t.hp(doll), 30)
        # as the Active, with Energy and a Benched Pokémon, it still can't retreat
        t2 = self.table()
        doll2 = t2.put(DOLL, P1, 'active')
        t2.put(self.filler, P1, 'bench')
        t2.energy(doll2, W, 2)
        self.assertFalse(t2.can(doll2, 'BaseRetreat'))

    async def test_poke_doll_ko_gives_no_prize(self):
        t = self.table()
        attacker = self.opp_attacker(t)
        doll = t.put(DOLL, P1, 'active')
        t.put(self.filler, P1, 'bench')
        t.next_turn()
        await t.attack(attacker, 'Vanguard Punch', pid=P2)
        self.assertNotIn(doll, t.board.pokemon_in_play(P1))
        self.assertEqual(t.board.prizes_taken(P2), 0)

    async def test_poke_doll_put_away_only_when_active(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        doll = t.put(DOLL, P1, 'bench')
        self.assertIsNone(t.ability_offer(doll, "Put Lillie's Poké Doll Away"))

    # --- Metal Goggles ---------------------------------------------------
    async def test_metal_goggles_30_less_for_metal(self):
        for spec, taken in ((DIALGA, 100), (None, 130)):
            t = self.table()
            attacker = self.opp_attacker(t)
            target = self.clean(t.put(spec or self.filler, P1, 'active'), hp=300)
            await t.play(t.put(GOGGLES, P1, 'hand'), targets=[target.entity_id])
            t.next_turn()
            await t.attack(attacker, 'Vanguard Punch', pid=P2)
            with self.subTest(card=spec):
                self.assertEqual(300 - t.hp(target), taken)

    async def test_metal_goggles_blocks_counters(self):
        t = self.table()
        attacker = self.opp_attacker(t, SWIRLIX, PokemonTypes.PSYCHIC)
        t.put(self.filler, P1, 'active')
        dialga = t.put(DIALGA, P1, 'bench')
        await t.play(t.put(GOGGLES, P1, 'hand'), targets=[dialga.entity_id])
        t.pokemon = lambda c, p: dialga if dialga in c else c[0]
        t.picks = lambda cards, count, prompt, display: [dialga] if dialga in cards else cards[:count]
        t.next_turn()
        before = t.hp(dialga)
        await t.attack(attacker, 'Sneaky Placement', pid=P2)
        self.assertEqual(before - t.hp(dialga), 0)

    # --- Crystal Cave ------------------------------------------------------
    def stadium_action(self, t, stadium, pid=P1):
        return next(iter(t.offers(stadium, None, pid)), None)

    async def test_crystal_cave_heals_each_metal_only(self):
        t = self.table()
        dialga = t.put(DIALGA, P1, 'active', hp=130 - 50)
        durant = t.put(DURANT, P1, 'bench', hp=70 - 10)
        snorlax = t.put(self.filler, P1, 'bench')
        snorlax.set_attribute(AttrID.HP, t.hp(snorlax) - 50)
        their = t.put(DIALGA, P2, 'bench', hp=130 - 50)
        cave = t.stadium(CAVE, P2)
        entry = self.stadium_action(t, cave)
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertEqual(t.damage(dialga), 20)
        self.assertEqual(t.damage(durant), 0)
        self.assertEqual(t.damage(snorlax), 50)
        self.assertEqual(t.damage(their), 50)
        self.assertIsNone(self.stadium_action(t, cave))

    async def test_crystal_cave_not_offered_without_damaged_metal(self):
        t = self.table()
        t.put(DIALGA, P1, 'active')
        snorlax = t.put(self.filler, P1, 'bench')
        snorlax.set_attribute(AttrID.HP, t.hp(snorlax) - 50)
        cave = t.stadium(CAVE, P1)
        self.assertIsNone(self.stadium_action(t, cave))

    # --- Shield Energy ------------------------------------------------------
    async def test_shield_energy_metal_only_attach(self):
        t = self.table()
        snorlax = t.put(self.filler, P1, 'active')
        dialga = t.put(DIALGA, P1, 'bench')
        card = t.put(SHIELD, P1, 'hand')
        targets = t.targets(card, 'DefaultEnergyPlayAbility') or set().union(
            *[t.targets(card, e['selectableAction']['description']) for e in t.offers(card)])
        self.assertIn(dialga.entity_id, targets)
        self.assertNotIn(snorlax.entity_id, targets)

    async def test_shield_energy_provides_metal(self):
        t = self.table()
        self.opp.set_attribute(AttrID.HP, 400)
        dialga = t.put(DIALGA, P1, 'active')
        await t.play(t.put(SHIELD, P1, 'hand'), targets=[dialga.entity_id])
        t.energy(dialga, W, 2)
        await t.attack(dialga, 'Metal Blast')
        self.assertEqual(400 - t.hp(self.opp), 80)

    async def test_shield_energy_10_less(self):
        t = self.table()
        attacker = self.opp_attacker(t)
        dialga = self.clean(t.put(DIALGA, P1, 'active'), hp=300)
        await t.play(t.put(SHIELD, P1, 'hand'), targets=[dialga.entity_id])
        t.next_turn()
        await t.attack(attacker, 'Vanguard Punch', pid=P2)
        self.assertEqual(300 - t.hp(dialga), 120)

    async def test_shield_energy_after_weakness(self):
        # PRC text: "reduced by 10 (after applying Weakness and Resistance)"
        t = self.table()
        attacker = self.opp_attacker(t)
        dialga = self.clean(t.put(DIALGA, P1, 'active'), hp=400)
        dialga.set_attribute(AttrID.WEAKNESS_TYPES, [W.value])
        await t.play(t.put(SHIELD, P1, 'hand'), targets=[dialga.entity_id])
        t.next_turn()
        await t.attack(attacker, 'Vanguard Punch', pid=P2)
        self.assertEqual(400 - t.hp(dialga), 260 - 10)


if __name__ == "__main__":
    unittest.main()
