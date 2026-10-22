"""Sweep: every coin-flip attack NOT covered by test_sweep_coins /
test_sweep_coin_tails -- "if tails" wordings, 2+ coins, flip-until-tails with
non-damage effects, and "flip a coin for each ...".

Each attack is run with chosen coin results (all heads, all tails, one heads
then tails, ...).  Its text is split into sentences; each sentence that a rule
below recognises adds an expectation for that number of heads (damage done,
Special Conditions, Energy discarded, cards drawn/milled, self damage, Knock
Out).  Any measured change no rule explains is also a failure.  Sentences no
rule recognises put the attack on the "manual" list with its measured results
so a person can read them.

Report: /home/claude/bughunt/sweep/coin_rest.json
"""
import json
import os
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests import test_sweep_coins as sc
from tests.test_sweep_coin_tails import PATTERN as HEADS_ONLY
from tests.sweep_core import (std_board, do_attack, neutral, unique_pokemon, norm, label,
                              REPORT_DIR, BIG)
from spirit.game.attributes import AttrID, PokemonTypes
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

COVERED = [re.compile(c.pattern) for c in sc.CASES]
COND = {'asleep': 'Asleep', 'burned': 'Burned', 'confused': 'Confused',
        'paralyzed': 'Paralyzed', 'poisoned': 'Poisoned'}
OPP = r"(?:your opponent's active pokémon|the defending pokémon|that pokémon)"
SELF = r"(?:this pokémon)"
NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3}
ME_DAMAGE = 60           # damage on the attacker before it attacks (heal checks)
OPP_ENERGY = 3


def in_scope(text):
    t = text
    if 'flip' not in t or 'coin' not in t:
        return False
    if any(r.search(t) for r in COVERED) or HEADS_ONLY.match(t):
        return False
    # Coins flipped by the opponent next turn / during Checkup: other sweep.
    if re.search(r"your opponent flips|they flip a coin|whenever your opponent flips|"
                 r"they flip|treat it as tails|between turns|during pokémon checkup, (?:your opponent )?flip"
                 r"|instead of \d+ for this pokémon", t):
        return False
    return True


def coin_count(text):
    m = re.search(r"flip (\d+) coins", text)
    return int(m.group(1)) if m else 1


# --------------------------------------------------------------- conditions
def gate(prefix, H, n, first_tails):
    """Does a sentence's leading condition hold?  None: not a coin gate."""
    p = prefix.strip()
    if p == '':
        return True
    table = {
        'if heads': H >= 1 and n == 1, 'if head': H >= 1 and n == 1,
        'if tails': H == 0 and n == 1,
        'if both of them are heads': H == n, 'if all of them are heads': H == n,
        'if both of them are tails': H == 0, 'if all of them are tails': H == 0,
        'if either of them is heads': H >= 1, 'if any of them are heads': H >= 1,
        'if either of them is tails': H < n,
        'if the first flip is tails': first_tails,
    }
    if p in table:
        return table[p]
    m = re.fullmatch(r"if at least (\d+) of them are heads", p)
    if m:
        return H >= int(m.group(1))
    m = re.fullmatch(r"if (\d+) of them (?:is|are) heads", p)
    if m:
        return H == int(m.group(1))
    return None


PREFIX = (r"(?P<prefix>(?:if (?:heads|head|tails|both of them are (?:heads|tails)|all of them are (?:heads|tails)"
          r"|either of them is (?:heads|tails)|any of them are heads|at least \d+ of them are heads"
          r"|\d+ of them (?:is|are) heads|the first flip is tails), )?)")


