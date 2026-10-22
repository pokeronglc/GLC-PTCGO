"""Sweep: non-damage attack effects (heal, energy discard, mill, hand disruption,
self/defender locks, next-turn protection, switching, damage-counter placement)."""
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import (SweepCase, run_sweep, Board, snapshot, pay_cost,
                              neutral, do_attack, dealt, BIG)
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack, CARD_DEFS_BY_GUID, def_for
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

# Vanilla attackers used by P2 on its next turn (160 damage, no Ability).
BASIC_ATTACKER = ('2fb04ba1-b2c6-59b2-8e93-32846118619c', 'Buster Tail')     # Dialga SV08 135
EVO_ATTACKER = ('fce33d95-a617-5a10-b332-2f32a0d09033', 'Boulder Crush')     # Armaldo SWSH12 96
ATTACKER_DMG = 160

TYPES = {'grass': PokemonTypes.GRASS, 'fire': PokemonTypes.FIRE, 'water': PokemonTypes.WATER,
         'lightning': PokemonTypes.LIGHTNING, 'psychic': PokemonTypes.PSYCHIC,
         'fighting': PokemonTypes.FIGHTING, 'darkness': PokemonTypes.DARKNESS,
         'metal': PokemonTypes.METAL, 'fairy': PokemonTypes.FAIRY}


def has_ability(d):
    return any(not isinstance(a, Attack) for a in (d.abilities or []))


def plain_damage(attack):
    """Printed damage when it is a fixed amount, else None."""
    if (attack.damage_operator or '') not in ('', None):
        return None
    return attack.damage or 0


# ----------------------------------------------------------------------
# Board
# ----------------------------------------------------------------------

class FxTable(Table):
    """Table that also records who is asked to pick a Pokémon, and scripts
    the click-to-place damage-counter picker."""

    def __init__(self, test):
        super().__init__(test)
        self.pokemon_askers = []      # player_id passed to choose_pokemon
        self.placement = None         # callable(candidates, count) -> {entity_id: n}
        self.placement_seen = []      # candidate entity lists offered

    def _patches(self):
        table = self
        out = super()._patches()
        base_choose = out[1].new

        async def choose_pokemon(ctx, candidates, prompt='', player_id=None, *a, **k):
            table.pokemon_askers.append(player_id or ctx.player_id)
            return await base_choose(ctx, candidates, prompt)

        async def placement(session, player_id, source_entity_id, candidates, count, *a, **k):
            table.placement_seen.append([c.entity_id for c in candidates])
            if table.placement is not None:
                return table.placement(candidates, count)
            return {candidates[0].entity_id: count}

        async def attempt_flip(session, player_id, attacker, title):
            # Smokescreen-family pre-attack flip uses random.choice; script it.
            return table.heads(title) if callable(table.heads) else bool(table.heads)

        out[1] = patch.object(EffectContext, 'choose_pokemon', choose_pokemon)
        out.append(patch.object(type(self.session), '_resolve_attack_attempt_flip', attempt_flip))
        out.append(patch.object(type(self.session), 'prompt_damage_counter_placement', placement))
        return out


def board(test, d, attack, *, heads=True, opp_spec=None, prep=None, my_max=None):
    t = FxTable(test)
    t.heads = heads
    me = t.put(d, P1, 'active')
    if my_max is not None:
        neutral(me, None)
        me.attribute_originals[AttrID.HP.value] = my_max
        me.set_attribute(AttrID.HP, my_max)
    my_bench = neutral(t.put(test.filler, P1, 'bench'))
    opp = neutral(t.put(opp_spec or test.filler, P2, 'active'))
    opp_bench = neutral(t.put(test.filler, P2, 'bench'))
    pay_cost(t, me, attack)
    b = Board(t, me, opp, my_bench, opp_bench, attack)
    if prep is not None:
        prep(b)
    b.before = snapshot(b)
    return b


def hurt(b, damage, max_hp=500):
    """Give P1's attacker a big max HP and `damage` damage."""
    me = b.me
    me.attribute_originals[AttrID.HP.value] = max_hp
    me.set_attribute(AttrID.HP, max_hp - damage)


