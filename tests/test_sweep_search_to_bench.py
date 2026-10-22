"""Sweep: every GLC attack that searches the deck for Pokémon and puts them
onto the Bench ("Call for Family" and friends) benches the printed number.

Player report (Oct 12): Gossifleur SWSH1 20 Call for Family ("up to 3")
only benched 1.  Every PRINTING is run (reprints may have their own script):
P1's Active is the attacker with its cost paid, the Bench is empty, and the
deck holds 6 Pokémon that satisfy the text (right type / stage / name) plus
filler Items.  The chooser always takes the maximum it is offered, coins are
heads; the number benched must equal the printed number (capped by the 5
free Bench spaces).

Report: audits/results/sweep/search_to_bench.json
"""
import json
import os
import re
import unittest

from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from tests.bughunt_table import Table
from tests.sweep_core import neutral, pay_cost, norm, REPORT_DIR, BIG
from spirit.game import glc
from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage
from spirit.game.data_utils import CARD_DEFS_BY_GUID, PokemonCardDef, Attack
from spirit.tools.effect_smoke import P1, P2

NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}
TYPES = ['grass', 'fire', 'water', 'lightning', 'psychic', 'fighting',
         'darkness', 'metal', 'fairy', 'dragon', 'colorless']
SEARCH = re.compile(r"search your deck for (?P<what>.*?pok[ée]mon\b.*?) and (?:put|place)s? "
                    r"(?:it|them|those pok[ée]mon|that pok[ée]mon) onto your bench")
SPACE = 5


def _attr(d, attr):
    spec = (d.extra_attributes or {}).get(str(attr.value))
    return spec.get('value') if isinstance(spec, dict) else None


def _stage(d):
    v = _attr(d, AttrID.STAGE)
    return PokemonStage(v) if v is not None else None


def _types(d):
    return {PokemonTypes(v).name.lower() for v in json.loads(_attr(d, AttrID.POKEMON_TYPES) or '[]')}


def wanted(text):
    """(expected count or callable, predicate over a deck def) or None."""
    m = SEARCH.search(text)
    if not m:
        return None
    what = m.group('what')
    if 'any number of' in what:
        count = SPACE
    elif 'number of' in what or 'for each' in text.split('search your deck')[0]:
        count = None                                  # resolved per case below
    else:
        n = re.match(r"(?:up to )?(\w+)", what).group(1)
        count = NUM.get(n, int(n) if n.isdigit() else 1)
    what_l = what
    def pred(d):
        if 'basic' in what_l and _stage(d) != PokemonStage.BASIC:
            return False
        if 'stage 1' in what_l and _stage(d) != PokemonStage.STAGE1:
            return False
        if 'stage 2' in what_l and _stage(d) != PokemonStage.STAGE2:
            return False
        for ty in TYPES:
            if re.search(rf"\b{ty}\b", what_l) and ty not in _types(d):
                return False
        name = d.display_name or ''
        for tag in ("team magma", "rapid strike", "lillie's", "steven's"):
            if tag in what_l:
                hay = (name + ' ' + ' '.join(getattr(d, 'subtypes', None) or [])
                       + ' ' + ' '.join(getattr(d, 'searchable_by', None) or [])).lower().replace('’', "'")
                if tag.replace("'s", '') not in hay:
                    return False
        if 'rotom' in what_l and 'rotom' not in name.lower():
            return False
        if 'except' in what_l:
            ex = re.search(r"except (\w+)", what_l).group(1)
            if ex.lower() in name.lower():
                return False
        lowered = (name + ' ' + ' '.join(getattr(d, 'subtypes', None) or [])).lower()
        if re.search(r"\b(ex|gx|v|vmax|vstar|prism|break|tag team)\b", lowered):
            return False                              # keep to plain Pokémon
        return True
    return count, pred, what


