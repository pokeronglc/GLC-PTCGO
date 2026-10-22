"""Bug hunt round 7, chunk 46: Buddy-Buddy Rescue, Morelull, Shiinotic, Tapu
Fini, Monferno, Larvesta, Volcarona, Litleo, Pyroar, Wela Volcano Park, Lucky
Egg, Gulpin, Swalot, Dark City, Smeargle -- each checked against its printed
text, including the cases where it should NOT work."""
import random
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, POISONED, ASLEEP, CONFUSED, BURNED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.tools.effect_smoke import P1, P2

FIRE, WATER, DARK, FAIRY, GRASS = (PokemonTypes.FIRE, PokemonTypes.WATER,
                                   PokemonTypes.DARKNESS, PokemonTypes.FAIRY,
                                   PokemonTypes.GRASS)

RESCUE = 'XY8.BuddyBuddyRescue_135'
MORELULL, SHIINOTIC = 'SM5.Morelull_92', 'SM5.Shiinotic_93'
TAPU_FINI = 'SM8.TapuFini_151'
MONFERNO = 'SM5.Monferno_22'
LARVESTA, VOLCARONA = 'SWSH3.Larvesta_29', 'ZSV10PT5.Volcarona_16'
LITLEO, PYROAR = 'SWSH11.Litleo_28', 'XY4.Pyroar_12'
WELA = 'DM.WelaVolcanoPark_63'
LUCKY_EGG = 'SWSH1.LuckyEgg_167'
GULPIN, SWALOT = 'SV07.Gulpin_91', 'SV07.Swalot_92'
DARK_CITY = 'SM11.DarkCity_193'
SMEARGLE = 'SWSH7.Smeargle_128'


def name(card):
    return def_for(card.archetype_id).display_name


def coins(value):
    real = random.choice

    def choice(seq):
        if list(seq) in ([0, 1], [True, False]):
            return seq[0] if value == 'heads' else seq[1]
        return real(seq)
    return patch.object(random, 'choice', choice)


