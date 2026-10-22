"""Sweep: every GLC-legal Pokémon ATTACK whose text discards something.

For each distinct attack text (title + text + damage, all printings noted) a
template turns the text into scenarios on a *rich board* where every zone holds
cards of every kind, so a wrong discard is visible:

  P1  attacker (Active, cost paid) + a Float Stone; Bench filler with a Water
      Energy and a Float Stone; hand = Item, Fire Energy, Water Energy, Pokémon,
      Supporter, Tool; deck = 30 filler Items (+ marked top cards).
  P2  Active filler with Fire + Water basic Energy, Weakness Guard Energy
      (Special, provides C) and a Float Stone; Bench filler with Water Energy,
      Weakness Guard Energy and a Float Stone; same hand kinds; 30-card deck.

After the attack, the set of cards that newly arrived in each discard pile is
compared with what the text allows (which cards, whose, how many), the
discard prompts are checked (candidates offered, minimum, who chooses), and
damage tied to the discard is checked.

Reports: /home/claude/bughunt/sweep/attack_discard.json
Real bugs: targeted @expectedFailure tests at the bottom (# BUG: ...).
"""
import collections
import json
import os
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost, norm, REPORT_DIR, BIG
from spirit.game import glc
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import (CARD_DEFS_BY_GUID, PokemonCardDef, Attack, def_for,
                                    SupporterCardDef, ItemCardDef, StadiumCardDef,
                                    PokemonToolCardDef, EnergyCardDef)
from spirit.game.models.board import PokemonEntity
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

FLOAT_STONE = '5d073628-31df-5dd0-91f1-df851a226be7'       # Tool, retreat only
WG_ENERGY = None                                            # Weakness Guard Energy (resolved lazily)
HAU = 'f471107c-e923-58bd-830c-34517922bfad'               # Supporter
PATH = 'b99e0bc2-063c-5165-a2d9-45283bb3deb1'              # Path to the Peak (Stadium)
COURT = '8fb314ca-2d3d-5117-a5bd-573d2d67bd15'             # Training Court (Stadium)
COUNTER = '18067340-de24-5600-9414-57fe907d07c7'           # Counter Energy
ELECTRODE_XY12 = None

TYPES = {'grass': PokemonTypes.GRASS, 'fire': PokemonTypes.FIRE, 'water': PokemonTypes.WATER,
         'lightning': PokemonTypes.LIGHTNING, 'psychic': PokemonTypes.PSYCHIC,
         'fighting': PokemonTypes.FIGHTING, 'darkness': PokemonTypes.DARKNESS,
         'metal': PokemonTypes.METAL, 'fairy': PokemonTypes.FAIRY}
TYPE_RX = r"(?:grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy)"
NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}
HIS = r"(?:his or her|their)"
WORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def num(s):
    return NUM[s] if s in NUM else int(s)


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


def def_attr(definition, attr_id, default=None):
    spec = (getattr(definition, 'extra_attributes', None) or {}).get(str(attr_id.value))
    return spec.get("value", default) if isinstance(spec, dict) else default


def dname(c):
    return def_for(c.archetype_id).display_name or '?'


def find_def(name, kind=None, set_code=None):
    for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, str(d.collector_number))):
        if d.display_name == name and (kind is None or isinstance(d, kind)) \
                and (set_code is None or d.set_code == set_code) and glc.is_glc_legal(d):
            return d
    raise KeyError(name)


# ===================================================================== table ==
class DTable(Table):
    """Table that records every discard prompt and scripts all choosers."""

    def __init__(self, test):
        super().__init__(test)
        self.calls = []          # (kind, player, prompt, cards, count, minimum)
        self.pick_mode = 'max'   # 'max' | 'min' | callable(cards, count, minimum, prompt) -> list
        self.choice = 0
        self.placement = None
        self.unit_pick = None    # callable(energies, amount) -> list

    def _patches(self):
        table = self
        out = super()._patches()
        base_pokemon = out[1].new

        async def choose_cards(ctx, cards, count, minimum=None, prompt='', player_id=None,
                               ordered=False, display_cards=None, slot_prompt='', submit_on_pick=False):
            cards = list(cards)
            pid = player_id or ctx.player_id
            if (not cards and not display_cards) or count <= 0:
                return []
            table.calls.append(('cards', pid, prompt or '', cards, count, minimum))
            table.prompts.append(prompt)
            eff_min = count if minimum is None else minimum
            eff_min = min(eff_min, len(cards))
            if callable(table.pick_mode):
                return list(table.pick_mode(cards, count, minimum, prompt))
            k = min(count, len(cards)) if table.pick_mode == 'max' else eff_min
            return list(reversed(cards))[:k]

        async def choose_pokemon(ctx, candidates, prompt='', player_id=None, *a, **k):
            table.calls.append(('pokemon', player_id or ctx.player_id, prompt or '', list(candidates), 1, None))
            return await base_pokemon(ctx, candidates, prompt)

        async def choose(ctx, prompt, buttons, player_id=None, descriptions=None, use_panel=True):
            table.calls.append(('choose', player_id or ctx.player_id, prompt or '', list(buttons), 1, None))
            return table.choice(prompt, list(buttons)) if callable(table.choice) else table.choice

        async def present_card_choice(ctx, card, prompt, buttons, player_id=None):
            table.calls.append(('choose', player_id or ctx.player_id, prompt or '', list(buttons), 1, None))
            return table.choice(prompt, list(buttons)) if callable(table.choice) else table.choice

        async def flip_until_tails(ctx, title=''):
            heads = 0
            while heads < 20:
                h = table.heads(title) if callable(table.heads) else bool(table.heads)
                if not h:
                    break
                heads += 1
            return heads

        async def unit_picker(session, player_id, source_entity_id, energies, amount, prompt='Choose Energy to discard'):
            from spirit.game.session.legal_actions import energy_provided_count
            energies = list(energies)
            table.calls.append(('units', player_id, prompt or '', energies, amount, None))
            if table.unit_pick is not None:
                return [e.entity_id for e in table.unit_pick(energies, amount)]
            picked, paid = [], 0
            for e in reversed(energies):
                if paid >= amount:
                    break
                picked.append(e.entity_id)
                paid += energy_provided_count(e, session.board_state)
            return picked

        async def attempt_flip(session, player_id, attacker, title):
            return table.heads(title) if callable(table.heads) else bool(table.heads)

        async def placement(session, player_id, source_entity_id, candidates, count, *a, **k):
            if table.placement is not None:
                return table.placement(candidates, count)
            return {candidates[0].entity_id: count}

        async def view_cards(session, *a, **k):
            return None

        out[0] = patch.object(EffectContext, 'choose_cards', choose_cards)
        out[1] = patch.object(EffectContext, 'choose_pokemon', choose_pokemon)
        S = type(self.session)
        out += [patch.object(EffectContext, 'choose', choose),
                patch.object(EffectContext, 'present_card_choice', present_card_choice),
                patch.object(EffectContext, 'flip_until_tails', flip_until_tails),
                patch.object(S, 'prompt_energy_unit_picker', unit_picker),
                patch.object(S, '_resolve_attack_attempt_flip', attempt_flip),
                patch.object(S, 'prompt_damage_counter_placement', placement)]
        if hasattr(S, 'prompt_view_cards'):
            out.append(patch.object(S, 'prompt_view_cards', view_cards))
        return out

    # prompts that pick cards to discard
    def discard_calls(self):
        return [c for c in self.calls if c[0] in ('cards', 'units')]


# ===================================================================== board ==
class B:
    pass


def basic(test, kind):
    return CARD_DEFS_BY_GUID[test.energies[kind.value].lower()]


def wg_energy():
    global WG_ENERGY
    if WG_ENERGY is None:
        WG_ENERGY = find_def('Weakness Guard Energy', EnergyCardDef)
    return WG_ENERGY


def off_type(*avoid):
    for k in (PokemonTypes.WATER, PokemonTypes.FIRE, PokemonTypes.GRASS, PokemonTypes.PSYCHIC):
        if k not in avoid:
            return k


def energy_type(test, card):
    g = def_for(card.archetype_id).guid.lower()
    for v, guid in test.energies.items():
        if guid.lower() == g:
            return PokemonTypes(v)
    return None


def attacker_type(t, me):
    for v in me.get_attribute(AttrID.POKEMON_TYPES) or []:
        if v in t.test.energies:
            return PokemonTypes(v)
    return None


def stock_hand(t, pid, c, prefix):
    test = t.test
    c[prefix + 'h_item'] = t.put(test.item, pid, 'hand')
    c[prefix + 'h_fire'] = t.put(basic(test, PokemonTypes.FIRE), pid, 'hand')
    c[prefix + 'h_water'] = t.put(basic(test, PokemonTypes.WATER), pid, 'hand')
    c[prefix + 'h_mon'] = t.put(test.filler, pid, 'hand')
    c[prefix + 'h_sup'] = t.put(CARD_DEFS_BY_GUID[HAU], pid, 'hand')
    c[prefix + 'h_tool'] = t.put(CARD_DEFS_BY_GUID[FLOAT_STONE], pid, 'hand')


def make_board(test, d, attack, s):
    t = DTable(test)
    t.heads = s.get('heads', True)
    t.yes = s.get('yes', True)
    t.pick_mode = s.get('pick', 'max')
    if 'choice' in s:
        t.choice = s['choice']
    if 'pokemon' in s:
        t.pokemon = s['pokemon']
    b = B()
    b.t, b.d, b.attack, b.s = t, d, attack, s
    c = b.c = {}
    b.me = t.put(d, P1, 'active')
    neutral(b.me, None)
    b.me.attribute_originals[AttrID.HP.value] = BIG
    b.me.set_attribute(AttrID.HP, BIG)
    b.my_bench = neutral(t.put(test.filler, P1, 'bench'))
    c['my_bench_e'] = t.energy(b.my_bench, PokemonTypes.WATER)
    c['my_bench_tool'] = t.attach(CARD_DEFS_BY_GUID[FLOAT_STONE], b.my_bench)
    b.opp = neutral(t.put(test.filler, P2, 'active'))
    c['opp_fire'] = t.energy(b.opp, PokemonTypes.FIRE)
    c['opp_water'] = t.energy(b.opp, PokemonTypes.WATER)
    c['opp_special'] = t.attach(wg_energy(), b.opp)
    c['opp_tool'] = t.attach(CARD_DEFS_BY_GUID[FLOAT_STONE], b.opp)
    b.opp_bench = neutral(t.put(test.filler, P2, 'bench'))
    c['opp_bench_e'] = t.energy(b.opp_bench, PokemonTypes.WATER)
    c['opp_bench_special'] = t.attach(wg_energy(), b.opp_bench)
    c['opp_bench_tool'] = t.attach(CARD_DEFS_BY_GUID[FLOAT_STONE], b.opp_bench)
    if s.get('my_tool', True):
        c['my_tool'] = t.attach(CARD_DEFS_BY_GUID[FLOAT_STONE], b.me)
    stock_hand(t, P1, c, 'my_')
    stock_hand(t, P2, c, 'opp_')
    pay_cost(t, b.me, attack)
    b.own = attacker_type(t, b.me)
    meet_attack_conditions(b)
    if s.get('setup'):
        s['setup'](b)
    b.loc0 = locations(t)
    b.stack0 = {'me': stack_of(b.me), 'opp': stack_of(b.opp), 'my_bench': stack_of(b.my_bench),
                'opp_bench': stack_of(b.opp_bench)}
    b.disc0 = {pid: set(x.entity_id for x in t.zone(pid, 'discard')) for pid in (P1, P2)}
    b.hp0 = {'opp': t.hp(b.opp), 'opp_bench': t.hp(b.opp_bench), 'me': t.hp(b.me)}
    b.hand0 = {pid: list(t.zone(pid, 'hand')) for pid in (P1, P2)}
    b.deck0 = {pid: list(t.zone(pid, 'deck')) for pid in (P1, P2)}
    b.me_energy0 = list(t.board.attached_energies(b.me))
    b.opp_energy0 = list(t.board.attached_energies(b.opp))
    b.opp_bench_energy0 = list(t.board.attached_energies(b.opp_bench))
    return b


def meet_attack_conditions(b):
    """Satisfy printed 'this Pokémon can't attack unless ...' Abilities so the attack can be judged."""
    for ab in b.d.abilities or []:
        if isinstance(ab, Attack):
            continue
        tx = norm(getattr(ab, 'game_text', ''))
        if "can't attack unless your opponent has 2 or fewer prize cards remaining" in tx:
            b.t.set_prizes(P2, 2)
        if "can't attack unless regirock, regice, and registeel are on your bench" in tx:
            for nm in ('Regirock', 'Regice', 'Registeel'):
                neutral(b.t.put(find_def(nm, PokemonCardDef), P1, 'bench'))


def locations(t):
    out = {}

    def walk(node, where):
        for ch in list(getattr(node, 'children', []) or []):
            out[ch.entity_id] = (where, getattr(ch.parent, 'entity_id', None))
            walk(ch, where)
    for pid in (P1, P2):
        for z in ('activePokemonArea', 'bench', 'hand', 'deck', 'discard', 'prizePile', 'lostZone'):
            try:
                area = t.board.find_player_area(pid, z)
            except Exception:
                continue
            if area is not None:
                walk(area, (pid, z))
    walk(t.board.find_global_area('activeStadium'), ('global', 'stadium'))
    return out


def new_discards(b, pid):
    return [c for c in b.t.zone(pid, 'discard') if c.entity_id not in b.disc0[pid]]


def dealt(b, who='opp'):
    p = b.opp if who == 'opp' else b.opp_bench if who == 'opp_bench' else b.me
    in_play = p in b.t.board.pokemon_in_play(p.owning_player_id)
    return (b.hp0[who] - b.t.hp(p)) if in_play else b.hp0[who]


def desc(cards):
    return '[' + ', '.join(f"{dname(c)}@{where(c)}" for c in cards) + ']'


_BOARD = {}


def where(c):
    return _BOARD.get(c.entity_id, '?')


def label_cards(b):
    """entity_id -> short label of its pre-attack place."""
    names = {}
    for key, card in b.c.items():
        names[card.entity_id] = key
    for e in b.me_energy0:
        names.setdefault(e.entity_id, 'my_e')
    for e in b.opp_energy0:
        names.setdefault(e.entity_id, 'opp_e')
    for pid, tag in ((P1, 'my'), (P2, 'opp')):
        for i, card in enumerate(b.deck0[pid][::-1][:12]):
            names.setdefault(card.entity_id, f"{tag}_deck{i}")
        for card in b.hand0[pid]:
            names.setdefault(card.entity_id, f"{tag}_hand")
    names.setdefault(b.me.entity_id, 'ME')
    names.setdefault(b.opp.entity_id, 'OPP')
    return names


# ============================================================== expectations ==
class Want:
    """Allowed set of newly discarded cards for one player."""

    def __init__(self, pool=(), lo=0, hi=None, exact=False, note=''):
        self.pool = {c.entity_id for c in pool}
        self.lo = lo
        self.hi = len(self.pool) if hi is None else hi
        self.exact = exact
        self.note = note


def NONE():
    return Want((), 0, 0)


def EXACT(cards, note=''):
    cards = list(cards)
    return Want(cards, len(cards), len(cards), exact=True, note=note)


def POOL(cards, lo, hi=None, note=''):
    cards = list(cards)
    hi = lo if hi is None else hi
    return Want(cards, min(lo, len(cards)), min(hi, len(cards)), note=note)


