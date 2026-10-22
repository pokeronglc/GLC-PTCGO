"""Bug hunt round 7, chunk 30: Cascoon, Cutiefly, Sandygast, Palossand, Heatran,
Po Town, Zorua, Zoroark, Cetitan, Latios, Ultra Necrozma, Swirlix, Punk Helmet,
Koraidon, Baltoy -- each checked against its printed text, including the cases
where it should NOT work."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, BURNED, ASLEEP, CONFUSED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, FIGHT, GRASS, DARK, FAIRY, PSY, METAL = (
    PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.FIGHTING, PokemonTypes.GRASS,
    PokemonTypes.DARKNESS, PokemonTypes.FAIRY, PokemonTypes.PSYCHIC, PokemonTypes.METAL)

CASCOON = 'XY6.Cascoon_6'
CUTIEFLY = 'SM8.Cutiefly_145'
SANDYGAST, PALOSSAND = 'SWSH12.Sandygast_99', 'SWSH12.Palossand_100'
HEATRAN = 'ME5.Heatran_7'
PO_TOWN = 'SM3.PoTown_121'
ZORUA, ZOROARK = 'RSV10PT5.Zorua_61', 'RSV10PT5.Zoroark_62'
CETITAN = 'SVP.Cetitan_63'
LATIOS = 'ME1.Latios_101'
NECROZMA = 'SM12.UltraNecrozma_164'
SWIRLIX = 'XY4.Swirlix_68'
PUNK = 'ME2.PunkHelmet_92'
KORAIDON = 'SV05.Koraidon_119'
BALTOY = 'SWSH12.Baltoy_93'
GREAT_TUSK = 'SV05.GreatTusk_96'      # Ancient Basic
SCREAM_TAIL = 'SV05.ScreamTail_77'    # Ancient Basic


def name(card):
    return def_for(card.archetype_id).display_name


class Chunk30(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, opp_spec=None):
        t = Table(self)
        self.opp = t.put(opp_spec or self.filler, P2, 'active')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        return t

    def mine(self, t, spec, kind=None, count=0, zone='active', hp=None, pid=P1):
        p = t.put(spec, pid, zone)
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        if hp is not None:
            p.set_attribute(AttrID.HP, hp)
        if count:
            t.energy(p, kind, count)
        return p

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None):
        return 400 - (target or self.opp).get_attribute(AttrID.HP)

    async def opp_hits(self, t):
        """P2's Snorlax uses Heavy Impact (80) on P1's Active."""
        t.energy(self.opp, WATER, 3)
        t.next_turn()
        await t.attack(self.opp, 'Heavy Impact', pid=P2)

    # --- Cascoon ROS 6 ---------------------------------------------------------
    async def test_cascoon_poison_sting_poisons(self):
        t = self.table()
        me = self.mine(t, CASCOON, GRASS, 1)
        await t.attack(me, 'Poison Sting')
        self.assertIn(POISONED, t.conditions(self.opp))
        self.assertEqual(self.dealt(), 0)

    async def test_cascoon_iron_defense_heads_prevents_damage(self):
        t = self.table()
        me = self.mine(t, CASCOON, WATER, 2, hp=80)
        t.heads = True
        await t.attack(me, 'Iron Defense')
        await self.opp_hits(t)
        self.assertEqual(t.damage(me), 0)
        self.assertIn(me, t.zone(P1, 'active'))

    async def test_cascoon_iron_defense_tails_no_protection(self):
        t = self.table()
        me = self.mine(t, CASCOON, WATER, 2, hp=200)
        t.heads = False
        await t.attack(me, 'Iron Defense')
        await self.opp_hits(t)
        self.assertEqual(200 - t.hp(me), 80)

    # --- Cutiefly LOT 145 ------------------------------------------------------
    async def test_cutiefly_sweet_scent_heals_30_from_benched(self):
        t = self.table()
        me = self.mine(t, CUTIEFLY, WATER, 1)
        hurt = self.mine(t, self.filler, zone='bench')
        full = t.hp(hurt)
        hurt.set_attribute(AttrID.HP, full - 50)
        t.pokemon = lambda cands, prompt: hurt
        await t.attack(me, 'Sweet Scent')
        self.assertEqual(full - t.hp(hurt), 20)
        self.assertEqual(self.dealt(), 0)

    async def test_cutiefly_sweet_scent_does_not_heal_opponent(self):
        t = self.table()
        me = self.mine(t, CUTIEFLY, WATER, 1)
        self.opp.set_attribute(AttrID.HP, 350)
        seen = []
        t.pokemon = lambda cands, prompt: (seen.extend(cands), cands[0])[1]
        await t.attack(me, 'Sweet Scent')
        self.assertTrue(all(c.owning_player_id == P1 for c in seen))
        self.assertEqual(self.opp.get_attribute(AttrID.HP), 350)

    # --- Sandygast SIT 99 ------------------------------------------------------
    async def test_sandygast_corner_blocks_retreat_next_turn_only(self):
        t = self.table()
        me = self.mine(t, SANDYGAST, FIGHT, 1)
        t.energy(self.opp, WATER, 4)
        self.mine(t, self.filler, zone='bench', pid=P2)
        await t.attack(me, 'Corner')
        self.assertEqual(self.dealt(), 10)
        t.next_turn()
        blocked = {e['selectableAction']['description'] for e in t.offers(self.opp, None, P2)}
        self.assertFalse(any('Retreat' in d for d in blocked), blocked)
        t.next_turn()
        t.next_turn()
        retreat_names = {e['selectableAction']['description'] for e in t.offers(self.opp, None, P2)}
        self.assertTrue(any('Retreat' in d for d in retreat_names), retreat_names)

    async def test_sandygast_corner_retreat_offered_without_corner(self):
        # control: the same board does offer a retreat without Corner
        t = self.table()
        self.mine(t, SANDYGAST, FIGHT, 1)
        t.energy(self.opp, WATER, 4)
        self.mine(t, self.filler, zone='bench', pid=P2)
        t.next_turn()
        descs = {e['selectableAction']['description'] for e in t.offers(self.opp, None, P2)}
        self.assertTrue(any('Retreat' in d for d in descs), descs)

    # --- Palossand SIT 100 -----------------------------------------------------
    async def test_palossand_sandpot_trap_30_each_no_bench_weakness(self):
        t = self.table()
        me = self.mine(t, PALOSSAND, FIGHT, 1)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [FIGHT.value])
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 400)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [FIGHT.value])
        mine_bench = self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Sandpot Trap')
        self.assertEqual(self.dealt(), 60)      # Active: Weakness x2
        self.assertEqual(self.dealt(bench), 30)  # Bench: no Weakness
        self.assertEqual(t.damage(mine_bench), 0)

    # --- Heatran PBL 7 ---------------------------------------------------------
    async def test_heatran_singe_burns(self):
        t = self.table()
        me = self.mine(t, HEATRAN, FIRE, 1)
        await t.attack(me, 'Singe')
        self.assertIn(BURNED, t.conditions(self.opp))

    async def test_heatran_lava_wall_blocks_burned_attacker(self):
        t = self.table()
        me = self.mine(t, HEATRAN, FIRE, 3, hp=140)
        await t.attack(me, 'Lava Wall')
        self.assertEqual(self.dealt(), 120)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        await self.opp_hits(t)
        self.assertEqual(t.damage(me), 0)

    async def test_heatran_lava_wall_not_vs_unburned_attacker(self):
        t = self.table()
        me = self.mine(t, HEATRAN, FIRE, 3, hp=140)
        await t.attack(me, 'Lava Wall')
        await self.opp_hits(t)
        self.assertEqual(t.damage(me), 80)

    # --- Po Town BUS 121 -------------------------------------------------------
    async def test_po_town_evolve_from_hand_puts_3_counters_both_players(self):
        t = self.table()
        self.mine(t, self.filler)
        t.stadium(PO_TOWN, P1)
        gast = self.mine(t, SANDYGAST, zone='bench')
        evo = t.put(PALOSSAND, P1, 'hand')
        await t.play(evo, targets=[gast.entity_id])
        self.assertIn(evo, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(evo), 30)
        # opponent's evolutions too
        t.next_turn()
        gast2 = self.mine(t, SANDYGAST, zone='bench', pid=P2)
        evo2 = t.put(PALOSSAND, P2, 'hand')
        await t.play(evo2, pid=P2, targets=[gast2.entity_id])
        self.assertEqual(t.damage(evo2), 30)

    async def test_po_town_benching_basic_no_counters(self):
        t = self.table()
        self.mine(t, self.filler)
        t.stadium(PO_TOWN, P1)
        gast = t.put(SANDYGAST, P1, 'hand')
        await t.play(gast)
        self.assertIn(gast, t.zone(P1, 'bench'))
        self.assertEqual(t.damage(gast), 0)

    # --- Zorua WHT 61 ----------------------------------------------------------
    async def test_zorua_take_down_damages_itself(self):
        t = self.table()
        me = self.mine(t, ZORUA, DARK, 1)
        await t.attack(me, 'Take Down')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.damage(me), 10)

    # --- Zoroark WHT 62 --------------------------------------------------------
    async def test_zoroark_mind_jack_30_per_opp_bench(self):
        t = self.table()
        me = self.mine(t, ZOROARK, DARK, 1)
        for _ in range(3):
            t.put(self.filler, P2, 'bench')
        self.mine(t, self.filler, zone='bench')       # my bench doesn't count
        await t.attack(me, 'Mind Jack')
        self.assertEqual(self.dealt(), 90)

    async def test_zoroark_mind_jack_no_opp_bench_zero(self):
        t = self.table()
        me = self.mine(t, ZOROARK, DARK, 1)
        self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Mind Jack')
        self.assertEqual(self.dealt(), 0)

    async def test_zoroark_foul_play_copies_opponent_attack(self):
        t = self.table(HEATRAN)
        me = self.mine(t, ZOROARK, WATER, 3)
        await t.attack(me, 'Foul Play')
        # pick whichever attack is offered first; Singe should burn, Lava Wall does 120
        self.assertTrue(BURNED in t.conditions(self.opp) or self.dealt() == 120,
                        (t.conditions(self.opp), self.dealt(), t.prompts))

    async def test_zoroark_foul_play_copies_singe(self):
        t = self.table(HEATRAN)
        me = self.mine(t, ZOROARK, WATER, 3)
        t.picks = lambda cards, count, prompt, display: [
            c for c in cards if 'Singe' in str(getattr(c, 'title', c))][:count] or list(cards)[:count]
        await t.attack(me, 'Foul Play')
        self.assertIn(BURNED, t.conditions(self.opp))

    # --- Cetitan SVP 63 --------------------------------------------------------
    async def test_cetitan_avalanche_hits_bench_10_without_weakness(self):
        t = self.table()
        me = self.mine(t, CETITAN, WATER, 1)
        bench = t.put(self.filler, P2, 'bench')
        bench.set_attribute(AttrID.HP, 400)
        bench.set_attribute(AttrID.WEAKNESS_TYPES, [WATER.value])
        mine_bench = self.mine(t, self.filler, zone='bench')
        await t.attack(me, 'Avalanche')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(self.dealt(bench), 10)
        self.assertEqual(t.damage(mine_bench), 0)

    async def test_cetitan_rolling_slider_100_per_heads(self):
        t = self.table()
        me = self.mine(t, CETITAN, WATER, 3)
        flips = iter([True, False, True])
        t.heads = lambda title: next(flips)
        await t.attack(me, 'Rolling Slider')
        self.assertEqual(self.dealt(), 200)

    async def test_cetitan_rolling_slider_all_tails_zero(self):
        t = self.table()
        me = self.mine(t, CETITAN, WATER, 3)
        t.heads = False
        await t.attack(me, 'Rolling Slider')
        self.assertEqual(self.dealt(), 0)

    # --- Latios MEG 101 --------------------------------------------------------
    async def test_latios_lustrous_assist_not_offered_without_mega_latias(self):
        # Mega Latias ex is not in the GLC card pool, so the Ability can never trigger.
        t = self.table()
        self.mine(t, self.filler)
        lat = self.mine(t, LATIOS, WATER, 2, zone='bench')
        self.assertIsNone(t.ability_offer(lat, 'Lustrous Assist'))
        self.assertIsNone(t.ability_offer(lat, 'Lustrous Assist', pid=P1))

    async def test_latios_lustrous_assist_not_on_ordinary_switch(self):
        # Moving Latios itself (not a Mega Latias ex) to the Active Spot: no Ability, no Energy moved.
        t = self.table()
        act = self.mine(t, self.filler)
        lat = self.mine(t, LATIOS, zone='bench')
        e = t.energy(act, WATER, 1)
        t.energy(lat, WATER, 1)
        self.assertIsNone(t.ability_offer(lat, 'Lustrous Assist'))
        self.assertIn(e, act.children)

    # --- Ultra Necrozma CEC 164 ------------------------------------------------
    # BUG: Ultra Burst "can't attack unless your opponent has 2 or fewer Prize cards" is not enforced
    async def test_ultra_necrozma_cannot_attack_with_3_opp_prizes(self):
        t = self.table()
        me = self.mine(t, NECROZMA, PSY, 1)
        t.energy(me, METAL, 1)
        t.set_prizes(P2, 3)
        self.assertIsNone(t.attack_offer(me, 'Luster of Downfall'))

    # BUG: Ultra Burst prize gate not enforced (attack offered with opponent at 6 Prizes)
    async def test_ultra_necrozma_my_prize_count_irrelevant(self):
        t = self.table()
        me = self.mine(t, NECROZMA, PSY, 1)
        t.energy(me, METAL, 1)
        t.set_prizes(P1, 1)
        t.set_prizes(P2, 6)
        self.assertIsNone(t.attack_offer(me, 'Luster of Downfall'))

    async def test_ultra_necrozma_attacks_at_2_prizes_and_discards_energy(self):
        t = self.table()
        me = self.mine(t, NECROZMA, PSY, 1)
        t.energy(me, METAL, 1)
        e = t.energy(self.opp, WATER, 1)
        t.set_prizes(P2, 2)
        self.assertIsNotNone(t.attack_offer(me, 'Luster of Downfall'))
        await t.attack(me, 'Luster of Downfall')
        self.assertEqual(self.dealt(), 170)
        self.assertIn(e, t.zone(P2, 'discard'))

    # --- Swirlix PHF 68 --------------------------------------------------------
    async def test_swirlix_lick_away_removes_conditions(self):
        t = self.table()
        me = self.mine(t, SWIRLIX, FAIRY, 1)
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED, BURNED])   # no Confusion: its flip is not scripted
        t.heads = True       # in case the Confusion flip uses flip_coins
        await t.attack(me, 'Lick Away')
        self.assertEqual(t.conditions(me), set())

    async def test_swirlix_lick_away_does_not_cure_opponent(self):
        t = self.table()
        me = self.mine(t, SWIRLIX, FAIRY, 1)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.attack(me, 'Lick Away')
        self.assertIn(POISONED, t.conditions(self.opp))
        self.assertEqual(self.dealt(), 0)

    # --- Punk Helmet PFL 92 ----------------------------------------------------
    async def test_punk_helmet_active_darkness_hit_puts_4_counters(self):
        t = self.table()
        me = self.mine(t, ZOROARK, hp=120)
        await t.play(t.put(PUNK, P1, 'hand'), targets=[me.entity_id])
        await self.opp_hits(t)
        self.assertEqual(t.damage(me), 80)
        self.assertEqual(self.dealt(), 40)

    async def test_punk_helmet_even_if_knocked_out(self):
        t = self.table()
        me = self.mine(t, ZOROARK, hp=50)
        self.mine(t, self.filler, zone='bench')
        await t.play(t.put(PUNK, P1, 'hand'), targets=[me.entity_id])
        await self.opp_hits(t)
        self.assertIn(me, t.zone(P1, 'discard'))
        self.assertEqual(self.dealt(), 40)

    async def test_punk_helmet_non_darkness_does_nothing(self):
        t = self.table()
        me = self.mine(t, self.filler, hp=200)
        await t.play(t.put(PUNK, P1, 'hand'), targets=[me.entity_id])
        await self.opp_hits(t)
        self.assertEqual(self.dealt(), 0)

    async def test_punk_helmet_benched_darkness_does_nothing(self):
        t = self.table()
        self.mine(t, self.filler, hp=300)
        bench = self.mine(t, ZOROARK, zone='bench')
        await t.play(t.put(PUNK, P1, 'hand'), targets=[bench.entity_id])
        # Cetitan-style bench damage from P2: Avalanche hits the bench
        t.next_turn()
        ceti = t.put(CETITAN, P2, 'bench')
        bench_area = t.board.find_player_area(P2, 'bench')
        t.board.move_card(self.opp.entity_id, bench_area.entity_id)
        t.board.move_card(ceti.entity_id,
                          t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        ceti.set_attribute(AttrID.HP, 170)
        t.energy(ceti, WATER, 1)
        await t.attack(ceti, 'Avalanche', pid=P2)
        self.assertEqual(t.damage(bench), 10)
        self.assertEqual(t.damage(ceti), 0)

    # --- Koraidon TEF 119 ------------------------------------------------------
    # BUG: "for each of your Ancient Pokémon in play" counts every Pokémon in play on both sides
    async def test_koraidon_primordial_beatdown_counts_ancients_in_play(self):
        t = self.table()
        me = self.mine(t, KORAIDON, FIGHT, 2)
        self.mine(t, GREAT_TUSK, zone='bench')
        self.mine(t, SCREAM_TAIL, zone='bench')
        self.mine(t, self.filler, zone='bench')       # not Ancient
        t.put(GREAT_TUSK, P1, 'hand')                 # not in play
        t.put(GREAT_TUSK, P2, 'bench')                # opponent's, not "your"
        await t.attack(me, 'Primordial Beatdown')
        self.assertEqual(self.dealt(), 90)

    # BUG: Primordial Beatdown counts both players' Pokémon (60 with Koraidon vs. Snorlax)
    async def test_koraidon_beatdown_alone_is_30_not_60(self):
        # Only Koraidon (Ancient) on my side; opponent's non-Ancient Snorlax must not count.
        t = self.table()
        me = self.mine(t, KORAIDON, FIGHT, 2)
        await t.attack(me, 'Primordial Beatdown')
        self.assertEqual(self.dealt(), 30)

    async def test_koraidon_shred_ignores_iron_defense(self):
        t = Table(self)
        cas = t.put(CASCOON, P2, 'active')
        cas.set_attribute(AttrID.HP, 400)
        cas.set_attribute(AttrID.WEAKNESS_TYPES, [])
        cas.set_attribute(AttrID.RESISTANCE_TYPES, [])
        t.energy(cas, WATER, 2)
        kor = self.mine(t, KORAIDON, FIRE, 1)
        t.energy(kor, FIGHT, 2)
        t.next_turn()
        t.heads = True
        await t.attack(cas, 'Iron Defense', pid=P2)
        t.next_turn()
        await t.attack(kor, 'Shred')
        self.assertEqual(400 - cas.get_attribute(AttrID.HP), 130)

    async def test_koraidon_beatdown_blocked_by_iron_defense(self):
        # control: a normal attack is prevented by Iron Defense
        t = Table(self)
        cas = t.put(CASCOON, P2, 'active')
        cas.set_attribute(AttrID.HP, 400)
        cas.set_attribute(AttrID.WEAKNESS_TYPES, [])
        cas.set_attribute(AttrID.RESISTANCE_TYPES, [])
        t.energy(cas, WATER, 2)
        kor = self.mine(t, KORAIDON, FIGHT, 2)
        t.next_turn()
        t.heads = True
        await t.attack(cas, 'Iron Defense', pid=P2)
        t.next_turn()
        await t.attack(kor, 'Primordial Beatdown')
        self.assertEqual(cas.get_attribute(AttrID.HP), 400)

    # --- Baltoy SIT 93 ---------------------------------------------------------
    async def test_baltoy_find_a_friend_takes_a_pokemon(self):
        t = self.table()
        me = self.mine(t, BALTOY, WATER, 1)
        self.clear_hand(t)
        target = t.deck(P1, [SANDYGAST])[0]
        t.deck(P1, [t.basic_energy(FIRE)])
        await t.attack(me, 'Find a Friend')
        self.assertEqual(t.zone(P1, 'hand'), [target])

    async def test_baltoy_find_a_friend_only_pokemon_offered(self):
        t = self.table()
        me = self.mine(t, BALTOY, WATER, 1)
        self.clear_hand(t)
        t.deck(P1, [t.basic_energy(FIRE)])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), [])[1]
        await t.attack(me, 'Find a Friend')
        self.assertEqual(seen, [])
        self.assertEqual(t.zone(P1, 'hand'), [])


if __name__ == '__main__':
    unittest.main()
