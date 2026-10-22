"""Sweep: every GLC-legal card whose text draws cards (attacks, Abilities, Trainers,
Tools/Special Energy).

Already covered elsewhere (not repeated here):
  test_sweep_basic.draw_n             attack text exactly "draw N cards."
  test_sweep_abilities.draw_ability   "once during your turn ..., you may draw N cards." (+active bonus)
  test_sweep_abilities.evolve_trigger "when you play this pokémon ... evolve ..., you may draw N cards."
  test_sweep_coin_rest                "flip N coins. for each heads, draw a card." bodies

Each card text is matched by a template (regex anchored on the whole normalised
text) that turns it into one or more *scenarios*: a board (hand / deck / prize
sizes for both players, extra setup), the action (attack, Ability, Trainer play,
Stadium use) and the expected FINAL hand / deck sizes of both players.  The
right player must draw exactly the right number; "you may" is also tested with
the choice declined; "draw until" is tested with the hand already at/above the
target and with a deck smaller than the draw.

Reports: audits/results/sweep/draw_<group>.json (failures, skipped and
the texts no template understood, with counts).
"""
import ast
import collections
import glob
import json
import os
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost, norm, label, REPORT_DIR, BIG
from spirit.game import glc
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import (CARD_DEFS_BY_GUID, PokemonCardDef, Attack, def_for,
                                    SupporterCardDef, ItemCardDef, StadiumCardDef,
                                    PokemonToolCardDef, EnergyCardDef)
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

WORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARDS_DIR = os.path.join(WORK, 'spirit', 'game', 'scripts', 'cards')
NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
       'seven': 7, 'eight': 8}
TYPES = {'grass': PokemonTypes.GRASS, 'fire': PokemonTypes.FIRE, 'water': PokemonTypes.WATER,
         'lightning': PokemonTypes.LIGHTNING, 'psychic': PokemonTypes.PSYCHIC,
         'fighting': PokemonTypes.FIGHTING, 'darkness': PokemonTypes.DARKNESS,
         'metal': PokemonTypes.METAL}
HIS = r"(?:his or her|their)"


def num(s):
    return NUM[s] if s in NUM else int(s)


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


# ----------------------------------------------------------------- the table --
class DrawTable(Table):
    """Table plus a scripted `choose` menu (mode pickers / either-player)."""

    def __init__(self, test, **k):
        super().__init__(test, **k)
        self.choice = 0          # int or callable(prompt, buttons) -> int
        self.menus = []

    def _patches(self):
        table = self

        async def choose(ctx, prompt, buttons, player_id=None, descriptions=None, use_panel=True):
            table.menus.append((prompt, list(buttons)))
            if callable(table.choice):
                return table.choice(prompt, list(buttons))
            return table.choice
        async def present_card_choice(ctx, card, prompt, buttons, player_id=None):
            table.menus.append((prompt, list(buttons)))
            if callable(table.choice):
                return table.choice(prompt, list(buttons))
            return table.choice

        async def flip_until_tails(ctx, title=''):
            heads = 0
            while heads < 50:
                h = table.heads(title) if callable(table.heads) else bool(table.heads)
                if not h:
                    break
                heads += 1
            return heads
        return super()._patches() + [patch.object(EffectContext, 'choose', choose),
                                     patch.object(EffectContext, 'flip_until_tails', flip_until_tails),
                                     patch.object(EffectContext, 'present_card_choice', present_card_choice)]


def set_zone(t, pid, zone, n, spec=None):
    area = t.board.find_player_area(pid, {'hand': 'hand', 'deck': 'deck',
                                          'prizes': 'prizePile', 'discard': 'discard'}[zone])
    for c in list(area.children):
        area.remove_child(c)
    for _ in range(n):
        t.put(spec or t.test.item, pid, zone)


def counts(t):
    return {'hand': len(t.zone(P1, 'hand')), 'deck': len(t.zone(P1, 'deck')),
            'opp_hand': len(t.zone(P2, 'hand')), 'opp_deck': len(t.zone(P2, 'deck')),
            'discard': len(t.zone(P1, 'discard')), 'opp_discard': len(t.zone(P2, 'discard'))}


class Ctx:
    pass


def energy_def(test, kind):
    return CARD_DEFS_BY_GUID[test.energies[kind.value].lower()]


def scn(name, **k):
    k['name'] = name
    return k


async def run_scenario(test, kind, d, ability, s):
    """kind: attack | ability | trainer | stadium.  Returns (ok, detail)."""
    t = DrawTable(test)
    t.heads = s.get('heads', True)
    if 'yes' in s:
        t.yes = s['yes']
    if 'picks' in s:
        t.picks = s['picks']
    if 'pokemon' in s:
        t.pokemon = s['pokemon']
    if 'choice' in s:
        t.choice = s['choice']
    c = Ctx()
    c.t = t
    where = s.get('where', 'active')
    if kind in ('attack', 'ability') and where == 'active':
        c.me = t.put(d, P1, 'active')
        neutral(c.me)
        c.my_bench = [neutral(t.put(test.filler, P1, 'bench')) for _ in range(s.get('my_bench', 1))]
    elif kind == 'ability' and where in ('hand', 'discard'):
        neutral(t.put(test.filler, P1, 'active'))
        c.me = None
        c.my_bench = [neutral(t.put(test.filler, P1, 'bench')) for _ in range(s.get('my_bench', 1))]
    elif kind in ('attack', 'ability'):
        neutral(t.put(test.filler, P1, 'active'))
        c.me = neutral(t.put(d, P1, 'bench'))
        c.my_bench = [neutral(t.put(test.filler, P1, 'bench')) for _ in range(s.get('my_bench', 1) - 1)]
    else:
        c.me = neutral(t.put(s.get('my_active', test.filler), P1, 'active'))
        c.my_bench = [neutral(t.put(test.filler, P1, 'bench')) for _ in range(s.get('my_bench', 1))]
    c.opp = neutral(t.put(s.get('opp_active', test.filler), P2, 'active'))
    c.opp_bench = [neutral(t.put(test.filler, P2, 'bench')) for _ in range(s.get('opp_bench', 1))]
    if kind == 'attack':
        pay_cost(t, c.me, ability)
    set_zone(t, P1, 'deck', s.get('deck', 30))
    set_zone(t, P2, 'deck', s.get('opp_deck', 30))
    set_zone(t, P1, 'hand', s.get('hand', 2))
    set_zone(t, P2, 'hand', s.get('opp_hand', 4))
    set_zone(t, P1, 'prizes', s.get('prizes', 6))
    set_zone(t, P2, 'prizes', s.get('opp_prizes', 6))
    for spec in s.get('hand_specs', ()):
        t.put(spec(test) if callable(spec) else spec, P1, 'hand')
    if c.me is None:
        c.me = t.put(d, P1, where)
    c.card = None
    if kind == 'trainer':
        c.card = t.put(d, P1, 'hand')
    elif kind == 'stadium':
        c.card = t.stadium(d, s.get('stadium_owner', P1))
    if s.get('setup'):
        s['setup'](c)
    c.before = counts(t)
    # ---- act
    if kind == 'attack':
        entry = t.attack_offer(c.me, ability.title)
    elif kind == 'ability':
        entry = t.ability_offer(c.me, ability.title)
    elif kind == 'trainer':
        entry = next((e for e in t.offers(c.card, None, P1) if e['selectableAction']['description']
                      in ('UseTrainerCard', 'DefaultToolPlayAbility', 'DefaultStadiumPlayAbility')), None)
    else:
        entry = next(iter(t.offers(c.card, None, P1)), None)
    offered = s.get('offered', True)
    if entry is None:
        if offered is False or offered is None:
            return True, f"{s['name']}: not offered (ok)"
        return False, f"{s['name']}: not offered"
    if offered is False:
        # still run it, to tell "free effect" apart from "button that does nothing"
        await t.do(entry)
        after = counts(t)
        return False, (f"{s['name']}: offered but should not be (using it anyway: hand {c.before['hand']}->"
                       f"{after['hand']}, deck {c.before['deck']}->{after['deck']}, opp hand {c.before['opp_hand']}->"
                       f"{after['opp_hand']})")
    await t.do(entry)
    c.after = counts(t)
    want = s['want'](c) if callable(s.get('want')) else s.get('want', {})
    if isinstance(want, tuple):           # custom judge
        ok, detail = want
        return ok, f"{s['name']}: {detail}"
    bad = []
    for key, val in want.items():
        got = c.after.get(key) if key in c.after else None
        if key == 'me_ko':
            got = c.me not in t.board.pokemon_in_play(P1)
        if key == 'me_damage':
            got = BIG - t.hp(c.me)
        if key == 'me_energy':
            got = len(t.board.attached_energies(c.me))
        if key == 'asleep':
            got = 'Asleep' in t.conditions(c.me)
        if got != val:
            bad.append(f"{key} {got} (want {val})")
    if bad:
        return False, f"{s['name']}: " + ', '.join(bad) + f" | before {c.before}"
    return True, f"{s['name']}: ok"


async def run_all(test, kind, d, ability, scenarios):
    probs, notes = [], []
    for s in scenarios:
        try:
            ok, detail = await run_scenario(test, s.get('kind', kind), d, ability, s)
        except Exception as ex:
            ok, detail = False, f"{s['name']}: ERROR {type(ex).__name__}: {ex}"
        (notes if ok else probs).append(detail)
    return (not probs), '; '.join(probs) if probs else '; '.join(notes)


# ------------------------------------------------------------ expectations --
def W(**k):
    """Expected final counts relative to the defaults (hand 2, deck 30, opp hand 4, opp deck 30)."""
    return k


def draw_n_expect(n, hand=2, deck=30, extra_hand=0):
    got = min(n, deck)
    return W(hand=hand + extra_hand + got, deck=deck - got)


def until_expect(n, hand=2, deck=30):
    got = max(0, min(n - hand, deck))
    return W(hand=hand + got, deck=deck - got)


