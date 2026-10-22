"""Oct 21 player reports (owner list)."""
import unittest
from unittest.mock import patch

from tests.test_untested_trainers import Base
from tests.bughunt_table import Table
from tests.untested_card_index import card as ci
from spirit.tools.effect_smoke import P1, P2
from spirit.game.attributes import PokemonTypes
from spirit.game.session.effects import EffectContext


class Reports(Base):
    async def test_impersonation_lusamine_roots_on_mimikyu_and_can_take_itself(self):
        # Discarding Lusamine for Impersonation must leave it pickable: the
        # discard-pile offer was rooted on Lusamine itself.
        t = Table(self)
        m = t.put('SM12.Mimikyu_96', P1, 'active')
        t.put(self.filler, P2, 'active')
        t.put('SM4.Lusamine_96', P1, 'hand')
        t.state.turn_number = 5
        t.energy(m, PokemonTypes.PSYCHIC, 2)
        roots = []
        base = t._patches

        def patches():
            ps = base()
            inner = ps[0].new

            async def choose_cards(ctx, cards, count, *a, **k):
                roots.append((k.get('prompt') or (a[1] if len(a) > 1 else ''),
                              ctx._offer_source_id, [c.entity_id for c in cards]))
                return await inner(ctx, cards, count, *a, **k)
            ps[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
            return ps
        t._patches = patches
        await t.attack(m, 'Impersonation')
        self.assertTrue(roots)
        self.assertTrue(all(src == m.entity_id for _, src, _ in roots), roots)
        self.assertIn('Lusamine', t.names(t.zone(P1, 'hand')))

    async def test_deduction_kit_shows_the_cards_before_the_choice(self):
        from spirit.game.session.game_session import GameSession
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.deck(P1, [ci('Switch'), ci('Potion'), ci('Nest Ball')])
        order = []

        async def view(session, pid, src, cards, prompt=''):
            order.append(('view', len(cards)))

        async def choose(ctx, prompt, buttons, *a, **k):
            order.append(('choose', prompt))
            return 1
        with patch.object(GameSession, 'prompt_view_cards', view), \
                patch.object(EffectContext, 'choose', choose):
            await t.play(t.put('SV08.DeductionKit_171', P1, 'hand'))
        self.assertEqual([o[0] for o in order][:2], ['view', 'choose'], order)
        self.assertEqual(order[0][1], 3)

    async def test_jumbo_ice_cream_counts_wild_growth(self):
        t = Table(self)
        a = t.put(ci('Bulbasaur'), P1, 'active', hp=10)
        t.put('ME1.Meganium_10', P1, 'bench')
        t.put(self.filler, P2, 'active')
        t.energy(a, PokemonTypes.GRASS, 2)
        ice = t.put('ME2.JumboIceCream_91', P1, 'hand')
        self.assertTrue(t.can(ice, 'UseTrainerCard'))

    async def test_jumbo_ice_cream_still_needs_three(self):
        t = Table(self)
        a = t.put(ci('Bulbasaur'), P1, 'active', hp=10)
        t.put(self.filler, P2, 'active')
        t.energy(a, PokemonTypes.GRASS, 2)
        ice = t.put('ME2.JumboIceCream_91', P1, 'hand')
        self.assertFalse(t.can(ice, 'UseTrainerCard'))

    async def test_mulligans_are_revealed_after_placement(self):
        t = Table(self)
        s = t.session
        order = []

        def mk(name):
            async def f(*a, **k):
                order.append(name)
            return f
        s._pending_mulligan_reveal = {P1: [], P2: [{'x': {}}]}
        s._pending_mulligan_counts = None
        with patch.object(s, '_run_active_placement', mk('active')), \
                patch.object(s, '_run_bench_placement', mk('bench')), \
                patch.object(s, '_reveal_mulligans', mk('reveal')), \
                patch.object(s, '_introduce_initial_pokemon', mk('intro')), \
                patch.object(s, '_deal_prize_cards', mk('prizes')):
            await s.run_placement_phase()
        self.assertEqual(order, ['active', 'active', 'bench', 'bench', 'reveal', 'intro', 'prizes'])


    async def test_foul_play_psyspear_counts_foul_plays_cost(self):
        # Owner ruling (Oct 21): "2 extra Energy in addition to this attack's
        # cost" on a copied attack counts against Foul Play's cost (CCC).
        from spirit.game.attributes import AttrID
        t = Table(self)
        z = t.put('RSV10PT5.Zoroark_62', P1, 'active')
        t.put('ME4.Deoxys_32', P2, 'active')
        b = t.put(self.filler, P2, 'bench', hp=300)
        t.state.turn_number = 5
        t.attach('RSV10PT5.IgnitionEnergy_86', z)
        t.energy(z, PokemonTypes.DARKNESS, 2)
        t.pokemon = lambda c, p: b if b in c else c[0]
        await t.attack(z, 'Foul Play')
        self.assertEqual(b.get_attribute(AttrID.HP), 180)

    async def test_foul_play_psyspear_without_extra_energy(self):
        from spirit.game.attributes import AttrID
        t = Table(self)
        z = t.put('RSV10PT5.Zoroark_62', P1, 'active')
        t.put('ME4.Deoxys_32', P2, 'active')
        b = t.put(self.filler, P2, 'bench', hp=300)
        t.state.turn_number = 5
        t.energy(z, PokemonTypes.DARKNESS, 4)
        t.pokemon = lambda c, p: b if b in c else c[0]
        await t.attack(z, 'Foul Play')
        self.assertEqual(b.get_attribute(AttrID.HP), 300)


    async def test_doll_in_hand_is_not_dragged_as_an_item(self):
        # Owner report (Oct 21): Poké Doll / Robo Substitute dropped on the
        # board froze mid-board. The client picks the Item drag handler when
        # TRAINER_TYPE has a value, so it must be empty in the hand and in play.
        from spirit.game.attributes import AttrID, CardType
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        for ref in ('SM12.LilliesPokDoll_197', 'XY4.RoboSubstituteTeamFlareGear_102'):
            doll = t.put(ref, P1, 'hand')

            def attr(card, aid):
                for a in card.serialize_attributes():
                    if a['name'] == aid.value:
                        return a['value']
                return 'absent'
            self.assertEqual(attr(doll, AttrID.CARD_TYPE), CardType.POKEMON.value, ref)
            self.assertIsNone(attr(doll, AttrID.TRAINER_TYPE), ref)
            # Rules side keeps the printed Item type.
            self.assertIsNotNone(doll.get_attribute(AttrID.TRAINER_TYPE), ref)
            # Back to a Trainer in the discard pile.
            t.board.move_card(doll.entity_id, t.board.find_player_area(P1, 'discard').entity_id)
            self.assertIsNotNone(attr(doll, AttrID.TRAINER_TYPE), ref)
            msgs = t.session._fossil_type_msgs(doll, CardType.TRAINER.value)
            self.assertEqual(msgs[1]['value']['attribute']['value'],
                             doll.get_attribute(AttrID.TRAINER_TYPE))


    async def test_discard_to_draw_abilities_always_draw(self):
        # Cinccino Make Do asked "Draw 2 cards?" after the discard; "No"
        # thinned the hand for free. Discarding is the cost; the draw is not
        # optional. Same for Gardevoir / Kirlia Refinement.
        for ref, title in (('SWSH1.Cinccino_147', 'Make Do'),
                           ('SWSH12.Gardevoir_69', 'Refinement')):
            t = Table(self)
            t.put(self.filler, P1, 'active')
            t.put(self.filler, P2, 'active')
            p = t.put(ref, P1, 'bench')
            t.put(ci('Switch'), P1, 'hand')
            t.deck(P1, [ci('Potion')] * 6)
            t.yes = False
            before = len(t.zone(P1, 'deck'))
            await t.use(p, title)
            self.assertEqual(before - len(t.zone(P1, 'deck')), 2, ref)
            self.assertFalse([x for x in t.prompts if 'Draw' in x], t.prompts)


if __name__ == '__main__':
    unittest.main()
