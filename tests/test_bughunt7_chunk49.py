"""Bug hunt round 7, chunk 49: Alolan Muk, Galarian Yamask, Galarian Runerigus,
Pupitar, Caterpie/Metapod/Butterfree (JTG), Ledian, Super Potion, Antique Root
Fossil, Fiery Torch, Altar of the Sunne, Rotom Bike, Order Pad, Dangerous
Energy -- each checked against its printed text, including the cases where it
should NOT work."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, PARALYZED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, GRASS, DARK, FIGHT, METAL = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS,
    PokemonTypes.DARKNESS, PokemonTypes.FIGHTING, PokemonTypes.METAL)

GRIMER, MUK = 'SM9.AlolanGrimer_83', 'SM9.AlolanMuk_84'
YAMASK, RUNERIGUS = 'SWSH2.GalarianYamask_101', 'SWSH2.GalarianRunerigus_102'
LARVITAR, PUPITAR = 'PGO.Larvitar_37', 'PGO.Pupitar_38'
CATERPIE, METAPOD, BUTTERFREE = 'SV09.Caterpie_1', 'SV09.Metapod_2', 'SV09.Butterfree_3'
LEDYBA, LEDIAN = 'SV07.Ledyba_2', 'SV07.Ledian_3'
SUPER_POTION = 'SV09.SuperPotion_158'
FIERY_TORCH = 'XY2.FieryTorch_89'
ALTAR = 'SM2.AltaroftheSunne_118'
ROTOM_BIKE = 'SWSH1.RotomBike_181'
ORDER_PAD = 'SM5.OrderPad_131'
DANGEROUS = 'XY7.DangerousEnergy_82'
FIRE_MON = 'ME2.Charcadet_19'          # a plain Fire Basic
SCREAM_TAIL_LIKE = 'SV2.Slakoth_160'   # a plain Colorless Basic


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk49(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None, hp=400):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.big(self.opp, hp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.HP, hp)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear(self, t, pid, zone):
        area = t.board.find_player_area(pid, {'hand': 'hand', 'deck': 'deck'}[zone])
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None, base=400):
        return base - (target or self.opp).get_attribute(AttrID.HP)

    # --- Alolan Muk TEU 84 -----------------------------------------------------
    async def test_muk_adventurous_appetite_discards_items_from_top_six(self):
        t = self.table()
        grimer = self.mine(t, GRIMER)
        self.clear(t, P2, 'deck')
        bottom = t.deck(P2, [self.item, self.item])           # below the top 6
        top = t.deck(P2, [self.filler, self.item, self.filler,
                          self.item, t.basic_energy(WATER), self.item])
        muk = t.put(MUK, P1, 'hand')
        t.yes = True
        await t.play(muk, targets=[grimer.entity_id])
        discard = t.zone(P2, 'discard')
        self.assertEqual(len(discard), 3)
        self.assertTrue(all(c in discard for c in (top[1], top[3], top[5])))
        deck = t.zone(P2, 'deck')
        self.assertEqual(len(deck), 5)
        self.assertTrue(all(c in deck for c in bottom + [top[0], top[2], top[4]]))

    async def test_muk_adventurous_appetite_declined_discards_nothing(self):
        t = self.table()
        grimer = self.mine(t, GRIMER)
        self.clear(t, P2, 'deck')
        t.deck(P2, [self.item] * 6)
        muk = t.put(MUK, P1, 'hand')
        t.yes = False
        await t.play(muk, targets=[grimer.entity_id])
        self.assertEqual(name(t.active(P1)), 'Alolan Muk')
        self.assertEqual(t.zone(P2, 'discard'), [])
        self.assertEqual(len(t.zone(P2, 'deck')), 6)

    async def test_muk_gunk_shot_poisons(self):
        t = self.table()
        muk = self.mine(t, MUK, DARK, 3)
        await t.attack(muk, 'Gunk Shot')
        self.assertEqual(self.dealt(), 80)
        self.assertIn(POISONED, t.conditions(self.opp))

    # --- Galarian Yamask RCL 101 ----------------------------------------------
    async def test_yamask_reckless_charge_recoil(self):
        t = self.table()
        y = self.mine(t, YAMASK, FIGHT, 2)
        await t.attack(y, 'Reckless Charge')
        self.assertEqual(self.dealt(), 50)
        self.assertEqual(t.damage(y), 30)

    # --- Galarian Runerigus RCL 102 -------------------------------------------
    async def _spite(self, t, rune):
        placed = []

        async def place(pid, src, pool, count, prompt=''):
            placed.append(count)
            return {self.opp.entity_id: count} if count else {}
        with patch.object(t.session, 'prompt_damage_counter_placement',
                          create=True, side_effect=place):
            await t.attack(rune, 'Spreading Spite')
        return placed

    async def test_runerigus_spreading_spite_two_per_counter(self):
        t = self.table()
        rune = self.mine(t, RUNERIGUS, FIGHT, 2, hp=70)    # 3 damage counters
        placed = await self._spite(t, rune)
        self.assertEqual(placed, [6])
        self.assertEqual(self.dealt(), 60)

    async def test_runerigus_spreading_spite_undamaged_does_nothing(self):
        t = self.table()
        rune = self.mine(t, RUNERIGUS, FIGHT, 2)
        placed = await self._spite(t, rune)
        self.assertIn(placed, ([], [0]))
        self.assertEqual(self.dealt(), 0)

    async def test_runerigus_mad_hammer_recoil(self):
        t = self.table()
        rune = self.mine(t, RUNERIGUS, FIGHT, 3)
        await t.attack(rune, 'Mad Hammer')
        self.assertEqual(self.dealt(), 120)
        self.assertEqual(t.damage(rune), 30)

    # --- Pupitar PGO 38 -------------------------------------------------------
    async def test_pupitar_crashing_bullet_hits_every_bench(self):
        t = self.table()
        pup = self.mine(t, PUPITAR, FIGHT, 1)
        my_bench = self.mine(t, self.filler, zone='bench', hp=150)
        opp_bench = t.put(self.filler, P2, 'bench')
        opp_bench.set_attribute(AttrID.HP, 150)
        # Fighting Weakness on the Benched one must not apply.
        opp_bench.set_attribute(AttrID.WEAKNESS_TYPES, [FIGHT.value])
        await t.attack(pup, 'Crashing Bullet')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(150 - t.hp(my_bench), 20)
        self.assertEqual(150 - t.hp(opp_bench), 20)
        self.assertEqual(t.damage(pup), 0)

    # --- Metapod JTG 2: Harden ------------------------------------------------
    async def test_metapod_harden_prevents_60_or_less(self):
        t = self.table()
        mp = self.mine(t, METAPOD, GRASS, 1)
        await t.attack(mp, 'Harden')
        t.next_turn()
        # Opponent's Galarian Yamask: Reckless Charge does 50.
        area = t.board.find_player_area(P2, 'activePokemonArea')
        area.remove_child(self.opp)
        y = self.mine(t, YAMASK, FIGHT, 2, pid=P2)
        await t.attack(y, 'Reckless Charge', pid=P2)
        self.assertEqual(t.damage(mp), 0)

    async def test_metapod_harden_does_not_stop_more_than_60(self):
        t = self.table()
        mp = self.mine(t, METAPOD, GRASS, 1)
        await t.attack(mp, 'Harden')
        t.next_turn()
        area = t.board.find_player_area(P2, 'activePokemonArea')
        area.remove_child(self.opp)
        p = self.mine(t, PUPITAR, FIGHT, 3, pid=P2)        # Tackle 70
        await t.attack(p, 'Tackle', pid=P2)
        self.assertEqual(t.damage(mp), 70)

    # --- Butterfree JTG 3: Scale Hurricane (paralysis threshold tested elsewhere)
    async def test_butterfree_scale_hurricane_60_per_heads(self):
        t = self.table()
        bf = self.mine(t, BUTTERFREE, GRASS, 1)
        seq = iter([True, True, True, False])
        t.heads = lambda title: next(seq)
        await t.attack(bf, 'Scale Hurricane')
        self.assertEqual(self.dealt(), 180)
        self.assertIn(PARALYZED, t.conditions(self.opp))

    # --- Ledian SCR 3 ---------------------------------------------------------
    # BUG: Glittering Star Pattern ignores "that has 90 HP or less remaining" (any Benched Pokemon can be gusted)
    async def test_ledian_glittering_star_pattern_gusts_90_or_less(self):
        t = self.table()
        ledyba = self.mine(t, LEDYBA)
        low = t.put(self.filler, P2, 'bench', hp=90)
        high = t.put(self.filler, P2, 'bench', hp=100)
        seen = []

        def pick(candidates, prompt):
            seen.append(list(candidates))
            return low if low in candidates else candidates[0]
        t.pokemon = pick
        t.yes = True
        await t.play(t.put(LEDIAN, P1, 'hand'), targets=[ledyba.entity_id])
        self.assertIs(t.active(P2), low)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        for cands in seen:
            self.assertNotIn(high, cands)

    # BUG: Glittering Star Pattern ignores "that has 90 HP or less remaining" (any Benched Pokemon can be gusted)
    async def test_ledian_glittering_star_pattern_no_target_over_90(self):
        t = self.table()
        ledyba = self.mine(t, LEDYBA)
        t.put(self.filler, P2, 'bench', hp=100)
        t.yes = True
        await t.play(t.put(LEDIAN, P1, 'hand'), targets=[ledyba.entity_id])
        self.assertEqual(name(t.active(P1)), 'Ledian')
        self.assertIs(t.active(P2), self.opp)

    async def test_ledian_swift_ignores_weakness(self):
        t = self.table()
        led = self.mine(t, LEDIAN, GRASS, 2)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [GRASS.value])
        await t.attack(led, 'Swift')
        self.assertEqual(self.dealt(), 70)

    # --- Super Potion JTG 158 -------------------------------------------------
    async def test_super_potion_heals_60_and_discards_energy(self):
        t = self.table()
        me = self.mine(t, self.filler, WATER, 2)
        me.set_attribute(AttrID.HP, t.hp(me) - 80)
        await t.play(t.put(SUPER_POTION, P1, 'hand'))
        self.assertEqual(t.damage(me), 20)
        self.assertEqual(len(t.attached(me)), 1)
        self.assertEqual(len([c for c in t.zone(P1, 'discard')
                              if name(c) != 'Super Potion']), 1)

    async def test_super_potion_not_playable_without_damage(self):
        t = self.table()
        self.mine(t, self.filler, WATER, 1)
        self.opp.set_attribute(AttrID.HP, 100)   # opponent's damage doesn't count
        card = t.put(SUPER_POTION, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Fiery Torch FLF 89 ---------------------------------------------------
    async def test_fiery_torch_discards_fire_draws_two(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        fire = t.put(t.basic_energy(FIRE), P1, 'hand')
        water = t.put(t.basic_energy(WATER), P1, 'hand')
        torch = t.put(FIERY_TORCH, P1, 'hand')
        t.picks = lambda cards, count, prompt, display: [c for c in cards if c is fire][:count]
        await t.play(torch)
        self.assertIn(fire, t.zone(P1, 'discard'))
        hand = t.zone(P1, 'hand')
        self.assertIn(water, hand)
        self.assertEqual(len(hand), 3)

    async def test_fiery_torch_needs_fire_energy_card(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        t.put(t.basic_energy(WATER), P1, 'hand')
        torch = t.put(FIERY_TORCH, P1, 'hand')
        self.assertFalse(t.can(torch, 'UseTrainerCard'))

    # --- Altar of the Sunne GRI 118 -------------------------------------------
    async def _altar_hit(self, target_spec, altar_owner, weak=FIGHT, defender_pid=P2):
        """Galarian Yamask (Fighting, 50) hits a Pokémon Weak to Fighting."""
        t = Table(self)
        target = t.put(target_spec, defender_pid, 'active')
        target.set_attribute(AttrID.HP, 300)
        target.set_attribute(AttrID.WEAKNESS_TYPES, [weak.value])
        target.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if altar_owner is not None:
            t.stadium(ALTAR, altar_owner)
        attacker_pid = P1 if defender_pid == P2 else P2
        y = self.mine(t, YAMASK, FIGHT, 2, pid=attacker_pid)
        if attacker_pid == P2:
            t.next_turn()
        await t.attack(y, 'Reckless Charge', pid=attacker_pid)
        return 300 - t.hp(target)

    async def test_altar_fire_pokemon_have_no_weakness(self):
        self.assertEqual(await self._altar_hit(FIRE_MON, None), 100)
        self.assertEqual(await self._altar_hit(FIRE_MON, P1), 50)
        self.assertEqual(await self._altar_hit(FIRE_MON, P2), 50)
        # your own Fire Pokémon too
        self.assertEqual(await self._altar_hit(FIRE_MON, P1, defender_pid=P1), 50)

    async def test_altar_metal_pokemon_have_no_weakness(self):
        t = Table(self)
        # Any Pokémon whose type is set to Metal
        self.assertEqual(await self._altar_hit_typed(METAL), 50)

    async def _altar_hit_typed(self, kind):
        t = Table(self)
        target = t.put(SCREAM_TAIL_LIKE, P2, 'active')
        target.set_attribute(AttrID.POKEMON_TYPES, [kind.value])
        target.set_attribute(AttrID.HP, 300)
        target.set_attribute(AttrID.WEAKNESS_TYPES, [FIGHT.value])
        target.set_attribute(AttrID.RESISTANCE_TYPES, [])
        t.stadium(ALTAR, P1)
        y = self.mine(t, YAMASK, FIGHT, 2)
        await t.attack(y, 'Reckless Charge')
        return 300 - t.hp(target)

    async def test_altar_other_types_keep_weakness(self):
        self.assertEqual(await self._altar_hit(SCREAM_TAIL_LIKE, P1), 100)

    # --- Rotom Bike SSH 181 ---------------------------------------------------
    async def test_rotom_bike_draws_to_six_and_ends_turn(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        t.put(self.item, P1, 'hand')
        ended = await t.play(t.put(ROTOM_BIKE, P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'hand')), 6)
        self.assertTrue(ended, 'Rotom Bike ends the turn')

    async def test_rotom_bike_with_big_hand_draws_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        for _ in range(7):
            t.put(self.item, P1, 'hand')
        deck = len(t.zone(P1, 'deck'))
        bike = t.put(ROTOM_BIKE, P1, 'hand')
        if t.can(bike, 'UseTrainerCard'):
            await t.play(bike)
            self.assertEqual(len(t.zone(P1, 'deck')), deck)
            self.assertEqual(len(t.zone(P1, 'hand')), 7)

    # --- Order Pad UPR 131 ----------------------------------------------------
    async def test_order_pad_heads_finds_an_item(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        self.clear(t, P1, 'deck')
        t.deck(P1, [self.filler, t.basic_energy(WATER), SUPER_POTION])
        t.heads = True
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), cards[:count])[1]
        await t.play(t.put(ORDER_PAD, P1, 'hand'))
        self.assertEqual(t.names(t.zone(P1, 'hand')), ['Super Potion'])
        self.assertTrue(all(name(c) == 'Super Potion' for c in seen))

    async def test_order_pad_tails_finds_nothing(self):
        t = self.table()
        self.mine(t, self.filler)
        self.clear(t, P1, 'hand')
        self.clear(t, P1, 'deck')
        t.deck(P1, [SUPER_POTION, self.filler])
        t.heads = False
        await t.play(t.put(ORDER_PAD, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [])
        self.assertEqual(len(t.zone(P1, 'deck')), 2)

    # --- Dangerous Energy AOR 82 (Pokémon-EX part untestable: no EX in pool) --
    async def test_dangerous_energy_attaches_to_darkness_only(self):
        t = self.table()
        muk = self.mine(t, MUK)
        other = self.mine(t, self.filler, zone='bench')
        card = t.put(DANGEROUS, P1, 'hand')
        targets = t.targets(card, 'DefaultEnergyPlayAbility')
        if not targets:
            targets = set().union(*(t.targets(card, e['selectableAction']['description'])
                                    for e in t.offers(card)))
        self.assertIn(muk.entity_id, targets)
        self.assertNotIn(other.entity_id, targets)
        await t.play(card, targets=[muk.entity_id])
        self.assertIn(card, t.attached(muk))
        t.energy(muk, DARK, 2)
        self.assertIsNotNone(t.attack_offer(muk, 'Gunk Shot'))


if __name__ == '__main__':
    unittest.main()
