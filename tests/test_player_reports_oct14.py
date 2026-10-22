"""Player reports Oct 14 (overnight).

1. Galarian Obstagoon SWSH8 161 Silence (and the other scripted "Choose 1 of
   your opponent's Active Pokemon's attacks ... can't use that attack"
   cards): the pick was plain buttons on the attacker's own panel, so the
   player never got a usable choice.  Now the same attack-row picker as
   Amnesia/Torment in the generic interpreter.
2. Nidoran: both genders shared one card name key (...pokemon.Nidoran.Name),
   so Nidorino could evolve from Nidoran F and Nidorina from Nidoran M (also
   by Rare Candy).  The cards now use the original PTCGO keys NidoranFemale
   / NidoranMale (already in the client's LocalizationDB).
3. Hex Maniac lasts "until the end of your opponent's next turn", so the
   Pokemon Checkup after that turn already sees Abilities again (Froslass
   Freezing Shroud didn't fire).
4. Random Receiver: RULING (owner, Oct 14) -- the deck IS shuffled afterwards
   even when the top card was the Supporter (an earlier change skipped it).
5. Pokemon League Headquarters (+Colorless for Basics) was added on top of
   "ignore all Energy in this Pokemon's attack costs" (Cramorant's Lost
   Provisions, Castform's Weather Reading): ignoring all Energy wins.
6. Canceling Cologne only covered the Pokemon that was Active when it was
   played; a replacement promoted later that turn (Archeops after the
   Knock Out) kept its Ability and blocked evolving.
7. Owner ruling: attack effects that switch Abilities off "until the end of
   [a] turn" (Greninja XY9 40 Shadow Stitching, Gastro Acid) are over in the
   Pokemon Checkup after that turn, like Hex Maniac.
"""
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import def_for, Attack, CARD_DEFS_BY_GUID, evolves_from_chain
from spirit.game.session.effects import EffectContext
from spirit.game.session.game_session import GameSession
from spirit.tools.effect_smoke import P1, P2

OBSTAGOON = 'SWSH8.GalarianObstagoon_161'
SCRIPTED_LOCKERS = [('SWSH8.GalarianObstagoon_161', 'Silence'), ('SWSH12.Ralts_67', 'Memory Skip'),
                    ('SWSH4.Exeggutor_5', 'Head Crack'), ('SWSH4.Sableye_105', 'Torment'),
                    ('SWSH2.Morpeko_73', 'Torment')]
NIDORAN_F, NIDORAN_M = 'SV035.Nidoran_29', 'SV035.Nidoran_32'
NIDORINA, NIDORINO = 'SV035.Nidorina_30', 'SV035.Nidorino_33'
NIDOQUEEN, NIDOKING = 'SV035.Nidoqueen_31', 'SV035.Nidoking_34'


