"""Offered-but-does-nothing detector.

For every Trainer (Item / Supporter / Tool / Stadium), every activated
Pokemon Ability and every attack in scope, build many randomized-but-plausible
boards in-process, ask the engine whether the action is offered, execute it
through the real action executor with randomized (and once with maximal)
answers to every prompt, snapshot the whole board before/after and flag:

  offered_noop           offered, ran cleanly, nothing changed except the card
                         being consumed (discard / once-per-turn flag) -- or
                         only its own cost was paid ("cost_only")
  offered_refused        offered, but execution raised / timed out / logged an
                         error, or the executor silently refused it
  cost_unpaid            text has a discard cost, the cost was not paid, but
                         the effect happened
  under_effect           did measurably less than printed (draw N, heal N,
                         "search for up to N" slot count)
  not_offered_but_could  Item/Supporter NOT offered although running its
                         effect on that same board does something (and the
                         card has no printed play restriction)

Each flag carries "excuses" (tails, chose fewer than allowed, empty search,
game over ...) so legit no-ops can be told apart from the suspicious ones.

Usage (from the repo root):
  PYTHONPATH=. python3 -m spirit.tools.noop_detector run \
      --decks audits/results/decks.txt \
      --out audits/results/noop/results.jsonl --boards 40 --jobs 2
  ... noop_detector run --card SL.DamageMover_58 --boards 20 --out /tmp/x.jsonl
  ... noop_detector summarize --results .../results.jsonl
  ... noop_detector replay --card SL.DamageMover_58 --kind trainer --seed 1234
"""
import argparse
import ast
import asyncio
import dataclasses
import html
import json
import logging
import multiprocessing as mp
import os
import random
import re
import signal
import sqlite3
import sys
import time
import traceback
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, 'spirit', 'game', 'scripts', 'cards')
LOCDB = os.path.join(REPO, 'spirit', 'database', 'game_data', 'LocalizationDB-UTF8.db')
SETS_JSON = os.path.join(REPO, 'spirit', 'database', 'json_data', 'sets.json')

EXEC_TIMEOUT = 6.0          # seconds per execution (SIGALRM + wait_for)
PLAYER_ZONES = ('deck', 'hand', 'bench', 'activePokemonArea', 'discard', 'prizePile', 'lostZone')
GLOBAL_ZONES = ('activeStadium', 'activeTrainer', 'outOfPlay')
# turn-state fields that merely record "the card was used"
CONSUMED_TS = {
    'supporter_played', 'supporters_played', 'trainers_played', 'used_abilities',
    'used_named_abilities', 'stadium_played', 'vstar_used', 'gx_used', 'attacks_used',
    'tools_attached_from_hand', 'auto_select_attack_entity_id', 'attack_coin_reroll_used',
    'on_move_to_active_fired',
}
ATTACK_KINDS = ('attack', 'granted_attack')
ENTITY_PLUMBING = {'entity_id', 'parent_id', 'owning_player_id', 'archetype_id', 'board_slot'}
NOISE_ATTRS = None   # filled lazily: attribute ids that change on mere movement


class ExecTimeout(Exception):
    pass


# ----------------------------------------------------------------------
# lazy engine imports
# ----------------------------------------------------------------------
E = {}


def init_engine():
    if E:
        return E
    logging.disable(logging.INFO)  # keep WARNING+ (we capture them)
    logging.getLogger().addHandler(logging.NullHandler())
    from tests import test_hgss_rules as fixtures
    fixtures.HgssRulesTests.setUpClass()
    from spirit.game import data_utils as du
    from spirit.game.attributes import AttrID, PokemonTypes, PokemonStage, TrainerType
    from spirit.game.session import effects as fx
    from spirit.game.session import legal_actions as la
    from spirit.game.session import passives
    from spirit.game.session.game_session import GameOver
    from spirit.tools.effect_smoke import Rig, P1, P2
    from tests.bughunt_table import Table
    E.update(dict(fixtures=fixtures, du=du, AttrID=AttrID, PokemonTypes=PokemonTypes,
                  PokemonStage=PokemonStage, TrainerType=TrainerType, fx=fx, la=la,
                  passives=passives, GameOver=GameOver, Rig=Rig, P1=P1, P2=P2, Table=Table,
                  F=fixtures.HgssRulesTests))
    global NOISE_ATTRS
    NOISE_ATTRS = set()
    return E


_LOWER = {}


def def_by_guid(guid):
    if not _LOWER:
        _LOWER.update({g.lower(): d for g, d in E['du'].CARD_DEFS_BY_GUID.items()})
    return _LOWER[guid.lower()]


class FakeTest:
    """Just enough of a TestCase for tests.bughunt_table.Table."""

    def __init__(self):
        F = E['F']
        self.filler, self.energies, self.item = F.filler, F.energies, F.item

    def rig(self, path, kind='pokemon'):
        rig = E['Rig'](E['fixtures'].definition(path), self.filler, self.energies, self.item)
        ents = rig.setup(kind)
        return rig, ents


# ----------------------------------------------------------------------
# scope: decklists -> definitions
# ----------------------------------------------------------------------
PROMO_MAP = {'SVP': 'SVP', 'SMP': 'Promo_SM', 'SP': 'Promo_SWSH', 'SWSHP': 'Promo_SWSH',
             'BWP': 'PROMO_BW', 'XYP': 'Promo_XY', 'MEP': 'MEP', 'PR-SV': 'SVP'}
BASIC_NAMES = {f'{p}{t} Energy' for p in ('', 'Basic ') for t in
               ('Darkness', 'Fire', 'Water', 'Grass', 'Lightning', 'Psychic', 'Fighting', 'Metal', 'Fairy')}


def set_map():
    out = dict(PROMO_MAP)
    for s in json.load(open(SETS_JSON)):
        out.setdefault(s['externalId'], s['name'])
    return out


_PATHS = None


def path_index():
    global _PATHS
    if _PATHS is None:
        _PATHS = {}
        rx = re.compile(r"guid\s*=\s*['\"]([0-9a-fA-F-]{36})")
        for s in os.listdir(SCRIPTS):
            d = os.path.join(SCRIPTS, s)
            if not os.path.isdir(d) or s.startswith('__'):
                continue
            for f in os.listdir(d):
                if f.endswith('.py') and not f.startswith('__'):
                    m = rx.search(open(os.path.join(d, f), encoding='utf-8').read())
                    if m:
                        _PATHS[m.group(1).lower()] = f'{s}.{f[:-3]}'
                    else:   # reprint(...) wrappers carry no guid literal
                        try:
                            import importlib
                            mod = importlib.import_module(f'spirit.game.scripts.cards.{s}.{f[:-3]}')
                            g = getattr(getattr(mod, 'card', None), 'guid', None)
                            if g:
                                _PATHS[g.lower()] = f'{s}.{f[:-3]}'
                        except Exception:
                            pass
    return _PATHS


def resolve_decks(deck_file):
    """-> {guid: {'name','printed':[...], 'decks': n}} for every non-basic-energy card."""
    du = E['du']
    by_name_num = defaultdict(list)
    by_name = defaultdict(list)
    for d in du.CARD_DEFS_BY_GUID.values():
        by_name_num[(d.display_name, str(d.collector_number))].append(d)
        by_name[d.display_name].append(d)
    smap = set_map()
    out = {}
    unresolved = []
    for line in open(deck_file, encoding='utf-8'):
        line = html.unescape(line.strip())
        m = re.match(r"(\d+) (.+) (\S+) (\S+)$", line)
        if not m or line.startswith('==='):
            continue
        name, ab, num = m.group(2), m.group(3), m.group(4)
        if name in BASIC_NAMES:
            continue
        for alias in (name, name + ' Team Flare Gear', name.replace('Flabebe', 'Flabébé')):
            if alias in by_name:
                name = alias
                break
        cands = by_name_num.get((name, num)) or by_name_num.get((name, re.sub(r'\D', '', num))) or []
        want = smap.get(ab, ab)
        if cands:
            pick = next((d for d in cands if d.set_code == want), cands[0])
        else:
            cands = sorted(by_name.get(name, []), key=lambda d: (d.set_code != want, d.set_code))
            if not cands:
                unresolved.append(line)
                continue
            pick = cands[0]
        row = out.setdefault(pick.guid.lower(), {'name': name, 'printed': set(), 'uses': 0})
        row['printed'].add(f'{ab} {num}')
        row['uses'] += 1
    for v in out.values():
        v['printed'] = sorted(v['printed'])
    return out, unresolved


# ----------------------------------------------------------------------
# printed text
# ----------------------------------------------------------------------
_LOC = None


def _loc():
    global _LOC
    if _LOC is None:
        _LOC = defaultdict(list)
        try:
            con = sqlite3.connect(LOCDB)
            for k, v in con.execute("select key, value from Lookup where key like '%gametext'"):
                _LOC[k.split('.')[-2].split('_')[0]].append((k, v))
        except Exception:
            pass
    return _LOC


TCGDATA_DIRS = [os.environ.get('NOOP_TCGDATA', 'audits/results/tcgdata/cards/en')]
_PRINTED = None
REMINDER_RX = re.compile(r'^(You may play (only 1|any number|as many)|This card stays in play|'
                         r'You may play only 1 Stadium|Attach a Pok.mon Tool|If this card is attached to 1 of your Pok.mon, discard it at the end)', re.I)


def _stem_for(set_code):
    sc = (set_code or '').lower()
    special = {'cz': 'swsh12pt5', 'dv': 'dv1', 'gum': 'det1', 'dm': 'sm75', 'sl': 'sm35', 'hf': 'sm115',
               'tatm': 'dc1', 'xy0': 'xy0', 'twentiethann': 'g1', 'promo_sm': 'smp', 'promo_swsh': 'swshp',
               'promo_xy': 'xyp', 'promo_bw': 'bwp', 'mep': 'mep'}
    if sc in special:
        return special[sc]
    m = re.fullmatch(r'sv0(\d)5', sc)
    if m:
        return f'sv{m.group(1)}pt5'
    m = re.fullmatch(r'(sv|me)0?(\d+)', sc)
    if m:
        return f'{m.group(1)}{int(m.group(2))}'
    return sc.replace('pt5', 'pt5')


