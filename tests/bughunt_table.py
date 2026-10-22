"""A small, explicit board builder for card-by-card scenario tests.

    t = Table(self)                       # empty board, turn 3, P1 to act
    weezing = t.put('SWSH2.GalarianWeezing_113', P1, 'active')
    t.energy(weezing, PokemonTypes.DARKNESS)
    t.deck(P1, ['SWSH2.Garbodor_118'])    # on top of a filler deck
    await t.play(P1, card)                # through the real action executor

Choices are scripted rather than prompted:  t.picks / t.pokemon / t.yes /
t.heads may be set to callables or values before acting.
"""
from contextlib import ExitStack
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID, Attack, def_for
from spirit.game.models.board import create_card_entity
from spirit.game.models.board import PokemonEntity
from spirit.game.scripts.cards import loader
from spirit.game.session.effects import EffectContext
from spirit.game.session.legal_actions import compute_legal_actions
from spirit.game.session.passives import effective_max_hp, effective_retreat_cost
from spirit.tools.effect_smoke import P1, P2

ZONES = {'active': 'activePokemonArea', 'bench': 'bench', 'hand': 'hand',
         'deck': 'deck', 'discard': 'discard', 'prizes': 'prizePile'}
POISONED, ASLEEP, CONFUSED, BURNED, PARALYZED = (
    'Poisoned', 'Asleep', 'Confused', 'Burned', 'Paralyzed')


def _definition(spec):
    if isinstance(spec, str):
        return fixtures.definition(spec)
    return spec


