"""Sweep: attacks that READ or REMOVE Special Conditions.

  * "If your opponent's Active Pokémon is Poisoned / Asleep / Confused /
    Burned / affected by a Special Condition, this attack does N more damage"
  * "If this Pokémon is ... , this attack does N more damage"
  * "If your opponent's Active Pokémon isn't Burned (not Asleep...), this
    attack does nothing"
  * "This attack does N (more) damage for each Special Condition affecting
    your opponent's Active Pokémon"
  * "(Heal N damage and) remove all Special Conditions from this Pokémon" /
    "this Pokémon recovers from all Special Conditions"

Every other attack that mentions a condition without giving one is run with
and without conditions and listed (manual) with its results.
Report: /home/claude/bughunt/sweep/status_reads.json
"""
import json
import os
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost, unique_pokemon, norm, label, REPORT_DIR, BIG
from spirit.game.attributes import AttrID
from spirit.game.data_utils import Attack
from spirit.tools.effect_smoke import P1, P2

CW = r"(?:asleep|burned|confused|paralyzed|poisoned)"
GIVES = re.compile(rf"\b(?:is|are) (?:now|also) {CW}")
MENTIONS = re.compile(r"\b(?:burn(?:ed)?|poison(?:ed)?|asleep|paralyz(?:ed|e)|confus(?:ed|ion)|special conditions?)\b")
OPP = r"(?:your opponent's active pokémon|the defending pokémon)"
NAME = {'asleep': 'Asleep', 'burned': 'Burned', 'confused': 'Confused',
        'paralyzed': 'Paralyzed', 'poisoned': 'Poisoned'}


def rules(text):
    """[(kind, data)] understood; None if any condition sentence isn't."""
    out = []
    for s in re.split(r"(?<=\.)\s+", text):
        s = s.strip().rstrip('.')
        if not s or not MENTIONS.search(s):
            continue
        m = re.fullmatch(rf"if {OPP} is ({CW}|affected by a special condition), this attack does (\d+) more damage", s)
        if m:
            out.append(('opp_bonus', (m.group(1), int(m.group(2)))))
            continue
        m = re.fullmatch(rf"if this pokémon is ({CW}|affected by a special condition|burned or poisoned), this attack does (\d+) more damage", s)
        if m:
            out.append(('self_bonus', (m.group(1), int(m.group(2)))))
            continue
        m = re.fullmatch(rf"if {OPP} (?:isn't|is not) ({CW}), this attack does nothing", s)
        if m:
            out.append(('opp_required', m.group(1)))
            continue
        m = re.fullmatch(rf"this attack does (\d+) (more )?damage for each special condition affecting {OPP}", s) \
            or re.fullmatch(rf"does (\d+) (more )?damage for each special condition affecting {OPP}", s)
        if m:
            out.append(('per_condition', (int(m.group(1)), bool(m.group(2)))))
            continue
        if re.fullmatch(r"(?:then, )?(?:heal \d+ damage and )?remove all special conditions from this pokémon", s) \
                or re.fullmatch(r"(?:heal \d+ damage from this pokémon, and it|this pokémon) recovers from all special conditions", s):
            out.append(('self_cure', None))
            continue
        return None
    return out


