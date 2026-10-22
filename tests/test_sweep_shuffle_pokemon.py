"""Sweep: every GLC-legal card text that shuffles Pokémon into a deck.

Checks the NUMBER and KIND of cards moved, that attached cards (and lower
evolution stages) travel with an in-play Pokémon, that they land in the right
player's deck as loose cards (not still nested under the Pokémon), that
"up to" allows fewer / zero and flat counts take the number when available.

Attacks       self_shuffle, self_shuffle_bonus, self_shuffle_heal, opp_active_shuffle,
              opp_bench_shuffle, opp_bench_then_self, expelling_tornado, each_active_shuffle,
              own_bench_shuffle, discard_pokemon_to_deck, opp_discard_pokemon_to_deck,
              reveal_shuffle_back
Abilities     ability_self_shuffle, ability_giant_fan
Trainers      trainer_shuffle (hand-written list: the Trainer scripts carry no text field)
"""
import json
import os
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import (SweepCase, run_sweep, Board, snapshot, pay_cost, neutral, do_attack,
                              dealt, norm, label, BIG, REPORT_DIR)
from tests.test_sweep_abilities import (pool, basic_energy_def, pre_evolution, stage_of, types_of,
                                        has_ability, num, set_deck, set_discard, evolve_board)
from tests.test_sweep_effects import FxTable
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage
from spirit.game.data_utils import (Attack, CARD_DEFS_BY_GUID, PokemonCardDef, EnergyCardDef,
                                    SupporterCardDef, PokemonToolCardDef, def_for)
from spirit.game.session.effects import EffectContext
from spirit.game.glc import is_glc_legal
from spirit.game.session.passives import effective_max_hp
from spirit.tools.effect_smoke import P1, P2


# ------------------------------------------------------------------ helpers --
def ids(cards):
    return {c.entity_id for c in cards}


def stack(p):
    """p and every card nested under it (energy, tools, lower stages)."""
    out, queue = [p], list(p.children)
    while queue:
        e = queue.pop(0)
        out.append(e)
        queue.extend(e.children)
    return out


def dname(c):
    return def_for(c.archetype_id).display_name or '?'


def in_deck_loose(t, cards, pid):
    """Missing cards (not loose in pid's deck)."""
    deck = ids(t.zone(pid, 'deck'))
    return [dname(c) for c in cards if c.entity_id not in deck]


def nested_in_deck(t, pid):
    return [dname(c) for c in t.zone(pid, 'deck') if list(c.children)]


def in_play(t, p):
    return p in t.board.pokemon_in_play(p.owning_player_id)


def check_stack_shuffled(t, cards, pid, deck_before, who='', extra_deck=0):
    """cards (a pre-move stack) must all be loose in pid's deck, deck grew by len."""
    problems = []
    miss = in_deck_loose(t, cards, pid)
    if miss:
        problems.append(f'{who} not in {pid_name(pid)} deck: {miss}')
    nest = nested_in_deck(t, pid)
    if nest:
        problems.append(f'cards still nested under {nest} inside the deck')
    grow = len(t.zone(pid, 'deck')) - deck_before
    if grow != len(cards) + extra_deck:
        problems.append(f'{pid_name(pid)} deck grew by {grow}, expected {len(cards) + extra_deck}')
    return problems


def pid_name(pid):
    return 'P1' if pid == P1 else 'P2'


def decorate(t, p, tool=True, energy=1):
    """Give an in-play Pokémon an Energy and a Tool so 'all attached cards' is visible."""
    if energy:
        t.energy(p, PokemonTypes.FIRE, energy)
    if tool:
        t.attach(pool(t.test)['tool'], p)
    return p


def add_pre_evolution(t, d, me):
    """Put d's lower stage under it, like a real evolution."""
    if stage_of(d) in (PokemonStage.STAGE1, PokemonStage.STAGE2):
        pre = pre_evolution(d)
        if pre is not None:
            card = t.put(pre, me.owning_player_id, 'hand')
            t.board.attach_card(card.entity_id, me.entity_id)
            return card
    return None


def psychic_basic(test):
    return pool(test)['basic_by_type'].get(PokemonTypes.PSYCHIC.value)