# ======================================================== ATTACK templates ==
def attack_plans(text, d, a):
    m = re.fullmatch(r"(you may )?draw cards until you have (\d+) cards in your hand\.", text)
    if m:
        n = int(m.group(2))
        out = [scn('hand 2', hand=2, want=until_expect(n)),
               scn('hand at target', hand=n, want=W(hand=n, deck=30)),
               scn('hand above target', hand=n + 1, want=W(hand=n + 1, deck=30)),
               scn('deck smaller', hand=0, deck=2, want=W(hand=2, deck=0))]
        if m.group(1):
            out.append(scn('declined', hand=2, yes=False, want=W(hand=2, deck=30)))
        return out
    m = re.fullmatch(r"this pokémon is now asleep\. draw cards until you have (\d+) cards in your hand\.", text)
    if m:
        n = int(m.group(1))
        return [scn('hand 2', hand=2, want=dict(until_expect(n), asleep=True)),
                scn('hand above', hand=n + 1, want=W(hand=n + 1, deck=30, asleep=True))]
    m = re.fullmatch(r"(?:if you go first, you can use this attack (?:during|on) your first turn\. )?"
                     r"(shuffle your hand into your deck\. then,|discard your hand and) draw (\d+) cards\.", text)
    if m:
        n, shuffle = int(m.group(2)), m.group(1).startswith('shuffle')
        return [scn('hand 3', hand=3, want=W(hand=n, deck=33 - n if shuffle else 30 - n,
                                              discard=(0 if shuffle else 3))),
                scn('empty hand', hand=0, want=W(hand=n, deck=30 - n)),
                scn('deck smaller', hand=1, deck=2, want=W(hand=3 if shuffle else 2, deck=0))]
    m = re.fullmatch(r"if you go first, you can use this attack on your first turn\. draw (\d+) cards\.", text)
    if m:
        return [scn('normal turn', want=draw_n_expect(int(m.group(1))))]
    m = re.fullmatch(r"each player draws (a|\d+) cards?\.", text)
    if m:
        n = num(m.group(1))
        return [scn('both draw', want=W(hand=2 + n, deck=30 - n, opp_hand=4 + n, opp_deck=30 - n)),
                scn('my deck smaller', deck=1, want=W(hand=3, deck=0, opp_hand=4 + n))]
    m = re.fullmatch(r"each player reveals the top (\d+) cards of their deck, then draws those cards\.", text)
    if m:
        n = int(m.group(1))
        return [scn('both draw', want=W(hand=2 + n, deck=30 - n, opp_hand=4 + n, opp_deck=30 - n))]
    if text == "your opponent draws a card.":
        return [scn('opp draws', want=W(hand=2, deck=30, opp_hand=5, opp_deck=29))]
    m = re.fullmatch(r"(?:you may have )?your opponent shuffles? " + HIS + r" hand into " + HIS +
                     r" deck(?:\. if you do, your opponent| and) draws? (\d+) cards\.", text)
    if m:
        n = int(m.group(1))
        out = [scn('opp hand 6', opp_hand=6, want=W(hand=2, deck=30, opp_hand=n, opp_deck=36 - n)),
               scn('opp hand 0', opp_hand=0, want=W(hand=2, opp_hand=n, opp_deck=30 - n))]
        if text.startswith('you may'):
            out.append(scn('declined', opp_hand=6, yes=False, want=W(hand=2, opp_hand=6, opp_deck=30)))
        return out
    m = re.fullmatch(r"your opponent shuffles their hand and puts it on the bottom of their deck\. if they put any "
                     r"cards on the bottom of their deck in this way, they draw (\d+) cards\.", text)
    if m:
        n = int(m.group(1))
        return [scn('opp hand 6', opp_hand=6, want=W(hand=2, opp_hand=n, opp_deck=36 - n)),
                scn('opp hand 0', opp_hand=0, want=W(hand=2, opp_hand=0, opp_deck=30))]
    m = re.fullmatch(r"(discard|put) (a|an) ?(basic energy|fire energy|water energy|lightning energy|grass energy|)"
                     r" ?card from your hand(?: in the lost zone)?\. if you do, draw (\d+) cards\.", text)
    if m:
        what, n = m.group(3), int(m.group(4))
        if what:
            t_ = TYPES.get(what.split()[0], PokemonTypes.FIRE)
            spec = (lambda test, t_=t_: energy_def(test, t_))
            return [scn('with ' + what, hand=2, hand_specs=[spec], want=W(hand=2 + n, deck=30 - n)),
                    scn('no ' + what, hand=2, want=W(hand=2, deck=30))]
        return [scn('with a card', hand=2, want=W(hand=1 + n, deck=30 - n)),
                scn('empty hand', hand=0, want=W(hand=0, deck=30))]
    m = re.fullmatch(r"draw (a|\d+) cards?\. (?:if you do, )?this pokémon is now asleep\.", text) or \
        re.fullmatch(r"this pokémon is now asleep\. draw (a|\d+) cards?\.", text)
    if m:
        n = num(m.group(1))
        out = [scn('draw + asleep', want=dict(draw_n_expect(n), asleep=True))]
        if 'if you do' in text:
            out.append(scn('empty deck: no draw, not asleep', deck=0, want=W(hand=2, deck=0, asleep=False)))
        return out
    m = re.fullmatch(r"shuffle your hand into your deck\. then, (?:draw a card for each card in your opponent's hand|"
                     r"draw a number of cards equal to the number of cards in your opponent's hand)\.", text)
    if m:
        return [scn('opp hand 5', hand=2, opp_hand=5, want=W(hand=5, deck=27, opp_hand=5)),
                scn('opp hand 0', hand=2, opp_hand=0, want=W(hand=0, deck=32))]
    m = re.fullmatch(r"shuffle your hand into your deck\. then, (?:draw a card for each benched pokémon|draw a number "
                     r"of cards equal to the number of benched pokémon) \(both yours and your opponent's\)\.", text)
    if m:
        return [scn('2+3 benched', hand=2, my_bench=2, opp_bench=3, want=W(hand=5, deck=27))]
    m = re.fullmatch(r"draw a card for each psychic energy attached to this pokémon\.", text)
    if m:
        def want(c):
            n = sum(1 for e in c.t.board.attached_energies(c.me)
                    if getattr(def_for(e.archetype_id), 'energy_type', None) == PokemonTypes.PSYCHIC)
            return W(hand=2 + n, deck=30 - n)
        return [scn('+2 psychic', setup=lambda c: c.t.energy(c.me, PokemonTypes.PSYCHIC, 2), want=want)]
    m = re.fullmatch(r"draw a card for each of your (\w+) in play\.", text)
    if m:
        nm = m.group(1)
        same = d.display_name.lower() == nm
        def setup(c, nm=nm):
            other = next((x for x in CARD_DEFS_BY_GUID.values() if isinstance(x, PokemonCardDef)
                          and x.display_name.lower() == nm), None)
            neutral(c.t.put(other, P1, 'bench'))
            neutral(c.t.put(other, P2, 'bench'))         # opponent's don't count
        n = 1 + (1 if same else 0)
        return [scn('one more ' + nm, setup=setup, want=W(hand=2 + n, deck=30 - n))]
    m = re.fullmatch(r"draw (a|\d+) cards?\. if (\w+) is on your bench, draw (\d+) more cards?\.", text) or \
        re.fullmatch(r"shuffle your hand into your deck\. then, draw (\d+) cards\. if (\w+) is on your bench, "
                     r"draw (\d+) more cards\.", text)
    if m:
        n, nm, extra = num(m.group(1)), m.group(2), int(m.group(3))
        shuffle = text.startswith('shuffle')
        def setup(c, nm=nm):
            other = next(x for x in CARD_DEFS_BY_GUID.values() if isinstance(x, PokemonCardDef)
                         and x.display_name.lower() == nm)
            neutral(c.t.put(other, P1, 'bench'))
        def opp_setup(c, nm=nm):
            other = next(x for x in CARD_DEFS_BY_GUID.values() if isinstance(x, PokemonCardDef)
                         and x.display_name.lower() == nm)
            neutral(c.t.put(other, P2, 'bench'))
        h0 = 0 if shuffle else 2
        return [scn('without ' + nm, want=W(hand=h0 + n)),
                scn('with ' + nm, setup=setup, want=W(hand=h0 + n + extra)),
                scn(nm + ' on opp bench', setup=opp_setup, want=W(hand=h0 + n))]
    m = re.fullmatch(r"if (\w+) is on your bench, draw (\d+) cards\.", text)
    if m:
        nm, n = m.group(1), int(m.group(2))
        def setup(c, nm=nm):
            other = next(x for x in CARD_DEFS_BY_GUID.values() if isinstance(x, PokemonCardDef)
                         and x.display_name.lower() == nm)
            neutral(c.t.put(other, P1, 'bench'))
        return [scn('without ' + nm, want=W(hand=2, deck=30)),
                scn('with ' + nm, setup=setup, want=W(hand=2 + n, deck=30 - n))]
    if text == "draw cards until you have the same number of cards in your hand as your opponent.":
        return [scn('opp 5 me 2', hand=2, opp_hand=5, want=W(hand=5, deck=27, opp_hand=5)),
                scn('opp 2 me 4', hand=4, opp_hand=2, want=W(hand=4, deck=30)),
                scn('deck smaller', hand=0, opp_hand=5, deck=2, want=W(hand=2, deck=0))]
    m = re.fullmatch(r"you may discard any number of cards from your hand(?: until you have 4 or fewer)?\.(?: then,)? "
                     r"draw cards until you have (\d+) cards in your hand\.", text)
    if m:
        n = int(m.group(1))
        return [scn('keep hand 2', hand=2, picks=lambda cards, cnt, p, dc: [], want=W(hand=n, discard=0)),
                scn('discard all 3', hand=3, picks=lambda cards, cnt, p, dc: cards[:3],
                    want=W(hand=n, discard=3))]
    if text == ("each player either draws or discards cards until that player has 4 cards in his or her hand. "
                "(your opponent does this first.)"):
        return [scn('me 1, opp 6', hand=1, opp_hand=6, want=W(hand=4, deck=27, opp_hand=4, opp_deck=30)),
                scn('me 6, opp 1', hand=6, opp_hand=1, want=W(hand=4, deck=30, opp_hand=4, opp_deck=27))]
    if text == "draw 2 cards. then, put a card from your hand on the bottom of your deck.":
        return [scn('net +1', want=W(hand=3, deck=29))]
    m = re.fullmatch(r"draw (a|\d+) cards?\. (?:you may )?switch this pokémon with 1 of your benched pokémon\.", text)
    if m:
        n = num(m.group(1))
        return [scn('draw', want=draw_n_expect(n))]
    if text == ("look at the top card of your deck. you may put that card into your hand. if you don't, discard "
                "that card and draw a card."):
        return [scn('take it', yes=True, choice=0, want=W(hand=3, deck=29, discard=0)),
                scn('discard it, draw', yes=False, choice=1, picks=lambda cards, cnt, p, dc: [],
                    want=W(hand=3, deck=28))]
    if text == "flip a coin. if heads, draw a card.":
        return [scn('heads', heads=True, want=W(hand=3, deck=29)),
                scn('tails', heads=False, want=W(hand=2, deck=30))]
    if text == "flip a coin until you get tails. for each heads, draw a card.":
        return [scn('H H T', heads=seq_heads([True, True, False]), want=W(hand=4, deck=28)),
                scn('T', heads=False, want=W(hand=2, deck=30))]
    m = re.fullmatch(r"draw a card\. if you go second and it's your first turn, draw (\d+) more cards\.", text)
    if m:
        return [scn('normal turn', want=W(hand=3, deck=29)),
                scn('going second, first turn', setup=go_second_first_turn, want=W(hand=3 + int(m.group(1))))]
    m = re.fullmatch(r"draw a card for each of your pokémon in play that has a retreat cost of exactly (\d+)\.", text)
    if m:
        n = int(m.group(1))
        def want(c, n=n):
            k = sum(1 for p in c.t.board.pokemon_in_play(P1) if c.t.retreat(p) == n)
            return W(hand=2 + k, deck=30 - k)
        return [scn('count', want=want)]
    m = re.fullmatch(r"choose a player\. that player shuffles their hand into their deck and draws (\d+) cards\.", text)
    if m:
        n = int(m.group(1))
        return [scn('choose opponent', opp_hand=6, choice=pick_button('opp'),
                    want=W(hand=2, deck=30, opp_hand=n, opp_deck=36 - n)),
                scn('choose me', hand=6, choice=pick_button('me'), want=W(hand=n, deck=36 - n, opp_hand=4))]
    return None


def seq_heads(seq):
    it = iter(seq)
    return lambda title='': next(it, False)


def go_second_first_turn(c):
    t = c.t
    t.state.turn_number = 2
    t.session.first_player_id = P2
    t.board.setup_first_player_id = P2


def pick_button(who):
    def f(prompt, buttons):
        low = [b.lower() for b in buttons]
        for i, b in enumerate(low):
            if who == 'opp' and ('opponent' in b or 'their' in b or 'opp' in b):
                return i
            if who == 'me' and ('you' in b or 'your' in b or 'self' in b or 'me' == b) and 'opponent' not in b:
                return i
        return 0 if who == 'me' else len(buttons) - 1
    return f


# ======================================================= ABILITY templates ==
ONCE = r"once during your turn(?: \(before your attack\))?, "
ACTIVE = r"(?:if this pokémon is (?:your active pokémon|in the active spot), )"