def not_offered(d):
    if has_ability(d):
        return None, 'attack not offered (card has an Ability that may forbid it)'
    return False, 'attack not offered with its cost paid'


def dmg_check(d, b, who='opp'):
    """'' when the printed damage was dealt (or can't be judged), else a message."""
    want = plain_damage(b.attack)
    if want is None or has_ability(d):
        return ''
    got = dealt(b, who)
    return '' if got == want else f"; damage {got}, printed {want}"


def energies(b, pokemon):
    return list(b.t.board.attached_energies(pokemon))


def count_type(b, pokemon, kind):
    guid = b.t.test.energies[kind.value].lower()
    return sum(1 for e in energies(b, pokemon) if def_for(e.archetype_id).guid.lower() == guid)


async def p2_attack(b, title):
    """Hand the turn to P2 and attack with its Active; returns damage done to P1's attacker."""
    t = b.t
    t.next_turn()
    before = t.hp(b.me)
    entry = t.attack_offer(b.opp, title, pid=P2)
    if entry is None:
        return None
    await t.do(entry, pid=P2)
    in_play = b.me in t.board.pokemon_in_play(P1)
    return (before - t.hp(b.me)) if in_play else before


# ----------------------------------------------------------------------
# Checkers
# ----------------------------------------------------------------------

async def heal_self(test, d, attack, m):
    n = int(m.group(1))
    b = board(test, d, attack, prep=lambda b: hurt(b, n + 30))
    if not await do_attack(b):
        return not_offered(d)
    healed = b.t.hp(b.me) - b.before['me_hp']
    msg = dmg_check(d, b)
    return healed == n and not msg, f"healed {healed} (want {n}){msg}"


async def heal_same(test, d, attack, m):
    want = plain_damage(attack)
    if not want:
        return None, 'no fixed damage'
    b = board(test, d, attack, prep=lambda b: hurt(b, 300))
    if not await do_attack(b):
        return not_offered(d)
    done = dealt(b)
    healed = b.t.hp(b.me) - b.before['me_hp']
    ok = healed == done and done > 0
    return ok, f"did {done}, healed {healed}{dmg_check(d, b)}"


async def self_energy_discard(test, d, attack, m):
    amount, kind = m.group(1), m.group(2)
    kind_t = TYPES.get(kind) if kind else None

    def prep(b):
        b.t.energy(b.me, PokemonTypes.WATER if kind_t != PokemonTypes.WATER else PokemonTypes.FIRE, 2)
        if kind_t is not None:
            b.t.energy(b.me, kind_t, 2)
    b = board(test, d, attack, prep=prep)
    total0 = len(energies(b, b.me))
    typed0 = count_type(b, b.me, kind_t) if kind_t else None
    if not await do_attack(b):
        return not_offered(d)
    total1 = len(energies(b, b.me))
    gone = total0 - total1
    to_discard = len(b.t.zone(P1, 'discard')) - b.before['my_discard']
    if amount == 'all':
        if kind_t:
            ok = count_type(b, b.me, kind_t) == 0 and gone == typed0
        else:
            ok = total1 == 0
        want = typed0 if kind_t else total0
    else:
        want = 1 if amount in ('an', 'a') else int(amount)
        ok = gone == want
        if kind_t:
            ok = ok and typed0 - count_type(b, b.me, kind_t) == want
    ok = ok and to_discard == gone
    return ok and not dmg_check(d, b), (f"{total0}->{total1} energy (want -{want}), "
                                        f"discard +{to_discard}{dmg_check(d, b)}")


SPECIAL_ENERGY = 'cd7f0518-76e6-5249-bd0a-b7c75e76e096'       # Aurora Energy
SPECIAL_NAME = 'Aurora Energy'


def special_energy_def():
    return CARD_DEFS_BY_GUID[SPECIAL_ENERGY]


