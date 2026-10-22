"""Bug hunt 4b (Oct 15): cards whose text refers to other cards' NAMES
('... that have "Ball" in their name', "Colress", "Antique", "Alolan",
"Falinks", "Team Rocket" ...).  Pattern behind the TM Machine report."""
import unittest

from tests.test_untested_trainers import Base
from tests.untested_trainer_kit import neutral
from tests.untested_card_index import card as card_index
from tests.bughunt_table import Table
from spirit.game.attributes import PokemonTypes as T
from spirit.tools.effect_smoke import P1, P2


def take_all(t, seen):
    def picks(cards, count, prompt, shown):
        seen.append(list(cards))
        return list(cards)[:count]
    t.picks = picks


class NamedSearches(Base):
    def table(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        return t

    async def test_ball_guy_three_different_ball_items(self):
        t = self.table()
        card = t.put('SWSH45.BallGuy_57', P1, 'hand')
        ub1, ub2, nest, level = t.deck(P1, [card_index('Ultra Ball'), card_index('Ultra Ball'),
                                            card_index('Nest Ball'), card_index('Level Ball')])
        other = t.deck(P1, [card_index('Switch'), card_index('Energy Search')])
        seen = []
        take_all(t, seen)
        await t.play(card)
        self.assertTrue(seen)
        offered = seen[0]
        for c in other:
            self.assertNotIn(c, offered)
        self.assertEqual(sum(c in offered for c in (ub1, ub2)), 1, 'different names only')
        hand = t.zone(P1, 'hand')
        self.assertEqual(sum(c in hand for c in (ub1, ub2, nest, level)), 3)

    async def test_aether_foundation_employee_only_alolan(self):
        t = self.table()
        card = t.put('SM8.AetherFoundationEmployee_168', P1, 'hand')
        alolan = [t.put(card_index(n), P1, 'discard') for n in
                  ('Alolan Vulpix', 'Alolan Meowth', 'Alolan Rattata')]
        plain = t.put(card_index('Vulpix'), P1, 'discard')
        seen = []
        take_all(t, seen)
        await t.play(card)
        hand = t.zone(P1, 'hand')
        self.assertNotIn(plain, hand)
        self.assertEqual(sum(c in hand for c in alolan), 3)

    async def test_fossil_quarry_only_antique_trainers(self):
        t = self.table()
        stadium = t.stadium('ME5.FossilQuarry_76', P1)
        antiques = t.deck(P1, [card_index('Antique Jaw Fossil'), card_index('Antique Skull Fossil')])
        other = t.deck(P1, [card_index('Unidentified Fossil'), card_index('Switch')])
        seen = []
        take_all(t, seen)
        entry = next(iter(t.offers(stadium, None, P1)), None)
        self.assertIsNotNone(entry, 'Fossil Quarry usable')
        await t.do(entry)
        self.assertTrue(seen)
        for c in other:
            self.assertNotIn(c, seen[0])
        bench = t.zone(P1, 'bench')
        self.assertEqual(sum(c in bench for c in antiques), 2)


class NamedConditions(Base):
    async def test_kyurem_plasma_bane_needs_colress_in_opponents_discard(self):
        for colress in (None, 'CZ.ColresssExperiment_219', card_index('Colress')):
            t = Table(self)
            k = neutral(t.put('SV065.Kyurem_47', P1, 'active'))
            t.energy(k, T.WATER, 1)
            d = neutral(t.put(self.filler, P2, 'active'), hp=400)
            if colress:
                t.put(colress, P2, 'discard')
            offered = t.attack_offer(k, 'Trifrost') is not None
            self.assertEqual(offered, colress is not None, colress)

    async def count_damage(self, ref, title, setup, kind=T.DARKNESS, energy=3):
        t = Table(self)
        a = neutral(t.put(ref, P1, 'active'))
        t.energy(a, kind, energy)
        d = neutral(t.put(self.filler, P2, 'active'), hp=600)
        setup(t, a, d)
        t.picks = lambda cards, count, prompt, shown: list(cards)[:count]
        t.pokemon = lambda cands, prompt: d
        before = t.hp(d)
        await t.attack(a, title)
        return before - t.hp(d)

    async def test_falinks_team_attack_counts_benched_falinks_only(self):
        def setup(t, a, d):
            t.put('SWSH2.Falinks_109', P1, 'bench')
            t.put('SWSH2.Falinks_109', P1, 'bench')
            t.put(self.filler, P1, 'bench')
        self.assertEqual(await self.count_damage('SWSH2.Falinks_109', 'Team Attack', setup, T.FIGHTING), 60)

    async def test_relicanth_counts_benched_antique(self):
        def setup(t, a, d):
            t.put(card_index('Antique Jaw Fossil'), P1, 'bench')
            t.put(self.filler, P1, 'bench')
        dmg = await self.count_damage('ME5.Relicanth_17', 'Fossil Beatdown', setup, T.FIGHTING)
        base = await self.count_damage('ME5.Relicanth_17', 'Fossil Beatdown', lambda *a: None, T.FIGHTING)
        self.assertEqual(dmg - base, 30)

    async def test_team_rockets_weezing_counts_koffing_and_weezing_both_sides(self):
        def setup(t, a, d):
            t.put("SV10.TeamRocketsKoffing_125", P1, 'bench')
            t.put(card_index('Koffing'), P2, 'bench')
            t.put(self.filler, P2, 'bench')
        # itself + TR Koffing + opponent's Koffing = 3 x 40
        self.assertEqual(await self.count_damage('SV10.TeamRocketsWeezing_126',
                                                 'Explode Together Now', setup, T.DARKNESS), 120)

    async def test_r_command_counts_team_rocket_supporters(self):
        def setup(t, a, d):
            t.put('ME2PT5.TeamRocketsPetrel_207', P1, 'discard')
            t.put('SV10.TeamRocketsAriana_171', P1, 'discard')
            t.put(card_index('Iono'), P1, 'discard')
        self.assertEqual(await self.count_damage('SV10.TeamRocketsPorygon2_154',
                                                 'R Command', setup, T.DARKNESS), 40)

    async def test_love_impact_needs_benched_nidoking(self):
        with_king = await self.count_damage(
            'SV10.TeamRocketsNidoqueen_116', 'Love Impact',
            lambda t, a, d: t.put(card_index('Nidoking'), P1, 'bench'), T.DARKNESS)
        without = await self.count_damage(
            'SV10.TeamRocketsNidoqueen_116', 'Love Impact',
            lambda t, a, d: t.put(card_index('Nidorino'), P1, 'bench'), T.DARKNESS)
        self.assertEqual(with_king - without, 120)

    async def test_paldean_tauros_counts_damaged_tauros(self):
        def setup(t, a, d):
            from spirit.game.attributes import AttrID
            a.set_attribute(AttrID.HP, t.hp(a) - 10)
            b = t.put(card_index('Tauros'), P1, 'bench')
            b.set_attribute(AttrID.HP, t.hp(b) - 10)
            t.put(card_index('Tauros'), P1, 'bench')            # undamaged
        self.assertEqual(await self.count_damage('ME2.PaldeanTauros_48', 'Raging Charge',
                                                 setup, T.FIGHTING), 80)


if __name__ == '__main__':
    unittest.main()