def judge_discards(b, wants):
    """wants: {pid: Want}.  Cards a Want doesn't cover must not be discarded."""
    probs = []
    names = label_cards(b)
    for pid in (P1, P2):
        w = wants.get(pid) or NONE()
        got = new_discards(b, pid)
        ids = {c.entity_id for c in got}
        extra = [c for c in got if c.entity_id not in w.pool]
        tag = 'P1' if pid == P1 else 'P2'
        lbl = ', '.join(names.get(c.entity_id, dname(c)) for c in got)
        if extra:
            probs.append(f"{tag} discarded {', '.join(names.get(c.entity_id, dname(c)) for c in extra)} "
                         f"(not allowed; all: {lbl})")
        elif not (w.lo <= len(got) <= w.hi):
            probs.append(f"{tag} discarded {len(got)} [{lbl}] (want {w.lo}" +
                         (f"..{w.hi}" if w.hi != w.lo else '') + f"{' ' + w.note if w.note else ''})")
        elif w.exact and ids != w.pool:
            probs.append(f"{tag} discarded [{lbl}] (want exactly {len(w.pool)})")
    return probs


def judge_prompts(b, pool=None, minimum=None, chooser=None, only_discard=True):
    """Checks every card prompt that looks like a discard pick."""
    probs = []
    names = label_cards(b)
    for kind, pid, prompt, cards, count, mn in b.t.discard_calls():
        if only_discard and 'discard' not in (prompt or '').lower() and kind != 'units':
            continue
        if pool is not None:
            allowed = {c.entity_id for c in pool}
            bad = [c for c in cards if c.entity_id not in allowed]
            if bad:
                probs.append(f"prompt '{prompt}' offers {', '.join(names.get(c.entity_id, dname(c)) for c in bad)}")
        if minimum is not None and kind == 'cards':
            eff = count if mn is None else mn
            if eff != minimum and not (minimum == 'all' and eff >= len(cards)):
                probs.append(f"prompt '{prompt}' minimum {mn!r} (count {count}), want {minimum}")
        if chooser is not None and pid != chooser:
            probs.append(f"prompt '{prompt}' asked {'P1' if pid == P1 else 'P2'}")
    return probs


def judge_damage(b, want, who='opp'):
    if want is None or has_ability(b.d):
        return []
    got = dealt(b, who)
    return [] if got == want else [f"damage {got} (want {want})"]


def printed(attack):
    return attack.damage or 0


# ================================================================= scenarios ==
def scn(name, **k):
    k['name'] = name
    return k


async def run_scenario(test, d, attack, s):
    b = make_board(test, d, attack, s)
    entry = b.t.attack_offer(b.me, attack.title)
    if entry is None:
        if s.get('offered', True) is False:
            return True, f"{s['name']}: not offered (ok)"
        if has_ability(d) or s.get('skip_if_not_offered'):
            return None, f"{s['name']}: not offered (card has an Ability / printed condition)"
        return None, f"{s['name']}: not offered with cost paid"
    if s.get('offered', True) is False:
        return False, f"{s['name']}: offered but should not be"
    await b.t.do(entry)
    probs = []
    if 'wants' in s:
        w = s['wants'](b) if callable(s['wants']) else s['wants']
        probs += judge_discards(b, w)
    if 'check' in s:
        probs += s['check'](b) or []
    if probs:
        return False, f"{s['name']}: " + '; '.join(probs)
    return True, f"{s['name']}: ok"


async def run_all(test, d, attack, scenarios):
    probs, notes, skipped = [], [], []
    for s in scenarios:
        try:
            ok, detail = await run_scenario(test, d, attack, s)
        except Exception as ex:
            import traceback
            ok, detail = False, f"{s['name']}: ERROR {type(ex).__name__}: {ex} " + \
                traceback.format_exc().splitlines()[-3][:200]
        if ok is None:
            skipped.append(detail)
        elif ok:
            notes.append(detail)
        else:
            probs.append(detail)
    if probs:
        return False, '; '.join(probs)
    if skipped and not notes:
        return None, '; '.join(skipped)
    return True, '; '.join(notes + skipped)


# ================================================================ tail logic ==
def tail_damage(tail, attack, k, did=None):
    """Expected damage to the opponent's Active given k discarded cards (None = not judged)."""
    did = (k > 0) if did is None else did
    base = printed(attack)
    m = re.search(r"this attack does (\d+) more damage for each (?:card|energy|energy card|\w+ energy)"
                  r"(?: card)? (?:you )?discarded", tail)
    if m:
        return base + int(m.group(1)) * k
    m = re.search(r"this attack does (\d+) damage (?:for each (?:card|energy card|energy|\w+ energy card)"
                  r" (?:you )?discarded|times the (?:number|amount) of (?:\w+ )?energy(?: cards)? you discarded)", tail)
    if m:
        return int(m.group(1)) * k
    m = re.search(r"if you do, this attack does (\d+) more damage", tail) or \
        re.search(r"and have this attack do (\d+) more damage", tail)
    if m:
        return base + (int(m.group(1)) if did else 0)
    if 'damage' in tail and ('for each' in tail or 'times' in tail or 'more damage' in tail):
        return None
    if re.search(r"this attack (?:also )?does \d+ damage to (?:1|2|3|each)", tail) or \
            'damage counters' in tail or 'damage to it' in tail or 'shuffles' in tail or 'knocked out' in tail:
        return None
    return base


def harmless_tail(tail):
    """A tail sentence that moves no card to a discard pile."""
    return not re.search(r"\bdiscards?\b(?! pile)", tail) and 'lost zone' not in tail


# ====================================================== family: self Energy ==
SELF_RX = re.compile(
    r"^(?P<pre>you may |flip a coin\. if tails, |before doing damage, |flip (?P<tc>\d) coins\. for each tails, "
    r"|heal 100 damage from each of your benched pokémon\. then, |heal all damage from 1 of your pokémon\. then, "
    r"|if the total of both players' remaining prize cards is 6 or less, "
    r"|if your opponent's active pokémon is an ultra beast, this attack does 100 more damage, and )?"
    r"discard (?P<n>an|a|1|\d+|all|up to \d+) "
    r"(?P<basic>basic |special )?(?:(?P<type>" + TYPE_RX + r") )?energy (?:cards? )?(?:attached to|from) this pokémon"
    r"(?P<tail>.*)$")
SELF_MULTI_RX = re.compile(
    r"^(?P<pre>you may |flip a coin\. if tails, )?discard (?P<list>(?:(?:a|an|1) " + TYPE_RX +
    r" energy(?:, | and |, and ))+(?:a|an|1) " + TYPE_RX + r" energy) (?:attached to|from) this pokémon(?P<tail>.*)$")


def self_energy_plans(text, d, a):
    m = SELF_RX.match(text)
    multi = None
    if not m:
        m = SELF_MULTI_RX.match(text)
        if not m:
            return None
        multi = re.findall(TYPE_RX, m.group('list'))
    pre, tail = m.group('pre') or '', m.group('tail')
    n_s = m.groupdict().get('n') or ''
    upto = n_s.startswith('up to')
    n = None if n_s == 'all' else (len(multi) if multi else num(n_s.split()[-1]))
    kind = TYPES.get(m.groupdict().get('type') or '') if not multi else None
    basic_only = (m.groupdict().get('basic') or '').strip() == 'basic'
    special_only = (m.groupdict().get('basic') or '').strip() == 'special'
    tails_coins = int(m.group('tc')) if m.groupdict().get('tc') else 0
    if not harmless_tail(tail) and not re.fullmatch(
            r"\. (?:if you do|then), discard an energy (?:attached to|from) (?:your opponent's active|the defending) pokémon\.", tail) \
            and not re.fullmatch(r"\. then, discard a card from the top of your opponent's deck for each energy "
                                 r"you discarded in this way\.", tail):
        return None

    def setup(b):
        t = b.t
        if multi:
            for nm in multi:
                t.energy(b.me, TYPES[nm], 1)
            b.c['me_off'] = t.energy(b.me, off_type(*[TYPES[x] for x in multi]))
            return
        want_total = (n or 2) + 1
        if kind is not None:
            have = sum(1 for e in t.board.attached_energies(b.me) if energy_type(t.test, e) == kind)
            t.energy(b.me, kind, max(1, want_total - have))
            b.c['me_off'] = t.energy(b.me, off_type(kind, b.own))
        else:
            have = len(t.board.attached_energies(b.me))
            b.c['me_off'] = t.energy(b.me, off_type(b.own))
            for _ in range(max(0, want_total - have - 1)):
                t.energy(b.me, off_type(b.own))
        if n is None or basic_only or special_only:
            b.c['me_special'] = t.attach(wg_energy(), b.me)
        if pre.startswith('if the total'):
            if b.s.get('cond', True):
                t.set_prizes(P1, 3)
                t.set_prizes(P2, 3)
        if pre.startswith('heal'):
            b.me.set_attribute(AttrID.HP, BIG - 30)

    def matching(b):
        out = []
        for e in b.me_energy0:
            et = energy_type(b.t.test, e)
            if basic_only and et is None:
                continue
            if special_only and et is not None:
                continue
            if multi and (et is None or et.name.lower() not in multi):
                continue
            if kind is not None and et != kind:
                continue
            out.append(e)
        return out

    def expect(do_it, pick='max'):
        def wants(b):
            pool = matching(b)
            if not do_it:
                w1 = NONE()
            elif n is None:
                w1 = EXACT(pool, 'all matching')
            elif upto:
                w1 = POOL(pool, 0 if pick == 'min' else n, n)
            else:
                w1 = POOL(pool, n)
            k_hi = w1.hi
            w = {P1: w1}
            if re.search(r"discard an energy (?:attached to|from) (?:your opponent's active|the defending)", tail):
                w[P2] = POOL(b.opp_energy0, 1) if do_it else NONE()
            if 'top of your opponent\'s deck' in tail:
                k = len(new_discards(b, P1))
                w[P2] = EXACT(b.deck0[P2][::-1][:k], 'top cards')
            return w

        def check(b):
            probs = []
            pool = matching(b)
            probs += judge_prompts(b, pool=pool + (b.opp_energy0 if 'discard' in tail else []))
            k = len(new_discards(b, P1))
            if multi and do_it:
                got = sorted(energy_type(b.t.test, c).name.lower() for c in new_discards(b, P1)
                             if energy_type(b.t.test, c))
                if got != sorted(multi):
                    probs.append(f"discarded types {got}, want {sorted(multi)}")
            dmg = tail_damage(tail, a, k, did=do_it and k > 0)
            probs += judge_damage(b, dmg)
            return probs
        return wants, check

    out = []
    if tails_coins:
        for name_, hv, k in (('all heads', True, 0), ('all tails', False, tails_coins),
                             ('T then H', seq([False] + [True] * (tails_coins - 1)), 1)):
            def w_k(b, k=k):
                return {P1: POOL(matching(b), (n or 1) * k)}
            out.append(scn(name_, heads=hv, setup=setup, wants=w_k,
                           check=lambda b: judge_prompts(b, pool=matching(b))))
        return out
    if pre.startswith('if the total') or pre.startswith('if your opponent\'s active pokémon is an ultra'):
        w, c = expect(True)
        if pre.startswith('if the total'):
            out.append(scn('6 or less', setup=setup, wants=w, check=c, cond=True))
        w, c = expect(False)
        out.append(scn('condition false', setup=setup, wants=w, cond=False,
                       check=lambda b: judge_damage(b, printed(a))))
        return out
    if pre == 'you may ':
        for yes in (True, False):
            w, c = expect(yes)
            out.append(scn('yes' if yes else 'declined', yes=yes, setup=setup, wants=w, check=c))
    elif pre.startswith('flip'):
        for heads in (True, False):
            w, c = expect(not heads)
            out.append(scn('heads' if heads else 'tails', heads=heads, setup=setup, wants=w, check=c))
    elif upto:
        for pick in ('max', 'min'):
            w, c = expect(True, pick)
            out.append(scn('pick ' + pick, pick=pick, setup=setup, wants=w, check=c))
    else:
        w, c = expect(True)
        out.append(scn('discard', setup=setup, wants=w, check=c))
    return out


# ================================================== family: opponent's Energy ==
def seq(values):
    it = iter(values)
    return lambda title='': next(it, False)


OPP_E_PRE = (r"(?P<pre>flip a coin\. if heads, |flip (?P<coins>\d) coins\. for each heads, "
             r"|flip a coin until you get tails\. for each heads, |flip 2 coins\. if both of them are heads, "
             r"|the defending pokémon is now poisoned\. flip a coin\. if heads, "
             r"|flip a coin\. if heads, (?:the defending pokémon|your opponent's active pokémon) is now paralyzed,? and "
             r"|flip a coin\. if heads, this attack does (?P<hbonus>\d+) more damage and "
             r"|flip a coin\. if heads, this attack does (?P<tbonus>\d+) more damage\. if tails, "
             r"|flip a coin\. if heads, the defending pokémon is now confused\. if tails, "
             r"|if your opponent's active pokémon is affected by a special condition, "
             r"|if your opponent's active pokémon is a pokémon-ex, "
             r"|if your opponent has only 1 prize card left, this attack does (?P<pbonus>\d+) more damage and "
             r"|you can use this attack only if you go second, and only on your first turn\. )?")
OPP_E_RX = re.compile(
    r"^" + OPP_E_PRE + r"discard (?P<n>an|a|2|all|up to 3) (?P<special>special )?(?:(?P<type>" + TYPE_RX +
    r") )?energy (?:cards? )?(?:attached to|from) (?P<who>the defending pokémon|your opponent's active pokémon ex|"
    r"your opponent's active pokémon|that pokémon|1 of your opponent's pokémon|your opponent's pokémon|"
    r"each of your opponent's pokémon|all of your opponent's pokémon)(?P<tail>.*)$")


def opp_energy_plans(text, d, a):
    m = OPP_E_RX.match(text)
    if not m:
        return None
    pre, tail, who = m.group('pre') or '', m.group('tail'), m.group('who')
    if tail not in ('.', '. if both of them are tails, this attack does nothing.',
                    '. if tails, this attack does nothing.') and not tail.startswith('. if you do, prevent'):
        return None
    n_s = m.group('n')
    n = None if n_s == 'all' else 3 if n_s == 'up to 3' else num(n_s)
    upto = n_s == 'up to 3'
    special = bool(m.group('special'))
    kind = TYPES.get(m.group('type') or '')
    every = who in ('each of your opponent\'s pokémon', 'all of your opponent\'s pokémon',
                    'your opponent\'s pokémon')
    one_of = who == '1 of your opponent\'s pokémon'
    ex_only = who.endswith(' ex') or 'pokémon-ex' in pre

    def setup(b, cond=False):
        if kind is not None:
            b.c['opp_extra'] = b.t.energy(b.opp, kind)
        if cond:
            b.opp.set_attribute(AttrID.SPECIAL_CONDITIONS, ['Poisoned'])

    def matching(b, pokemon):
        out = []
        for e in (b.opp_energy0 if pokemon is b.opp else b.opp_bench_energy0):
            et = energy_type(b.t.test, e)
            if special and et is not None:
                continue
            if kind is not None and et != kind:
                continue
            out.append(e)
        return out

    def pool_of(b):
        if every or one_of:
            return matching(b, b.opp) + matching(b, b.opp_bench)
        return matching(b, b.opp)

    def plan(name, times, **k):
        def wants(b):
            pool = pool_of(b)
            if times == 0 or ex_only:
                return {P2: NONE()}
            if n is None and every:
                return {P2: EXACT(pool, 'all matching on every Pokémon')}
            if n is None:
                return {P2: EXACT(pool, 'all matching')}
            if upto:
                return {P2: POOL(pool, 0 if k.get('pick') == 'min' else n, n)}
            return {P2: POOL(pool, n * times)}

        def check(b):
            probs = judge_prompts(b, pool=pool_of(b), chooser=P1)
            if one_of:
                got = new_discards(b, P2)
                if got and not any(c in (b.c['opp_bench_e'], b.c['opp_bench_special']) for c in got) \
                        and b.t.calls and any(cl[0] == 'pokemon' for cl in b.t.calls):
                    probs.append('picked the Benched Pokémon but discarded from elsewhere')
            if 'this attack does nothing' in tail and times == 0:
                probs += judge_damage(b, 0)
            return probs
        s = scn(name, wants=wants, check=check, **k)
        s.setdefault('setup', setup)
        return s

    out = []
    if one_of:
        pick_bench = lambda cands, prompt: next((c for c in cands if c.entity_id == cands[-1].entity_id), cands[0])
        out.append(plan('bench target', 1, pokemon=lambda c, p: c[-1], skip_if_not_offered=True))
        return out
    if pre.startswith('you can use this attack only'):
        return None
    if pre.startswith('if your opponent\'s active pokémon is affected'):
        out.append(plan('poisoned', 1, setup=lambda b: setup(b, True)))
        out.append(plan('no condition', 0))
        return out
    if pre.startswith('if your opponent\'s active pokémon is a pokémon-ex') or ex_only:
        out.append(plan('not an ex', 0))
        return out
    if pre.startswith('if your opponent has only 1 prize'):
        def one_prize(b):
            setup(b)
            b.t.set_prizes(P2, 1)
        out.append(plan('1 prize', 1, setup=one_prize))
        out.append(plan('6 prizes', 0))
        return out
    if m.group('coins'):
        c = int(m.group('coins'))
        out.append(plan('all heads', c, heads=True))
        out.append(plan('all tails', 0, heads=False))
        if c >= 2:
            out.append(plan('H then T', 1, heads=seq([True] + [False] * (c - 1))))
        return out
    if pre.startswith('flip a coin until'):
        out.append(plan('H H T', 2, heads=seq([True, True, False])))
        out.append(plan('T', 0, heads=False))
        return out
    if pre.startswith('flip 2 coins. if both'):
        out.append(plan('H H', 1, heads=True))
        out.append(plan('H T', 0, heads=seq([True, False])))
        return out
    if 'if tails, ' in pre and pre.endswith('if tails, '):
        out.append(plan('heads', 0, heads=True))
        out.append(plan('tails', 1, heads=False))
        return out
    if pre:
        out.append(plan('heads', 1, heads=True))
        out.append(plan('tails', 0, heads=False))
        return out
    if upto:
        out.append(plan('pick max', 1, pick='max'))
        out.append(plan('pick min', 1, pick='min'))
        return out
    if tail.startswith('. if tails'):
        out.append(plan('heads', 1, heads=True))
        out.append(plan('tails', 0, heads=False))
        return out
    out.append(plan('discard', 1))
    return out


