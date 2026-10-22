"""Focused regressions for generic draw Trainers whose count depends on a coin,
a board condition or a per-card multiplier (standard_era._resolve_draw_variant),
their play conditions (standard_trainer_condition), and Ninja Boy's identity
swap with the deck."""
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.test_sweep_draw import DrawTable, set_zone, counts, any_stadium, basic_of_type, seq_heads
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID, def_for
from spirit.tools.effect_smoke import P1, P2


def card(set_code, number):
    return next(d for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: d.guid)
                if d.set_code == set_code and str(d.collector_number) == str(number))


def plain_stage1():
    """A Stage 1 Pokémon without Abilities.  (Deliberately not
    tests.test_sweep_abilities.pool: that module-level cache must not be
    filled this early in a full run, before card definitions are reloaded.)"""
    from spirit.game.data_utils import PokemonCardDef, Attack
    from spirit.game.attributes import PokemonStage
    for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, str(d.collector_number), d.guid)):
        spec = (d.extra_attributes or {}).get(str(AttrID.STAGE.value)) \
            if isinstance(d, PokemonCardDef) else None
        stage = spec.get('value') if isinstance(spec, dict) else None
        if stage == PokemonStage.STAGE1.value \
                and all(isinstance(a, Attack) for a in (d.abilities or [])):
            return d
    raise AssertionError('no Stage 1 Pokémon')


def neutral(p):
    p.set_attribute(AttrID.SPECIAL_CONDITIONS, [])
    return p