def expect_sentence(s, H, n, first_tails, base, exp):
    """Add this sentence's expectation to `exp` for H heads.  Returns False if
    the sentence isn't recognised."""
    if re.fullmatch(r"flip (?:a coin|\d+ coins)(?: until you get tails)?", s) \
            or re.fullmatch(r"flip a coin for each .+", s) and 'damage' not in s:
        return True
    m = re.fullmatch(PREFIX + r"(?P<body>.+)", s)
    prefix, body = m.group('prefix').rstrip(', '), m.group('body')
    ok = gate(prefix, H, n, first_tails)
    if ok is None:
        return False

    def nothing():
        exp['nothing'] = True

    # ---- damage to the opponent's Active
    r = re.fullmatch(r"this attack does (\d+) (more )?damage(?: for each heads| times the number of heads)"
                     r"( to each of your opponent's pokémon)?(?:\. \(don't apply weakness and resistance for benched pokémon\))?",
                     body) or re.fullmatch(r"this attack does (\d+) (more )?(?:damage )?times the number of heads()", body)
    if r and prefix == '':
        per, more, each = int(r.group(1)), r.group(2), r.group(3)
        exp['opp_dmg'] = (base if more else 0) + per * H
        if each:
            exp['opp_bench_dmg'] = per * H
        return True
    r = re.fullmatch(r"this attack does (\d+) more damage", body)
    if r:
        if ok:
            exp['opp_dmg'] = exp.get('opp_dmg_tier', base) + int(r.group(1))
            exp['opp_dmg_tier'] = exp['opp_dmg']
        return True
    r = re.fullmatch(r"this attack does (\d+) damage", body)
    if r:
        if ok:
            exp['opp_dmg'] = int(r.group(1))
        return True
    r = re.fullmatch(r"this attack does (\d+) damage to your opponent's active pokémon", body)
    if r:
        exp['opp_dmg'] = int(r.group(1)) if ok else exp.get('opp_dmg', 0)
        return True
    if body in ("this attack does nothing", "that attack does nothing"):
        if ok:
            nothing()
        return True
    if body == "you lose this game":
        return True                    # all tails only; never forced here
    # ---- Special Conditions
    r = re.fullmatch(OPP + r" is (?:now|also) (\w+)(?: and (\w+))?", body)
    if r and r.group(1) in COND:
        if ok:
            exp.setdefault('opp_conds', set()).update(COND[w] for w in r.groups() if w)
        return True
    r = re.fullmatch(SELF + r" is now (\w+)", body)
    if r and r.group(1) in COND:
        if ok:
            exp.setdefault('my_conds', set()).add(COND[r.group(1)])
        return True
    if re.fullmatch(r"choose a special condition\. " + OPP + r" is now affected by that special condition", body):
        if ok:
            exp['opp_conds_any'] = True
        return True
    # ---- Knock Out
    if re.fullmatch(OPP + r" is knocked out", body) or body == "knock out 1 of your opponent's pokémon":
        exp['opp_ko'] = bool(ok)
        return True
    # ---- self damage
    r = re.fullmatch(SELF + r" (?:also )?does (\d+) damage to itself", body)
    if r:
        if ok:
            exp['me_dmg'] = exp.get('me_dmg', 0) + int(r.group(1))
        return True
    # ---- Energy
    r = re.fullmatch(r"for each heads, discard an energy (?:attached to|from) " + OPP, body)
    if r:
        exp['opp_energy'] = -min(H, OPP_ENERGY)
        return True
    r = re.fullmatch(r"for each tails, discard an energy from " + SELF, body)
    if r:
        exp['my_energy'] = -(n - H)
        return True
    r = re.fullmatch(r"discard (an|a|\d+|all) (?:(\w+) )?energy (?:attached to|from) " + OPP, body)
    if r:
        if ok:
            exp['opp_energy'] = -OPP_ENERGY if r.group(1) == 'all' else -NUM.get(r.group(1), int(r.group(1)) if r.group(1).isdigit() else 1)
        return True
    if re.fullmatch(r"discard all energy attached to " + OPP, body):
        if ok:
            exp['opp_energy'] = -OPP_ENERGY
        return True
    r = re.fullmatch(r"discard (an|a|\d+|all) (?:(\w+) )?energy (?:card )?(?:attached to|from) " + SELF, body) \
        or re.fullmatch(r"discard (a) (fire) energy and a psychic energy from " + SELF, body)
    if r:
        if ok:
            exp['my_energy_lost'] = 'all' if r.group(1) == 'all' else (
                2 if 'and a psychic' in body else NUM.get(r.group(1)) or int(r.group(1)))
        return True
    # ---- cards
    r = re.fullmatch(r"for each heads, discard the top (?:card|(\d+) cards) of your opponent's deck", body) \
        or re.fullmatch(r"for each heads, discard (\d+) cards from the top of your opponent's deck", body)
    if r:
        exp['opp_deck'] = -H * int(r.group(1) or 1)
        return True
    if body == "for each heads, draw a card":
        exp['my_hand'] = H
        return True
    r = re.fullmatch(r"for each heads, heal (\d+) damage from " + SELF, body)
    if r:
        exp['me_dmg'] = -min(ME_DAMAGE, int(r.group(1)) * H)
        return True
    if re.fullmatch(r"for each heads, (?:choose a random card|discard a random card) from your opponent's hand.*", body):
        exp['opp_hand'] = -H
        return True
    if body == "for each heads, put a card from your discard pile into your hand":
        exp['my_hand'] = H
        return True
    return False


