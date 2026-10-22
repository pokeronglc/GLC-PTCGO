"""Sweep: every attack that GIVES a Special Condition (Burned, Poisoned,
Asleep, Paralyzed, Confused).

For each attack whose text says "<someone> is now <condition(s)>", the text
is split into sentences.  A sentence like
    [coin gate,] <subject> is/are now X[, Y][ and Z]
is understood when the gate is a coin result (or none) and the subject is the
opponent's Active ("the Defending Pokémon", "your opponent's Active Pokémon",
"that Pokémon"), the attacker ("this Pokémon"), "both Active Pokémon" or the
switched-in "new Active Pokémon".  The attack is run for every coin outcome
that matters and the Special Conditions on the opponent's Active and on the
attacker must be exactly the expected ones.

Poison strength ("put 2 damage counters instead of 1") and Burn strength are
checked by running Pokémon Checkup afterwards.

Attacks with any condition sentence not understood (e.g. "if the Defending
Pokémon is a Basic Pokémon, it is now Paralyzed") go on the manual list
with their measured results.

Report: audits/results/sweep/status_inflict.json
"""
import json
import os
import re
import unittest
from unittest.mock import patch

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests import test_sweep_coins as sc
from tests.test_sweep_coin_rest import gate, coin_count
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost, unique_pokemon, norm, label, REPORT_DIR, BIG
from spirit.game.attributes import AttrID
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext
from spirit.tools.effect_smoke import P1, P2

COND = {'asleep': 'Asleep', 'burned': 'Burned', 'confused': 'Confused',
        'paralyzed': 'Paralyzed', 'poisoned': 'Poisoned'}
CW = r"(?:asleep|burned|confused|paralyzed|poisoned)"
CLIST = rf"({CW}(?:(?:,? and |, |,? or ){CW})*)"
SUBJECTS = {
    'opp': r"(?:the defending pokémon|your opponent's active pokémon|that pokémon|it)",
    'self': r"(?:this pokémon)",
    'both': r"(?:both active pokémon)",
    'new': r"(?:the new active pokémon|the new defending pokémon)",
}
PREFIX = (r"(?P<prefix>(?:if (?:heads|tails|both of them are (?:heads|tails)|all of them are (?:heads|tails)"
          r"|either of them is (?:heads|tails)|any of them are heads|at least \d+ of them are heads"
          r"|\d+ of them (?:is|are) heads|the first flip is tails), )?)")
MENTION = re.compile(rf"\b(?:is|are) (?:now|also) {CW}")


def sentences(text):
    text = re.sub(r"\([^)]*\)", "", text)
    return [s.strip().rstrip('.') for s in re.split(r"(?<=\.)\s+", text) if s.strip().strip('.')]


def parse(text):
    """[(gate_prefix, who, {conditions})] for understood sentences, and a
    list of condition sentences not understood."""
    found, unknown = [], []
    for s in sentences(text):
        if not MENTION.search(s):
            continue
        hit = None
        for who, subj in SUBJECTS.items():
            m = re.fullmatch(PREFIX + rf"(?:and )?{subj} (?:is|are) (?:now|also) {CLIST}", s)
            if m:
                hit = (m.group('prefix').rstrip(', '), who, {COND[w] for w in re.findall(CW, m.group(2))})
                break
        # "Flip a coin. If heads, the Defending Pokémon is now X; if tails, Y" variants
        # and leading "flip a coin" inside the sentence are not split here.
        if hit is None or ' or ' in s:
            unknown.append(s)
        else:
            found.append(hit)
    return found, unknown


def scenarios(text):
    if 'until you get tails' in text:
        return [('0H', dict(until=0), 0, 1, True), ('2H', dict(until=2), 2, 3, False)]
    if 'flip a coin for each' in text:
        return None
    n = coin_count(text)
    if 'flip' not in text:
        return [('-', dict(seq=[True] * 8), 1, 1, False)]
    out = [('allH', dict(seq=[True] * n), n, n, False), ('allT', dict(seq=[False] * n), 0, n, True)]
    if n >= 2:
        out.append(('1H', dict(seq=[True] + [False] * (n - 1)), 1, n, False))
    return out