def cases():
    out = []
    for d in sorted(CARD_DEFS_BY_GUID.values(), key=lambda d: (d.set_code, str(d.collector_number))):
        if not isinstance(d, PokemonCardDef) or not glc.is_glc_legal(d):
            continue
        for a in d.abilities or []:
            if isinstance(a, Attack) and wanted(norm(a.game_text)):
                out.append((d, a))
    return out


class SweepSearchToBench(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    add = meta.GlcMetaCardTests.add

    def deck_cards(self, pred, text):
        pool = [d for d in sorted(CARD_DEFS_BY_GUID.values(),
                                  key=lambda d: (d.set_code, str(d.collector_number)))
                if isinstance(d, PokemonCardDef) and glc.is_glc_legal(d) and pred(d)]
        if 'different types' in text:
            seen, picked = set(), []
            for d in pool:
                ty = frozenset(_types(d))
                if len(ty) == 1 and ty not in seen:
                    seen.add(ty)
                    picked.append(d)
            return picked[:6]
        # distinct names so "different names" style limits don't bite
        seen, picked = set(), []
        for d in pool:
            if d.display_name not in seen:
                seen.add(d.display_name)
                picked.append(d)
        return picked[:6]

    async def run_case(self, d, a):
        text = norm(a.game_text)
        count, pred, what = wanted(text)
        t = Table(self)
        t.heads = True
        me = neutral(t.put(d, P1, 'active'))
        opp = neutral(t.put(self.filler, P2, 'active'))
        neutral(t.put(self.filler, P2, 'bench'))
        pay_cost(t, me, a)
        if 'for each energy attached' in text:
            count = len(t.attached(me))
        elif "opponent's benched" in what:
            count = 1
        elif 'up to the number of heads' in what:
            count = 2
        if count is None:
            return {'fail': f'unhandled count: {what}'}
        count = min(count, SPACE)
        deck = self.deck_cards(pred, text)
        if len(deck) < count:
            return {'skip': f'only {len(deck)} legal deck targets'}
        t.deck(P1, deck)
        t.state.turn_number = 3
        offer = t.attack_offer(me, a.title)
        if offer is None:
            return {'fail': 'attack not offered'}
        try:
            await t.attack(me, a.title)
        except Exception as exc:                       # pragma: no cover - report
            return {'fail': f'crash: {type(exc).__name__}: {exc}'}
        benched = len(t.zone(P1, 'bench'))
        if benched != count:
            return {'fail': f'benched {benched}, expected {count}'}
        return {'ok': benched}

    async def test_sweep(self):
        report, fails = [], []
        for d, a in cases():
            res = await self.run_case(d, a)
            row = {'card': f"{d.display_name} ({d.set_code} {d.collector_number})",
                   'attack': a.title, 'text': a.game_text, **res}
            report.append(row)
            if 'fail' in res:
                fails.append(f"{row['card']} {a.title}: {res['fail']}")
        os.makedirs(REPORT_DIR, exist_ok=True)
        with open(os.path.join(REPORT_DIR, 'search_to_bench.json'), 'w') as fh:
            json.dump(report, fh, indent=1, ensure_ascii=False)
        self.assertGreater(len(report), 100)
        self.assertEqual(fails, [])

    async def test_gossifleur_prompt_says_up_to_3(self):
        # The browser header used to read "Choose a Pokémon ..." for every
        # count, which reads as a single pick.
        d = next(d for d, a in cases() if d.display_name == 'Gossifleur' and d.set_code == 'SWSH1')
        a = next(a for a in d.abilities if a.title == 'Call for Family')
        t = Table(self)
        me = neutral(t.put(d, P1, 'active'))
        neutral(t.put(self.filler, P2, 'active'))
        pay_cost(t, me, a)
        t.deck(P1, [self.filler] * 4)
        t.state.turn_number = 3
        await t.attack(me, a.title)
        self.assertIn('Choose up to 3 Pokémon to put onto your Bench.', t.prompts)
        self.assertEqual(len(t.zone(P1, 'bench')), 3)


if __name__ == '__main__':
    unittest.main()
