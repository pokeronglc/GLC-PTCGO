"""Oct 23 player reports: TM: Evolution offered Pokémon with no evolution in
the GLC pool; Slowbro's Strange Behavior and Quagsire's Wash Out needed one
activation per use."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import PokemonTypes as PT, AttrID
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2


class Oct23Reports(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def prompts_seen(self, t):
        seen = []
        base = t._patches

        def patches():
            ps = base()
            inner = ps[0].new

            async def choose_cards(ctx, cards, count, minimum=None, prompt='', *a, **k):
                seen.append((prompt, list(cards), count))
                return await inner(ctx, cards, count, minimum, prompt, *a, **k)
            ps[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
            return ps
        t._patches = patches
        return seen

    async def test_strange_behavior_repeats_in_one_activation(self):
        t = Table(self)
        slowbro = t.put('SV1.Slowbro_43', P1, 'active')
        a = t.put(self.filler, P1, 'bench')
        b = t.put(self.filler, P1, 'bench')
        a.set_attribute(AttrID.HP, a.get_attribute(AttrID.HP) - 30)
        b.set_attribute(AttrID.HP, b.get_attribute(AttrID.HP) - 20)
        t.put(self.filler, P2, 'active')
        order = [a, a, b, None]                 # 3 counters, then Done
        t.pokemon = lambda c, p: order.pop(0) if order and (order[0] is None or order[0] in c) else None
        t.picks = None
        await t.use(slowbro, 'Strange Behavior')
        self.assertEqual(t.damage(slowbro), 30)
        self.assertEqual(t.damage(a), 10)
        self.assertEqual(t.damage(b), 10)
        # Still usable afterwards ("as often as you like").
        self.assertIsNotNone(t.ability_offer(slowbro, 'Strange Behavior'))

    async def test_strange_behavior_stops_when_nothing_is_damaged(self):
        t = Table(self)
        slowbro = t.put('SV1.Slowbro_43', P1, 'active')
        a = t.put(self.filler, P1, 'bench')
        a.set_attribute(AttrID.HP, a.get_attribute(AttrID.HP) - 20)
        t.put(self.filler, P2, 'active')
        t.pokemon = lambda c, p: c[0]           # keeps picking until none left
        await t.use(slowbro, 'Strange Behavior')
        self.assertEqual(t.damage(slowbro), 20)
        self.assertEqual(t.damage(a), 0)

    async def test_wash_out_moves_many_energy_without_asking_for_the_active(self):
        t = Table(self)
        active = t.put(self.filler, P1, 'active')
        quag = t.put('DM.Quagsire_26', P1, 'bench')
        other = t.put(self.filler, P1, 'bench')
        water = t.energy(quag, PT.WATER, 3) + [t.energy(other, PT.WATER, 1)]
        dark = t.energy(other, PT.DARKNESS, 1)
        t.put(self.filler, P2, 'active')
        seen = self.prompts_seen(t)
        t.picks = lambda c, n, p, s: list(c)[:n]
        await t.use(quag, 'Wash Out')
        self.assertTrue(all(e.parent is active for e in water))
        self.assertIs(dark.parent, other)        # only Water Energy
        self.assertEqual(len(seen), 1)           # one pick, no "choose the Active"
        self.assertEqual(seen[0][2], 4)

    async def test_tm_evolution_skips_pokemon_with_no_evolution(self):
        from spirit import config
        with patch.object(config, 'GLC_ONLY', False):
            t = Table(self)
            a = t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            entei = t.put('CZ.Entei_21', P1, 'bench')
            wooper = t.put('DM.Wooper_25', P1, 'bench')
            t.deck(P1, ['DM.Quagsire_26'])
            t.state.turn_number = 5
            t.attach('SV4.TechnicalMachineEvolution_178', a)
            t.energy(a, PT.FIRE, 1)
            await t.session.refresh_granted_abilities(a)
            seen = self.prompts_seen(t)
            await t.attack(a, 'Evolution')
        evolve = [cards for prompt, cards, _ in seen if prompt == 'Choose Pokémon to evolve']
        self.assertTrue(evolve)
        self.assertNotIn(entei, evolve[0])
        self.assertIn(wooper, evolve[0])

if __name__ == '__main__':
    unittest.main()
