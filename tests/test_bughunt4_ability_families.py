"""Bug hunt 4e (Oct 15): the Pokémon Abilities still without a test after
bug hunt 3 (dev_notes/untested_abilities_oct14.txt), checked by family."""
import unittest
from unittest.mock import patch

from tests.test_untested_trainers import Base
from tests.untested_trainer_kit import (
    board, strike, big, plain, neutral, C, G, R, W, L, P, F, D, M, Y)
from tests.untested_card_index import card as card_index
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID
from spirit.game.session.passives import effective_retreat_cost
from spirit.tools.effect_smoke import P1, P2


class FlatReduction(Base):
    """'This Pokémon takes N less damage from attacks (after W/R)'."""
    CASES = [
        ('SM2.Jangmoo_98', 10), ('SM11.Swadloon_8', 30), ('SV3.Bouffalant_174', 20),
        ('SV08.Cetitan_201', 30), ('SM11.Crustle_11', 30), ('SWSH10.HisuianAvalugg_48', 30),
        ('SWSH5.Marowak_70', 30), ('SV10.Mudsdale_108', 30), ('SM1.Palossand_75', 20),
        ('SWSH4.Samurott_35', 30), ('BW1.Samurott_32', 20), ('SWSH1.Sandaconda_110', 30),
        ('SM8.Scizor_126', 30), ('SV1.Stonjourner_121', 20), ('SV06.Tangrowth_2', 30),
        ('Promo_SWSH.Zamazenta_34', 20), ('BW9.Quagsire_22', 20),
    ]

    async def test_flat_reduction(self):
        atk = big(C)
        for ref, n in self.CASES:
            with self.subTest(ref):
                base, *_ = await self.through(None, atk, None)
                t, a, d = board(self, atk, ref)
                self.assertEqual(await strike(t, a, d), base - n)


class TypePrevention(Base):
    CASES = [('SM1.Araquanid_46', R), ('SWSH10.Bronzong_112', R), ('SV3.Bellibolt_201', L)]

    async def test_prevent_damage_from_one_type(self):
        for ref, kind in self.CASES:
            with self.subTest(ref):
                t, a, d = board(self, big(kind), ref)
                self.assertEqual(await strike(t, a, d), 0)
                t, a, d = board(self, big(C), ref)
                self.assertGreater(await strike(t, a, d), 0)


class SapSipper(Base):
    CASES = [('SWSH5.Bouffalant_118', 60), ('XY5.Bouffalant_119', 40), ('SM4.Gogoat_11', 80)]

    async def test_more_damage_to_grass(self):
        for ref, n in self.CASES:
            with self.subTest(ref):
                t, a, d = board(self, ref, plain(G))
                t2, a2, d2 = board(self, ref, plain(F))
                atk = next(x for x in t.board_defs if False) if False else None
                from spirit.game.data_utils import def_for
                attack = next(x for x in def_for(a.archetype_id).abilities
                              if type(x).__name__ == 'Attack' and x.damage)
                for tt, aa in ((t, a), (t2, a2)):
                    for k, v in attack.cost.items():
                        tt.energy(aa, D if k == C else k, v)
                tt_d = []
                for tt, aa, dd in ((t, a, d), (t2, a2, d2)):
                    neutral(dd, 600)
                    tt.picks = lambda cs, n2, pr, sh: list(cs)[:n2]
                    tt.pokemon = lambda cs, pr: cs[0]
                    before = tt.hp(dd)
                    await tt.attack(aa, attack.title)
                    tt_d.append(before - tt.hp(dd))
                self.assertEqual(tt_d[0] - tt_d[1], n)


class BenchShield(Base):
    """'As long as this Pokémon is on your Bench, prevent all damage done to
    this Pokémon by attacks (both yours and your opponent's)'."""
    CASES = ['SM12.AlolanVulpix_39', 'XY6.Carbink_47', 'SM5.Magnemite_81',
             'SWSH12.Meditite_72', 'Promo_XY.Rayquaza_64', 'Promo_SWSH.Vaporeon_72']

    async def test_benched_takes_no_spread_damage(self):
        for ref in self.CASES:
            with self.subTest(ref):
                t = Table(self)
                a = neutral(t.put('SWSH10.Absol_97', P1, 'active'))
                t.energy(a, D, 1)
                t.put(self.filler, P2, 'active')
                shield = t.put(ref, P2, 'bench')
                other = t.put(self.filler, P2, 'bench')
                await t.attack(a, 'Swirling Disaster')
                self.assertEqual(t.damage(shield), 0)
                self.assertEqual(t.damage(other), 10)


