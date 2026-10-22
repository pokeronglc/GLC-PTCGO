"""Bug hunt 10: unusual board states (hunt3 sweep).

Regression tests for real game bugs found by re-running the whole-database
sweep checkers (and cross-cutting Trainer / Ability sweeps) on odd boards:
Rare Candy stacks, Poké Dolls / Robo Substitute / fossils in play, Tools,
Electrode attached as Energy, Ability locks, full Benches and empty decks,
damaged / conditioned / W-R defenders.  Tooling: audits/results/hunt3.
"""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.tools.effect_smoke import P1, P2


def empty_deck(t, pid):
    area = t.board.find_player_area(pid, 'deck')
    for c in list(area.children):
        area.remove_child(c)


class Base(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        for pid in (P1, P2):
            t.put(self.filler, pid, 'active').set_attribute(AttrID.HP, 400)
            t.put(self.filler, pid, 'bench').set_attribute(AttrID.HP, 400)
            for _ in range(3):
                t.put(self.item, pid, 'hand')
        return t


# ---------------------------------------------------------------------------
# Empty deck: Trainers whose only effect is drawing must not be playable.
# House rules: "Draw Supporters can't be played with an empty deck" and "a
# card may be played if any part of it works".  The generic gate in
# standard_era.standard_trainer_condition skips texts that merely MENTION
# discard/shuffle/... in a follow-up clause that depends on the draw.
# ---------------------------------------------------------------------------
DRAW_ONLY = [
    ('SM5.Mars_128', 'Draw 2 cards. If you do, discard a random card from your opponent\'s hand.'),
    ('SM8.Whitney_193', 'Draw a card. Then, draw 2 cards for each other Whitney in your discard pile.'),
    ('SV06.Caretaker_144', 'Draw 2 cards. If you drew any cards in this way and ... shuffle this Caretaker'),
    ('SV085.Amarys_93', 'Draw 4 cards. At the end of this turn, if 5+ cards in hand, discard your hand.'),
    ('SM11.BluesTactics_188', 'At the end of this turn, draw cards until you have 8 cards in your hand.'),
    ('SVP.Picnicker_114', 'Flip a coin. If heads, draw 4 cards. If tails, draw 2 cards.'),
    ('XY1.RollerSkates_125', 'Flip a coin. If heads, draw 3 cards.'),
]


class EmptyDeckDrawTrainers(Base):
    async def test_draw_only_trainers_offered_with_a_deck(self):
        for spec, _ in DRAW_ONLY:
            with self.subTest(card=spec):
                t = self.table()
                card = t.put(spec, P1, 'hand')
                self.assertTrue(t.can(card, 'UseTrainerCard'))

    # FIXED Oct 13 (was: draw-only Trainers whose text continues with an "if you do/then"
    # clause (or starts with a coin flip / "at the end of this turn") are
    # still playable with an empty deck; nothing can happen.
    async def test_draw_only_trainers_not_playable_with_empty_deck(self):
        offered = []
        for spec, _ in DRAW_ONLY:
            t = self.table()
            empty_deck(t, P1)
            card = t.put(spec, P1, 'hand')
            if t.can(card, 'UseTrainerCard'):
                offered.append(spec)
        self.assertEqual(offered, [])


# ---------------------------------------------------------------------------
# "Pokémon that has an Ability": Poké Doll / Robo Substitute / Unidentified
# Fossil rule buttons are not Abilities (Antique Fossils DO have one).  Three
# card scripts read AttrID.PIE_ABILITIES (the client's ability-panel list,
# which also carries the rule-action buttons as "PokeAbility") instead of the
# definition's non-rule Abilities (bw_era._pokemon_has_ability).
# ---------------------------------------------------------------------------
DOLL = 'SM12.LilliesPokDoll_197'
ROBO = 'XY4.RoboSubstituteTeamFlareGear_102'
UFOSSIL = 'SM5.UnidentifiedFossil_134'
AFOSSIL = 'SV035.AntiqueDomeFossil_152'      # real Ability (Domed Armor)
COFAGRIGUS = 'SV08.Cofagrigus_83'            # Law of the Underworld (12 decks)
FLAPPLE = 'SWSH7.Flapple_120'                # Acidic Mucus (3 decks)
FROSLASS = 'SV06.Froslass_53'                # Freezing Shroud (14 decks)
WEEZING = 'SWSH2.GalarianWeezing_113'


def big(p, hp=400):
    p.attribute_originals[AttrID.HP.value] = hp
    p.set_attribute(AttrID.HP, hp)
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    return p


class DollsHaveNoAbility(Base):
    def board(self, attacker, opp_active=None):
        t = Table(self)
        me = big(t.put(attacker, P1, 'active'))
        big(t.put(self.filler, P1, 'bench'))
        opp = big(t.put(opp_active or self.filler, P2, 'active'))
        bench = {s: big(t.put(s, P2, 'bench')) for s in (DOLL, ROBO, UFOSSIL, AFOSSIL)}
        return t, me, opp, bench

    def lost(self, t, p):
        return 400 - t.hp(p)

    async def test_cofagrigus_law_of_the_underworld_hits_only_real_abilities_control(self):
        t, me, opp, bench = self.board(COFAGRIGUS)
        t.energy(me, PokemonTypes.PSYCHIC, 1)
        await t.attack(me, 'Law of the Underworld')
        self.assertEqual(self.lost(t, bench[AFOSSIL]), 60)
        self.assertEqual(self.lost(t, opp), 0)

    # FIXED Oct 13 (was: Law of the Underworld puts 6 counters on Lillie's Poké Doll, Robo
    # Substitute and Unidentified Fossil (rule buttons counted as Abilities).
    async def test_cofagrigus_law_of_the_underworld_skips_dolls(self):
        t, me, opp, bench = self.board(COFAGRIGUS)
        t.energy(me, PokemonTypes.PSYCHIC, 1)
        await t.attack(me, 'Law of the Underworld')
        self.assertEqual({s: self.lost(t, p) for s, p in bench.items() if s != AFOSSIL},
                         {DOLL: 0, ROBO: 0, UFOSSIL: 0})

    # FIXED Oct 13 (was: Acidic Mucus counts the doll/robo/fossil rule buttons: 200 instead
    # of 50 (only the Antique Fossil has an Ability).
    async def test_flapple_acidic_mucus_counts_only_real_abilities(self):
        t, me, opp, bench = self.board(FLAPPLE)
        t.energy(me, PokemonTypes.GRASS, 1)
        t.energy(me, PokemonTypes.FIRE, 1)
        await t.attack(me, 'Acidic Mucus')
        self.assertEqual(self.lost(t, opp), 50)

    # FIXED Oct 13 (was: a Poké Doll as the opponent's Active counts for Acidic Mucus.
    async def test_flapple_acidic_mucus_doll_active_counts_zero(self):
        t = Table(self)
        me = big(t.put(FLAPPLE, P1, 'active'))
        t.energy(me, PokemonTypes.GRASS, 1)
        t.energy(me, PokemonTypes.FIRE, 1)
        doll = big(t.put(DOLL, P2, 'active'))
        big(t.put(self.filler, P2, 'bench'))
        await t.attack(me, 'Acidic Mucus')
        self.assertEqual(self.lost(t, doll), 0)

    # FIXED Oct 13 (was: Acidic Mucus ignores Ability locks (Hex Maniac style): an Antique
    # Fossil whose Abilities are switched off still counts (Scizor SV3 141's
    # Punishing Scissors gets this right via bw_era._has_working_ability).
    async def test_flapple_acidic_mucus_respects_ability_lock(self):
        t = Table(self)
        me = big(t.put(FLAPPLE, P1, 'active'))
        t.energy(me, PokemonTypes.GRASS, 1)
        t.energy(me, PokemonTypes.FIRE, 1)
        opp = big(t.put(self.filler, P2, 'active'))
        big(t.put(AFOSSIL, P2, 'bench'))
        t.state.abilities_disabled_through_turn = t.state.turn_number + 1
        await t.attack(me, 'Acidic Mucus')
        self.assertEqual(self.lost(t, opp), 0)

    async def froslass_board(self, lock=False):
        t = Table(self)
        big(t.put(self.filler, P1, 'active'))
        mine = {s: big(t.put(s, P1, 'bench')) for s in (DOLL, ROBO, UFOSSIL, AFOSSIL)}
        big(t.put(WEEZING if lock else self.filler, P2, 'active'))
        big(t.put(FROSLASS, P2, 'bench'))
        t.next_turn()            # P2's turn ends -> checkup
        await t.checkup()
        return t, mine

    async def test_froslass_freezing_shroud_control(self):
        t, mine = await self.froslass_board()
        self.assertEqual(self.lost(t, mine[AFOSSIL]), 10)

    # FIXED Oct 13 (was: Freezing Shroud puts a counter on Poké Doll / Robo Substitute /
    # Unidentified Fossil every Pokémon Checkup.
    async def test_froslass_freezing_shroud_skips_dolls(self):
        t, mine = await self.froslass_board()
        self.assertEqual({s: self.lost(t, p) for s, p in mine.items() if s != AFOSSIL},
                         {DOLL: 0, ROBO: 0, UFOSSIL: 0})

    # FIXED Oct 13 (was: Freezing Shroud ignores Ability locks: under the opponent's
    # Neutralizing Gas P1's Antique Fossil "has no Abilities" but still takes
    # a counter (Cofagrigus uses _has_working_ability; Froslass doesn't).
    async def test_froslass_freezing_shroud_respects_ability_lock(self):
        t, mine = await self.froslass_board(lock=True)
        self.assertEqual(self.lost(t, mine[AFOSSIL]), 0)


if __name__ == '__main__':
    unittest.main()