# ======================================================== family: Pokémon Tools ==
TOOL_RX = re.compile(
    r"^(?P<pre>before doing damage, (?:you may )?|you may |your opponent's active pokémon is now poisoned\. )?"
    r"discard (?P<n>a|all|up to 2|any number of) pokémon tools?(?: cards?)?(?P<spec> and special energy)? "
    r"(?:attached to|from) (?P<who>this pokémon|your pokémon|the defending pokémon|your opponent's active pokémon|"
    r"that pokémon|1 of your opponent's pokémon|each of your opponent's pokémon|all of your opponent's pokémon|"
    r"your opponent's pokémon)(?P<tail>.*)$")


def tool_plans(text, d, a):
    m = TOOL_RX.match(text)
    if not m:
        return None
    pre, n_s, who, tail = m.group('pre') or '', m.group('n'), m.group('who'), m.group('tail')
    spec = bool(m.group('spec'))
    may = 'you may' in pre
    known_tails = ('.', '. if you can\'t discard any, this attack does nothing.')
    if tail not in known_tails and not tail.startswith('. if you discarded a pokémon tool') and \
            not tail.startswith('. if you do, this attack does') and \
            not re.fullmatch(r"\. this attack does \d+ more damage for each card you discarded in this way\.", tail):
        return None

    def pools(b):
        c = b.c
        if who == 'this pokémon':
            return P1, [c['my_tool']]
        if who == 'your pokémon':
            return P1, [c['my_tool'], c['my_bench_tool']]
        if who in ('the defending pokémon', "your opponent's active pokémon", 'that pokémon'):
            return P2, [c['opp_tool']] + ([c['opp_special']] if spec else [])
        return P2, [c['opp_tool'], c['opp_bench_tool']] + ([c['opp_special'], c['opp_bench_special']] if spec else [])

    def strip_tools(b):
        pid, pool = pools(b)
        for card in pool:
            if card.parent is not None and 'Float Stone' in dname(card):
                card.parent.remove_child(card)

    def hurt(b):
        b.me.set_attribute(AttrID.HP, BIG - 50)

    def plan(name, act=True, pick='max', no_tools=False, **k):
        def setup(b):
            if no_tools:
                strip_tools(b)
            if 'heal all damage' in tail:
                hurt(b)

        def wants(b):
            pid, pool = pools(b)
            pool = [x for x in pool if x.parent is not None] if no_tools else pool
            if no_tools:
                pool = [x for x in pool if 'Float Stone' not in dname(x)]
            if not act:
                return {pid: NONE()}
            if n_s == 'all':
                return {pid: EXACT(pool)}
            if n_s == 'a':
                return {pid: POOL(pool, 1)}
            hi = 2 if n_s == 'up to 2' else len(pool)
            return {pid: POOL(pool, hi if pick == 'max' else 0, hi)}

        def check(b):
            pid, pool = pools(b)
            probs = judge_prompts(b, pool=pool, chooser=P1)
            k_ = len(new_discards(b, pid))
            tools_k = sum(1 for x in new_discards(b, pid) if 'Float Stone' in dname(x))
            base = printed(a)
            mm = re.search(r"this attack does (\d+) more damage", tail)
            if 'this attack does nothing' in tail:
                probs += judge_damage(b, base if tools_k else 0)
            elif 'for each card' in tail and mm:
                probs += judge_damage(b, base + int(mm.group(1)) * k_)
            elif mm:
                probs += judge_damage(b, base + (int(mm.group(1)) if tools_k else 0))
            if 'paralyzed' in tail:
                par = 'Paralyzed' in b.t.conditions(b.opp)
                if par != bool(tools_k):
                    probs.append(f"paralyzed {par} after discarding {tools_k} tool(s)")
            if 'heal all damage' in tail:
                healed = b.t.hp(b.me) >= BIG
                if healed != bool(tools_k):
                    probs.append(f"healed {healed} after discarding {tools_k} tool(s)")
            if 'poisoned' in pre and 'Poisoned' not in b.t.conditions(b.opp):
                probs.append('not poisoned')
            return probs
        return scn(name, setup=setup, wants=wants, check=check, pick=pick, **k)

    out = []
    if may:
        if n_s == 'any number of':
            out += [plan('pick max', pick='max'), plan('pick none', pick='min')]
        else:
            out += [plan('yes', yes=True), plan('declined', act=False, yes=False)]
    elif n_s == 'up to 2':
        out += [plan('pick max', pick='max'), plan('pick none', pick='min')]
    elif who == '1 of your opponent\'s pokémon':
        out += [plan('bench target', pokemon=lambda c, p: c[-1])]
    else:
        out += [plan('with tool')]
    if not may or n_s != 'any number of':
        out.append(plan('no tool', no_tools=True, act=True))
    return out


# ============================================================ family: Stadium ==
STADIUM_RX = [
    re.compile(r"^(?P<may>you may )?discard (?:a|any) stadium(?: card)? in play(?P<tail>\.|\. if you can't, this attack "
               r"does nothing\.|\. if you do, this attack does (?P<bonus>\d+) more damage\.)$"),
    re.compile(r"^if your opponent has a stadium(?: card)? in play, discard it(?P<opp>)(?P<tail>\.|\. .*)$"),
    re.compile(r"^if (?:a stadium is|there is any stadium card) in play, this attack does (?P<bonus>\d+) more damage\. "
               r"(?:then, )?discard (?:that|the) stadium(?: card)?(?P<tail>\.)$"),
    re.compile(r"^if a stadium is in play, this attack also does 30 damage to each of your opponent's benched pokémon, "
               r"and discard that stadium(?P<tail>\. \(don't apply weakness and resistance for benched pokémon\.\))$"),
]


def stadium_plans(text, d, a):
    for rx in STADIUM_RX:
        m = rx.match(text)
        if m:
            break
    else:
        return None
    g = m.groupdict()
    opp_only = g.get('opp') is not None
    may = bool(g.get('may'))
    tail = g.get('tail') or ''
    bonus = int(g['bonus']) if g.get('bonus') else 0
    extra_energy = 'discard 2 energy from your opponent\'s active' in tail
    if opp_only and tail not in ('.',) and not re.match(
            r"\. if (?:you do|you discarded a stadium in this way), ", tail):
        return None

    def plan(name, owner, act=True, **k):
        def setup(b):
            b.st = b.t.stadium(CARD_DEFS_BY_GUID[COURT], owner) if owner else None

        def wants(b):
            discarded = act and owner is not None and not (opp_only and owner == P1)
            w = {P1: NONE(), P2: NONE()}
            if discarded:
                w[owner] = EXACT([b.st])
            if extra_energy and discarded:
                w[P2] = Want([b.st] + b.opp_energy0, 3, 3)
            return w

        def check(b):
            probs = []
            discarded = act and owner is not None and not (opp_only and owner == P1)
            if owner is not None:
                in_play = b.st in b.t.board.find_global_area('activeStadium').children
                if in_play == discarded:
                    probs.append(f"stadium in play: {in_play}")
            base = printed(a)
            if 'this attack does nothing' in tail:
                probs += judge_damage(b, base if owner else 0)
            elif bonus:
                had = owner is not None and not (opp_only and owner == P1)
                probs += judge_damage(b, base + (bonus if (had and act) else 0))
            if 'paralyzed' in tail:
                par = 'Paralyzed' in b.t.conditions(b.opp)
                if par != discarded:
                    probs.append(f"paralyzed {par} (stadium discarded {discarded})")
            return probs
        return scn(name, setup=setup, wants=wants, check=check, **k)

    out = [plan('opp stadium', P2), plan('my stadium', P1), plan('no stadium', None)]
    if may:
        out.append(plan('declined', P2, act=False, yes=False))
    return out


# ======================================================= family: your hand ==
_SPECS = {}


def spec_def(key):
    """Extra card definitions used to stock hands for kind-specific discards."""
    if key in _SPECS:
        return _SPECS[key]
    if key == 'ball':
        d = find_def('Quick Ball', ItemCardDef)
    elif key == 'plasma':
        d = find_def('Team Plasma Ball', ItemCardDef)
    elif key == 'fossil':
        d = find_def('Unidentified Fossil')
    elif key == 'exeggcute':
        d = find_def('Exeggcute', PokemonCardDef, 'CZ')
    elif key == 'rocket':
        d = find_def("Team Rocket's Archer", SupporterCardDef)
    elif key == 'retreat4':
        d = next(x for x in sorted(CARD_DEFS_BY_GUID.values(), key=lambda x: (x.set_code, str(x.collector_number)))
                 if isinstance(x, PokemonCardDef) and def_attr(x, AttrID.RETREAT_COST) == 4
                 and glc.is_glc_legal(x) and not has_ability(x))
    else:
        raise KeyError(key)
    _SPECS[key] = d
    return d


def is_basic_energy_def(dd):
    return isinstance(dd, EnergyCardDef) and 'basic' in (dd.display_name or '').lower() or \
        isinstance(dd, EnergyCardDef) and any(dd.guid.lower() == g.lower() for g in _ENERGY_GUIDS)


_ENERGY_GUIDS = []


def kind_rule(kind):
    """kind phrase -> (predicate(card_def, test) , extra hand stock list of (spec_fn, count))."""
    k = kind.strip()
    k = re.sub(r"\s+cards?$", "", k)
    k = k.replace('[ [fire] ]', 'fire')
    def etype(dd, test):
        for v, g in test.energies.items():
            if g.lower() == dd.guid.lower():
                return PokemonTypes(v)
        return None
    m = re.fullmatch(r"(basic )?(" + TYPE_RX + r" )?energy", k)
    if m:
        t_ = TYPES.get((m.group(2) or '').strip())
        def pred(dd, test, t_=t_, basic_only=bool(m.group(1))):
            if not isinstance(dd, EnergyCardDef):
                return False
            et = etype(dd, test)
            if basic_only and et is None:
                return False
            return t_ is None or et == t_
        extra = [(lambda test, t_=t_: basic(test, t_), 'n')] if t_ not in (None, PokemonTypes.FIRE, PokemonTypes.WATER) else []
        return pred, extra
    if k in ('card', 'cards'):
        return (lambda dd, test: True), []
    if k == 'pokémon tool':
        return (lambda dd, test: isinstance(dd, PokemonToolCardDef)), []
    if k == 'supporter':
        return (lambda dd, test: isinstance(dd, SupporterCardDef)), []
    if k == 'item':      # owner ruling Oct 12: Tools are never Item cards
        return (lambda dd, test: ITEM_STRICT(dd)), []
    if k == 'trainer':
        return (lambda dd, test: isinstance(dd, (ItemCardDef, PokemonToolCardDef, SupporterCardDef, StadiumCardDef))), []
    if k == 'pokémon':
        return (lambda dd, test: isinstance(dd, PokemonCardDef)), []
    if k == 'exeggcute':
        return (lambda dd, test: dd.display_name == 'Exeggcute'), [(lambda test: spec_def('exeggcute'), 2)]
    if k == 'item cards that have the word "ball" in their name' or k == 'item that have the word "ball" in their name':
        return (lambda dd, test: isinstance(dd, ItemCardDef) and 'ball' in (dd.display_name or '').lower()), \
            [(lambda test: spec_def('ball'), 2)]
    if k == 'team plasma':
        return (lambda dd, test: 'team plasma' in (dd.display_name or '').lower()
                or 'Team Plasma' in (getattr(dd, 'subtypes', None) or [])), [(lambda test: spec_def('plasma'), 1)]
    if k in ('item card that has fossil in its name', 'item that has fossil in its name'):
        return (lambda dd, test: 'fossil' in (dd.display_name or '').lower()), [(lambda test: spec_def('fossil'), 1)]
    if k == 'unidentified fossil':
        return (lambda dd, test: dd.display_name == 'Unidentified Fossil'), [(lambda test: spec_def('fossil'), 1)]
    if k == 'pokémon with a retreat cost of exactly 4':
        return (lambda dd, test: isinstance(dd, PokemonCardDef) and def_attr(dd, AttrID.RETREAT_COST) == 4), \
            [(lambda test: spec_def('retreat4'), 2)]
    if k == 'supporter cards that have "team rocket" in their name' or k == 'supporter that have "team rocket" in their name':
        return (lambda dd, test: isinstance(dd, SupporterCardDef) and 'team rocket' in (dd.display_name or '').lower()), \
            [(lambda test: spec_def('rocket'), 2)]
    return None


HAND_RX = re.compile(
    r"^(?P<may>you may )?discard (?P<q>a|an|\d+|up to \d+|any number of|as many) (?P<kind>.+?) "
    r"(?:as you like )?from your hand(?P<tail>.*)$")
HAND_TAILS = [
    (r"\. if you can't(?: discard (?:a card|\d+ cards)(?: in this way)?)?, this attack does nothing\.|"
     r"\. if you don't, this attack does nothing\.", 'cost'),
    (r", and knock out your opponent's active pokémon\. if you can't discard (\d+) cards in this way, this attack does nothing\.", 'cost_ko'),
    (r"\. if you do, draw (\d+) cards\.", 'draw'),
    (r"\. if you do, your opponent discards a card from their hand\.", 'opp_discard'),
    (r"\. if you do, use the effect of that card as the effect of this attack\.", 'copy'),
    (r"\. if you do, this attack does 60 damage to 1 of your opponent's pokémon\. this damage isn't affected by weakness or resistance\.", 'snipe'),
    (r"[.,] (?:and )?this attack does (\d+) (?:more )?damage for each card you discarded in this way\.", 'per'),
    (r"\. then, draw cards until you have (\d+) cards in your hand\.", 'draw_until'),
    (r"(?: until you have 4 or fewer)?\. draw cards until you have (\d+) cards in your hand\.", 'draw_until'),
    (r"\. this attack does (\d+) damage times the number of (?:energy cards|pokémon|cards) you discarded\.", 'per'),
    (r"\. heal (\d+) damage from this pokémon for each card you discarded in this way\.", 'heal_per'),
    (r"\. this attack does (\d+) damage for each type of basic energy you discarded in this way\.", 'per_type'),
    (r"\. if you do, this attack does (\d+) more damage\.", 'bonus'),
    (r"\. this attack does (\d+) more damage for each card you discarded in this way\.", 'per'),
    (r"\.", 'none'),
]