async def opp_energy_discard(test, d, attack, m):
    flip, special = bool(m.group(1)), bool(m.group(2))
    results = []
    for heads in ((True, False) if flip else (True,)):
        def prep(b):
            b.t.energy(b.opp, PokemonTypes.WATER, 2)
            if special:
                b.t.attach(special_energy_def(), b.opp)
        b = board(test, d, attack, heads=heads, prep=prep)
        if not await do_attack(b):
            return not_offered(d)
        gone = b.before['opp_energy'] - len(energies(b, b.opp))
        to_discard = len(b.t.zone(P2, 'discard')) - b.before['opp_discard']
        want = 1 if heads else 0
        ok = gone == want and to_discard == want
        if special and heads:
            names = [def_for(e.archetype_id).display_name for e in energies(b, b.opp)]
            ok = ok and SPECIAL_NAME not in names
        mine = b.before['my_energy'] - len(energies(b, b.me))
        ok = ok and mine == 0
        results.append((ok, f"{'H' if heads else 'T'}: opp -{gone} energy (want -{want}), "
                            f"opp discard +{to_discard}, mine -{mine}{dmg_check(d, b)}"))
    return all(r[0] for r in results), ' | '.join(r[1] for r in results)


async def mill(test, d, attack, m):
    n = 1 if m.group(1) == 'card' else int(m.group(2))
    pid = P2 if m.group(3) == "your opponent's" else P1
    holder = {}

    def prep(b):
        holder['marks'] = b.t.deck(pid, [b.t.basic_energy(PokemonTypes.FIRE)] * n)
    b = board(test, d, attack, prep=prep)
    if not await do_attack(b):
        return not_offered(d)
    side = 'opp' if pid == P2 else 'my'
    lost = b.before[f'{side}_deck'] - len(b.t.zone(pid, 'deck'))
    gained = len(b.t.zone(pid, 'discard')) - b.before[f'{side}_discard']
    disc = b.t.zone(pid, 'discard')
    tops = all(c in disc for c in holder['marks'])
    other = P1 if pid == P2 else P2
    oside = 'my' if pid == P2 else 'opp'
    other_ok = len(b.t.zone(other, 'deck')) == b.before[f'{oside}_deck']
    ok = lost == n and gained == n and tops and other_ok
    return ok and not dmg_check(d, b), (f"deck -{lost}, discard +{gained} (want {n}), top cards discarded "
                                        f"{tops}, other deck untouched {other_ok}{dmg_check(d, b)}")


async def random_hand(test, d, attack, m):
    flip = bool(m.group(1))
    shuffle = 'shuffles' in m.group(0)
    results = []
    for heads in ((True, False) if flip else (True,)):
        def prep(b):
            for _ in range(3):
                b.t.put(test.item, P2, 'hand')
        b = board(test, d, attack, heads=heads, prep=prep)
        if not await do_attack(b):
            return not_offered(d)
        want = 1 if heads else 0
        hand = b.before['opp_hand'] - len(b.t.zone(P2, 'hand'))
        disc = len(b.t.zone(P2, 'discard')) - b.before['opp_discard']
        deck = len(b.t.zone(P2, 'deck')) - b.before['opp_deck']
        mine = b.before['my_hand'] - len(b.t.zone(P1, 'hand'))
        if shuffle:
            ok = hand == want and deck == want and disc == 0
        else:
            ok = hand == want and disc == want and deck == 0
        ok = ok and mine == 0
        results.append((ok, f"{'H' if heads else 'T'}: opp hand -{hand}, discard +{disc}, "
                            f"deck +{deck} (want {want}){dmg_check(d, b)}"))
    return all(r[0] for r in results), ' | '.join(r[1] for r in results)


def _offered(b, title):
    return b.t.attack_offer(b.me, title) is not None


