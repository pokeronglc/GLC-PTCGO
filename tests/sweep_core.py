"""Whole-database sweep: one checker per common card wording.

A checker is a regex over one attack's normalised text plus a function that
runs that attack on a standard board and says whether the result matches the
text.  `run_sweep` applies a checker to every distinct GLC-legal card whose
attack text matches, and writes a report (JSON) of the mismatches.

    from tests.sweep_core import SweepCase, run_sweep, std_board, norm

Board used by `std_board` (all HP large, no Weakness/Resistance anywhere):
    P1: the card under test Active (cost paid with basic Energy), one filler
        on the Bench.
    P2: filler Active (HP 999), one filler on the Bench (HP 999).
Coins: `heads=True/False` forces every flip. Choices: Table defaults (first
candidates), override via the `prep` hook.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from tests.bughunt_table import Table
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import CARD_DEFS_BY_GUID, PokemonCardDef, Attack
from spirit.tools.effect_smoke import P1, P2

REPORT_DIR = '/home/claude/bughunt/sweep'
BIG = 999


def norm(text):
    return re.sub(r"\s+", " ", (text or "").replace("’", "'").lower()).strip()


_UNIQUE = None


def unique_pokemon():
    """One representative per distinct printed Pokémon (name + attack texts)."""
    global _UNIQUE
    if _UNIQUE is None:
        seen = {}
        for d in CARD_DEFS_BY_GUID.values():
            if not isinstance(d, PokemonCardDef):
                continue
            abil = getattr(d, 'abilities', None) or []
            key = (d.display_name, tuple(getattr(a, 'title', '') for a in abil),
                   tuple(norm(getattr(a, 'game_text', '')) for a in abil),
                   tuple(getattr(a, 'damage', None) for a in abil))
            seen.setdefault(key, d)
        _UNIQUE = sorted(seen.values(), key=lambda d: (d.set_code, d.collector_number))
    return _UNIQUE


def label(d, attack=None):
    return f"{d.display_name} ({d.set_code} {d.collector_number})" + (f" — {attack.title}" if attack else "")


def pay_cost(t, pokemon, attack):
    own = None
    types = pokemon.get_attribute(AttrID.POKEMON_TYPES) or []
    for value in types:
        if value in t.test.energies:
            own = PokemonTypes(value)
            break
    for kind, count in (attack.cost or {}).items():
        kind = PokemonTypes(kind) if not isinstance(kind, PokemonTypes) else kind
        if kind == PokemonTypes.COLORLESS or kind.value not in t.test.energies:
            kind = own or PokemonTypes.WATER
        t.energy(pokemon, kind, count)


def neutral(p, hp=BIG):
    p.set_attribute(AttrID.WEAKNESS_TYPES, [])
    p.set_attribute(AttrID.RESISTANCE_TYPES, [])
    if hp is not None:
        p.set_attribute(AttrID.HP, hp)
    return p


@dataclass
class Board:
    t: Table
    me: object
    opp: object
    my_bench: object
    opp_bench: object
    attack: Attack
    before: dict = field(default_factory=dict)


def std_board(test, d, attack, *, heads=True, my_hp=None, prep=None):
    t = Table(test)
    t.heads = heads
    me = t.put(d, P1, 'active')
    if my_hp is not None:
        me.set_attribute(AttrID.HP, my_hp)
    my_bench = neutral(t.put(test.filler, P1, 'bench'))
    opp = neutral(t.put(test.filler, P2, 'active'))
    opp_bench = neutral(t.put(test.filler, P2, 'bench'))
    pay_cost(t, me, attack)
    b = Board(t, me, opp, my_bench, opp_bench, attack)
    if prep is not None:
        prep(b)
    b.before = snapshot(b)
    return b


def snapshot(b):
    t = b.t
    return {
        'me_hp': t.hp(b.me), 'opp_hp': t.hp(b.opp),
        'my_bench_hp': t.hp(b.my_bench), 'opp_bench_hp': t.hp(b.opp_bench),
        'my_hand': len(t.zone(P1, 'hand')), 'opp_hand': len(t.zone(P2, 'hand')),
        'my_deck': len(t.zone(P1, 'deck')), 'opp_deck': len(t.zone(P2, 'deck')),
        'my_discard': len(t.zone(P1, 'discard')), 'opp_discard': len(t.zone(P2, 'discard')),
        'my_energy': len(t.board.attached_energies(b.me)),
        'opp_energy': len(t.board.attached_energies(b.opp)),
        'my_bench_n': len(t.zone(P1, 'bench')), 'opp_bench_n': len(t.zone(P2, 'bench')),
    }


async def do_attack(b):
    """Returns False if the attack isn't offered."""
    entry = b.t.attack_offer(b.me, b.attack.title)
    if entry is None:
        return False
    await b.t.do(entry)
    return True


def dealt(b, who='opp'):
    """Damage done to a Pokémon still in play (KO'd → its whole HP)."""
    t = b.t
    p = {'opp': b.opp, 'me': b.me, 'my_bench': b.my_bench, 'opp_bench': b.opp_bench}[who]
    key = {'opp': 'opp_hp', 'me': 'me_hp', 'my_bench': 'my_bench_hp', 'opp_bench': 'opp_bench_hp'}[who]
    in_play = p in t.board.pokemon_in_play(p.owning_player_id)
    return (b.before[key] - t.hp(p)) if in_play else b.before[key]


@dataclass
class SweepCase:
    name: str
    pattern: str                       # regex over the normalised attack text (search)
    check: Callable                    # async (test, d, attack, match) -> (ok: bool|None, detail: str)
    attack_only: bool = True           # match Attack texts (False: Abilities)


async def run_sweep(test, case: SweepCase, limit: Optional[int] = None):
    """Run a checker over every matching card. Returns (checked, failures, skipped)."""
    os.makedirs(REPORT_DIR, exist_ok=True)
    rx = re.compile(case.pattern)
    checked, failures, skipped = 0, [], []
    for d in unique_pokemon():
        for a in getattr(d, 'abilities', None) or []:
            if case.attack_only and not isinstance(a, Attack):
                continue
            if not case.attack_only and isinstance(a, Attack):
                continue
            m = rx.search(norm(getattr(a, 'game_text', '')))
            if not m:
                continue
            if limit is not None and checked >= limit:
                break
            checked += 1
            try:
                ok, detail = await case.check(test, d, a, m)
            except Exception as ex:          # a crash is a finding too
                ok, detail = False, f"ERROR {type(ex).__name__}: {ex}"
            if ok is None:
                skipped.append({'card': label(d, a), 'why': detail})
            elif not ok:
                failures.append({'card': label(d, a), 'guid': d.guid, 'text': a.game_text,
                                 'detail': detail})
    with open(os.path.join(REPORT_DIR, f"{case.name}.json"), 'w') as fh:
        json.dump({'case': case.name, 'checked': checked, 'failures': failures,
                   'skipped': skipped}, fh, indent=1, ensure_ascii=False)
    return checked, failures, skipped