class SweepStatusReads(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    async def play(self, d, attack, opp_conds=(), self_conds=()):
        t = Table(self)
        t.heads = True
        me = neutral(t.put(d, P1, 'active'))
        neutral(t.put(self.filler, P1, 'bench'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        neutral(t.put(self.filler, P2, 'bench'))
        pay_cost(t, me, attack)
        opp.set_attribute(AttrID.SPECIAL_CONDITIONS, list(opp_conds))
        me.set_attribute(AttrID.SPECIAL_CONDITIONS, list(self_conds))
        me.set_attribute(AttrID.HP, BIG - 50)
        before = (t.hp(me), t.hp(opp))
        entry = t.attack_offer(me, attack.title)
        if entry is None:
            return None
        await t.do(entry)
        live = lambda p: p in t.board.pokemon_in_play(p.owning_player_id)
        return {'dealt': before[1] - (t.hp(opp) if live(opp) else 0),
                'healed': (t.hp(me) if live(me) else 0) - before[0],
                'opp': sorted(t.conditions(opp)) if live(opp) else [],
                'self': sorted(t.conditions(me)) if live(me) else []}

    async def test_sweep(self):
        checked, failures, manual, errors = 0, [], [], []
        for d in unique_pokemon():
            for a in getattr(d, 'abilities', None) or []:
                if not isinstance(a, Attack):
                    continue
                text = norm(a.game_text)
                if not MENTIONS.search(text) or GIVES.search(text):
                    continue
                checked += 1
                found = rules(text)
                has_ability = any(not isinstance(x, Attack) for x in d.abilities)
                entry = {'card': label(d, a), 'text': a.game_text}
                try:
                    if found is None or has_ability or not found:
                        entry['runs'] = {
                            'none': await self.play(d, a),
                            'opp Poisoned+Confused': await self.play(d, a, ['Poisoned', 'Confused']),
                            'opp Asleep+Burned': await self.play(d, a, ['Asleep', 'Burned']),
                            'self Poisoned+Burned': await self.play(d, a, (), ['Poisoned', 'Burned']),
                        }
                        manual.append(entry)
                        continue
                    base = a.damage or 0
                    problems = []
                    plain = await self.play(d, a)
                    if plain is None:
                        problems.append('not offered')
                    for kind, data in found:
                        if kind == 'opp_bonus':
                            word, n = data
                            conds = ['Poisoned'] if word.startswith('affected') else [NAME[word]]
                            got = await self.play(d, a, conds)
                            if plain and plain['dealt'] != base:
                                problems.append(f"no condition: did {plain['dealt']} want {base}")
                            if got and got['dealt'] != base + n:
                                problems.append(f"opp {conds}: did {got['dealt']} want {base + n}")
                            other = 'Burned' if conds != ['Burned'] else 'Poisoned'
                            if not word.startswith('affected'):
                                miss = await self.play(d, a, [other])
                                if miss and miss['dealt'] != base:
                                    problems.append(f"opp {other}: did {miss['dealt']} want {base}")
                        elif kind == 'self_bonus':
                            word, n = data
                            conds = ['Burned'] if word in ('affected by a special condition', 'burned or poisoned') \
                                else [NAME[word]]
                            got = await self.play(d, a, (), conds)
                            if got is None:
                                problems.append(f"self {conds}: not offered")
                            elif got['dealt'] != base + n:
                                problems.append(f"self {conds}: did {got['dealt']} want {base + n}")
                            if plain and plain['dealt'] != base:
                                problems.append(f"no condition: did {plain['dealt']} want {base}")
                        elif kind == 'opp_required':
                            got = await self.play(d, a, [NAME[data]])
                            if plain and plain['dealt'] != 0:
                                problems.append(f"no condition: did {plain['dealt']} want 0")
                            if got and got['dealt'] != base:
                                problems.append(f"opp {NAME[data]}: did {got['dealt']} want {base}")
                        elif kind == 'per_condition':
                            per, more = data
                            got = await self.play(d, a, ['Poisoned', 'Burned', 'Confused'])
                            want = (base if more else 0) + 3 * per
                            if got and got['dealt'] != want:
                                problems.append(f"3 conditions: did {got['dealt']} want {want}")
                            if plain and plain['dealt'] != (base if more else 0):
                                problems.append(f"no condition: did {plain['dealt']} want {base if more else 0}")
                        elif kind == 'self_cure':
                            got = await self.play(d, a, (), ['Poisoned', 'Burned'])
                            if got and got['self']:
                                problems.append(f"self still {got['self']}")
                    if problems:
                        failures.append(dict(entry, problems=problems))
                except Exception as ex:
                    errors.append({'card': label(d, a), 'error': f"{type(ex).__name__}: {ex}"})
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, 'status_reads.json'), 'w') as fh:
            json.dump({'checked': checked, 'failures': failures, 'manual': manual, 'errors': errors},
                      fh, indent=1, ensure_ascii=False)
        print(f"status_reads: checked {checked}, failures {len(failures)}, manual {len(manual)}, "
              f"errors {len(errors)}")
        self.assertEqual([f['card'] for f in failures], [])
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