class ShTable(FxTable):
    """FxTable that also records the `minimum` of every card pick."""

    def __init__(self, test):
        super().__init__(test)
        self.minimums = []

    def _patches(self):
        table = self
        out = super()._patches()
        base = out[0].new

        async def choose_cards(ctx, cards, count, minimum=None, prompt='', *a, **k):
            table.minimums.append((len(list(cards)), count, minimum))
            return await base(ctx, cards, count, minimum, prompt, *a, **k)
        out[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
        return out


def board(test, d, attack, *, heads=True, prep=None, yes=True):
    t = ShTable(test)
    t.heads = heads
    t.yes = yes
    me = t.put(d, P1, 'active')
    my_bench = neutral(t.put(test.filler, P1, 'bench'))
    opp = neutral(t.put(test.filler, P2, 'active'))
    opp_bench = neutral(t.put(test.filler, P2, 'bench'))
    pay_cost(t, me, attack)
    b = Board(t, me, opp, my_bench, opp_bench, attack)
    if prep is not None:
        prep(b)
    b.before = snapshot(b)
    return b


def hurt(t, p, n):
    """Real damage counters: HP = printed max - n (neutral() sets HP above max)."""
    p.set_attribute(AttrID.HP, effective_max_hp(t.board, p) - n)


def deck_len(t, pid):
    return len(t.zone(pid, 'deck'))


# ================================================================== attacks ==
ATTACHED = r"all (?:attached cards|cards attached to it)"
COND = r"(?:asleep|burned|confused|paralyzed|poisoned)"

SELF_RX = (r"^(?:(?:the defending pokémon|your opponent's active pokémon) is now %s(?: and %s)?\. )?"
           r"(you may )?shuffle this pokémon and %s into your deck\."
           r"(?: your opponent can't play any item cards from their hand during their next turn\.)?$"
           % (COND, COND, ATTACHED))


async def self_shuffle(test, d, attack, m):
    may = bool(m.group(1))
    problems = []
    for yes in ((True, False) if may else (True,)):
        def prep(b):
            decorate(b.t, b.me, tool=True, energy=1)
            add_pre_evolution(b.t, d, b.me)
        b = board(test, d, attack, prep=prep, yes=yes)
        t = b.t
        cards = stack(b.me)
        if not await do_attack(b):
            return False, 'attack not offered'
        tag = '' if not may else ('[yes] ' if yes else '[no] ')
        if yes:
            pr = check_stack_shuffled(t, cards, P1, b.before['my_deck'], 'this Pokémon stack')
            if in_play(t, b.me):
                pr.append('attacker still in play')
            if t.active(P1) is not b.my_bench:
                pr.append('benched Pokémon not promoted')
            if deck_len(t, P2) != b.before['opp_deck']:
                pr.append('opponent deck changed')
        else:
            pr = []
            if not in_play(t, b.me) or t.active(P1) is not b.me:
                pr.append('declined but attacker left the Active Spot')
            if deck_len(t, P1) != b.before['my_deck']:
                pr.append('declined but deck changed')
        problems += [tag + p for p in pr]
    return (not problems), '; '.join(problems) or f'shuffled {len(cards)} cards'


BONUS_RX = r"^you may do (\d+) more damage\. if you do, shuffle this pokémon and %s into your deck\.$" % ATTACHED


async def self_shuffle_bonus(test, d, attack, m):
    more = int(m.group(1))
    problems = []
    for yes in (True, False):
        b = board(test, d, attack, prep=lambda b: decorate(b.t, b.me), yes=yes)
        t = b.t
        cards = stack(b.me)
        if not await do_attack(b):
            return False, 'attack not offered'
        want = (attack.damage or 0) + (more if yes else 0)
        if not has_ability(d) and dealt(b) != want:
            problems.append(f'[{yes}] damage {dealt(b)}, expected {want}')
        if yes:
            problems += ['[yes] ' + p for p in check_stack_shuffled(t, cards, P1, b.before['my_deck'])]
        elif not in_play(t, b.me):
            problems.append('[no] attacker left play')
    return (not problems), '; '.join(problems) or 'ok'


HEAL_SELF_RX = (r"^(heal all damage from all of your pokémon\. |heal all damage from each of your benched pokémon\. "
                r"if you healed any damage in this way, )shuffle this pokémon and %s into your deck\.$" % ATTACHED)


async def self_shuffle_heal(test, d, attack, m):
    conditional = m.group(1).startswith('heal all damage from each')
    problems = []
    for damaged in ((True, False) if conditional else (True,)):
        def prep(b):
            decorate(b.t, b.me)
            if damaged:
                hurt(b.t, b.my_bench, 50)
        b = board(test, d, attack, prep=prep)
        t = b.t
        cards = stack(b.me)
        if not await do_attack(b):
            return False, 'attack not offered'
        tag = f'[bench damaged={damaged}] '
        if damaged:
            if t.damage(b.my_bench) != 0:
                problems.append(tag + f'bench not healed (damage {t.damage(b.my_bench)})')
            problems += [tag + p for p in check_stack_shuffled(t, cards, P1, b.before['my_deck'])]
        else:
            if not in_play(t, b.me):
                problems.append(tag + 'nothing healed but attacker was shuffled away')
    return (not problems), '; '.join(problems) or 'ok'


OPP_ACTIVE_RX = (r"^(flip a coin\. if heads, |discard (\d+) energy from this pokémon\. if you discarded any energy in "
                 r"this way, |if 1 of your opponent's pokémon used a gx attack during their last turn, )?"
                 r"your opponent shuffles (?:their active pokémon|the defending pokémon) and %s into "
                 r"(?:their|his or her) deck\.$" % ATTACHED)


async def opp_active_shuffle(test, d, attack, m):
    pre = m.group(1) or ''
    runs = [(True, True)]
    if pre.startswith('flip'):
        runs = [(True, True), (False, False)]      # (heads, should shuffle)
    if 'gx attack' in pre:
        runs = [(True, False)]                     # no GX attacks exist in GLC
    problems = []
    for heads, should in runs:
        def prep(b):
            decorate(b.t, b.opp)
            if pre.startswith('discard'):
                b.t.energy(b.me, PokemonTypes.WATER, int(m.group(2)))
        b = board(test, d, attack, heads=heads, prep=prep)
        t = b.t
        cards = stack(b.opp)
        if not await do_attack(b):
            return False, 'attack not offered'
        tag = f'[heads={heads}] ' if len(runs) > 1 else ''
        if should:
            pr = check_stack_shuffled(t, cards, P2, b.before['opp_deck'], "opponent's Active stack")
            if in_play(t, b.opp):
                pr.append('opponent Active still in play')
            if t.active(P2) is not b.opp_bench:
                pr.append('opponent bench not promoted')
            if deck_len(t, P1) != b.before['my_deck']:
                pr.append('my deck changed')
        else:
            pr = []
            if not in_play(t, b.opp):
                pr.append('opponent Active shuffled although it should not be')
        problems += [tag + p for p in pr]
    return (not problems), '; '.join(problems) or 'ok'


OPP_BENCH_RX = (r"^(you can use this attack only if you go second, and only (?:during|on) your first turn\. )?"
                r"(flip a coin\. if heads, )?"
                r"(?:choose 1 of your opponent's (benched )?pokémon\. shuffle that pokémon|"
                r"shuffle 1 of your opponent's (benched )?pokémon( that has any damage counters on it)?) "
                r"and %s into their deck\.$" % ATTACHED)


def opp_bench_board(test, d, attack, heads, damaged_only, go_second):
    def prep(b):
        b.extra = neutral(b.t.put(test.filler, P2, 'bench'))
        decorate(b.t, b.extra)
        if damaged_only:
            hurt(b.t, b.extra, 30)
        if go_second:
            b.t.state.turn_number = 2
    b = board(test, d, attack, heads=heads, prep=prep)
    seen = []

    def pick(cands, prompt):
        seen.append(list(cands))
        return b.extra if b.extra in cands else cands[0]
    b.t.pokemon = pick
    return b, seen


async def opp_bench_shuffle(test, d, attack, m):
    go_second, coin, benched1, benched2, damaged_only = m.groups()
    benched = bool(benched1 or benched2)
    problems = []
    if go_second:
        b = board(test, d, attack)
        if b.t.attack_offer(b.me, attack.title) is not None:
            problems.append('offered on turn 3 (not the go-second first turn)')
    runs = [(True, True), (False, False)] if coin else [(True, True)]
    for heads, should in runs:
        b, seen = opp_bench_board(test, d, attack, heads, damaged_only, go_second)
        t = b.t
        cards = stack(b.extra)
        if not await do_attack(b):
            return False, 'attack not offered (go-second turn set)' if go_second else 'attack not offered'
        tag = f'[heads={heads}] ' if coin else ''
        if should:
            if seen:
                cands = seen[0]
                if benched and b.opp in cands:
                    problems.append(tag + 'Active offered as a target')
                if not benched and b.opp not in cands:
                    problems.append(tag + 'Active not offered (text: any of your opponent\'s Pokémon)')
                if damaged_only and b.opp_bench in cands:
                    problems.append(tag + 'undamaged Pokémon offered')
                if b.extra not in cands:
                    problems.append(tag + 'decorated bench Pokémon not offered')
            problems += [tag + p for p in check_stack_shuffled(t, cards, P2, b.before['opp_deck'],
                                                               'chosen Pokémon stack')]
            if not in_play(t, b.opp) or not in_play(t, b.opp_bench):
                problems.append(tag + 'an unchosen opponent Pokémon left play')
            if deck_len(t, P1) != b.before['my_deck']:
                problems.append(tag + 'my deck changed')
        else:
            if not in_play(t, b.extra):
                problems.append(tag + 'tails but the Pokémon was shuffled')
    return (not problems), '; '.join(problems) or 'ok'


THEN_SELF_RX = (r"^choose 1 of your opponent's benched pokémon\. (?:they shuffle|shuffle) that pokémon and %s into "
                r"their deck(?:\. then,|, and then) shuffle this pokémon and %s into your deck\."
                r"( if your opponent has no benched pokémon, this attack does nothing\.)?$" % (ATTACHED, ATTACHED))


async def opp_bench_then_self(test, d, attack, m):
    problems = []
    b, seen = opp_bench_board(test, d, attack, True, False, False)
    decorate(b.t, b.me, tool=False)
    t = b.t
    opp_cards, my_cards = stack(b.extra), stack(b.me)
    deck_p1 = deck_len(t, P1)
    if not await do_attack(b):
        return False, 'attack not offered'
    if seen and b.opp in seen[0]:
        problems.append('Active offered')
    problems += check_stack_shuffled(t, opp_cards, P2, b.before['opp_deck'], 'chosen opp Pokémon')
    problems += check_stack_shuffled(t, my_cards, P1, deck_p1, 'this Pokémon')
    if m.group(1):
        # no opponent bench -> attack does nothing (attacker stays)
        def prep(b2):
            for c in list(t2_bench(b2)):
                b2.t.board.find_player_area(P2, 'bench').remove_child(c)
        b2 = board(test, d, attack, prep=prep)
        if await do_attack(b2):
            if not in_play(b2.t, b2.me):
                problems.append('[no opp bench] attacker still shuffled away')
    return (not problems), '; '.join(problems) or 'ok'


def t2_bench(b):
    return b.t.zone(P2, 'bench')


TORNADO_RX = (r"^choose (\d+) of your opponent's benched pokémon\. if you do, shuffle all of your opponent's benched "
              r"pokémon that you didn't choose, and all cards attached to those pokémon, into their deck\.$")


async def expelling_tornado(test, d, attack, m):
    keep = int(m.group(1))
    problems = []

    def prep(b):
        b.extras = [neutral(b.t.put(test.filler, P2, 'bench')) for _ in range(4)]   # 5 benched
        for e in b.extras:
            decorate(b.t, e, tool=False)
    b = board(test, d, attack, prep=prep)
    t = b.t
    bench = t.zone(P2, 'bench')
    chosen = bench[:keep]
    t.picks = lambda cards, count, prompt, disp: [c for c in cards if c in chosen][:count]
    pokes = iter(chosen)
    t.pokemon = lambda cands, prompt: next(pokes, cands[0])
    gone = [c for p in bench[keep:] for c in stack(p)]
    if not await do_attack(b):
        return False, 'attack not offered'
    problems += check_stack_shuffled(t, gone, P2, b.before['opp_deck'], 'unchosen Pokémon')
    if [p for p in chosen if not in_play(t, p)]:
        problems.append('a chosen Pokémon left play')
    if not in_play(t, b.opp):
        problems.append('Active left play')
    # with exactly `keep` benched nothing is shuffled
    def prep2(b2):
        for _ in range(keep - 1):
            neutral(b2.t.put(test.filler, P2, 'bench'))
    b2 = board(test, d, attack, prep=prep2)
    if await do_attack(b2):
        if deck_len(b2.t, P2) != b2.before['opp_deck'] or len(b2.t.zone(P2, 'bench')) != keep:
            problems.append(f'[{keep} benched] something was shuffled')
    return (not problems), '; '.join(problems) or 'ok'


EACH_ACTIVE_RX = (r"^shuffle each player's active pokémon and all attached cards into their deck\. "
                  r"\(you choose a new active pokémon first\.\)$")


async def each_active_shuffle(test, d, attack, m):
    b = board(test, d, attack, prep=lambda b: decorate(b.t, b.opp))
    t = b.t
    mine, theirs = stack(b.me), stack(b.opp)
    if not await do_attack(b):
        return False, 'attack not offered'
    problems = check_stack_shuffled(t, mine, P1, b.before['my_deck'], 'my Active')
    problems += check_stack_shuffled(t, theirs, P2, b.before['opp_deck'], 'opp Active')
    if t.active(P1) is not b.my_bench or t.active(P2) is not b.opp_bench:
        problems.append('new Actives not promoted')
    return (not problems), '; '.join(problems) or 'ok'


OWN_BENCH_RX = (r"^(?:shuffle 1 of your benched pokémon|choose 1 of your benched (\w+) and shuffle that pokémon) and %s "
                r"into your deck\.( if you can't shuffle an? \w+ into your deck, this attack does nothing\.)?$"
                % ATTACHED)


def find_named_basic(name):
    for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, x.collector_number)):
        if isinstance(d, PokemonCardDef) and (d.display_name or '').lower() == name and is_glc_legal(d):
            return d
    return None


