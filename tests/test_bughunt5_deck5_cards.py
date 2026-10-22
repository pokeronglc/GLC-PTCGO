"""Bug hunt round 5, deck 5 (Fossils): Archen SIT 146, Archeops SIT 147,
Minccino LTR 104, Aerodactyl TEU 130, Miriam SVI 179, Fossil Excavation Map
FLI 107, Pokemon Communication TEU 152, Stadium Nav UNM 208, Unidentified
Fossil SIT 165, Sparkling Robe FFI 99 -- checked against their printed text,
including the should-NOT-work cases."""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table, ASLEEP, CONFUSED, POISONED
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

P, W = PokemonTypes.PSYCHIC, PokemonTypes.WATER
ARCHEN, ARCHEOPS = 'SWSH12.Archen_146', 'SWSH12.Archeops_147'
MINCCINO, AERODACTYL = 'BW11.Minccino_104', 'SM9.Aerodactyl_130'
MIRIAM, MAP = 'SV1.Miriam_179', 'SM6.FossilExcavationMap_107'
COMMUNICATION, NAV = 'SM9.PokmonCommunication_152', 'SM11.StadiumNav_208'
FOSSIL, ROBE = 'SWSH12.UnidentifiedFossil_165', 'XY3.SparklingRobe_99'
MISMAGIUS, GOLETT = 'SM10.Mismagius_78', 'SM12.Golett_89'
JUBILIFE = 'SWSH10.JubilifeVillage_148'
ARTAZON = 'SV2.Artazon_171'
RAINBOW, DRAW_E = 'SM7.RainbowEnergy_151', 'SM12.DrawEnergy_209'