def ability_plans(text, d, a):
    active_only = bool(re.search(ACTIVE, text))
    bench_check = [scn('on Bench (Active only)', where='bench', offered=False)] if active_only else []
    m = re.fullmatch(ONCE + ACTIVE + r"?you may draw cards until you have (\d+) cards in your hand\."
                     r"(?: you can't use more than 1 [\w' ]+ ability each turn\.| if you use this ability, "
                     r"your turn ends\.)?", text)
    if m:
        n = int(m.group(1))
        return [scn('hand 1', hand=1, want=until_expect(n, hand=1)),
                scn('hand at target', hand=n, offered=None, want=W(hand=n, deck=30)),
                scn('deck smaller', hand=0, deck=2, want=W(hand=2, deck=0))] + bench_check
    m = re.fullmatch(ONCE + r"you may draw cards until you have (\d+) cards in your hand\. if you drew any cards in "
                     r"this way, this pokémon is knocked out\.", text)
    if m:
        n = int(m.group(1))
        return [scn('hand 1', hand=1, want=dict(until_expect(n, hand=1), me_ko=True)),
                scn('hand at target', hand=n, offered=None, want=W(hand=n, deck=30, me_ko=False))]
    m = re.fullmatch(r"you must (discard a card|discard 2 cards|discard an energy card|put a card) from your hand"
                     r"(?: on the bottom of your deck)? in order to use this ability\. once during your turn, you may "
                     r"(?:draw (a|\d+) cards?|draw cards until you have (\d+) cards in your hand)\.", text)
    if m:
        cost = 2 if '2 cards' in m.group(1) else 1
        energy = 'energy' in m.group(1)
        to_bottom = m.group(1) == 'put a card'
        n, until = (num(m.group(2)) if m.group(2) else None), (int(m.group(3)) if m.group(3) else None)
        specs = [lambda test: energy_def(test, PokemonTypes.FIRE)] if energy else []
        h = 3 + len(specs)
        after = h - cost
        if n is not None:
            w = W(hand=after + n, deck=30 - n)
        else:
            dr = max(0, until - after)
            w = W(hand=after + dr, deck=30 - dr + (cost if to_bottom else 0))
        return [scn('pay + draw', hand=3, hand_specs=specs, want=w),
                scn('cannot pay', hand=(cost - 1) if not energy else 3, offered=False)]
    m = re.fullmatch(r"you must discard a basic lightning energy from this pokémon in order to use this ability\. "
                     r"once during your turn, you may draw cards until you have (\d+) cards in your hand\.", text)
    if m:
        n = int(m.group(1))
        return [scn('with energy', hand=2, setup=lambda c: c.t.energy(c.me, PokemonTypes.LIGHTNING),
                    want=dict(until_expect(n), me_energy=0)),
                scn('no energy', hand=2, offered=False)]
    m = re.fullmatch(ONCE + r"you may discard (?:a|1) (card|fire energy card|grass energy card) from your hand\. "
                     r"(?:if you do|then), draw (\d+) cards\.", text)
    if m:
        what, n = m.group(1), int(m.group(2))
        if what == 'card':
            return [scn('discard 1', hand=3, want=W(hand=2 + n, deck=30 - n, discard=1)),
                    scn('empty hand', hand=0, offered=None, want=W(hand=0, deck=30))]
        t_ = TYPES[what.split()[0]]
        spec = (lambda test, t_=t_: energy_def(test, t_))
        return [scn('with ' + what, hand=2, hand_specs=[spec], want=W(hand=2 + n, deck=30 - n, discard=1)),
                scn('no ' + what, hand=2, offered=None, want=W(hand=2, deck=30))]
    if re.fullmatch(ONCE + r"you may discard your hand and draw 4 cards\.", text):
        return [scn('hand 3', hand=3, want=W(hand=4, deck=26, discard=3))]
    m = re.fullmatch(ONCE + ACTIVE + r"?you may (?:use this ability\. each player draws a card|have each player "
                     r"draw a card)\.", text)
    if m:
        return [scn('both draw', want=W(hand=3, deck=29, opp_hand=5, opp_deck=29))] + bench_check
    m = re.fullmatch(ONCE + ACTIVE + r"?you may have your opponent shuffle their hand into their deck and draw (\d+) "
                     r"cards\.", text)
    if m:
        n = int(m.group(1))
        return [scn('opp hand 6', opp_hand=6, want=W(hand=2, deck=30, opp_hand=n, opp_deck=36 - n))] + bench_check
    m = re.fullmatch(ONCE + r"you may use this ability\. your opponent shuffles their hand and puts it on the bottom "
                     r"of their deck\. if they put any cards on the bottom of their deck in this way, they draw (\d+) "
                     r"cards\.", text)
    if m:
        n = int(m.group(1))
        return [scn('opp hand 6', opp_hand=6, want=W(hand=2, deck=30, opp_hand=n, opp_deck=36 - n)),
                scn('opp hand 0', opp_hand=0, offered=None, want=W(hand=2, opp_hand=0, opp_deck=30))]
    m = re.fullmatch(ONCE + r"you may choose either player\. that player shuffles his or her hand into his or her "
                     r"deck and draws (\d+) cards\.", text) or \
        re.fullmatch(ONCE + r"you may have either player shuffle their hand and put it on the bottom of their deck\. "
                     r"if that player put any cards on the bottom of their deck in this way, they draw (\d+) cards\.",
                     text)
    if m:
        n = int(m.group(1))
        return [scn('choose opponent', opp_hand=6, choice=pick_button('opp'),
                    want=W(hand=2, deck=30, opp_hand=n, opp_deck=36 - n)),
                scn('choose me', hand=6, choice=pick_button('me'),
                    want=W(hand=n, deck=36 - n, opp_hand=4, opp_deck=30))]
    if re.fullmatch(ONCE + r"you may shuffle your hand and put it on the bottom of your deck\. if you put any cards on "
                    r"the bottom of your deck in this way, draw a card\.", text):
        return [scn('hand 3', hand=3, want=W(hand=1, deck=32)),
                scn('empty hand', hand=0, offered=None, want=W(hand=0, deck=30))]
    if re.fullmatch(ONCE + r"you may put 1 damage counter on this pokémon\. if you do, draw a card\.", text):
        return [scn('draw 1', want=W(hand=3, deck=29, me_damage=10))]
    if re.fullmatch(ONCE + r"you may draw 3 cards\. if you drew any cards in this way, shuffle this pokémon and all "
                    r"attached cards into your deck\.", text):
        def want(c):
            return W(hand=5, deck=27 + 1, me_ko=True)
        return [scn('draw 3, shuffle self', want=want)]
    if re.fullmatch(ONCE + r"you may flip a coin\. if heads, shuffle your hand into your deck and then draw 6 cards\. "
                    r"if you use this ability, your turn ends\.", text):
        return [scn('heads', hand=3, heads=True, want=W(hand=6, deck=27)),
                scn('tails', hand=3, heads=False, want=W(hand=3, deck=30))]
    if re.fullmatch(ONCE + r"if this pokémon is on your bench, you may discard this pokémon and all cards attached "
                    r"to it \(this does not count as a knock out\)\. if you do, draw a card\.", text):
        return [scn('bench', where='bench', my_bench=1, want=W(hand=3, deck=29)),
                scn('active', where='active', offered=False)]
    if re.fullmatch(r"once during your turn, if this pokémon is in your hand, you may reveal it and put it on the "
                    r"bottom of your deck\. if you do, draw a card\. you can't use more than 1 [\w ]+ ability each "
                    r"turn\.", text):
        return [scn('from hand', where='hand', hand=2, want=W(hand=3, deck=30)),
                scn('in play', where='active', offered=False)]
    if re.fullmatch(r"once during your turn, if this pokémon is the last card in your hand, you may play it onto your "
                    r"bench\. if you do, draw 3 cards\.", text):
        return [scn('last card', where='hand', hand=0, want=W(hand=3, deck=27)),
                scn('not last card', where='hand', hand=1, offered=False)]
    if re.fullmatch(r"once during your turn, if this pokémon is in your discard pile and you have no cards in your hand, "
                    r"you may put this pokémon onto your bench\. if you do, draw 3 cards\.", text):
        return [scn('empty hand', where='discard', hand=0, want=W(hand=3, deck=27)),
                scn('1 card in hand', where='discard', hand=1, offered=False)]
    m = re.fullmatch(r"you must discard a pokémon that has the ([\w ]+) attack from your hand in order to use this "
                     r"ability\. once during your turn, you may draw (\d+) cards\.", text)
    if m:
        atk, n = m.group(1), int(m.group(2))
        mate = next((x for x in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number)))
                     if isinstance(x, PokemonCardDef) and any(isinstance(y, Attack) and y.title.lower() == atk
                                                              for y in x.abilities or [])), None)
        return [scn('pay', hand=1, hand_specs=[mate], want=W(hand=1 + n, deck=30 - n)),
                scn('no such pokémon', hand=2, hand_specs=[lambda test: test.filler], offered=False)]
    m = re.fullmatch(r"once during your turn, you may attach a basic psychic energy card from your hand to 1 of your "
                     r"benched pokémon\. if you attached energy to a pokémon in this way, draw (\d+) cards\.", text)
    if m:
        n = int(m.group(1))
        spec = (lambda test: energy_def(test, PokemonTypes.PSYCHIC))
        return [scn('attach + draw', hand=2, hand_specs=[spec], want=W(hand=2 + n, deck=30 - n)),
                scn('no psychic energy', hand=2, offered=None, want=W(hand=2, deck=30))]
    m = re.fullmatch(r"once during your turn, if you have solrock in play, you may discard a basic (?:\[ \[fighting\] \]|"
                     r"fighting) energy card from your hand in order to use this ability\. draw (\d+) cards\. you can't "
                     r"use more than 1 lunar cycle ability each turn\.", text)
    if m:
        n = int(m.group(1))
        spec = (lambda test: energy_def(test, PokemonTypes.FIGHTING))
        def solrock(c):
            s = next(x for x in CARD_DEFS_BY_GUID.values() if isinstance(x, PokemonCardDef)
                     and x.display_name == 'Solrock')
            neutral(c.t.put(s, P1, 'bench'))
        return [scn('with Solrock', hand=2, hand_specs=[spec], setup=solrock, want=W(hand=2 + n, deck=30 - n)),
                scn('no Solrock', hand=2, hand_specs=[spec], offered=False)]
    m = re.fullmatch(r"once during your turn, you may discard a basic (?:\[ \[fire\] \]|fire) energy card from your hand "
                     r"in order to use this ability\. draw cards until you have (\d+) cards in your hand\.", text)
    if m:
        n = int(m.group(1))
        spec = (lambda test: energy_def(test, PokemonTypes.FIRE))
        return [scn('pay + draw', hand=2, hand_specs=[spec], want=until_expect(n, hand=2)),
                scn('no fire energy', hand=2, offered=False)]
    return None


# ------------------------------------------------- evolution-trigger draws --
EVO = r"(?:once during your turn, )?when you play this pokémon from your hand to evolve 1 of your pokémon" \
      r"(?: during your turn)?, you may "