async def own_bench_shuffle(test, d, attack, m):
    name = m.group(1)
    problems = []
    named = find_named_basic(name) if name else None
    if name and named is None:
        return None, f'no {name} card'
    seen = []

    def prep(b):
        b.extra = neutral(b.t.put(named or test.filler, P1, 'bench'))
        decorate(b.t, b.extra)
    b = board(test, d, attack, prep=prep)
    t = b.t

    def pick(cands, prompt):
        seen.append(list(cands))
        return b.extra if b.extra in cands else cands[0]
    t.pokemon = pick
    cards = stack(b.extra)
    if not await do_attack(b):
        return False, 'attack not offered'
    if seen:
        if b.me in seen[0]:
            problems.append('Active offered')
        if name and b.my_bench in seen[0]:
            problems.append(f'non-{name} offered')
    problems += check_stack_shuffled(t, cards, P1, b.before['my_deck'], 'chosen benched Pokémon')
    if not in_play(t, b.my_bench) and name:
        problems.append('filler bench shuffled')
    if m.group(2):
        b2 = board(test, d, attack)
        if await do_attack(b2):
            if dealt(b2) or deck_len(b2.t, P1) != b2.before['my_deck']:
                problems.append(f'[no {name}] attack still did something (damage {dealt(b2)})')
    return (not problems), '; '.join(problems) or 'ok'


DISCARD_RX = (r"^shuffle (up to )?(\d+) (?:(psychic) pokémon|pokémon|in any combination of pokémon and basic energy cards) "
              r"from your discard pile into your deck\.$")


def discard_kind(test, text_kind, psychic):
    """(matching specs, non-matching specs, match(def))"""
    P = pool(test)
    bt = P['basic_by_type']
    fire = basic_energy_def(test, PokemonTypes.FIRE)
    if psychic:
        ps = bt[PokemonTypes.PSYCHIC.value]
        return ([ps] * 8, [bt[PokemonTypes.WATER.value], fire, P['item']],
                lambda dd: isinstance(dd, PokemonCardDef) and PokemonTypes.PSYCHIC.value in types_of(dd))
    if 'combination' in text_kind:
        return ([test.filler, fire, P['stage1'], basic_energy_def(test, PokemonTypes.WATER)] * 3,
                [P['special_energy'], P['item'], P['supporter']],
                lambda dd: isinstance(dd, PokemonCardDef) or
                (isinstance(dd, EnergyCardDef) and str(AttrID.IS_SPECIAL_ENERGY.value) not in dd.extra_attributes))
    return ([test.filler, P['stage1']] * 4, [fire, P['item'], P['special_energy']],
            lambda dd: isinstance(dd, PokemonCardDef))


class Rec:
    def __init__(self, t, choose=None):
        self.calls = []
        self.choose = choose
        t.picks = self

    def __call__(self, cards, count, prompt, display):
        self.calls.append((list(cards), count, prompt))
        return self.choose(cards, count) if self.choose else cards[:count]