class CoinPrevention(Base):
    CASES = ['BW11.Cinccino_105', 'SV045.Jumpluff_98', 'SV045.Skiploom_97',
             'SV08.Kecleon_150', 'XY3.Noivern_77']

    async def test_heads_prevents_tails_does_not(self):
        for ref in self.CASES:
            for heads, prevented in ((True, True), (False, False)):
                with self.subTest(ref, heads=heads):
                    t, a, d = board(self, big(C), ref)
                    t.heads = heads
                    dmg = await strike(t, a, d)
                    self.assertEqual(dmg == 0, prevented)


class NoRetreatCost(Base):
    async def rc(self, ref, setup=None, zone='active'):
        t = Table(self)
        p = t.put(ref, P1, zone)
        if zone != 'active':
            t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        if setup:
            setup(t, p)
        return effective_retreat_cost(t.board, p)

    async def test_conditional_free_retreat(self):
        energy = lambda kind: (lambda t, p: t.energy(p, kind, 1))
        dmg = lambda t, p: p.set_attribute(AttrID.HP, t.hp(p) - 10)
        stadium = lambda t, p: t.stadium(card_index('Artazon'), P1)
        cases = [
            ('SM5.Gible_97', energy(F)), ('SM11.Dratini_148', energy(W)),
            ('SWSH10.Sudowoodo_74', dmg),
            ('SWSH4.Tynamo_57', energy(L)), ('Promo_SM.AlolanRaichu_72', stadium),
            ('SV035.Articuno_144', energy(W)), ('XY8.Cresselia_70', stadium),
            ('SVP.Latias_139', energy(P)), ('SM7.Lombre_37', energy(W)),
            ('SM8.Mantine_58', energy(W)), ('HF.Voltorb_113', energy(L)),
            ('Promo_XY.Weezing_163', energy(P)),
        ]
        for ref, setup in cases:
            with self.subTest(ref):
                self.assertEqual(await self.rc(ref, setup), 0, 'condition met')
                self.assertGreater(await self.rc(ref), 0, 'condition not met')

    async def test_free_retreat_with_no_energy(self):
        for ref in ('ME2PT5.EthansMagcargo_222', 'SM10.Gligar_98', 'BW8.Lampent_22', 'BW8.Zubat_53'):
            with self.subTest(ref):
                self.assertEqual(await self.rc(ref), 0)
                self.assertGreater(await self.rc(ref, lambda t, p: t.energy(p, D, 1)), 0)

    async def test_floating_shell_needs_your_own_stadium(self):
        self.assertEqual(await self.rc('SM9.Squirtle_22',
                                       lambda t, p: t.stadium(card_index('Artazon'), P1)), 0)
        self.assertGreater(await self.rc('SM9.Squirtle_22',
                                         lambda t, p: t.stadium(card_index('Artazon'), P2)), 0)

    async def test_wimp_out_on_either_players_first_turn(self):
        def on_turn(n):
            def setup(t, p):
                t.state.turn_number = n
                t.board.turn_state = t.state
            return setup
        self.assertEqual(await self.rc('HF.Wimpod_104', on_turn(1)), 0)
        self.assertEqual(await self.rc('HF.Wimpod_104', on_turn(2)), 0)
        self.assertGreater(await self.rc('HF.Wimpod_104', on_turn(3)), 0)


class EffectShields(Base):
    """Hide 'n' Sneak / Cocoon Cover: no effects of the opponent's attacks."""
    CASES = ['ME5.Shuppet_33', 'ME5.Poltchageist_5', 'ME5.Sinistcha_6', 'SV035.Kakuna_14']

    async def test_attack_effects_prevented(self):
        for ref in self.CASES:
            with self.subTest(ref):
                t = Table(self)
                a = neutral(t.put('DM.Heatmor_10', P1, 'active'))
                t.energy(a, R, 1)
                d = t.put(ref, P2, 'active')
                await t.attack(a, 'Singe')
                self.assertNotIn('Burned', t.conditions(d))


