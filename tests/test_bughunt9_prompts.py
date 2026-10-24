"""Bug hunt 9: "unexpected prompt" audit (whole GLC pool).

Every distinct Pokémon attack / activated Ability, Trainer, Special Energy and
play-from-hand trigger was run once on a rich board by
audits/results/prompt_audit.py; every prompt was logged and checked
against the printed text (prompt_classify.py).  The tests below pin the real
bugs found, grouped by root cause.  Each asserts the CORRECT behaviour.
"""
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from tests import test_glc_meta_cards as meta
from tests import test_hgss_rules as fixtures
from tests.bughunt_table import Table
from tests.sweep_core import pay_cost
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2


def _big(p, hp=300, dmg=0):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    p.attribute_originals[AttrID.HP.value] = hp
    p.set_attribute(AttrID.HP, hp - dmg)
    return p


class PromptTable(Table):
    """Table that also records WHO is asked, the candidates and minimums."""

    def __init__(self, test, **kw):
        super().__init__(test, **kw)
        self.log = []          # (kind, player_id, prompt, candidates, minimum)
        self.coins = []        # (title, count)

    def _patches(self):
        table = self

        async def choose_cards(ctx, cards, count, minimum=None, prompt='', player_id=None,
                               ordered=False, display_cards=None, slot_prompt='',
                               submit_on_pick=False):
            cards = list(cards)
            table.log.append(('cards', player_id or ctx.player_id, prompt, cards, minimum))
            if table.picks is not None:
                return list(table.picks(cards, count, prompt, display_cards))
            return cards[:count]

        async def choose_pokemon(ctx, candidates, prompt='', player_id=None, optional=False):
            candidates = ctx.selectable_pokemon(list(candidates))
            table.log.append(('pokemon', player_id or ctx.player_id, prompt, candidates, None))
            if not candidates:
                return None
            if table.pokemon is not None:
                return table.pokemon(candidates, prompt)
            return candidates[0]

        async def ask_yes_no(ctx, prompt, player_id=None):
            table.log.append(('yesno', player_id or ctx.player_id, prompt, [], None))
            return table.yes(prompt) if callable(table.yes) else table.yes

        async def flip_coins(ctx, count, title='', source=None, player_id=None):
            table.coins.append((title, count))
            return [bool(table.heads)] * count

        async def flip_until_tails(ctx, title=''):
            table.coins.append((title, None))
            return 0

        return [patch.object(EffectContext, 'choose_cards', choose_cards),
                patch.object(EffectContext, 'choose_pokemon', choose_pokemon),
                patch.object(EffectContext, 'ask_yes_no', ask_yes_no),
                patch.object(EffectContext, 'flip_coins', flip_coins),
                patch.object(EffectContext, 'flip_until_tails', flip_until_tails)]

    def asked(self, pid):
        return [entry for entry in self.log if entry[1] == pid]


def _attack(d, title):
    return next(a for a in d.abilities if isinstance(a, Attack) and a.title == title)


