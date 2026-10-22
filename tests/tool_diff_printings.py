"""Differential run: every flagged multi-printing group, same scenario, compare."""
import json, os, re, unittest, importlib, copy
from unittest.mock import patch
from tests import test_hgss_rules as fixtures
from tests import test_glc_meta_cards as meta
from spirit.game.attributes import AttrID
from spirit.game.data_utils import Attack
from spirit.game.session.effects import EffectContext, resolve_attack
from spirit.tools.effect_smoke import P1, P2

ROOT = os.path.join(os.path.dirname(__file__), '..', 'spirit', 'game', 'scripts', 'cards')

def path_index():
    idx = {}
    for s in os.listdir(ROOT):
        d = os.path.join(ROOT, s)
        if not os.path.isdir(d) or s.startswith('__'): continue
        for f in os.listdir(d):
            if f.endswith('.py') and not f.startswith('__'):
                txt = open(os.path.join(d, f), encoding='utf-8').read()
                m = re.search(r"guid\s*=\s*['\"]([0-9a-fA-F-]{36})", txt)
                if m: idx[m.group(1).lower()] = f"{s}.{f[:-3]}"
    return idx

class Diff(unittest.IsolatedAsyncioTestCase):
    setUpClass = classmethod(fixtures.HgssRulesTests.setUpClass.__func__)
    rig = meta.GlcMetaCardTests.rig
    async def snapshot_run(self, path, index, kind):
        rig, e = self.rig(path, 'pokemon')
        b = rig.board
        src = e['target']
        for pid in (P1, P2):
            for p in b.pokemon_in_play(pid):
                p.set_attribute(AttrID.HP, p.get_attribute(AttrID.HP) - 10)
        d = fixtures.definition(path)
        ab = [a for a in d.abilities][index]
        async def cc(self_, cards, count, minimum=None, *a, **k): return list(cards)[:count]
        async def cp(self_, c, *a, **k): return list(c)[0] if c else None
        async def yn(self_, *a, **k): return True
        async def fl(self_, n, *a, **k): return [True]*n
        with patch.object(EffectContext,'choose_cards',cc), patch.object(EffectContext,'choose_pokemon',cp), \
             patch.object(EffectContext,'ask_yes_no',yn), patch.object(EffectContext,'flip_coins',fl):
            try:
                if isinstance(ab, Attack):
                    await resolve_attack(rig.session, P1, src, ab, ab.title)
                elif ab.effect is not None:
                    await ab.effect(EffectContext(rig.session, P1, src, ab))
                else:
                    return 'passive'
            except Exception as ex:
                return f'ERR {type(ex).__name__}: {ex}'
        snap = {}
        for pid in (P1, P2):
            snap[pid] = {z: len(b.find_player_area(pid, z).children) for z in ('hand','deck','discard','bench','prizePile')}
            snap[pid]['hp'] = [p.get_attribute(AttrID.HP) for p in b.pokemon_in_play(pid)]
            snap[pid]['cond'] = [sorted(p.get_attribute(AttrID.SPECIAL_CONDITIONS) or []) for p in b.pokemon_in_play(pid)]
            snap[pid]['att'] = [len(p.children) for p in b.pokemon_in_play(pid)]
        st = rig.session.turn_state
        snap['locks'] = len(getattr(st,'attack_locks',{}) or {})
        return snap
    async def trainer_run(self, path):
        rig, e = self.rig(path, 'trainer')
        b = rig.board
        d = fixtures.definition(path)
        async def cc(self_, cards, count, minimum=None, *a, **k): return list(cards)[:count]
        async def cp(self_, c, *a, **k): return list(c)[0] if c else None
        async def yn(self_, *a, **k): return True
        async def fl(self_, n, *a, **k): return [True]*n
        cond = getattr(d, 'condition', None)
        ok = None
        try: ok = bool(cond(b, P1)) if cond else None
        except Exception as ex: ok = f'cond err {ex}'
        with patch.object(EffectContext,'choose_cards',cc), patch.object(EffectContext,'choose_pokemon',cp), \
             patch.object(EffectContext,'ask_yes_no',yn), patch.object(EffectContext,'flip_coins',fl):
            try:
                if d.effect: await d.effect(EffectContext(rig.session, P1, e['target'], None))
            except Exception as ex:
                return f'ERR {type(ex).__name__}: {ex}'
        snap = {'cond': ok}
        for pid in (P1, P2):
            snap[pid] = {z: len(b.find_player_area(pid, z).children) for z in ('hand','deck','discard','bench','prizePile')}
            snap[pid]['hp'] = [p.get_attribute(AttrID.HP) for p in b.pokemon_in_play(pid)]
            snap[pid]['att'] = [len(p.children) for p in b.pokemon_in_play(pid)]
        return snap

    async def test_trainers(self):
        idx = path_index()
        from spirit.game.data_utils import CARD_DEFS_BY_GUID
        by = {f"{d.set_code}.{d.collector_number}": d for d in CARD_DEFS_BY_GUID.values()}
        groups = json.load(open('audits/results/flag_groups.json'))
        out = []
        for g in groups:
            if not g['head'].startswith('T'): continue
            reps = [v[0] for v in g['variants']]
            paths = [idx[by[r].guid.lower()] for r in reps]
            res = [await self.trainer_run(p) for p in paths]
            if not all(r == res[0] for r in res):
                out.append(f"DIFF {g['head']}\n" + "\n".join(f"     {p}: {r}" for p, r in zip(paths, res)))
            else:
                out.append(f"same {g['head']}")
        open('audits/results/diff_trainers.txt','w').write("\n".join(out))

    async def test_diff(self):
        idx = path_index()
        from spirit.game.data_utils import CARD_DEFS_BY_GUID
        by = {f"{d.set_code}.{d.collector_number}": d for d in CARD_DEFS_BY_GUID.values()}
        groups = json.load(open('audits/results/flag_groups_all.json'))
        out = []
        for g in groups:
            if not g['head'].startswith(('A','B','X')): continue
            reps = [v[0] for v in g['variants']]
            paths = [idx[by[r].guid.lower()] for r in reps]
            n = len(fixtures.definition(paths[0]).abilities)
            for i in range(n):
                res = [await self.snapshot_run(p, i, 'p') for p in paths]
                same = all(r == res[0] for r in res)
                title = fixtures.definition(paths[0]).abilities[i].title
                if not same:
                    out.append(f"DIFF {g['head']} :: {title}\n" + "\n".join(f"     {p}: {r}" for p, r in zip(paths, res)))
        open('audits/results/diff_report.txt','w').write("\n".join(out))
        print(len(out), 'differences')