def evolve_plans(text, d, a):
    m = re.fullmatch(EVO + r"use this ability\. draw (\d+) cards\.", text)
    if m:
        n = int(m.group(1))
        return [scn('yes', want=W(hand=2 + n, deck=30 - n)), scn('declined', yes=False, want=W(hand=2, deck=30))]
    if re.fullmatch(EVO + r"have each player draw a card\.", text):
        return [scn('yes', want=W(hand=3, deck=29, opp_hand=5, opp_deck=29)),
                scn('declined', yes=False, want=W(hand=2, opp_hand=4))]
    if re.fullmatch(EVO + r"have each player shuffle their hand and put it on the bottom of their deck\. if either "
                    r"player put any cards on the bottom of their deck in this way, each player draws 4 cards\.", text):
        return [scn('yes', hand=2, opp_hand=6, want=W(hand=4, deck=28, opp_hand=4, opp_deck=32)),
                scn('both hands empty', hand=0, opp_hand=0, want=W(hand=0, opp_hand=0)),
                scn('declined', yes=False, want=W(hand=2, opp_hand=4))]
    if re.fullmatch(EVO + r"have your opponent shuffle his or her hand into his or her deck and draw a card for each "
                    r"of his or her remaining prize cards\.", text):
        return [scn('opp 3 prizes', opp_prizes=3, opp_hand=6, want=W(hand=2, opp_hand=3, opp_deck=33)),
                scn('declined', yes=False, opp_hand=6, want=W(hand=2, opp_hand=6))]
    return None


async def run_evolve(test, d, a, s):
    from tests.test_sweep_abilities import pre_evolution
    t = DrawTable(test)
    t.yes = s.get('yes', True)
    pre = pre_evolution(d)
    if pre is None:
        return None, 'no pre-evolution'
    base = neutral(t.put(pre, P1, 'active'), hp=None)
    neutral(t.put(test.filler, P1, 'bench'))
    neutral(t.put(test.filler, P2, 'active'))
    neutral(t.put(test.filler, P2, 'bench'))
    set_zone(t, P1, 'deck', s.get('deck', 30))
    set_zone(t, P2, 'deck', s.get('opp_deck', 30))
    set_zone(t, P1, 'hand', s.get('hand', 2))
    set_zone(t, P2, 'hand', s.get('opp_hand', 4))
    set_zone(t, P2, 'prizes', s.get('opp_prizes', 6))
    card = t.put(d, P1, 'hand')
    await t.play(card, targets=[base.entity_id])
    # some "once during your turn ... you may use this ability" evolve triggers are offered as a button
    entry = t.ability_offer(t.active(P1), a.title)
    if entry is not None and s.get('yes', True):
        await t.do(entry)
    after = counts(t)
    bad = [f"{k} {after[k]} (want {v})" for k, v in s['want'].items() if after[k] != v]
    return (not bad), f"{s['name']}: " + (', '.join(bad) if bad else 'ok')


# ======================================================= TRAINER templates ==
_JSON = None
_FILES = None


def json_texts():
    global _JSON
    if _JSON is None:
        _JSON = {}
        skip = ('you may play only 1', 'you may play any number', 'you may play as many', 'this card stays',
                'attach a pokémon tool', 'ace spec rule', "you can't have more than 1 ace spec",
                'pokémon tool cards are', 'pokemon tool')
        for f in sorted(glob.glob(os.path.join(CARDS_DIR, '*', '*.json'))):
            with open(f) as fh:
                cards = json.load(fh)
            for c in cards:
                if c.get('supertype') in ('Trainer', 'Energy'):
                    rules = [r for r in c.get('rules', []) if not r.lower().startswith(skip)]
                    if rules:
                        _JSON.setdefault(c['name'], ' '.join(rules))
    return _JSON


def guid_files():
    global _FILES
    if _FILES is None:
        _FILES = {}
        for f in glob.glob(os.path.join(CARDS_DIR, '*', '*.py')):
            with open(f) as fh:
                src = fh.read()
            for g in re.findall(r"guid=['\"]([0-9a-fA-F-]{36})['\"]", src):
                _FILES[g.lower()] = f
    return _FILES


def _file_strings(f, depth=0):
    if not f or depth > 2 or not os.path.exists(f):
        return []
    with open(f) as fh:
        src = fh.read()
    out = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and ' ' in node.value \
                and len(node.value) > 8 and not node.value.startswith('com.'):
            out.append(node.value)
    m = re.search(r"from spirit\.game\.scripts\.cards\.(\w+)\.(\w+) import card", src)
    if m:
        out += _file_strings(os.path.join(CARDS_DIR, m.group(1), m.group(2) + '.py'), depth + 1)
    m = re.search(r"sibling_card\(__file__, ['\"](\w+\.py)['\"]\)", src)
    if m:
        out += _file_strings(os.path.join(os.path.dirname(f), m.group(1)), depth + 1)
    return out


def _closure_strings(fn, depth=0):
    out = []
    if fn is None or depth > 3:
        return out
    for cell in getattr(fn, '__closure__', None) or []:
        try:
            v = cell.cell_contents
        except ValueError:
            continue
        if isinstance(v, str) and ' ' in v and len(v) > 8:
            out.append(v)
        elif callable(v):
            out += _closure_strings(v, depth + 1)
    return out


# Official texts for BW dispatcher cards whose script carries no text.
MANUAL_TEXT = {
    'N': "each player shuffles his or her hand into his or her deck. then, each player draws a card for each "
         "of his or her remaining prize cards.",
    'Colress': "shuffle your hand into your deck. then, draw a card for each benched pokémon (both yours and your "
               "opponent's).",
    'Ghetsis': "your opponent reveals his or her hand. shuffle all item cards you find there into your opponent's "
               "deck. then, draw a card for each card you shuffled into your opponent's deck.",
    'Tropical Beach': "once during each player's turn, that player may draw cards until he or she has 7 cards in his "
                      "or her hand. if he or she does, his or her turn ends.",
}
RULE_SENTENCES = ('you may play only 1 supporter', 'you may play as many item', 'you may play any number of item',
                  'this card stays in play when you play it', 'attach a pokémon tool to 1 of your pokémon',
                  "you can't have more than 1 ace spec", "discard it if another stadium comes into play",
                  "if a stadium with the same name is in play, you can't play this card",
                  "this stadium stays in play when you play it")


def clean(text):
    sents, out = re.split(r'(?<=[.)])\s+', norm(text)), []
    for s in sents:
        if s and s not in out and not s.startswith(RULE_SENTENCES):
            out.append(s)
    return ' '.join(out)


def trainer_text(defs):
    """Best printed text for a trainer name (all its printings): set JSON > rules-text closure >
    script strings > manual."""
    d = defs[0]
    if d.display_name in MANUAL_TEXT:
        return 'manual', MANUAL_TEXT[d.display_name]
    js = json_texts()
    if d.display_name in js:
        return 'json', clean(js[d.display_name])
    for x in defs:
        s = _closure_strings(getattr(x, 'effect', None)) + _closure_strings(getattr(x, 'condition', None))
        s = [v for v in s if 'draw' in v.lower()]
        if s:
            return 'closure', clean(s[0])
    for x in defs:
        doc = getattr(getattr(x, 'effect', None), '__doc__', None)
        if doc and 'draw' in doc.lower() and 'dispatcher' not in doc.lower():
            return 'doc', clean(doc)
    for x in defs:
        s = [v for v in _file_strings(guid_files().get(x.guid.lower())) if 'draw' in v.lower()]
        if s:
            return 'file', clean(min(s, key=len))
    return 'none', ''


def trainer_pool():
    by = collections.OrderedDict()
    for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, str(d.collector_number))):
        if isinstance(d, PokemonCardDef) or not glc.is_glc_legal(d):
            continue
        if isinstance(d, EnergyCardDef) and str(AttrID.IS_SPECIAL_ENERGY.value) not in d.extra_attributes:
            continue
        by.setdefault(d.display_name, []).append(d)
    return by


def item(test):
    return test.item


def stadium_named(name):
    return next((x for x in CARD_DEFS_BY_GUID.values() if x.display_name == name and isinstance(x, StadiumCardDef)),
                None)


def any_stadium(test):
    return next(x for x in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number)))
                if type(x) is StadiumCardDef and glc.is_glc_legal(x))


def poke_named(name):
    return next((x for x in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number)))
                 if isinstance(x, PokemonCardDef) and x.display_name == name), None)


def basic_of_type(type_value, exclude_name=None):
    from tests.test_sweep_abilities import stage_of, types_of
    from spirit.game.attributes import PokemonStage
    for x in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number))):
        if isinstance(x, PokemonCardDef) and stage_of(x) == PokemonStage.BASIC and types_of(x) == [type_value] \
                and not has_ability(x) and x.display_name != exclude_name and glc.is_glc_legal(x):
            return x
    return None


def ko_last_turn(c):
    c.t.state.kos_suffered_last_turn = {P1: [{'name': 'x', 'entity_id': 'gone'}]}
    c.t.state.kos_by_attack_last_turn = {P1: [{'name': 'x', 'entity_id': 'gone'}]}