def hand_plans(text, d, a):
    mh = re.fullmatch(r"(?:if you go first, you can use this attack during your first turn\. )?discard your hand"
                      r"(?P<tail>\.| and draw (\d+) cards\.|\. if you discarded 5 or more cards in this way, this attack "
                      r"does 150 more damage\.)", text)
    if mh:
        draw = int(mh.group(2)) if mh.group(2) else 0

        def hand_n(k):
            def setup(b):
                for c in b.t.zone(P1, 'hand')[k:]:
                    c.parent.remove_child(c)
            return setup

        def wants(b):
            return {P1: EXACT(b.hand0[P1], 'whole hand')}

        def check(b):
            probs = []
            if draw and len(b.t.zone(P1, 'hand')) != draw:
                probs.append(f"hand {len(b.t.zone(P1, 'hand'))} (want {draw})")
            if '150 more' in text:
                probs += judge_damage(b, printed(a) + (150 if len(b.hand0[P1]) >= 5 else 0))
            return probs
        out = [scn('hand 6', wants=wants, check=check)]
        if '150 more' in text:
            out.append(scn('hand 4', wants=wants, check=check, setup=hand_n(4)))
            out.append(scn('hand 5', wants=wants, check=check, setup=hand_n(5)))
        return out
    m = HAND_RX.match(text)
    if not m:
        return None
    may, q, kind, tail = bool(m.group('may')), m.group('q'), m.group('kind'), m.group('tail')
    kind = re.sub(r"^(?:cards?|energy cards?)$", lambda x: x.group(0), kind)
    rule = kind_rule(kind)
    if rule is None:
        return None
    pred, extra = rule
    for rx, tk in HAND_TAILS:
        tm = re.fullmatch(rx, tail)
        if tm:
            break
    else:
        return None
    tval = int(tm.group(1)) if tm.groups() and tm.group(1) else None
    if q in ('a', 'an'):
        n, flexible = 1, False
    elif q.isdigit():
        n, flexible = int(q), False
    elif q.startswith('up to'):
        n, flexible = int(q.split()[-1]), True
    else:
        n, flexible = None, True        # any number / as many
    per_card = 'per' in tk or tk == 'heal_per'

    def setup_for(have):
        def setup(b):
            t = b.t
            for fn, cnt in extra:
                c_ = (n + 1 if n else 2) if cnt == 'n' else cnt
                for _ in range(c_):
                    t.put(fn(t.test), P1, 'hand')
            if tk in ('cost', 'cost_ko') and n and n > 1:
                # cost needs n matching cards: top up
                cur = [c for c in t.zone(P1, 'hand') if pred(def_for(c.archetype_id), t.test)]
                spec = def_for(cur[0].archetype_id) if cur else None
                for _ in range(max(0, n + 1 - len(cur))):
                    if spec is not None:
                        t.put(spec, P1, 'hand')
            if have is not None:
                cur = [c for c in t.zone(P1, 'hand') if pred(def_for(c.archetype_id), t.test)]
                for c in cur[have:]:
                    c.parent.remove_child(c)
            if tk == 'heal_per':
                b.me.set_attribute(AttrID.HP, BIG - 200)
        return setup

    def matching(b):
        return [c for c in b.hand0[P1] if pred(def_for(c.archetype_id), b.t.test)]

    def plan(name, act=True, pick='max', have=None, **k):
        def wants(b):
            pool = matching(b)
            w = {}
            if not act:
                w[P1] = NONE()
            elif tk in ('cost', 'cost_ko') and len(pool) < (n or 1):
                w[P1] = POOL(pool, 0, len(pool), 'cost not payable')
            elif n is None:
                w[P1] = POOL(pool, len(pool) if pick == 'max' else 0, len(pool))
            elif flexible:
                w[P1] = POOL(pool, n if pick == 'max' else 0, n)
            else:
                w[P1] = POOL(pool, n)
            if tk == 'opp_discard':
                w[P2] = POOL(b.hand0[P2], 1) if act and pool else NONE()
            if tk == 'cost_ko' and act and len(pool) >= n:
                w[P2] = Want(list(b.t.zone(P2, 'discard')), 0, 99)
            return w

        def check(b):
            pool = matching(b)
            probs = judge_prompts(b, pool=pool + (b.hand0[P2] if tk == 'opp_discard' else []),
                                  minimum=(0 if flexible and pick == 'min' else None))
            mine = [c for c in new_discards(b, P1) if c in b.hand0[P1]]
            kk = len(mine)
            base = printed(a)
            if tk in ('cost', 'cost_ko'):
                paid = len(pool) >= (n or 1) and act
                if tk == 'cost':
                    probs += judge_damage(b, base if paid else 0)
                else:
                    ko = b.opp not in b.t.board.pokemon_in_play(P2)
                    if ko != paid:
                        probs.append(f"opponent's Active knocked out: {ko} (cost paid {paid})")
            elif tk == 'draw':
                hand = len(b.t.zone(P1, 'hand'))
                want = len(b.hand0[P1]) - kk + (tval if kk else 0)
                if hand != want:
                    probs.append(f"hand {hand} (want {want} after discarding {kk})")
            elif tk == 'draw_until':
                hand = len(b.t.zone(P1, 'hand'))
                if hand != max(tval, len(b.hand0[P1]) - kk):
                    probs.append(f"hand {hand} after discarding {kk} (want {tval})")
            elif tk == 'per':
                more = 'more damage' in tail
                probs += judge_damage(b, (base if more else 0) + tval * kk)
            elif tk == 'per_type':
                types = {energy_type(b.t.test, c) for c in mine} - {None}
                probs += judge_damage(b, tval * len(types))
            elif tk == 'bonus':
                probs += judge_damage(b, base + (tval if kk else 0))
            elif tk == 'heal_per':
                healed = b.t.hp(b.me) - (BIG - 200)
                if healed != tval * kk:
                    probs.append(f"healed {healed} (want {tval * kk})")
            if tk == 'opp_discard':
                if any(cl[1] != P2 for cl in b.t.discard_calls() if any(c in b.hand0[P2] for c in cl[3])):
                    probs.append('opponent hand discard chosen by P1')
            return probs
        return scn(name, setup=setup_for(have), wants=wants, check=check, pick=pick, **k)

    out = []
    if may and not flexible:
        out += [plan('yes', yes=True), plan('declined', act=False, yes=False, pick='min')]
    elif flexible:
        out += [plan('pick max', pick='max'), plan('pick none', pick='min')]
    else:
        out.append(plan('discard'))
    if tk in ('cost', 'cost_ko', 'draw', 'opp_discard', 'copy', 'snipe', 'bonus') and not flexible:
        out.append(plan('none matching' if tk not in ('cost', 'cost_ko') or (n or 1) == 1 else 'too few',
                        have=(0 if (n or 1) == 1 or tk not in ('cost', 'cost_ko') else (n - 1))))
    return out


# =================================================== family: opponent's hand ==
OPP_KIND = {'trainer': lambda dd: isinstance(dd, (ItemCardDef, PokemonToolCardDef, SupporterCardDef, StadiumCardDef)),
            'item': lambda dd: ITEM_STRICT(dd),
            'supporter': lambda dd: isinstance(dd, SupporterCardDef),
            'pokémon': lambda dd: isinstance(dd, PokemonCardDef),
            'card': lambda dd: True,
            'item cards and pokémon tool': lambda dd: isinstance(dd, (ItemCardDef, PokemonToolCardDef))}
ITEM_STRICT = lambda dd: isinstance(dd, ItemCardDef) and not isinstance(dd, PokemonToolCardDef)


def opp_hand_plans(text, d, a):
    plans = []

    def plan(name, lo, hi=None, pred=None, chooser=None, exact_all=False, **k):
        def wants(b):
            pool = [c for c in b.hand0[P2] if pred is None or pred(def_for(c.archetype_id))]
            if exact_all:
                return {P2: EXACT(pool)}
            return {P2: POOL(pool, lo, hi if hi is not None else lo)}

        def check(b):
            pool = [c for c in b.hand0[P2] if pred is None or pred(def_for(c.archetype_id))]
            return judge_prompts(b, pool=pool, chooser=chooser, only_discard=False)
        return scn(name, wants=wants, check=check, **k)

    m = re.fullmatch(r"(?P<pre>flip a coin\. if heads, |flip (?P<c>\d) coins\. for each heads, |flip a coin until you get "
                     r"tails\. for each heads, )?discard a random card from your opponent's hand(?P<tail>\.|\. switch this "
                     r"pokémon with 1 of your benched pokémon\.|\. if this pokémon evolved from \w+ during this turn, discard "
                     r"2 cards instead of 1\.)", text)
    if m:
        pre = m.group('pre') or ''
        if m.group('c'):
            c = int(m.group('c'))
            return [plan('all heads', c, heads=True), plan('all tails', 0, heads=False),
                    plan('H T T', 1, heads=seq([True, False, False]))]
        if pre.startswith('flip a coin until'):
            return [plan('H H T', 2, heads=seq([True, True, False])), plan('T', 0, heads=False)]
        if pre:
            return [plan('heads', 1, heads=True), plan('tails', 0, heads=False)]
        return [plan('not evolved' if 'evolved' in text else 'discard', 1)]
    m = re.fullmatch(r"discard (?:random cards from your opponent's hand until they have|cards from your opponent's hand at "
                     r"random until he or she has) (\d+) cards in (?:their|his or her) hand\.", text)
    if m:
        n = int(m.group(1))
        def few(b):
            for c in b.t.zone(P2, 'hand')[n - 1:]:
                c.parent.remove_child(c)
        return [plan('hand 6', 6 - n), plan(f'hand {n - 1}', 0, setup=few)]
    m = re.fullmatch(r"your opponent discards (a card|2 cards) from " + HIS + r" hand\.(?P<sal> if this pokémon evolved from "
                     r"\w+ during this turn, your opponent discards 2 more cards\.)?", text)
    if m:
        n = 1 if m.group(1) == 'a card' else 2
        def one(b):
            for c in b.t.zone(P2, 'hand')[1:]:
                c.parent.remove_child(c)
        out = [plan('discard', n, chooser=P2)]
        if n == 2:
            out.append(plan('hand 1', 1, chooser=P2, setup=one))
        return out
    m = re.fullmatch(r"your opponent flips 4 coins\. for each tails, he or she discards a card from his or her hand\.", text)
    if m:
        return [plan('all heads', 0, heads=True), plan('all tails', 4, heads=False, chooser=P2)]
    m = re.fullmatch(r"your opponent reveals? " + HIS + r" hand\. discard (a|an|all) (trainer|item|pokémon|item cards and "
                     r"pokémon tool)(?: cards?)? (?:you find there|from it)\.", text)
    if m:
        kind = m.group(2)
        pred = OPP_KIND[kind]
        if m.group(1) == 'all' and kind == 'item':
            def wants_items(b):
                strict = [c for c in b.hand0[P2] if ITEM_STRICT(def_for(c.archetype_id))]
                loose = [c for c in b.hand0[P2] if pred(def_for(c.archetype_id))]
                return {P2: POOL(strict, len(strict), len(strict), 'Items only (Tools stay: ruling)')}
            return [scn('discard all', wants=wants_items)]
        if m.group(1) == 'all':
            return [plan('discard all', 0, pred=pred, exact_all=True, chooser=P1)]
        out = [plan('discard', 1, pred=pred, chooser=P1)]

        def none_of(b, pred=pred):
            for c in list(b.t.zone(P2, 'hand')):
                if pred(def_for(c.archetype_id)):
                    c.parent.remove_child(c)
        out.append(plan('none of that kind', 0, pred=pred, setup=none_of))
        return out
    m = re.fullmatch(r"flip 3 coins\. if any of them are heads, your opponent reveals " + HIS + r" hand\. then, for each heads, "
                     r"discard a (trainer )?card from your opponent's hand\.", text)
    if m:
        pred = OPP_KIND['trainer'] if m.group(1) else None
        return [plan('3 heads', 3, pred=pred, heads=True, chooser=P1),
                plan('H T T', 1, pred=pred, heads=seq([True, False, False]), chooser=P1),
                plan('all tails', 0, heads=False)]
    if text == ("if your opponent has 4 or more cards in their hand, they reveal their hand. discard cards you find there "
                "until your opponent has exactly 4 cards in their hand."):
        def three(b):
            for c in b.t.zone(P2, 'hand')[3:]:
                c.parent.remove_child(c)
        return [plan('hand 6', 2, chooser=P1), plan('hand 3', 0, setup=three)]
    return None


# ======================================================= family: top of deck ==
def deck_specs(test):
    """10 marked cards, topmost first."""
    F, W = basic(test, PokemonTypes.FIRE), basic(test, PokemonTypes.WATER)
    sup, mon, item = CARD_DEFS_BY_GUID[HAU], test.filler, test.item
    return [F, sup, mon, W, F, item, mon, F, W, sup]


def stack_top(t, pid, specs):
    return t.deck(pid, list(reversed(specs)))[::-1]


def tops(b, pid, n):
    return b.deck0[pid][::-1][:n]


def is_energy_def(dd):
    return isinstance(dd, EnergyCardDef)


def kind_count(b, cards, what):
    what = what.strip()
    n = 0
    for c in cards:
        dd = def_for(c.archetype_id)
        if what in ('energy card', 'energy'):
            n += is_energy_def(dd)
        elif what in ('supporter card', 'supporter'):
            n += isinstance(dd, SupporterCardDef)
        elif what in ('pokémon',):
            n += isinstance(dd, PokemonCardDef)
        else:
            m = re.fullmatch(r"(basic )?(" + TYPE_RX + r") energy(?: card)?", what)
            if m:
                n += energy_type(b.t.test, c) == TYPES[m.group(2)]
            else:
                return None
    return n


DECK_RX = re.compile(
    r"^(?P<pre>flip a coin\. if heads, |flip (?P<c>\d) coins\. for each heads, |flip a coin until you get tails\. for each heads, "
    r"|if this pokémon has any damage counters on it, |for each (?P<per_e>" + TYPE_RX + r") energy attached to this pokémon, "
    r"|for each of your (?P<per_n>\w+) in play, |flip a coin for each (?P<coin_n>\w+) you have in play\. for each heads, )?"
    r"(?:discard the top (?:(?P<n>\d+) cards|card) of (?P<whose>your opponent's|your|each player's) deck|discard (?P<n2>\d+) "
    r"cards from the top of your opponent's deck(?P<whose2>))(?P<tail>.*)$")


def deck_plans(text, d, a):
    m = DECK_RX.match(text)
    if m is None:
        m2 = re.fullmatch(r"each player discards the top card of " + HIS + r" deck(?P<tail>\..*)", text)
        if not m2:
            return None
        return deck_builder(text, d, a, pre='', n=1, whose="each player's", tail=m2.group('tail'), m=None)
    n = int(m.group('n') or m.group('n2') or 1)
    whose = m.group('whose') if m.group('whose') is not None else "your opponent's"
    return deck_builder(text, d, a, pre=m.group('pre') or '', n=n, whose=whose, tail=m.group('tail'), m=m)


