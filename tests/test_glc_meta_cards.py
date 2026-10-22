"""Scenario checks for meta GLC cards the semantic audit marked for review."""
import unittest
from unittest.mock import AsyncMock

from tests import test_hgss_rules as fixtures
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID
from spirit.game.session.effects import EffectContext
from spirit.game.session.legal_actions import energy_provided_count
from spirit.game.session.passives import compute_damage, effective_supporter_limit
from spirit.tools.effect_smoke import P1, P2


class GlcMetaCardTests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = fixtures.HgssRulesTests.rig
    add = fixtures.HgssRulesTests.add

    def basic_energy(self, rig, kind, zone='hand', pid=P1):
        return self.add(rig, CARD_DEFS_BY_GUID[self.energies[kind.value].lower()], pid, zone)

    # Magnezone PLS 46 -- Dual Brains
    async def test_dual_brains_allows_two_supporters_for_owner_only(self):
        rig, e = self.rig('SV1.Nemona_180', 'trainer')
        self.assertEqual(effective_supporter_limit(rig.board, P1), 1)
        self.add(rig, fixtures.definition('BW8.Magnezone_46'), P1, 'bench')
        self.assertEqual(effective_supporter_limit(rig.board, P1), 2)
        self.assertEqual(effective_supporter_limit(rig.board, P2), 1)
        self.add(rig, fixtures.definition('BW8.Magnezone_46'), P1, 'bench')
        self.assertEqual(effective_supporter_limit(rig.board, P1), 2)

    # Hop's Snorlax JTG 117 -- Extra Helpings
    async def test_extra_helpings_only_hops_pokemon_and_does_not_stack(self):
        rig, e = self.rig('SV09.HopsDubwool_136')
        dubwool = e['target']                       # a Hop's Pokemon
        defender = rig.board.active_pokemon(P2)
        def dmg(attacker):
            return compute_damage(rig.board, attacker, defender, 100,
                                  ignore_weakness=True, ignore_resistance=True).amount
        without = dmg(dubwool)
        self.add(rig, fixtures.definition('SV09.HopsSnorlax_117'), P1, 'bench')
        self.assertEqual(dmg(dubwool), without + 30)
        self.add(rig, fixtures.definition('SV09.HopsSnorlax_117'), P1, 'bench')
        self.assertEqual(dmg(dubwool), without + 30, "Extra Helpings must not stack")
        plain = self.add(rig, fixtures.definition('SV1.Pawmi_74'), P1, 'bench')
        self.assertEqual(dmg(plain), 100, "only Hop's Pokemon get the bonus")
        bench_target = rig.board.find_player_area(P2, 'bench').children[0]
        self.assertEqual(compute_damage(rig.board, dubwool, bench_target, 100,
                                        ignore_weakness=True, ignore_resistance=True).amount,
                         100, "only to the opponent's Active Pokemon")

    # Gardevoir NXD 57 -- Psychic Mirage (and it does not stack)
    async def test_psychic_mirage_doubles_basic_psychic_once(self):
        rig, e = self.rig('BW4.Gardevoir_57')
        gardevoir = e['target']
        energy = self.basic_energy(rig, PokemonTypes.PSYCHIC)
        rig.attach(energy, gardevoir)
        self.assertEqual(energy_provided_count(energy, rig.board), 2)
        self.add(rig, fixtures.definition('BW4.Gardevoir_57'), P1, 'bench')
        self.assertEqual(energy_provided_count(energy, rig.board), 2)
        grass = self.basic_energy(rig, PokemonTypes.GRASS)
        rig.attach(grass, gardevoir)
        self.assertEqual(energy_provided_count(grass, rig.board), 1)
        foe = self.basic_energy(rig, PokemonTypes.PSYCHIC, pid=P2)
        rig.attach(foe, rig.board.active_pokemon(P2))
        self.assertEqual(energy_provided_count(foe, rig.board), 1)

    # Delphox (Chaos Rising 13) -- Flaring Magic
    async def test_flaring_magic_discards_fire_and_draws_to_seven(self):
        path = 'ME4.Delphox_13'
        rig, e = self.rig(path)
        delphox = e['target']
        ability = next(a for a in fixtures.definition(path).abilities if a.title == 'Flaring Magic')
        ctx = EffectContext(rig.session, P1, delphox, ability)
        hand = rig.board.find_player_area(P1, 'hand')
        for card in list(hand.children):
            rig.to_area(card, P1, 'discard')
        fire = self.basic_energy(rig, PokemonTypes.FIRE)
        other = self.basic_energy(rig, PokemonTypes.WATER)
        ctx.choose_cards = AsyncMock(side_effect=lambda cards, n, **kw: list(cards)[:n])
        await ability.effect(ctx)
        self.assertIn(fire, ctx.discard_pile())
        self.assertIn(other, ctx.hand())
        self.assertEqual(len(ctx.hand()), 7)

    # Colress's Tenacity SFA 57
    async def test_colresss_tenacity_takes_what_it_finds(self):
        from spirit.game.attributes import TrainerType
        path = 'SV065.ColresssTenacity_57'
        for with_stadium in (True, False):
            with self.subTest(with_stadium=with_stadium):
                rig, e = self.rig(path, 'trainer')
                ctx = EffectContext(rig.session, P1, e['target'], None)
                deck = rig.board.find_player_area(P1, 'deck')
                for card in [c for c in ctx.deck()
                             if c.get_attribute(AttrID.TRAINER_TYPE) == TrainerType.STADIUM.value]:
                    rig.to_area(card, P1, 'discard')
                stadium = None
                if with_stadium:
                    stadium = self.add(rig, fixtures.definition('SV3.TownStore_196'), P1, 'deck')
                energy = self.basic_energy(rig, PokemonTypes.FIRE, zone='deck')
                wanted = {c.entity_id for c in (stadium, energy) if c is not None}
                async def chooser(pid, src, specs, prompt, **kw):
                    return [[c.entity_id for c in s['cards'] if c.entity_id in wanted][:1]
                            for s in specs]
                rig.session.prompt_card_chooser_groups = chooser
                shuffle = AsyncMock()
                ctx.shuffle_deck = shuffle
                await fixtures.definition(path).effect(ctx)
                self.assertIn(energy, ctx.hand())
                if stadium is not None:
                    self.assertIn(stadium, ctx.hand())
                shuffle.assert_awaited()

    # Night Stretcher SFA 61
    async def test_night_stretcher_returns_pokemon_or_basic_energy(self):
        path = 'SV065.NightStretcher_61'
        rig, e = self.rig(path, 'trainer')
        ctx = EffectContext(rig.session, P1, e['target'], None)
        energy = self.basic_energy(rig, PokemonTypes.GRASS, zone='discard')
        offered = []
        async def choose(cards, n, **kw):
            offered.extend(cards)
            return [energy]
        ctx.choose_cards = choose
        await fixtures.definition(path).effect(ctx)
        self.assertIn(energy, ctx.hand())
        self.assertTrue(any(c is not energy for c in offered))


if __name__ == "__main__":
    unittest.main()