class Table:
    def __init__(self, test, filler_deck=30):
        self.test = test
        rig, _ = test.rig('SWSH2.Garbodor_118', 'trainer')
        self.rig, self.board, self.session = rig, rig.board, rig.session
        self.state = rig.session.turn_state
        for pid in (P1, P2):
            for zone in ('activePokemonArea', 'bench', 'hand', 'discard', 'prizePile', 'deck'):
                area = self.board.find_player_area(pid, zone)
                for card in list(area.children):
                    area.remove_child(card)
            for _ in range(6):
                self.put(test.item, pid, 'prizes')
            # Deck filler is a plain Item so Pokémon/Energy searches only
            # ever find the cards a scenario puts there.
            for _ in range(filler_deck):
                self.put(test.item, pid, 'deck')
        stadium = self.board.find_global_area('activeStadium')
        for card in list(stadium.children):
            stadium.remove_child(card)
        # scripted answers
        self.picks = None        # callable(cards, count, prompt, display) -> list
        self.pokemon = None      # callable(candidates, prompt) -> entity
        self.yes = True          # bool or callable(prompt)
        self.heads = True        # bool or callable(title) per coin
        self.prompts = []        # every prompt text seen, in order
        self.shown = []          # display_cards sizes for browser picks

    # -- building --------------------------------------------------------
    def put(self, spec, pid, zone, *, hp=None):
        definition = _definition(spec)
        card = create_card_entity(loader.cards_by_guid[definition.guid.lower()], pid)
        card.owning_player_id = pid
        area = self.board.find_player_area(pid, ZONES.get(zone, zone))
        self.board.add_card_to_area(card, area)
        if isinstance(card, PokemonEntity) and zone in ('active', 'bench'):
            card.set_attribute(AttrID.HP, hp if hp is not None
                               else effective_max_hp(self.board, card))
            self.state.entered_play_turn[card.entity_id] = 0
        return card

    def basic_energy(self, kind):
        return CARD_DEFS_BY_GUID[self.test.energies[kind.value].lower()]

    def energy(self, pokemon, kind=PokemonTypes.DARKNESS, count=1):
        made = []
        for _ in range(count):
            card = self.put(self.basic_energy(kind), pokemon.owning_player_id, 'hand')
            self.board.attach_card(card.entity_id, pokemon.entity_id)
            made.append(card)
        return made[0] if count == 1 else made

    def attach(self, spec, pokemon):
        card = self.put(spec, pokemon.owning_player_id, 'hand')
        self.board.attach_card(card.entity_id, pokemon.entity_id)
        return card

    def stadium(self, spec, owner):
        card = self.put(spec, owner, 'hand')
        self.board.move_card(card.entity_id, self.board.find_global_area('activeStadium').entity_id)
        card.owning_player_id = owner
        return card

    def deck(self, pid, specs, top=True):
        cards = [self.put(s, pid, 'deck') for s in specs]
        if not top:
            area = self.board.find_player_area(pid, 'deck')
            for c in cards:
                area.children.remove(c)
                area.children.insert(0, c)
        return cards

    def set_prizes(self, pid, count):
        area = self.board.find_player_area(pid, 'prizePile')
        while len(area.children) > count:
            area.remove_child(area.children[0])
        while len(area.children) < count:
            self.put(self.test.item, pid, 'prizes')

    # -- reading ---------------------------------------------------------
    def zone(self, pid, zone):
        return list(self.board.find_player_area(pid, ZONES.get(zone, zone)).children)

    def active(self, pid):
        return self.board.active_pokemon(pid)

    def hp(self, pokemon):
        return pokemon.get_attribute(AttrID.HP, 0)

    def damage(self, pokemon):
        return effective_max_hp(self.board, pokemon) - self.hp(pokemon)

    def conditions(self, pokemon):
        return set(pokemon.get_attribute(AttrID.SPECIAL_CONDITIONS) or [])

    def retreat(self, pokemon):
        return effective_retreat_cost(self.board, pokemon)

    def names(self, cards):
        return sorted((def_for(c.archetype_id).display_name or '?') for c in cards)

    def attached(self, pokemon):
        return [c for c in pokemon.children]

    # -- actions ---------------------------------------------------------
    def actions(self, pid=P1):
        return compute_legal_actions(self.board, self.state, pid, self.session.game_id)

    def offers(self, card, description=None, pid=P1):
        return [e for e in self.actions(pid) if e['entityID'] == card.entity_id
                and (description is None or e['selectableAction']['description'] == description)]

    def can(self, card, description, pid=P1):
        return bool(self.offers(card, description, pid))

    def targets(self, card, description, pid=P1):
        out = set()
        for e in self.offers(card, description, pid):
            for info in e.get('targetInfoLst') or []:
                out.update(info.get('validTargets') or [])
        return out

    def ability_offer(self, pokemon, title, pid=P1):
        from spirit.game.data_utils import ABILITIES_BY_ID
        for e in self.offers(pokemon, 'UsePokemonAbility', pid):
            ab = ABILITIES_BY_ID.get(e['selectableAction']['actionID'])
            if ab is not None and ab.title == title:
                return e
        return None

    def attack_offer(self, pokemon, title, pid=P1):
        from spirit.game.data_utils import ABILITIES_BY_ID
        for e in self.offers(pokemon, 'UsePokemonAttack', pid):
            ab = ABILITIES_BY_ID.get(e['selectableAction']['actionID'])
            if ab is not None and ab.title == title:
                return e
        return None

    def _patches(self):
        table = self

        async def choose_cards(ctx, cards, count, minimum=None, prompt='', player_id=None,
                               ordered=False, display_cards=None, slot_prompt='',
                               submit_on_pick=False):
            table.prompts.append(prompt)
            if display_cards is not None:
                table.shown.append(len(display_cards))
            cards = list(cards)
            if table.picks is not None:
                return list(table.picks(cards, count, prompt, display_cards))
            return cards[:count]

        async def choose_pokemon(ctx, candidates, prompt='', *a, **k):
            table.prompts.append(prompt)
            candidates = list(candidates)
            if hasattr(ctx, 'selectable_pokemon'):      # same filtering as the real chooser
                candidates = ctx.selectable_pokemon(candidates)
            if not candidates:
                return None
            if table.pokemon is not None:
                return table.pokemon(candidates, prompt)
            return candidates[0]

        async def ask_yes_no(ctx, prompt, player_id=None):
            table.prompts.append(prompt)
            return table.yes(prompt) if callable(table.yes) else table.yes

        async def flip_coins(ctx, count, title='', source=None, player_id=None):
            if callable(table.heads):
                return [table.heads(title) for _ in range(count)]
            return [bool(table.heads)] * count

        return [patch.object(EffectContext, 'choose_cards', choose_cards),
                patch.object(EffectContext, 'choose_pokemon', choose_pokemon),
                patch.object(EffectContext, 'ask_yes_no', ask_yes_no),
                patch.object(EffectContext, 'flip_coins', flip_coins)]

    async def _run(self, coro_fn):
        with ExitStack() as stack:
            for p in self._patches():
                stack.enter_context(p)
            return await coro_fn()

    async def do(self, entry, targets=(), pid=P1, amounts=None):
        assert entry is not None, 'action not offered'
        return await self._run(lambda: self.session._apply_player_action(
            pid, entry, list(targets), amounts))

    async def play(self, card, pid=P1, targets=()):
        entry = next((e for e in self.offers(card, None, pid)
                      if e['selectableAction']['description'] in
                      ('UseTrainerCard', 'DefaultStadiumPlayAbility',
                       'DefaultPokemonPlayAbility', 'DefaultToolPlayAbility',
                       'DefaultEnergyPlayAbility', 'EvolvePokemonPlayAbility')), None)
        if entry is None:
            entry = next(iter(self.offers(card, None, pid)), None)
        return await self.do(entry, targets, pid)

    async def use(self, pokemon, title, pid=P1):
        return await self.do(self.ability_offer(pokemon, title, pid), pid=pid)

    async def attack(self, pokemon, title, pid=P1):
        return await self.do(self.attack_offer(pokemon, title, pid), pid=pid)

    async def effect(self, spec, source, title=None, pid=P1):
        """Run a definition's effect directly (no legality gate)."""
        definition = _definition(spec)
        ability = None
        if title is not None:
            ability = next(a for a in definition.abilities if a.title == title)
            fn = ability.effect
        else:
            fn = definition.effect
        ctx = EffectContext(self.session, pid, source, ability)
        await self._run(lambda: fn(ctx))
        return ctx

    async def checkup(self):
        await self._run(lambda: self.session._run_pokemon_checkup())

    async def knockouts(self, ctx):
        await self._run(lambda: self.session.resolve_knockouts(ctx))

    def next_turn(self):
        """Hand the turn to the other player (turn_state only)."""
        other = P2 if self.state.active_player_id == P1 else P1
        self.state.begin_turn(other, self.board)   # board: expire temporary effects like the real game