def printed_rules(definition):
    """Printed Trainer text from pokemon-tcg-data (rules minus reminder lines), if available."""
    global _PRINTED
    if _PRINTED is None:
        _PRINTED = defaultdict(list)
        import glob
        for d in TCGDATA_DIRS:
            for fp in glob.glob(os.path.join(d, '*.json')):
                try:
                    for c in json.load(open(fp, encoding='utf-8')):
                        if c.get('supertype') == 'Trainer' and c.get('rules'):
                            _PRINTED[c['name']].append((os.path.basename(fp)[:-5], str(c.get('number')), c['rules']))
                except Exception:
                    pass
    rows = _PRINTED.get(definition.display_name or '') or []
    if not rows:
        return None
    stem, num = _stem_for(definition.set_code), str(definition.collector_number)
    rows = sorted(rows, key=lambda r: (r[0] != stem, r[1] != num))
    rules = [x for x in rows[0][2] if not REMINDER_RX.search(x)]
    return ' '.join(rules) or None


def trainer_text(definition, path):
    """Printed text of a Trainer: pokemon-tcg-data, script literal, else client localization."""
    printed = printed_rules(definition)
    if printed:
        return printed
    best = ''
    if path:
        fp = os.path.join(SCRIPTS, *path.split('.')) + '.py'
        try:
            tree = ast.parse(open(fp, encoding='utf-8').read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    s = node.value
                    if len(s) > len(best) and ' ' in s and 'direwolfdigital' not in s \
                            and not re.fullmatch(r'[0-9a-f-]{36}', s):
                        best = s
        except Exception:
            pass
    if len(best) >= 25:
        return best
    token = re.sub(r'[^a-z0-9]', '', (definition.display_name or '').lower().replace('é', 'e'))
    rows = _loc().get(token, [])
    if rows:
        sc = (definition.set_code or '').lower()
        num = str(definition.collector_number)
        rows = sorted(rows, key=lambda kv: (not (sc in kv[0] and f'_{num}.' in kv[0]), len(kv[0])))
        return rows[0][1]
    return best


# ----------------------------------------------------------------------
# targets
# ----------------------------------------------------------------------
def targets_for(definition, path):
    du = E['du']
    out = []
    if isinstance(definition, du.PokemonToolCardDef):
        out.append(('tool', None, definition.display_name, trainer_text(definition, path)))
        for i, a in enumerate(definition.granted_abilities):
            if isinstance(a, du.Attack):
                out.append(('granted_attack', i, a.title, a.game_text))
            elif a.activation in (du.Activations.ONCE_PER_TURN, du.Activations.UNLIMITED) and a.effect:
                out.append(('granted', i, a.title, a.game_text))
    elif isinstance(definition, du.StadiumCardDef):
        out.append(('stadium', None, definition.display_name, trainer_text(definition, path)))
        a = definition.ability
        if a is not None and a.effect is not None:
            out.append(('stadium_ability', None, a.title, a.game_text or trainer_text(definition, path)))
    elif isinstance(definition, du.FossilItemCardDef):
        pass
    elif isinstance(definition, du.TrainerCardDef):
        out.append(('trainer', None, definition.display_name, trainer_text(definition, path)))
    elif isinstance(definition, du.PokemonCardDef):
        for i, a in enumerate(definition.abilities):
            if isinstance(a, du.Attack):
                out.append(('attack', i, a.title, a.game_text))
            elif a.activation in (du.Activations.ONCE_PER_TURN, du.Activations.UNLIMITED) \
                    and a.trigger is None and a.effect is not None:
                out.append(('ability', i, a.title, a.game_text))
    return out


# ----------------------------------------------------------------------
# random boards
# ----------------------------------------------------------------------
class Pool:
    def __init__(self, guids):
        du, AttrID, Stage = E['du'], E['AttrID'], E['PokemonStage']
        self.basics, self.evos, self.trainers, self.tools, self.stadiums, self.special = [], [], [], [], [], []
        for g in sorted(guids):
            try:
                d = def_by_guid(g)
            except KeyError:
                continue
            if g.lower() not in E['fixtures'].loader.cards_by_guid:
                continue
            if isinstance(d, du.PokemonCardDef):
                st = (d.extra_attributes.get(str(AttrID.STAGE.value)) or {}).get('value')
                (self.basics if st == Stage.BASIC.value else self.evos).append(d)
            elif isinstance(d, du.PokemonToolCardDef):
                self.tools.append(d)
            elif isinstance(d, du.StadiumCardDef):
                self.stadiums.append(d)
            elif isinstance(d, du.TrainerCardDef):
                self.trainers.append(d)
            elif isinstance(d, du.EnergyCardDef) and d.set_code not in ('Free_Energy',):
                self.special.append(d)
        self.pokemon = self.basics + self.evos
        # indexes for target-aware enrichment
        A = E['AttrID']
        attr = lambda d, a: (d.extra_attributes.get(str(a.value)) or {}).get('value')
        by_logic = defaultdict(list)
        for d in self.pokemon:
            by_logic[attr(d, A.EVOLUTION_LOGIC_NAME)].append(d)
        self.lines = []
        for evo in self.evos:
            prev = by_logic.get(attr(evo, A.EVOLUTION_LOGIC_FROM)) or []
            for p in prev[:1]:
                if p in self.basics:
                    self.lines.append((p, evo))
                else:
                    pp = by_logic.get(attr(p, A.EVOLUTION_LOGIC_FROM)) or []
                    if pp and pp[0] in self.basics:
                        self.lines.append((pp[0], p, evo))
        self.evos_of = defaultdict(list)
        for evo in self.evos:
            self.evos_of[attr(evo, A.EVOLUTION_LOGIC_FROM)].append(evo)
        self.logic_name = lambda d: attr(d, A.EVOLUTION_LOGIC_NAME)
        self.by_name = defaultdict(list)
        self.by_title = defaultdict(list)
        self.by_type = defaultdict(list)
        for d in self.pokemon + self.trainers + self.tools + self.stadiums + self.special:
            if d.display_name:
                self.by_name[d.display_name.lower()].append(d)
        for d in self.pokemon:
            for a in d.abilities:
                self.by_title[(a.title or '').lower()].append(d)
            for tv in _types(d):
                self.by_type[tv].append(d)

    def random_card(self, rng, energy_types):
        r = rng.random()
        if r < 0.35:
            return rng.choice(self.pokemon)
        if r < 0.62:
            return rng.choice(self.trainers)
        if r < 0.67 and self.tools:
            return rng.choice(self.tools)
        if r < 0.70 and self.stadiums:
            return rng.choice(self.stadiums)
        if r < 0.75 and self.special:
            return rng.choice(self.special)
        return ('energy', rng.choice(energy_types))


def _types(definition):
    AttrID = E['AttrID']
    raw = (definition.extra_attributes.get(str(AttrID.POKEMON_TYPES.value)) or {}).get('value')
    try:
        vals = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    except Exception:
        vals = []
    return vals


_ENRICH_CACHE = {}


class Board:
    """One randomized board around a target; keeps a description for replay."""

    def __init__(self, pool, definition, target, seed):
        self.pool, self.definition, self.target, self.seed = pool, definition, target, seed
        self.rng = random.Random(seed)
        self.desc = {}
        self.source = None
        self.build()

    def _put(self, spec, pid, zone, hp=None):
        t = self.t
        if isinstance(spec, tuple):
            return t.put(t.basic_energy(E['PokemonTypes'](spec[1])), pid, zone)
        return t.put(spec, pid, zone, hp=hp)

    def _energy_types(self):
        PT = E['PokemonTypes']
        return [v for v in (PT.GRASS.value, PT.FIRE.value, PT.WATER.value, PT.LIGHTNING.value,
                            PT.PSYCHIC.value, PT.FIGHTING.value, PT.DARKNESS.value, PT.METAL.value)
                if v in E['F'].energies]

    def _attach_energy(self, mon, type_value):
        t = self.t
        card = t.put(t.basic_energy(E['PokemonTypes'](type_value)), mon.owning_player_id, 'hand')
        t.board.attach_card(card.entity_id, mon.entity_id)

    def _attach_legal(self, d, mon):
        """Attach a Special Energy / Tool only where the engine itself would allow it."""
        rule = getattr(d, 'attach_to', None)
        try:
            if rule is not None and not rule(mon):
                return None
            if isinstance(d, E['du'].PokemonToolCardDef) and any(
                    c.get_attribute(E['AttrID'].TRAINER_TYPE) is not None for c in mon.children):
                return None
            return self.t.attach(d, mon)
        except Exception:
            return None

    def _decorate(self, mon, rng, types):
        """random damage / energy / tool / condition on an in-play Pokemon"""
        t, AttrID = self.t, E['AttrID']
        own = [x for x in _types(E['du'].def_for(mon.archetype_id)) if x in types] or [rng.choice(types)]
        for _ in range(rng.choice([0, 0, 1, 1, 2, 3, 4])):
            r = rng.random()
            if r < 0.55:
                self._attach_energy(mon, rng.choice(own) if rng.random() < 0.7 else rng.choice(types))
            elif self.pool.special and r < 0.65:
                self._attach_legal(rng.choice(self.pool.special), mon)
            else:
                self._attach_energy(mon, rng.choice(types))
        if self.pool.tools and rng.random() < 0.15:
            self._attach_legal(rng.choice(self.pool.tools), mon)
        mx = E['passives'].effective_max_hp(t.board, mon)
        if rng.random() < 0.55 and mx > 10:
            mon.set_attribute(AttrID.HP, rng.randrange(1, max(2, mx // 10)) * 10)
        if mon.parent is not None and mon.parent.get_attribute(AttrID.NAME) == 'activePokemonArea' \
                and rng.random() < 0.12:
            mon.set_attribute(AttrID.SPECIAL_CONDITIONS,
                              [rng.choice(['Poisoned', 'Asleep', 'Confused', 'Burned', 'Paralyzed'])])
        if rng.random() < 0.2:
            self.t.state.entered_play_turn[mon.entity_id] = self.t.state.turn_number

    TYPE_WORDS = {'grass': 'GRASS', 'fire': 'FIRE', 'water': 'WATER', 'lightning': 'LIGHTNING',
                  'psychic': 'PSYCHIC', 'fighting': 'FIGHTING', 'darkness': 'DARKNESS', 'metal': 'METAL',
                  '{g}': 'GRASS', '{r}': 'FIRE', '{w}': 'WATER', '{l}': 'LIGHTNING', '{p}': 'PSYCHIC',
                  '{f}': 'FIGHTING', '{d}': 'DARKNESS', '{m}': 'METAL'}

    def enrich(self, rng, types):
        """Bias the board toward what the target's text talks about."""
        P1, P2 = E['P1'], E['P2']
        t, pool = self.t, self.pool
        text = (self.target[3] or '').lower()
        added = []
        zones = ['hand', 'deck', 'deck', 'discard']
        bench_free = lambda pid: len(t.zone(pid, 'bench')) < 5

        def drop(d, pid=P1, zone=None):
            zone = zone or rng.choice(zones)
            if zone == 'bench' and not bench_free(pid):
                zone = 'deck'
            c = self._put(d, pid, zone)
            added.append(f"{getattr(d, 'display_name', d)}@{zone}")
            return c
        # cards / attacks named in the text, and "<Owner>'s" families (matches cached per text)
        key = (id(pool), text)
        if key not in _ENRICH_CACHE:
            names = [defs for name, defs in pool.by_name.items() if len(name) >= 4 and name in text]
            fams = []
            for m in re.finditer(r"([a-z][a-z.]+(?: rocket)?'s) pok", text):
                fam = [d for n, ds in pool.by_name.items() if n.startswith(m.group(1)) for d in ds]
                if fam:
                    fams.append(fam)
            titles = [defs for title, defs in pool.by_title.items()
                      if (len(title) >= 8 or ' ' in title) and title in text
                      and re.search(r'\b' + re.escape(title) + r'\b', text)]
            _ENRICH_CACHE[key] = (names, fams, titles)
        names, fams, titles = _ENRICH_CACHE[key]
        for defs in names:
            if rng.random() < 0.8:
                for _ in range(rng.randint(1, 2)):
                    drop(rng.choice(defs))
        for fam in fams:
            for _ in range(rng.randint(1, 3)):
                drop(rng.choice(fam))
        for defs in titles:
            if rng.random() < 0.8:
                for _ in range(rng.randint(1, 3)):
                    drop(rng.choice(defs), zone=rng.choice(['discard', 'deck', 'bench', 'hand']))
        # evolution lines
        if re.search(r'evol|stage 1|stage 2|rare candy', text) and pool.lines:
            for _ in range(rng.randint(1, 2)):
                line = rng.choice(pool.lines)
                if not bench_free(P1):
                    victim = t.zone(P1, 'bench')[-1]
                    t.board.move_card(victim.entity_id, t.board.find_player_area(P1, 'discard').entity_id)
                b = t.put(line[0], P1, 'bench')
                added.append(f'{line[0].display_name}@bench')
                if rng.random() < 0.3:
                    t.state.entered_play_turn[b.entity_id] = t.state.turn_number
                drop(line[-1], zone='hand' if rng.random() < 0.8 else 'deck')
                for d in line[1:-1]:
                    drop(d, zone=rng.choice(['hand', 'deck']))
        # the source's own evolutions ("search your deck for a card that evolves from this Pokemon")
        if 'evolve' in text and isinstance(self.definition, E['du'].PokemonCardDef):
            mine = pool.evos_of.get(pool.logic_name(self.definition)) or []
            for d in mine[:2]:
                if rng.random() < 0.7:
                    drop(d, zone=rng.choice(['deck', 'deck', 'hand']))
        # energy / Pokemon types mentioned
        for word, tname in self.TYPE_WORDS.items():
            if word in text:
                tv = getattr(E['PokemonTypes'], tname).value
                if tv not in types:
                    continue
                for _ in range(rng.randint(1, 4)):
                    drop(('energy', tv), zone=rng.choice(['hand', 'discard', 'deck']))
                if rng.random() < 0.5:
                    self._attach_energy(rng.choice(t.board.pokemon_in_play(P1)), tv)
                if f'{word} pok' in text and pool.by_type.get(tv):
                    for _ in range(rng.randint(1, 3)):
                        drop(rng.choice(pool.by_type[tv]), zone=rng.choice(['hand', 'deck', 'discard', 'bench']))
        if 'energy' in text and rng.random() < 0.5:
            for _ in range(rng.randint(1, 4)):
                drop(('energy', rng.choice(types)), zone=rng.choice(['hand', 'discard', 'deck']))
            if pool.special:
                drop(rng.choice(pool.special), zone=rng.choice(['hand', 'discard', 'deck']))
        if 'tool' in text and pool.tools:
            for pid in (P1, P2):
                for mon in t.board.pokemon_in_play(pid):
                    if rng.random() < 0.4 and not any(c.get_attribute(E['AttrID'].TRAINER_TYPE) is not None
                                                      for c in mon.children):
                        self._attach_legal(rng.choice(pool.tools), mon)
            drop(rng.choice(pool.tools), zone=rng.choice(['hand', 'discard', 'deck']))
        if 'stadium' in text and pool.stadiums and not t.board.find_global_area('activeStadium').children:
            t.stadium(rng.choice(pool.stadiums), rng.choice([P1, P2]))
        if re.search(r'item card|trainer card', text):
            for _ in range(rng.randint(1, 3)):
                drop(rng.choice(pool.trainers), zone=rng.choice(['hand', 'discard', 'deck']))
        for cond in ('Poisoned', 'Asleep', 'Confused', 'Burned', 'Paralyzed'):
            if cond.lower() in text and rng.random() < 0.5:
                mon = t.active(rng.choice([P1, P2]))
                if mon is not None:
                    mon.set_attribute(E['AttrID'].SPECIAL_CONDITIONS, [cond])
        if 'damage counter' in text or 'heal' in text or 'damaged' in text:
            for pid in (P1, P2):
                for mon in t.board.pokemon_in_play(pid):
                    mx = E['passives'].effective_max_hp(t.board, mon)
                    if rng.random() < 0.5 and mx > 20:
                        mon.set_attribute(E['AttrID'].HP, rng.randrange(1, mx // 10) * 10)
        self.desc['enriched'] = added[:12]

    def build(self):
        P1, P2, du = E['P1'], E['P2'], E['du']
        rng, pool = self.rng, self.pool
        kind, idx = self.target[0], self.target[1]
        self.t = t = E['Table'](FakeTest(), filler_deck=0)
        st = t.state
        types = self._energy_types()
        turn = rng.choice([1, 2, 2, 3, 3, 4, 5, 6, 8])
        st.turn_number = turn
        st.active_player_id = P1
        t.session.first_player_id = P1 if turn % 2 == 1 else P2
        st.energy_attached = rng.random() < 0.3
        self.desc['turn'] = turn
        for pid in (P1, P2):
            # real (random) prize contents, not the Table's filler Items
            area = t.board.find_player_area(pid, 'prizePile')
            for card in list(area.children):
                area.remove_child(card)
            for _ in range(rng.choice([1, 2, 3, 4, 4, 5, 6, 6, 6])):
                self._put(self.pool.random_card(rng, self._energy_types()), pid, 'prizes')
        t.board.prizes_dealt = {P1: 6, P2: 6}

        defn = self.definition
        mine_active = None
        src_zone = None
        if kind in ('ability', 'attack'):
            ab = defn.abilities[idx]
            src_zone = getattr(ab, 'usable_from', None)
            if kind == 'attack' or src_zone is None and rng.random() < 0.55:
                src_zone = src_zone or 'active'
            src_zone = src_zone or 'bench'
        # P1 board
        bench_n = rng.choice([0, 1, 2, 3, 3, 4, 5, 5])
        for pid in (P1, P2):
            if pid == P1 and src_zone == 'active':
                active = self.source = t.put(defn, P1, 'active')
            else:
                active = t.put(rng.choice(pool.pokemon), pid, 'active')
            if pid == P1:
                mine_active = active
            n = bench_n if pid == P1 else rng.choice([0, 1, 2, 3, 4, 5])
            for i in range(n):
                if pid == P1 and src_zone == 'bench' and i == 0:
                    self.source = t.put(defn, P1, 'bench')
                else:
                    t.put(rng.choice(pool.pokemon), pid, 'bench')
            if pid == P1 and src_zone == 'bench' and self.source is None:
                self.source = t.put(defn, P1, 'bench')
            for mon in t.board.pokemon_in_play(pid):
                self._decorate(mon, rng, types)
            # hand / discard / deck
            hand_n = rng.choice([0, 1, 2, 3, 4, 5, 6, 8])
            for _ in range(hand_n):
                self._put(pool.random_card(rng, types), pid, 'hand')
            for _ in range(rng.choice([0, 0, 2, 5, 8, 12, 18])):
                self._put(pool.random_card(rng, types), pid, 'discard')
            r = rng.random()
            deck_n = 0 if r < 0.07 else rng.randint(1, 5) if r < 0.2 else rng.randint(10, 40)
            for _ in range(deck_n):
                self._put(pool.random_card(rng, types), pid, 'deck')
        if src_zone in ('hand', 'discard'):
            self.source = t.put(defn, P1, src_zone)
        # attack cost: pay it most of the time
        if kind == 'attack' and self.source is not None and rng.random() < 0.85:
            ab = defn.abilities[idx]
            own = [x for x in _types(defn) if x in types] or [rng.choice(types)]
            for ptype, count in (ab.cost or {}).items():
                tv = getattr(ptype, 'value', ptype)
                if tv not in types:
                    tv = rng.choice(own)
                for _ in range(count):
                    self._attach_energy(self.source, tv)
            self.source.set_attribute(E['AttrID'].SPECIAL_CONDITIONS, []) if rng.random() < 0.8 else None
        if kind in ('trainer', 'tool', 'stadium'):
            self.source = t.put(defn, P1, 'hand')
        if kind in ('granted', 'granted_attack'):
            holder = mine_active if kind == 'granted_attack' else rng.choice(t.board.pokemon_in_play(P1))
            for c in list(holder.children):
                if c.get_attribute(E['AttrID'].TRAINER_TYPE) is not None:
                    t.board.move_card(c.entity_id, t.board.find_player_area(P1, 'discard').entity_id)
            self.source = holder
            self.tool = t.attach(defn, holder)
            if kind == 'granted_attack' and rng.random() < 0.85:
                ab = defn.granted_abilities[idx]
                own = [x for x in _types(du.def_for(holder.archetype_id)) if x in types] or [rng.choice(types)]
                for ptype, count in (ab.cost or {}).items():
                    tv = getattr(ptype, 'value', ptype)
                    for _ in range(count):
                        self._attach_energy(holder, tv if tv in types else rng.choice(own))
        # stadium
        if kind == 'stadium_ability':
            self.source = t.stadium(defn, rng.choice([P1, P2]))
        elif pool.stadiums and rng.random() < 0.45:
            sd = rng.choice(pool.stadiums)
            if sd.guid != defn.guid or kind != 'stadium':
                t.stadium(sd, rng.choice([P1, P2]))
        if rng.random() < 0.6:
            self.enrich(rng, types)
        # The session tracks the last effective max HP it broadcast; prime it
        # so a Tool/Stadium HP bonus on our hand-built board is not "applied"
        # again (as a fake heal) by the next resync.
        for pid in (P1, P2):
            for mon in t.board.pokemon_in_play(pid):
                mx = E['passives'].effective_max_hp(t.board, mon)
                t.session._effective_max_seen[mon.entity_id] = mx
                if t.hp(mon) > mx:
                    mon.set_attribute(E['AttrID'].HP, mx)
        # description for the report
        nm = lambda c: (du.def_for(c.archetype_id).display_name or '?')
        for pid, tag in ((P1, 'me'), (P2, 'opp')):
            mons = t.board.pokemon_in_play(pid)
            self.desc[tag] = {
                'active': [f"{nm(m)} {t.hp(m)}/{E['passives'].effective_max_hp(t.board, m)}"
                           + f" att={[nm(c) for c in m.children]}"
                           + (f" {m.get_attribute(E['AttrID'].SPECIAL_CONDITIONS)}" if m.get_attribute(E['AttrID'].SPECIAL_CONDITIONS) else '')
                           for m in mons[:1]],
                'bench': [f"{nm(m)} {t.hp(m)}/{E['passives'].effective_max_hp(t.board, m)} att={len(m.children)}" for m in mons[1:]],
                'hand': t.names(t.zone(pid, 'hand')),
                'deck': len(t.zone(pid, 'deck')),
                'discard': len(t.zone(pid, 'discard')),
                'prizes': len(t.zone(pid, 'prizes')),
            }
        stad = t.board.find_global_area('activeStadium').children
        self.desc['stadium'] = nm(stad[0]) if stad else None
        self.desc['me']['bench_cap'] = E['passives'].effective_bench_capacity(t.board, P1)
        if self.target[0] in ATTACK_KINDS and self.source is not None and t.active(P2) is not None:
            res_types = t.active(P2).get_attribute(E['AttrID'].RESISTANCE_TYPES) or []
            mine = E['passives'].effective_pokemon_types(t.board, self.source) \
                if hasattr(E['passives'], 'effective_pokemon_types') else _types(du.def_for(self.source.archetype_id))
            mine = [getattr(x, 'value', x) for x in (mine or [])]
            res_types = [getattr(x, 'value', x) for x in (res_types if isinstance(res_types, (list, tuple)) else [res_types])]
            self.desc['resisted'] = bool(set(mine) & set(res_types))
            defender = t.active(P2)
            shields = [a.title for a in getattr(du.def_for(defender.archetype_id), 'abilities', [])
                       if getattr(a, 'passive', None) is not None and not hasattr(a, 'damage')]
            shields += [du.def_for(c.archetype_id).display_name for c in defender.children
                        if getattr(du.def_for(c.archetype_id), 'passive', None) is not None]
            self.desc['defender_passives'] = shields
            ab = defn.granted_abilities[self.target[1]] if self.target[0] == 'granted_attack' \
                else defn.abilities[self.target[1]]
            if getattr(ab, 'damage', 0):
                try:
                    calc = E['passives'].compute_damage(t.board, self.source, defender, ab.damage,
                                                        attack_title=ab.title)
                    self.desc['expected_damage'] = calc.amount
                    self.desc['damage_prevented'] = bool(getattr(calc, 'prevented', False))
                except Exception as ex:
                    self.desc['expected_damage'] = f'err {type(ex).__name__}'


# ----------------------------------------------------------------------
# prompt policy (patched onto the session instance)
# ----------------------------------------------------------------------
class Policy:
    def __init__(self, rng, mode):
        self.rng, self.mode = rng, mode
        self.trace = []
        self.coins = []

    def _k(self, n_valid, count, minimum):
        hi = max(0, min(count, n_valid))
        lo = hi if minimum is None else max(0, min(minimum, hi))
        return hi if self.mode == 'max' else self.rng.randint(lo, hi), lo, hi

    def install(self, session):
        pol = self

        def where(cards):
            out = set()
            for c in cards:
                e = c
                while getattr(getattr(e, 'parent', None), 'archetype_id', None):
                    e = e.parent
                p = getattr(e, 'parent', None)
                nm = p.get_attribute(E['AttrID'].NAME) if p is not None else None
                out.add(('attached' if e is not c else nm) if isinstance(nm, str) else '?')
            return sorted(out)

        async def card_chooser(player_id, source_entity_id, cards, count, minimum=None,
                               prompt='', ordered=False, display_cards=None, slot_prompt=''):
            valid = [c.entity_id for c in cards]
            k, lo, hi = pol._k(len(valid), count, minimum)
            pick = pol.rng.sample(valid, k) if pol.mode != 'max' else valid[:k]
            pol.trace.append({'p': 'cards', 'pid': player_id[-2:], 'prompt': prompt, 'n': len(valid),
                              'shown': len(display_cards or []), 'count': count, 'min': minimum,
                              'k': k, 'lo': lo, 'hi': hi, 'from': where(cards)})
            return pick

        async def entity_picker(player_id, source_entity_id, cards, count, minimum=None,
                                prompt='', **kw):
            valid = [c.entity_id for c in cards]
            k, lo, hi = pol._k(len(valid), count, minimum)
            pick = pol.rng.sample(valid, k) if pol.mode != 'max' else valid[:k]
            pol.trace.append({'p': 'pick', 'pid': player_id[-2:], 'prompt': prompt, 'n': len(valid),
                              'count': count, 'min': minimum, 'k': k, 'lo': lo, 'hi': hi,
                              'from': where(cards)})
            return pick

        async def groups(player_id, source_entity_id, groups, prompt='', display_cards=None,
                         total=None, any_of=False):
            res, left = [], total if total is not None else 10 ** 6
            for g in groups:
                k, lo, hi = pol._k(len(g['cards']), min(g['count'], left), g.get('minimum', 0))
                ids = [c.entity_id for c in g['cards']]
                pick = ids[:k] if pol.mode == 'max' else pol.rng.sample(ids, k)
                left -= k
                res.append(pick)
            pol.trace.append({'p': 'groups', 'pid': player_id[-2:], 'prompt': prompt,
                              'n': [len(g['cards']) for g in groups], 'count': [g['count'] for g in groups],
                              'k': [len(r) for r in res], 'total': total})
            return res

        async def player_choice(player_id, prompt, buttons, sort_type=''):
            i = 0 if pol.mode == 'max' or not buttons else pol.rng.randrange(len(buttons))
            pol.trace.append({'p': 'choice', 'pid': player_id[-2:], 'prompt': prompt,
                              'buttons': list(buttons)[:8], 'i': i})
            return i

        async def choice_panel(player_id, source, options, prompt=None, descriptions=None):
            i = 0 if pol.mode == 'max' or not options else pol.rng.randrange(len(options))
            pol.trace.append({'p': 'panel', 'pid': player_id[-2:], 'prompt': prompt,
                              'buttons': list(options)[:8], 'i': i})
            return i

        async def attack_sel(player_id, source, candidates, prompt=None):
            if not candidates:
                return None
            i = 0 if pol.mode == 'max' else pol.rng.randrange(len(candidates))
            pol.trace.append({'p': 'attack_sel', 'n': len(candidates), 'i': i})
            return i

        async def prize_pick(player_id, prize_ids, count, prompt=None, minimum=None, prize_area=None):
            k, lo, hi = pol._k(len(prize_ids), count, minimum)
            pol.trace.append({'p': 'prize', 'pid': player_id[-2:], 'prompt': prompt,
                              'n': len(prize_ids), 'count': count, 'min': minimum, 'k': k, 'lo': lo, 'hi': hi})
            return list(prize_ids[:k]) if pol.mode == 'max' else pol.rng.sample(list(prize_ids), k)

        async def prize_reveal(player_id, source_id, prize_ids, selectable_ids, prompt=None, forced=False):
            pol.trace.append({'p': 'prize_reveal', 'n': len(selectable_ids)})
            if not selectable_ids:
                return None
            if pol.mode != 'max' and not forced and pol.rng.random() < 0.3:
                return None
            return pol.rng.choice(selectable_ids) if pol.mode != 'max' else selectable_ids[0]

        async def counters(player_id, source_entity_id, candidates, count, amount_per_click=10,
                           prompt='', minimum=None):
            valid = [c.entity_id for c in candidates]
            if not valid or count <= 0:
                return {}
            lo = count if minimum is None else max(0, min(minimum, count))
            total = count if pol.mode == 'max' else pol.rng.randint(lo, count)
            out = {}
            for _ in range(total):
                v = valid[0] if pol.mode == 'max' else pol.rng.choice(valid)
                out[v] = out.get(v, 0) + 1
            pol.trace.append({'p': 'counters', 'prompt': prompt, 'n': len(valid), 'count': count,
                              'min': minimum, 'k': total})
            return out

        session.prompt_card_chooser = card_chooser
        session.prompt_entity_picker = entity_picker
        session.prompt_card_chooser_groups = groups
        session.prompt_player_choice = player_choice
        session.prompt_choice_panel = choice_panel
        session.prompt_attack_selection = attack_sel
        session._prompt_prize_pick = prize_pick
        session.prompt_prize_reveal_pick = prize_reveal
        session.prompt_damage_counter_placement = counters


# ----------------------------------------------------------------------
# snapshots
# ----------------------------------------------------------------------
_ADDR = re.compile(r' at 0x[0-9a-f]+')


def canon(v, depth=0):
    if depth > 6:
        return '...'
    if isinstance(v, dict):
        return tuple(sorted(((canon(k, depth + 1), canon(x, depth + 1)) for k, x in v.items()), key=repr))
    if isinstance(v, (set, frozenset)):
        return tuple(sorted((canon(x, depth + 1) for x in v), key=repr))
    if isinstance(v, (list, tuple)):
        return tuple(canon(x, depth + 1) for x in v)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if callable(v):
        return getattr(v, '__qualname__', type(v).__name__)
    if hasattr(v, '__dict__'):
        return (type(v).__name__, canon({k: x for k, x in vars(v).items() if not k.startswith('_')}, depth + 1))
    return _ADDR.sub('', repr(v))


def snapshot(t):
    AttrID = E['AttrID']
    board, st, s = t.board, t.state, t.session
    cards, names = {}, {}

    def rec(c, loc):
        attrs = {k: v for k, v in c.attributes.items() if k not in NOISE_ATTRS and v not in (None, [], (), {}, '')}
        # plain instance flags (Town Map's publicly_revealed, ...)
        for k, v in vars(c).items():
            if k not in ENTITY_PLUMBING and not k.startswith('_') and isinstance(v, (bool, int, float, str)) \
                    and v not in (None, False, 0, ''):
                attrs['py.' + k] = v
        cards[c.entity_id] = (loc, canon(attrs))
        names[c.entity_id] = (E['du'].def_for(c.archetype_id).display_name if c.archetype_id else '?') or '?'
        for ch in c.children:
            rec(ch, ('att', c.entity_id))

    decks = {}
    for pid in board.player_ids:
        for z in PLAYER_ZONES:
            area = board.find_player_area(pid, z)
            for c in (area.children if area else []):
                rec(c, (pid, z))
        decks[pid] = tuple(c.entity_id for c in board.find_player_area(pid, 'deck').children)
    for z in GLOBAL_ZONES:
        area = board.find_global_area(z)
        for c in (area.children if area else []):
            rec(c, ('global', z))
    ts = {f.name: canon(getattr(st, f.name)) for f in dataclasses.fields(st)}
    extra = {
        'temporary_passives': canon(getattr(board, 'temporary_passives', [])),
        'scheduled_effects': canon(getattr(s, 'scheduled_effects', [])),
        'poison_counters': canon(getattr(s, 'poison_counters', {})),
        'confusion_damage': canon(getattr(s, 'confusion_damage', {})),
        'extra_turn_pending': getattr(s, 'extra_turn_pending', None),
        'turn_visualizations': canon(getattr(s, '_turn_visualizations', {})),
        'players': canon({pid: board.find_player_entity(pid).attributes for pid in board.player_ids}),
        'game_phase': str(getattr(s, 'game_phase', '')),
    }
    return {'cards': cards, 'names': names, 'decks': decks, 'ts': ts, 'extra': extra}


def diff(a, b):
    moves, attrs = [], []
    for eid, (loc, at) in b['cards'].items():
        if eid not in a['cards']:
            moves.append((eid, None, loc))
            continue
        loc0, at0 = a['cards'][eid]
        if loc0 != loc:
            moves.append((eid, loc0, loc))
        if at0 != at:
            d0, d1 = dict(at0), dict(at)
            for k in set(d0) | set(d1):
                if d0.get(k) != d1.get(k):
                    attrs.append((eid, k, d0.get(k), d1.get(k)))
    for eid, (loc0, _) in a['cards'].items():
        if eid not in b['cards']:
            moves.append((eid, loc0, None))
    ts = {k: (a['ts'][k], b['ts'][k]) for k in a['ts'] if a['ts'][k] != b['ts'][k]}
    extra = {k: (a['extra'][k], b['extra'][k]) for k in a['extra'] if a['extra'][k] != b['extra'][k]}
    reordered = [pid for pid in a['decks'] if a['decks'][pid] != b['decks'][pid]
                 and set(a['decks'][pid]) == set(b['decks'][pid])]
    return {'moves': moves, 'attrs': attrs, 'ts': ts, 'extra': extra, 'reordered': reordered}


def short_loc(loc, names):
    if loc is None:
        return 'gone'
    if loc[0] == 'att':
        return 'on:' + names.get(loc[1], '?')
    return f'{loc[0][-2:]}:{loc[1]}'


# ----------------------------------------------------------------------
# text heuristics
# ----------------------------------------------------------------------
NUM = {'a': 1, 'an': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7}


def num(s):
    return int(s) if s.isdigit() else NUM.get(s.lower(), 1)


COST_RX = re.compile(
    r"(?:you can use this card only if you discard|you must discard|in order to (?:use|play)[^.]*discard|"
    r"^discard|\. discard|you may discard)\s+(\d+|an?|one|two|three)\s+(?:other\s+)?"
    r"(cards?|[a-z ]*energy|basic[a-z ]*|item cards?|pok[eé]mon tool cards?|[a-z ]*cards?)"
    r"[^.]*?(?:from your hand|attached to|from this pok|\. if you do|in order)", re.I)
RESTRICT_RX = re.compile(r"only if|only when|can't play|cannot play|unless|you can use this card only|"
                         r"you may play this card only|if you have|if your opponent has|if any of your|"
                         r"if you don't|during your first turn|prize cards? remaining|if it's your first",
                         re.I)


def cost_clause(text):
    m = COST_RX.search(text or '')
    if not m:
        return None
    clause = m.group(0).lower()
    end = (text or '').find('.', m.end())
    sentence = (text or '')[m.start():end if end >= 0 else None].lower()
    if 'opponent' in sentence:
        return None
    if 'from your hand' not in clause and 'attached' not in clause and 'from this pok' not in clause \
            and 'if you do' not in clause and 'in order' not in clause:
        return None
    lead = (text or '')[:m.start()].lower()
    leading = not lead.strip() or re.fullmatch(r'\s*(once during your turn(?: \(before your attack\))?,?\s*)', lead) is not None
    return {'n': num(m.group(1)), 'what': m.group(2).lower(), 'optional': 'you may discard' in clause,
            'leading': leading,
            'hand': 'from your hand' in clause or 'cards from your hand' in clause or 'card from your hand' in clause}


# ----------------------------------------------------------------------
# one execution
# ----------------------------------------------------------------------
class LogCatch(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.records = []

    def emit(self, record):
        try:
            self.records.append(f'{record.levelname}: {record.getMessage()[:240]}')
        except Exception:
            pass


def _alarm(signum, frame):
    raise ExecTimeout()


def find_entry(t, board, target):
    P1, la, du = E['P1'], E['la'], E['du']
    kind = target[0]
    src = board.source
    if src is None:
        return None, []
    acts = t.actions(P1)
    want_desc = {'trainer': la.ACTION_USE_TRAINER, 'tool': la.ACTION_ATTACH_TOOL,
                 'stadium': la.ACTION_PLAY_STADIUM}.get(kind)
    for e in acts:
        if e['entityID'] != src.entity_id:
            continue
        sa = e['selectableAction']
        if want_desc is not None:
            if sa['description'] == want_desc:
                return e, acts
            continue
        ab = board.ability
        if sa['description'] in (la.ACTION_USE_ABILITY, la.ACTION_USE_ATTACK) \
                and (sa.get('actionID') == ab.ability_id):
            return e, acts
    return None, acts


def why_not_offered(t, board, target):
    """Is a Trainer blocked by generic rules (so its condition never got asked)?"""
    P1, la = E['P1'], E['la']
    st, card = t.state, board.source
    from spirit.game.session.passives import trainer_play_blocked
    if st.play_locked(P1, card) or trainer_play_blocked(t.board, P1, card):
        return 'locked'
    d = board.definition
    tt = card.get_attribute(E['AttrID'].TRAINER_TYPE)
    if tt == E['TrainerType'].SUPPORTER.value:
        if st.turn_number <= 1 and not getattr(d, 'usable_first_turn', False):
            return 'turn1_supporter'
        if st.supporter_played:
            return 'supporter_played'
    cond = getattr(d, 'condition', None)
    if not la.trainer_condition_met(cond, t.board, P1, card):
        return 'condition'
    return 'other'


def run_exec(pool, definition, target, seed, mode, check_not_offered=False):
    """Build board(seed), maybe execute; returns a result dict."""
    P1, P2, du, AttrID = E['P1'], E['P2'], E['du'], E['AttrID']
    kind, idx, title, text = target
    res = {'kind': kind, 'title': title, 'seed': seed, 'mode': mode}
    try:
        board = Board(pool, definition, target, seed)
    except Exception as ex:
        res.update(status='board_error', error=f'{type(ex).__name__}: {ex}')
        return res
    t = board.t
    if kind in ('ability', 'attack'):
        board.ability = definition.abilities[idx]
    elif kind in ('granted', 'granted_attack'):
        board.ability = definition.granted_abilities[idx]
    elif kind == 'stadium_ability':
        board.ability = definition.ability
    else:
        board.ability = None
    res['board'] = board.desc
    entry, acts = find_entry(t, board, target)
    res['offered'] = entry is not None
    policy = Policy(random.Random(seed * 7 + (1 if mode == 'max' else 0)), mode)
    policy.install(t.session)
    if entry is None:
        res['status'] = 'not_offered'
        if check_not_offered and kind == 'trainer' and board.source is not None:
            reason = why_not_offered(t, board, target)
            res['not_offered_reason'] = reason
            if reason == 'condition':
                res.update(_direct_effect(t, board, policy))
        return res
    targets = []
    if kind == 'tool':
        valid = []
        for info in entry.get('targetInfoLst') or []:
            valid.extend(info.get('validTargets') or [])
        if valid:
            targets = [random.Random(seed).choice(valid)]
    pre_hp = {}
    before = snapshot(t)
    res.update(_execute(t, board, policy, lambda: t.session._apply_player_action(P1, entry, targets, None)))
    after = snapshot(t)
    res['diff'] = summarize_diff(before, after, board, target, res)
    res['prompts'] = policy.trace[:12]
    res['coins'] = policy.coins
    classify(res, before, after, board, target, definition)
    return res


def _execute(t, board, policy, coro_fn):
    from unittest.mock import patch
    fx = E['fx']
    out = {}
    real_flip = fx.EffectContext.flip_coins
    real_until = fx.EffectContext.flip_until_tails

    async def flip(ctx, count, title='', source=None, player_id=None):
        r = await real_flip(ctx, count, title, source=source, player_id=player_id)
        policy.coins.extend(['H' if x else 'T' for x in r])
        return r

    async def until(ctx, title=''):
        r = await real_until(ctx, title)
        policy.coins.extend(['H'] * r + ['T'])
        return r

    catcher = LogCatch()
    root = logging.getLogger()
    root.addHandler(catcher)
    random.seed(board.seed * 31 + (1 if policy.mode == 'max' else 0))
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, EXEC_TIMEOUT)
    try:
        with patch.object(fx.EffectContext, 'flip_coins', flip), \
                patch.object(fx.EffectContext, 'flip_until_tails', until):
            ret = asyncio.run(asyncio.wait_for(coro_fn(), EXEC_TIMEOUT - 0.5))
        out['status'] = 'ok'
        if ret:
            out['turn_ended'] = True
    except E['GameOver']:
        out['status'] = 'game_over'
    except (ExecTimeout, asyncio.TimeoutError) as ex:
        out['status'] = 'timeout'
        out['prompts_at_timeout'] = policy.trace[-3:]
        tb = traceback.extract_tb(ex.__traceback__)
        out['where'] = [f'{os.path.relpath(f.filename, REPO)}:{f.lineno}:{f.name}' for f in tb[-8:]]
    except Exception as ex:
        if type(ex).__name__ in ('SuddenDeath', 'GameOver'):
            out['status'] = 'game_over'
            return out
        out['status'] = 'error'
        out['error'] = f'{type(ex).__name__}: {ex}'[:300]
        tb = traceback.extract_tb(ex.__traceback__)
        out['where'] = [f'{os.path.relpath(f.filename, REPO)}:{f.lineno}:{f.name}' for f in tb[-4:]]
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
        root.removeHandler(catcher)
    logs = [r for r in catcher.records if not _benign_log(r)]
    if logs:
        out['logs'] = logs[:6]
    return out


def _benign_log(rec):
    # Stadium plays route through resolve_trainer_effect; a passive-only
    # Stadium legitimately has no scripted play effect.
    return False


def _direct_effect(t, board, policy):
    """Not offered: run the effect anyway (no legality gate) and see if it does anything."""
    fx = E['fx']
    before = snapshot(t)
    card = board.source
    trainer_area = t.board.find_global_area('activeTrainer')

    async def go():
        t.board.move_card(card.entity_id, trainer_area.entity_id)
        card.owning_player_id = E['P1']
        await fx.resolve_trainer_effect(t.session, E['P1'], card)

    r = _execute(t, board, policy, go)
    after = snapshot(t)
    d = summarize_diff(before, after, board, board.target, r)
    return {'direct': {'status': r.get('status'), 'error': r.get('error'), 'effect': d['effect'][:8],
                       'n_effect': len(d['effect']), 'prompts': policy.trace[:6], 'coins': policy.coins}}


def summarize_diff(before, after, board, target, res):
    d = diff(before, after)
    names = dict(before['names'])
    names.update(after['names'])
    src = board.source.entity_id if board.source is not None else None
    tool = getattr(board, 'tool', None)
    P1 = E['P1']
    consumed, effect, cost = [], [], []
    for eid, l0, l1 in d['moves']:
        line = f"{names.get(eid, '?')} {short_loc(l0, names)}->{short_loc(l1, names)}"
        if target[0] in ('trainer', 'tool', 'stadium') and eid == src:
            consumed.append(line)
        elif target[0] == 'stadium' and l0 == ('global', 'activeStadium'):
            consumed.append(line + ' (replaced stadium)')
        elif l1 is not None and l1[1] in ('discard', 'lostZone') and l0 is not None and \
                (l0 == (P1, 'hand') or (l0[0] == 'att' and before['cards'].get(l0[1], ((None,),))[0][0] == P1)):
            cost.append(line)
            effect.append(line)
        else:
            effect.append(line)
    for eid, k, v0, v1 in d['attrs']:
        if eid == src and target[0] in ('trainer', 'tool', 'stadium'):
            continue
        if eid not in before['cards'] or eid not in after['cards']:
            continue
        line = f"{names.get(eid, '?')} attr{k}: {str(v0)[:40]} -> {str(v1)[:40]}"
        effect.append(line)
    for k, (v0, v1) in d['ts'].items():
        if k in CONSUMED_TS or (k == 'attack_locks' and target[0] in ATTACK_KINDS):
            consumed.append(f'ts.{k}')
        else:
            effect.append(f'ts.{k}: {str(v0)[:60]} -> {str(v1)[:60]}')
    for k, (v0, v1) in d['extra'].items():
        if k == 'game_phase':
            effect.append('game_phase')
        elif k == 'players':
            consumed.append('player attrs')
        else:
            effect.append(f'{k} changed')
    shuffled = [f'deck shuffled ({p[-2:]})' for p in d['reordered']]
    if d['reordered'] and re.search(r'\btop of (?:your|their|his or her|your opponent.s) deck|on top of it|'
                                    r'rearrange|any order', (target[3] or '').lower()):
        effect.extend(f'deck top/order set ({p[-2:]})' for p in d['reordered'])
    # derived numbers
    moved = Counter()
    for eid, l0, l1 in d['moves']:
        if l0 and l1:
            moved[(l0[0] if l0[0] != 'att' else 'att', l0[1] if l0[0] != 'att' else 'x',
                   l1[0] if l1[0] != 'att' else 'att', l1[1] if l1[0] != 'att' else 'x')] += 1
    hp_gain, hp_loss = {}, {}
    for eid, k, v0, v1 in d['attrs']:
        if k == E['AttrID'].HP.value and isinstance(v0, int) and isinstance(v1, int):
            if v1 > v0:
                hp_gain[eid] = v1 - v0
            elif v1 < v0:
                hp_loss[eid] = v0 - v1
    return {'consumed': consumed, 'effect': effect, 'cost': cost, 'shuffled': shuffled,
            'moved': {f'{str(k[0])[-2:]}|{k[1]}|>|{str(k[2])[-2:]}|{k[3]}': v for k, v in moved.items()},
            'hp_gain': sum(hp_gain.values()), 'hp_gain_max': max(hp_gain.values(), default=0),
            'hp_loss': sum(hp_loss.values()),
            '_hp_gain_ids': list(hp_gain), '_moves': [(e, l0, l1) for e, l0, l1 in d['moves']]}


def _excuses(res, board):
    ex = []
    if 'T' in res.get('coins', []):
        ex.append('coin_tails')
    for p in res.get('prompts', []):
        if p.get('k') is not None and isinstance(p.get('k'), int) and p.get('hi') is not None \
                and p['k'] < p['hi']:
            ex.append('chose_less')
        if p.get('p') == 'groups' and sum(p['k']) < sum(min(a, b) for a, b in zip(p['n'], p['count'])):
            ex.append('chose_less')
        if p.get('p') == 'groups' and sum(p['n']) == 0:
            ex.append('search_found_nothing')
        if p.get('p') in ('cards',) and p.get('n') == 0:
            ex.append('search_found_nothing')
        if p.get('p') in ('choice', 'panel') and p.get('i'):
            ex.append('chose_option')
        if p.get('pid') == 'p2':
            ex.append('opponent_chose')
    if res.get('status') == 'game_over':
        ex.append('game_over')
    txt_all = (getattr(board, 'text', None) or '').lower()
    if re.search(r"reveals? (?:their|his or her) hand|opponent reveals|top cards? of (?:your|their|your opponent.s) deck|"
                 r"bottom \d+ cards of your deck|face-down prize|look at your prize|reveal the top", txt_all):
        ex.append('hidden_info')
    if res.get('mode') == 'max' and re.search(r'any order|rearrange', txt_all):
        ex.append('order_kept')      # the maximal policy returns the cards in their current order
    if board.desc.get('me', {}).get('deck', 1) == 0:
        ex.append('empty_deck')
    ab = getattr(board, 'ability', None)
    if ab is not None and hasattr(ab, 'damage'):
        txt = (ab.game_text or '').lower()
        if getattr(ab, 'damage_operator', '') in ('x', '×') or 'for each' in txt or not ab.damage:
            ex.append('scaling_or_zero_base')
        if board.desc.get('resisted'):
            ex.append('resisted')
        if board.desc.get('damage_prevented') or board.desc.get('expected_damage') == 0:
            ex.append('damage_prevented')
        elif board.desc.get('defender_passives') and (not isinstance(board.desc.get('expected_damage'), int)
                                                      or res.get('coins')):
            ex.append('defender_passive')   # incl. coin-flip shields (Evasion Jutsu, Infiltrator)
        if re.search(r"does nothing|if you can't|if you don't", txt):
            ex.append('text_allows_nothing')
    return sorted(set(ex))


def classify(res, before, after, board, target, definition):
    kind, idx, title, text = target
    if kind == 'stadium_ability' and len(text or '') < 40:      # "Use this Stadium's effect."
        text = trainer_text(definition, None) or text
    d = res['diff']
    # deck-order-only effects (put back in any order / on the bottom)
    if d.get('shuffled') and not any(e.startswith('deck top/order set') for e in d['effect']) and re.search(
            r"top of (?:your|their|his or her|your opponent.s) deck|on top of it|any order|rearrange|"
            r"bottom of (?:your|their|his or her|your opponent.s) deck", (text or '').lower()):
        d['effect'] = d['effect'] + ['deck order changed']
    # a Defending-Pokemon lock ("can't attack during your opponent's next
    # turn") lands in the same attack_locks map as the attacker's own lock
    if 'ts.attack_locks' in d['consumed'] and not getattr(getattr(board, 'ability', None), 'locks_next_turn', False):
        d['consumed'] = [c for c in d['consumed'] if c != 'ts.attack_locks']
        d['effect'] = d['effect'] + ['ts.attack_locks (defender lock)']
    # rows from older runs filed Will's forced coin under "consumed"
    moved_back = [c for c in d['consumed'] if c.startswith('ts.forced_coin_result')]
    if moved_back:
        d['consumed'] = [c for c in d['consumed'] if c not in moved_back]
        d['effect'] = d['effect'] + moved_back
    flags = []
    text_l = (text or '').lower()
    status = res.get('status')
    try:
        board.text = text
    except Exception:
        pass
    excuses = _excuses(res, board)
    res['excuses'] = excuses
    if status in ('error', 'timeout'):
        flags.append('offered_refused')
    elif res.get('logs') and any(l.startswith(('ERROR', 'CRITICAL')) for l in res['logs']):
        flags.append('offered_refused')
    # silent refusal: nothing at all happened, not even consumption
    if status == 'ok' and not d['consumed'] and not d['effect'] and kind not in ATTACK_KINDS \
            and not ({'chose_less', 'coin_tails', 'chose_option'} & set(excuses)):
        flags.append('offered_refused')
        res['refused_silently'] = True
    attacked = any('attacks_used' in c for c in d['consumed'])
    if kind in ATTACK_KINDS and status == 'ok' and not attacked:
        confused = any('Confused' in a for a in board.desc.get('me', {}).get('active', []))
        if confused:
            res['excuses'] = excuses = sorted(set(excuses) | {'confusion_fizzle'})
            res['flags'] = []
            return
        if not d['effect'] and 'coin_tails' not in excuses:
            flags.append('offered_refused')
            res['refused_silently'] = True
    if kind == 'trainer' and any('no scripted effect' in l or 'unimplemented' in l for l in res.get('logs', [])):
        flags.append('offered_noop')
        res['excuses'] = []
        res['public_precondition'] = 'engine logged: no scripted/unimplemented effect'
    if kind in ('ability', 'stadium_ability', 'granted') and any('unimplemented' in l for l in res.get('logs', [])):
        flags.append('offered_noop')
        res['excuses'] = []
        res['public_precondition'] = 'engine logged: unimplemented ability text'
    if kind in ('tool', 'stadium'):
        # attaching / placing is the whole effect; only refusals matter
        res['flags'] = [f for f in flags if f == 'offered_refused']
        return
    cc = cost_clause(text)
    real_effect = [e for e in d['effect'] if e not in d['cost']] if cc else d['effect']
    if status == 'ok' and 'offered_refused' not in flags:
        if not d['effect']:
            flags.append('offered_noop')
            me, opp = board.desc.get('me', {}), board.desc.get('opp', {})
            own_bench_rx = r'onto (?:your|their) bench' if kind == 'stadium_ability' else r'onto your bench'
            if kind not in ATTACK_KINDS and re.search(own_bench_rx, text_l) and \
                    len(me.get('bench', [])) >= me.get('bench_cap', 5):
                res['excuses'] = []
                res['public_precondition'] = 'own bench was full'
            elif kind not in ATTACK_KINDS and kind != 'stadium_ability' \
                    and re.search(r'onto (?:their|your opponent.s) bench', text_l) \
                    and len(opp.get('bench', [])) >= 5:
                res['excuses'] = []
                res['public_precondition'] = "opponent's bench was full"
        elif cc and not real_effect and d['cost']:
            flags.append('offered_noop')
            res['cost_only'] = True
        if cc and real_effect:
            paid = len(d['cost'])
            if paid < cc['n'] and not cc['optional']:
                flags.append('cost_unpaid')
                res['cost_detail'] = f"need {cc['n']} {cc['what']}, paid {paid}"
            elif cc['optional'] and cc.get('leading') and paid == 0 and 'if you do' in text_l:
                flags.append('cost_unpaid')
                res['cost_detail'] = f"optional cost ({cc['what']}) not paid but effect happened"
    if kind not in ATTACK_KINDS and status == 'ok' and res.get('turn_ended') \
            and not re.search(r"turn ends|ends your turn|end your turn", text_l):
        flags.append('turn_end_mismatch')
        res['turn_detail'] = 'turn ended but the text has no turn-ending clause'
    pv = prize_violation(text_l, board)
    if pv:
        flags.append('offered_violates_text')
        res['violation'] = pv
    # under-effect checks (maximal mode only: random mode may choose less)
    if status == 'ok' and res['mode'] == 'max' and 'offered_refused' not in flags:
        _under(res, board, target, text_l, d, flags)
    res['flags'] = flags
    # drop bulky internals
    d.pop('_hp_gain_ids', None)
    d.pop('_moves', None)


PRIZE_RX = re.compile(r"(?:only (?:if|when)|if) (you|your opponent) ha(?:ve|s) exactly (\d+|one|two|three|four|five|six) prize cards? remaining|"
                      r"(?:only (?:if|when)|if) (you|your opponent) ha(?:ve|s) (\d+|one|two|three|four|five|six) or (fewer|less|more) prize cards? remaining")


def prize_violation(text_l, board):
    """An action gated by a printed prize count that was offered anyway."""
    head = text_l.split('.')[0] if text_l else ''
    m = PRIZE_RX.search(head) if ('can use this' in head or 'can play this' in head or 'only' in head) else None
    if not m:
        return None
    me, opp = board.desc['me']['prizes'], board.desc['opp']['prizes']
    if m.group(1):
        who, n = m.group(1), num(m.group(2))
        have = me if who == 'you' else opp
        return None if have == n else f'needs {who} exactly {n} prizes, had {have}'
    who, n, rel = m.group(3), num(m.group(4)), m.group(5)
    have = me if who == 'you' else opp
    ok = have <= n if rel in ('fewer', 'less') else have >= n
    return None if ok else f'needs {who} {n} or {rel} prizes, had {have}'


def _under(res, board, target, text_l, d, flags):
    P1 = E['P1']
    me = board.desc.get('me', {})
    deck0 = me.get('deck', 0)
    coins = res.get('coins', [])
    m = re.search(r"(?:^|[.!] )draw (\d+|a|an|one|two|three|four|five|six|seven) cards?\b", text_l)
    if m and 'up to' not in text_l[max(0, m.start() - 12):m.end()] and not coins \
            and 'for each' not in text_l[m.end():m.end() + 20] and 'your opponent' not in text_l[:m.start()][-30:]:
        n = num(m.group(1))
        # drawn cards may move on within the same effect (attached, discarded)
        drawn = sum(v for k, v in d['moved'].items()
                    if k.startswith(f'{P1[-2:]}|deck|>|') and not k.endswith(('|deck', '|prizePile')))
        if drawn < min(n, deck0) and not re.search(r'(shuffle|put) your hand', text_l):
            flags.append('under_effect')
            res['under_detail'] = f'draw {n}: drew {drawn} with deck {deck0}'
    m = re.search(r"heal (\d+) damage from (?:1 of )?your", text_l)
    if m and not coins:
        n = int(m.group(1))
        damaged = any(re.search(r' (\d+)/(\d+)', s) and int(re.search(r' (\d+)/(\d+)', s).group(1))
                      < int(re.search(r' (\d+)/(\d+)', s).group(2))
                      for s in me.get('active', []) + me.get('bench', []))
        if damaged and d['hp_gain'] == 0:
            flags.append('under_effect')
            res['under_detail'] = f'heal {n}: healed 0 with a damaged Pokemon in play'
    m = re.search(r"search your deck for up to (\d+|two|three|four|five)", text_l)
    if m and not coins:
        n = num(m.group(1))
        deck_prompts = [p for p in res.get('prompts', []) if p.get('p') in ('cards', 'groups')]
        if deck_prompts:
            p = deck_prompts[0]
            room = n
            if 'onto your bench' in text_l:
                room = max(0, me.get('bench_cap', 5) - len(me.get('bench', [])))
            if p.get('p') == 'cards' and p.get('count', n) < min(n, room) and p.get('n', 0) >= min(n, room):
                flags.append('under_effect')
                res['under_detail'] = f'up to {n}: prompt allowed {p.get("count")} with {p.get("n")} valid'


# ----------------------------------------------------------------------
# per-card driver
# ----------------------------------------------------------------------
def stable_seed(guid, kind, idx, b):
    import zlib
    return zlib.crc32(f'{guid}|{kind}|{idx}'.encode()) % 1000003 * 1000 + b


def _row(guid, path, definition, r):
    r['guid'] = guid
    r['path'] = path
    r['card'] = definition.display_name
    r['set'] = definition.set_code
    r['number'] = definition.collector_number
    return r


KINDS = None   # optional filter set by --kinds


def card_rows(guid, n_boards, pool):
    du = E['du']
    definition = def_by_guid(guid)
    path = path_index().get(guid)
    out = []
    for target in targets_for(definition, path):
        if KINDS and target[0] not in KINDS:
            continue
        for b in range(n_boards):
            seed = stable_seed(guid, target[0], target[1], b)
            r = run_exec(pool, definition, target, seed, 'random', check_not_offered=True)
            r['text'] = (target[3] or '')[:400] if b == 0 else None
            out.append(_row(guid, path, definition, r))
            if r.get('offered') and r.get('status') != 'board_error':
                r2 = run_exec(pool, definition, target, seed, 'max')
                out.append(_row(guid, path, definition, r2))
    return out


# ----------------------------------------------------------------------
# multiprocessing
# ----------------------------------------------------------------------
def _worker(task_q, out_q, pool_guids, n_boards, kinds=None):
    global KINDS
    KINDS = kinds
    sys.setrecursionlimit(5000)
    init_engine()
    pool = Pool(pool_guids)
    while True:
        guid = task_q.get()
        if guid is None:
            break
        t0 = time.time()
        try:
            rows = card_rows(guid, n_boards, pool)
        except Exception as ex:
            rows = [{'guid': guid, 'status': 'card_error', 'error': f'{type(ex).__name__}: {ex}',
                     'tb': traceback.format_exc()[-800:]}]
        out_q.put((guid, rows, time.time() - t0))


def cmd_run(args):
    global KINDS
    init_engine()
    if args.kinds:
        KINDS = set(args.kinds.split(','))
    du = E['du']
    scope, unresolved = resolve_decks(args.decks)
    pool_guids = sorted(scope)
    def_by_guid(pool_guids[0])
    if args.card:
        want = []
        idx = path_index()
        rev = {v: k for k, v in idx.items()}
        for c in args.card:
            g = rev.get(c) or c.lower()
            want.append(g)
        guids = want
    else:
        guids = [g for g in pool_guids if g in _LOWER
                 and targets_for(def_by_guid(g), path_index().get(g))]
        if args.all_glc or args.only_extra:
            extra = sorted(g for g, d in _LOWER.items() if g not in scope
                           and any(not KINDS or t[0] in KINDS for t in targets_for(d, path_index().get(g))))
            guids = extra if args.only_extra else guids + extra
    if args.limit:
        guids = guids[:args.limit]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    print(f'scope: {len(scope)} deck cards ({len(unresolved)} unresolved lines); running {len(guids)} cards x '
          f'{args.boards} boards on {args.jobs} jobs', flush=True)
    t0 = time.time()
    done = 0
    with open(args.out, 'w', encoding='utf-8') as fh:
        if args.jobs <= 1:
            pool = Pool(pool_guids)
            for g in guids:
                for r in card_rows(g, args.boards, pool):
                    fh.write(json.dumps(r, ensure_ascii=False, default=str) + '\n')
                done += 1
                if done % 20 == 0:
                    print(f'{done}/{len(guids)} {time.time() - t0:.0f}s', flush=True)
            return
        ctx = mp.get_context('fork')
        task_q, out_q = ctx.Queue(), ctx.Queue()
        procs = []
        card_deadline = args.card_timeout

        def spawn():
            p = ctx.Process(target=_worker, args=(task_q, out_q, pool_guids, args.boards, KINDS), daemon=True)
            p.start()
            return p

        for g in guids:
            task_q.put(g)
        for _ in range(args.jobs):
            task_q.put(None)
        procs = [spawn() for _ in range(args.jobs)]
        import queue
        while done < len(guids):
            try:
                guid, rows, dt = out_q.get(timeout=card_deadline)
            except queue.Empty:
                print('worker stalled; aborting remaining', flush=True)
                break
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False, default=str) + '\n')
            fh.flush()
            done += 1
            if done % 25 == 0:
                print(f'{done}/{len(guids)} {time.time() - t0:.0f}s', flush=True)
        for p in procs:
            p.join(timeout=5)
    print(f'done {done} cards in {time.time() - t0:.0f}s', flush=True)


# ----------------------------------------------------------------------
# summarize
# ----------------------------------------------------------------------
EX_KEYS = ('seed', 'mode', 'status', 'board', 'coins', 'prompts', 'diff', 'error', 'where', 'logs', 'excuses',
           'cost_detail', 'under_detail', 'violation', 'public_precondition', 'direct', 'not_offered_reason')
CATEGORIES = ('offered_refused', 'cost_unpaid', 'offered_violates_text', 'under_effect', 'turn_end_mismatch',
              'offered_noop',
              'not_offered_but_could', 'offered_noop(excused)', 'not_offered_but_could(restricted)')


_TARGET_CACHE = {}


def reclassify(r):
    """Re-derive flags from a stored row (lets heuristics improve without re-running)."""
    if not r.get('offered') or 'diff' not in r:
        return r
    from types import SimpleNamespace
    init_engine()
    key = (r['guid'], r['kind'], r['title'])
    if key not in _TARGET_CACHE:
        d = def_by_guid(r['guid'])
        tg = next((t for t in targets_for(d, r.get('path')) if t[0] == r['kind'] and t[2] == r['title']), None)
        ab = None
        if tg is not None:
            if tg[0] in ('ability', 'attack'):
                ab = d.abilities[tg[1]]
            elif tg[0] in ('granted', 'granted_attack'):
                ab = d.granted_abilities[tg[1]]
            elif tg[0] == 'stadium_ability':
                ab = d.ability
        _TARGET_CACHE[key] = (d, tg, ab)
    d, tg, ab = _TARGET_CACHE[key]
    if tg is None:
        return r
    if r.get('status') == 'error' and str(r.get('error', '')).startswith(('SuddenDeath', 'GameOver')):
        r['status'] = 'game_over'
    stub = SimpleNamespace(desc=r.get('board') or {}, ability=ab, source=None)
    classify(r, None, None, stub, tg, d)
    return r


def aggregate(results_path, recheck=True):
    per = defaultdict(lambda: {'boards': 0, 'offered': 0, 'execs': 0, 'flags': Counter(), 'excuses': Counter(),
                               'examples': defaultdict(list), 'statuses': Counter(), 'text': None,
                               'noop_boards': set()})
    total = Counter()
    for line in open(results_path, encoding='utf-8'):
        r = json.loads(line)
        if r.get('status') == 'card_error':
            total['card_error'] += 1
            continue
        if recheck:
            reclassify(r)
        key = (r['card'], r['set'], str(r['number']), r.get('path'), r['kind'], r['title'])
        s = per[key]
        if r['mode'] == 'random':
            s['boards'] += 1
            total['boards'] += 1
            s['offered'] += bool(r.get('offered'))
        if r.get('offered'):
            s['execs'] += 1
            total['execs'] += 1
        s['statuses'][r.get('status')] += 1
        if r.get('text'):
            s['text'] = r['text']
        for f in r.get('flags', []):
            if f == 'offered_noop' and r.get('excuses'):
                f = 'offered_noop(excused)'
                for e in r['excuses']:
                    s['excuses'][e] += 1
            if f == 'offered_noop':
                s['noop_boards'].add(r['seed'])
            s['flags'][f] += 1
            if len(s['examples'][f]) < 3:
                s['examples'][f].append({k: r.get(k) for k in EX_KEYS if r.get(k) not in (None, [], {})})
        d = r.get('direct')
        if d and d.get('n_effect') and d.get('status') == 'ok':
            s['_direct'] = s.get('_direct', 0) + 1
            if len(s['examples']['_direct']) < 3:
                s['examples']['_direct'].append({k: r.get(k) for k in ('seed', 'board', 'direct', 'not_offered_reason')})
    for key, s in per.items():
        if s.get('_direct'):
            text = s.get('text') or ''
            f = 'not_offered_but_could'
            if RESTRICT_RX.search(text) or cost_clause(text):
                f += '(restricted)'
            s['flags'][f] += s['_direct']
            s['examples'][f] = s['examples'].pop('_direct')
        else:
            s['examples'].pop('_direct', None)
    return per, total


def cmd_summarize(args):
    per, total = aggregate(args.results, recheck=not args.no_recheck)
    cards = {k[:4] for k in per}
    kinds = Counter(k[4] for k in per)
    offered_targets = sum(1 for s in per.values() if s['offered'])
    out = ['# Offered-but-does-nothing detector: raw summary\n\n',
           f'- cards: {len(cards)}; targets (card x action): {len(per)} {dict(kinds)}\n',
           f'- random boards: {total["boards"]}; executions (random + maximal): {total["execs"]}; '
           f'targets offered at least once: {offered_targets}; card errors: {total["card_error"]}\n',
           f'- statuses: {dict(sum((s["statuses"] for s in per.values()), Counter()))}\n\n']
    for cat in CATEGORIES:
        rows = sorted(((s['flags'][cat], k, s) for k, s in per.items() if s['flags'].get(cat)),
                      key=lambda x: -x[0])
        out.append(f'\n## {cat}: {len(rows)} targets\n\n')
        for n, key, s in rows:
            out.append(f"### {key[0]} ({key[1]} {key[2]}, {key[3]}) {key[4]} '{key[5]}': {n} "
                       f"(offered {s['offered']}/{s['boards']} boards, {s['execs']} execs)\n")
            if s.get('text'):
                out.append(f"text: {s['text'][:300]}\n")
            if 'excused' in cat:
                out.append(f"excuses: {dict(s['excuses'])}\n\n")
                continue
            for ex in s['examples'].get(cat, [])[:1]:
                out.append('example: ' + json.dumps(ex, ensure_ascii=False, default=str)[:1800] + '\n')
            out.append('\n')
    open(args.summary, 'w', encoding='utf-8').write(''.join(out))
    if args.json:
        json.dump([{'key': list(k), 'flags': dict(s['flags']), 'offered': s['offered'], 'boards': s['boards'],
                    'execs': s['execs'], 'text': s.get('text'), 'excuses': dict(s['excuses']),
                    'examples': dict(s['examples'])}
                   for k, s in per.items() if s['flags']], open(args.json, 'w'), indent=1, default=str)
    print(''.join(out[:4]))


def cmd_replay(args):
    init_engine()
    scope, _ = resolve_decks(args.decks)
    pool = Pool(sorted(scope))
    rev = {v: k for k, v in path_index().items()}
    guid = rev.get(args.card) or args.card.lower()
    d = def_by_guid(guid)
    for target in targets_for(d, path_index().get(guid)):
        if target[0] != args.kind or (args.title and target[2] != args.title):
            continue
        r = run_exec(pool, d, target, args.seed, args.mode, check_not_offered=True)
        print(json.dumps(r, indent=1, ensure_ascii=False, default=str))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--decks', default='audits/results/decks.txt')
    r.add_argument('--out', required=True)
    r.add_argument('--boards', type=int, default=40)
    r.add_argument('--jobs', type=int, default=1)
    r.add_argument('--card', action='append', help='module path (SL.DamageMover_58) or guid; repeatable')
    r.add_argument('--limit', type=int, default=0)
    r.add_argument('--all-glc', action='store_true', help='also every other scripted printing')
    r.add_argument('--only-extra', action='store_true', help='only printings NOT in the decklists')
    r.add_argument('--kinds', help='comma list: trainer,tool,stadium,stadium_ability,ability,granted,attack,granted_attack')
    r.add_argument('--card-timeout', type=float, default=900)
    s = sub.add_parser('summarize')
    s.add_argument('--results', required=True)
    s.add_argument('--summary', required=True)
    s.add_argument('--json')
    s.add_argument('--no-recheck', action='store_true', help='trust stored flags instead of re-deriving them')
    p = sub.add_parser('replay')
    p.add_argument('--decks', default='audits/results/decks.txt')
    p.add_argument('--card', required=True)
    p.add_argument('--kind', required=True)
    p.add_argument('--title')
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--mode', default='max')
    args = ap.parse_args()
    {'run': cmd_run, 'summarize': cmd_summarize, 'replay': cmd_replay}[args.cmd](args)


if __name__ == '__main__':
    main()