async def discard_to_deck_judge(t, n, upto, match, matching, nonmatch, act, pid=P1, label_='', draw=0):
    """Discard = nonmatch + `avail` matching; judge offered / count / moved."""
    problems = []
    for avail, pick_n in ([(n + 1, n), (max(n - 1, 1), None)] + ([(n + 1, 0)] if upto else [])):
        tt = t()                                   # fresh table factory
        set_discard(tt, pid, nonmatch + matching[:avail])
        deck0 = deck_len(tt, pid)
        disc_before = list(tt.zone(pid, 'discard'))
        rec = Rec(tt, (lambda cards, count, k=pick_n: cards[:count if k is None else k]))
        res = await act(tt)
        tag = f'[{avail} matching in discard{", pick 0" if pick_n == 0 else ""}] '
        if res is False:
            if pick_n == 0:
                continue
            problems.append(tag + 'not offered/used')
            continue
        want = min(n, avail) if pick_n != 0 else 0
        moved = [c for c in disc_before if c in tt.zone(pid, 'deck') or (draw and c in tt.zone(pid, 'hand'))]
        bad = [dname(c) for c in moved if not match(def_for(c.archetype_id))]
        if rec.calls:
            cands, count, _ = rec.calls[0]
            offered_bad = [dname(c) for c in cands if not match(def_for(c.archetype_id))]
            if offered_bad:
                problems.append(tag + f'non-matching offered {offered_bad}')
            if len(cands) != avail:
                problems.append(tag + f'{len(cands)} offered, {avail} matching')
            if count != min(n, avail) and count != n:
                problems.append(tag + f'pick count {count}, text {n}')
            mins = tt.minimums[0][2] if tt.minimums else 'n/a'
            if upto and mins not in (0, 1):
                problems.append(tag + f'"up to" but minimum={mins}')
            if upto and mins == 1:
                RULINGS.add(label_ or '?')
            if not upto and mins not in (None, min(n, avail)):
                problems.append(tag + f'flat count {n} but minimum={mins} (player may stop short)')
        elif want:
            problems.append(tag + 'no choice offered')
        if len(moved) != want:
            problems.append(tag + f'shuffled {len(moved)}, expected {want}')
        if bad:
            problems.append(tag + f'non-matching shuffled {bad}')
        grow = want - (draw if want else 0)
        if deck_len(tt, pid) - deck0 != grow:
            problems.append(tag + f'deck grew {deck_len(tt, pid) - deck0}, expected {grow}')
    return problems


async def discard_pokemon_to_deck(test, d, attack, m):
    upto, n, psychic = bool(m.group(1)), int(m.group(2)), m.group(3)
    if psychic and psychic_basic(test) is None:
        return None, 'no psychic basic in pool'
    matching, nonmatch, match = discard_kind(test, m.group(0), psychic)
    boards = []

    def factory():
        b = board(test, d, attack)
        boards.append(b)
        return b.t

    async def act(tt):
        b = boards[-1]
        b.before = snapshot(b)
        return await do_attack(b)
    problems = await discard_to_deck_judge(factory, n, upto, match, matching, nonmatch, act,
                                           label_=label(d, attack))
    # minimum: with a flat count the player must not be allowed to stop short
    return (not problems), '; '.join(problems) or 'ok'


OPP_DISCARD_RX = (r"^for each pokémon in your opponent's discard pile, put 1 damage counter on your opponent's pokémon "
                  r"in any way you like\. if you placed any damage counters in this way, your opponent shuffles all "
                  r"pokémon from their discard pile into their deck\.$")


async def opp_discard_pokemon_to_deck(test, d, attack, m):
    P = pool(test)
    problems = []
    for npk in (3, 0):
        def prep(b):
            set_discard(b.t, P2, [test.filler] * npk + [P['item'], basic_energy_def(test, PokemonTypes.FIRE)])
        b = board(test, d, attack, prep=prep)
        t = b.t
        pk = [c for c in t.zone(P2, 'discard') if isinstance(def_for(c.archetype_id), PokemonCardDef)]
        if not await do_attack(b):
            return False, 'attack not offered'
        tag = f'[{npk} Pokémon in opp discard] '
        miss = in_deck_loose(t, pk, P2)
        if miss:
            problems.append(tag + f'not shuffled: {miss}')
        if len(t.zone(P2, 'discard')) != 2:
            problems.append(tag + f'opp discard now {len(t.zone(P2, "discard"))}, expected 2 non-Pokémon')
        if deck_len(t, P2) - b.before['opp_deck'] != npk:
            problems.append(tag + f'opp deck grew {deck_len(t, P2) - b.before["opp_deck"]}')
        placed = (BIG - t.hp(b.opp)) + (BIG - t.hp(b.opp_bench)) - (attack.damage or 0)
        if not has_ability(d) and placed != 10 * npk:
            problems.append(tag + f'placed {placed // 10} counters, expected {npk}')
    return (not problems), '; '.join(problems) or 'ok'


REVEAL_RX = (r"^reveal the top (\d+) cards of your deck\. this attack does (\d+) damage for each (psychic) pokémon you "
             r"find there\. then, shuffle those pokémon back into your deck and discard the other cards\.$")


async def reveal_shuffle_back(test, d, attack, m):
    n, per = int(m.group(1)), int(m.group(2))
    ps = psychic_basic(test)
    P = pool(test)

    def prep(b):
        set_deck(b.t, P1, [P['item']] * 10 + [ps, P['item'], ps] + [P['item']] * (n - 3))
    b = board(test, d, attack, prep=prep)
    t = b.t
    top = t.zone(P1, 'deck')[-n:]
    pk = [c for c in top if isinstance(def_for(c.archetype_id), PokemonCardDef)]
    if not await do_attack(b):
        return False, 'attack not offered'
    problems = []
    miss = in_deck_loose(t, pk, P1)
    if miss:
        problems.append(f'Pokémon not back in deck: {miss}')
    if len(t.zone(P1, 'discard')) - b.before['my_discard'] != n - 2:
        problems.append(f'discarded {len(t.zone(P1, "discard")) - b.before["my_discard"]}, expected {n - 2}')
    if not has_ability(d) and dealt(b) != per * 2:
        problems.append(f'damage {dealt(b)}, expected {per * 2}')
    return (not problems), '; '.join(problems) or 'ok'


RULINGS = set()     # "up to" picks that force at least 1 (minimum=1)


# ================================================================ abilities ==
AB_SELF_RX = (r"^once during your turn(?: \(before your attack\))?, (?:(if this pokémon is in the active spot, )you may "
              r"shuffle it|you may shuffle this pokémon|you may (draw 3 cards)\. if you drew any cards in this way, "
              r"shuffle this pokémon|you may (put 2 damage counters on 1 of your opponent's pokémon)\. if you placed "
              r"any damage counters in this way, shuffle this pokémon) and %s into your deck\.$" % ATTACHED)


def ability_board(test, d, where):
    t = ShTable(test)
    t.yes = True
    if where == 'active':
        me = t.put(d, P1, 'active')
        other = neutral(t.put(test.filler, P1, 'bench'))
    else:
        other = neutral(t.put(test.filler, P1, 'active'))
        me = t.put(d, P1, 'bench')
    opp = neutral(t.put(test.filler, P2, 'active'))
    opp_bench = neutral(t.put(test.filler, P2, 'bench'))
    decorate(t, me)
    add_pre_evolution(t, d, me)
    return t, me, other, opp, opp_bench


async def ability_self_shuffle(test, d, ability, m):
    active_only, draw, counters = m.group(1), m.group(2), m.group(3)
    problems = []
    for where in ('bench', 'active'):
        t, me, other, opp, opp_bench = ability_board(test, d, where)
        cards = stack(me)
        deck0, hand0 = deck_len(t, P1), len(t.zone(P1, 'hand'))
        entry = t.ability_offer(me, ability.title)
        tag = f'[{where}] '
        if active_only and where == 'bench':
            if entry is not None:
                problems.append(tag + 'offered on the Bench (text: if in the Active Spot)')
            continue
        if entry is None:
            problems.append(tag + 'not offered')
            continue
        await t.do(entry)
        drawn = len(t.zone(P1, 'hand')) - hand0
        problems += [tag + p for p in check_stack_shuffled(t, cards, P1, deck0 + (-drawn if draw else 0))]
        if draw and drawn != 3:
            problems.append(tag + f'drew {drawn}, expected 3')
        if counters:
            got = (BIG - t.hp(opp)) + (BIG - t.hp(opp_bench))
            if got != 20:
                problems.append(tag + f'placed {got // 10} counters, expected 2')
        if where == 'active' and t.active(P1) is not other:
            problems.append(tag + 'bench not promoted')
    return (not problems), '; '.join(problems) or 'ok'