async def self_lock(test, d, attack, m):
    flip = bool(m.group(1))
    what = m.group(2)
    if what in ('attack', 'use attacks'):
        locked_title = None
    else:
        locked_title = what[len('use '):]
        if norm_title(attack.title) != locked_title:
            return None, f"locks a different attack ({locked_title})"
    others = [a for a in d.abilities if isinstance(a, Attack) and a is not attack]
    results = []
    for heads in ((True, False) if flip else (True,)):
        def prep(b):
            for a in others:
                pay_cost(b.t, b.me, a)
            pay_cost(b.t, b.me, attack)       # spare copy in case it discards Energy
        b = board(test, d, attack, heads=heads, prep=prep, my_max=BIG)
        if not await do_attack(b):
            return not_offered(d)
        should_lock = (not flip) or (not heads)
        t = b.t
        t.next_turn(); t.next_turn()          # P2 then P1
        nxt = {a.title: _offered(b, a.title) for a in [attack] + others}
        t.next_turn(); t.next_turn()
        after = {a.title: _offered(b, a.title) for a in [attack] + others}
        if not after[attack.title]:
            return None, f"attack not offered two turns later either ({after})"
        bad = []
        if should_lock:
            if nxt[attack.title]:
                bad.append('still offered next turn')
            if locked_title is None:
                bad += [f"{k} offered next turn" for k in nxt if nxt[k]]
            else:
                bad += [f"{k} locked next turn" for k in nxt
                        if k != attack.title and after[k] and not nxt[k]]
        elif not nxt[attack.title]:
            bad.append('locked next turn although the coin said no lock')
        results.append((not bad, f"{'H' if heads else 'T'}: next {nxt}, after {after} {bad}"))
    return all(r[0] for r in results), ' | '.join(r[1] for r in results)


def norm_title(title):
    return re.sub(r"\s+", " ", title.replace("’", "'").lower()).strip()


def _retreat_offered(b):
    return b.t.can(b.opp, 'BaseRetreat', pid=P2)


async def defender_no_retreat(test, d, attack, m):
    b = board(test, d, attack, prep=lambda b: b.t.energy(b.opp, PokemonTypes.WATER, 5),
              my_max=BIG)
    if not await do_attack(b):
        return not_offered(d)
    t = b.t
    if b.opp not in t.board.pokemon_in_play(P2) or t.active(P2) is not b.opp:
        return False, 'defending Pokémon left the Active spot'
    t.next_turn()
    nxt = _retreat_offered(b)
    t.next_turn()
    mine = t.can(b.me, 'BaseRetreat', pid=P1)
    t.next_turn()
    after = _retreat_offered(b)
    if not after:
        return None, 'retreat not offered two turns later either'
    return (not nxt), f"P2 retreat offered next turn: {nxt}, turn after: {after}, P1 can retreat: {mine}{dmg_check(d, b)}"


async def _protect_run(test, d, attack, attacker, heads=True, prep_extra=None):
    """P1 attacks, then P2's attacker hits twice (next turn and the turn after).
    Returns (first, second, board) damage to P1's Pokémon, or a skip string."""
    guid, title = attacker
    spec = CARD_DEFS_BY_GUID[guid]
    a2 = next(x for x in spec.abilities if x.title == title)

    def prep(b):
        pay_cost(b.t, b.opp, a2)
        if prep_extra:
            prep_extra(b)
    b = board(test, d, attack, heads=heads, opp_spec=spec, prep=prep, my_max=BIG)
    if not await do_attack(b):
        return 'not offered', None, b
    if b.t.active(P2) is not b.opp:
        return 'defender moved', None, b
    first = await p2_attack(b, title)
    b.t.next_turn()
    b.t.heads = True
    second = await p2_attack(b, title)
    return first, second, b


async def protect_reduce(test, d, attack, m):
    n = int(m.group(1) or m.group(2))
    first, second, b = await _protect_run(test, d, attack, BASIC_ATTACKER)
    if first == 'not offered':
        return not_offered(d)
    if isinstance(first, str) or first is None:
        return None, f"P2 couldn't attack ({first})"
    want = max(0, ATTACKER_DMG - n)
    ok = first == want and second == ATTACKER_DMG
    return ok, f"took {first} next turn (want {want}), then {second} (want {ATTACKER_DMG}){dmg_check(d, b)}"


async def protect_stage(test, d, attack, m):
    kind = m.group(1) or m.group(2)
    out = []
    for attacker, is_basic in ((BASIC_ATTACKER, True), (EVO_ATTACKER, False)):
        first, second, b = await _protect_run(test, d, attack, attacker)
        if first == 'not offered':
            return not_offered(d)
        if isinstance(first, str) or first is None:
            return None, f"P2 couldn't attack ({first})"
        blocked = (kind == 'basic') == is_basic
        want = 0 if blocked else ATTACKER_DMG
        out.append((first == want and second == ATTACKER_DMG,
                    f"{'basic' if is_basic else 'evo'} attacker: {first} (want {want}) then {second}"))
    return all(o[0] for o in out), ' | '.join(o[1] for o in out)