def deck_builder(text, d, a, pre, n, whose, tail, m):
    pids = {"your opponent's": [P2], 'your': [P1], "each player's": [P1, P2]}[whose]
    dmg = None
    tm = re.fullmatch(r"\.(?:,)? ?this attack does (\d+) (more )?damage (?:for each (.+?) (?:you )?discarded in this way|"
                      r"times the number of (.+?)s?(?: you)? discarded)\.", tail) or \
        re.fullmatch(r", and this attack does (\d+) (more )?damage for each (.+?) you discarded in this way\.", tail) or \
        re.fullmatch(r"\. this attack does (\d+) (more )?damage for each (.+?) discarded in this way\.", tail)
    if tm:
        what = tm.group(3) or tm.group(4)
        dmg = ('per', int(tm.group(1)), bool(tm.group(2)), what)
    elif re.fullmatch(r"\. if that card is an energy card, this attack does (\d+) more damage\.", tail):
        dmg = ('if_energy', int(re.search(r"(\d+) more", tail).group(1)))
    elif tail not in ('.',):
        return None
    if dmg and dmg[0] == 'per' and kind_count(None, [], dmg[3]) is None:
        return None

    def setup_for(extra=None):
        def setup(b):
            for pid in pids:
                stack_top(b.t, pid, deck_specs(b.t.test))
            if extra:
                extra(b)
        return setup

    def plan(name, times, extra=None, **k):
        def wants(b):
            return {pid: EXACT(tops(b, pid, n * times), 'top cards') for pid in pids}

        def check(b):
            probs = []
            if dmg is None or has_ability(b.d):
                return probs
            cards = [c for pid in pids for c in new_discards(b, pid)]
            base = printed(a)
            if dmg[0] == 'per':
                cnt = kind_count(b, cards, dmg[3])
                if cnt is None:
                    return probs
                probs += judge_damage(b, (base if dmg[2] else 0) + dmg[1] * cnt)
            elif dmg[0] == 'if_energy':
                probs += judge_damage(b, base + (dmg[1] if kind_count(b, cards, 'energy') else 0))
            return probs
        return scn(name, setup=setup_for(extra), wants=wants, check=check, **k)

    if m is not None and m.group('c'):
        c = int(m.group('c'))
        return [plan('all heads', c, heads=True), plan('all tails', 0, heads=False),
                plan('H then T', 1, heads=seq([True] + [False] * (c - 1)))]
    if pre.startswith('flip a coin until'):
        return [plan('H H T', 2, heads=seq([True, True, False])), plan('T', 0, heads=False)]
    if pre.startswith('flip a coin. if heads'):
        return [plan('heads', 1, heads=True), plan('tails', 0, heads=False)]
    if pre.startswith('if this pokémon has any damage'):
        return [plan('damaged', 1, extra=lambda b: b.me.set_attribute(AttrID.HP, BIG - 10)), plan('undamaged', 0)]
    if m is not None and m.group('per_e'):
        kind = TYPES[m.group('per_e')]

        def times_e(b):
            return sum(1 for e in b.me_energy0 if energy_type(b.t.test, e) == kind)

        def extra(b):
            b.t.energy(b.me, kind, 1)
            b.t.energy(b.me, off_type(kind, b.own), 1)

        def wants(b):
            return {P2: EXACT(tops(b, P2, times_e(b)), 'one per matching energy')}
        return [scn('count energy', setup=setup_for(extra), wants=wants)]
    if m is not None and m.group('per_n'):
        name_ = m.group('per_n')
        other = next((x for x in CARD_DEFS_BY_GUID.values() if isinstance(x, PokemonCardDef)
                      and (x.display_name or '').lower() == name_ and glc.is_glc_legal(x)), None)
        if other is None:
            return None

        def extra(b):
            neutral(b.t.put(other, P1, 'bench'))
            neutral(b.t.put(other, P2, 'bench'))

        def wants(b):
            mine = sum(1 for p in b.t.board.pokemon_in_play(P1) if dname(p).lower() == name_)
            return {P2: EXACT(tops(b, P2, mine), f'one per own {name_}')}
        return [scn('count', setup=setup_for(extra), wants=wants)]
    if m is not None and m.group('coin_n'):
        name_ = m.group('coin_n')
        other = next((x for x in CARD_DEFS_BY_GUID.values() if isinstance(x, PokemonCardDef)
                      and (x.display_name or '').lower() == name_ and glc.is_glc_legal(x)), None)
        if other is None:
            return None

        def extra(b):
            neutral(b.t.put(other, P1, 'bench'))
            neutral(b.t.put(other, P2, 'bench'))

        def wants(b):
            mine = sum(1 for p in b.t.board.pokemon_in_play(P1) if dname(p).lower() == name_)
            return {P2: EXACT(tops(b, P2, n * mine), f'{n} per own {name_} (all heads)')}
        return [scn('all heads', setup=setup_for(extra), wants=wants, heads=True),
                scn('all tails', setup=setup_for(extra), wants={P2: NONE()}, heads=False)]
    if pre:
        return None
    return [plan('discard', 1)]


# ============================================ family: Energy from your Pokémon ==
MYPK_RX = re.compile(
    r"^(?P<may>you may )?discard (?:(?P<q1>any amount of|up to \d+) (?P<t1>" + TYPE_RX + r" )?energy(?: cards)? from "
    r"(?P<w1>your pokémon|this pokémon)|as many (?P<t2>" + TYPE_RX + r" )?energy attached to your pokémon as you like)"
    r"(?P<tail>.*)$")


def my_pokemon_energy_plans(text, d, a):
    m = MYPK_RX.match(text)
    if not m:
        return None
    q = m.group('q1') or 'any'
    kind = TYPES.get((m.group('t1') or m.group('t2') or '').strip())
    whole = (m.group('w1') or 'your pokémon') == 'your pokémon'
    hi = int(q.split()[-1]) if q.startswith('up to') else None
    tail = m.group('tail')
    tm = re.fullmatch(r"\. this attack does (\d+) (more )?damage (?:for each card you discarded in this way|times the "
                      r"(?:number|amount) of (?:\w+ )?energy(?: cards)? you discarded(?: in this way)?)\.", tail)
    spread = re.fullmatch(r"\. then, for each energy(?: card)? you discarded in this way, choose 1 of your opponent's pokémon "
                          r"and do (\d+) damage to it\..*", tail)
    if not tm and not spread:
        return None

    def setup(b):
        t = b.t
        k = kind or off_type(b.own)
        t.energy(b.me, k, 2)
        b.c['me_off'] = t.energy(b.me, off_type(k, b.own) if kind else k)
        if kind:
            b.c['my_bench_typed'] = t.energy(b.my_bench, kind)
        b.my_bench_energy0 = list(t.board.attached_energies(b.my_bench))

    def pool(b):
        cards = list(b.me_energy0) + (list(b.my_bench_energy0) if whole else [])
        return [e for e in cards if kind is None or energy_type(b.t.test, e) == kind]

    def plan(pick):
        def wants(b):
            p_ = pool(b)
            top = len(p_) if hi is None else min(hi, len(p_))
            return {P1: POOL(p_, top if pick == 'max' else 0, top)}

        def check(b):
            probs = judge_prompts(b, pool=pool(b), minimum=0 if pick == 'min' else None)
            k = len(new_discards(b, P1))
            if tm:
                more = bool(tm.group(2))
                probs += judge_damage(b, (printed(a) if more else 0) + int(tm.group(1)) * k)
            if whole and pick == 'max' and not any(c in b.my_bench_energy0 for c in new_discards(b, P1)):
                probs.append('could not discard Energy from the Bench')
            return probs
        return scn('pick ' + pick, pick=pick, setup=setup, wants=wants, check=check)
    return [plan('max'), plan('min')]


# ================================================= hand-checked outlier texts ==
def stack_of(p):
    out = [p]
    for ch in list(getattr(p, 'children', []) or []):
        out += stack_of(ch)
    return out


def named(name):
    return find_def(name, PokemonCardDef)


def top_setup(pid, specs_fn, extra=None):
    def setup(b):
        stack_top(b.t, pid, specs_fn(b.t.test))
        if extra:
            extra(b)
    return setup


def std_tops(pid, extra=None):
    return top_setup(pid, deck_specs, extra)


def hand_delta(b, pid=P1):
    return len(b.t.zone(pid, 'hand')) - len(b.hand0[pid])


