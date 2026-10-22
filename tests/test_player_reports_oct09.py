"""Player reports, Oct 9: Kiawe, Lacey, Chandelure, Thwackey, Veluza,
Stellar Wish, Evil Admonition vs Dolls/Fossils, unlimited energy Abilities,
Moltres Inferno Wings."""
import unittest
from unittest.mock import AsyncMock, patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.test_sm_knockout_timing import SmKnockoutTimingTests
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID
from spirit.game.card_effects.bw_era import _pokemon_has_ability
from spirit.game.session.effects import EffectContext, resolve_attack
from spirit.game.session.legal_actions import compute_legal_actions
from spirit.game.session.passives import effective_retreat_cost
from spirit.tools.effect_smoke import P1, P2


class PlayerReportOct09Tests(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    attack_context = SmKnockoutTimingTests.attack_context
    energy = SmKnockoutTimingTests.energy

    def basic(self, kind):
        return CARD_DEFS_BY_GUID[self.energies[kind.value].lower()]

    def set_prizes(self, rig, pid, count):
        board = rig.board
        prizes = board.find_player_area(pid, 'prizePile')
        deck = board.find_player_area(pid, 'deck')
        while len(prizes.children) > count:
            board.move_card(prizes.children[0].entity_id, deck.entity_id)
        while len(prizes.children) < count:
            board.move_card(deck.children[0].entity_id, prizes.entity_id)

    # --- Kiawe -----------------------------------------------------------
    async def test_kiawe_attaches_everything_to_one_pokemon(self):
        rig, e = self.rig('SM3.Kiawe_116', 'trainer')
        board = rig.board
        for _ in range(4):
            self.add(rig, self.basic(PokemonTypes.FIRE), P1, 'deck')
        mine = board.pokemon_in_play(P1)
        self.assertGreater(len(mine), 1)
        target = mine[-1]
        before = {p.entity_id: len(board.attached_energies(p)) for p in mine}
        prompts = []

        async def choose_pokemon(ctx_self, candidates, prompt='', **k):
            prompts.append(prompt)
            return target

        async def choose_cards(ctx_self, pool, n, *a, **k):
            return list(pool)[:n]

        definition = fixtures.definition('SM3.Kiawe_116')
        with patch.object(EffectContext, 'choose_pokemon', choose_pokemon), \
                patch.object(EffectContext, 'choose_cards', choose_cards):
            await definition.effect(EffectContext(rig.session, P1, e['target'], None))
        gained = {p.entity_id: len(board.attached_energies(p)) - before[p.entity_id] for p in mine}
        self.assertEqual(len(prompts), 1)
        self.assertEqual(gained[target.entity_id], 4)
        self.assertEqual(sum(gained.values()), 4)
        self.assertTrue(definition.effect.printed_ends_turn)

    # --- Lacey / Emcee's Hype -------------------------------------------
    async def _drawn(self, path, prizes):
        rig, e = self.rig(path, 'trainer')
        for _ in range(12):    # enough deck for an 8-card draw in any rig
            self.add(rig, self.filler, P1, 'deck')
        self.set_prizes(rig, P2, prizes)
        hand = rig.board.find_player_area(P1, 'hand')
        # A played Supporter is not in the hand while it resolves.
        rig.board.move_card(e['target'].entity_id, rig.board.find_player_area(P1, 'discard').entity_id)
        start = len([c for c in hand.children if c is not e['target']])
        await fixtures.definition(path).effect(EffectContext(rig.session, P1, e['target'], None))
        return len([c for c in hand.children if c is not e['target']]), start

    async def test_lacey_draws_eight_against_three_or_fewer_prizes(self):
        self.assertEqual((await self._drawn('SV07.Lacey_139', 6))[0], 4)
        self.assertEqual((await self._drawn('SV07.Lacey_139', 4))[0], 4)
        self.assertEqual((await self._drawn('SV07.Lacey_139', 3))[0], 8)
        self.assertEqual((await self._drawn('SV07.Lacey_139', 1))[0], 8)

    async def test_emcees_hype_draws_two_more(self):
        after, start = await self._drawn('SV10.EmceesHype_163', 6)
        self.assertEqual(after - start, 2)
        after, start = await self._drawn('SV10.EmceesHype_163', 3)
        self.assertEqual(after - start, 4)

    # --- Chandelure ------------------------------------------------------
    async def test_alluring_light_both_players_draw(self):
        rig, e = self.rig('SV06.Chandelure_38')
        board = rig.board
        mine = len(board.find_player_area(P1, 'hand').children)
        theirs = len(board.find_player_area(P2, 'hand').children)
        ability = fixtures.definition('SV06.Chandelure_38').abilities[0]
        await ability.effect(EffectContext(rig.session, P1, e['target'], ability))
        self.assertEqual(len(board.find_player_area(P1, 'hand').children), mine + 1)
        self.assertEqual(len(board.find_player_area(P2, 'hand').children), theirs + 1)

    # --- Thwackey / Terrakion / Sawsbuck: YOUR Stadium -------------------
    def _with_stadium(self, rig, owner):
        stadium = self.add(rig, fixtures.definition('SV2.Artazon_171'), owner, 'hand')
        slot = rig.board.find_global_area('activeStadium')
        rig.board.move_card(stadium.entity_id, slot.entity_id)
        stadium.owning_player_id = owner

    async def test_lay_of_the_land_needs_your_own_stadium(self):
        for owner, free in ((None, False), (P2, False), (P1, True)):
            rig, e = self.rig('SWSH45.Thwackey_12')
            if owner:
                self._with_stadium(rig, owner)
            cost = effective_retreat_cost(rig.board, e['target'])
            with self.subTest(owner=owner):
                self.assertEqual(cost == 0, free)

    async def test_stadium_bonus_attacks_need_your_own_stadium(self):
        for path, title in (('SWSH4.Terrakion_92', None), ('SWSH6.Sawsbuck_12', None)):
            for owner, bonus in ((P2, False), (P1, True)):
                rig, e = self.rig(path)
                self._with_stadium(rig, owner)
                defender = rig.board.active_pokemon(P2)
                defender.set_attribute(AttrID.HP, 999)
                defender.set_attribute(AttrID.WEAKNESS_TYPES, [])
                defender.set_attribute(AttrID.RESISTANCE_TYPES, [])
                attack = next(a for a in fixtures.definition(path).abilities
                              if '80 more damage' in (getattr(a, 'game_text', '') or ''))
                with patch.object(EffectContext, 'ask_yes_no', AsyncMock(return_value=False)):
                    await attack.effect(EffectContext(rig.session, P1, e['target'], attack))
                done = 999 - defender.get_attribute(AttrID.HP)
                with self.subTest(path=path, owner=owner):
                    self.assertEqual(done, attack.damage + (80 if bonus else 0))

    # --- Veluza: only when Veluza itself is KO'd in the Active Spot ------
    async def test_fillet_memento_ignores_other_knockouts(self):
        rig, e = self.rig('SV4.Veluza_54')
        veluza = e['target']
        rig.to_area(veluza, P1, 'bench')
        victim = self.add(rig, self.filler, P1, 'activePokemonArea')
        energy = self.energy(rig, victim)
        ctx = self.attack_context(rig, victim)
        with patch.object(EffectContext, 'choose_cards', AsyncMock(side_effect=AssertionError('prompted'))):
            await ctx.deal_damage(1000, target=victim)
            await rig.session.resolve_knockouts(ctx)
        self.assertIn(energy, ctx.discard_pile(P1))

    async def test_fillet_memento_moves_water_when_veluza_ko_active(self):
        rig, e = self.rig('SV4.Veluza_54')
        veluza = e['target']
        self.assertIs(rig.board.active_pokemon(P1), veluza)
        for card in list(rig.board.attached_energies(veluza)):
            veluza.remove_child(card)
        energies = [self.energy(rig, veluza) for _ in range(2)]
        ctx = self.attack_context(rig, veluza)

        async def choose_cards(ctx_self, pool, n, *a, **k):
            return list(pool)[:n]

        with patch.object(EffectContext, 'choose_cards', choose_cards), \
                patch.object(EffectContext, 'choose_pokemon',
                             AsyncMock(side_effect=lambda c, *a, **k: c[0])):
            await ctx.deal_damage(1000, target=veluza)
            await rig.session.resolve_knockouts(ctx)
        bench = rig.board.pokemon_in_play(P1)
        self.assertTrue(all(any(en in p.children for p in bench) for en in energies))

    # --- Stellar Wish shows all 5 cards ----------------------------------
    async def test_stellar_wish_shows_the_other_cards(self):
        rig, e = self.rig('Promo_SM.Jirachi_161')
        self.add(rig, CARD_DEFS_BY_GUID[self.item.lower()] if isinstance(self.item, str)
                 else self.item, P1, 'deck')
        ability = fixtures.definition('Promo_SM.Jirachi_161').abilities[0]
        seen = {}

        async def choose_cards(ctx_self, cards, count, *a, display_cards=None, **k):
            seen['selectable'], seen['shown'] = len(cards), len(display_cards or [])
            return []

        with patch.object(EffectContext, 'choose_cards', choose_cards):
            await ability.effect(EffectContext(rig.session, P1, e['target'], ability))
        self.assertEqual(seen['shown'], 5)
        self.assertGreaterEqual(seen['selectable'], 1)
        self.assertLess(seen['selectable'], 5)

    # --- Evil Admonition: Dolls / Fossils have no Ability ----------------
    def test_rule_actions_are_not_abilities(self):
        from spirit.game.models.board import create_card_entity
        from spirit.game.scripts.cards import loader
        for path in ('SM12.LilliesPokDoll_197', 'XY4.RoboSubstituteTeamFlareGear_102',
                     'SV4.SnorlaxDoll_175'):
            card = create_card_entity(loader.cards_by_guid[fixtures.definition(path).guid.lower()], P2)
            with self.subTest(path=path):
                self.assertFalse(_pokemon_has_ability(card))
        tapu = create_card_entity(loader.cards_by_guid[
            fixtures.definition('Promo_SM.TapuLele_152').guid.lower()], P2)
        self.assertTrue(_pokemon_has_ability(tapu))

    # --- Unlimited energy Abilities can be used again and again ----------
    async def test_unlimited_attach_abilities_repeat(self):
        cases = [('SWSH1.Frosmoth_64', PokemonTypes.WATER), ('SWSH5.Cherrim_8', PokemonTypes.GRASS),
                 ('BW1.Emboar_20', PokemonTypes.FIRE), ('BW7.Blastoise_31', PokemonTypes.WATER),
                 ('SV2.Baxcalibur_60', PokemonTypes.WATER)]
        for path, kind in cases:
            rig, e = self.rig(path)
            board, source = rig.board, e['target']
            self.add(rig, fixtures.definition('SV4.Veluza_54'), P1, 'bench')
            hand = board.find_player_area(P1, 'hand')
            deck = board.find_player_area(P1, 'deck')
            for card in list(hand.children):
                if type(card).__name__ == 'EnergyEntity':
                    board.move_card(card.entity_id, deck.entity_id)
            for _ in range(3):
                self.add(rig, self.basic(kind), P1, 'hand')
            state = rig.session.turn_state
            attached = 0
            for _ in range(3):
                offers = [x for x in compute_legal_actions(board, state, P1, rig.session.game_id)
                          if x['entityID'] == source.entity_id
                          and x['selectableAction']['description'] == 'UsePokemonAbility']
                if not offers:
                    break
                picks = iter([True, False])

                async def choose_cards(ctx_self, pool, n, *a, **k):
                    return [pool[0]] if next(picks, False) else []

                async def choose_pokemon(ctx_self, candidates, *a, **k):
                    return candidates[-1]

                before = sum(len(board.attached_energies(p)) for p in board.pokemon_in_play(P1))
                with patch.object(EffectContext, 'choose_cards', choose_cards), \
                        patch.object(EffectContext, 'choose_pokemon', choose_pokemon):
                    await rig.session._execute_use_ability(P1, source, offers[0])
                attached += sum(len(board.attached_energies(p))
                                for p in board.pokemon_in_play(P1)) - before
            with self.subTest(path=path):
                self.assertEqual(attached, 3)

    # --- Moltres (BRS) Inferno Wings -------------------------------------
    async def test_inferno_wings_bonus_when_damaged(self):
        for damaged, expected in ((False, 20), (True, 90)):
            rig, e = self.rig('SWSH9.Moltres_21')
            moltres = e['target']
            if damaged:
                moltres.set_attribute(AttrID.HP, moltres.get_attribute(AttrID.HP) - 10)
            defender = rig.board.active_pokemon(P2)
            defender.set_attribute(AttrID.HP, 999)
            defender.set_attribute(AttrID.RESISTANCE_TYPES, [])
            attack = fixtures.definition('SWSH9.Moltres_21').abilities[0]
            await resolve_attack(rig.session, P1, moltres, attack, attack.title)
            self.assertEqual(999 - defender.get_attribute(AttrID.HP), expected)


if __name__ == "__main__":
    unittest.main()


class RuleOfEvilTests(unittest.IsolatedAsyncioTestCase):
    """Weavile (BUS) Rule of Evil: 60 to each Pokémon with a working Ability,
    both sides, once; Weakness only on the opponent's Active."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _run(self, lock=False, weak=False):
        from tests.bughunt_table import Table
        t = Table(self)
        weavile = t.put('SM3.Weavile_86', P1, 'active')
        t.energy(weavile, PokemonTypes.DARKNESS)
        board = dict(
            my_ability=t.put('Promo_SM.TapuLele_152', P1, 'bench'),
            my_plain=t.put(self.filler, P1, 'bench'),
            opp_ability=t.put('Promo_SM.TapuLele_152', P2, 'active'),
            doll=t.put('SM12.LilliesPokDoll_197', P2, 'bench'),
            opp_plain=t.put(self.filler, P2, 'bench'))
        board['opp_ability'].set_attribute(
            AttrID.WEAKNESS_TYPES, [PokemonTypes.DARKNESS.value] if weak else [])
        board['opp_ability'].set_attribute(AttrID.RESISTANCE_TYPES, [])
        if lock:
            t.state.abilities_disabled_through_turn = t.state.turn_number + 1
        before = {k: t.hp(p) for k, p in board.items()}
        await t.attack(weavile, 'Rule of Evil')
        in_play = set(t.board.pokemon_in_play(P1)) | set(t.board.pokemon_in_play(P2))
        return {k: (before[k] - t.hp(p)) if p in in_play else before[k] for k, p in board.items()}

    async def test_hits_each_ability_pokemon_once(self):
        self.assertEqual(await self._run(), dict(
            my_ability=60, my_plain=0, opp_ability=60, doll=0, opp_plain=0))

    async def test_weakness_on_active_only(self):
        hit = await self._run(weak=True)
        self.assertEqual(hit['opp_ability'], 110)   # 60 x2 = 120 Knocks Out the 110 HP Active
        self.assertEqual(hit['my_ability'], 60)

    async def test_nothing_under_ability_lock(self):
        self.assertEqual(sum((await self._run(lock=True)).values()), 0)


class PrizePrivacyTests(unittest.IsolatedAsyncioTestCase):
    """Cards going INTO the Prizes are hidden in an earlier client step than
    their move, so none can flash face up (Redeemable Ticket, Rotom Dex)."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def _steps(self, path):
        from tests.bughunt_table import Table
        t = Table(self)
        t.put(self.filler, P1, 'active')
        t.put(self.filler, P2, 'active')
        card = t.put(path, P1, 'hand')
        steps = []
        session = t.session
        original = session.send_game_sequence

        async def record(viewers, sequence, msgs, *a, **k):
            steps.append([m for m in msgs if isinstance(m, dict)])
            return await original(viewers, sequence, msgs, *a, **k)

        old = set(c.entity_id for c in t.zone(P1, 'prizes'))
        with patch.object(session, 'send_game_sequence', record):
            await t.play(card)
        new = set(c.entity_id for c in t.zone(P1, 'prizes')) - old
        return steps, new

    def _first(self, steps, entity_id, kind):
        import json
        for i, msgs in enumerate(steps):
            for m in msgs:
                text = json.dumps(m)
                if entity_id in text and kind in text:
                    return i
        return None

    async def test_new_prizes_hidden_before_they_move(self):
        for path in ('SV09.RedeemableTicket_156', 'SM1.RotomDex_131'):
            steps, new = await self._steps(path)
            self.assertTrue(new, path)
            for entity_id in new:
                hide = self._first(steps, entity_id, 'AttributesReset')
                move = self._first(steps, entity_id, 'EntityMoved')
                with self.subTest(card=path):
                    self.assertIsNotNone(hide)
                    self.assertIsNotNone(move)
                    self.assertLess(hide, move)