class Bughunt5Deck5(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def table(self):
        t = Table(self)
        self.opp = t.put(self.filler, P2, 'active')
        self.big(self.opp)
        return t

    @staticmethod
    def big(p, hp=400):
        p.set_attribute(AttrID.WEAKNESS_TYPES, [])
        p.set_attribute(AttrID.RESISTANCE_TYPES, [])
        p.set_attribute(AttrID.HP, hp)

    def name(self, card):
        return def_for(card.archetype_id).display_name

    def dealt(self, t, p):
        return 400 - t.hp(p)

    def bench_fossil(self, t, pid=P1, played_turn=0):
        """An Unidentified Fossil already on the Bench (as if played earlier)."""
        f = t.put(FOSSIL, pid, 'hand')
        t.board.move_card(f.entity_id, t.board.find_player_area(pid, 'bench').entity_id)
        t.state.entered_play_turn[f.entity_id] = played_turn
        return f

    def opp_attacker(self, t, spec):
        old = t.active(P2)
        mon = t.put(spec, P2, 'bench')
        t.board.move_card(old.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(mon.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        return mon

    async def test_set_codes(self):
        for path, code in ((ARCHEN, 'SWSH12'), (ARCHEOPS, 'SWSH12'), (MINCCINO, 'BW11'),
                           (AERODACTYL, 'SM9'), (MIRIAM, 'SV1'), (MAP, 'SM6'),
                           (COMMUNICATION, 'SM9'), (NAV, 'SM11'), (FOSSIL, 'SWSH12'),
                           (ROBE, 'XY3')):
            self.assertEqual(fixtures.definition(path).set_code, code, path)

    # --- Unidentified Fossil (SIT 165) ------------------------------------
    async def test_fossil_benches_as_60hp_basic_colorless(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = t.put(FOSSIL, P1, 'hand')
        await t.play(f)
        self.assertIn(f, t.zone(P1, 'bench'))
        self.assertEqual(t.hp(f), 60)
        self.assertEqual(f.get_attribute(AttrID.STAGE), 0)

    async def test_fossil_cannot_retreat(self):
        t = self.table()
        f = t.put(FOSSIL, P1, 'hand')
        t.board.move_card(f.entity_id, t.board.find_player_area(P1, 'activePokemonArea').entity_id)
        t.put(self.filler, P1, 'bench')
        self.assertFalse(t.offers(f, 'RetreatPokemon') or t.offers(f, 'Retreat'))
        actions = {e['selectableAction']['description'] for e in t.offers(f)}
        self.assertFalse(any('Retreat' in a for a in actions), actions)

    async def test_fossil_discard_from_play_takes_attachments(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = self.bench_fossil(t)
        e = t.energy(f, W)
        entry = t.ability_offer(f, 'Discard')
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertIn(f, t.zone(P1, 'discard'))
        self.assertIn(e, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P2, 'prizes')), 6)   # not a Knock Out

    async def test_fossil_is_an_item_in_hand(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = t.put(FOSSIL, P1, 'hand')
        t.put('XY1.Trevenant_55', P2, 'bench')
        # Opponent's Forest's Curse (Active) locks Items: the fossil can't be played.
        tre = t.zone(P2, 'bench')[-1]
        t.board.move_card(self.opp.entity_id, t.board.find_player_area(P2, 'bench').entity_id)
        t.board.move_card(tre.entity_id, t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        self.assertFalse(t.offers(f, None))

    # --- Archen (SIT 146) / Aerodactyl evolve from Unidentified Fossil ----
    async def test_archen_evolves_from_benched_fossil(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = self.bench_fossil(t)
        archen = t.put(ARCHEN, P1, 'hand')
        entry = t.ability_offer(f, 'Evolve')
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertIs(f.parent, archen)
        self.assertIn(archen, t.zone(P1, 'bench'))
        self.assertEqual(t.hp(archen), 80)

    async def test_archen_not_onto_fossil_played_this_turn(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = t.put(FOSSIL, P1, 'hand')
        await t.play(f)
        archen = t.put(ARCHEN, P1, 'hand')
        self.assertIsNone(t.ability_offer(f, 'Evolve'))
        self.assertNotIn(f.entity_id, t.targets(archen, 'EvolvePokemonPlayAbility'))

    async def test_aerodactyl_drag_evolves_onto_fossil(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = self.bench_fossil(t)
        aero = t.put(AERODACTYL, P1, 'hand')
        entry = t.ability_offer(f, 'Evolve')
        self.assertIsNotNone(entry)
        await t.do(entry)
        self.assertIs(f.parent, aero)

    # --- Archeops (SIT 147): Primal Turbo ---------------------------------
    async def test_primal_turbo_two_special_energy_to_one_pokemon(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        ops = t.put(ARCHEOPS, P1, 'bench')
        target = t.put(self.filler, P1, 'bench')
        specials = t.deck(P1, [RAINBOW, DRAW_E, RAINBOW])
        basic = t.put(t.basic_energy(W), P1, 'deck')
        t.pokemon = lambda cands, pr: target
        await t.use(ops, 'Primal Turbo')
        att = t.attached(target)
        self.assertEqual(len(att), 2)
        self.assertTrue(all(c in specials for c in att))
        self.assertIn(basic, t.zone(P1, 'deck'))
        self.assertIsNone(t.ability_offer(ops, 'Primal Turbo'))   # once per turn

    async def test_primal_turbo_ignores_basic_energy(self):
        t = self.table()
        ops = t.put(ARCHEOPS, P1, 'active')
        basic = t.put(t.basic_energy(W), P1, 'deck')
        t.picks = lambda cards, n, pr, d: list(cards)[:n]
        offer = t.ability_offer(ops, 'Primal Turbo')
        if offer is not None:
            await t.do(offer)
        self.assertEqual(t.attached(ops), [])
        self.assertIn(basic, t.zone(P1, 'deck'))

    # --- Minccino (LTR 104): Call for Family ------------------------------
    async def test_call_for_family_benches_a_basic(self):
        t = self.table()
        m = t.put(MINCCINO, P1, 'active')
        t.energy(m, W)
        g = t.deck(P1, [GOLETT])[0]
        await t.attack(m, 'Call for Family')
        self.assertEqual(t.zone(P1, 'bench'), [g])

    async def test_call_for_family_cannot_fetch_fossil_or_evolution(self):
        t = self.table()
        m = t.put(MINCCINO, P1, 'active')
        t.energy(m, W)
        t.deck(P1, [FOSSIL, ARCHEN, ARCHEOPS])
        t.picks = lambda cards, n, pr, d: list(cards)[:n]
        await t.attack(m, 'Call for Family')
        self.assertEqual(t.zone(P1, 'bench'), [])

    # --- Aerodactyl (TEU 130): Supersonic / Fossil Fangs ------------------
    async def test_supersonic_confuses(self):
        t = self.table()
        a = t.put(AERODACTYL, P1, 'active')
        t.energy(a, W)
        await t.attack(a, 'Supersonic')
        self.assertIn(CONFUSED, t.conditions(self.opp))
        self.assertEqual(self.dealt(t, self.opp), 0)

    async def test_fossil_fangs_no_gx_ex_on_bench(self):
        t = self.table()
        a = t.put(AERODACTYL, P1, 'active')
        t.energy(a, W, 3)
        t.put(self.filler, P1, 'bench')
        await t.attack(a, 'Fossil Fangs')
        self.assertEqual(self.dealt(t, self.opp), 180)

    async def test_fossil_fangs_with_gx_on_bench(self):
        t = self.table()
        a = t.put(AERODACTYL, P1, 'active')
        t.energy(a, W, 3)
        gx = t.put(self.filler, P1, 'bench')
        from spirit.game.card_effects import attack_state_clauses as asc
        real = asc.subtypes_for

        def fake(arch):
            return ['Basic', 'GX'] if arch == gx.archetype_id else real(arch)
        with patch.object(asc, 'subtypes_for', fake):
            await t.attack(a, 'Fossil Fangs')
        self.assertEqual(self.dealt(t, self.opp), 90)

    # --- Miriam (SVI 179) -------------------------------------------------
    # FIXED (was BUG): Miriam lets you shuffle only 1 Pokemon (count parsed as 1) and never draws 3.
    async def test_miriam_shuffles_up_to_five_pokemon_and_draws_three(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mons = [t.put(GOLETT, P1, 'discard') for _ in range(6)]
        energy = t.put(t.basic_energy(W), P1, 'discard')
        card = t.put(MIRIAM, P1, 'hand')
        await t.play(card)
        back = [m for m in mons if m in t.zone(P1, 'deck') or m in t.zone(P1, 'hand')]
        self.assertEqual(len(back), 5)
        self.assertIn(energy, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    # FIXED (was BUG): Miriam never draws 3 cards after shuffling (handler returns early).
    async def test_miriam_one_pokemon_still_draws_three(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        mon = t.put(GOLETT, P1, 'discard')
        card = t.put(MIRIAM, P1, 'hand')
        await t.play(card)
        self.assertNotIn(mon, t.zone(P1, 'discard'))
        self.assertEqual(len(t.zone(P1, 'hand')), 3)

    async def test_miriam_no_pokemon_in_discard_no_draw(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.put(t.basic_energy(W), P1, 'discard')
        card = t.put(MIRIAM, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertEqual([c for c in t.zone(P1, 'hand') if c is not card], [])

    # --- Fossil Excavation Map (FLI 107) ----------------------------------
    async def _map(self, t, option):
        async def choose(ctx, prompt, buttons, *a, **k):
            t.prompts.append(prompt)
            return option
        card = t.put(MAP, P1, 'hand')
        with patch.object(EffectContext, 'choose', choose):
            await t.play(card)
        return card

    async def test_map_searches_deck_for_fossil(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = t.deck(P1, [FOSSIL])[0]
        await self._map(t, 0)
        self.assertIn(f, t.zone(P1, 'hand'))

    async def test_map_takes_fossil_from_discard(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        f = t.put(FOSSIL, P1, 'discard')
        deck_f = t.deck(P1, [FOSSIL])[0]
        await self._map(t, 1)
        self.assertIn(f, t.zone(P1, 'hand'))
        self.assertIn(deck_f, t.zone(P1, 'deck'))

    async def test_map_does_not_find_other_cards(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        a = t.deck(P1, [ARCHEN])[0]
        t.picks = lambda cards, n, pr, d: list(cards)[:n]
        card = t.put(MAP, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            async def choose(ctx, prompt, buttons, *a_, **k):
                return 0
            with patch.object(EffectContext, 'choose', choose):
                await t.play(card)
        self.assertIn(a, t.zone(P1, 'deck'))
        self.assertNotIn(a, t.zone(P1, 'hand'))

    # --- Pokemon Communication (TEU 152) ----------------------------------
    async def test_communication_swaps_pokemon(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        give = t.put(GOLETT, P1, 'hand')
        want = t.deck(P1, [ARCHEOPS])[0]
        calls = []

        def picks(cards, n, pr, d):
            calls.append(pr)
            if len(calls) == 1:
                return [give]
            return [want] if want in cards else list(cards)[:n]
        t.picks = picks
        card = t.put(COMMUNICATION, P1, 'hand')
        await t.play(card)
        self.assertIn(want, t.zone(P1, 'hand'))
        self.assertIn(give, t.zone(P1, 'deck'))

    async def test_communication_needs_pokemon_in_hand(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        t.deck(P1, [ARCHEOPS])
        t.put(FOSSIL, P1, 'hand')       # a fossil in hand is an Item, not a Pokemon
        card = t.put(COMMUNICATION, P1, 'hand')
        if t.can(card, 'UseTrainerCard'):
            await t.play(card)
        self.assertFalse(any(self.name(c) == 'Archeops' for c in t.zone(P1, 'hand')))

    # --- Stadium Nav (UNM 208) --------------------------------------------
    async def test_stadium_nav_two_heads_two_stadiums(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        st = t.deck(P1, [JUBILIFE, ARTAZON, JUBILIFE])
        t.heads = True
        card = t.put(NAV, P1, 'hand')
        await t.play(card)
        got = [c for c in t.zone(P1, 'hand') if c in st]
        self.assertEqual(len(got), 2)

    async def test_stadium_nav_one_heads_one_stadium(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        st = t.deck(P1, [JUBILIFE, ARTAZON])
        flips = iter([True, False])
        t.heads = lambda title: next(flips)
        card = t.put(NAV, P1, 'hand')
        await t.play(card)
        self.assertEqual(len([c for c in t.zone(P1, 'hand') if c in st]), 1)

    async def test_stadium_nav_tails_nothing(self):
        t = self.table()
        t.put(self.filler, P1, 'active')
        st = t.deck(P1, [JUBILIFE, ARTAZON])
        t.heads = False
        card = t.put(NAV, P1, 'hand')
        await t.play(card)
        self.assertFalse([c for c in t.zone(P1, 'hand') if c in st])

    # --- Sparkling Robe (FFI 99) ------------------------------------------
    async def test_robe_removes_and_blocks_special_conditions(self):
        t = self.table()
        mon = t.put(self.filler, P1, 'active')
        self.big(mon)
        mon.set_attribute(AttrID.SPECIAL_CONDITIONS, [POISONED])
        robe = t.put(ROBE, P1, 'hand')
        await t.play(robe, targets=[mon.entity_id])
        self.assertEqual(t.conditions(mon), set())
        t.next_turn()
        mis = self.opp_attacker(t, MISMAGIUS)
        t.energy(mis, P, 3)
        await t.attack(mis, 'Hypnoblast', pid=P2)
        self.assertEqual(400 - t.hp(mon), 70)
        self.assertNotIn(ASLEEP, t.conditions(mon))

    async def test_robe_only_protects_holder(self):
        t = self.table()
        mon = t.put(self.filler, P1, 'active')
        self.big(mon)
        other = t.put(self.filler, P1, 'bench')
        robe = t.put(ROBE, P1, 'hand')
        await t.play(robe, targets=[other.entity_id])
        t.next_turn()
        mis = self.opp_attacker(t, MISMAGIUS)
        t.energy(mis, P, 3)
        await t.attack(mis, 'Hypnoblast', pid=P2)
        self.assertIn(ASLEEP, t.conditions(mon))


if __name__ == '__main__':
    unittest.main()