def trainer_plans(text, d):
    """Scenarios for a Trainer text. Default board: my hand 2 fillers (+ the card), deck 30,
    opp hand 4, opp deck 30, 6 prizes each, 1 Benched Pokémon each."""
    sup = isinstance(d, SupporterCardDef)
    no_deck_rule = "if you have no cards in your deck, you can't play this card." in text
    base = re.sub(r" ?if you have no cards in your deck, you can't play this card\.", '', text).strip()
    extra = [scn('empty deck', deck=0, offered=False)] if no_deck_rule else []
    m = re.fullmatch(r"(?:if you go first, you may play this card during your first turn\. )?draw (\d+) cards\."
                     r"(?: (?:during this turn, your pokémon's attacks do 20 more damage to your opponent's active "
                     r"pokémon \(before applying weakness and resistance\)|look at your face-down prize cards|"
                     r"discard a stadium in play|"
                     r"each player reveals their hand)\.)?", base) or \
        re.fullmatch(r"each player reveals their hand\. draw (\d+) cards\.", base)
    if m:
        n = int(m.group(1))
        return [scn('draw', want=draw_n_expect(n)), scn('deck smaller', deck=1, want=W(hand=3, deck=0))] + extra
    m = re.fullmatch(r"draw (\d+) cards\. put a basic energy card from your discard pile into your hand\.", base)
    if m:
        n = int(m.group(1))
        def disc(c):
            c.t.put(energy_def(c.t.test, PokemonTypes.WATER), P1, 'discard')
        return [scn('energy in discard', setup=disc, want=draw_n_expect(n, extra_hand=1)),
                scn('no energy in discard', offered=None, want=draw_n_expect(n))]
    m = re.fullmatch(r"draw (\d+) cards (?:and heal 20 damage from your active pokémon|from the bottom of your deck)\.",
                     base)
    if m:
        n = int(m.group(1))
        return [scn('draw', want=draw_n_expect(n))] + extra
    m = re.fullmatch(r"(?:playable on your first turn\. )?discard your hand and draw (\d+) cards\.(?: playable on your "
                     r"first turn\.)?", base)
    if m:
        n = int(m.group(1))
        return [scn('hand 3', hand=3, want=W(hand=n, deck=30 - n, discard=4)),
                scn('only card', hand=0, want=W(hand=n, deck=30 - n)),
                scn('deck smaller', hand=2, deck=3, want=W(hand=3, deck=0))]
    m = re.fullmatch(r"(?:you can (?:use|play) this card only if (.+?)\. )?shuffle your hand into your deck\. then, "
                     r"draw (\d+) cards\.(?: your turn ends\.)?", base)
    if m:
        cond, n = m.group(1), int(m.group(2))
        setup = None
        if cond == "your opponent's active pokémon is poisoned":
            def setup(c):
                c.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])
            neg = scn('opp not poisoned', offered=False)
        elif cond:
            return None
        else:
            neg = None
        out = [scn('hand 3', hand=3, setup=setup, want=W(hand=n, deck=33 - n, opp_hand=4)),
               scn('only card', hand=0, setup=setup, want=W(hand=n, deck=30 - n))]
        return out + ([neg] if neg else [])
    m = re.fullmatch(r"draw cards until you have (\d+) cards in your hand\.(?: your turn ends\.)?", base)
    if m:
        n = int(m.group(1))
        return [scn('hand 2', hand=2, want=until_expect(n)),
                scn('hand at target', hand=n, offered=None, want=W(hand=n, deck=30)),
                scn('deck smaller', hand=0, deck=2, want=W(hand=2, deck=0))]
    m = re.fullmatch(r"at the end of this turn, draw cards until you have (\d+) cards in your hand\.", base)
    if m:
        return None           # end-of-turn trigger: manual
    m = re.fullmatch(r"each player shuffles (?:their|his or her) hand into (?:their|his or her) deck and draws (\d+) "
                     r"cards\.", base)
    if m:
        n = int(m.group(1))
        return [scn('both', hand=3, opp_hand=6, want=W(hand=n, deck=33 - n, opp_hand=n, opp_deck=36 - n))]
    m = re.fullmatch(r"your opponent shuffles (?:their|his or her) hand into (?:their|his or her) deck and draws (\d+) "
                     r"cards\.", base)
    if m:
        n = int(m.group(1))
        return [scn('opp', hand=2, opp_hand=6, want=W(hand=2, deck=30, opp_hand=n, opp_deck=36 - n))]
    m = re.fullmatch(r"your opponent shuffles their hand into their deck and draws a card for each of their remaining "
                     r"prize cards\.", base)
    if m:
        return [scn('opp 3 prizes', opp_prizes=3, opp_hand=6, want=W(hand=2, deck=30, opp_hand=3, opp_deck=33)),
                scn('opp 1 prize', opp_prizes=1, opp_hand=6, want=W(hand=2, opp_hand=1, opp_deck=35))]
    if base == MANUAL_TEXT['N']:
        return [scn('6 vs 2 prizes', hand=3, prizes=6, opp_prizes=2, opp_hand=7,
                    want=W(hand=6, deck=27, opp_hand=2, opp_deck=35)),
                scn('1 vs 4 prizes', hand=0, prizes=1, opp_prizes=4, opp_hand=0,
                    want=W(hand=1, deck=29, opp_hand=4, opp_deck=26))]
    m = re.fullmatch(r"each player shuffles their hand and puts it on the bottom of their deck\. if either player put "
                     r"any cards on the bottom of their deck in this way, each player draws a card for each of their "
                     r"remaining prize cards\.", base)
    if m:
        return [scn('6 vs 2 prizes', hand=3, prizes=6, opp_prizes=2, opp_hand=7,
                    want=W(hand=6, deck=27, opp_hand=2, opp_deck=35)),
                scn('only I have cards (opp hand 0)', hand=1, prizes=3, opp_prizes=2, opp_hand=0,
                    want=W(hand=3, deck=28, opp_hand=2, opp_deck=28)),
                scn('both hands empty', hand=0, opp_hand=0, want=W(hand=0, deck=30, opp_hand=0, opp_deck=30))]
    m = re.fullmatch(r"each player shuffles their hand and puts it on the bottom of their deck\. if either player put "
                     r"any cards on the bottom of their deck in this way, you draw (\d+) cards, and your opponent draws "
                     r"(\d+) cards\.", base)
    if m:
        a_, b_ = int(m.group(1)), int(m.group(2))
        return [scn('both', hand=3, opp_hand=7, want=W(hand=a_, deck=33 - a_, opp_hand=b_, opp_deck=37 - b_)),
                scn('only opp has cards', hand=0, opp_hand=3, want=W(hand=a_, opp_hand=b_))]
    m = re.fullmatch(r"you can use this card only if your opponent has 3 or fewer prize cards remaining\. each player "
                     r"shuffles their hand into their deck\. then, you draw (\d+) cards, and your opponent draws (\d+) "
                     r"cards\.", base)
    if m:
        a_, b_ = int(m.group(1)), int(m.group(2))
        return [scn('opp 3 prizes', opp_prizes=3, hand=2, opp_hand=6,
                    want=W(hand=a_, deck=32 - a_, opp_hand=b_, opp_deck=36 - b_)),
                scn('opp 4 prizes', opp_prizes=4, offered=False)]
    m = re.fullmatch(r"you can play this card only if you have more prize cards left than your opponent\. each player "
                     r"shuffles his or her hand into his or her deck\. then, draw (\d+) cards\. your opponent draws (\d+) "
                     r"cards\.", base)
    if m:
        a_, b_ = int(m.group(1)), int(m.group(2))
        return [scn('6 vs 5 prizes', opp_prizes=5, hand=2, opp_hand=6,
                    want=W(hand=a_, deck=32 - a_, opp_hand=b_, opp_deck=36 - b_)),
                scn('equal prizes', offered=False)]
    m = re.fullmatch(r"each player shuffles their hand into their deck; you draw (\d+), opponent (\d+)\.", base)
    if m:   # Team Rocket's Archer (paraphrased script text; condition not stated)
        return None
    # conditional "draw 2 cards. if X, draw 2 more cards."
    m = re.fullmatch(r"draw (\d+) cards\. (?:then, )?if (.+?), draw (\d+) more cards\.", base)
    if m:
        n, cond, more = int(m.group(1)), m.group(2), int(m.group(3))
        pair = cond_scenarios(cond)
        if pair is None:
            return None
        yes_s, no_s = pair
        out = []
        if yes_s is not None:
            out.append(dict(yes_s, name='cond true: ' + cond, want=yes_s.get('want') or draw_n_expect(n + more,
                                                                                               hand=yes_s.get('hand', 2))))
        out.append(dict(no_s, name='cond false: ' + cond, want=no_s.get('want') or draw_n_expect(n,
                                                                                          hand=no_s.get('hand', 2))))
        return out
    m = re.fullmatch(r"draw (\d+) cards\. flip a coin\. if heads, draw (\d+) more cards\.", base)
    if m:
        n, more = int(m.group(1)), int(m.group(2))
        return [scn('heads', heads=True, want=draw_n_expect(n + more)),
                scn('tails', heads=False, want=draw_n_expect(n))]
    m = re.fullmatch(r"flip a coin\. if heads, draw (\d+) cards\.(?: if tails, draw (\d+) cards\.)?", base)
    if m:
        h, tl = int(m.group(1)), int(m.group(2) or 0)
        return [scn('heads', heads=True, want=draw_n_expect(h)), scn('tails', heads=False, want=draw_n_expect(tl))]
    m = re.fullmatch(r"shuffle your hand into your deck(?:\. then,| and) flip a coin\. if heads, draw (\d+) cards\. if "
                     r"tails, draw (\d+) cards\.", base)
    if m:
        h, tl = int(m.group(1)), int(m.group(2))
        return [scn('heads', hand=3, heads=True, want=W(hand=h, deck=33 - h)),
                scn('tails', hand=3, heads=False, want=W(hand=tl, deck=33 - tl))]
    if base == "flip a coin until you get tails. for each heads, draw a card.":
        return [scn('H H H T', heads=seq_heads([True, True, True, False]), want=draw_n_expect(3)),
                scn('T', heads=False, want=draw_n_expect(0))]
    m = re.fullmatch(r"each player shuffles their hand into their deck and flips a coin\. if heads, that player draws "
                     r"(\d+) cards\. if tails, they draw (\d+) cards\.", base) or \
        re.fullmatch(r"each player shuffles their hand and puts it on the bottom of their deck\. if either player put "
                     r"any cards on the bottom of their deck in this way, each player flips a coin\. if heads, that "
                     r"player draws (\d+) cards\. if tails, they draw (\d+) cards\.", base)
    if m:
        h, tl = int(m.group(1)), int(m.group(2))
        return [scn('both heads', hand=2, opp_hand=5, heads=True, want=W(hand=h, deck=32 - h, opp_hand=h,
                                                                         opp_deck=35 - h)),
                scn('both tails', hand=2, opp_hand=5, heads=False, want=W(hand=tl, deck=32 - tl, opp_hand=tl,
                                                                          opp_deck=35 - tl)),
                scn('one heads, one tails', hand=2, opp_hand=5, heads=seq_heads([True, False]),
                    want=lambda c: (sorted([c.after['hand'], c.after['opp_hand']]) == sorted([h, tl]),
                                    f"hands me {c.after['hand']} / opp {c.after['opp_hand']}, want {{{h}, {tl}}}"))]
    m = re.fullmatch(r"each player shuffles their hand into their deck\. then, flip a coin\. if heads, you draw (\d+) "
                     r"cards, and your opponent draws (\d+) cards\. if tails, you draw (\d+) cards, and your opponent "
                     r"draws (\d+) cards\.", base)
    if m:
        a_, b_, c_, d_ = map(int, m.groups())
        return [scn('heads', hand=2, opp_hand=6, heads=True, want=W(hand=a_, deck=32 - a_, opp_hand=b_,
                                                                    opp_deck=36 - b_)),
                scn('tails', hand=2, opp_hand=6, heads=False, want=W(hand=c_, deck=32 - c_, opp_hand=d_,
                                                                     opp_deck=36 - d_))]
    # draw-for-each
    plans = for_each_plans(base, d)
    if plans is not None:
        return plans
    plans = cost_plans(base, d)
    if plans is not None:
        return plans
    plans = until_variant_plans(base, d)
    if plans is not None:
        return plans
    plans = misc_trainer_plans(base, d)
    if plans is not None:
        return plans
    return extra_trainer_plans(base, d)


def cond_scenarios(cond):
    """(scenario-overrides when true, when false) for 'draw N. if <cond>, draw M more.'"""
    if cond == "your opponent has 3 or fewer prize cards remaining":
        return scn('', opp_prizes=3), scn('', opp_prizes=4)
    if cond == "your opponent has exactly 2, 4, or 6 prize cards remaining":
        return scn('', opp_prizes=4), scn('', opp_prizes=3)
    if cond == "your opponent has exactly 1, 3, or 5 prize cards remaining":
        return scn('', opp_prizes=5), scn('', opp_prizes=6)
    if cond == "you have a stadium in play":
        return scn('', setup=lambda c: c.t.stadium(any_stadium(c.t.test), P1)), \
            scn('', setup=lambda c: c.t.stadium(any_stadium(c.t.test), P2))
    if cond == "wyndon stadium is in play":
        st = stadium_named('Wyndon Stadium')
        return (scn('', setup=lambda c: c.t.stadium(st, P2)) if st else None), scn('')
    if cond == "any of your pokémon were knocked out during your opponent's last turn":
        return scn('', setup=ko_last_turn), scn('')
    if cond == "you have 10 or more cards in your hand":
        # 2 drawn first: hand 8 + 2 = 10 -> 2 more; hand 7 + 2 = 9 -> none
        return scn('', hand=8), scn('', hand=7)
    if cond == "both active pokémon are the same type":
        def same(c):
            pass
        def diff(c):
            tv = PokemonTypes.FIRE.value
            x = basic_of_type(tv)
            from tests.test_sweep_abilities import types_of
            if x is not None and types_of(x) != [v for v in (c.me.get_attribute(AttrID.POKEMON_TYPES) or [])]:
                old = c.opp
                c.t.board.move_card(old.entity_id, c.t.board.find_player_area(P2, 'discard').entity_id)
                c.opp = neutral(c.t.put(x, P2, 'active'))
        return scn('', setup=same), scn('', setup=diff)
    if cond == "your active pokémon has \"hisuian\" in its name":
        hp_ = next((x for x in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number)))
                    if isinstance(x, PokemonCardDef) and x.display_name.startswith('Hisuian')), None)
        return (scn('', my_active=hp_) if hp_ else None), scn('')
    if cond in ("your opponent's active pokémon is a pokémon ex", "your opponent's active pokémon is a pokémon vmax",
                "your active pokémon is a tag team pokémon"):
        return None, scn('')            # no Rule Box Pokémon in the pool: only the false case
    if cond == "you go second and it's your first turn":
        return scn('', setup=go_second_first_turn), scn('')
    return None


