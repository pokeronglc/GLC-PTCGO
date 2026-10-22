"""Bug hunt round 4, deck 2 (Fire): Cyndaquil ASR 23, Quilava ASR 24,
Typhlosion LOT 42, Vulpix PRC 20, Ninetales DRX 19, Castform Sunny Form CRE 22,
Moltres BRS 21."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, ASLEEP, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

R, W, G = PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS
CYNDAQUIL, QUILAVA, TYPHLOSION = 'SWSH10.Cyndaquil_23', 'SWSH10.Quilava_24', 'SM8.Typhlosion_42'
VULPIX, NINETALES = 'XY5.Vulpix_20', 'BW6.Ninetales_19'
CASTFORM, MOLTRES = 'SWSH6.CastformSunnyForm_22', 'SWSH9.Moltres_21'
ARTAZON = 'SV2.Artazon_171'
HIDING = 'SWSH3.HidingDarknessEnergy_175'


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

    # --- Cyndaquil: Charge Energy -------------------------------------------
    async def test_charge_energy_up_to_two_basic(self):
        t = self.table()
        c = t.put(CYNDAQUIL, P1, 'active')
        t.energy(c, W)
        fire = t.deck(P1, [t.basic_energy(R), t.basic_energy(R), t.basic_energy(W), HIDING])
        seen = {}

        def picks(cards, count, prompt, display):
            seen['cards'], seen['count'] = list(cards), count
            return [c for c in cards if c in fire][:count]
        t.picks = picks
        await t.attack(c, 'Charge Energy')
        self.assertEqual(seen['count'], 2)
        self.assertNotIn(fire[3], seen['cards'])           # Special Energy not eligible
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertTrue(all(h in fire[:3] for h in hand))

    async def test_charge_energy_may_take_none(self):
        t = self.table()
        c = t.put(CYNDAQUIL, P1, 'active')
        t.energy(c, W)
        t.deck(P1, [t.basic_energy(R)])
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(c, 'Charge Energy')
        self.assertEqual(t.zone(P1, 'hand'), [])

    # --- Quilava: vanilla, but evolves from Cyndaquil -----------------------
    async def test_quilava_evolves_from_cyndaquil(self):
        t = self.table()
        c = t.put(CYNDAQUIL, P1, 'bench')
        q = t.put(QUILAVA, P1, 'hand')
        await t.play(q, targets=[c.entity_id])
        self.assertIn(q, t.zone(P1, 'bench'))

    # --- Typhlosion: Blazing Energy / Lost Flame -----------------------------
    async def test_blazing_energy_turns_water_into_fire_this_turn(self):
        t = self.table()
        ty = t.put(TYPHLOSION, P1, 'active')
        t.energy(ty, W, 4)
        self.assertIsNone(t.attack_offer(ty, 'Lost Flame'))
        await t.use(ty, 'Blazing Energy')
        self.assertIsNone(t.ability_offer(ty, 'Blazing Energy'))   # once per turn
        self.assertIsNotNone(t.attack_offer(ty, 'Lost Flame'))
        t.next_turn(); t.next_turn()
        self.assertIsNone(t.attack_offer(ty, 'Lost Flame'))        # expired
        self.assertIsNotNone(t.ability_offer(ty, 'Blazing Energy'))

    async def test_blazing_energy_applies_to_cards_attached_later(self):
        t = self.table()
        ty = t.put(TYPHLOSION, P1, 'bench')
        a = t.put(self.filler, P1, 'active')
        t.energy(a, W, 0) if False else None
        await t.use(ty, 'Blazing Energy')
        t.energy(ty, W, 4)
        t.board.move_card(a.entity_id, t.board.find_player_area(P1, 'bench').entity_id)
        t.board.move_card(ty.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        self.assertIsNotNone(t.attack_offer(ty, 'Lost Flame'))

    async def test_blazing_energy_does_not_change_opponent_energy(self):
        t = self.table()
        ty = t.put(TYPHLOSION, P1, 'active')
        await t.use(ty, 'Blazing Energy')
        t.next_turn()
        theirs = t.put(TYPHLOSION, P2, 'bench')
        t.energy(theirs, W, 4)
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(theirs.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        self.assertIsNone(t.attack_offer(theirs, 'Lost Flame', P2))

    async def test_lost_flame_lost_zones_two_energy(self):
        t = self.table()
        ty = t.put(TYPHLOSION, P1, 'active')
        t.energy(ty, R, 4)
        energies = t.energy(self.opp, W, 2) + [t.attach(HIDING, self.opp)]
        await t.attack(ty, 'Lost Flame')
        self.assertEqual(t.hp(self.opp), 400 - 120)
        lost = t.zone(P2, 'lostZone')
        self.assertEqual(len(lost), 2)
        self.assertEqual(len([e for e in energies if e in self.opp.children]), 1)
        self.assertEqual(len(ty.children), 4)          # own Energy untouched

    async def test_lost_flame_with_one_energy(self):
        t = self.table()
        ty = t.put(TYPHLOSION, P1, 'active')
        t.energy(ty, R, 4)
        e = t.energy(self.opp, W)
        await t.attack(ty, 'Lost Flame')
        self.assertEqual(t.zone(P2, 'lostZone'), [e])

    # --- Vulpix: Roar ---------------------------------------------------------
    async def test_roar_opponent_switches(self):
        t = self.table()
        v = t.put(VULPIX, P1, 'active')
        t.energy(v, W)
        b1 = t.put(self.filler, P2, 'bench')
        b2 = t.put(MOLTRES, P2, 'bench')
        chooser = {}

        def pick(candidates, prompt):
            chooser['c'] = list(candidates)
            return b2
        t.pokemon = pick
        await t.attack(v, 'Roar')
        self.assertIs(t.active(P2), b2)
        self.assertIn(self.opp, t.zone(P2, 'bench'))

    async def test_roar_without_bench_does_nothing(self):
        t = self.table()
        v = t.put(VULPIX, P1, 'active')
        t.energy(v, W)
        await t.attack(v, 'Roar')
        self.assertIs(t.active(P2), self.opp)

    # --- Ninetales: Bright Look / Hexed Flame ---------------------------------
    async def test_bright_look_on_evolve(self):
        t = self.table()
        v = t.put(VULPIX, P1, 'bench')
        target = t.put(MOLTRES, P2, 'bench')
        t.put(self.filler, P2, 'bench')
        t.pokemon = lambda c, p: target if target in c else c[0]
        t.yes = True
        n = t.put(NINETALES, P1, 'hand')
        await t.play(n, targets=[v.entity_id])
        self.assertIn(n, t.zone(P1, 'bench'))
        self.assertIs(t.active(P2), target)

    async def test_bright_look_is_optional(self):
        t = self.table()
        v = t.put(VULPIX, P1, 'bench')
        t.put(MOLTRES, P2, 'bench')
        t.yes = False
        n = t.put(NINETALES, P1, 'hand')
        await t.play(n, targets=[v.entity_id])
        self.assertIs(t.active(P2), self.opp)

    async def test_hexed_flame_scales_with_conditions(self):
        t = self.table()
        n = t.put(NINETALES, P1, 'active')
        t.energy(n, R)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [ASLEEP, POISONED, BURNED])
        await t.attack(n, 'Hexed Flame')
        self.assertEqual(400 - t.hp(self.opp), 20 + 150)

    async def test_hexed_flame_no_conditions(self):
        t = self.table()
        n = t.put(NINETALES, P1, 'active')
        t.energy(n, R)
        await t.attack(n, 'Hexed Flame')
        self.assertEqual(400 - t.hp(self.opp), 20)

    # --- Castform Sunny Form -------------------------------------------------
    async def test_high_pressure_blast_discards_stadium(self):
        t = self.table()
        c = t.put(CASTFORM, P1, 'active')
        t.energy(c, R, 3)
        st = t.stadium(ARTAZON, P2)
        await t.attack(c, 'High-Pressure Blast')
        self.assertIn(st, t.zone(P2, 'discard'))
        self.assertEqual(400 - t.hp(self.opp), 150)

    async def test_high_pressure_blast_without_stadium_does_nothing(self):
        t = self.table()
        c = t.put(CASTFORM, P1, 'active')
        t.energy(c, R, 3)
        await t.attack(c, 'High-Pressure Blast')
        self.assertEqual(t.hp(self.opp), 400)

    async def test_weather_reading_eight_stadiums_free(self):
        t = self.table()
        c = t.put(CASTFORM, P1, 'active')
        for _ in range(7):
            t.put(ARTAZON, P1, 'discard')
        self.assertIsNone(t.attack_offer(c, 'High-Pressure Blast'))
        t.put(ARTAZON, P2, 'discard')                   # opponent's discard doesn't count
        self.assertIsNone(t.attack_offer(c, 'High-Pressure Blast'))
        t.put(ARTAZON, P1, 'discard')
        self.assertIsNotNone(t.attack_offer(c, 'High-Pressure Blast'))
        st = t.stadium(ARTAZON, P1)
        await t.attack(c, 'High-Pressure Blast')
        self.assertEqual(400 - t.hp(self.opp), 150)
        self.assertIn(st, t.zone(P1, 'discard'))

    # --- Moltres: Inferno Wings ---------------------------------------------
    async def test_inferno_wings_undamaged_ignores_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [R.value])
        m = t.put(MOLTRES, P1, 'active')
        t.energy(m, R)
        await t.attack(m, 'Inferno Wings')
        self.assertEqual(400 - t.hp(self.opp), 20)

    async def test_inferno_wings_damaged_ignores_weakness(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [R.value])
        m = t.put(MOLTRES, P1, 'active', hp=110)
        t.energy(m, R)
        await t.attack(m, 'Inferno Wings')
        self.assertEqual(400 - t.hp(self.opp), 90)

    async def test_control_weakness_attribute_doubles_normal_attack(self):
        t = self.table()
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [R.value])
        q = t.put(QUILAVA, P1, 'active')
        t.energy(q, R)
        await t.attack(q, 'Tackle')
        self.assertEqual(400 - t.hp(self.opp), 40)