class SweepStatus(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def run_attack(self, d, attack, seq=None, until=None):
        t = Table(self)
        me = neutral(t.put(d, P1, 'active'))
        neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        neutral(t.put(self.filler, P2, 'bench'))
        pay_cost(t, me, attack)
        t.heads = sc.coins(seq or [])
        if until is not None:
            async def fixed(_self, title=''):
                return until
            with patch.object(EffectContext, 'flip_until_tails', fixed):
                entry = t.attack_offer(me, attack.title)
                if entry is None:
                    return None
                await t.do(entry)
        else:
            entry = t.attack_offer(me, attack.title)
            if entry is None:
                return None
            await t.do(entry)
        active = t.active(P2)
        got = {
            'opp': set(t.conditions(active)) if active is not None else set(),
            'orig_opp': set(t.conditions(opp)) if opp in t.board.pokemon_in_play(P2) else set(),
            'self': set(t.conditions(me)) if me in t.board.pokemon_in_play(P1) else set(),
            'switched': active is not opp,
        }
        # Checkup strength: damage the opponent's Active takes from Poison/Burn.
        got['checkup'] = None
        if active is not None and got['opp'] & {'Poisoned', 'Burned'}:
            t.heads = False          # Burn stays (tails); Poison has no flip
            before = t.hp(active)
            try:
                await t.checkup()
            except Exception:
                pass
            got['checkup'] = before - (t.hp(active) if active in t.board.pokemon_in_play(P2) else 0)
        return got

    async def test_sweep(self):
        checked, failures, manual, errors = 0, [], [], []
        for d in unique_pokemon():
            for a in getattr(d, 'abilities', None) or []:
                if not isinstance(a, Attack):
                    continue
                text = norm(a.game_text)
                if not MENTION.search(text):
                    continue
                found, unknown = parse(text)
                if not found and not unknown:
                    continue
                plan = scenarios(text)
                checked += 1
                entry = {'card': label(d, a), 'text': a.game_text}
                if "you can use this attack only if" in text:
                    unknown = unknown + ['attack requirement']
                if plan is None or unknown or any(not isinstance(x, Attack) for x in d.abilities):
                    entry['unrecognised'] = unknown or ['coin count / Ability']
                    entry['runs'] = {}
                    try:
                        for name, kw, *_ in (plan or [('allH', dict(seq=[True] * 20), 0, 0, 0),
                                                      ('allT', dict(seq=[False] * 20), 0, 0, 0)]):
                            got = await self.run_attack(d, a, **kw)
                            entry['runs'][name] = None if got is None else {
                                k: sorted(v) if isinstance(v, set) else v for k, v in got.items()
                                if v not in (None, False, set())}
                    except Exception as ex:
                        entry['runs']['error'] = f"{type(ex).__name__}: {ex}"
                    manual.append(entry)
                    continue
                problems, runs = [], {}
                try:
                    for name, kw, H, n, first_tails in plan:
                        got = await self.run_attack(d, a, **kw)
                        if got is None:
                            problems.append(f"{name}: attack not offered")
                            break
                        runs[name] = {k: sorted(v) if isinstance(v, set) else v for k, v in got.items()}
                        want = {'opp': set(), 'self': set()}
                        bad_gate = False
                        for prefix, who, conds in found:
                            ok = gate(prefix, H, n, first_tails)
                            if ok is None:
                                bad_gate = True
                                continue
                            if not ok:
                                continue
                            if who == 'opp' or (who == 'new' and got['switched']):
                                want['opp'] |= conds
                            elif who == 'self':
                                want['self'] |= conds
                            elif who == 'both':
                                want['opp'] |= conds
                                want['self'] |= conds
                        if bad_gate:
                            problems.append("gate?")
                            break
                        # Only one of Asleep / Confused / Paralyzed can stand.
                        for side in ('opp', 'self'):
                            rot = [c for c in ('Asleep', 'Confused', 'Paralyzed') if c in want[side]]
                            if len(rot) > 1:
                                want[side] -= set(rot[:-1])
                        if got['opp'] != want['opp']:
                            problems.append(f"{name}: opponent {sorted(got['opp'])} want {sorted(want['opp'])}")
                        if got['self'] != want['self']:
                            problems.append(f"{name}: attacker {sorted(got['self'])} want {sorted(want['self'])}")
                        if got['checkup'] is not None and not re.search(
                                r"if [^.]*, put \d+ damage counters", text):
                            pc = re.search(r"put (\d+) damage counters (?:on that pokémon )?instead of 1", text)
                            bc = re.search(r"put (\d+) damage counters (?:on that pokémon )?instead of 2", text)
                            expect = 0
                            if 'Poisoned' in got['opp']:
                                expect += 10 * (int(pc.group(1)) if pc else 1)
                            if 'Burned' in got['opp']:
                                expect += 10 * (int(bc.group(1)) if bc else 2)
                            if got['checkup'] != expect:
                                problems.append(f"{name}: checkup damage {got['checkup']} want {expect}")
                except Exception as ex:
                    errors.append({'card': label(d, a), 'error': f"{type(ex).__name__}: {ex}"})
                    continue
                if problems:
                    failures.append(dict(entry, problems=problems, runs=runs))
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, 'status_inflict.json'), 'w') as fh:
            json.dump({'checked': checked, 'failures': failures, 'manual': manual, 'errors': errors},
                      fh, indent=1, ensure_ascii=False)
        print(f"status_inflict: checked {checked}, failures {len(failures)}, manual {len(manual)}, "
              f"errors {len(errors)}")
        self.assertEqual([f['card'] for f in failures], [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