async def protect_other(test, d, attack, m):
    """Conditional shields our vanilla Basic (160, no Ability, not VMAX) must get through."""
    first, second, b = await _protect_run(test, d, attack, BASIC_ATTACKER)
    if first == 'not offered':
        return not_offered(d)
    if isinstance(first, str) or first is None:
        return None, f"P2 couldn't attack ({first})"
    return (first == ATTACKER_DMG and second == ATTACKER_DMG,
            f"vanilla Basic 160 attacker: {first} (want {ATTACKER_DMG}) then {second}")


async def protect_flip(test, d, attack, m):
    out = []
    for heads in (True, False):
        first, second, b = await _protect_run(test, d, attack, BASIC_ATTACKER, heads=heads)
        if first == 'not offered':
            return not_offered(d)
        if isinstance(first, str) or first is None:
            return None, f"P2 couldn't attack ({first})"
        want = 0 if heads else ATTACKER_DMG
        out.append((first == want and second == ATTACKER_DMG,
                    f"{'H' if heads else 'T'}: {first} (want {want}) then {second}"))
    return all(o[0] for o in out), ' | '.join(o[1] for o in out)


async def defender_flip_attack(test, d, attack, m):
    out = []
    for p2_heads in (True, False):
        guid, title = BASIC_ATTACKER
        spec = CARD_DEFS_BY_GUID[guid]
        a2 = next(x for x in spec.abilities if x.title == title)
        b = board(test, d, attack, opp_spec=spec, prep=lambda b: pay_cost(b.t, b.opp, a2),
                  my_max=BIG)
        if not await do_attack(b):
            return not_offered(d)
        b.t.heads = p2_heads
        first = await p2_attack(b, title)
        if first is None:
            return False, 'P2 attack not offered (should be offered, coin decides)'
        b.t.next_turn()
        b.t.heads = False
        second = await p2_attack(b, title)
        want = ATTACKER_DMG if p2_heads else 0
        out.append((first == want and second == ATTACKER_DMG,
                    f"P2 {'H' if p2_heads else 'T'}: {first} (want {want}), later turn (tails) {second}"))
    return all(o[0] for o in out), ' | '.join(o[1] for o in out)


async def defender_less(test, d, attack, m):
    n = int(m.group(1) or m.group(2))
    guid, title = BASIC_ATTACKER
    spec = CARD_DEFS_BY_GUID[guid]
    a2 = next(x for x in spec.abilities if x.title == title)
    b = board(test, d, attack, opp_spec=spec, prep=lambda b: pay_cost(b.t, b.opp, a2), my_max=BIG)
    if not await do_attack(b):
        return not_offered(d)
    first = await p2_attack(b, title)
    b.t.next_turn()
    second = await p2_attack(b, title)
    want = max(0, ATTACKER_DMG - n)
    return first == want and second == ATTACKER_DMG, f"{first} (want {want}) then {second}"


async def self_switch(test, d, attack, m):
    b = board(test, d, attack)
    if not await do_attack(b):
        return not_offered(d)
    t = b.t
    ok = t.active(P1) is b.my_bench and b.me in t.zone(P1, 'bench') and t.active(P2) is b.opp
    msg = dmg_check(d, b)
    return ok and not msg, f"P1 active is {'bench filler' if t.active(P1) is b.my_bench else 'attacker' if t.active(P1) is b.me else t.active(P1)}{msg}"


async def opp_switch(test, d, attack, m):
    """The opponent picks the new Active."""
    def prep(b):
        b.extra = neutral(b.t.put(test.filler, P2, 'bench'))
    b = board(test, d, attack, prep=prep)
    b.t.pokemon = lambda c, prompt: c[-1]
    if not await do_attack(b):
        return not_offered(d)
    t = b.t
    new = t.active(P2)
    switched = new is not b.opp and b.opp in t.zone(P2, 'bench')
    askers = t.pokemon_askers
    total = (b.before['opp_hp'] - t.hp(b.opp)) + (b.before['opp_bench_hp'] - t.hp(b.opp_bench)) \
        + (BIG - t.hp(b.extra))
    want = plain_damage(attack)
    dmg_ok = want is None or has_ability(d) or total == want
    who_ok = (not askers) or askers[-1] == P2
    hit = 'old active' if dealt(b) else 'new active' if new is not None and t.hp(new) < BIG else 'nobody'
    ok = switched and dmg_ok and who_ok
    return ok, f"switched {switched}, chooser {askers}, damage {total} (printed {want}) on {hit}"