GIANT_FAN_RX = (r"^when you play this pokémon from your hand to evolve 1 of your pokémon, you may flip a coin\. if heads, "
                r"choose 1 of your opponent's pokémon\. your opponent shuffles that pokémon and all cards attached to it "
                r"into his or her deck\.$")


async def ability_giant_fan(test, d, ability, m):
    problems = []
    for heads in (True, False):
        built = evolve_board(test, d)
        if built is None:
            return None, 'no pre-evolution'
        t, base, card, bench, opp, opp_bench = built
        t.heads = heads
        t.yes = True
        decorate(t, opp_bench)
        t.pokemon = lambda cands, prompt: opp_bench if opp_bench in cands else cands[0]
        cards = stack(opp_bench)
        deck0, mine0 = deck_len(t, P2), deck_len(t, P1)
        await t.play(card, targets=[base.entity_id])
        tag = f'[heads={heads}] '
        if heads:
            problems += [tag + p for p in check_stack_shuffled(t, cards, P2, deck0, 'chosen opp Pokémon')]
            if deck_len(t, P1) != mine0:
                problems.append(tag + 'my deck changed')
        elif not in_play(t, opp_bench):
            problems.append(tag + 'tails but shuffled')
    return (not problems), '; '.join(problems) or 'ok'



# ================================================================= trainers ==
# Trainer scripts have no text field: texts below are the printed (current
# errata) wordings, keyed by display name.  Every GLC-legal printing is run.
def trainer_defs(name):
    out = [d for d in CARD_DEFS_BY_GUID.values()
           if not isinstance(d, PokemonCardDef) and d.display_name == name and is_glc_legal(d)]
    return sorted(out, key=lambda d: (d.set_code, d.collector_number))


def trainer_table(test):
    t = ShTable(test)
    t.yes = True
    me = neutral(t.put(test.filler, P1, 'active'))
    bench = neutral(t.put(test.filler, P1, 'bench'))
    neutral(t.put(test.filler, P2, 'active'))
    neutral(t.put(test.filler, P2, 'bench'))
    return t, me, bench


async def play_trainer(t, card):
    if not t.can(card, 'UseTrainerCard'):
        return False
    await t.play(card)
    return True


def is_pk(c):
    return isinstance(def_for(c.archetype_id), PokemonCardDef)


def kind_specs(test, kind):
    """(matching specs, non-matching specs, match(def))"""
    P = pool(test)
    bt = P['basic_by_type']
    fire = basic_energy_def(test, PokemonTypes.FIRE)
    if kind == 'pokemon':
        return discard_kind(test, 'pokémon', False)
    if kind == 'combo':
        return discard_kind(test, 'in any combination', False)
    if kind == 'pokemon_supporter':
        return ([test.filler, P['supporter'], P['stage1'], P['supporter']] * 3,
                [P['item'], fire, trainer_defs("Team Yell's Cheer")[0]],
                lambda dd: isinstance(dd, PokemonCardDef) or
                (isinstance(dd, SupporterCardDef) and dd.display_name != "Team Yell's Cheer"))
    raise KeyError(kind)


async def tr_discard(test, d, n, upto, kind, draw=0):
    matching, nonmatch, match = kind_specs(test, kind)
    cards = {}

    def factory():
        t, _, _ = trainer_table(test)
        cards[id(t)] = t.put(d, P1, 'hand')
        return t

    async def act(tt):
        tt.hand0 = len(tt.zone(P1, 'hand')) - 1
        return await play_trainer(tt, cards[id(tt)])
    problems = await discard_to_deck_judge(factory, n, upto, match, matching, nonmatch, act, label_=label(d),
                                           draw=draw)
    # nothing matching in the discard -> not playable
    t = factory()
    set_discard(t, P1, nonmatch)
    if t.can(cards[id(t)], 'UseTrainerCard'):
        problems.append('playable with no matching card in the discard')
    if draw:
        for k in (n, 0) if upto else (n,):
            t = factory()
            set_discard(t, P1, nonmatch + matching[:n + 1])
            Rec(t, lambda cs, c, k=k: cs[:k])
            hand0 = len(t.zone(P1, 'hand')) - 1
            if await play_trainer(t, cards[id(t)]):
                got = len(t.zone(P1, 'hand')) - hand0
                want = draw if k else 0
                if got != want:
                    problems.append(f'[shuffled {k}] drew {got}, expected {want}')
    return problems


async def tr_two_kinds(test, d, n, water):
    """Ordinary Rod / Great Haul Net: up to n Pokémon and/or up to n basic Energy."""
    P = pool(test)
    bt = P['basic_by_type']
    if water:
        pk, en = bt[PokemonTypes.WATER.value], basic_energy_def(test, PokemonTypes.WATER)
        junk = [bt[PokemonTypes.FIRE.value], basic_energy_def(test, PokemonTypes.FIRE), P['item']]
    else:
        pk, en = test.filler, basic_energy_def(test, PokemonTypes.FIRE)
        junk = [P['special_energy'], P['item'], P['supporter']]
    problems = []
    for take_p, take_e in ((n, n), (0, n), (n, 0)):
        t, _, _ = trainer_table(test)
        card = t.put(d, P1, 'hand')
        set_discard(t, P1, junk + [pk] * (n + 1) + [en] * (n + 1))
        disc = list(t.zone(P1, 'discard'))
        deck0 = deck_len(t, P1)

        def chooser(cards, count, tp=take_p, te=take_e):
            k = tp if is_pk(cards[0]) else te
            return cards[:k]
        rec = Rec(t, chooser)
        tag = f'[take {take_p} Pokémon/{take_e} Energy] '
        if not await play_trainer(t, card):
            problems.append(tag + 'not playable')
            continue
        moved = [c for c in disc if c in t.zone(P1, 'deck')]
        mp = [c for c in moved if is_pk(c)]
        bad = [dname(c) for c in moved if c.archetype_id in {x.archetype_id for x in disc[:len(junk)]}]
        for cands, count, _ in rec.calls:
            if count != n:
                problems.append(tag + f'pick count {count}, text {n}')
            wrong = [dname(c) for c in cands if c.archetype_id not in (disc[len(junk)].archetype_id,
                                                                       disc[-1].archetype_id)]
            if wrong:
                problems.append(tag + f'non-matching offered {wrong}')
        if len(mp) != take_p or len(moved) - len(mp) != take_e:
            problems.append(tag + f'shuffled {len(mp)} Pokémon + {len(moved) - len(mp)} Energy')
        if bad:
            problems.append(tag + f'non-matching shuffled {bad}')
        if deck_len(t, P1) - deck0 != take_p + take_e:
            problems.append(tag + f'deck grew {deck_len(t, P1) - deck0}')
    return problems