# ------------------------------------------------------------------ running
def _prep(b):
    t = b.t
    neutral(b.me, hp=None)
    b.me.set_attribute(AttrID.HP, BIG)
    b.me.attribute_originals[AttrID.HP.value] = BIG + ME_DAMAGE
    t.energy(b.opp, PokemonTypes.WATER, OPP_ENERGY)
    for _ in range(4):
        t.put(t.test.item, P2, 'hand')
    for kind in (PokemonTypes.FIRE, PokemonTypes.WATER, PokemonTypes.LIGHTNING):
        t.put(t.basic_energy(kind), P1, 'discard')
    for _ in range(3):
        t.put(t.test.item, P1, 'discard')


def measure(b):
    t = b.t
    def hp(p):
        return t.hp(p) if p in t.board.pokemon_in_play(p.owning_player_id) else 0
    return {
        'opp_dmg': b.before['opp_hp'] - hp(b.opp),
        'opp_bench_dmg': b.before['opp_bench_hp'] - hp(b.opp_bench),
        'me_dmg': b.before['me_hp'] - hp(b.me),
        'my_bench_dmg': b.before['my_bench_hp'] - hp(b.my_bench),
        'opp_ko': b.opp not in t.board.pokemon_in_play(P2),
        'opp_conds': set(t.conditions(b.opp)) if b.opp in t.board.pokemon_in_play(P2) else set(),
        'my_conds': set(t.conditions(b.me)),
        'opp_energy': len(t.board.attached_energies(b.opp)) - b.before['opp_energy'],
        'my_energy': len(t.board.attached_energies(b.me)) - b.before['my_energy'],
        'my_hand': len(t.zone(P1, 'hand')) - b.before['my_hand'],
        'opp_hand': len(t.zone(P2, 'hand')) - b.before['opp_hand'],
        'opp_deck': len(t.zone(P2, 'deck')) - b.before['opp_deck'],
        'my_deck': len(t.zone(P1, 'deck')) - b.before['my_deck'],
    }


async def run(test, d, attack, seq=None, until=None):
    b = std_board(test, d, attack, heads=True, my_hp=BIG, prep=_prep)
    if seq is not None:
        b.t.heads = sc.coins(seq)
    if until is not None:
        b.t.heads = sc.coins([True] * until)

        async def fixed(self, title=''):
            return until
        with patch.object(EffectContext, 'flip_until_tails', fixed):
            offered = await do_attack(b)
    else:
        offered = await do_attack(b)
    energy_before = b.before['my_energy']
    return (measure(b) if offered else None), energy_before


def scenarios(text):
    if 'until you get tails' in text:
        return [('0H', dict(until=0), 0, 1, True), ('2H', dict(until=2), 2, 3, False)]
    if text.startswith('flip a coin for each') or 'flip a coin for each' in text:
        return [('allH', dict(seq=[True] * 20), None, None, False),
                ('allT', dict(seq=[False] * 20), 0, None, True)]
    n = coin_count(text)
    out = [('allH', dict(seq=[True] * n), n, n, False), ('allT', dict(seq=[False] * n), 0, n, True)]
    if n >= 2:
        out.append(('1H', dict(seq=[True] + [False] * (n - 1)), 1, n, False))
    if n >= 3:
        out.append(('2H', dict(seq=[True, True] + [False] * (n - 2)), 2, n, False))
    return out


def sentences(text):
    text = re.sub(r"\(don't apply weakness and resistance for benched pokémon\.\)", "", text)
    text = text.replace("this attack's damage isn't affected by weakness or resistance.", "")
    return [s.strip() for s in re.split(r"(?<=\.)\s+", text) if s.strip().strip('.')]