def for_each_plans(base, d):
    m = re.fullmatch(r"(?:you can (?:use|play) this card only (when it is the last card in your hand|if you have 4 or "
                     r"fewer other cards in your hand|if you discard (?:another card|2 other cards) from your hand)\. )?"
                     r"draw (?:a card|(\d+) cards) for each (.+?)\.", base)
    if not m:
        return None
    cond, per, what = m.group(1), int(m.group(2) or 1), m.group(3)
    hand, specs, cost = 2, [], 0
    neg = []
    if cond == 'when it is the last card in your hand':
        hand = 0
        neg = [scn('not last card', hand=1, offered=False)]
    elif cond == 'if you have 4 or fewer other cards in your hand':
        hand = 4
        neg = [scn('5 other cards', hand=5, offered=False)]
    elif cond == 'if you discard another card from your hand':
        cost = 1
        neg = [scn('no other card', hand=0, offered=False)]
    elif cond == 'if you discard 2 other cards from your hand':
        hand, cost = 3, 2
        neg = [scn('only 1 other card', hand=1, offered=False)]
    h0 = hand - cost
    if what == "of your opponent's benched pokémon":
        return [scn('opp bench 3', hand=hand, opp_bench=3, want=W(hand=h0 + 3 * per, deck=30 - 3 * per)),
                scn('opp bench 0', hand=hand, opp_bench=0, offered=None, want=W(hand=h0, deck=30))] + neg
    if what == "of your opponent's pokémon in play":
        return [scn('opp 1+2', hand=hand, opp_bench=2, want=W(hand=h0 + 3 * per, deck=30 - 3 * per))] + neg
    if what == "of your opponent's benched basic pokémon":
        def setup(c):
            from tests.test_sweep_abilities import pool
            st1 = pool(c.t.test)['stage1']
            neutral(c.t.put(st1, P2, 'bench'))
        return [scn('2 basics + 1 stage1 on opp bench', hand=hand, opp_bench=2, setup=setup,
                    want=W(hand=h0 + 2 * per, deck=30 - 2 * per))] + neg
    if what == "benched pokémon (both yours and your opponent's)":
        return [scn('2+3 benched', hand=hand, my_bench=2, opp_bench=3, want=W(hand=h0 + 5 * per,
                                                                              deck=30 - 5 * per))] + neg
    if what == "fire pokémon you have in play":
        fire = basic_of_type(PokemonTypes.FIRE.value)
        def setup(c, fire=fire):
            neutral(c.t.put(fire, P1, 'bench'))
            neutral(c.t.put(fire, P1, 'bench'))
            neutral(c.t.put(fire, P2, 'bench'))
        return [scn('2 fire mine, 1 opp', hand=hand, setup=setup, want=W(hand=h0 + 2 * per, deck=30 - 2 * per))] + neg
    if what in ("of your opponent's benched pokémon v", "of your opponent's mega evolution pokémon ex in play"):
        return [scn('none in pool', hand=hand, offered=None, want=W(hand=h0, deck=30))] + neg
    if what == "card in your opponent's hand":
        return [scn('opp hand 5', hand=3, opp_hand=5, want=W(hand=5))]
    return None


def opp_hand_with(kinds):
    """setup: replace opponent's hand with given card kinds ('item', 'supporter', 'pokemon', 'energy')."""
    def setup(c):
        from tests.test_sweep_abilities import pool
        P = pool(c.t.test)
        set_zone(c.t, P2, 'hand', 0)
        for k in kinds:
            spec = {'item': c.t.test.item, 'supporter': P['supporter'], 'pokemon': c.t.test.filler,
                    'energy': energy_def(c.t.test, PokemonTypes.WATER)}[k]
            c.t.put(spec, P2, 'hand')
    return setup


def cost_plans(base, d):
    m = re.fullmatch(r"discard (\d+|a) cards? from your hand\. (?:\(if you can't discard (?:a card|\d+ cards), you can't "
                     r"play this card\.\) )?(?:if you do, )?draw (\d+) cards\.", base)
    if m:
        k, n = num(m.group(1)), int(m.group(2))
        return [scn('pay', hand=k + 1, want=W(hand=1 + n, deck=30 - n)),
                scn('cannot pay', hand=k - 1, offered=False)]
    m = re.fullmatch(r"discard a (fire) energy card from your hand\. \(if you can't discard a fire energy card, you can't "
                     r"play this card\.\) draw (\d+) cards\.", base)
    if m:
        n = int(m.group(2))
        spec = (lambda test: energy_def(test, PokemonTypes.FIRE))
        return [scn('pay', hand=2, hand_specs=[spec], want=W(hand=2 + n, deck=30 - n)),
                scn('no fire energy', hand=2, offered=False)]
    m = re.fullmatch(r"discard a card from your hand\. \(if you can't discard a card, you can't play this card\.\) draw 3 "
                     r"cards\. if you discarded a team (aqua|magma) pokémon, draw 1 more card\.", base)
    if m:
        return [scn('discard filler', hand=2, want=W(hand=4, deck=27)), scn('cannot pay', hand=0, offered=False)]
    m = re.fullmatch(r"discard a card from your hand\. if you do, draw 2 cards\. if you discarded an energy card in this "
                     r"way, draw 2 more cards\.", base)
    if m:
        spec = (lambda test: energy_def(test, PokemonTypes.WATER))
        return [scn('discard item', hand=1, want=W(hand=2, deck=28)),
                scn('discard energy', hand=0, hand_specs=[spec], want=W(hand=4, deck=26)),
                scn('empty hand', hand=0, offered=None, want=W(hand=0, deck=30))]
    m = re.fullmatch(r"shuffle (a|\d+) cards? from your hand into your deck\. (?:\(if you can't shuffle \d+ cards into your "
                     r"deck, you can't play this card\.\) then,|if you do,) draw (a card|\d+ cards)\.", base)
    if m:
        k = num(m.group(1))
        n = 1 if m.group(2) == 'a card' else int(m.group(2).split()[0])
        return [scn('pay', hand=k + 1, want=W(hand=1 + n, deck=30 + k - n)),
                scn('cannot pay', hand=k - 1, offered=None if k == 1 else False,
                    want=W(hand=k - 1, deck=30))]
    m = re.fullmatch(r"put 2 cards from your hand in the lost zone\. if you do, draw a card\.", base)
    if m:
        return [scn('pay', hand=3, want=W(hand=2, deck=29)), scn('cannot pay', hand=1, offered=False)]
    m = re.fullmatch(r"put 2 cards from your hand on the bottom of your deck in any order\. if you put 2 cards on the "
                     r"bottom of your deck in this way, draw 4 cards\. \(if you can't put 2 cards from your hand on the "
                     r"bottom of your deck, you can't use this card\.\)", base)
    if m:
        return [scn('pay', hand=3, want=W(hand=5, deck=28)), scn('cannot pay', hand=1, offered=False)]
    m = re.fullmatch(r"put a card from your hand on the bottom of your deck\. if you do, draw cards until you have 5 cards "
                     r"in your hand\. \(if you have no other cards in your hand, you can't use this card\.\)", base)
    if m:
        return [scn('pay', hand=2, want=W(hand=5, deck=27)), scn('no other card', hand=0, offered=False),
                scn('hand big', hand=7, want=W(hand=6, deck=31))]
    m = re.fullmatch(r"you can use this card only if you discard another card from your hand\. draw cards until you have "
                     r"(\d+) cards in your hand\.", base)
    if m:
        n = int(m.group(1))
        return [scn('pay', hand=2, want=W(hand=n, deck=30 - (n - 1))), scn('no other card', hand=0, offered=False)]
    m = re.fullmatch(r"choose a card in your hand, and discard the other cards\. if you do, draw 4 cards\. \(if you have "
                     r"no other cards in your hand, you can't use this card\.\)", base)
    if m:
        return [scn('hand 3', hand=3, want=W(hand=5, deck=26, discard=3)), scn('no other card', hand=0, offered=False)]
    m = re.fullmatch(r"discard up to 2 cards from your hand, and draw 2 cards for each card you discarded in this way\.",
                     base)
    if m:
        return [scn('discard 2', hand=3, picks=lambda cards, cnt, p, dc: cards[:2], want=W(hand=5, deck=26)),
                scn('discard 1', hand=3, picks=lambda cards, cnt, p, dc: cards[:1], want=W(hand=4, deck=28))]
    m = re.fullmatch(r"discard up to 2 (?:pokemon that don't have a rule box|pokémon that aren't pokémon-gx or pokémon-ex"
                     r"|ultra beast cards) from your hand,? (?:and )?draw 3 cards for each card you discarded in this "
                     r"way\.", base)
    if m:
        if 'ultra beast' in base:
            return None
        return [scn('discard 2 pokémon', hand=1, hand_specs=[lambda test: test.filler] * 2,
                    picks=lambda cards, cnt, p, dc: cards[:2], want=W(hand=7, deck=24))]
    m = re.fullmatch(r"put any number of cards from your hand on the bottom of your deck in any order\. then, draw that "
                     r"many cards\.", base)
    if m:
        return [scn('put 2', hand=3, picks=lambda cards, cnt, p, dc: cards[:2], want=W(hand=3, deck=30))]
    m = re.fullmatch(r"your opponent reveals his or her hand\. discard as many cards as you like from your hand\. then, "
                     r"draw that many cards\.", base)
    if m:
        return [scn('discard 2', hand=3, picks=lambda cards, cnt, p, dc: cards[:2], want=W(hand=3, deck=28))]
    m = re.fullmatch(r"(?:you may discard any number of cards from your hand\. then, draw cards until you have 5 cards in "
                     r"your hand\. if you can't draw any cards in this way, you can't play this card\.|draw cards until "
                     r"you have 5 cards in your hand\. before drawing cards, you may discard any number of cards from "
                     r"your hand\. \(if you can't draw any cards in this way, you can't use this card\.\))", base)
    if m:
        return [scn('discard none', hand=2, picks=lambda cards, cnt, p, dc: [], want=W(hand=5, deck=27)),
                scn('hand 6, discard all (RULING: playable?)', hand=6, offered=None,
                    picks=lambda cards, cnt, p, dc: list(cards), want=W(hand=5, deck=25))]
    return None