class Chunk46(unittest.IsolatedAsyncioTestCase):
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

    def clear_hand(self, t, pid=P1):
        area = t.board.find_player_area(pid, 'hand')
        for c in list(area.children):
            area.remove_child(c)

    def dealt(self, target=None, base=400):
        return base - (target or self.opp).get_attribute(AttrID.HP)

    # --- Buddy-Buddy Rescue BKT 135 --------------------------------------------
    async def test_rescue_each_player_takes_a_pokemon_opponent_first(self):
        t = self.table()
        self.mine(t, self.filler)
        mine_poke = t.put(MORELULL, P1, 'discard')
        mine_energy = t.put(t.basic_energy(FIRE), P1, 'discard')
        theirs = t.put(GULPIN, P2, 'discard')
        order = []

        def picks(cards, count, prompt, display):
            owners = {c.owning_player_id for c in cards}
            order.append(owners)
            return cards[:count]
        t.picks = picks
        card = t.put(RESCUE, P1, 'hand')
        await t.play(card)
        self.assertIn(mine_poke, t.zone(P1, 'hand'))
        self.assertIn(mine_energy, t.zone(P1, 'discard'))
        self.assertIn(theirs, t.zone(P2, 'hand'))
        self.assertEqual(order[0], {P2})        # opponent chooses first
        self.assertEqual(order[1], {P1})

    async def test_rescue_only_my_pokemon_still_works(self):
        t = self.table()
        self.mine(t, self.filler)
        mine_poke = t.put(MORELULL, P1, 'discard')
        t.put(t.basic_energy(FIRE), P2, 'discard')
        card = t.put(RESCUE, P1, 'hand')
        self.assertTrue(t.can(card, 'UseTrainerCard'))
        await t.play(card)
        self.assertIn(mine_poke, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P2, 'hand')), 0)

    async def test_rescue_not_playable_with_no_pokemon_in_discards(self):
        t = self.table()
        self.mine(t, self.filler)
        t.put(t.basic_energy(FIRE), P1, 'discard')
        t.put(self.item, P1, 'discard')
        card = t.put(RESCUE, P1, 'hand')
        self.assertFalse(t.can(card, 'UseTrainerCard'))

    # --- Morelull UPR 92: Flickering Spores ------------------------------------
    async def test_morelull_flickering_spores_sleeps_opponent_only(self):
        t = self.table()
        m = self.mine(t, MORELULL, FAIRY, 1)
        await t.attack(m, 'Flickering Spores')
        self.assertEqual(t.conditions(self.opp), {ASLEEP})
        self.assertEqual(t.conditions(m), set())
        self.assertEqual(self.dealt(), 0)

    # --- Shiinotic UPR 93: Illuminate / Flickering Spores ----------------------
    async def test_shiinotic_illuminate_finds_fairy_pokemon(self):
        t = self.table()
        s = self.mine(t, SHIINOTIC)
        fairy, other = t.deck(P1, [TAPU_FINI, GULPIN])
        seen = []
        t.picks = lambda cards, count, prompt, display: (seen.extend(cards), [fairy])[1]
        await t.use(s, 'Illuminate')
        self.assertIn(fairy, t.zone(P1, 'hand'))
        self.assertNotIn(other, seen)
        self.assertIn(other, t.zone(P1, 'deck'))
        # once per turn
        t.deck(P1, [MORELULL])
        self.assertIsNone(t.ability_offer(s, 'Illuminate'))

    async def test_shiinotic_illuminate_never_takes_non_fairy(self):
        t = self.table()
        s = self.mine(t, SHIINOTIC, zone='bench')
        self.mine(t, self.filler)
        other = t.deck(P1, [GULPIN])[0]
        entry = t.ability_offer(s, 'Illuminate')
        if entry is not None:            # searches may fail to find
            await t.do(entry)
        self.assertIn(other, t.zone(P1, 'deck'))
        self.assertEqual([c for c in t.zone(P1, 'hand') if name(c) == 'Gulpin'], [])

    async def test_shiinotic_flickering_spores_30_and_asleep(self):
        t = self.table()
        s = self.mine(t, SHIINOTIC, FAIRY, 2)
        await t.attack(s, 'Flickering Spores')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.conditions(self.opp), {ASLEEP})

    # --- Tapu Fini LOT 151: Dream Away / Wonder Shine --------------------------
    async def test_tapu_fini_dream_away_heads_shuffles_active_and_attachments(self):
        t = self.table()
        fini = self.mine(t, TAPU_FINI, FAIRY, 2)
        energy = t.energy(self.opp, WATER, 1)
        bench = self.mine(t, GULPIN, zone='bench', pid=P2)
        t.heads = True
        await t.attack(fini, 'Dream Away')
        deck = t.zone(P2, 'deck')
        self.assertIn(self.opp, deck)
        self.assertIn(energy, deck)
        self.assertIs(t.active(P2), bench)
        self.assertEqual(len(t.zone(P1, 'prizes')), 6)   # not a Knock Out

    async def test_tapu_fini_dream_away_tails_does_nothing(self):
        t = self.table()
        fini = self.mine(t, TAPU_FINI, FAIRY, 2)
        self.mine(t, GULPIN, zone='bench', pid=P2)
        t.heads = False
        with coins('tails'):
            await t.attack(fini, 'Dream Away')
        self.assertIs(t.active(P2), self.opp)
        self.assertEqual(self.dealt(), 0)

    async def test_tapu_fini_wonder_shine_100_and_confused(self):
        t = self.table()
        fini = self.mine(t, TAPU_FINI, FAIRY, 3)
        await t.attack(fini, 'Wonder Shine')
        self.assertEqual(self.dealt(), 100)
        self.assertEqual(t.conditions(self.opp), {CONFUSED})
        self.assertEqual(t.conditions(fini), set())

    # --- Monferno UPR 22 / Larvesta DAA 29 / Litleo LOR 28 ---------------------
    async def test_monferno_super_singe_20_and_burned(self):
        t = self.table()
        m = self.mine(t, MONFERNO, FIRE, 1)
        await t.attack(m, 'Super Singe')
        self.assertEqual(self.dealt(), 20)
        self.assertEqual(t.conditions(self.opp), {BURNED})
        self.assertEqual(t.conditions(m), set())

    async def test_larvesta_and_litleo_singe_burn_without_damage(self):
        for spec in (LARVESTA, LITLEO):
            t = self.table()
            m = self.mine(t, spec, FIRE, 1)
            await t.attack(m, 'Singe')
            self.assertEqual(self.dealt(), 0, spec)
            self.assertEqual(t.conditions(self.opp), {BURNED}, spec)
            self.assertEqual(t.conditions(m), set(), spec)

    # --- Volcarona BLK 16: Torrid Scales ---------------------------------------
    async def test_volcarona_torrid_scales_discards_basic_fire_and_burns(self):
        t = self.table()
        v = self.mine(t, VOLCARONA, zone='bench')
        self.mine(t, self.filler)
        fire = t.put(t.basic_energy(FIRE), P1, 'hand')
        await t.use(v, 'Torrid Scales')
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertEqual(t.conditions(self.opp), {BURNED})
        t.put(t.basic_energy(FIRE), P1, 'hand')
        self.assertIsNone(t.ability_offer(v, 'Torrid Scales'))    # once per turn

    async def test_volcarona_torrid_scales_needs_basic_fire_in_hand(self):
        t = self.table()
        v = self.mine(t, VOLCARONA)
        t.put(t.basic_energy(WATER), P1, 'hand')
        t.energy(v, FIRE, 1)        # attached Fire doesn't count
        self.assertIsNone(t.ability_offer(v, 'Torrid Scales'))

    # --- Pyroar PHF 12: Flare Command / Inferno Onrush -------------------------
    async def test_pyroar_flare_command_discards_fire_and_gusts(self):
        t = self.table()
        p = self.mine(t, PYROAR)
        fire = t.energy(p, FIRE, 1)
        target = self.mine(t, GULPIN, zone='bench', pid=P2)
        t.pokemon = lambda cands, prompt: target
        t.picks = lambda cards, count, prompt, display: (
            [target] if target in cards else cards[:count])
        await t.use(p, 'Flare Command')
        self.assertIn(fire, t.zone(P1, 'discard'))
        self.assertIs(t.active(P2), target)
        self.assertIn(self.opp, t.zone(P2, 'bench'))
        self.assertIsNone(t.ability_offer(p, 'Flare Command'))

    async def test_pyroar_flare_command_not_offered_without_fire_or_bench(self):
        t = self.table()
        p = self.mine(t, PYROAR, WATER, 1)
        self.mine(t, GULPIN, zone='bench', pid=P2)
        self.assertIsNone(t.ability_offer(p, 'Flare Command'))      # no Fire Energy
        t2 = self.table()
        p2 = self.mine(t2, PYROAR, FIRE, 1)
        entry = t2.ability_offer(p2, 'Flare Command')
        if entry is not None:
            await t2.do(entry)
        # with no Benched opponent nothing should be discarded
        self.assertEqual(len([c for c in p2.children]), 1)

    async def test_pyroar_inferno_onrush_110_and_30_to_itself(self):
        t = self.table()
        p = self.mine(t, PYROAR, FIRE, 4, hp=110)
        await t.attack(p, 'Inferno Onrush')
        self.assertEqual(self.dealt(), 110)
        self.assertEqual(t.hp(p), 80)

    # --- Wela Volcano Park DRM 63 ----------------------------------------------
    async def test_wela_burn_stays_on_heads_for_both_players(self):
        for owner in (P1, P2):
            t = self.table()
            me = self.mine(t, self.filler, hp=300)
            t.stadium(WELA, owner)
            self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
            me.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
            t.heads = True
            with coins('heads'):
                await t.checkup()
            self.assertIn(BURNED, t.conditions(self.opp), owner)
            self.assertIn(BURNED, t.conditions(me), owner)
            self.assertEqual(self.dealt(), 20, owner)

    async def test_wela_absent_heads_removes_burn(self):
        t = self.table()
        self.mine(t, self.filler)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [BURNED])
        t.heads = True
        with coins('heads'):
            await t.checkup()
        self.assertNotIn(BURNED, t.conditions(self.opp))

    async def test_wela_does_not_affect_other_conditions(self):
        t = self.table()
        self.mine(t, self.filler)
        t.stadium(WELA, P1)
        self.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, [ASLEEP])
        t.heads = True
        with coins('heads'):
            await t.checkup()
        self.assertNotIn(ASLEEP, t.conditions(self.opp))

    # --- Lucky Egg SSH 167 -----------------------------------------------------
    async def _egg_holder(self, t):
        holder = self.mine(t, GULPIN, hp=20)
        self.mine(t, self.filler, zone='bench')
        egg = t.put(LUCKY_EGG, P1, 'hand')
        await t.play(egg, targets=[holder.entity_id])
        self.assertIn(egg, holder.children)
        self.clear_hand(t)
        t.put(self.item, P1, 'hand')
        return holder

    async def test_lucky_egg_draws_to_seven_on_attack_ko(self):
        t = self.table()
        holder = await self._egg_holder(t)
        attacker = self.mine(t, MONFERNO, FIRE, 1, pid=P2, zone='bench')
        # swap P2's active for the attacker
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(self.opp)
        t.board.move_card(attacker.entity_id,
                          t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        t.next_turn()
        await t.attack(attacker, 'Super Singe', pid=P2)
        self.assertNotIn(holder, t.zone(P1, 'active') + t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 7)

    async def test_lucky_egg_no_draw_on_poison_ko(self):
        t = self.table()
        holder = await self._egg_holder(t)
        holder.set_attribute(AttrID.HP, 10)
        holder.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        await t.checkup()
        self.assertNotIn(holder, t.zone(P1, 'active') + t.zone(P1, 'bench'))
        self.assertEqual(len(t.zone(P1, 'hand')), 1)

    # --- Gulpin SCR 91 / Swalot SCR 92 -----------------------------------------
    async def test_gulpin_super_poison_breath_30_and_poisoned(self):
        t = self.table()
        g = self.mine(t, GULPIN, DARK, 3)
        await t.attack(g, 'Super Poison Breath')
        self.assertEqual(self.dealt(), 30)
        self.assertEqual(t.conditions(self.opp), {POISONED})

    async def test_swalot_devouring_mouth_more_energy_adds_160(self):
        t = self.table()
        s = self.mine(t, SWALOT, DARK, 2)
        t.energy(self.opp, WATER, 1)
        await t.attack(s, 'Devouring Mouth')
        self.assertEqual(self.dealt(), 170)

    async def test_swalot_devouring_mouth_equal_energy_only_10(self):
        t = self.table()
        s = self.mine(t, SWALOT, DARK, 2)
        t.energy(self.opp, WATER, 2)
        await t.attack(s, 'Devouring Mouth')
        self.assertEqual(self.dealt(), 10)

    async def test_swalot_venomous_hit_100_and_poisoned(self):
        t = self.table()
        s = self.mine(t, SWALOT, DARK, 3)
        await t.attack(s, 'Venomous Hit')
        self.assertEqual(self.dealt(), 100)
        self.assertEqual(t.conditions(self.opp), {POISONED})

    # --- Dark City UNM 193 -----------------------------------------------------
    async def test_dark_city_basic_darkness_free_retreat_both_sides(self):
        for owner in (P1, P2):
            t = self.table()
            mine_g = self.mine(t, GULPIN)
            their_g = self.mine(t, GULPIN, zone='bench', pid=P2)
            self.assertEqual(t.retreat(mine_g), 2)
            t.stadium(DARK_CITY, owner)
            self.assertEqual(t.retreat(mine_g), 0, owner)
            self.assertEqual(t.retreat(their_g), 0, owner)

    async def test_dark_city_ignores_stage1_and_non_darkness(self):
        t = self.table()
        swalot = self.mine(t, SWALOT)
        larvesta = self.mine(t, LARVESTA, zone='bench')
        t.stadium(DARK_CITY, P1)
        self.assertEqual(t.retreat(swalot), 3)
        self.assertEqual(t.retreat(larvesta), 2)

    # --- Smeargle EVS 128: Live Painting ---------------------------------------
    # BUG: Live Painting never deals its printed base 30 (only 30 per type revealed)
    async def test_smeargle_live_painting_counts_types_not_cards(self):
        t = self.table()
        s = self.mine(t, SMEARGLE, WATER, 2)
        self.clear_hand(t)
        for kind in (FIRE, FIRE, WATER):
            t.put(t.basic_energy(kind), P1, 'hand')
        await t.attack(s, 'Live Painting')
        self.assertEqual(self.dealt(), 90)          # 30 + 2 types x 30
        self.assertEqual(len(t.zone(P1, 'hand')), 3)   # revealed, not discarded

    # BUG: Live Painting never deals its printed base 30 (only 30 per type revealed)
    async def test_smeargle_live_painting_reveal_none_is_30(self):
        t = self.table()
        s = self.mine(t, SMEARGLE, WATER, 2)
        self.clear_hand(t)
        t.put(t.basic_energy(FIRE), P1, 'hand')
        t.picks = lambda cards, count, prompt, display: []
        await t.attack(s, 'Live Painting')
        self.assertEqual(self.dealt(), 30)

    # BUG: Live Painting never deals its printed base 30 (only 30 per type revealed)
    async def test_smeargle_live_painting_resistance_applied_once(self):
        t = self.table()
        s = self.mine(t, SMEARGLE, WATER, 2)
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, PokemonTypes.COLORLESS.value)
        self.clear_hand(t)
        for kind in (FIRE, WATER):
            t.put(t.basic_energy(kind), P1, 'hand')
        await t.attack(s, 'Live Painting')
        self.assertEqual(self.dealt(), 60)          # (30 + 60) - 30


if __name__ == '__main__':
    unittest.main()