async def tr_rescue_stretcher(test, d):
    problems = []
    for avail in (4, 2):
        t, _, _ = trainer_table(test)
        card = t.put(d, P1, 'hand')
        set_discard(t, P1, [pool(test)['item'], basic_energy_def(test, PokemonTypes.FIRE)] + [test.filler] * avail)
        disc = list(t.zone(P1, 'discard'))
        deck0 = deck_len(t, P1)

        async def choose(ctx, prompt, buttons, *a, **k):
            return 1                               # "Shuffle 3 Pokémon ... into your deck"
        with patch.object(EffectContext, 'choose', choose):
            ok = await play_trainer(t, card)
        if not ok:
            problems.append(f'[{avail}] not playable')
            continue
        moved = [c for c in disc if c in t.zone(P1, 'deck')]
        want = min(3, avail)
        if len(moved) != want or any(not is_pk(c) for c in moved):
            problems.append(f'[{avail} Pokémon in discard] shuffled {[dname(c) for c in moved]}, expected {want} Pokémon')
        mins = t.minimums[0][2] if t.minimums else 'n/a'
        if mins not in (None, want):
            problems.append(f'[{avail}] flat 3 but minimum={mins}')
        if deck_len(t, P1) - deck0 != want:
            problems.append(f'[{avail}] deck grew {deck_len(t, P1) - deck0}')
    return problems


async def tr_lana(test, d):
    P = pool(test)
    problems = []
    for tools in (2, 0):
        t, _, _ = trainer_table(test)
        card = t.put(d, P1, 'hand')
        set_discard(t, P1, [P['item'], basic_energy_def(test, PokemonTypes.FIRE), test.filler, P['stage1']]
                    + [P['tool']] * tools)
        disc = list(t.zone(P1, 'discard'))
        if not await play_trainer(t, card):
            problems.append(f'[{tools} tools] not playable')
            continue
        moved = [c for c in disc if c in t.zone(P1, 'deck')]
        npk = sum(1 for c in moved if is_pk(c))
        ntool = sum(1 for c in moved if isinstance(def_for(c.archetype_id), PokemonToolCardDef))
        if npk != 1 or ntool != min(1, tools) or len(moved) != 1 + min(1, tools):
            problems.append(f'[{tools} tools in discard] shuffled {[dname(c) for c in moved]}, '
                            f'expected 1 Pokémon + {min(1, tools)} Tool')
    return problems


async def tr_roseanne(test, d):
    P = pool(test)
    t, _, _ = trainer_table(test)
    card = t.put(d, P1, 'hand')
    set_discard(t, P1, [P['item'], test.filler, P['stage1'], P['tool'], P['tool'], P['stadium'],
                        basic_energy_def(test, PokemonTypes.FIRE), basic_energy_def(test, PokemonTypes.WATER)])
    disc = list(t.zone(P1, 'discard'))
    deck0 = deck_len(t, P1)
    if not await play_trainer(t, card):
        return ['not playable']
    moved = [c for c in disc if c in t.zone(P1, 'deck')]
    npk = sum(1 for c in moved if is_pk(c))
    problems = []
    if npk != 1:
        problems.append(f'shuffled {npk} Pokémon, expected exactly 1')
    if len(moved) != 4 or deck_len(t, P1) - deck0 != 4:
        problems.append(f'shuffled {[dname(c) for c in moved]}, expected 1 Pokémon/Tool/Stadium/Energy each')
    return problems


async def tr_cassius(test, d):
    t, me, bench = trainer_table(test)
    card = t.put(d, P1, 'hand')
    decorate(t, bench)
    cards = stack(bench)
    seen = []
    t.pokemon = lambda cands, prompt: (seen.append(list(cands)), bench)[1]
    deck0 = deck_len(t, P1)
    if not await play_trainer(t, card):
        return ['not playable']
    problems = check_stack_shuffled(t, cards, P1, deck0, 'chosen Pokémon stack')
    if seen and me not in seen[0]:
        problems.append('Active not offered (text: 1 of your Pokémon)')
    if not in_play(t, me):
        problems.append('Active left play')
    # alone in play -> not playable (would leave no Active)
    t2, me2, bench2 = trainer_table(test)
    t2.board.find_player_area(P1, 'bench').remove_child(bench2)
    c2 = t2.put(d, P1, 'hand')
    if t2.can(c2, 'UseTrainerCard'):
        RULINGS.add('Cassius playable with only the Active in play')
    return problems


async def tr_ninja_boy(test, d):
    P = pool(test)
    t, me, bench = trainer_table(test)
    card = t.put(d, P1, 'hand')
    decorate(t, me)
    hurt(t, me, 30)
    attached = [c for c in stack(me) if c is not me]
    new_def = P['basic_by_type'][PokemonTypes.FIRE.value]
    set_deck(t, P1, [P['item']] * 5 + [new_def])
    t.pokemon = lambda cands, prompt: me if me in cands else cands[0]
    deck0 = deck_len(t, P1)
    if not await play_trainer(t, card):
        return ['not playable']
    problems = []
    new = t.active(P1)
    if new is me or new is None or def_for(new.archetype_id) is not new_def:
        problems.append(f'Active is {dname(new) if new else None}, expected the searched Basic')
    if me.entity_id not in ids(t.zone(P1, 'deck')):
        problems.append('first Pokémon not shuffled into the deck')
    lost = [dname(c) for c in attached if new is None or c not in stack(new)]
    if lost:
        problems.append(f'attached cards did not stay on the new Pokémon: {lost}')
    if deck_len(t, P1) != deck0:
        problems.append(f'deck size {deck0} -> {deck_len(t, P1)} (one out, one in)')
    if new is not None and t.damage(new) != 30:
        problems.append(f'damage on new Pokémon {t.damage(new)}, expected 30')
    return problems


async def tr_perrin(test, d):
    P = pool(test)
    bt = P['basic_by_type']
    problems = []
    for reveal in (2, 1, 0):
        t, _, _ = trainer_table(test)
        card = t.put(d, P1, 'hand')
        hand_pk = [t.put(test.filler, P1, 'hand'), t.put(P['stage1'], P1, 'hand')]
        t.put(P['item'], P1, 'hand')
        deck_pk = set_deck(t, P1, [P['item']] * 5 + [bt[PokemonTypes.FIRE.value], bt[PokemonTypes.WATER.value],
                                                       bt[PokemonTypes.GRASS.value]])[5:]
        calls = []

        def chooser(cards, count, r=reveal):
            calls.append((list(cards), count))
            if len(calls) == 1:
                return [c for c in cards if c in hand_pk][:r]
            return [c for c in cards if c in deck_pk][:count]
        Rec(t, chooser)
        if not await play_trainer(t, card):
            problems.append(f'[reveal {reveal}] not playable')
            continue
        tag = f'[reveal {reveal}] '
        into_deck = [c for c in hand_pk if c in t.zone(P1, 'deck')]
        got = [c for c in deck_pk if c in t.zone(P1, 'hand')]
        if len(into_deck) != reveal:
            problems.append(tag + f'{len(into_deck)} hand Pokémon put into deck')
        if len(got) != reveal:
            problems.append(tag + f'took {len(got)} Pokémon from the deck, expected {reveal}')
        if calls and [c for c in calls[0][0] if not is_pk(c)]:
            problems.append(tag + 'non-Pokémon offered from hand')
    return problems