def until_variant_plans(base, d):
    m = re.fullmatch(r"draw cards until you have (\d+) cards in your hand\. if (.+?), draw cards until you have (\d+) "
                     r"cards in your hand instead\.", base) or \
        re.fullmatch(r"draw cards until you have (\d+) cards in your hand\. if (it's your first turn), draw cards until "
                     r"you have (\d+) cards in your hand\.", base)
    if m:
        n, cond, n2 = int(m.group(1)), m.group(2), int(m.group(3))
        if cond == "any of your pokémon were knocked out during your opponent's last turn":
            yes_setup = ko_last_turn
        elif cond == "none of your pokémon have any energy attached":
            def yes_setup(c):
                pass
            def no_setup(c):
                c.t.energy(c.my_bench[0], PokemonTypes.WATER)
            return [scn('no energy', setup=yes_setup, want=until_expect(n2)),
                    scn('energy on bench', setup=no_setup, want=until_expect(n))]
        elif cond == "it's your first turn":
            yes_setup = go_second_first_turn
        else:
            return None
        return [scn('cond true', setup=yes_setup, want=until_expect(n2)),
                scn('cond false', want=until_expect(n))]
    m = re.fullmatch(r"shuffle your hand into your deck\. then, draw (\d+) cards\. if (.+?), draw (\d+) cards instead\.",
                     base)
    if m:
        n, cond, n2 = int(m.group(1)), m.group(2), int(m.group(3))
        if cond == "you have exactly 6 prize cards remaining":
            t_, f_ = scn('', prizes=6), scn('', prizes=5)
        elif cond == "your opponent has 3 or fewer prize cards remaining":
            t_, f_ = scn('', opp_prizes=3), scn('', opp_prizes=4)
        elif cond == "any of your pokémon were knocked out during your opponent's last turn":
            t_, f_ = scn('', setup=ko_last_turn), scn('')
        elif cond == "your active pokémon is your only pokémon in play":
            t_, f_ = scn('', my_bench=0), scn('')
        elif cond == "you go second and it's your first turn":
            t_, f_ = scn('', setup=go_second_first_turn), scn('')
        else:
            return None
        return [dict(t_, name='cond true: ' + cond, hand=3, want=W(hand=n2, deck=33 - n2)),
                dict(f_, name='cond false: ' + cond, hand=3, want=W(hand=n, deck=33 - n))]
    m = re.fullmatch(r"shuffle your hand into your deck\. if you have used your gx attack, draw 7 cards\. if not, draw 4 "
                     r"cards\.", base)
    if m:
        def gx(c):
            c.t.state.gx_used.add(P1)
        return [scn('GX used', hand=3, setup=gx, want=W(hand=7, deck=26)),
                scn('GX not used', hand=3, want=W(hand=4, deck=29))]
    if base == "draw cards until you have the same number of cards in your hand as your opponent.":
        return [scn('opp 6 me 2', hand=2, opp_hand=6, want=W(hand=6, deck=26, opp_hand=6)),
                scn('opp 2 me 3', hand=3, opp_hand=2, offered=None, want=W(hand=3, deck=30))]
    if base == "draw cards until you have 1 more card in your hand than your opponent.":
        return [scn('opp 5 me 2', hand=2, opp_hand=5, want=W(hand=6, deck=26, opp_hand=5)),
                scn('opp 2 me 4', hand=4, opp_hand=2, offered=None, want=W(hand=4, deck=30))]
    return None


def misc_trainer_plans(base, d):
    if base == ("look at the top card of your deck. you may put that card into your hand. if you don't, discard that "
                "card and draw a card."):
        return [scn('take it', yes=True, choice=0, want=W(hand=3, deck=29)),
                scn('discard it, draw', yes=False, choice=1, picks=lambda cards, cnt, p, dc: [],
                    want=W(hand=3, deck=28, discard=2))]
    if base == "count the cards in your hand, shuffle those cards into your deck, then draw that many cards plus 1.":
        return [scn('hand 3', hand=3, want=W(hand=4, deck=29)), scn('only card', hand=0, want=W(hand=1, deck=29))]
    if base == ("each player counts the cards in their hand, shuffles those cards into their deck, then draws that many "
                "cards."):
        return [scn('3 / 6', hand=3, opp_hand=6, want=W(hand=3, deck=30, opp_hand=6, opp_deck=30))]
    if base == ("your opponent counts the cards in their hand, shuffles those cards, and puts them on the bottom of their "
                "deck. if they do, they draw that many cards."):
        return [scn('opp 6', hand=2, opp_hand=6, want=W(hand=2, deck=30, opp_hand=6, opp_deck=30))]
    m = re.fullmatch(r"your opponent reveals (?:their|his or her) hand(?:, and you draw (?:a card|(\d+) cards) for each "
                     r"(trainer|pokémon|supporter) card you find there)\.", base) or \
        re.fullmatch(r"your opponent reveals their hand, and you draw (?:a card|(\d+) cards) for each (pokémon) you find "
                     r"there\.", base)
    if m:
        per, what = int(m.group(1) or 1), m.group(2)
        kinds = ['item', 'supporter', 'pokemon', 'pokemon', 'energy']
        cnt = {'trainer': 2, 'pokémon': 2, 'supporter': 1}[what]
        return [scn('opp hand I S P P E', hand=2, setup=opp_hand_with(kinds),
                    want=W(hand=2 + per * cnt, deck=30 - per * cnt, opp_hand=5))]
    if base == MANUAL_TEXT['Ghetsis']:
        return [scn('opp hand I I S P', hand=2, setup=opp_hand_with(['item', 'item', 'supporter', 'pokemon']),
                    want=W(hand=4, deck=28, opp_hand=2, opp_deck=32))]
    if base == MANUAL_TEXT['Colress']:
        return [scn('2+3 benched', hand=3, my_bench=2, opp_bench=3, want=W(hand=5, deck=28))]
    if base == "draw a card. then, draw 2 cards for each other whitney in your discard pile.":
        def whit(c):
            for _ in range(2):
                c.t.put(d, P1, 'discard')
        return [scn('2 in discard', setup=whit, want=draw_n_expect(5)), scn('none', want=draw_n_expect(1))]
    if base == ("you can play this card only if your opponent's active pokémon is a stage 1 pokémon. draw 4 cards."):
        from tests.test_sweep_abilities import pool
        return [scn('opp stage 1', setup=lambda c: swap_opp_active(c, pool(c.t.test)['stage1']),
                    want=draw_n_expect(4)),
                scn('opp basic', offered=False)]
    m = re.fullmatch(r"(?:choose 1: • )?draw cards until you have 5 cards in your hand\. • during this turn, your pokémon's "
                     r"attacks do 20 more damage.*", base)
    if m:
        return [scn('mode draw', choice=0, want=until_expect(5))]
    if base.startswith("choose 1: • shuffle your hand into your deck then draw 5 cards."):
        return [scn('mode shuffle+draw', hand=3, choice=0, want=W(hand=5, deck=28))]
    if base.startswith("choose 1: • draw a card • put a judge card"):
        return [scn('mode draw', choice=0, want=draw_n_expect(1))]
    if base == "discard any stadium card in play. then, draw a card.":
        return [scn('stadium in play', setup=lambda c: c.t.stadium(any_stadium(c.t.test), P2), want=draw_n_expect(1)),
                scn('no stadium (RULING: playable?)', offered=None, want=draw_n_expect(1))]
    if base == "switch your active pokémon with 1 of your benched pokémon. if you do, draw 3 cards.":
        return [scn('switch', want=draw_n_expect(3)), scn('no bench', my_bench=0, offered=None,
                                                          want=W(hand=2, deck=30))]
    if base == ("draw 3 cards. your opponent may draw a card. if they do, draw 1 more card."):
        return [scn('opp accepts', yes=True, want=W(hand=6, deck=26, opp_hand=5, opp_deck=29)),
                scn('opp declines', yes=False, want=W(hand=5, deck=27, opp_hand=4))]
    if base == "draw 3 cards. then, discard a card from your hand.":
        return [scn('net +2', want=W(hand=4, deck=27))]
    m = re.fullmatch(r"draw (\d+) cards\. (?:if you (?:drew any cards in this way|do), (?:flip a coin\. if heads, )?"
                     r"(?:attach|your active|discard a random|your opponent discards).*|then, flip a coin\. if heads, if "
                     r"you played this kahili.*|if you drew any cards in this way and if community center.*|switch out "
                     r"your opponent's active pokémon to the bench\. \(your opponent chooses the new active pokémon\.\)|"
                     r"if you drew any cards in this way, discard up to 3 cards from your hand\. \(you must discard at "
                     r"least 1 card\.\))", base)
    if m:
        n = int(m.group(1))
        if 'discard up to 3' in base:
            return [scn('draw 3, discard 1', picks=lambda cards, cnt, p, dc: cards[:1], want=W(hand=4, deck=27))]
        if 'discard a random card from your opponent' in base:
            return [scn('draw', want=dict(draw_n_expect(n), opp_hand=3))]
        if 'kahili' in base:
            return [scn('tails', heads=False, want=draw_n_expect(n)),
                    scn('heads (Kahili back to hand)', heads=True, want=draw_n_expect(n, extra_hand=1))]
        return [scn('draw', heads=False, want=draw_n_expect(n))]
    m = re.fullmatch(r"draw (\d+) cards\. at the end of this turn, if you have (\d+) or more cards in your hand, .*", base)
    if m:
        return [scn('draw', want=draw_n_expect(int(m.group(1))))]
    m = re.fullmatch(r"(?:attach (?:a|up to 2) (?:water|fire) energy cards? from your (?:discard pile|hand) to 1 of your "
                     r"pokémon(?: v)?)\. if you do, draw (\d+) cards\.", base)
    if m:
        n = int(m.group(1))
        if 'pokémon v' in base:
            return None
        spec = (lambda test: energy_def(test, PokemonTypes.FIRE))
        return [scn('attach 1', hand=2, hand_specs=[spec], picks=lambda cards, cnt, p, dc: cards[:1],
                    want=W(hand=2 + n, deck=30 - n)),
                scn('no fire energy', hand=2, offered=None, want=W(hand=2, deck=30))]
    m = re.fullmatch(r"shuffle up to 5 pokémon from your discard pile into your deck\. if you shuffled any cards into your "
                     r"deck in this way, draw 3 cards\.", base)
    if m:
        def disc(c):
            c.t.put(c.t.test.filler, P1, 'discard')
            c.t.put(c.t.test.filler, P1, 'discard')
        return [scn('2 pokémon', setup=disc, want=W(hand=5, deck=32 - 3))]
    return None


def extra_trainer_plans(base, d):
    if base == "shuffle your hand into your deck. then, draw a card for each card in your opponent's hand.":
        return [scn('opp hand 5', hand=3, opp_hand=5, want=W(hand=5, deck=28, opp_hand=5)),
                scn('opp hand 0', hand=3, opp_hand=0, offered=None, want=W(hand=0, deck=33))]
    if base.startswith("your opponent shuffles their hand and puts it on the bottom of their deck. if they put any cards "
                       "on the bottom of their deck in this way, they draw 3 cards."):
        return [scn('opp 3 prizes, hand 6', opp_prizes=3, opp_hand=6, want=W(hand=2, deck=30, opp_hand=3, opp_deck=33)),
                scn('opp 4 prizes', opp_prizes=4, offered=False)]
    if base == ("discard up to 2 pokémon that aren't pokémon-gx or pokémon-ex from your hand. draw 3 cards for each card "
                "you discarded in this way."):
        return [scn('discard 2 pokémon', hand=1, hand_specs=[lambda test: test.filler] * 2,
                    picks=lambda cards, cnt, p, dc: [x for x in cards if def_for(x.archetype_id) is not None
                                                     and isinstance(def_for(x.archetype_id), PokemonCardDef)][:2],
                    want=W(hand=7, deck=24))]
    if base == "each player may draw up to 3 cards. you draw first.":
        return [scn('both pick 2', choice=2, want=W(hand=4, deck=28, opp_hand=6, opp_deck=28)),
                scn('both pick 0', choice=0, want=W(hand=2, deck=30, opp_hand=4, opp_deck=30))]
    return None


def swap_opp_active(c, spec):
    old = c.opp
    c.t.board.move_card(old.entity_id, c.t.board.find_player_area(P2, 'discard').entity_id)
    c.opp = neutral(c.t.put(spec, P2, 'active'))