async def gust(test, d, attack, m):
    """P1 picks which Benched Pokémon comes in."""
    def prep(b):
        b.extra = neutral(b.t.put(test.filler, P2, 'bench'))
    b = board(test, d, attack, prep=prep)
    b.t.pokemon = lambda c, prompt: c[-1]
    if not await do_attack(b):
        return not_offered(d)
    t = b.t
    new = t.active(P2)
    switched = new is b.extra and b.opp in t.zone(P2, 'bench')
    askers = t.pokemon_askers
    who_ok = (not askers) or askers[-1] in (P1, None)
    total = (b.before['opp_hp'] - t.hp(b.opp)) + (b.before['opp_bench_hp'] - t.hp(b.opp_bench)) \
        + (BIG - t.hp(b.extra))
    want = plain_damage(attack)
    dmg_ok = want is None or has_ability(d) or total == want
    hit = 'old active' if dealt(b) else 'new active' if t.hp(b.extra) < BIG else 'nobody'
    ok = switched and who_ok and dmg_ok
    return ok, (f"picked bench Pokémon is active: {new is b.extra}, chooser {askers}, "
                f"damage {total} (printed {want}) on {hit}")


async def counters_any(test, d, attack, m):
    n = int(m.group(1))
    bench_only = bool(m.group(2))
    out = []
    for split in (False, True):
        b = board(test, d, attack)
        t = b.t
        if split:
            t.placement = lambda c, cnt: ({c[0].entity_id: cnt - 1, c[-1].entity_id: 1}
                                          if len(c) > 1 and cnt > 1 else {c[0].entity_id: cnt})
        if not await do_attack(b):
            return not_offered(d)
        seen = t.placement_seen[-1] if t.placement_seen else []
        allowed = {b.opp_bench.entity_id} | (set() if bench_only else {b.opp.entity_id})
        cand_ok = set(seen) == allowed
        printed = plain_damage(attack) if not has_ability(d) else None
        opp_total = (b.before['opp_hp'] - t.hp(b.opp)) + (b.before['opp_bench_hp'] - t.hp(b.opp_bench))
        want = n * 10 + (printed or 0)
        mine = (b.before['me_hp'] - t.hp(b.me)) + (b.before['my_bench_hp'] - t.hp(b.my_bench))
        ok = cand_ok and mine == 0 and (printed is None and opp_total >= n * 10 or opp_total == want)
        out.append((ok, f"{'split' if split else 'one'}: candidates ok {cand_ok} ({len(seen)}), "
                        f"opp took {opp_total} (want {want}), mine {mine}"))
    return all(o[0] for o in out), ' | '.join(o[1] for o in out)


OPP = r"(?:your opponent's active|the defending) pokémon"
TYPE_RX = r"(?:grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy)"