class Reports(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def power(self, t, pokemon, attack):
        for kind, n in attack.cost.items():
            t.energy(pokemon, kind if kind.value in self.energies else PokemonTypes.DARKNESS, n)

    # --- 1. Silence & co -------------------------------------------------
    async def test_scripted_attack_locks_use_the_attack_picker(self):
        for spec, title in SCRIPTED_LOCKERS:
            with self.subTest(spec):
                t = Table(self)
                me = t.put(spec, P1, 'active')
                attack = next(a for a in def_for(me.archetype_id).abilities
                              if isinstance(a, Attack) and a.title == title)
                self.power(t, me, attack)
                opp = t.put(OBSTAGOON, P2, 'active', hp=500)
                silence, strike = [a for a in def_for(opp.archetype_id).abilities
                                   if isinstance(a, Attack)]
                shown = []

                async def pick(session, pid, source, candidates, prompt=''):
                    shown.append([a.title for _, a in candidates])
                    return 1                                    # Merciless Strike
                with patch.object(GameSession, 'prompt_attack_selection', pick):
                    await t.attack(me, title)
                self.assertEqual(shown, [['Silence', 'Merciless Strike']])
                turn = t.state.turn_number
                t.state.turn_number = turn + 1                  # opponent's next turn
                self.assertTrue(t.state.attack_locked(opp.entity_id, strike.ability_id))
                self.assertFalse(t.state.attack_locked(opp.entity_id, silence.ability_id))
                t.state.turn_number = turn + 3                  # their turn after that
                self.assertFalse(t.state.attack_locked(opp.entity_id, strike.ability_id))

    # --- 2. Nidoran ------------------------------------------------------
    def test_every_nidoran_line_is_split_by_gender(self):
        seen = 0
        for d in CARD_DEFS_BY_GUID.values():
            name = d.display_name or ''
            if 'Nidoran' in name:
                seen += 1
                own = d.extra_attributes[str(AttrID.EVOLUTION_LOGIC_NAME.value)]['value']
                self.assertTrue(own.endswith('Female' if '♀' in name else 'Male'), (name, own))
            elif any(x in name for x in ('Nidorina', 'Nidoqueen')):
                self.assertTrue(evolves_from_chain(d.guid)[-1].endswith('NidoranFemale'), name)
            elif any(x in name for x in ('Nidorino', 'Nidoking')):
                self.assertTrue(evolves_from_chain(d.guid)[-1].endswith('NidoranMale'), name)
        self.assertGreaterEqual(seen, 12)

    def test_nidoran_names_are_the_original_client_keys(self):
        f = fixtures.definition(NIDORAN_F)
        m = fixtures.definition(NIDORAN_M)
        self.assertEqual(f.name, 'com.direwolfdigital.cake.data.archetypes.pokemon.NidoranFemale.Name')
        self.assertEqual(m.name, 'com.direwolfdigital.cake.data.archetypes.pokemon.NidoranMale.Name')
        self.assertEqual(f.display_name, 'Nidoran ♀')
        self.assertEqual(m.display_name, 'Nidoran ♂')

    async def test_evolve_only_onto_matching_gender(self):
        t = Table(self)
        female = t.put(NIDORAN_F, P1, 'bench')
        male = t.put(NIDORAN_M, P1, 'bench')
        t.put(self.filler, P1, 'active')
        nidorina = t.put(NIDORINA, P1, 'hand')
        nidorino = t.put(NIDORINO, P1, 'hand')
        self.assertEqual(t.targets(nidorina, 'EvolvePokemonPlayAbility'), {female.entity_id})
        self.assertEqual(t.targets(nidorino, 'EvolvePokemonPlayAbility'), {male.entity_id})

    async def test_rare_candy_respects_gender(self):
        t = Table(self)
        male = t.put(NIDORAN_M, P1, 'bench')
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        candy = t.put('ME1.RareCandy_125', P1, 'hand')
        t.put(NIDOQUEEN, P1, 'hand')
        self.assertFalse(t.can(candy, 'UseTrainerCard'))
        t.put(NIDOKING, P1, 'hand')
        self.assertTrue(t.can(candy, 'UseTrainerCard'))
        await t.play(candy)
        self.assertIn('Nidoking', t.names(t.board.pokemon_in_play(P1)))

    async def test_come_along_finds_only_nidoran_female(self):
        t = Table(self)
        male = t.put('XY11.Nidoran_43', P1, 'active')
        attack = next(a for a in def_for(male.archetype_id).abilities if isinstance(a, Attack))
        self.power(t, male, attack)
        t.put(self.filler, P2, 'active')
        t.deck(P1, [NIDORAN_M, NIDORAN_F])
        offered = []

        def picks(cards, count, prompt, display):
            offered.append(t.names(cards))
            return [c for c in cards if '♀' in (def_for(c.archetype_id).display_name or '')][:count]
        t.picks = picks
        await t.attack(male, attack.title)
        bench = t.names(t.zone(P1, 'bench'))
        self.assertEqual(bench, ['Nidoran ♀'])

    # --- 3. Hex Maniac ends before the Checkup ----------------------------
    async def test_freezing_shroud_returns_at_the_checkup_hex_maniac_ends(self):
        t = Table(self)
        froslass = t.put('SV06.Froslass_53', P1, 'bench')
        t.put(self.filler, P1, 'active')
        victim = t.put('SWSH2.Garbodor_118', P2, 'active')
        hex_maniac = t.put('XY7.HexManiac_75', P1, 'hand')
        await t.play(hex_maniac)
        await t.checkup()                       # end of the Hex Maniac turn
        self.assertEqual(t.damage(victim), 0)
        t.next_turn()                           # opponent's turn: still no Abilities
        from spirit.game.session.passives import ability_locked
        self.assertTrue(ability_locked(t.board, victim))
        await t.checkup()                       # Hex Maniac is over
        self.assertEqual(t.damage(victim), 10)
        self.assertEqual(t.damage(froslass), 0)
        t.next_turn()
        self.assertFalse(ability_locked(t.board, victim))

    # --- 4. Random Receiver ------------------------------------------------
    async def receiver(self, top):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        t.deck(P1, top)
        shuffles = []
        real = EffectContext.shuffle_deck

        async def counting(ctx, player_id=None):
            shuffles.append(player_id or ctx.player_id)
            return await real(ctx, player_id)
        with patch.object(EffectContext, 'shuffle_deck', counting):
            await t.play(t.put('XY10.RandomReceiver_109', P1, 'hand'))
        return t, shuffles

    async def test_random_receiver_shuffles_even_when_top_card_is_the_supporter(self):
        # RULING (owner, Oct 14): shuffle afterwards even if the Supporter was on top.
        t, shuffles = await self.receiver(['SM10.Welder_189'])
        self.assertEqual(shuffles, [P1])
        self.assertIn('Welder', t.names(t.zone(P1, 'hand')))

    async def test_random_receiver_shuffles_the_other_revealed_cards(self):
        t, shuffles = await self.receiver(['SM10.Welder_189', 'ME1.RareCandy_125'])
        self.assertEqual(shuffles, [P1])
        self.assertIn('Welder', t.names(t.zone(P1, 'hand')))

    # --- 5. Free attacks vs Pokemon League Headquarters -------------------
    def cost_of(self, t, pokemon):
        from spirit.game.session.passives import effective_attack_cost
        attack = next(a for a in def_for(pokemon.archetype_id).abilities if isinstance(a, Attack))
        cost = {PokemonTypes(k).name.capitalize() if not isinstance(k, str) else k: v
                for k, v in attack.cost.items()}
        return effective_attack_cost(t.board, pokemon, cost, attack), attack

    async def test_lost_provisions_ignores_league_headquarters(self):
        t = Table(self)
        bird = t.put('SWSH11.Cramorant_50', P1, 'active')
        t.put(self.filler, P2, 'active')
        t.stadium('SV3.PokmonLeagueHeadquarters_192', P2)
        cost, attack = self.cost_of(t, bird)
        self.assertEqual(sum(cost.values()), sum(attack.cost.values()) + 1)   # HQ applies
        for _ in range(4):
            t.put(self.item, P1, 'lostZone')
        cost, _ = self.cost_of(t, bird)
        self.assertEqual(cost, {})
        self.assertIsNotNone(t.attack_offer(bird, attack.title))

    async def test_weather_reading_ignores_league_headquarters(self):
        t = Table(self)
        castform = t.put('SWSH6.Castform_121', P1, 'active')
        t.put(self.filler, P2, 'active')
        for _ in range(8):
            t.put('SV3.PokmonLeagueHeadquarters_192', P1, 'discard')
        t.stadium('SV3.PokmonLeagueHeadquarters_192', P2)
        cost, _ = self.cost_of(t, castform)
        self.assertEqual(cost, {})

    async def test_league_headquarters_still_taxes_ordinary_basics(self):
        t = Table(self)
        mon = t.put('SWSH8.GalarianObstagoon_161', P1, 'active')   # not Basic: no tax
        zub = t.put('SWSH12.Ralts_67', P1, 'bench')
        t.stadium('SV3.PokmonLeagueHeadquarters_192', P2)
        cost, attack = self.cost_of(t, zub)
        self.assertEqual(sum(cost.values()), sum(attack.cost.values()) + 1)
        cost, attack = self.cost_of(t, mon)
        self.assertEqual(sum(cost.values()), sum(attack.cost.values()))

    # --- 6. Canceling Cologne covers the new Active ------------------------
    async def test_canceling_cologne_covers_a_promoted_archeops(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        female = t.put(NIDORAN_F, P1, 'bench')
        nidorina = t.put(NIDORINA, P1, 'hand')
        okidogi = t.put(self.filler, P2, 'active')
        archeops = t.put('BW3.Archeops_67', P2, 'bench')
        self.assertFalse(t.can(nidorina, 'EvolvePokemonPlayAbility'))   # Archeops on
        await t.play(t.put('SWSH10.CancelingCologne_136', P1, 'hand'))
        # Okidogi is Knocked Out; the opponent promotes Archeops.
        t.board.move_card(okidogi.entity_id, t.board.find_player_area(P2, 'discard').entity_id)
        t.board.move_card(archeops.entity_id,
                          t.board.find_player_area(P2, 'activePokemonArea').entity_id)
        self.assertIs(t.active(P2), archeops)
        self.assertEqual(t.targets(nidorina, 'EvolvePokemonPlayAbility'), {female.entity_id})
        t.next_turn()                                   # Cologne is over
        t.next_turn()
        self.assertFalse(t.can(nidorina, 'EvolvePokemonPlayAbility'))

    async def test_canceling_cologne_leaves_the_bench_alone(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(NIDORAN_F, P1, 'bench')
        nidorina = t.put(NIDORINA, P1, 'hand')
        t.put(self.filler, P2, 'active')
        t.put('BW3.Archeops_67', P2, 'bench')
        await t.play(t.put('SWSH10.CancelingCologne_136', P1, 'hand'))
        self.assertFalse(t.can(nidorina, 'EvolvePokemonPlayAbility'))

    # --- 7. Attack ability locks end before the Checkup ---------------------
    async def test_shadow_stitching_ends_before_the_checkup(self):
        t = Table(self)
        greninja = t.put('XY9.Greninja_40', P1, 'active')
        attack = next(a for a in def_for(greninja.archetype_id).abilities
                      if isinstance(a, Attack) and a.title == 'Shadow Stitching')
        self.power(t, greninja, attack)
        victim = t.put('SWSH2.Garbodor_118', P2, 'active', hp=500)
        t.put('SV06.Froslass_53', P2, 'bench')
        await t.attack(greninja, 'Shadow Stitching')
        hit = t.damage(victim)
        await t.checkup()                          # end of the attacking turn: still locked
        self.assertEqual(t.damage(victim), hit)
        t.next_turn()
        from spirit.game.session.passives import ability_locked
        self.assertTrue(ability_locked(t.board, victim))
        await t.checkup()                          # after the opponent's turn: over
        self.assertEqual(t.damage(victim), hit + 10)

    async def test_gastro_acid_lasts_through_the_next_checkup_then_ends(self):
        t = Table(self)
        bell = t.put('SM10.Victreebel_15', P1, 'active')
        attack = next(a for a in def_for(bell.archetype_id).abilities
                      if isinstance(a, Attack) and a.title == 'Gastro Acid')
        self.power(t, bell, attack)
        froslass = t.put('SV06.Froslass_53', P2, 'active', hp=500)
        victim = t.put('SWSH2.Garbodor_118', P2, 'bench')
        await t.attack(bell, 'Gastro Acid')
        await t.checkup()
        t.next_turn()
        await t.checkup()                          # "until the end of YOUR next turn"
        self.assertEqual(t.damage(victim), 0)
        t.next_turn()
        await t.checkup()                          # that turn is over
        self.assertEqual(t.damage(victim), 10)

    async def test_canceling_cologne_is_over_at_that_turns_checkup(self):
        t = Table(self)
        t.put(self.filler, P1, 'active')
        froslass = t.put('SV06.Froslass_53', P2, 'active')
        victim = t.put('SWSH2.Garbodor_118', P2, 'bench')
        await t.play(t.put('SWSH10.CancelingCologne_136', P1, 'hand'))
        from spirit.game.session.passives import ability_locked
        self.assertTrue(ability_locked(t.board, froslass))     # during the turn
        await t.checkup()                                       # turn over
        self.assertEqual(t.damage(victim), 10)


if __name__ == '__main__':
    unittest.main()


class ChoicePromptSweep(unittest.IsolatedAsyncioTestCase):
    """Choice-prompt sweep (Oct 14): the floating ability panel (R.U) is a
    single unscrolled column of buttons, the dialog is a grid. Long menus
    (type pickers, 0..N counters) must use the dialog."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _route(self, buttons, **kw):
        t = Table(self)
        source = t.put(self.filler, P1, 'active') if hasattr(self, 'filler') \
            else t.put('SWSH8.GalarianObstagoon_161', P1, 'active')
        ctx = EffectContext(t.session, P1, source, None)
        calls = []

        async def panel(*a, **k):
            calls.append('panel'); return 0

        async def dialog(*a, **k):
            calls.append('dialog'); return 0
        with patch.object(t.session, 'prompt_choice_panel', panel), \
                patch.object(t.session, 'prompt_player_choice', dialog):
            await ctx.choose("Pick", buttons, **kw)
        return calls

    async def test_short_menu_uses_panel(self):
        self.assertEqual(await self._route(["A", "B", "C", "D"]), ['panel'])

    async def test_type_picker_uses_dialog(self):
        types = ["Grass", "Fire", "Water", "Lightning", "Psychic",
                 "Fighting", "Darkness", "Metal", "Colorless"]
        self.assertEqual(await self._route(types), ['dialog'])

    async def test_counter_picker_uses_dialog(self):
        self.assertEqual(await self._route([str(i) for i in range(8)]), ['dialog'])

    async def test_opponent_choice_still_dialog(self):
        self.assertEqual(await self._route(["A", "B"], player_id=P2), ['dialog'])