def manual_plans(text, d, a):
    T = text
    F = lambda test: basic(test, PokemonTypes.FIRE)
    W = lambda test: basic(test, PokemonTypes.WATER)
    FG = lambda test: basic(test, PokemonTypes.FIGHTING)

    if T.startswith("at the end of your opponent's next turn, discard the defending pokémon"):
        return [scn('nothing yet', wants={})]
    if T.startswith("during your opponent's next turn, if this pokémon is knocked out") or \
            T.startswith("during your opponent's next turn, whenever they try to use a trainer") or \
            T.startswith("whenever your opponent plays a trainer card from his or her hand during his or her next turn"):
        return [scn('nothing now', wants={})]
    if T.startswith("discard a number of your benched dreepy"):
        def setup(b):
            b.dreepy = [neutral(b.t.put(named('Dreepy'), P1, 'bench')) for _ in range(3)]
        return [scn('pick max', setup=setup, wants=lambda b: {P1: POOL(b.dreepy, 2)}, pick='max'),
                scn('pick none', setup=setup, wants={}, pick='min')]
    if T == ("discard a random card from your opponent's hand, discard the top card of your opponent's deck, and discard "
             "an energy from your opponent's active pokémon."):
        def wants(b):
            return {P2: Want(b.hand0[P2] + tops(b, P2, 1) + b.opp_energy0, 3, 3)}

        def check(b):
            got = new_discards(b, P2)
            parts = (sum(c in b.hand0[P2] for c in got), sum(c in tops(b, P2, 1) for c in got),
                     sum(c in b.opp_energy0 for c in got))
            return [] if parts == (1, 1, 1) else [f"hand/deck/energy split {parts}, want (1, 1, 1)"]
        return [scn('discard', setup=std_tops(P2), wants=wants, check=check)]
    if T == "discard all cards from both active pokémon.":
        return [scn('discard', wants=lambda b: {P1: EXACT(b.stack0['me'][1:]), P2: EXACT(b.stack0['opp'][1:])})]
    if T == "discard all special energy from each pokémon.":
        def setup(b):
            b.c['my_bench_special'] = b.t.attach(wg_energy(), b.my_bench)
        return [scn('discard', setup=setup, wants=lambda b: {
            P1: EXACT([b.c['my_bench_special']]), P2: EXACT([b.c['opp_special'], b.c['opp_bench_special']])})]
    if T.startswith("discard any number of arrokuda from your bench"):
        def setup(b):
            b.arro = [neutral(b.t.put(named('Arrokuda'), P1, 'bench')) for _ in range(2)]
        return [scn('pick max', setup=setup, wants=lambda b: {P1: EXACT(b.arro)},
                    check=lambda b: judge_damage(b, 60 * 2)),
                scn('pick none', setup=setup, pick='min', wants={}, check=lambda b: judge_damage(b, 0))]
    if T.startswith("discard any number of your benched pokémon. this attack does 30 more damage"):
        return [scn('pick max', wants=lambda b: {P1: EXACT(b.stack0['my_bench'])},
                    check=lambda b: judge_damage(b, printed(a) + 30)),
                scn('pick none', pick='min', wants={}, check=lambda b: judge_damage(b, printed(a)))]
    if T == "discard each player's active pokémon and all attached cards. (you choose a new active pokémon first.)":
        return [scn('discard', wants=lambda b: {P1: EXACT(b.stack0['me']), P2: EXACT(b.stack0['opp'])})]
    if T == "discard this pokémon and all cards attached to it.":
        return [scn('discard', wants=lambda b: {P1: EXACT(b.stack0['me'])})]
    if T == "discard the top 3 cards of your deck and put 1 of them into your hand.":
        def check(b):
            got_hand = [c for c in b.t.zone(P1, 'hand') if c in tops(b, P1, 3)]
            return [] if len(got_hand) == 1 else [f"{len(got_hand)} of the top 3 put into hand (want 1)"]
        return [scn('discard', setup=std_tops(P1), wants=lambda b: {P1: POOL(tops(b, P1, 3), 2)}, check=check)]
    if T.startswith("discard the top 3 cards of your deck. for each water energy card"):
        def setup(b):
            stack_top(b.t, P1, [W(b.t.test), CARD_DEFS_BY_GUID[HAU], W(b.t.test)])
            stack_top(b.t, P2, deck_specs(b.t.test))
        return [scn('2 water', setup=setup, wants=lambda b: {P1: EXACT(tops(b, P1, 3)), P2: EXACT(tops(b, P2, 6))})]
    if T.startswith("discard the top 4 cards of your deck. if any of those cards are fire energy cards, attach them"):
        def check(b):
            fires = [c for c in tops(b, P1, 4) if energy_type(b.t.test, c) == PokemonTypes.FIRE]
            bad = [c for c in fires if not isinstance(c.parent, PokemonEntity)]
            return [f"{len(bad)} Fire Energy not attached"] if bad else []
        return [scn('discard', setup=std_tops(P1), check=check, wants=lambda b: {
            P1: EXACT([c for c in tops(b, P1, 4) if energy_type(b.t.test, c) != PokemonTypes.FIRE])})]
    if T.startswith("discard the top 5 cards of your deck. if any of those cards are fighting energy cards, attach them"):
        def specs(test):
            return [FG(test), CARD_DEFS_BY_GUID[HAU], FG(test), test.item, W(test)]

        def check(b):
            fg = [c for c in tops(b, P1, 5) if energy_type(b.t.test, c) == PokemonTypes.FIGHTING]
            return [] if all(c.parent is b.me for c in fg) else ['Fighting Energy not attached to this Pokémon']
        return [scn('discard', setup=top_setup(P1, specs), check=check, wants=lambda b: {
            P1: EXACT([c for c in tops(b, P1, 5) if energy_type(b.t.test, c) != PokemonTypes.FIGHTING])})]
    if T.startswith("discard the top 5 cards of your deck, and then choose 2 of your opponent's benched pokémon"):
        def setup(b):
            stack_top(b.t, P1, deck_specs(b.t.test))
            b.opp_bench2 = neutral(b.t.put(b.t.test.filler, P2, 'bench'))

        def check(b):
            hit = BIG - b.t.hp(b.opp_bench)
            return [] if hit == 150 else [f"benched Pokémon took {hit} (want 150 = 3 Energy)"]
        return [scn('discard', setup=setup, check=check, wants=lambda b: {P1: EXACT(tops(b, P1, 5))},
                    pokemon=lambda c, p: c[0])]
    if T.startswith("discard the top 5 cards of your deck. this attack does 60 more damage for each pokémon"):
        return [scn('discard', setup=std_tops(P1), wants=lambda b: {P1: EXACT(tops(b, P1, 5))},
                    check=lambda b: judge_damage(b, printed(a) + 60), pick='min')]
    if T.startswith("discard the top card of your deck, and if that card is a pokémon that doesn't have a rule box"):
        return [scn('item on top', setup=std_tops(P1, lambda b: stack_top(b.t, P1, [b.t.test.item])),
                    wants=lambda b: {P1: EXACT(tops(b, P1, 1))}, check=lambda b: judge_damage(b, 0))]
    if T.startswith("discard the top card of your deck, and if that card is a supporter card, use the effect"):
        return [scn('item on top', setup=lambda b: stack_top(b.t, P1, [b.t.test.item]),
                    wants=lambda b: {P1: EXACT(tops(b, P1, 1))},
                    check=lambda b: [] if hand_delta(b) == 0 else [f"hand {hand_delta(b):+d}"]),
                scn('Hau on top', setup=lambda b: stack_top(b.t, P1, [CARD_DEFS_BY_GUID[HAU]]),
                    wants=lambda b: {P1: EXACT(tops(b, P1, 1))},
                    check=lambda b: [] if hand_delta(b) == 3 else [f"hand {hand_delta(b):+d} (Hau: draw 3)"])]
    m = re.fullmatch(r"discard the top card of your deck\. if that card is a fighting energy(?: card)?, attach it to this pokémon\.", T)
    if m:
        return [scn('fighting on top', setup=lambda b: stack_top(b.t, P1, [FG(b.t.test)]), wants={},
                    check=lambda b: [] if tops(b, P1, 1)[0].parent is b.me else ['not attached']),
                scn('item on top', setup=lambda b: stack_top(b.t, P1, [b.t.test.item]),
                    wants=lambda b: {P1: EXACT(tops(b, P1, 1))})]
    if T.startswith("discard the top card of your deck. if that card is an energy card, this attack does 100 more damage"):
        return [scn('energy on top', setup=lambda b: stack_top(b.t, P1, [F(b.t.test)]), wants={},
                    check=lambda b: ([] if tops(b, P1, 1)[0].parent is b.me else ['not attached'])
                    + judge_damage(b, printed(a) + 100)),
                scn('item on top', setup=lambda b: stack_top(b.t, P1, [b.t.test.item]),
                    wants=lambda b: {P1: EXACT(tops(b, P1, 1))}, check=lambda b: judge_damage(b, printed(a)))]
    if T.startswith("discard the top card of your opponent's deck. if the card you discarded is a pokémon"):
        def setup(b):
            stack_top(b.t, P2, [b.t.test.filler])
        return [scn('pokémon on top', setup=setup, wants=lambda b: {P2: EXACT(tops(b, P2, 1))},
                    check=lambda b: judge_damage(b, def_attr(b.t.test.filler, AttrID.HP)))]
    if T.startswith("discard the top card of your opponent's deck. if this pokémon has a cursed shovel") or \
            T.startswith("discard the top card of your opponent's deck. if you played"):
        return [scn('condition not met', setup=std_tops(P2), wants=lambda b: {P2: EXACT(tops(b, P2, 1))})]
    if T.startswith("discard up to 6 cards from the top of your deck"):
        def check(b):
            k = len(new_discards(b, P1))
            return judge_damage(b, 30 * k) + ([] if set(new_discards(b, P1)) == set(tops(b, P1, k)) else ['not the top cards'])
        return [scn('discard', setup=std_tops(P1), wants=lambda b: {P1: POOL(tops(b, P1, 6), 0, 6)}, check=check,
                    choice=lambda prompt, buttons: len(buttons) - 1)]
    if T.startswith("discard your opponent's active pokémon and all attached cards. if this pokémon didn't evolve"):
        return [scn('not evolved this turn', wants={}, check=lambda b: judge_damage(b, 0))]
    if T.startswith("each player either draws or discards cards until that player has 4"):
        def check(b):
            probs = []
            for pid in (P1, P2):
                if len(b.t.zone(pid, 'hand')) != 4:
                    probs.append(f"{'P1' if pid == P1 else 'P2'} hand {len(b.t.zone(pid, 'hand'))}")
            for kind, pid, prompt, cards, cnt, mn in b.t.discard_calls():
                if cards and cards[0].owning_player_id != pid:
                    probs.append(f"{'P1' if pid == P1 else 'P2'} chose the other player's discards")
            return probs
        return [scn('both hands 6', wants=lambda b: {P1: POOL(b.hand0[P1], 2), P2: POOL(b.hand0[P2], 2)}, check=check)]
    if T.startswith("flip 2 coins. if both of them are heads, discard the top card of your opponent's deck for each damage counter"):
        def setup(b):
            stack_top(b.t, P2, deck_specs(b.t.test))
            b.me.set_attribute(AttrID.HP, BIG - 30)
        return [scn('H H, 3 counters', setup=setup, heads=True, wants=lambda b: {P2: EXACT(tops(b, P2, 3))}),
                scn('H T', setup=setup, heads=seq([True, False]), wants={})]
    if T.startswith("flip a coin. if heads, discard the top 5 cards of your opponent's deck. if tails"):
        def setup(b):
            stack_top(b.t, P1, deck_specs(b.t.test))
            stack_top(b.t, P2, deck_specs(b.t.test))
        return [scn('heads', setup=setup, heads=True, wants=lambda b: {P2: EXACT(tops(b, P2, 5))}),
                scn('tails', setup=setup, heads=False, wants=lambda b: {P1: EXACT(tops(b, P1, 5))})]
    if T == "flip a coin. if heads, discard your opponent's active pokémon and all attached cards.":
        return [scn('heads', heads=True, wants=lambda b: {P2: EXACT(b.stack0['opp'])}),
                scn('tails', heads=False, wants={})]
    if T.startswith("flip a coin. if heads, search your deck for a card and put it into your hand. then, shuffle your deck. if tails, discard"):
        return [scn('heads', heads=True, wants={}),
                scn('tails', heads=False, wants=lambda b: {P1: POOL(b.hand0[P1], 1)},
                    check=lambda b: judge_prompts(b, pool=b.hand0[P1]))]
    if T.startswith("if you have exactly 2, 4, or 6 prize cards remaining, discard the top 10"):
        return [scn('6 prizes', setup=std_tops(P1), wants=lambda b: {P1: EXACT(tops(b, P1, 10))}),
                scn('5 prizes', setup=std_tops(P1, lambda b: b.t.set_prizes(P1, 5)), wants={})]
    if T.startswith("if you played tarragon"):
        return [scn('not played', wants={})]
    if T == "look at the top 2 cards of your opponent's deck, discard 1 of them, and put the other card back.":
        def check(b):
            left = [c for c in tops(b, P2, 2) if c not in new_discards(b, P2)]
            return [] if left and b.t.zone(P2, 'deck')[-1] is left[0] else ['the other card is not back on top']
        return [scn('discard', setup=std_tops(P2), wants=lambda b: {P2: POOL(tops(b, P2, 2), 1)}, check=check)]
    if T == "look at the top 4 cards of your deck and put 2 of them into your hand. discard the other cards.":
        return [scn('discard', setup=std_tops(P1), wants=lambda b: {P1: POOL(tops(b, P1, 4), 2)},
                    check=lambda b: [] if hand_delta(b) == 2 else [f"hand {hand_delta(b):+d}"])]
    if T.startswith("look at the top 6 cards of your deck, reveal any number of pokémon"):
        return [scn('take the Pokémon', setup=std_tops(P1),
                    wants=lambda b: {P1: EXACT([c for c in tops(b, P1, 6) if not isinstance(def_for(c.archetype_id), PokemonCardDef)])}),
                scn('take none', setup=std_tops(P1), pick='min', wants=lambda b: {P1: EXACT(tops(b, P1, 6))})]
    if T == "look at the top card of your deck. you may discard that card.":
        def button(word):
            return lambda prompt, btns: next((i for i, x in enumerate(btns) if word in str(x).lower()), 0)
        return [scn('yes', setup=std_tops(P1), wants=lambda b: {P1: EXACT(tops(b, P1, 1))}, choice=button('discard')),
                scn('no', setup=std_tops(P1), yes=False, choice=button('keep'), pick='min', wants={})]
    if T.startswith("reveal the top 5 cards of your deck and put all team plasma cards"):
        def specs(test):
            return [spec_def('plasma')] + deck_specs(test)[:4]
        return [scn('1 plasma', setup=top_setup(P1, specs), wants=lambda b: {P1: EXACT(tops(b, P1, 5)[1:])})]
    if T.startswith("reveal the top 5 cards of your deck. this attack does 70 damage for each future card"):
        return [scn('no future cards', setup=std_tops(P1), wants={}, check=lambda b: judge_damage(b, 0))]
    if T.startswith("reveal the top 5 cards of your deck. this attack does 80 damage for each energy card"):
        def wants(b):
            return {P1: EXACT([c for c in tops(b, P1, 5) if isinstance(def_for(c.archetype_id), EnergyCardDef)])}
        return [scn('3 energy', setup=std_tops(P1), wants=wants, check=lambda b: judge_damage(b, 240))]
    if T.startswith("reveal the top 6 cards of your deck. this attack does 60 damage for each psychic pokémon"):
        return [scn('no psychic', setup=std_tops(P1), wants=lambda b: {P1: EXACT(tops(b, P1, 6))},
                    check=lambda b: judge_damage(b, 0))]
    if T.startswith("reveal the top 6 cards of your deck. this attack does 60 damage to 1 of your opponent's pokémon for each energy"):
        def wants(b):
            return {P1: EXACT([c for c in tops(b, P1, 6) if isinstance(def_for(c.archetype_id), EnergyCardDef)])}

        def check(b):
            total = (b.hp0['opp'] - b.t.hp(b.opp)) + (b.hp0['opp_bench'] - b.t.hp(b.opp_bench))
            return [] if total == 180 else [f"total damage {total} (want 180)"]
        return [scn('3 energy', setup=std_tops(P1), wants=wants, check=check)]
    if T.startswith("reveal the top 7 cards of your deck. this attack does 30 more damage times the amount of water energy"):
        def wants(b):
            return {P1: EXACT([c for c in tops(b, P1, 7) if energy_type(b.t.test, c) != PokemonTypes.WATER])}
        return [scn('1 water', setup=std_tops(P1), wants=wants, check=lambda b: judge_damage(b, printed(a) + 30))]
    if T == "search your deck for up to 2 cards and discard them. shuffle your deck afterward.":
        return [scn('pick max', wants=lambda b: {P1: POOL(b.deck0[P1], 2)}),
                scn('pick none', pick='min', wants={})]
    if T == "search your deck for up to 4 pokémon and discard them. then, shuffle your deck.":
        def pk(b):
            return [c for c in b.deck0[P1] if isinstance(def_for(c.archetype_id), PokemonCardDef)]
        return [scn('pick max', setup=std_tops(P1), wants=lambda b: {P1: EXACT(pk(b))},
                    check=lambda b: judge_prompts(b, pool=pk(b), only_discard=False)),
                scn('pick none', setup=std_tops(P1), pick='min', wants={})]
    if T.startswith("you may discard the top card of your deck. if that card is a fire energy card"):
        return [scn('yes, fire on top', setup=std_tops(P1), wants=lambda b: {P1: EXACT(tops(b, P1, 1))},
                    check=lambda b: judge_damage(b, printed(a) + 50)),
                scn('declined', setup=std_tops(P1), yes=False, wants={}, check=lambda b: judge_damage(b, printed(a)))]
    if T == "you may do 40 more damage. if you do, discard the top 2 cards of your deck.":
        return [scn('yes', setup=std_tops(P1), wants=lambda b: {P1: EXACT(tops(b, P1, 2))},
                    check=lambda b: judge_damage(b, printed(a) + 40)),
                scn('declined', setup=std_tops(P1), yes=False, wants={}, check=lambda b: judge_damage(b, printed(a)))]
    if T.startswith("your opponent chooses to discard the top 3 cards of their deck or to discard 3 cards from their hand"):
        def check(b):
            menus = [c for c in b.t.calls if c[0] == 'choose']
            probs = [] if not menus or all(c[1] == P2 for c in menus) else ['the menu was shown to P1']
            got = new_discards(b, P2)
            from_deck = set(got) == set(tops(b, P2, 3))
            from_hand = len(got) == 3 and all(c in b.hand0[P2] for c in got)
            if not (from_deck or from_hand):
                probs.append(f"discarded {len(got)}: neither the top 3 nor 3 from hand")
            if from_hand and any(c[1] != P2 for c in b.t.discard_calls()):
                probs.append('P1 chose the hand cards')
            return probs
        return [scn('option 0', setup=std_tops(P2), choice=0, check=check),
                scn('option 1', setup=std_tops(P2), choice=1, check=check)]
    if T.startswith("your opponent reveal his or her hand. discard a supporter card you find there. use the effect"):
        return [scn('Hau in hand', wants=lambda b: {P2: EXACT([b.c['opp_h_sup']])},
                    check=lambda b: [] if hand_delta(b) == 3 else [f"P1 hand {hand_delta(b):+d} (Hau: draw 3)"])]
    if T.startswith("your opponent reveals his or her hand. you may choose a supporter card you find there. if you do, your opponent plays"):
        return [scn('Hau played', wants=lambda b: {P2: EXACT([b.c['opp_h_sup']])})]
    if T.startswith("your opponent reveals their hand. you may discard a pokémon you find there"):
        return [scn('yes', wants=lambda b: {P2: EXACT([b.c['opp_h_mon']])}),
                scn('declined', yes=False, pick='min', wants={})]
    if T.startswith("your opponent reveals their hand. you may discard a supporter card you find there"):
        return [scn('yes', wants=lambda b: {P2: EXACT([b.c['opp_h_sup']])},
                    check=lambda b: [] if hand_delta(b) == 3 else [f"P1 hand {hand_delta(b):+d} (Hau: draw 3)"]),
                scn('declined', yes=False, pick='min', wants={})]
    return None


NOT_TESTED = {
    "reveal the bottom 7 cards of your deck": "covered by test_sweep_shuffle_pokemon.shuf_bug_out (same mill/shuffle split)",
    "you and your opponent play rock-paper-scissors": "rock-paper-scissors prompt not scriptable through EffectContext",
    "look at the top card of your deck. you may put that card into your hand. if you don't":
        "covered by test_sweep_draw (take it / discard it, draw)",
}


FAMILIES = [
    ('manual', manual_plans),
    ('my_pokemon_energy', my_pokemon_energy_plans),
    ('deck', deck_plans),
    ('opp_hand', opp_hand_plans),
    ('hand', hand_plans),
    ('stadium', stadium_plans),
    ('tools', tool_plans),
    ('self_energy', self_energy_plans),
    ('opp_energy', opp_energy_plans),
]


# ================================================================== the sweep ==
def scope():
    """{(title, text, damage): [defs]} for GLC-legal attacks that discard (not just 'discard pile')."""
    groups = collections.OrderedDict()
    for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, str(d.collector_number))):
        if not isinstance(d, PokemonCardDef) or not glc.is_glc_legal(d):
            continue
        for a in d.abilities or []:
            if not isinstance(a, Attack):
                continue
            text = norm(a.game_text)
            if 'discard' not in text:
                continue
            key = (a.title, text, a.damage, a.damage_operator)
            groups.setdefault(key, []).append((d, a))
    return groups


def is_pile_only(text):
    return 'discard' not in re.sub(r"discard piles?", "", text)


async def sweep(test, limit=None, only=None):
    report = {'checked': 0, 'groups': 0, 'printings': 0, 'failures': [], 'skipped': [],
              'unhandled': {}, 'pile_only': 0, 'by_family': collections.Counter(),
              'fail_by_family': collections.Counter()}
    for (title, text, dmg, op), members in scope().items():
        report['groups'] += 1
        report['printings'] += len(members)
        if is_pile_only(text):
            report['pile_only'] += 1
            continue
        d, a = members[0]
        plans, fam = None, None
        for fam_name, fn in FAMILIES:
            plans = fn(text, d, a)
            if plans is not None:
                fam = fam_name
                break
        if plans is None:
            report['unhandled'][text] = report['unhandled'].get(text, 0) + len(members)
            continue
        if only and fam not in only:
            continue
        if limit is not None and report['checked'] >= limit:
            break
        report['checked'] += 1
        report['by_family'][fam] += 1
        report.setdefault('texts_by_family', collections.defaultdict(set))[fam].add(text)
        # every printing is judged (reprints can have their own scripts)
        prints = [f"{x.display_name} ({x.set_code} {x.collector_number})" for x, _ in members]
        bad, skips, details = [], [], []
        for (dx, ax), label_ in zip(members, prints):
            report['printings_checked'] = report.get('printings_checked', 0) + 1
            ok, detail = await run_all(test, dx, ax, fn(text, dx, ax))
            if ok is None:
                skips.append(label_ + ': ' + detail)
            elif not ok:
                bad.append(label_)
                details.append(label_ + ': ' + detail)
        if bad:
            report['fail_by_family'][fam] += 1
            report['failures'].append({'attack': title, 'text': text, 'family': fam, 'printings': bad,
                                       'all_printings': prints, 'guid': d.guid, 'detail': ' || '.join(details)})
        elif skips and len(skips) == len(members):
            report['skipped'].append({'attack': title, 'text': text, 'family': fam, 'printings': prints,
                                      'why': ' || '.join(skips)})
    return report