class TrainerDrawFixes(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    # -- helpers ---------------------------------------------------------
    def table(self, hand=2, deck=30, opp_hand=4):
        t = DrawTable(self)
        t.me = neutral(t.put(self.filler, P1, 'active'))
        t.bench = neutral(t.put(self.filler, P1, 'bench'))
        t.opp = neutral(t.put(self.filler, P2, 'active'))
        t.opp_bench = neutral(t.put(self.filler, P2, 'bench'))
        set_zone(t, P1, 'deck', deck)
        set_zone(t, P2, 'deck', 30)
        set_zone(t, P1, 'hand', hand)
        set_zone(t, P2, 'hand', opp_hand)
        return t

    def offer(self, t, c):
        return next((e for e in t.offers(c, None, P1)
                     if e['selectableAction']['description'] == 'UseTrainerCard'), None)

    async def play(self, t, d):
        c = t.put(d, P1, 'hand')
        entry = self.offer(t, c)
        self.assertIsNotNone(entry, f'{d.display_name} not offered')
        await t.do(entry)
        return c

    def hand(self, t, pid=P1):
        return len(t.zone(pid, 'hand'))

    # -- A. conditional / multiplied draws -------------------------------
    async def test_samson_oak_same_type(self):
        d = card('SM10', 185)
        t = self.table()
        await self.play(t, d)
        self.assertEqual(self.hand(t), 6)            # both Actives are the filler
        t = self.table()
        fire = basic_of_type(PokemonTypes.FIRE.value)
        t.board.move_card(t.opp.entity_id, t.board.find_player_area(P2, 'discard').entity_id)
        neutral(t.put(fire, P2, 'active'))
        await self.play(t, d)
        self.assertEqual(self.hand(t), 4)

    async def test_falkner_own_stadium(self):
        d = card('SV2', 180)
        t = self.table()
        t.stadium(any_stadium(self), P1)
        await self.play(t, d)
        self.assertEqual(self.hand(t), 6)
        t = self.table()
        t.stadium(any_stadium(self), P2)             # opponent's Stadium does not count
        await self.play(t, d)
        self.assertEqual(self.hand(t), 4)

    async def test_billy_onare_checks_after_first_draw(self):
        d = card('SV09', 142)
        t = self.table(hand=8)
        await self.play(t, d)
        self.assertEqual(self.hand(t), 12)
        t = self.table(hand=7)
        await self.play(t, d)
        self.assertEqual(self.hand(t), 9)

    async def test_grusha_seven_without_energy(self):
        d = card('SV2', 184)
        t = self.table()
        await self.play(t, d)
        self.assertEqual(self.hand(t), 7)
        t = self.table()
        t.energy(t.bench, PokemonTypes.WATER)
        await self.play(t, d)
        self.assertEqual(self.hand(t), 5)
        # 5 cards, no Energy: still playable (7 target); with Energy it is not.
        t = self.table(hand=5)
        await self.play(t, d)
        self.assertEqual(self.hand(t), 7)
        t = self.table(hand=5)
        t.energy(t.bench, PokemonTypes.WATER)
        self.assertIsNone(self.offer(t, t.put(d, P1, 'hand')))

    async def test_hala_gx_used(self):
        d = card('SM2', 126)
        t = self.table(hand=3)
        t.state.gx_used.add(P1)
        await self.play(t, d)
        self.assertEqual((self.hand(t), len(t.zone(P1, 'deck'))), (7, 26))
        t = self.table(hand=3)
        await self.play(t, d)
        self.assertEqual((self.hand(t), len(t.zone(P1, 'deck'))), (4, 29))

    async def test_parasol_lady_going_second_first_turn(self):
        d = card('SV4', 169)
        t = self.table(hand=3)
        t.state.turn_number = 2
        t.session.first_player_id = P2
        t.board.setup_first_player_id = P2
        await self.play(t, d)
        self.assertEqual(self.hand(t), 8)
        t = self.table(hand=3)
        await self.play(t, d)
        self.assertEqual(self.hand(t), 4)

    async def test_whitney_counts_other_whitneys(self):
        d = card('SM8', 193)
        t = self.table()
        t.put(d, P1, 'discard')
        t.put(d, P1, 'discard')
        await self.play(t, d)
        self.assertEqual(self.hand(t), 7)
        t = self.table()
        await self.play(t, d)
        self.assertEqual(self.hand(t), 3)

    async def test_blaines_last_stand(self):
        d = card('DM', 58)
        fire = basic_of_type(PokemonTypes.FIRE.value)
        t = self.table(hand=0)
        neutral(t.put(fire, P1, 'bench'))
        neutral(t.put(fire, P1, 'bench'))
        neutral(t.put(fire, P2, 'bench'))            # opponent's Fire Pokémon don't count
        await self.play(t, d)
        self.assertEqual(self.hand(t), 4)
        # E: only when it is the last card in hand.
        t = self.table(hand=1)
        self.assertIsNone(self.offer(t, t.put(d, P1, 'hand')))

    async def test_lass_special_counts_benched_basics_only(self):
        d = card('XY10', 103)
        t = self.table()
        neutral(t.put(self.filler, P2, 'bench'))
        neutral(t.put(plain_stage1(), P2, 'bench'))
        await self.play(t, d)
        self.assertEqual(self.hand(t), 4)            # 2 Basics, Stage 1 ignored

    # -- B. coin cards ---------------------------------------------------
    async def test_picnicker_tails_draws_two(self):
        d = card('SVP', 114)
        for heads, want in ((True, 6), (False, 4)):
            t = self.table()
            t.heads = heads
            await self.play(t, d)
            self.assertEqual(self.hand(t), want)

    async def test_professor_birch_tails_draws_four(self):
        d = card('XY5', 134)
        for heads, want in ((True, 7), (False, 4)):
            t = self.table(hand=3)
            t.heads = heads
            await self.play(t, d)
            self.assertEqual((self.hand(t), len(t.zone(P1, 'deck'))), (want, 33 - want))

    async def test_gym_badge_flips_until_tails(self):
        d = card('Promo_XY', 203)
        t = self.table()
        t.heads = seq_heads([True, True, True, False])
        await self.play(t, d)
        self.assertEqual(self.hand(t), 5)
        t = self.table()
        t.heads = False
        await self.play(t, d)
        self.assertEqual(self.hand(t), 2)

    async def test_kahili_draws_then_flips(self):
        d = card('SM8', 179)
        t = self.table()
        t.heads = False
        c = await self.play(t, d)
        self.assertEqual(self.hand(t), 4)
        self.assertIn(c, t.zone(P1, 'discard'))
        t = self.table()
        t.heads = True
        c = await self.play(t, d)
        self.assertEqual(self.hand(t), 5)
        self.assertIn(c, t.zone(P1, 'hand'))
        # E: no deck, no play.
        t = self.table(deck=0)
        self.assertIsNone(self.offer(t, t.put(d, P1, 'hand')))

    async def test_harlequin_split_draws(self):
        d = card('RSV10PT5', 163)
        for heads, mine, theirs in ((True, 5, 3), (False, 3, 5)):
            t = self.table(opp_hand=6)
            t.heads = heads
            await self.play(t, d)
            self.assertEqual((self.hand(t), self.hand(t, P2)), (mine, theirs))
            self.assertEqual(len(t.zone(P2, 'deck')), 36 - theirs)

    async def test_ilima_each_player_flips(self):
        d = card('SM1', 121)
        t = self.table(opp_hand=5)
        t.heads = seq_heads([True, False])
        await self.play(t, d)
        self.assertEqual((self.hand(t), self.hand(t, P2)), (6, 3))
        t = self.table(opp_hand=5)
        t.heads = False
        await self.play(t, d)
        self.assertEqual((self.hand(t), self.hand(t, P2)), (3, 3))
        self.assertEqual(len(t.zone(P1, 'deck')), 29)

    async def test_coin_switch_resolves_one_branch(self):
        d = card('SV4', 174)            # heads: gust the opponent; tails: switch own
        t = self.table()
        t.heads = True
        me, opp = t.me, t.opp
        await self.play(t, d)
        self.assertIs(t.active(P1), me)
        self.assertIs(t.active(P2), t.opp_bench)
        t = self.table()
        t.heads = False
        me, opp = t.me, t.opp
        await self.play(t, d)
        self.assertIs(t.active(P1), t.bench)
        self.assertIs(t.active(P2), opp)

    async def test_coin_damage_counters_either_side(self):
        d = card('SV10', 179)
        t = self.table()
        t.heads = True
        t.pokemon = lambda cands, prompt: t.opp_bench if t.opp_bench in cands else cands[0]
        await self.play(t, d)
        self.assertEqual((t.damage(t.opp_bench), t.damage(t.me)), (20, 0))
        t = self.table()
        t.heads = False
        await self.play(t, d)
        self.assertEqual((t.damage(t.me), t.damage(t.opp), t.damage(t.opp_bench)), (20, 0, 0))

    async def test_coin_search_tails_branch(self):
        d = card('SV4', 165)
        fire = basic_of_type(PokemonTypes.FIRE.value)
        stage1 = plain_stage1()
        for heads, want in ((True, 4), (False, 3)):
            t = self.table()
            t.heads = heads
            t.put(fire, P1, 'deck')
            t.put(stage1, P1, 'deck')
            t.picks = lambda cards, cnt, p, dc: list(cards)[:cnt]
            await self.play(t, d)
            self.assertEqual(self.hand(t), want)

    # -- C. Lucian -------------------------------------------------------
    async def test_lucian_each_player_flips(self):
        d = card('SV06', 157)
        t = self.table(opp_hand=5)
        t.heads = seq_heads([False, True])
        await self.play(t, d)
        self.assertEqual((self.hand(t), self.hand(t, P2)), (3, 6))
        self.assertEqual(len(t.zone(P2, 'deck')), 29)
        # Nobody moved any cards: nobody draws.
        t = self.table(hand=0, opp_hand=0)
        await self.play(t, d)
        self.assertEqual((self.hand(t), self.hand(t, P2)), (0, 0))

    # -- D. Amarys -------------------------------------------------------
    async def test_amarys_draws_and_discards_only_at_end_of_turn(self):
        d = card('SV085', 132)
        t = self.table()
        await self.play(t, d)
        self.assertEqual(self.hand(t), 6)            # hand kept during the turn
        await t.checkup()
        self.assertEqual(self.hand(t), 0)
        self.assertEqual(len(t.zone(P1, 'discard')), 7)   # 6 cards + Amarys
        t = self.table(hand=0)
        await self.play(t, d)
        await t.checkup()
        self.assertEqual(self.hand(t), 4)            # under 5: keep the hand

    # -- E. conditions ---------------------------------------------------
    async def test_pokemon_breeder_needs_deck(self):
        d = card('SL', 63)
        t = self.table(deck=0)
        self.assertIsNone(self.offer(t, t.put(d, P1, 'hand')))
        t = self.table()
        self.assertIsNotNone(self.offer(t, t.put(d, P1, 'hand')))

    async def test_maintenance_needs_two_other_cards(self):
        d = card('TwentiethAnn', 64)
        t = self.table(hand=1)
        self.assertIsNone(self.offer(t, t.put(d, P1, 'hand')))
        t = self.table(hand=2)
        await self.play(t, d)
        self.assertEqual((self.hand(t), len(t.zone(P1, 'deck'))), (1, 31))

    # -- F. Ninja Boy ----------------------------------------------------
    async def test_ninja_boy_swaps_with_deck(self):
        d = card('XY11', 103)
        fire = basic_of_type(PokemonTypes.FIRE.value)
        t = self.table(deck=0)
        set_zone(t, P1, 'deck', 5)
        incoming_card = t.put(fire, P1, 'deck')
        energy = t.energy(t.me, PokemonTypes.WATER)
        t.me.set_attribute(AttrID.HP, t.me.get_attribute(AttrID.HP) - 30)
        old = t.me
        t.pokemon = lambda cands, prompt: old if old in cands else cands[0]
        await self.play(t, d)
        new = t.active(P1)
        self.assertIs(def_for(new.archetype_id), fire)
        self.assertIs(new, incoming_card)
        self.assertIn(old, t.zone(P1, 'deck'))
        self.assertEqual(len(t.zone(P1, 'deck')), 6)
        self.assertIn(energy, list(new.children))
        self.assertEqual(t.damage(new), 30)

    async def test_ninja_boy_no_basic_in_deck_keeps_pokemon(self):
        d = card('XY11', 103)
        t = self.table()
        old = t.me
        await self.play(t, d)
        self.assertIs(t.active(P1), old)
        self.assertEqual(len(t.zone(P1, 'deck')), 30)


if __name__ == '__main__':
    unittest.main()