CASES = [
    SweepCase('fx_heal_self', r"^heal (\d+) damage from this pokémon\.$", heal_self),
    SweepCase('fx_heal_same',
              rf"^heal from this pokémon the same amount of damage you did to {OPP}\.$", heal_same),
    SweepCase('fx_self_energy_discard',
              rf"^discard (an|a|\d+|all) (?:({TYPE_RX}) )?energy (?:from|attached to) this pokémon\.$",
              self_energy_discard),
    SweepCase('fx_opp_energy_discard',
              rf"^(flip a coin\. if heads, )?discard (?:an|a (special)) energy (?:from|attached to) {OPP}\.$",
              opp_energy_discard),
    SweepCase('fx_mill', r"^discard the top (card|(\d+) cards) of (your opponent's|your) deck\.$", mill),
    SweepCase('fx_random_hand',
              r"^(flip a coin\. if heads, )?(?:discard a random card from your opponent's hand|"
              r"choose a random card from your opponent's hand\. your opponent reveals that card "
              r"and shuffles it into (?:their|his or her) deck)\.$", random_hand),
    SweepCase('fx_self_lock',
              r"^(flip a coin\. if tails, )?during your next turn, this pokémon can't "
              r"(attack|use attacks|use [a-z0-9'é. -]+)\.$", self_lock),
    SweepCase('fx_defender_no_retreat',
              r"^(?:during your opponent's next turn, the defending pokémon can't retreat|"
              r"the defending pokémon can't retreat during your opponent's next turn)\.$",
              defender_no_retreat),
    SweepCase('fx_protect_reduce',
              r"^during your opponent's next turn, (?:this pokémon takes (\d+) less damage from attacks|"
              r"any damage done to this pokémon by attacks is reduced by (\d+)) "
              r"\(after applying weakness and resistance\)\.$", protect_reduce),
    SweepCase('fx_protect_stage',
              r"^(?:during your opponent's next turn, prevent all damage done to this pokémon by attacks "
              r"from (basic|evolution) pokémon|prevent all damage done to this pokémon by attacks from "
              r"(basic|evolution) pokémon during your opponent's next turn)\.$", protect_stage),
    SweepCase('fx_protect_other',
              r"^during your opponent's next turn, prevent all damage done to this pokémon by attacks "
              r"(?:from pokémon vmax|from pokémon that have an ability|if that damage is (?:[1-9]|[1-9]\d|1[0-5]\d) or less)\.$",
              protect_other),
    SweepCase('fx_protect_flip',
              r"^flip a coin\. if heads, (?:during your opponent's next turn, prevent all damage "
              r"(?:from and effects of attacks done to this pokémon|done to this pokémon by attacks)|"
              r"prevent all (?:effects of attacks, including damage,|damage) done to this pokémon"
              r"(?: by attacks)? during your opponent's next turn)\.$", protect_flip),
    SweepCase('fx_defender_flip_attack',
              r"^(?:if the defending pokémon tries to attack during your opponent's next turn, your "
              r"opponent flips a coin|during your opponent's next turn, if the defending pokémon tries "
              r"to attack, your opponent flips a coin)\. if tails, that attack (?:does nothing|doesn't happen)\.$",
              defender_flip_attack),
    SweepCase('fx_defender_less',
              r"^during your opponent's next turn, (?:(?:the defending pokémon's attacks|attacks used by "
              r"the defending pokémon) do (\d+) less damage|any damage done by attacks from the defending "
              r"pokémon is reduced by (\d+)) \(before applying weakness and resistance\)\.$", defender_less),
    SweepCase('fx_self_switch', r"^(?:you may )?switch this pokémon with 1 of your benched pokémon\.$",
              self_switch),
    SweepCase('fx_opp_switch',
              r"^(?:your opponent switches (?:their active pokémon|the defending pokémon|his or her active "
              r"pokémon) with 1 of (?:their|his or her) benched pokémon|switch out your opponent's active "
              r"pokémon to the bench\. \(your opponent chooses the new active pokémon\.)\)?\.?$", opp_switch),
    SweepCase('fx_gust',
              r"^(?:switch in 1 of your opponent's benched pokémon to the active spot|switch 1 of your "
              r"opponent's benched pokémon with (?:their|his or her) active pokémon|switch the defending "
              r"pokémon with 1 of your opponent's benched pokémon|switch 1 of your opponent's benched "
              r"pokémon with the defending pokémon)\.$", gust),
    SweepCase('fx_counters_any',
              r"^put (\d+) damage counters on your opponent's (benched )?pokémon in any way you like\.$",
              counters_any),
]


class SweepEffects(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add
    LIMIT = None
    ONLY = None

    async def test_sweep(self):
        import os
        limit = int(os.environ['SWEEP_LIMIT']) if os.environ.get('SWEEP_LIMIT') else self.LIMIT
        only = os.environ.get('SWEEP_ONLY')
        for case in CASES:
            if only and case.name not in only.split(','):
                continue
            checked, failures, skipped = await run_sweep(self, case, limit=limit)
            print(f"{case.name}: checked {checked}, failures {len(failures)}, skipped {len(skipped)}")


if __name__ == "__main__":
    unittest.main()