# ================================================================ known bugs ==
# attack text (normalised) -> (root cause, targeted test).  Shared by the report
# and by test_sweep, which fails on any failure NOT listed here.
_TOOL_CLEANUP = ("spirit/game/card_effects/bw_era.py:bw_legacy_attack, 'Attached Tool/Special Energy cleanup' branch "
                 "(if \"discard\" in text and (\"pokémon tool\" in text or \"special energy\" in text)): it fires for "
                 "every text that mentions Pokémon Tools / Special Energy, ignores whose Pokémon / hand / 'you may' / "
                 "'any number', gathers attachments from the opponent's (or both) boards, and discards all of them when "
                 "only one candidate is left")
_PREDICATE = ("spirit/game/card_effects/bw_era.py:_attack_discard_predicate falls back to `lambda card: True` when "
              "_ability_search_predicate does not understand the descriptor ('item', 'trainer', 'team plasma'), so the "
              "fixed / optional / variable hand-discard branches offer (and accept) any card")
_OPT_ALL = ("spirit/game/card_effects/bw_era.py:bw_legacy_attack: the declined optional discard-all is redone by an "
            "unconditional branch")
KNOWN_BUGS = {
    # --- optional 'discard all' Energy
    "you may discard all lightning energy attached to this pokémon. if you do, this attack does 60 more damage.":
        (_OPT_ALL + " (discard_all_bonus at ~l.7766 asks, but does not set prepaid_discard, so the generic after-effect "
                    "'discard (up to )?(\\d+|an|a|all) ... energy (attached to|from) this pokémon' at ~l.8966 discards "
                    "anyway)", 'test_optional_discard_all_declined_attached_metagross'),
    "you may discard all lightning energy attached to this pokémon. if you do, this attack does 50 more damage.":
        (_OPT_ALL + " (discard_all_bonus ~l.7766 / generic after-effect ~l.8966)",
         'test_optional_discard_all_declined_attached_metagross'),
    "you may discard all metal energy attached to this pokémon. if you do, this attack does 80 more damage.":
        (_OPT_ALL + " (discard_all_bonus ~l.7766 / generic after-effect ~l.8966)",
         'test_optional_discard_all_declined_attached_metagross'),
    "you may discard all lightning energy from this pokémon. if you do, this attack does 100 more damage.":
        (_OPT_ALL + " (optional_all_source ~l.7391 asks, then typed_all_discard ~l.11355 'discard all <type> energy "
                    "from this pokémon' discards with no 'you may' check)", 'test_optional_discard_all_declined_from_vikavolt'),
    "you may discard all lightning energy from this pokémon. if you do, this attack does 70 more damage.":
        (_OPT_ALL + " (typed_all_discard ~l.11355)", 'test_optional_discard_all_declined_from_vikavolt'),
    "you may discard all energy attached to this pokémon. if you do, this attack does 70 more damage.":
        ("spirit/game/card_effects/bw_era.py:bw_legacy_attack: neither optional_all_source (needs 'from') nor "
         "discard_all_bonus (needs a type word) matches 'all energy attached to', so the generic after-effect "
         "(~l.8966) discards everything without asking and the +70 is never added", 'test_raichu_spark_bolt_bonus_and_optional'),
    "if the total of both players' remaining prize cards is 6 or less, discard all energy attached to this pokémon, and "
    "this attack does 100 more damage.":
        ("spirit/game/card_effects/bw_era.py:_attack_clause_allowed -> attack_state_clauses.public_attack_condition does "
         "not understand the prize-total clause (returns None = allowed), so the generic self-discard (~l.8966) runs "
         "with 12 Prizes left", 'test_ultra_necrozma_shining_burst_needs_prize_total'),
    # --- opponent's Energy
    "flip a coin. if heads, your opponent's active pokémon is now paralyzed, and discard an energy from that pokémon.":
        ("spirit/game/card_effects/bw_era.py:bw_legacy_attack text normalisation (~l.5889) only rewrites 'if heads, "
         "discard an energy attached to that pokémon'; '...paralyzed(,) and discard an energy (from|attached to) that "
         "pokémon' never matches direct_defender_energy (~l.9038)", 'test_paralyzed_and_discard_that_pokemon_glalie'),
    "flip a coin. if heads, your opponent's active pokémon is now paralyzed and discard an energy attached to that pokémon.":
        ("same as Glalie: 'that pokémon' not normalised (bw_era.py ~l.5889)", 'test_paralyzed_and_discard_that_pokemon_glalie'),
    "discard a special energy from 1 of your opponent's pokémon.":
        (_TOOL_CLEANUP + " -- here it runs after opponent_energy_discard (~l.9069) already discarded 1, and discards the "
                         "last remaining Special Energy too", 'test_absol_ominous_news_discards_one'),
    # --- Tools
    "you may discard a pokémon tool card from this pokémon. if you do, this attack does 90 more damage.":
        (_TOOL_CLEANUP, 'test_kommo_o_scaly_uppercut_own_tool_only'),
    "before doing damage, you may discard any number of pokémon tool cards from your pokémon. this attack does 40 more "
    "damage for each card you discarded in this way.": (_TOOL_CLEANUP, 'test_gourgeist_pumpkin_bomb_own_tools'),
    "before doing damage, you may discard any number of pokémon tools from your pokémon. this attack does 40 more damage "
    "for each card you discarded in this way.": (_TOOL_CLEANUP, 'test_gourgeist_pumpkin_bomb_own_tools'),
    "you may discard a special energy from this pokémon. if you do, this attack does 80 more damage.":
        (_TOOL_CLEANUP, 'test_octillery_special_artillery_own_special'),
    "discard as many pokémon tool cards as you like from your hand. this attack does 40 damage times the number of cards "
    "you discarded.": (_TOOL_CLEANUP, 'test_garbodor_chuck_discards_from_hand'),
    "discard any number of pokémon tool cards from your hand. this attack does 50 damage for each card you discarded in "
    "this way.": (_TOOL_CLEANUP, 'test_garbodor_chuck_discards_from_hand'),
    "discard a pokémon tool card from your hand. if you don't, this attack does nothing.":
        (_TOOL_CLEANUP, 'test_passimian_intentional_grounding_hand_tool'),
    "your opponent reveals their hand. discard all item cards and pokémon tool cards you find there.":
        (_TOOL_CLEANUP + " -- strips every Tool in play on BOTH sides", 'test_rotom_crushing_pulse_leaves_board_tools'),
    "before doing damage, discard all pokémon tool cards from your opponent's active pokémon. if you discarded a pokémon "
    "tool card in this way, this attack does 70 more damage.":
        ("spirit/game/card_effects/bw_era.py:bw_legacy_attack: only the status clause is gated on _defender_had_tool "
         "(~l.8314); the 'if you discarded a pokémon tool ... N more damage' bonus is never added",
         'test_tool_discard_bonus_farfetchd'),
    "before doing damage, discard all pokémon tool cards from your opponent's active pokémon. if you discarded a pokémon "
    "tool card in this way, this attack does 40 more damage, and your opponent's active pokémon is now paralyzed.":
        ("bw_era.py:bw_legacy_attack: tool-gated bonus damage not implemented (~l.8314 gates only the status)",
         'test_tool_discard_bonus_farfetchd'),
    "before doing damage, discard all pokémon tool cards from your opponent's active pokémon. if you discarded a pokémon "
    "tool card in this way, heal all damage from this pokémon.":
        ("bw_era.py:bw_legacy_attack: the generic 'heal all damage from this pokémon' branch is not gated on "
         "_defender_had_tool", 'test_lickilicky_eat_up_heals_only_with_tool'),
    # --- Stadium
    "you may discard any stadium card in play. if you do, this attack does 40 more damage.":
        ("bw_era.py:bw_legacy_attack ~l.11925 'discard any stadium card in play' discards with no 'you may' prompt, and "
         "the conditional +40 is applied whenever a Stadium was in play", 'test_optional_stadium_discard_declined_swanna'),
    "you may discard any stadium card in play.":
        ("bw_era.py:bw_legacy_attack ~l.11925 discards unconditionally (no ask_yes_no)", 'test_optional_stadium_discard_declined_wooloo'),
    "you may discard a stadium in play.":
        ("bw_era.py:bw_legacy_attack ~l.9599 ('discard a stadium in play' -> ctx.discard_stadium()) ignores 'you may'",
         'test_optional_stadium_discard_declined_wooloo'),
    "if your opponent has a stadium card in play, discard it.":
        ("bw_era.py:bw_legacy_attack has no handler for 'if your opponent has a stadium card in play, discard it' (the "
         "'stadium in play' wording has per-card scripts; the only reference is the status gate ~l.8316)",
         'test_white_kyurem_field_crush_discards_opponents_stadium'),
    "if your opponent has a stadium card in play, discard it. if you do, prevent all effects of attacks, including "
    "damage, done to this pokémon during your opponent's next turn.":
        ("same as White Kyurem (no handler)", 'test_white_kyurem_field_crush_discards_opponents_stadium'),
    "if your opponent has a stadium card in play, discard it. if you do, your opponent's active pokémon is now paralyzed.":
        ("same as White Kyurem (no handler)", 'test_white_kyurem_field_crush_discards_opponents_stadium'),
    # --- your hand
    "discard an item card from your hand. if you do, this attack does 60 damage to 1 of your opponent's pokémon. this "
    "damage isn't affected by weakness or resistance.": (_PREDICATE, 'test_mandibuzz_trash_crash_item_only'),
    "you may discard an item card from your hand. if you do, this attack does 40 more damage.":
        (_PREDICATE, 'test_mandibuzz_trash_crash_item_only'),
    "discard a team plasma card from your hand. if you do, draw 3 cards.": (_PREDICATE, 'test_skarmory_cargo_jet_team_plasma_only'),
    "discard up to 2 trainer cards from your hand. this attack does 20 damage for each card you discarded in this way.":
        (_PREDICATE, 'test_snubbull_make_a_mess_trainers_only'),
    "you may discard as many basic energy cards as you like from your hand. this attack does 40 damage for each type of "
    "basic energy you discarded in this way.":
        ("spirit/game/card_effects/bw_era.py:bw_legacy_attack uses energy_provided_options at ~l.7119, but the function "
         "also does `from spirit.game.session.passives import energy_provided_options` at ~l.8068/~l.11365, which makes "
         "the name local to the whole function -> UnboundLocalError after the cards are already discarded",
         'test_grafaiai_colorful_graffiti_does_not_crash'),
    "discard a card from your hand. if you do, your opponent discards a card from their hand.":
        ("bw_era.py:bw_legacy_attack: the 'your opponent discards a card from their hand' clause runs even when the "
         "attacker discarded nothing (empty hand); 'if you do' is not tied to hand_discard_paid",
         'test_porygon_hacking_needs_own_discard'),
    "discard as many cards as you like from your hand. heal 10 damage from this pokémon for each card you discarded in "
    "this way.":
        ("bw_era.py:bw_legacy_attack: after variable_hand_utility heals 10 x cards (~l.7447), the generic healing "
         "template 'heal (\\d+) damage from (?:this pokémon|it)' (~l.8581) heals another 10", 'test_mantine_healing_wave_exact_heal'),
    "flip a coin. if heads, search your deck for a card and put it into your hand. then, shuffle your deck. if tails, "
    "discard a card from your hand.":
        ("bw_era.py:bw_legacy_attack: the tails-branch 'discard a card from your hand' never runs (fixed_hand_discard "
         "requires the clause to start a sentence: '(?:^|\\. )discard')", 'test_slowpoke_tail_fishing_tails_discards'),
    # --- decks
    "discard the top 4 cards of your deck. this attack does 50 damage times the number of fire energy cards discarded.":
        ("bw_era.py:bw_legacy_attack top_formula (~l.7219): the matching filter only special-cases 'basic water energy'; "
         "'fire energy cards' falls to the 'any Energy card' else branch", 'test_heatmor_fiery_licks_counts_fire_only'),
    "discard all lightning energy attached to this pokémon. this attack does 30 damage times the number of energy cards "
    "you discarded.":
        ("bw_era.py:bw_legacy_attack: the generic self-discard (~l.8966) discards, but no formula handles '30 damage "
         "times the number of energy cards you discarded' (damage stays at the printed 30)", 'test_galvantula_discharge_damage'),
    "each player discards the top card of their deck. this attack does 60 more damage for each energy card discarded in "
    "this way.":
        ("bw_era.py:bw_legacy_attack paired_top_formula (~l.7279) only matches 'discard the top card of each player's "
         "deck'; 'each player discards the top card of their/his or her deck' is unhandled (nothing discarded, no bonus)",
         'test_eruption_each_player_discards'),
    "each player discards the top card of his or her deck. this attack does 60 more damage for each energy card discarded "
    "in this way.": ("same as Entei SM8 47 (paired_top_formula wording)", 'test_eruption_each_player_discards'),
    "discard the top card of your opponent's deck. if that card is an energy card, this attack does 60 more damage.":
        ("bw_era.py:bw_legacy_attack: top_formula (~l.7219) only matches 'your deck'; the opponent-deck mill (~l.9210) "
         "ignores the 'if that card is an energy card' bonus", 'test_ambipom_furry_chance_bonus'),
    "discard the top card of your opponent's deck. if the card you discarded is a pokémon, this attack does damage equal "
    "to that pokémon's hp to your opponent's active pokémon.":
        ("bw_era.py:bw_legacy_attack: the opponent-deck mill (~l.9210) runs, the 'damage equal to that Pokémon's HP' "
         "clause is unimplemented", 'test_alolan_marowak_spirit_smash_damage'),
    "discard the top 4 cards of your deck. if any of those cards are fire energy cards, attach them to your pokémon in any "
    "way you like.":
        ("bw_era.py:bw_legacy_attack 'Top-card/top-five Energy acceleration' (~l.10099): energy_type is 'fighting' "
         "or else 'basic', so ANY basic Energy (e.g. Water) is attached instead of only Fire",
         'test_flaming_honk_attaches_fire_only'),
    "look at the top 2 cards of your opponent's deck, discard 1 of them, and put the other card back.":
        ("no handler in bw_era.py:bw_legacy_attack (nothing happens)", 'test_watchog_scrutinize_discards_one'),
    "you may do 40 more damage. if you do, discard the top 2 cards of your deck.":
        ("bw_era.py:bw_legacy_attack: no 'you may do N more damage' prompt; self_top_discard (~l.9133) mills 2 every "
         "time and the +40 is never added", 'test_diggersby_mountaintop_mining_optional'),
    "discard the top 3 cards of your deck. for each water energy card you discarded in this way, discard the top 3 cards "
    "of your opponent's deck.":
        ("bw_era.py:bw_legacy_attack opponent-deck mill (~l.9210) handles 'for each heads' / 'for each <type> energy "
         "attached' leads only: always mills exactly 3", 'test_avalugg_melting_floe_per_water'),
    "if you have exactly 2, 4, or 6 prize cards remaining, discard the top 10 cards of your deck.":
        ("bw_era.py:_attack_clause_allowed -> attack_state_clauses.public_attack_condition returns None for 'you have "
         "exactly 2, 4, or 6 prize cards remaining' (treated as allowed), so self_top_discard (~l.9133) always mills 10",
         'test_guzzlord_lords_valley_prize_condition'),
}

# Texts whose report entry is a ruling question, not a bug.
RULINGS = {}   # Oct 12: owner ruled Tools are never Item cards.


