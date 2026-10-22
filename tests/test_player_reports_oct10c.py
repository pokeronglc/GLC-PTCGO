"""Player reports (Oct 10, late): Venonat's Radar Eyes, Trick Shovel's
reveal, Bronzor's Evolutionary Advantage."""
import glob
import unittest
from spirit.game.data_utils import Attack
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import pay_cost
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

HOP = 'CZ.Hop_133'


class Reports(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_radar_eyes_chosen_card_to_hand_rest_stay_in_deck(self):
        t = Table(self)
        venonat = t.put('SM10.Venonat_9', P1, 'active')
        t.put(self.filler, P2, 'active')
        pay_cost(t, venonat, next(a for a in fixtures.definition('SM10.Venonat_9').abilities
                                  if a.title == 'Radar Eyes'))
        wanted = t.deck(P1, [HOP])[0]
        deck_before = len(t.zone(P1, 'deck'))
        shown = []
        t.picks = lambda cards, count, prompt, display: (shown.append(display and len(display)), [wanted])[1]
        await t.attack(venonat, 'Radar Eyes')
        self.assertIn(wanted, t.zone(P1, 'hand'))
        self.assertEqual(len(t.zone(P1, 'deck')), deck_before - 1)
        self.assertEqual(shown, [7])                      # the 7 looked-at cards are shown

    async def test_trick_shovel_shows_card_before_asking(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        order = []
        real_flush = EffectContext.flush_choreography

        async def flush(ctx):
            order.append('show')
            await real_flush(ctx)
        t.yes = lambda prompt: (order.append('ask'), True)[1]
        top = t.deck(P1, [HOP])[0]
        with patch.object(EffectContext, 'flush_choreography', flush), \
                patch.object(EffectContext, 'choose', lambda *a, **k: _zero()):
            await t.play(t.put('XY2.TrickShovel_98', P1, 'hand'))
        self.assertIn('ask', order)
        self.assertLess(order.index('show'), order.index('ask'))
        self.assertIn(top, t.zone(P1, 'discard'))

    async def test_bronzor_evolves_on_turn_two_even_if_played_that_turn(self):
        # TPCi ruling (Ultra Prism FAQ): it needn't be in play at the start of the turn.
        bronzong = sorted(p.split('cards/')[1][:-3].replace('/', '.')
                          for p in glob.glob('spirit/game/scripts/cards/SM9/Bronzong_*.py'))[0]
        for turn, played_this_turn, legal in ((1, False, False), (2, False, True),
                                               (2, True, True), (3, False, True),
                                               (3, True, False)):
            with self.subTest(turn=turn, played_this_turn=played_this_turn):
                t = Table(self)
                t.state.turn_number = turn
                bronzor = t.put('SM9.Bronzor_100', P1, 'active')
                if played_this_turn:
                    t.state.entered_play_turn[bronzor.entity_id] = turn
                t.put(self.filler, P2, 'active')
                card = t.put(bronzong, P1, 'hand')
                self.assertEqual(bool(t.offers(card, 'EvolvePokemonPlayAbility')), legal)


class CresseliaTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _attack(self, yes, revealed_before=0):
        from spirit.game.attributes import AttrID
        t = Table(self)
        t.yes = yes
        cres = t.put('SV065.Cresselia_21', P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        for mon in (cres, opp):
            mon.set_attribute(AttrID.WEAKNESS_TYPES, [])
            mon.set_attribute(AttrID.RESISTANCE_TYPES, [])
        opp.set_attribute(AttrID.HP, 900)
        for prize in t.zone(P1, 'prizes')[:revealed_before]:
            prize.publicly_revealed = True
        pay_cost(t, cres, next(a for a in fixtures.definition('SV065.Cresselia_21').abilities
                               if a.title == 'Crescent Purge'))
        await t.attack(cres, 'Crescent Purge')
        shown = sum(bool(getattr(p, 'publicly_revealed', False)) for p in t.zone(P1, 'prizes'))
        return 900 - t.hp(opp), shown

    async def test_turn_prize_face_up_for_more_damage(self):
        self.assertEqual(await self._attack(True), (160, 1))

    async def test_decline_does_base_damage(self):
        self.assertEqual(await self._attack(False), (80, 0))

    async def test_no_face_down_prizes_left(self):
        self.assertEqual(await self._attack(True, revealed_before=6), (80, 6))


class CoinFlipAttackTests(unittest.IsolatedAsyncioTestCase):
    """Heads-only attack effects: happen on heads, never on tails."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    @staticmethod
    def _atk(spec, title):
        return next(a for a in fixtures.definition(spec).abilities if a.title == title)

    async def _survives(self, spec, title, heads):
        from spirit.game.attributes import AttrID
        t = Table(self)
        t.heads = heads
        me = t.put(spec, P1, 'active')
        opp = t.put('SWSH7.Dialga_112', P2, 'active')
        t.put(self.filler, P1, 'bench')
        t.put(self.filler, P2, 'bench')
        opp.set_attribute(AttrID.HP, 900)
        pay_cost(t, me, self._atk(spec, title))
        pay_cost(t, opp, self._atk('SWSH7.Dialga_112', 'Heavy Impact'))
        await t.attack(me, title)
        t.next_turn()
        await t.attack(opp, 'Heavy Impact', pid=P2)
        return t.active(P1) is me and t.hp(me) == 10

    async def test_bide_and_endure(self):
        for spec, title in (('XY11.Seedot_9', 'Bide'), ('SM7.Meditite_76', 'Bide'),
                            ('SM7.Phanpy_72', 'Endure')):
            with self.subTest(spec):
                self.assertTrue(await self._survives(spec, title, True))
                self.assertFalse(await self._survives(spec, title, False))

    async def test_active_back_to_hand(self):
        for spec, title in (('SM1.Pinsir_6', 'Roof Fling'), ('SV3.Floatzel_49', 'Swirling Tail')):
            for heads in (True, False):
                with self.subTest(spec, heads=heads):
                    t = Table(self)
                    t.heads = heads
                    me = t.put(spec, P1, 'active')
                    opp = t.put(self.filler, P2, 'active')
                    t.put(self.filler, P2, 'bench')
                    pay_cost(t, me, self._atk(spec, title))
                    await t.attack(me, title)
                    self.assertEqual(len(t.zone(P2, 'hand')), 1 if heads else 0)
                    self.assertEqual(t.active(P2) is opp, not heads)

    async def test_heal_only_on_heads(self):
        from spirit.game.attributes import AttrID
        for heads in (True, False):
            t = Table(self)
            t.heads = heads
            me = t.put('SM2.Chansey_101', P1, 'active')
            t.put(self.filler, P2, 'active')
            me.set_attribute(AttrID.HP, t.hp(me) - 40)
            before = t.hp(me)
            pay_cost(t, me, self._atk('SM2.Chansey_101', 'Bind Wound'))
            await t.attack(me, 'Bind Wound')
            self.assertEqual(t.hp(me) - before, 30 if heads else 0)


class BellOfSilenceTests(unittest.IsolatedAsyncioTestCase):
    """Chimecho (SM4) Bell of Silence: the opponent can't play Pokémon with an
    Ability from hand next turn -- evolving included (Silcoon's Multiplying
    Cocoon was the report)."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _offers_after_bell(self, specs, attack=True):
        t = Table(self)
        chime = t.put('SM4.Chimecho_43', P1, 'active')
        t.put(self.filler, P2, 'active')
        t.put('ME2PT5.Wurmple_11', P2, 'bench')
        cards = [t.put(spec, P2, 'hand') for spec in specs]
        if attack:
            pay_cost(t, chime, next(a for a in fixtures.definition('SM4.Chimecho_43').abilities
                                    if a.title == 'Bell of Silence'))
            await t.attack(chime, 'Bell of Silence')
        t.next_turn()
        return [bool(t.offers(card, pid=P2)) for card in cards], t

    async def test_ability_evolution_blocked(self):
        offered, _ = await self._offers_after_bell(['ME2PT5.Silcoon_12', 'SM8.Silcoon_25'])
        self.assertEqual(offered, [False, True])

    async def test_ability_basic_blocked(self):
        offered, _ = await self._offers_after_bell(['ME2PT5.Wurmple_11', 'SM8.Wurmple_23'])
        ability = [any(not isinstance(a, Attack) for a in fixtures.definition(s).abilities)
                   for s in ('ME2PT5.Wurmple_11', 'SM8.Wurmple_23')]
        self.assertEqual(offered, [not a for a in ability])

    async def test_without_bell_evolution_allowed(self):
        offered, _ = await self._offers_after_bell(['ME2PT5.Silcoon_12'], attack=False)
        self.assertEqual(offered, [True])


class AllergyStormTests(unittest.IsolatedAsyncioTestCase):
    """Vileplume (SWSH11) Allergy Storm: heads -> no Supporters next turn,
    tails -> no Items (it used to lock Items on heads and never Supporters)."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _after(self, heads):
        t = Table(self)
        t.heads = heads
        me = t.put('SWSH11.Vileplume_3', P1, 'active')
        t.put(self.filler, P2, 'active')
        item = t.put(self.item, P2, 'hand')
        supporter = t.put('SM1.Hau_120', P2, 'hand')
        pay_cost(t, me, next(a for a in fixtures.definition('SWSH11.Vileplume_3').abilities
                             if a.title == 'Allergy Storm'))
        await t.attack(me, 'Allergy Storm')
        t.next_turn()
        return bool(t.offers(item, pid=P2)), bool(t.offers(supporter, pid=P2))

    async def test_heads_locks_supporters(self):
        self.assertEqual(await self._after(True), (True, False))

    async def test_tails_locks_items(self):
        self.assertEqual(await self._after(False), (False, True))


class CoinFlipAttackTests2(unittest.IsolatedAsyncioTestCase):
    """Coin attacks found by the "if tails" / multi-coin check (Oct 10)."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def go(self, spec, title, seq, damage=0):
        from tests import test_sweep_coins as sc
        from tests.sweep_core import neutral
        from spirit.game.attributes import AttrID, PokemonTypes
        t = Table(self)
        t.heads = sc.coins(seq)
        me = neutral(t.put(spec, P1, 'active'), hp=None)
        if damage:
            me.set_attribute(AttrID.HP, t.hp(me) - damage)
        mb = neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        ob = neutral(t.put(self.filler, P2, 'bench'))
        t.energy(opp, PokemonTypes.WATER, 2)
        for _ in range(4):
            t.put(self.item, P2, 'hand')
        pay_cost(t, me, next(a for a in fixtures.definition(spec).abilities if a.title == title))
        hp = [t.hp(x) for x in (me, mb, opp, ob)]
        hand = len(t.zone(P2, 'hand'))
        await t.attack(me, title)
        live = lambda x: x in t.board.pokemon_in_play(x.owning_player_id)
        return {'dmg': [a - (t.hp(x) if live(x) else 0) for a, x in zip(hp, (me, mb, opp, ob))],
                'opp_hand': len(t.zone(P2, 'hand')) - hand, 'me_active': t.active(P1) is me,
                'conds': set(t.conditions(opp))}

    async def test_hail_tails_does_nothing(self):
        self.assertEqual((await self.go('BW8.Cubchoo_40', 'Hail', [False]))['dmg'], [0, 0, 0, 0])
        self.assertEqual((await self.go('BW8.Cubchoo_40', 'Hail', [True]))['dmg'], [0, 0, 10, 10])

    async def test_mystical_return_tails(self):
        self.assertEqual((await self.go('SV065.Sylveon_22', 'Mystical Return', [False]))['dmg'][3], 0)

    async def test_electric_mischief_per_heads(self):
        for seq, want in (([True] * 3, -3), ([False] * 3, 0), ([True, False, False], -1)):
            self.assertEqual((await self.go('XY7.Rotom_29', 'Electric Mischief', seq))['opp_hand'], want)

    async def test_returning_echo_only_on_tails(self):
        self.assertTrue((await self.go('XY8.Swoobat_72', 'Returning Echo', [True]))['me_active'])
        self.assertFalse((await self.go('XY8.Swoobat_72', 'Returning Echo', [False]))['me_active'])

    async def test_trample_benches(self):
        self.assertEqual((await self.go('SM7.Tyranitar_87', 'Trample', [True] * 4))['dmg'], [0, 60, 120, 60])
        self.assertEqual((await self.go('SM7.Tyranitar_87', 'Trample', [False] * 4))['dmg'], [0, 0, 120, 0])

    async def test_miracle_powder(self):
        self.assertTrue((await self.go('BW8.Amoonguss_13', 'Miracle Powder', [True]))['conds'])
        self.assertFalse((await self.go('BW8.Amoonguss_13', 'Miracle Powder', [False]))['conds'])

    async def test_coin_per_damage_counter(self):
        r = await self.go('XY1.Tauros_100', 'Seething Anger', [True] * 10, damage=60)
        self.assertEqual(r['dmg'][2], 180)

    async def test_fury_cutter_tiers(self):
        for seq, want in (([True] * 3, 50 + 120), ([True, True, False], 50 + 60),
                          ([True, False, False], 50 + 20), ([False] * 3, 50)):
            self.assertEqual((await self.go('SV3.Bisharp_149', 'Fury Cutter', seq))['dmg'][2], want)


class CaptivatingSalsaTests(unittest.IsolatedAsyncioTestCase):
    """Oricorio (SM7 30) Captivating Salsa: the switched-in Pokémon is Burned
    AND Confused (it was only Burned)."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_burned_and_confused(self):
        t = Table(self)
        me = t.put('SM7.Oricorio_30', P1, 'active')
        old = t.put(self.filler, P2, 'active')
        new = t.put(self.filler, P2, 'bench')
        pay_cost(t, me, next(a for a in fixtures.definition('SM7.Oricorio_30').abilities
                             if a.title == 'Captivating Salsa'))
        await t.attack(me, 'Captivating Salsa')
        self.assertIs(t.active(P2), new)
        self.assertEqual(set(t.conditions(new)), {'Burned', 'Confused'})
        self.assertEqual(set(t.conditions(old)), set())


class MultiConditionTests(unittest.IsolatedAsyncioTestCase):
    """"... is now X and Y" applies both conditions (Weezing, Jellicent, Venusaur)."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_thick_liquid_both_actives(self):
        t = Table(self)
        me = t.put('XY10.Weezing_28', P1, 'active')
        opp = t.put(self.filler, P2, 'active')
        pay_cost(t, me, next(a for a in fixtures.definition('XY10.Weezing_28').abilities
                             if a.title == 'Thick Liquid'))
        await t.attack(me, 'Thick Liquid')
        self.assertEqual(set(t.conditions(me)), {'Confused', 'Poisoned'})
        self.assertEqual(set(t.conditions(opp)), {'Confused', 'Poisoned'})

    async def test_spiteful_spirit_on_knock_out(self):
        from spirit.game.attributes import AttrID
        t = Table(self)
        jelly = t.put('BW8.Jellicent_39', P1, 'active')
        t.put(self.filler, P1, 'bench')
        opp = t.put('SWSH7.Dialga_112', P2, 'active')
        t.put(self.filler, P2, 'bench')
        jelly.set_attribute(AttrID.HP, 10)
        pay_cost(t, opp, next(a for a in fixtures.definition('SWSH7.Dialga_112').abilities
                              if a.title == 'Heavy Impact'))
        t.next_turn()
        await t.attack(opp, 'Heavy Impact', pid=P2)
        self.assertEqual(set(t.conditions(opp)), {'Confused', 'Poisoned'})

    async def test_loopy_lasso(self):
        t = Table(self)
        t.heads = True
        me = t.put('PGO.Venusaur_3', P1, 'active')
        t.put(self.filler, P2, 'active')
        new = t.put(self.filler, P2, 'bench')
        entry = t.ability_offer(me, 'Loopy Lasso')
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertIs(t.active(P2), new)
        self.assertEqual(set(t.conditions(new)), {'Asleep', 'Poisoned'})


async def _zero():
    return 0


if __name__ == "__main__":
    unittest.main()