def per_thing_heads(text, b_energy):
    m = re.search(r"flip a coin for each (?:(\w+) )?energy attached to this pokémon", text)
    if m and m.group(1) is None:          # typed counts depend on how the cost was paid
        return b_energy
    return None


def evaluate(text, base, H, n, first_tails, got, my_energy_before):
    exp, unknown = {}, []
    for s in sentences(text):
        if not expect_sentence(s.rstrip('.'), H, n, first_tails, base, exp):
            unknown.append(s)
    if unknown:
        return None, unknown
    want = {'opp_dmg': base, 'opp_bench_dmg': 0, 'me_dmg': 0, 'my_bench_dmg': 0, 'opp_ko': False,
            'opp_conds': set(), 'my_conds': set(), 'opp_energy': 0, 'my_energy': 0, 'opp_hand': 0,
            'my_hand': 0, 'opp_deck': 0}
    if exp.get('nothing'):
        exp = {}
        want['opp_dmg'] = 0
    for k, v in exp.items():
        if k in want:
            want[k] = v
    if 'my_energy_lost' in exp:
        want['my_energy'] = -my_energy_before if exp['my_energy_lost'] == 'all' else -exp['my_energy_lost']
    if exp.get('opp_ko'):
        want['opp_dmg'], want['opp_conds'], want['opp_energy'] = None, None, None
    bad = []
    for k, v in want.items():
        if v is None:
            continue
        g = got[k]
        if k == 'opp_conds' and exp.get('opp_conds_any'):
            if (H >= 1) != bool(g):
                bad.append(f"opp_conds {sorted(g)}")
            continue
        if k == 'my_hand' and 'my_hand' not in exp:
            continue                      # draws/searches checked only when stated
        if k == 'my_energy' and 'my_energy' not in exp and 'my_energy_lost' not in exp:
            if g != 0:
                bad.append(f"my_energy {g} want 0")
            continue
        if k == 'opp_deck' and 'opp_deck' not in exp:
            continue
        if isinstance(v, set):
            if g != v:
                bad.append(f"{k} {sorted(g)} want {sorted(v)}")
        elif g != v:
            bad.append(f"{k} {g} want {v}")
    return bad, []


class SweepCoinRest(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def test_sweep(self):
        checked, failures, manual, errors = 0, [], [], []
        for d in unique_pokemon():
            for a in getattr(d, 'abilities', None) or []:
                if not isinstance(a, Attack):
                    continue
                text = norm(a.game_text)
                if not in_scope(text):
                    continue
                if any(not isinstance(x, Attack) for x in d.abilities):
                    continue              # an Ability could change the numbers
                checked += 1
                base = a.damage or 0
                runs, problems, unknown = {}, [], []
                try:
                    for name, kw, H, n, first_tails in scenarios(text):
                        got, energy_before = await run(self, d, a, **kw)
                        if got is None:
                            problems.append(f"{name}: attack not offered")
                            break
                        runs[name] = {k: (sorted(v) if isinstance(v, set) else v) for k, v in got.items()
                                      if v not in (0, False, set())}
                        if H is None:
                            H = per_thing_heads(text, energy_before)
                        if H is None:
                            unknown = ['coin count']
                            continue
                        bad, unk = evaluate(text, base, H, n or H, first_tails, got, energy_before)
                        if unk:
                            unknown = unk
                        elif bad:
                            problems.append(f"{name}: " + "; ".join(bad))
                except Exception as ex:
                    errors.append({'card': label(d, a), 'error': f"{type(ex).__name__}: {ex}"})
                    continue
                entry = {'card': label(d, a), 'damage': base, 'text': a.game_text, 'runs': runs}
                if problems:
                    failures.append(dict(entry, problems=problems))
                elif unknown:
                    manual.append(dict(entry, unrecognised=unknown))
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, 'coin_rest.json'), 'w') as fh:
            json.dump({'checked': checked, 'failures': failures, 'manual': manual, 'errors': errors},
                      fh, indent=1, ensure_ascii=False)
        print(f"coin_rest: checked {checked}, failures {len(failures)}, manual {len(manual)}, "
              f"errors {len(errors)}")
        self.assertEqual([f['card'] for f in failures], [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