def write_report(r):
    os.makedirs(REPORT_DIR, exist_ok=True)
    bugs = collections.defaultdict(list)
    for f in r['failures']:
        rc = KNOWN_BUGS.get(f['text'])
        f['root_cause'], f['test'] = (rc if rc else ('UNTRIAGED', ''))
        bugs[f['test']].append(f['printings'][0] + ' — ' + f['attack'])
    out = {
        'case': 'attack_discard',
        'scope': {'attack_groups_title_text_damage': r['groups'], 'printings': r['printings'],
                  'pile_only_groups_out_of_scope': r['pile_only'],
                  'groups_checked': r['checked'], 'printings_checked': r.get('printings_checked', 0),
                  'distinct_texts_checked': sum(len(v) for v in r.get('texts_by_family', {}).values()),
                  'groups_by_family': dict(r['by_family']),
                  'distinct_texts_by_family': {k: len(v) for k, v in r.get('texts_by_family', {}).items()},
                  'fail_by_family': dict(r['fail_by_family'])},
        'bugs_by_test': dict(bugs),
        'failures': r['failures'],
        'skipped': r['skipped'],
        'not_tested': [{'text': t, 'printings': c, 'why': next((w for k, w in NOT_TESTED.items() if t.startswith(k)),
                                                                'no template')} for t, c in r['unhandled'].items()],
        'rulings': RULINGS,
    }
    with open(os.path.join(REPORT_DIR, 'attack_discard.json'), 'w') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False, default=str)
    return out


class SweepAttackDiscard(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_sweep(self):
        if os.environ.get('SWEEP_SKIP'):
            self.skipTest('SWEEP_SKIP')
        r = await sweep(self)
        out = write_report(r)
        print(f"\nattack_discard: {r['groups']} groups / {r['printings']} printings; checked {r['checked']} groups, "
              f"{out['scope']['distinct_texts_checked']} texts, {r.get('printings_checked')} printings "
              f"{dict(r['by_family'])}; failures {len(r['failures'])}; skipped {len(r['skipped'])}; "
              f"not tested {len(r['unhandled'])}; 'discard pile' only {r['pile_only']}")
        new = [f for f in r['failures'] if f['text'] not in KNOWN_BUGS and f['text'] not in RULINGS]
        fixed = sorted({t for t in KNOWN_BUGS} - {f['text'] for f in r['failures']})
        if fixed:
            print('  known bugs that now pass:', fixed)
        self.assertEqual([], [(f['printings'][0], f['attack'], f['detail'][:300]) for f in new])


# ========================================================= targeted bug tests ==
def card_attack(set_code, number, title):
    for d in CARD_DEFS_BY_GUID.values():
        if isinstance(d, PokemonCardDef) and d.set_code == set_code and str(d.collector_number) == str(number):
            for a in d.abilities or []:
                if isinstance(a, Attack) and a.title == title:
                    return d, a
    raise KeyError((set_code, number, title))


class AttackDiscardBugs(unittest.IsolatedAsyncioTestCase):
    """One scenario per bug group, through the same templates as the sweep."""
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def scenario(self, set_code, number, title, name):
        d, a = card_attack(set_code, number, title)
        text = norm(a.game_text)
        plans = None
        for _, fn in FAMILIES:
            plans = fn(text, d, a)
            if plans is not None:
                break
        self.assertIsNotNone(plans, text)
        s = next(p for p in plans if p['name'] == name)
        ok, detail = await run_scenario(self, d, a, s)
        self.assertTrue(ok, detail)

    # --- regression guards for the brief's examples (pass)
    async def test_melmetal_reforged_axe_only_own_tools(self):
        await self.scenario('SV07', 104, 'Reforged Axe', 'with tool')
        await self.scenario('SV07', 104, 'Reforged Axe', 'no tool')

    async def test_mawile_hand_discard_energy_only(self):
        d, a = next((d, a) for (t, tx, dm, op), ms in scope().items() for d, a in ms
                    if d.display_name == 'Mawile' and 'energy cards from your hand' in tx)
        for name in ('pick max', 'pick none'):
            plans = hand_plans(norm(a.game_text), d, a)
            ok, detail = await run_scenario(self, d, a, next(p for p in plans if p['name'] == name))
            self.assertTrue(ok, detail)

    async def test_whiscash_mills_opponents_deck_per_energy(self):
        d, a = next((d, a) for (t, tx, dm, op), ms in scope().items() for d, a in ms
                    if d.display_name == 'Whiscash' and 'top card of your opponent' in tx)
        ok, detail = await run_scenario(self, d, a, deck_plans(norm(a.game_text), d, a)[0])
        self.assertTrue(ok, detail)


    # --- Energy units vs Energy cards (Counter Energy behind on Prizes = 2 of every type)
    def units_board(self, set_code, number, title, extra):
        d, a = card_attack(set_code, number, title)

        def setup(b):
            b.t.set_prizes(P2, 3)                    # P1 has more Prizes left: Counter Energy provides 2
            b.counter = b.t.attach(CARD_DEFS_BY_GUID[COUNTER], b.me)
            if extra:
                extra(b)
        b = make_board(self, d, a, {'name': 'units', 'setup': setup})
        return d, a, b

    async def test_top_burner_counts_energy_units(self):
        """Moltres SM9 19: '...a card from the top of your opponent's deck for each Energy you discarded'."""
        d, a, b = self.units_board('SM9', 19, 'Top Burner', lambda b: stack_top(b.t, P2, deck_specs(b.t.test)))
        fires = [e for e in b.me_energy0 if energy_type(b.t.test, e) == PokemonTypes.FIRE]
        await b.t.attack(b.me, a.title)
        self.assertIn(b.counter, new_discards(b, P1))
        self.assertEqual(len(new_discards(b, P2)), len(fires) + 2)

    async def test_discharge_counts_cards_not_units(self):
        """Zeraora SM10 60: 'this attack does 50 damage for each card you discarded'."""
        d, a, b = self.units_board('SM10', 60, 'Discharge', None)
        light = [e for e in b.me_energy0 if energy_type(b.t.test, e) == PokemonTypes.LIGHTNING]
        await b.t.attack(b.me, a.title)
        self.assertIn(b.counter, new_discards(b, P1))
        self.assertEqual(dealt(b), 50 * (len(light) + 1))

    async def test_discard_2_energy_accepts_one_double_unit_card(self):
        """Kyogre ME1 34 'Discard 2 Energy': the unit picker is asked for 2 and one 2-unit card pays it."""
        d, a, b = self.units_board('ME1', 34, 'Swirling Waves', None)
        b.t.unit_pick = lambda energies, amount: [b.counter]
        await b.t.attack(b.me, a.title)
        units = [c for c in b.t.calls if c[0] == 'units']
        self.assertTrue(units and units[0][4] == 2, units)
        self.assertEqual(new_discards(b, P1), [b.counter])

    # --- optional 'discard all' Energy
    # FIXED: bw_era.py:bw_legacy_attack -- declined 'you may discard all X energy attached to' is redone by the generic after-effect (~l.8966)
    async def test_optional_discard_all_declined_attached_metagross(self):
        await self.scenario('XY7', 49, 'Iron Cannon', 'declined')

    # FIXED: bw_era.py:bw_legacy_attack -- typed_all_discard (~l.11355) ignores 'you may'
    async def test_optional_discard_all_declined_from_vikavolt(self):
        await self.scenario('Promo_SM', 208, 'Electricannon', 'declined')

    # FIXED: bw_era.py:bw_legacy_attack -- 'you may discard all energy attached to' has no optional branch: always discards, never +70
    async def test_raichu_spark_bolt_bonus_and_optional(self):
        await self.scenario('XY12', 36, 'Spark Bolt', 'yes')

    # FIXED: bw_era.py:_attack_clause_allowed/public_attack_condition -- prize-total clause unknown = allowed
    async def test_ultra_necrozma_shining_burst_needs_prize_total(self):
        await self.scenario('Promo_SM', 165, 'Shining Burst', 'condition false')

    # --- opponent's Energy
    # FIXED: bw_era.py:bw_legacy_attack -- '...paralyzed, and discard an energy from that pokémon' never discards (~l.5889 normalisation)
    async def test_paralyzed_and_discard_that_pokemon_glalie(self):
        await self.scenario('SM12', 48, 'Ice Fang', 'heads')

    # FIXED: bw_era.py:bw_legacy_attack -- Tool/Special Energy cleanup branch discards a 2nd Special Energy
    async def test_absol_ominous_news_discards_one(self):
        await self.scenario('SM12', 133, 'Ominous News', 'bench target')

    # --- Tools (cleanup branch)
    # FIXED: bw_era.py:bw_legacy_attack -- Tool cleanup branch offers both boards' Tools, ignores 'you may' and 'this pokémon'
    async def test_kommo_o_scaly_uppercut_own_tool_only(self):
        await self.scenario('SM12', 163, 'Scaly Uppercut', 'yes')

    # FIXED: bw_era.py:bw_legacy_attack -- Tool cleanup branch: discards the OPPONENT's Tool, 1 card, even when picking none
    async def test_gourgeist_pumpkin_bomb_own_tools(self):
        await self.scenario('SM4', 45, 'Pumpkin Bomb', 'pick none')

    # FIXED: bw_era.py:bw_legacy_attack -- Tool/Special cleanup branch discards the opponent's Special Energy instead of this Pokémon's
    async def test_octillery_special_artillery_own_special(self):
        await self.scenario('SM4', 23, 'Special Artillery', 'declined')

    # FIXED: bw_era.py:bw_legacy_attack -- Tool cleanup branch: Chuck discards a Tool in PLAY (opponent's) instead of from hand
    async def test_garbodor_chuck_discards_from_hand(self):
        await self.scenario('SV4', 117, 'Chuck', 'pick max')

    # FIXED: bw_era.py:bw_legacy_attack -- Tool cleanup branch: cost paid with a Tool in play; attack not 'nothing' without a hand Tool
    async def test_passimian_intentional_grounding_hand_tool(self):
        await self.scenario('SM3', 79, 'Intentional Grounding', 'none matching')

    # FIXED: bw_era.py:bw_legacy_attack -- Tool cleanup branch strips every Tool in play on both sides
    async def test_rotom_crushing_pulse_leaves_board_tools(self):
        await self.scenario('SV08', 61, 'Crushing Pulse', 'discard all')

    # FIXED: bw_era.py:bw_legacy_attack -- 'if you discarded a pokémon tool ..., N more damage' bonus missing
    async def test_tool_discard_bonus_farfetchd(self):
        await self.scenario('SM9', 127, 'Tool Buster', 'with tool')

    # FIXED: bw_era.py:bw_legacy_attack -- Eat Up heals with no Tool discarded
    async def test_lickilicky_eat_up_heals_only_with_tool(self):
        await self.scenario('SM10', 153, 'Eat Up', 'no tool')

    # --- Stadium
    # FIXED: bw_era.py:bw_legacy_attack ~l.11925 -- optional Stadium discard always happens (+40 too)
    async def test_optional_stadium_discard_declined_swanna(self):
        await self.scenario('BW7', 43, 'Defog', 'declined')

    # FIXED: bw_era.py:bw_legacy_attack ~l.9599 -- 'you may discard a stadium in play' always discards
    async def test_optional_stadium_discard_declined_wooloo(self):
        await self.scenario('SV07', 124, 'Knock Over', 'declined')

    # FIXED: bw_era.py:bw_legacy_attack -- 'if your opponent has a stadium card in play, discard it' unimplemented
    async def test_white_kyurem_field_crush_discards_opponents_stadium(self):
        await self.scenario('SM8', 63, 'Field Crush', 'opp stadium')

    async def test_white_kyurem_field_crush_keeps_my_stadium(self):
        await self.scenario('SM8', 63, 'Field Crush', 'my stadium')

    # --- your hand
    # FIXED: bw_era.py:_attack_discard_predicate -- 'item' falls back to any card (no Item in hand: a Supporter is discarded)
    async def test_mandibuzz_trash_crash_item_only(self):
        await self.scenario('SM9', 93, 'Trash Crash', 'none matching')

    # FIXED: bw_era.py:_attack_discard_predicate -- 'team plasma' falls back to any card
    async def test_skarmory_cargo_jet_team_plasma_only(self):
        await self.scenario('BW8', 87, 'Cargo Jet', 'none matching')

    # FIXED: bw_era.py:_attack_discard_predicate -- 'trainer' falls back to any card (Energy/Pokémon offered)
    async def test_snubbull_make_a_mess_trainers_only(self):
        await self.scenario('SM8', 137, 'Make a Mess', 'pick max')

    # FIXED: bw_era.py:bw_legacy_attack -- UnboundLocalError energy_provided_options (local import later in the function)
    async def test_grafaiai_colorful_graffiti_does_not_crash(self):
        await self.scenario('SV045', 190, 'Colorful Graffiti', 'pick max')

    # FIXED: bw_era.py:bw_legacy_attack -- opponent discards although the attacker discarded nothing
    async def test_porygon_hacking_needs_own_discard(self):
        await self.scenario('SV10', 153, 'Hacking', 'none matching')

    # FIXED: bw_era.py:bw_legacy_attack -- generic heal template adds 10 on top of the per-card heal
    async def test_mantine_healing_wave_exact_heal(self):
        await self.scenario('XY11', 27, 'Healing Wave', 'pick none')

    # FIXED: bw_era.py:bw_legacy_attack -- tails 'discard a card from your hand' never happens
    async def test_slowpoke_tail_fishing_tails_discards(self):
        await self.scenario('SV2', 85, 'Tail-Fishing', 'tails')

    # --- decks
    # FIXED: bw_era.py:bw_legacy_attack top_formula -- counts every Energy card, not Fire
    async def test_heatmor_fiery_licks_counts_fire_only(self):
        await self.scenario('BW8', 23, 'Fiery Licks', 'discard')

    # FIXED: bw_era.py:bw_legacy_attack -- 'damage times the number of energy cards you discarded' not applied
    async def test_galvantula_discharge_damage(self):
        await self.scenario('BW8', 51, 'Discharge', 'discard')

    # FIXED: bw_era.py:bw_legacy_attack paired_top_formula -- 'each player discards the top card' unhandled
    async def test_eruption_each_player_discards(self):
        await self.scenario('SM8', 47, 'Eruption', 'discard')

    # FIXED: bw_era.py:bw_legacy_attack -- opponent-deck 'if that card is an energy card' bonus missing
    async def test_ambipom_furry_chance_bonus(self):
        await self.scenario('XY11', 91, 'Furry Chance', 'discard')

    # FIXED: bw_era.py:bw_legacy_attack -- 'damage equal to that Pokémon's HP' unimplemented
    async def test_alolan_marowak_spirit_smash_damage(self):
        await self.scenario('SM11', 75, 'Spirit Smash', 'pokémon on top')

    # FIXED: bw_era.py:bw_legacy_attack Top-card Energy acceleration -- attaches any basic Energy, not only Fire
    async def test_flaming_honk_attaches_fire_only(self):
        await self.scenario('SM7', 29, 'Flaming Honk', 'discard')

    # FIXED: bw_era.py:bw_legacy_attack -- Scrutinize unimplemented
    async def test_watchog_scrutinize_discards_one(self):
        await self.scenario('SM2', 108, 'Scrutinize', 'discard')

    # FIXED: bw_era.py:bw_legacy_attack -- 'you may do 40 more damage. if you do, discard ...' never asks, always mills, no +40
    async def test_diggersby_mountaintop_mining_optional(self):
        await self.scenario('SM6', 98, 'Mountaintop Mining', 'declined')

    # FIXED: bw_era.py:bw_legacy_attack -- opponent mill ignores 'for each water energy card you discarded'
    async def test_avalugg_melting_floe_per_water(self):
        await self.scenario('XY11', 37, 'Melting Floe', '2 water')

    # FIXED: bw_era.py:_attack_clause_allowed/public_attack_condition -- '2, 4, or 6 prize cards' clause unknown = allowed
    async def test_guzzlord_lords_valley_prize_condition(self):
        await self.scenario('HF', 126, "Lord's Valley", '5 prizes')


if __name__ == "__main__":
    unittest.main()