async def tr_communication(test, d):
    P = pool(test)
    bt = P['basic_by_type']
    problems = []
    t, _, _ = trainer_table(test)
    card = t.put(d, P1, 'hand')
    a = t.put(test.filler, P1, 'hand')
    t.put(P['item'], P1, 'hand')
    c_ = set_deck(t, P1, [P['item']] * 5 + [bt[PokemonTypes.FIRE.value]])[-1]
    hand0, deck0 = len(t.zone(P1, 'hand')), deck_len(t, P1)
    if not await play_trainer(t, card):
        return ['not playable']
    if a not in t.zone(P1, 'deck'):
        problems.append('hand Pokémon not put into the deck')
    if c_ not in t.zone(P1, 'hand'):
        problems.append('deck Pokémon not put into hand')
    if deck_len(t, P1) != deck0:
        problems.append(f'deck size {deck0} -> {deck_len(t, P1)}')
    t2, _, _ = trainer_table(test)
    c2 = t2.put(d, P1, 'hand')
    t2.put(P['item'], P1, 'hand')
    set_deck(t2, P1, [P['item']] * 5 + [bt[PokemonTypes.FIRE.value]])
    if t2.can(c2, 'UseTrainerCard'):
        problems.append('playable with no Pokémon in hand')
    return problems


async def tr_devolution_spray_z(test, d):
    P = pool(test)
    st1 = P['stage1']
    pre = pre_evolution(st1)
    t = ShTable(test)
    base = neutral(t.put(pre, P1, 'active'), hp=None)
    neutral(t.put(test.filler, P1, 'bench'))
    neutral(t.put(test.filler, P2, 'active'))
    evo = t.put(st1, P1, 'hand')
    await t.session.perform_evolution(P1, evo, base)
    t.state.entered_play_turn[evo.entity_id] = 0
    t.energy(evo, PokemonTypes.FIRE)
    energy = t.board.attached_energies(evo)[0]
    card = t.put(d, P1, 'hand')
    t.pokemon = lambda cands, prompt: evo if evo in cands else cands[0]
    Rec(t, lambda cards, count: [c for c in cards if c is evo] or cards[:count])
    deck0 = deck_len(t, P1)

    async def choose(ctx, prompt, buttons, *a, **k):
        return 0
    with patch.object(EffectContext, 'choose', choose):
        if not await play_trainer(t, card):
            return ['not playable']
    problems = []
    if evo.entity_id not in ids(t.zone(P1, 'deck')):
        problems.append('Evolution card not loose in the deck')
    if t.active(P1) is not base:
        problems.append(f'Active is {dname(t.active(P1)) if t.active(P1) else None}, expected the Basic')
    elif energy not in stack(base):
        problems.append('Energy did not stay on the devolved Pokémon')
    if deck_len(t, P1) - deck0 != 1:
        problems.append(f'deck grew {deck_len(t, P1) - deck0}, expected 1')
    return problems


TRAINERS = [
    # name, printed text, checker
    ('Super Rod', 'Shuffle up to 3 in any combination of Pokémon and basic Energy cards from your discard pile into your deck.',
     lambda test, d: tr_discard(test, d, 3, True, 'combo')),
    ("Brock's Grit", 'Shuffle 6 in any combination of Pokémon and basic Energy cards from your discard pile into your deck.',
     lambda test, d: tr_discard(test, d, 6, False, 'combo')),
    ('Miriam', 'Shuffle up to 5 Pokémon from your discard pile into your deck. If you shuffled any cards into your deck in this way, draw 3 cards.',
     lambda test, d: tr_discard(test, d, 5, True, 'pokemon', draw=3)),
    ('Sacred Ash', 'Shuffle up to 5 Pokémon from your discard pile into your deck. (errata of "Shuffle 5")',
     lambda test, d: tr_discard(test, d, 5, True, 'pokemon')),
    ("Team Yell's Cheer", "Shuffle up to 3 in any combination of Pokémon and Supporter cards, except for Team Yell's Cheer, from your discard pile into your deck.",
     lambda test, d: tr_discard(test, d, 3, True, 'pokemon_supporter')),
    ('Ordinary Rod', 'Choose 1 or both: Shuffle up to 2 Pokémon / up to 2 basic Energy cards from your discard pile into your deck.',
     lambda test, d: tr_two_kinds(test, d, 2, False)),
    ('Great Haul Net', 'Choose 1 or both: Shuffle up to 3 Water Pokémon / up to 3 Basic Water Energy cards from your discard pile into your deck.',
     lambda test, d: tr_two_kinds(test, d, 3, True)),
    ('Rescue Stretcher', 'Choose 1: Put a Pokémon from your discard pile into your hand. / Shuffle 3 Pokémon from your discard pile into your deck.',
     tr_rescue_stretcher),
    ("Lana's Fishing Rod", 'Shuffle a Pokémon and a Pokémon Tool card from your discard pile into your deck.', tr_lana),
    ("Roseanne's Backup", 'Choose 1 or more: Shuffle a Pokémon / a Pokémon Tool / a Stadium / an Energy card from your discard pile into your deck.',
     tr_roseanne),
    ('Cassius', 'Shuffle 1 of your Pokémon and all cards attached to it into your deck.', tr_cassius),
    ('Ninja Boy', 'Choose 1 of your Basic Pokémon in play. Search your deck for a Basic Pokémon and switch it with that Pokémon. (...) Shuffle the first Pokémon into your deck.',
     tr_ninja_boy),
    ('Perrin', 'Reveal up to 2 Pokémon in your hand and put them into your deck. If you do, search your deck for up to that many Pokémon, reveal them, and put them into your hand. Then, shuffle your deck.',
     tr_perrin),
    ('Pokémon Communication', 'Reveal a Pokémon from your hand and put it into your deck. Then, search your deck for a Pokémon, reveal it, and put it into your hand. Shuffle your deck afterward.',
     tr_communication),
    ('Devolution Spray Z', 'Devolve 1 of your evolved Pokémon by shuffling any number of Evolution cards on it into your deck.',
     tr_devolution_spray_z),
]


async def run_trainer_sweep(test):
    os.makedirs(REPORT_DIR, exist_ok=True)
    checked, failures, skipped = 0, [], []
    for name, text, fn in TRAINERS:
        defs = trainer_defs(name)
        if not defs:
            skipped.append({'card': name, 'why': 'no GLC-legal printing'})
        for d in defs:
            checked += 1
            try:
                problems = await fn(test, d)
            except Exception as ex:
                import traceback
                problems = [f'ERROR {type(ex).__name__}: {ex} @ {traceback.format_exc().splitlines()[-3].strip()}']
            if problems:
                failures.append({'card': label(d), 'guid': d.guid, 'text': text, 'detail': '; '.join(problems)})
    with open(os.path.join(REPORT_DIR, 'shuf_trainers.json'), 'w') as fh:
        json.dump({'case': 'shuf_trainers', 'checked': checked, 'failures': failures, 'skipped': skipped},
                  fh, indent=1, ensure_ascii=False)
    return checked, failures, skipped


BUG_OUT_RX = (r"^reveal the bottom (\d+) cards of your deck, and this attack does (\d+) damage for each pokémon you find "
              r"there that has the ([\w -]+) attack\. then, shuffle any revealed pokémon back into your deck\. discard the "
              r"other cards\.$")