# --------------------------------------------------------- Stadium templates --
def stadium_plans(text, d):
    m = re.fullmatch(r"once during each player's turn, that player may draw cards until they have (\d+) cards in their "
                     r"hand\.", text)
    if m:
        n = int(m.group(1))
        return [scn('hand 1', hand=1, want=until_expect(n, hand=1)),
                scn('hand at target', hand=n, offered=None, want=W(hand=n, deck=30)),
                scn("opponent's Stadium", hand=1, stadium_owner=P2, want=until_expect(n, hand=1))]
    if text == MANUAL_TEXT['Tropical Beach']:
        return [scn('hand 1', hand=1, want=until_expect(7, hand=1))]
    m = re.fullmatch(r"once during each player's turn, that player may shuffle their hand into their deck and draw (\d+) "
                     r"cards\. if they do, their turn ends\.", text)
    if m:
        n = int(m.group(1))
        return [scn('hand 3', hand=3, want=W(hand=n, deck=33 - n))]
    m = re.fullmatch(r"once during each player's turn, that player may discard a (basic|fire or fighting) energy card from "
                     r"(?:their|his or her) hand(?: in order to draw a card|\. if that player does so, he or she draws "
                     r"(\d+) cards)\..*", text)
    if m:
        n = int(m.group(2) or 1)
        kind = PokemonTypes.FIRE if m.group(1) != 'basic' else PokemonTypes.WATER
        spec = (lambda test, kind=kind: energy_def(test, kind))
        return [scn('pay', hand=2, hand_specs=[spec], want=W(hand=2 + n, deck=30 - n, discard=1)),
                scn('no energy', hand=2, offered=False)]
    m = re.search(r"(?:once during each player's turn, that player may discard 2 cards from their hand in order to draw a "
                  r"card\.|^discard 2 cards from your hand to draw a card\.$)", text)
    if m:
        return [scn('pay 2', hand=3, want=W(hand=2, deck=29)), scn('cannot pay', hand=1, offered=False)]
    return None


# ------------------------------------------------- Tool / Special Energy --
async def attachment_case(test, d, text, *, ko=False, weak=False, where='active', hand=2):
    """P1 holds `d` attached to its Active; P2's vanilla attacker attacks it.  Returns counts delta."""
    from tests.test_sweep_abilities import pool, types_of
    ad, aa = pool(test)['attacker']
    t = DrawTable(test)
    me = neutral(t.put(test.filler, P1, 'active'), hp=10 if ko else BIG)
    bench = neutral(t.put(test.filler, P1, 'bench'))
    holder = me if where == 'active' else bench
    if weak:
        holder.set_attribute(AttrID.WEAKNESS_TYPES, [types_of(ad)[0]])
    if isinstance(d, PokemonToolCardDef):
        await t.play(t.put(d, P1, 'hand'), targets=[holder.entity_id])     # real attach (Tool passives)
    else:
        t.attach(d, holder)
    att = neutral(t.put(ad, P2, 'active'))
    neutral(t.put(test.filler, P2, 'bench'))
    pay_cost(t, att, aa)
    set_zone(t, P1, 'hand', hand)
    set_zone(t, P1, 'deck', 30)
    t.next_turn()
    before = counts(t)
    await t.do(t.attack_offer(att, aa.title, pid=P2), pid=P2)
    after = counts(t)
    return after['hand'] - before['hand'], after['deck'] - before['deck']


async def attachment_check(test, d, text):
    probs = []

    async def case(name, want, **k):
        dh, dd = await attachment_case(test, d, text, **k)
        if dh != want or dd != -want:
            probs.append(f"{name}: hand {dh:+d}, deck {dd:+d} (want +{want})")

    m = re.search(r"if the pokémon this card is attached to is in the active spot and is damaged by an attack from your "
                  r"opponent's pokémon \(even if it is knocked out\), draw (a card|\d+ cards)\.", text)
    if m:
        n = 1 if m.group(1) == 'a card' else int(m.group(1).split()[0])
        await case('damaged', n)
        await case('knocked out', n, ko=True)
        await case('on bench (not hit)', 0, where='bench')
        return (not probs), '; '.join(probs) or 'ok'
    m = re.search(r"if the pokémon this card is attached to is knocked out by damage from an (?:attack from your "
                  r"opponent's pokémon|opponent's attack), draw cards until you have (\d+) cards in your hand\.", text)
    if m:
        n = int(m.group(1))
        await case('knocked out, hand 2', n - 2, ko=True)
        await case('not knocked out', 0)
        await case('knocked out, hand 8', 0, ko=True, hand=8)
        return (not probs), '; '.join(probs) or 'ok'
    m = re.search(r"if the pokémon this card is attached to has weakness to your opponent's active pokémon's type, is in "
                  r"the active spot, and is damaged by an attack from your opponent's pokémon \(even if this pokémon is "
                  r"knocked out\), draw (\d+) cards\.", text)
    if m:
        n = int(m.group(1))
        await case('weak, damaged', n, weak=True)
        await case('not weak', 0)
        return (not probs), '; '.join(probs) or 'ok'
    m = re.search(r"when you attach this card from your hand to a (\w+) pokémon, draw (\d+) cards\.", text)
    if m:
        ptype, n = TYPES[m.group(1)], int(m.group(2))
        for name, typed, want in (('to ' + m.group(1), True, n), ('to other type', False, 0)):
            t = DrawTable(test)
            target = basic_of_type(ptype.value) if typed else test.filler
            mon = neutral(t.put(target, P1, 'active'))
            neutral(t.put(test.filler, P2, 'active'))
            set_zone(t, P1, 'hand', 2)
            card = t.put(d, P1, 'hand')
            h0, d0 = len(t.zone(P1, 'hand')), len(t.zone(P1, 'deck'))
            await t.play(card, targets=[mon.entity_id])
            dh, dd = len(t.zone(P1, 'hand')) - h0, len(t.zone(P1, 'deck')) - d0
            if dh != want - 1 or dd != -want:
                probs.append(f"{name}: hand {dh:+d}, deck {dd:+d} (want draw {want})")
        return (not probs), '; '.join(probs) or 'ok'
    return None, 'not modelled'


# ------------------------------------------------------------ running sweeps --
def write_report(name, checked, failures, skipped, unhandled):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, f"draw_{name}.json"), 'w') as fh:
        json.dump({'case': f'draw_{name}', 'checked': checked, 'failures': failures, 'skipped': skipped,
                   'unhandled': unhandled}, fh, indent=1, ensure_ascii=False)


COVERED_ELSEWHERE = [
    re.compile(r"^draw (\d+|a) cards?\.$"),                                     # test_sweep_basic.draw_n
    re.compile(r"^once during your turn(?: \(before your attack\))?, (?:if this pokémon is your active pokémon, )?"
               r"you may (?:use this ability\. )?draw (a|\d+) cards?\.( if this pokémon is your active pokémon, draw "
               r"1 more card\.)?$"),                                                 # draw_ability
    re.compile(r"^once during your turn, you may use this ability\. draw (a|\d+) cards?\.$"),
    re.compile(r"^when you play this pokémon from your hand to evolve 1 of your pokémon(?: during your turn)?, you may "
               r"draw (\d+|a) cards?\.$"),                                           # evolve_trigger
    re.compile(r"^flip (\d+) coins\. for each heads, draw a card\.$"),             # coin_rest
]


def is_covered(text):
    return any(rx.search(text) for rx in COVERED_ELSEWHERE)


def pokemon_items(kind):
    seen = set()
    for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, str(d.collector_number))):
        if not isinstance(d, PokemonCardDef) or not glc.is_glc_legal(d):
            continue
        for a in d.abilities or []:
            if (kind == 'attack') != isinstance(a, Attack):
                continue
            text = norm(a.game_text)
            if 'draw' not in text:
                continue
            key = (d.display_name, a.title, text)
            if key in seen:
                continue
            seen.add(key)
            yield d, a, text


NOT_A_DRAW = re.compile(r"can't draw|draws? (?:a )?cards? at the beginning|drew this pokémon|drew any cards in this way"
                        r"|does \d+ (?:more )?damage for each card|if you drew")


async def sweep_pokemon(test, kind, limit=None):
    checked, failures, skipped, unhandled = 0, [], [], collections.Counter()
    covered = 0
    for d, a, text in pokemon_items(kind):
        if is_covered(text):
            covered += 1
            continue
        plans = attack_plans(text, d, a) if kind == 'attack' else ability_plans(text, d, a)
        evolve = False
        if plans is None and kind == 'ability':
            plans = evolve_plans(text, d, a)
            evolve = plans is not None
        if plans is None:
            unhandled[text] += 1
            continue
        if limit is not None and checked >= limit:
            break
        checked += 1
        if evolve:
            probs = []
            for s in plans:
                try:
                    ok, detail = await run_evolve(test, d, a, s)
                except Exception as ex:
                    ok, detail = False, f"{s['name']}: ERROR {type(ex).__name__}: {ex}"
                if ok is None:
                    skipped.append({'card': label(d, a), 'why': detail})
                    break
                if not ok:
                    probs.append(detail)
            ok, detail = (not probs), '; '.join(probs)
        else:
            ok, detail = await run_all(test, kind, d, a, plans)
        if not ok:
            failures.append({'card': label(d, a), 'guid': d.guid, 'text': text, 'detail': detail})
    write_report({'attack': 'attacks', 'ability': 'abilities'}[kind], checked, failures, skipped, dict(unhandled.most_common()))
    return checked, failures, skipped, unhandled, covered


async def sweep_trainers(test, limit=None):
    checked, failures, skipped, unhandled = 0, [], [], collections.Counter()
    for name, defs in trainer_pool().items():
        src, text = trainer_text(defs)
        if 'draw' not in text:
            continue
        d = defs[0]
        if isinstance(d, StadiumCardDef):
            plans, kind = stadium_plans(text, d), 'stadium'
        elif isinstance(d, (PokemonToolCardDef, EnergyCardDef)):
            plans, kind = None, 'attachment'
            if limit is not None and checked >= limit:
                break
            try:
                ok, detail = await attachment_check(test, d, text)
            except Exception as ex:
                ok, detail = False, f"ERROR {type(ex).__name__}: {ex}"
            if ok is None:
                unhandled[f"[{type(d).__name__}] {name}: {text}"] += 1
                continue
            checked += 1
            if not ok:
                failures.append({'card': f"{name} ({d.set_code} {d.collector_number})", 'guid': d.guid,
                                 'text': text, 'source': src, 'detail': detail})
            continue
        else:
            plans, kind = trainer_plans(text, d), 'trainer'
        if plans is None:
            unhandled[f"[{type(d).__name__}] {name}: {text}"] += 1
            continue
        if limit is not None and checked >= limit:
            break
        checked += 1
        ok, detail = await run_all(test, kind, d, None, plans)
        if not ok:
            failures.append({'card': f"{name} ({d.set_code} {d.collector_number})", 'guid': d.guid, 'text': text,
                             'source': src, 'detail': detail})
    write_report('trainers', checked, failures, skipped, dict(unhandled.most_common()))
    return checked, failures, skipped, unhandled, 0


class SweepDraw(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def _limit(self):
        v = os.environ.get('SWEEP_LIMIT')
        return int(v) if v else None

    def _show(self, name, res):
        checked, failures, skipped, unhandled, covered = res
        print(f"\ndraw_{name}: checked {checked}, failures {len(failures)}, skipped {len(skipped)}, "
              f"unhandled wordings {len(unhandled)} ({sum(unhandled.values())} cards)"
              + (f", covered elsewhere {covered}" if covered else ''))
        for f in failures:
            print('  FAIL', f['card'], '|', f['detail'][:400])

    async def test_attacks(self):
        if os.environ.get('SWEEP_ONLY') not in (None, '', 'attacks'):
            self.skipTest('SWEEP_ONLY')
        self._show('attacks', await sweep_pokemon(self, 'attack', self._limit()))

    async def test_abilities(self):
        if os.environ.get('SWEEP_ONLY') not in (None, '', 'abilities'):
            self.skipTest('SWEEP_ONLY')
        self._show('abilities', await sweep_pokemon(self, 'ability', self._limit()))

    async def test_trainers(self):
        if os.environ.get('SWEEP_ONLY') not in (None, '', 'trainers'):
            self.skipTest('SWEEP_ONLY')
        self._show('trainers', await sweep_trainers(self, self._limit()))


if __name__ == "__main__":
    unittest.main()