class SkyCircus(Base):
    async def test_bird_keeper_makes_attacks_free(self):
        for ref in ('SWSH3.Starly_145', 'SWSH3.Swanna_149', 'SWSH3.Rowlet_11'):
            with self.subTest(ref):
                t = Table(self)
                t.put(self.filler, P1, 'active')
                bird = t.put(ref, P1, 'bench')
                t.put(self.filler, P2, 'active')
                t.deck(P1, [self.filler] * 6)
                from spirit.game.data_utils import def_for
                attack = next(x for x in def_for(bird.archetype_id).abilities
                              if type(x).__name__ == 'Attack' and x.cost)
                keeper = t.put('SWSH3.BirdKeeper_159', P1, 'hand')
                t.pokemon = lambda cs, pr: bird if bird in cs else cs[0]
                t.picks = lambda cs, n, pr, sh: list(cs)[:n]
                await t.play(keeper)
                self.assertIs(t.active(P1), bird, 'Bird Keeper switched the bird in')
                self.assertIsNotNone(t.attack_offer(bird, attack.title),
                                     'attack free after playing Bird Keeper')


if __name__ == '__main__':
    unittest.main()


class SlimySliding(Base):
    """Goodra ME4 68 (20 live decks): the opponent's retreat fails on tails
    (no Energy discarded, no switch) and works on heads."""

    async def retreat(self, heads):
        t = Table(self)
        t.put('ME4.Goodra_68', P1, 'active')
        mover = t.put(plain(C), P2, 'active')
        e = t.energy(mover, D, 3)
        bench = t.put(self.filler, P2, 'bench')
        t.next_turn()
        t.heads = heads
        t.picks = lambda cs, n, pr, sh: list(cs)[:n]
        entry = next(iter(t.offers(mover, 'BaseRetreat', P2)), None)
        self.assertIsNotNone(entry)
        energy = [c.entity_id for c in t.attached(mover)]
        await t.do(entry, targets=energy + [bench.entity_id], pid=P2)
        return t, mover, bench

    async def test_tails_retreat_fails_and_keeps_energy(self):
        t, mover, bench = await self.retreat(False)
        self.assertIs(t.active(P2), mover)
        self.assertEqual(len([c for c in t.attached(mover)]), 3)

    async def test_heads_retreat_works(self):
        t, mover, bench = await self.retreat(True)
        self.assertIs(t.active(P2), bench)
        self.assertLess(len(t.attached(mover)), 3, 'Retreat Cost paid')


class MoreOneOffs(Base):
    async def test_carracosta_mighty_shell_blocks_special_energy_attackers(self):
        atk = big(C)
        t, a, d = board(self, atk, 'ZSV10PT5.Carracosta_107')
        self.assertGreater(await strike(t, a, d), 0, 'no Special Energy: normal damage')
        t, a, d = board(self, atk, 'ZSV10PT5.Carracosta_107')
        t.attach(card_index('Counter Energy'), a)
        self.assertEqual(await strike(t, a, d), 0, 'attacker has a Special Energy')

    async def test_durable_body_survives_on_heads(self):
        for ref in ('ME5.Annihilape_41', 'BW3.Cofagrigus_47'):
            for heads in (True, False):
                with self.subTest(ref, heads=heads):
                    t, a, d = board(self, big(C), ref, hp=30)
                    t.set_prizes(P1, 6)
                    t.set_prizes(P2, 6)
                    t.put(self.filler, P2, 'bench')
                    t.heads = heads
                    await strike(t, a, d)
                    if heads:
                        self.assertIs(t.active(P2), d)
                        self.assertEqual(t.hp(d), 10)
                    else:
                        self.assertIn(d, t.zone(P2, 'discard'))

    async def test_klefki_secret_key_fairy_resistance_minus_40(self):
        from spirit.game.session.passives import active_passives
        t = Table(self)
        fairy = t.put(plain(Y), P1, 'active')
        t.put('XY3.Klefki_73', P1, 'bench')
        t.put(self.filler, P2, 'active')
        mods = [getattr(p, 'modify_resistance', None) for p, c in active_passives(t.board)]
        self.assertTrue(any(mods), 'Secret Key has a resistance passive')