async def bug_out_reveal(test, d, attack, m):
    n, per, title = int(m.group(1)), int(m.group(2)), m.group(3)
    if norm(attack.title) != title:
        return None, 'counts a different attack name'
    P = pool(test)

    def prep(b):
        # bottom of the deck = first children
        set_deck(b.t, P1, [d, P['item'], test.filler, d] + [P['item']] * (n - 4) + [P['item']] * 8)
    b = board(test, d, attack, prep=prep)
    t = b.t
    bottom = t.zone(P1, 'deck')[:n]
    pk = [c for c in bottom if is_pk(c)]
    if not await do_attack(b):
        return False, 'attack not offered'
    problems = []
    miss = in_deck_loose(t, pk, P1)
    if miss:
        problems.append(f'revealed Pokémon not back in deck: {miss}')
    disc = len(t.zone(P1, 'discard')) - b.before['my_discard']
    if disc != n - len(pk):
        problems.append(f'discarded {disc}, expected {n - len(pk)}')
    if not has_ability(d) and dealt(b) != per * 2:
        problems.append(f'damage {dealt(b)}, expected {per * 2} (2 with {title})')
    return (not problems), '; '.join(problems) or 'ok'


SCATTER_RX = (r"^at the end of your opponent's turn, if this pokémon has any damage counters on it, flip a coin\. "
              r"if tails, shuffle this pokémon and %s into your deck\.$" % ATTACHED)


async def ability_scatter(test, d, ability, m):
    problems = []
    # (where, damaged, heads, whose turn ends, should shuffle)
    runs = [('bench', True, False, P2, True), ('active', True, False, P2, True),
            ('bench', True, True, P2, False), ('bench', False, False, P2, False),
            ('bench', True, False, P1, False)]
    for where, damaged, heads, ending, should in runs:
        t, me, other, opp, opp_bench = ability_board(test, d, where)
        t.heads = heads
        if damaged:
            hurt(t, me, 10)
        else:
            me.set_attribute(AttrID.HP, effective_max_hp(t.board, me))
        if ending == P2:
            t.next_turn()
        cards = stack(me)
        deck0 = deck_len(t, P1)
        await t._run(lambda: t.session._fire_passive_event(ending, 'on_end_turn'))
        tag = f'[{where}, damaged={damaged}, heads={heads}, end of {"opp" if ending == P2 else "own"} turn] '
        if should:
            problems += [tag + p for p in check_stack_shuffled(t, cards, P1, deck0)]
            if where == 'active' and t.active(P1) is not other:
                problems.append(tag + 'bench not promoted')
        elif not in_play(t, me):
            problems.append(tag + 'shuffled although it should stay')
    return (not problems), '; '.join(problems) or 'ok'


LEAP_RX = (r"^when this pokémon is knocked out, flip a coin\. if heads, shuffle this pokémon and %s into your deck, "
           r"and your opponent can't take any prize cards for it\.$" % ATTACHED)


async def ability_leap(test, d, ability, m):
    att_def, att = pool(test)['attacker']
    problems = []
    for heads in (True, False):
        t, me, other, opp, opp_bench = ability_board(test, d, 'active')
        t.heads = heads
        me.set_attribute(AttrID.HP, 10)
        t.board.find_player_area(P2, 'activePokemonArea').remove_child(opp)
        attacker = neutral(t.put(att_def, P2, 'active'))
        pay_cost(t, attacker, att)
        t.next_turn()
        cards = stack(me)
        deck0, prizes0 = deck_len(t, P1), len(t.zone(P2, 'prizes'))
        hand0 = len(t.zone(P2, 'hand'))
        entry = t.attack_offer(attacker, att.title, pid=P2)
        if entry is None:
            return None, 'attacker not offered'
        await t.do(entry, pid=P2)
        tag = f'[heads={heads}] '
        taken = prizes0 - len(t.zone(P2, 'prizes'))
        if in_play(t, me):
            problems.append(tag + 'not Knocked Out (setup)')
            continue
        if heads:
            problems += [tag + p for p in check_stack_shuffled(t, cards, P1, deck0)]
            if taken:
                problems.append(tag + f'opponent took {taken} Prize(s)')
        else:
            if taken != 1:
                problems.append(tag + f'opponent took {taken} Prizes, expected 1')
            if deck_len(t, P1) != deck0:
                problems.append(tag + 'tails but deck changed')
    return (not problems), '; '.join(problems) or 'ok'


ATTACK_CASES = [
    SweepCase('shuf_self', SELF_RX, self_shuffle),
    SweepCase('shuf_self_bonus', BONUS_RX, self_shuffle_bonus),
    SweepCase('shuf_self_heal', HEAL_SELF_RX, self_shuffle_heal),
    SweepCase('shuf_opp_active', OPP_ACTIVE_RX, opp_active_shuffle),
    SweepCase('shuf_opp_bench', OPP_BENCH_RX, opp_bench_shuffle),
    SweepCase('shuf_opp_bench_then_self', THEN_SELF_RX, opp_bench_then_self),
    SweepCase('shuf_expelling_tornado', TORNADO_RX, expelling_tornado),
    SweepCase('shuf_each_active', EACH_ACTIVE_RX, each_active_shuffle),
    SweepCase('shuf_own_bench', OWN_BENCH_RX, own_bench_shuffle),
    SweepCase('shuf_discard_to_deck', DISCARD_RX, discard_pokemon_to_deck),
    SweepCase('shuf_opp_discard_to_deck', OPP_DISCARD_RX, opp_discard_pokemon_to_deck),
    SweepCase('shuf_reveal_back', REVEAL_RX, reveal_shuffle_back),
    SweepCase('shuf_bug_out', BUG_OUT_RX, bug_out_reveal),
]
ABILITY_CASES = [
    SweepCase('shuf_ability_self', AB_SELF_RX, ability_self_shuffle, attack_only=False),
    SweepCase('shuf_ability_giant_fan', GIANT_FAN_RX, ability_giant_fan, attack_only=False),
    SweepCase('shuf_ability_scatter', SCATTER_RX, ability_scatter, attack_only=False),
    SweepCase('shuf_ability_leap', LEAP_RX, ability_leap, attack_only=False),
]

# Wordings in scope that no checker reads (reported for manual review).
SCOPE_RX = re.compile(r"shuffl[^.]*pokémon[^.]*into|pokémon[^.]*shuffl[^.]*into (?:your|their|his|her)")


class SweepShufflePokemon(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    LIMIT = None

    async def test_attacks_and_abilities(self):
        for case in ATTACK_CASES + ABILITY_CASES:
            checked, failures, skipped = await run_sweep(self, case, limit=self.LIMIT)
            print(f"{case.name}: checked {checked}, failures {len(failures)}, skipped {len(skipped)}")

    async def test_unmatched_scope(self):
        """In-scope wordings no checker reads (manual review list)."""
        from tests.sweep_core import unique_pokemon
        rxs = [re.compile(c.pattern) for c in ATTACK_CASES + ABILITY_CASES]
        out = {}
        for d in unique_pokemon():
            for a in d.abilities or []:
                text = norm(a.game_text)
                if SCOPE_RX.search(text) and 'deck' in text and not any(r.search(text) for r in rxs):
                    out.setdefault(text, []).append(label(d, a))
        with open(os.path.join(REPORT_DIR, 'shuf_unmatched.json'), 'w') as fh:
            json.dump(out, fh, indent=1, ensure_ascii=False)
        print(f"shuf_unmatched: {len(out)} wordings, {sum(len(v) for v in out.values())} cards")

    async def test_trainers(self):
        checked, failures, skipped = await run_trainer_sweep(self)
        print(f"shuf_trainers: checked {checked}, failures {len(failures)}, skipped {len(skipped)}")
        print('rulings:', sorted(RULINGS))


if __name__ == "__main__":
    unittest.main()
