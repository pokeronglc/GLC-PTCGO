"""Bug hunt, deck 1 (Colorless): Supporters and Items, through the real
play-trainer executor (so play conditions and once-per-turn rules apply)."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

W = PokemonTypes.WATER
PIKIPEK, TOUCANNON = 'ME5.Pikipek_66', 'ME5.Toucannon_68'
MINCCINO, BIDOOF = 'SWSH9.Minccino_124', 'CZ.Bidoof_111'
WOOLOO, HOP_SNORLAX, CRAMORANT = 'SV09.HopsWooloo_135', 'SV09.HopsSnorlax_117', 'SV09.HopsCramorant_138'
SABLEYE, ORANGURU = 'SV2.Sableye_136', 'SM1.Oranguru_113'
ARTAZON, LOST_CITY = 'SV2.Artazon_171', 'SWSH11.LostCity_161'
MUSCLE_BAND, DRAW_ENERGY = 'XY1.MuscleBand_121', 'SM12.DrawEnergy_209'
WINONA, HEX, LYSANDRE = 'XY6.Winona_96', 'XY7.HexManiac_75', 'XY2.Lysandre_90'
PETREL, CIPHER, COLRESS = ('SV10.TeamRocketsPetrel_176', 'SV05.CiphermaniacsCodebreaking_145',
                           'SV065.ColresssTenacity_57')
TOWN_MAP, RESET_STAMP = 'BW7.TownMap_136', 'SM11.ResetStamp_206'
LOST_VACUUM, STRETCHER = 'SWSH11.LostVacuum_162', 'SM2.RescueStretcher_130'


class ChoiceTable(Table):
    """Table that also scripts ctx.choose (Choose 1 menus)."""
    choice = 0

    def _patches(self):
        table = self

        async def choose(ctx, prompt, buttons, player_id=None, descriptions=None, use_panel=True):
            table.prompts.append(prompt)
            return table.choice
        return super()._patches() + [patch.object(EffectContext, 'choose', choose)]


class Deck1Trainers(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self, **kw):
        t = ChoiceTable(self, **kw)
        self.me = t.put(self.filler, P1, 'active')
        self.opp = t.put(self.filler, P2, 'active')
        return t

    def hand_names(self, t, pid=P1):
        return t.names(t.zone(pid, 'hand'))

    def spy(self, t):
        seen = {}
        t.picks = lambda cards, count, prompt, display: (
            seen.setdefault('n', (t.names(cards), count)), cards[:count])[1]
        return seen

    # --- Winona -------------------------------------------------------------
    async def test_winona_up_to_three_colorless(self):
        t = self.table()
        t.deck(P1, [PIKIPEK, MINCCINO, HOP_SNORLAX, SABLEYE, CRAMORANT, t.basic_energy(W)])
        seen = self.spy(t)
        await t.play(t.put(WINONA, P1, 'hand'))
        names, count = seen['n']
        self.assertEqual(count, 3)
        self.assertNotIn('Sableye', names)
        self.assertEqual(len(t.zone(P1, 'hand')), 3)
        self.assertNotIn('Sableye', self.hand_names(t))

    # --- Hex Maniac ----------------------------------------------------------
    async def test_hex_maniac_locks_both_until_end_of_opponents_turn(self):
        t = self.table()
        mine = t.put(TOUCANNON, P1, 'bench')
        theirs = t.put(TOUCANNON, P2, 'bench')
        self.assertIsNotNone(t.ability_offer(mine, 'Aerial Draw'))
        await t.play(t.put(HEX, P1, 'hand'))
        self.assertIsNone(t.ability_offer(mine, 'Aerial Draw'))
        t.next_turn()
        self.assertIsNone(t.ability_offer(theirs, 'Aerial Draw', P2))
        t.next_turn()
        self.assertIsNotNone(t.ability_offer(mine, 'Aerial Draw'))

    async def test_hex_maniac_turns_off_passive_abilities(self):
        t = self.table()
        t.board.find_player_area(P1, 'activePokemonArea').remove_child(self.me)
        wooloo = t.put(WOOLOO, P1, 'active')
        t.energy(wooloo, W, 3)
        t.put(HOP_SNORLAX, P1, 'bench')
        self.opp.set_attribute(AttrID.HP, 400)
        self.opp.set_attribute(AttrID.WEAKNESS_TYPES, [])
        self.opp.set_attribute(AttrID.RESISTANCE_TYPES, [])
        await t.play(t.put(HEX, P1, 'hand'))
        await t.attack(wooloo, 'Smash Kick')
        self.assertEqual(400 - t.hp(self.opp), 50)       # no Extra Helpings

    # --- Lysandre --------------------------------------------------------------
    async def test_lysandre_switches_opponent_only(self):
        t = self.table()
        target = t.put(SABLEYE, P2, 'bench')
        my_bench = t.put(PIKIPEK, P1, 'bench')
        t.pokemon = lambda c, p: target if target in c else c[0]
        await t.play(t.put(LYSANDRE, P1, 'hand'))
        self.assertIs(t.active(P2), target)
        self.assertIs(t.active(P1), self.me)

    async def test_lysandre_needs_opponent_bench(self):
        t = self.table()
        t.put(PIKIPEK, P1, 'bench')
        self.assertFalse(t.can(t.put(LYSANDRE, P1, 'hand'), 'UseTrainerCard'))

    # --- Team Rocket's Petrel ---------------------------------------------------
    async def test_petrel_trainer_only(self):
        t = self.table(filler_deck=0)
        t.deck(P1, [PIKIPEK, t.basic_energy(W), ARTAZON])
        seen = self.spy(t)
        await t.play(t.put(PETREL, P1, 'hand'))
        names, count = seen['n']
        self.assertEqual(names, ['Artazon'])
        self.assertEqual(count, 1)
        self.assertEqual(self.hand_names(t), ['Artazon'])

    # --- Ciphermaniac's Codebreaking ---------------------------------------
    async def test_ciphermaniac_two_cards_on_top_in_order(self):
        t = self.table()
        a, b = t.deck(P1, [PIKIPEK, SABLEYE], top=False)
        t.picks = lambda cards, count, prompt, display: [b, a]
        await t.play(t.put(CIPHER, P1, 'hand'))
        deck = t.zone(P1, 'deck')
        self.assertIs(deck[-1], b)      # first pick is the new top
        self.assertIs(deck[-2], a)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_ciphermaniac_needs_two_cards_in_deck(self):
        t = self.table(filler_deck=1)
        self.assertFalse(t.can(t.put(CIPHER, P1, 'hand'), 'UseTrainerCard'))

    # --- Colress's Tenacity -------------------------------------------------
    async def test_colress_stadium_and_energy(self):
        t = self.table()
        t.deck(P1, [ARTAZON, t.basic_energy(W), PIKIPEK, MUSCLE_BAND])
        await t.play(t.put(COLRESS, P1, 'hand'))
        hand = t.zone(P1, 'hand')
        self.assertEqual(len(hand), 2)
        self.assertIn('Artazon', self.hand_names(t))
        self.assertTrue(any(c.archetype_id.lower() == t.basic_energy(W).guid.lower() for c in hand))

    async def test_colress_special_energy_counts_and_no_stadium_ok(self):
        t = self.table()
        t.deck(P1, [DRAW_ENERGY, PIKIPEK])
        await t.play(t.put(COLRESS, P1, 'hand'))
        self.assertEqual(self.hand_names(t), ['Draw Energy'])

    # --- Town Map --------------------------------------------------------------
    async def test_town_map_turns_own_prizes_face_up(self):
        t = self.table()
        await t.play(t.put(TOWN_MAP, P1, 'hand'))
        self.assertTrue(all(getattr(p, 'publicly_revealed', False) for p in t.zone(P1, 'prizes')))
        self.assertFalse(any(getattr(p, 'publicly_revealed', False) for p in t.zone(P2, 'prizes')))

    # --- Reset Stamp ---------------------------------------------------------
    async def test_reset_stamp_opponent_draws_per_prize(self):
        t = self.table()
        t.set_prizes(P2, 3)
        old = [t.put(PIKIPEK, P2, 'hand') for _ in range(5)]
        mine = [t.put(self.filler, P1, 'hand') for _ in range(2)]
        await t.play(t.put(RESET_STAMP, P1, 'hand'))
        hand = t.zone(P2, 'hand')
        self.assertEqual(len(hand), 3)
        self.assertEqual(len([c for c in t.zone(P2, 'deck') if c in old]) + len(set(hand) & set(old)), 5)
        self.assertEqual(set(t.zone(P1, 'hand')), set(mine))

    # --- Lost Vacuum -----------------------------------------------------------
    async def test_lost_vacuum_tool(self):
        t = self.table()
        tool = t.attach(MUSCLE_BAND, self.opp)
        cost = t.put(PIKIPEK, P1, 'hand')
        vac = t.put(LOST_VACUUM, P1, 'hand')
        await t.play(vac)
        lost1 = t.zone(P1, 'lostZone')
        lost2 = t.zone(P2, 'lostZone')
        self.assertIn(cost, lost1)
        self.assertIn(tool, lost2)
        self.assertNotIn(tool, self.opp.children)

    async def test_lost_vacuum_stadium(self):
        t = self.table()
        stadium = t.stadium(ARTAZON, P2)
        t.put(PIKIPEK, P1, 'hand')
        await t.play(t.put(LOST_VACUUM, P1, 'hand'))
        self.assertFalse(t.board.find_global_area('activeStadium').children)
        self.assertIn(stadium, t.zone(P2, 'lostZone'))

    async def test_lost_vacuum_conditions(self):
        t = self.table()
        t.attach(MUSCLE_BAND, self.opp)
        vac = t.put(LOST_VACUUM, P1, 'hand')
        self.assertFalse(t.can(vac, 'UseTrainerCard'))     # no other card to Lost-Zone
        t = self.table()
        t.put(PIKIPEK, P1, 'hand')
        vac = t.put(LOST_VACUUM, P1, 'hand')
        self.assertFalse(t.can(vac, 'UseTrainerCard'))     # nothing to remove

    # --- Rescue Stretcher ----------------------------------------------------
    async def test_rescue_stretcher_one_to_hand(self):
        t = self.table()
        pk = t.put(PIKIPEK, P1, 'discard')
        t.put(t.basic_energy(W), P1, 'discard')
        t.choice = 0
        await t.play(t.put(STRETCHER, P1, 'hand'))
        self.assertEqual(t.zone(P1, 'hand'), [pk])

    async def test_rescue_stretcher_three_to_deck(self):
        t = self.table()
        mons = [t.put(s, P1, 'discard') for s in (PIKIPEK, MINCCINO, BIDOOF, SABLEYE)]
        t.choice = 1
        await t.play(t.put(STRETCHER, P1, 'hand'))
        left = [c for c in t.zone(P1, 'discard') if c in mons]
        self.assertEqual(len(left), 1)
        self.assertEqual(len([c for c in t.zone(P1, 'deck') if c in mons]), 3)
        self.assertEqual(len(t.zone(P1, 'hand')), 0)

    async def test_rescue_stretcher_needs_pokemon_in_discard(self):
        t = self.table()
        t.put(t.basic_energy(W), P1, 'discard')
        self.assertFalse(t.can(t.put(STRETCHER, P1, 'hand'), 'UseTrainerCard'))


if __name__ == "__main__":
    unittest.main()