class BugHunt9Prompts(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # ----------------------------------------------------------------- board
    def board(self, path=None, zone='active', my_dmg=30):
        t = PromptTable(self)
        me = None
        if path is not None:
            me = _big(t.put(path, P1, zone), dmg=my_dmg)
        if zone != 'active' or path is None:
            active = _big(t.put(self.filler, P1, 'active'), dmg=my_dmg)
            me = me or active
        bench = _big(t.put(self.filler, P1, 'bench'), dmg=20)
        t.energy(bench, PokemonTypes.FIRE)
        opp = _big(t.put(self.filler, P2, 'active'), dmg=30)
        t.energy(opp, PokemonTypes.FIGHTING, 2)
        opp_bench = _big(t.put(self.filler, P2, 'bench'), dmg=20)
        for pid in (P1, P2):
            for kind in (PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.GRASS):
                t.put(t.basic_energy(kind), pid, 'hand')
                t.put(t.basic_energy(kind), pid, 'discard')
                t.put(t.basic_energy(kind), pid, 'deck')
        return t, me, bench, opp, opp_bench

    async def attack(self, t, me, path, title):
        pay_cost(t, me, _attack(fixtures.definition(path), title))
        await t.attack(me, title)

    # ===================================================================
    # Root cause A: bw_era.bw_legacy_ability "switch your active pokémon
    # with 1 of your benched pokémon" branch always makes the opponent
    # switch too (written for Slippery Soles / Magnetic Warp / Witch Rondo).
    # ===================================================================
    async def test_gengar_night_gate_only_switches_own_active(self):
        # FIXED Oct 13: Gengar SV045 57 Night Gate also prompts the OPPONENT to switch their Active (no such text).
        t, me, bench, opp, opp_bench = self.board('SV045.Gengar_57')
        await t.use(me, 'Night Gate')
        self.assertIs(t.active(P1), bench)               # our switch happened
        self.assertEqual(t.asked(P2), [])               # opponent never asked
        self.assertIs(t.active(P2), opp)                # opponent's Active unchanged

    # ===================================================================
    # Root cause B: bw_era.bw_legacy_ability generic "move 1 damage counter"
    # branch (Shady Move) offers EVERY Pokémon in play as source and target,
    # ignoring "of your Pokémon" / "to this Pokémon" / "Team Rocket's".
    # ===================================================================
    async def test_jynx_ominous_posture_only_own_pokemon(self):
        # FIXED Oct 13: Jynx SM11 76 Ominous Posture offers the opponent's Pokémon as source and destination.
        t, me, bench, opp, opp_bench = self.board('SM11.Jynx_76')
        await t.use(me, 'Ominous Posture')
        picks = [e for e in t.log if e[0] == 'pokemon']
        self.assertTrue(picks)
        for _, pid, prompt, cands, _ in picks:
            self.assertTrue(all(c.owning_player_id == P1 for c in cands), prompt)

    async def test_dusknoir_shadow_void_moves_counter_onto_itself(self):
        # FIXED Oct 13: Dusknoir XY2 40 Shadow Void asks for any destination (incl. opponent's) instead of "this Pokémon".
        t, me, bench, opp, opp_bench = self.board('XY2.Dusknoir_40', my_dmg=0)
        t.pokemon = lambda cands, prompt: (bench if bench in cands else cands[0])
        before = t.damage(me)
        await t.use(me, 'Shadow Void')
        for kind, pid, prompt, cands, _ in t.log:
            if kind == 'pokemon':
                self.assertTrue(all(c.owning_player_id == P1 for c in cands), prompt)
        self.assertEqual(t.damage(me), before + 10)

    async def test_slowbro_strange_behavior_from_other_own_pokemon_to_itself(self):
        # FIXED Oct 13: Slowbro SV1 43 Strange Behavior: source list includes itself and the opponent's Pokémon; target is chosen.
        # Oct 23: repeats in one activation until Done / nothing left to move.
        t, me, bench, opp, opp_bench = self.board('SV1.Slowbro_43')
        before_me, before_bench = t.damage(me), t.damage(bench)
        await t.use(me, 'Strange Behavior')
        first = next(e for e in t.log if e[0] == 'pokemon')
        self.assertEqual(set(first[3]), {bench})        # "1 of your other Pokémon"
        self.assertEqual(t.damage(bench), 0)
        self.assertEqual(t.damage(me), before_me + before_bench)

    async def test_team_rockets_orbeetle_rocket_brain_only_own_pokemon(self):
        # FIXED Oct 13: Team Rocket's Orbeetle SV10 89 Rocket Brain offers opponent's (and non-Team Rocket) Pokémon.
        t, me, bench, opp, opp_bench = self.board('SV10.TeamRocketsOrbeetle_89')
        await t.use(me, 'Rocket Brain')
        first = next(e for e in t.log if e[0] == 'pokemon')
        self.assertEqual(set(first[3]), {me})            # only damaged Team Rocket's Pokémon
        for kind, pid, prompt, cands, _ in t.log:
            if kind == 'pokemon':
                self.assertTrue(all(c.owning_player_id == P1 for c in cands), prompt)

    # ===================================================================
    # Root cause C: bw_era.bw_legacy_attack coin detection
    # (re.search("flip (?:a|1) coin") / "flip (\d+) coins") scans the whole
    # text, so a flip that belongs to a LATER turn is flipped right now.
    # ===================================================================
    async def test_reactive_prevent_damage_attacks_flip_no_coin_now(self):
        # FIXED Oct 13: "If any damage is done to this Pokémon ... during your opponent's next turn, flip a coin" flips during the attack.
        for path, title in (('SM1.Cutiefly_92', 'Fly Around'),
                            ('SM10.Frogadier_52', 'Afterimage Strike'),
                            ('XY3.Accelgor_9', 'Afterimage Strike')):
            with self.subTest(card=path):
                t, me, *_ = self.board(path)
                await self.attack(t, me, path, title)
                self.assertEqual(t.coins, [])

    async def test_psyduck_overthink_flips_no_coin_now(self):
        # FIXED Oct 13: Psyduck SV035 54 Overthink ("whenever they flip a coin") flips a coin during the attack.
        t, me, *_ = self.board('SV035.Psyduck_54')
        await self.attack(t, me, 'SV035.Psyduck_54', 'Overthink')
        self.assertEqual(t.coins, [])

    async def test_maractus_exciting_shake_flips_no_coins_now(self):
        # FIXED Oct 13: Maractus XY2 10 Exciting Shake flips 6 coins during the attack (they belong to next turn's Prickly Needles).
        t, me, *_ = self.board('XY2.Maractus_10')
        await self.attack(t, me, 'XY2.Maractus_10', 'Exciting Shake')
        self.assertEqual(t.coins, [])

    async def test_maractus_exciting_shake_next_prickly_needles_flips_six(self):
        # FIXED Oct 13: Exciting Shake's "flip 6 coins instead of 2" next turn is not implemented at all.
        path = 'XY2.Maractus_10'
        t, me, *_ = self.board(path)
        await self.attack(t, me, path, 'Exciting Shake')
        t.next_turn()
        t.next_turn()
        t.coins.clear()
        await self.attack(t, me, path, 'Prickly Needles')
        self.assertEqual(sum(c for _, c in t.coins if c), 6)

    # ===================================================================
    # Root cause D: card scripts restrict "1 of your Pokémon" to the Bench.
    # ===================================================================
    async def test_attach_to_1_of_your_pokemon_offers_the_active(self):
        # FIXED Oct 13: Volcarona BW3 21 / Delcatty BW7 114 / Magnezone BW8 47 only offer Benched Pokémon (and do nothing with an empty Bench).
        for path, title in (('BW3.Volcarona_21', 'Fiery Dance'),
                            ('BW7.Delcatty_114', 'Gather Energy'),
                            ('BW8.Magnezone_47', 'Double Assist')):
            with self.subTest(card=path):
                t, me, *_ = self.board(path)
                await self.attack(t, me, path, title)
                targets = [e for e in t.log if e[0] == 'pokemon']
                self.assertTrue(targets)
                self.assertIn(me, targets[-1][3])

    # ===================================================================
    # Root cause E: wrong prompt / coin labels shown to players.
    # ===================================================================
    async def test_banette_cursed_words_prompt_is_not_discard(self):
        # FIXED Oct 13: Banette SV09 60 Cursed Words asks the opponent "Choose cards to discard" but shuffles them into the deck.
        t, me, *_ = self.board('SV09.Banette_60')
        await self.attack(t, me, 'SV09.Banette_60', 'Cursed Words')
        asked = [e for e in t.asked(P2) if e[0] == 'cards']
        self.assertTrue(asked)
        self.assertNotIn('discard', asked[0][2].lower())

    async def test_coin_titles_name_the_attack(self):
        # FIXED Oct 13: shared helpers title the coin with another card's attack (Crunch -> "Destructive Beam", etc.).
        for path, title in (('BW1.Basculin_35', 'Crunch'),
                            ('BW2.Throh_58', 'Scarf Hold'),
                            ('BW7.Liepard_91', 'Assist')):
            with self.subTest(card=path):
                t, me, *_ = self.board(path)
                await self.attack(t, me, path, title)
                self.assertTrue(t.coins)
                self.assertEqual(t.coins[0][0], title)

    # ===================================================================
    # Root cause F: attacks force a pick on "up to N" (owner ruling: attacks
    # and private deck searches may take 0).
    # ===================================================================
    async def test_up_to_attack_picks_allow_zero(self):
        # FIXED Oct 13: "Search your deck for up to N cards" (bw_era _search_printed_cards caller) and Gather Flowers force minimum=1.
        for path, title in (('SM12.Weavile_44', 'Nasty Plot'),
                            ('CZ.Shaymin_115', 'Gather Flowers')):
            with self.subTest(card=path):
                t, me, *_ = self.board(path)
                await self.attack(t, me, path, title)
                picks = [e for e in t.log if e[0] == 'cards']
                self.assertTrue(picks)
                self.assertEqual(picks[0][4], 0)

    # ===================================================================
    # Root cause G: activated-Ability scripts re-ask their "you may" after
    # the player already chose to use the Ability; "No" burns the use.
    # ===================================================================
    async def test_wyrdeer_hurried_gait_no_reconfirm(self):
        # FIXED Oct 13: Wyrdeer SWSH10 69 asks "Draw a card?" after activation; answering No wastes the once-per-turn Ability.
        t, me, *_ = self.board('SWSH10.Wyrdeer_69')
        t.yes = False
        hand = len(t.zone(P1, 'hand'))
        await t.use(me, 'Hurried Gait')
        self.assertEqual([e for e in t.log if e[0] == 'yesno'], [])
        self.assertEqual(len(t.zone(P1, 'hand')), hand + 1)

    async def test_milotic_bright_heal_no_reconfirm(self):
        t, me, bench, *_ = self.board('SWSH3.Milotic_39')
        t.yes = False
        me_hp, bench_hp = me.get_attribute(AttrID.HP), bench.get_attribute(AttrID.HP)
        await t.use(me, 'Bright Heal')
        self.assertEqual([e for e in t.log if e[0] == 'yesno'], [])
        self.assertEqual(me.get_attribute(AttrID.HP), me_hp + 20)
        self.assertEqual(bench.get_attribute(AttrID.HP), bench_hp + 20)

    async def test_control_triggered_you_may_still_asks(self):
        # Oricorio SM2 55 Vital Dance is an ON_PLAY trigger: nothing was
        # clicked, so the printed "you may" must still be asked.
        t, *_ = self.board()
        oricorio = t.put('SM2.Oricorio_55', P1, 'hand')
        t.yes = False
        hand = len(t.zone(P1, 'hand'))
        await t.play(oricorio)
        self.assertEqual(len([e for e in t.log if e[0] == 'yesno']), 1)
        self.assertEqual(len(t.zone(P1, 'hand')), hand - 1)

    # ------------------------------------------------- controls (must pass)
    async def test_control_witch_rondo_still_switches_both(self):
        t, me, bench, opp, opp_bench = self.board('SWSH6.Hatterene_73')
        await t.use(me, 'Witch Rondo')
        self.assertIs(t.active(P1), bench)
        self.assertIs(t.active(P2), opp_bench)

    async def test_control_chandelure_shady_move_any_pokemon(self):
        t, me, bench, opp, opp_bench = self.board('SM2.Chandelure_13')
        await t.use(me, 'Shady Move')
        first = next(e for e in t.log if e[0] == 'pokemon')
        self.assertTrue(any(c.owning_player_id == P2 for c in first[3]))

    async def test_control_dragonair_dragons_wish_no_prompt_now(self):
        t, me, *_ = self.board('SM1.Dragonair_95')
        await self.attack(t, me, 'SM1.Dragonair_95', "Dragon's Wish")
        self.assertEqual(t.log, [])


if __name__ == '__main__':
    unittest.main()
