"""Bot-vs-bot stress test: plays many full games between randomized bots on
real GLC decklists and checks engine invariants as the game runs.

Everything runs in-process (no network, no DB).  Each game builds a real
GameSession and drives it through the same entry points the server uses:
``mark_player_ready`` -> ``run_gameplay_sequence`` (coin flip, deal,
mulligans, placement, prizes, turn loop, checkups, knockouts).

Modes (--mode):
  net    (default) both seats are NetworkPlayers bound to an in-process fake
         client.  Every prompt goes over the real wire format
         (SequenceMessage envelope -> SelectionWithTargets[AndActions]Required /
         CustomChoiceRequired / CoinFlip / GoFirst) and is answered through
         ``receive_player_action`` exactly like the network handler does.
  ai     both seats are the server's AIPlayer (prompt shortcuts in the engine);
         the main-phase policy is ai_policy.choose_action half the time and a
         seeded random legal action otherwise.
  mixed  one seat of each (what a real "bot match" looks like).

Usage (from the repo root, PYTHONPATH=.):
  python3 -m spirit.tools.stress_bots --games 200 --workers 2 --seed 1
  python3 -m spirit.tools.stress_bots --replay 1000017 [--mode net]
  python3 -m spirit.tools.stress_bots --minutes 45 --workers 2

The game seed fully determines the deck pair, every bot decision and the
engine's RNG (global ``random`` is seeded, ``uuid.uuid4`` is made
deterministic and PYTHONHASHSEED is pinned by re-exec), so ``--replay SEED``
reproduces a game exactly in a fresh process.
"""

import os
import sys

if __name__ == "__main__" and os.environ.get("PYTHONHASHSEED") != "0":
    # Set iteration order must not depend on per-process hash salt, or a
    # replay could diverge from the recorded game.
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-m", "spirit.tools.stress_bots"] + sys.argv[1:])

import argparse
import asyncio
import collections
import html
import json
import logging
import multiprocessing
import random
import re
import signal
import time
import traceback
import types
import uuid
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DECKS = "audits/results/decks.txt"
DEFAULT_OUT = "audits/results/stress"
TURN_CAP = 200
STALL_SECONDS = 20.0          # no wire traffic for this long = soft lock
HARD_TIMEOUT_SECONDS = 240.0  # wall-clock ceiling per game (CPU-bound loops)
RECENT = 15

P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"

UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
NUM_RE = re.compile(r"\b\d+\b")

# Limitless spellings -> engine display_name (run 2026-10-11 was made
# without these; replay its seeds with --no-aliases).
NAME_ALIASES = {
    "Unit Energy FDY": "Unit Energy FightingDarknessFairy",
    "Unit Energy GRW": "Unit Energy GrassFireWater",
    "Unit Energy LPM": "Unit Energy LightningPsychicMetal",
    "Blend Energy WLFM": "Blend Energy WaterLightningFightingMetal",
    "Blend Energy GRPD": "Blend Energy GrassFirePsychicDarkness",
    "Flabebe": "Flabébé",
    # Team Flare Gear Items: engine names carry the suffix (added 2026-10-12;
    # Robo Substitute was unresolved -> never played in earlier runs).
    "Robo Substitute": "Robo Substitute Team Flare Gear",
    "Battle Compressor": "Battle Compressor Team Flare Gear",
    "Target Whistle": "Target Whistle Team Flare Gear",
    "Head Ringer": "Head Ringer Team Flare Hyper Gear",
    "Jamming Net": "Jamming Net Team Flare Hyper Gear",
}
USE_ALIASES = True

BASIC_ENERGY_TYPES = {
    "Grass": 7, "Fire": 6, "Water": 11, "Lightning": 8, "Psychic": 10,
    "Fighting": 5, "Darkness": 2, "Metal": 9, "Fairy": 4,
}


# ----------------------------------------------------------------------
# Engine bootstrap (done once per process; workers fork after this)
# ----------------------------------------------------------------------

_ENGINE: Dict[str, Any] = {}


def load_engine():
    if _ENGINE:
        return _ENGINE
    _orig_sleep = asyncio.sleep

    async def fast_sleep(delay=0, result=None):
        # Choreography / animation pacing sleeps: yield once, never wait.
        return await _orig_sleep(0, result)

    asyncio.sleep = fast_sleep
    _ENGINE["orig_sleep"] = _orig_sleep

    from spirit.game.scripts.cards import loader
    loader.load_all()
    from spirit.game.session import game_session as gs
    from spirit.game.session import legal_actions as la
    from spirit.game.session import ai_policy
    from spirit.game.session import passives
    from spirit.game.session.constants import SelectionKind, GamePhase
    from spirit.game.models import board as board_mod
    from spirit.game import data_utils
    from spirit.tools.effect_smoke import basic_energy_guids

    # A prompt that reaches the wire for an AIPlayer waits this long before
    # the engine gives up with a null selection (logged as ERROR -> finding).
    gs.AI_PROMPT_GRACE_SECONDS = 2.0
    _ENGINE.update(
        loader=loader, gs=gs, la=la, ai_policy=ai_policy, passives=passives,
        SelectionKind=SelectionKind, GamePhase=GamePhase, board=board_mod,
        du=data_utils, energy=basic_energy_guids(),
        real_choose_action=ai_policy.choose_action,
    )
    return _ENGINE


# ----------------------------------------------------------------------
# Decklists
# ----------------------------------------------------------------------

def parse_decklists(path: str) -> Dict[int, List[Tuple[int, str, str, str]]]:
    decks: Dict[int, List[Tuple[int, str, str, str]]] = {}
    cur = None
    for raw in open(path, encoding="utf-8"):
        line = html.unescape(raw.strip())
        if line.startswith("=== DECK"):
            cur = int(line.split()[2])
            decks[cur] = []
            continue
        m = re.match(r"(\d+) (.+) (\S+) (\S+)$", line)
        if m and cur is not None:
            decks[cur].append((int(m.group(1)), m.group(2), m.group(3), m.group(4)))
    return decks


class DeckResolver:
    """Decklist line -> engine card GUID (logic of bughunt/resolve_all7.py:
    exact display_name + collector number, else display_name only)."""

    def __init__(self):
        eng = load_engine()
        du, loader = eng["du"], eng["loader"]
        self.by_name_num: Dict[Tuple[str, str], List[Any]] = collections.defaultdict(list)
        self.by_name: Dict[str, List[Any]] = collections.defaultdict(list)
        # Live-server DECK logs name the engine's own set code + number.
        self.by_set_num: Dict[Tuple[str, str], Any] = {}
        for d in du.CARD_DEFS_BY_GUID.values():
            if d.guid.lower() in loader.cards_by_guid:
                self.by_set_num.setdefault((str(d.set_code), str(d.collector_number)), d)
        for d in du.CARD_DEFS_BY_GUID.values():
            if not d.display_name or d.guid.lower() not in loader.cards_by_guid:
                continue
            self.by_name_num[(d.display_name, str(d.collector_number))].append(d)
            self.by_name[d.display_name].append(d)
        for lst in list(self.by_name_num.values()) + list(self.by_name.values()):
            lst.sort(key=lambda d: (d.set_code or "", d.guid))
        self.energy = eng["energy"]
        self.cache: Dict[int, Dict[str, Any]] = {}

    def _basic_energy_type(self, name: str) -> Optional[int]:
        n = name.replace("Basic ", "")
        if n.endswith(" Energy") and n[:-7] in BASIC_ENERGY_TYPES:
            return BASIC_ENERGY_TYPES[n[:-7]]
        return None

    def resolve(self, deck_id: int, lines) -> Dict[str, Any]:
        if deck_id in self.cache:
            return self.cache[deck_id]
        eng = load_engine()
        du = eng["du"]
        guids: List[str] = []
        notes: List[str] = []
        type_votes: collections.Counter = collections.Counter()
        for count, name, setab, num in lines:
            etype = self._basic_energy_type(name)
            if etype is not None and etype in self.energy:
                guids.extend([self.energy[etype]] * count)
                type_votes[etype] += 100  # explicit basic energy decides the type
                continue
            exact = self.by_set_num.get((setab, num))
            if USE_ALIASES:
                name = NAME_ALIASES.get(name, name)
            numi = re.sub(r"\D", "", num)
            cands = [exact] if exact is not None else (self.by_name_num.get((name, numi)) or [])
            how = "exact"
            if not cands:
                cands = self.by_name.get(name) or []
                how = "name-only"
            if not cands:
                notes.append(f"UNRESOLVED {count}x {name} {setab} {num}")
                continue
            d = cands[0]
            if how != "exact":
                notes.append(f"name-only {name} {setab} {num} -> {d.set_code} {d.collector_number}")
            guids.extend([d.guid.lower()] * count)
            if isinstance(d, du.PokemonCardDef):
                try:
                    from spirit.game.attributes import AttrID
                    raw = du._attr_value(d, AttrID.POKEMON_TYPES, "[]")
                    vals = json.loads(raw) if isinstance(raw, str) else list(raw or [])
                except Exception:
                    vals = []
                for v in vals:
                    type_votes[v] += 1
        deck_type = next((t for t, _ in type_votes.most_common() if t in self.energy), 11)
        if len(guids) < 60:
            notes.append(f"padded {60 - len(guids)} basic energy (type {deck_type})")
            guids.extend([self.energy[deck_type]] * (60 - len(guids)))
        elif len(guids) > 60:
            notes.append(f"truncated {len(guids) - 60} cards")
            guids = guids[:60]
        out = {"guids": guids, "notes": notes, "type": deck_type}
        self.cache[deck_id] = out
        return out


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def card_name(board, entity_or_id) -> str:
    eng = load_engine()
    ent = board.get_entity(entity_or_id) if isinstance(entity_or_id, str) else entity_or_id
    if ent is None:
        return str(entity_or_id)[:8] if entity_or_id else "?"
    d = eng["du"].def_for(getattr(ent, "archetype_id", None))
    name = getattr(d, "display_name", None)
    if name:
        return name
    from spirit.game.attributes import AttrID
    n = ent.get_attribute(AttrID.NAME)
    if isinstance(n, dict):
        n = n.get("id")
    return str(n or type(ent).__name__)


def normalize_msg(msg: str) -> str:
    msg = UUID_RE.sub("<id>", msg)
    msg = re.sub(r"^\[(Session|Effects|Passives)? ?[^\]]*\]\s*", "", msg)
    msg = re.sub(r"\{[^{}]*\}", "{...}", msg)
    msg = re.sub(r"\[[^\[\]]*\]", "[...]", msg)
    msg = NUM_RE.sub("N", msg)
    return msg[:200]


def name_guids(msg: str) -> str:
    """Replace card-archetype GUIDs in a log line by the card's name."""
    du = load_engine()["du"]

    def sub(m):
        d = du.def_for(m.group(0).lower())
        return f"'{d.display_name}'" if d is not None and getattr(d, "display_name", None) else m.group(0)
    return UUID_RE.sub(sub, msg)


def tb_signature(exc_type: str, tb_frames) -> Tuple[str, List[str]]:
    """exception type + deepest spirit/ frame; card scripts named separately."""
    spirit_frames = [f for f in tb_frames if "/spirit/" in f.filename and "stress_bots" not in f.filename]
    cards = []
    for f in tb_frames:
        m = re.search(r"scripts/cards/([^/]+)/([^/]+)\.py", f.filename)
        if m:
            cards.append(f"{m.group(1)}.{m.group(2)}")
    top = spirit_frames[-1] if spirit_frames else (tb_frames[-1] if tb_frames else None)
    where = f"{top.filename.split('/spirit/')[-1]}:{top.name}" if top else "?"
    return f"{exc_type} @ {where}", cards


class GameTimeout(BaseException):
    """Raised from SIGALRM when a game exceeds its wall-clock budget."""


# ----------------------------------------------------------------------
# One game
# ----------------------------------------------------------------------

class GameRun:
    def __init__(self, seed: int, deck_ids: Tuple[int, int], decks: Tuple[Dict, Dict],
                 mode: str, verbose: bool = False, turn_cap: int = TURN_CAP):
        self.seed = seed
        self.deck_ids = deck_ids
        self.decks = decks
        self.mode = mode
        self.verbose = verbose
        self.turn_cap = turn_cap
        self.rng = random.Random(seed * 7919 + 17)
        self.recent: collections.deque = collections.deque(maxlen=RECENT)
        self.failures: List[Dict[str, Any]] = []
        self._seen_sigs: set = set()
        self.warnings: collections.Counter = collections.Counter()
        self.last_progress = time.monotonic()
        self.packets = 0
        self.main_offers = 0
        self.prompts = 0
        self.actions_this_turn: Dict[Tuple[str, int], int] = collections.Counter()
        self.capped = False
        self.session = None
        self.original_cards: Dict[str, set] = {}
        self.phase_note = "init"

    # -- logging -------------------------------------------------------
    def log(self, text: str):
        turn = self.turn()
        line = f"T{turn} {text}"
        self.recent.append(line)
        if self.verbose:
            print("  " + line, flush=True)

    def turn(self) -> int:
        s = self.session
        return getattr(getattr(s, "turn_state", None), "turn_number", 0) if s else 0

    def pname(self, pid: str) -> str:
        return {P1: "P1", P2: "P2"}.get(pid, pid[:4])

    def fail(self, kind: str, signature: str, message: str, cards=None, tb: str = ""):
        sig = f"[{kind}] {signature}"
        if sig in self._seen_sigs:
            return
        self._seen_sigs.add(sig)
        rec = {
            "kind": kind, "signature": sig, "message": message[:2000],
            "cards": sorted(set(cards or [])), "turn": self.turn(),
            "phase": self.phase_note, "recent": list(self.recent),
            "traceback": tb[-6000:],
        }
        self.failures.append(rec)
        if self.verbose:
            print(f"!! FAILURE {sig}\n   {message[:500]}\n{tb[-3000:]}", flush=True)

    # -- session construction -----------------------------------------
    def build_session(self):
        eng = load_engine()
        gs = eng["gs"]
        run = self

        class StressSession(gs.GameSession):
            choreography_pauses = False

            async def end_game(self, winner_id: str, reason: str):
                # Exercise the EOG payload builders, skip DB/network side effects.
                for pid in self.players:
                    self._eog_additional_parameters(pid, winner_id, reason)
                run.log(f"GAME OVER winner={run.pname(winner_id)} ({reason})")
                self.declare_winner(winner_id, reason)
                raise gs.GameOver()

        class FakeClient:
            def __init__(self, account_id, name):
                self.player = types.SimpleNamespace(
                    account_id=account_id, username=name, screen_name=name,
                    avatar_decks=None)
                self.running = True

            async def send_packet(self, packet, request_id=0, flags=0):
                run.on_packet(self.player.account_id, packet)

        players = {}
        for pid, deck, name in ((P1, self.decks[0], "P1"), (P2, self.decks[1], "P2")):
            ai = self.mode == "ai" or (self.mode == "mixed" and pid == P2)
            players[pid] = {
                "client": None if ai else FakeClient(pid, name),
                "deck": {"deckName": name, "piles": {"deck": list(deck["guids"])}},
                "ready": True,
            }
        pairing = {"players": players, "is_solo": self.mode != "net",
                   "solitaire_id": "basic_bot_id", "options": {}, "queue_name": "stress"}
        session = StressSession(f"stress-{self.seed}", pairing)
        self.session = session
        session._rating_cache = {pid: 1000 for pid in players}
        session.board_state.game_options = session._build_game_options()
        session._build_match_found_payload()
        from spirit.game.models.board import CardEntity, CompositePokemonEntity
        for pid in players:
            deck_area = session.board_state.find_player_area(pid, "deck")
            self.original_cards[pid] = {
                c.entity_id for c in deck_area.children
                if isinstance(c, CardEntity) and not isinstance(c, CompositePokemonEntity)}
        return session

    # -- wire handling (NetworkPlayer seats) ---------------------------
    def on_packet(self, account_id: str, packet: Dict[str, Any]):
        self.packets += 1
        self.last_progress = time.monotonic()
        if packet.get("messageName") != "SequenceMessage":
            return
        msg = packet.get("msg") or {}
        name = msg.get("name")
        value = msg.get("value") or {}
        if name not in PROMPT_NAMES:
            return
        self.prompts += 1
        try:
            if name == "SelectionWithTargetsAndActionsRequired":
                self.check_invariants("main", account_id)
                reply = self.answer_main(account_id, value)
            else:
                self.check_invariants("prompt", account_id)
                reply = self.answer_prompt(account_id, name, value)
        except GameTimeout:
            raise
        except Exception as e:
            tb = traceback.format_exc()
            self.fail("harness", f"bot answer crashed: {type(e).__name__}", f"{name}: {e}", tb=tb)
            reply = {"selection": None, "counter": value.get("counter")}
        if reply is None:
            return  # turn cap: leave the prompt open; runner cancels the game
        loop = asyncio.get_running_loop()
        session = self.session
        loop.call_soon(lambda: asyncio.ensure_future(
            session.receive_player_action(account_id, reply)))

    def answer_main(self, pid: str, value: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self.main_offers += 1
        turn = self.turn()
        if turn > self.turn_cap:
            self.capped = True
            return None
        target_map = value.get("targetMap") or []
        counter = value.get("counter")
        picked = self.pick_main(pid, target_map,
                                value.get("sourceID") if value.get("ignoreFirst") else None)
        if picked is None:
            self.log(f"{self.pname(pid)} END TURN ({len(target_map)} offered)")
            return {"selection": None, "counter": counter}
        entry, responses = picked
        return {"selection": [[entry["entityID"], entry["selectableAction"]["actionID"]], responses],
                "counter": counter}

    def pick_main(self, pid, target_map, source_id=None):
        """Random legal main-phase play with a bias toward attacking/ending."""
        la = load_engine()["la"]
        turn = self.turn()
        k = self.actions_this_turn[(pid, turn)]
        if source_id:
            subset = [e for e in target_map if e["entityID"] == source_id]
            target_map = subset or target_map
        if not target_map:
            return None
        p_end = min(0.85, 0.02 + 0.02 * k)
        if self.rng.random() < p_end:
            return None
        attacks = [e for e in target_map if e["selectableAction"]["description"] == la.ACTION_USE_ATTACK]
        if attacks and self.rng.random() < 0.5:
            entry = self.rng.choice(attacks)
        else:
            weights = [ACTION_WEIGHTS.get(e["selectableAction"]["description"], 1.0)
                       * self._self_ko_damping(pid, e) for e in target_map]
            entry = self.rng.choices(target_map, weights=weights)[0]
        self.actions_this_turn[(pid, turn)] += 1
        responses = [self.target_response(info) for info in (entry.get("targetInfoLst") or [])]
        if entry["selectableAction"]["description"] == la.ACTION_PLAY_ENERGY and responses \
                and self.rng.random() < 0.5:
            # Feed the Active half the time so attacks actually come online.
            active = self.session.board_state.active_pokemon(pid)
            valid = (entry.get("targetInfoLst") or [{}])[0].get("validTargets") or []
            if active is not None and active.entity_id in valid:
                responses[0] = {"entityList": [active.entity_id]}
        self.log_action(pid, entry, responses)
        return entry, responses

    def _self_ko_damping(self, pid, entry) -> float:
        """Rarely scoop up a lone Active (instant loss ends the game early)."""
        board = self.session.board_state
        card = board.get_entity(entry.get("entityID"))
        if card is None or entry["selectableAction"]["description"] != "UseTrainerCard":
            return 1.0
        name = card_name(board, card)
        removers = getattr(load_engine()["ai_policy"], "_OWN_POKEMON_REMOVERS", ())
        if name in removers and len(board.pokemon_in_play(pid)) <= 1:
            return 0.05
        return 1.0

    def log_action(self, pid, entry, responses):
        eng = load_engine()
        board = self.session.board_state
        desc = entry["selectableAction"]["description"]
        what = card_name(board, entry["entityID"])
        ab = eng["du"].ABILITIES_BY_ID.get(entry["selectableAction"]["actionID"])
        if ab is not None and getattr(ab, "title", None):
            what += f" [{ab.title}]"
        tgt = []
        for r in responses:
            if not isinstance(r, dict):
                continue
            for t in r.get("entityList") or []:
                tgt.append(card_name(board, t))
            if "amount" in r:
                tgt.append(f"#{r['amount']}")
        short = desc.replace("PlayAbility", "").replace("Default", "").replace("UsePokemon", "")
        self.log(f"{self.pname(pid)} {short}: {what}" + (f" -> {', '.join(tgt)}" if tgt else ""))

    def _pay_value(self, valid: List[str], value: int) -> List[str]:
        la = load_engine()["la"]
        board = self.session.board_state
        order = list(valid)
        self.rng.shuffle(order)
        out, paid = [], 0
        for eid in order:
            if paid >= value:
                break
            ent = board.get_entity(eid)
            out.append(eid)
            try:
                paid += la.energy_provided_count(ent, board) if ent is not None else 1
            except Exception:
                paid += 1
        return out

    def _pick_count(self, valid, number, minimum) -> List[str]:
        n = len(valid)
        hi = max(0, min(number if isinstance(number, int) and number >= 0 else n, n))
        lo = max(0, min(minimum if isinstance(minimum, int) and minimum >= 0 else hi, hi))
        k = self.rng.randint(lo, hi) if hi >= lo else hi
        return self.rng.sample(list(valid), k)

    def target_response(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """One TargetResponse for a target node (main-turn action infos)."""
        if "titles" in info or "choices" in info:
            count = len(info.get("titles") or info.get("choices") or []) or 1
            return {"amount": self.rng.randrange(count)}
        valid = list(info.get("validTargets") or [])
        if info.get("valueToSelect"):
            return {"entityList": self._pay_value(valid, int(info["valueToSelect"]))}
        number = info.get("numberToSelect", 1)
        minimum = info.get("minimumToSelect", number)
        # Action nodes: pick at least one when anything is offered (a bare
        # action with an empty target list is just re-offered).
        if valid and (not isinstance(minimum, int) or minimum < 1):
            minimum = 1
        return {"entityList": self._pick_count(valid, number, minimum)}

    def answer_prompt(self, pid: str, name: str, value: Dict[str, Any]) -> Dict[str, Any]:
        SK = load_engine()["SelectionKind"]
        board = self.session.board_state
        counter = value.get("counter")
        who = self.pname(pid)
        if name in ("CustomChoiceRequired", "CoinFlipChoiceRequired", "GoFirstChoiceRequired"):
            buttons = value.get("buttons") or []
            idx = self.rng.randrange(len(buttons)) if buttons else 0
            label = (buttons[idx] or {}).get("id") if buttons else None
            prompt = (value.get("prompt") or {}).get("id") or name
            self.log(f"{who} choice '{prompt[:50]}' -> {label}")
            return {"selection": idx, "counter": counter}
        # SelectionWithTargetsRequired
        ttype = value.get("targetType")
        tmap = value.get("targetMap") or {}
        if ttype in (SK.KNOCKOUT_POKEMON.value, SK.INITIAL_BENCHED.value) and \
                all(not v for v in tmap.values()):
            keys = list(tmap.keys())
            prompt = (value.get("prompt") or {}).get("id") or ttype
            if not keys or (ttype == SK.INITIAL_BENCHED.value and self.rng.random() < 0.15):
                self.log(f"{who} placement '{prompt[:40]}' -> done")
                return {"selection": None, "counter": counter}
            pick = self.rng.choice(keys)
            self.log(f"{who} placement '{prompt[:40]}' -> {card_name(board, pick)}")
            return {"selection": {"entityID": pick}, "counter": counter}
        if not tmap:
            self.fail("harness", f"empty targetMap in {ttype}", json.dumps(value)[:800])
            return {"selection": None, "counter": counter}
        source, nodes = next(iter(tmap.items()))
        node = nodes[0] if nodes else {}
        kind = node.get("name") or ttype
        prompt = (node.get("targetPrompt") or {}).get("id") or ""
        src = card_name(board, value.get("sourceID") or source)
        if "titles" in node or "choices" in node:
            count = len(node.get("choices") or node.get("titles") or []) or 1
            idx = self.rng.randrange(count)
            titles = node.get("titles") or []
            label = (titles[idx] or {}).get("id") if idx < len(titles) else f"#{idx}"
            self.log(f"{who} menu({src}) '{prompt[:40]}' -> {label}")
            return {"selection": {"targetResponses": [{"amount": idx}]}, "counter": counter}
        if kind == SK.MULTI_SELECT_ENTITY_LIST.value:
            valid = list(node.get("validTargets") or [])
            total_hi = int(node.get("numberToSelect") or 0)
            total_lo = int(node.get("minimumToSelect") or 0)
            total = self.rng.randint(min(total_lo, total_hi), total_hi) if total_hi else 0
            alloc: Dict[str, int] = collections.Counter()
            for _ in range(total):
                alloc[self.rng.choice(valid)] += 1
            self.log(f"{who} counters({src}) {total} -> " +
                     ", ".join(f"{card_name(board, t)}x{c}" for t, c in alloc.items()))
            return {"selection": {"targetResponses": [{"entities": [
                {"target": t, "selections": c} for t, c in alloc.items()]}]},
                "counter": counter}
        if node.get("valueToSelect"):
            picks = self._pay_value(list(node.get("validTargets") or []), int(node["valueToSelect"]))
            self.log(f"{who} pay({src}) -> {', '.join(card_name(board, p) for p in picks)}")
            return {"selection": {"targetResponses": [{"entityList": picks}]}, "counter": counter}
        if node.get("selections") and kind != SK.COMPOSITE_REVEAL.value:
            # AND / ANY composite browser: one response per labeled slot.
            responses, picked_total = [], 0
            cap = node.get("numberToSelect")
            any_of = kind == SK.ANY_COMPOSITE_REVEAL.value
            for sel in node["selections"]:
                valid = list(sel.get("validTargets") or [])
                number = sel.get("numberToSelect", 1)
                if any_of and isinstance(cap, int):
                    number = max(0, min(number, cap - picked_total))
                minimum = sel.get("minimumToSelect", 0)
                picks = self._pick_count(valid, number, min(minimum, number))
                picked_total += len(picks)
                responses.append({"entityList": picks})
            names = [card_name(board, p) for r in responses for p in r["entityList"]]
            self.log(f"{who} browse({src}) '{prompt[:40]}' -> {', '.join(names) or 'none'}")
            return {"selection": {"targetResponses": responses}, "counter": counter}
        inner = (node.get("selections") or [node])[0]
        valid = list(inner.get("validTargets") or node.get("validTargets") or [])
        number = inner.get("numberToSelect", node.get("numberToSelect", 1))
        minimum = inner.get("minimumToSelect", node.get("minimumToSelect", number))
        picks = self._pick_count(valid, number, minimum)
        if not picks and kind in (SK.ENTITY_LIST.value, SK.COMPOSITE_REVEAL.value) \
                and self.rng.random() < 0.5:
            self.log(f"{who} pick({src}) '{prompt[:40]}' -> cancel/none")
            return {"selection": None, "counter": counter}
        self.log(f"{who} pick({src}) '{prompt[:40]}' {kind.replace('TargetInformation', '')} -> "
                 f"{', '.join(card_name(board, p) for p in picks) or 'none'}")
        return {"selection": {"targetResponses": [{"entityList": picks}]}, "counter": counter}

    # -- AIPlayer seats ---------------------------------------------------
    def ai_choose_action(self, session, player_id, target_map):
        """Replacement for game_session.choose_action (AIPlayer main phase)."""
        eng = load_engine()
        self.last_progress = time.monotonic()
        self.check_invariants("main", player_id)
        if self.turn() > self.turn_cap:
            self.capped = True
            raise asyncio.CancelledError()
        if self.rng.random() < 0.5:
            k = self.actions_this_turn[(player_id, self.turn())]
            if k > 40:
                picked = None
            else:
                picked = eng["real_choose_action"](session, player_id, target_map)
            if picked is None:
                self.log(f"{self.pname(player_id)}(AI) END TURN")
                return None
            entry, targets = picked
            self.actions_this_turn[(player_id, self.turn())] += 1
            self.log_action(player_id, entry, [{"entityList": targets}])
            return picked
        picked = self.pick_main(player_id, target_map)
        if picked is None:
            self.log(f"{self.pname(player_id)}(AI) END TURN")
            return None
        entry, responses = picked
        targets = [t for r in responses for t in (r.get("entityList") or [])]
        return entry, targets

    # -- invariants -------------------------------------------------------
    def check_invariants(self, when: str, acting: Optional[str] = None):
        s = self.session
        if s is None:
            return
        eng = load_engine()
        from spirit.game.models.board import (
            CardEntity, CompositePokemonEntity, PokemonEntity, PlayArea)
        from spirit.game.attributes import AttrID
        board = s.board_state
        passives = eng["passives"]
        seen: Dict[str, Any] = {}
        where: Dict[str, str] = {}
        zone_owner: Dict[str, Optional[str]] = {}
        dup: List[str] = []
        stack = [(board.playmat, None, None)]
        visited_nodes = set()
        while stack:
            node, zone, owner = stack.pop()
            if id(node) in visited_nodes:
                self.fail("invariant", "entity tree cycle / shared child",
                          f"{type(node).__name__} {card_name(board, node)} reached twice",
                          [card_name(board, node)])
                continue
            visited_nodes.add(id(node))
            if isinstance(node, PlayArea):
                zone = node.get_attribute(AttrID.NAME)
                owner = node.owning_player_id
            for child in node.children:
                if child.parent is not node:
                    self.fail("invariant", "child.parent pointer mismatch",
                              f"{card_name(board, child)} in {zone} has parent "
                              f"{card_name(board, child.parent) if child.parent else None}",
                              [card_name(board, child)])
                if board.get_entity(child.entity_id) is not child:
                    self.fail("invariant", "entity not registered in cache",
                              f"{card_name(board, child)} in {zone}", [card_name(board, child)])
                stack.append((child, zone, owner))
            if isinstance(node, CardEntity) and not isinstance(node, CompositePokemonEntity):
                if node.entity_id in seen:
                    dup.append(node.entity_id)
                seen[node.entity_id] = node
                where[node.entity_id] = zone
                zone_owner[node.entity_id] = owner
        for eid in dup:
            self.fail("invariant", "card appears twice in tree",
                      f"{card_name(board, eid)} in {where.get(eid)}", [card_name(board, eid)])
        all_orig = set()
        for pid, ids in self.original_cards.items():
            all_orig |= ids
            missing = [i for i in ids if i not in seen]
            if missing:
                names = [card_name(board, i) for i in missing]
                self.fail("invariant", f"card vanished from play tree: {names[0]}",
                          f"{self.pname(pid)} lost {len(missing)} card(s): {names}; "
                          f"in cache: {[board.get_entity(i) is not None for i in missing]}", names)
        extra = [i for i in seen if i not in all_orig]
        if extra:
            names = [card_name(board, i) for i in extra]
            self.fail("invariant", f"unknown card entity in tree: {names[0]}",
                      f"{len(extra)} extra card(s): {names} in {[where[i] for i in extra]}", names)
        # zone ownership: private zones must hold only their owner's cards
        for pid, ids in self.original_cards.items():
            for eid in ids:
                z, o = where.get(eid), zone_owner.get(eid)
                if z in ("deck", "hand", "discard", "prizePile", "lostZone") and o is not None and o != pid:
                    self.fail("invariant", f"card in opponent's {z}: {card_name(board, eid)}",
                              f"{card_name(board, eid)} owned by {self.pname(pid)} sits in "
                              f"{self.pname(o)}'s {z}", [card_name(board, eid)])
        # cards outside play must not carry attachments / damage
        for pid in s.players:
            for zone in ("deck", "hand", "discard", "prizePile", "lostZone"):
                area = board.find_player_area(pid, zone)
                for c in (area.children if area else []):
                    if c.children:
                        self.fail("invariant", f"card in {zone} carries attached cards: {card_name(board, c)}",
                                  f"{card_name(board, c)} in {self.pname(pid)} {zone} has "
                                  f"{[card_name(board, x) for x in c.children]}",
                                  [card_name(board, c)] + [card_name(board, x) for x in c.children])
                    if isinstance(c, PokemonEntity) and when == "main":
                        printed = c.attribute_originals.get(AttrID.HP.value)
                        hp = c.get_attribute(AttrID.HP)
                        if printed is not None and hp != printed and zone != "prizePile" or \
                                (zone == "prizePile" and printed is not None and hp != printed):
                            self.fail("invariant", f"damage kept after leaving play ({zone}): {card_name(board, c)}",
                                      f"{card_name(board, c)} in {zone} HP {hp} != printed {printed}",
                                      [card_name(board, c)])
        if when != "main":
            return
        if s.game_phase == eng["GamePhase"].GAME_OVER:
            return
        stadium = board.find_global_area("activeStadium")
        if stadium is not None and len(stadium.children) > 1:
            names = [card_name(board, c) for c in stadium.children]
            self.fail("invariant", f"{len(stadium.children)} cards in Stadium area",
                      f"activeStadium holds {names}", names)
        trainer_zone = board.find_global_area("activeTrainer")
        if trainer_zone is not None and trainer_zone.children:
            names = [card_name(board, c) for c in trainer_zone.children]
            self.fail("invariant", f"card stranded in activeTrainer: {names[0]}",
                      f"activeTrainer still holds {names} at a main offer", names)
        tool_slots_free = getattr(passives, "tool_slots_free", None)
        for pid in s.players:
            bench_area = board.find_player_area(pid, "bench")
            for p in [c for c in bench_area.children if isinstance(c, PokemonEntity)]:
                conds = p.get_attribute(AttrID.SPECIAL_CONDITIONS) or []
                if conds:
                    nm = card_name(board, p)
                    self.fail("invariant", f"Benched Pokemon has Special Condition: {nm}",
                              f"{nm} on bench has {conds}", [nm])
            for p in board.pokemon_in_play(pid):
                if tool_slots_free is not None:
                    try:
                        free = tool_slots_free(board, p)
                    except Exception:
                        free = 0
                    if free < 0:
                        nm = card_name(board, p)
                        tools = [card_name(board, c) for c in p.children
                                 if c.get_attribute(AttrID.TRAINER_TYPE) in (4, 5)]
                        self.fail("invariant", f"too many Tools attached: {nm}",
                                  f"{nm} tool slots free {free}: {tools}", [nm] + tools)
        for pid in s.players:
            active_area = board.find_player_area(pid, "activePokemonArea")
            bench = board.find_player_area(pid, "bench")
            actives = [c for c in active_area.children if isinstance(c, PokemonEntity)]
            if len(actives) != 1:
                self.fail("invariant", f"active count {len(actives)}",
                          f"{self.pname(pid)} has {len(actives)} Active Pokemon at a main offer: "
                          f"{[card_name(board, a) for a in actives]}",
                          [card_name(board, a) for a in actives])
            non_pkmn = [c for c in list(active_area.children) + list(bench.children)
                        if not isinstance(c, PokemonEntity)]
            if non_pkmn:
                self.fail("invariant", f"non-Pokemon top-level card in play area: {card_name(board, non_pkmn[0])}",
                          f"{self.pname(pid)}: {[ (card_name(board, c), type(c).__name__) for c in non_pkmn]}",
                          [card_name(board, c) for c in non_pkmn])
            try:
                cap = passives.effective_bench_capacity(board, pid)
            except Exception as e:
                cap = 5
                self.fail("exception", f"{type(e).__name__} in effective_bench_capacity", str(e),
                          tb=traceback.format_exc())
            nb = len([c for c in bench.children if isinstance(c, PokemonEntity)])
            if nb > cap:
                self.fail("invariant", "bench over capacity",
                          f"{self.pname(pid)} bench {nb} > capacity {cap}: "
                          f"{[card_name(board, c) for c in bench.children]}",
                          [card_name(board, c) for c in bench.children])
            for p in actives + [c for c in bench.children if isinstance(c, PokemonEntity)]:
                hp = p.get_attribute(AttrID.HP)
                try:
                    mx = passives.effective_max_hp(board, p)
                except Exception as e:
                    mx = None
                    self.fail("exception", f"{type(e).__name__} in effective_max_hp", str(e),
                              [card_name(board, p)], tb=traceback.format_exc())
                nm = card_name(board, p)
                if not isinstance(hp, int):
                    self.fail("invariant", f"non-int HP: {nm}", f"{nm} HP={hp!r}", [nm])
                    continue
                if hp < 0:
                    self.fail("invariant", f"negative HP: {nm}", f"{nm} HP {hp}", [nm])
                elif hp == 0:
                    self.fail("invariant", f"0-HP Pokemon left in play: {nm}",
                              f"{nm} HP 0 (max {mx}) still in play at a main offer", [nm])
                if mx is not None and hp > mx:
                    self.fail("invariant", f"HP above max: {nm}", f"{nm} HP {hp} > max {mx}", [nm])
                if hp % 10:
                    self.fail("invariant", f"HP not a multiple of 10: {nm}", f"{nm} HP {hp}", [nm])

    # -- run ----------------------------------------------------------------
    async def run_async(self) -> str:
        eng = load_engine()
        gs = eng["gs"]
        session = self.build_session()
        loop = asyncio.get_running_loop()

        def exc_handler(loop_, context):
            exc = context.get("exception")
            msg = context.get("message", "")
            if isinstance(exc, (asyncio.CancelledError, gs.GameOver)):
                return
            if exc is not None:
                frames = traceback.extract_tb(exc.__traceback__)
                sig, cards = tb_signature(type(exc).__name__, frames)
                self.fail("exception", "background task: " + sig, f"{msg}: {exc}", cards,
                          tb="".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            else:
                self.fail("error_log", "loop: " + normalize_msg(msg), msg)
        loop.set_exception_handler(exc_handler)

        for pid in list(session.players):
            await session.mark_player_ready(pid)
        if session.gameplay_task is None:
            # all-AI seats: no network player to wait for
            await session._dispatch_initial_state_if_ready()
        task = session.gameplay_task
        if task is None:
            self.fail("harness", "gameplay task never started", "")
            return "harness"
        outcome = "finished"
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.5)
            if done:
                break
            if self.capped:
                outcome = "turn_cap"
                break
            if time.monotonic() - self.last_progress > STALL_SECONDS:
                outcome = "stall"
                chain = []
                coro = task.get_coro()
                while coro is not None:
                    fr = getattr(coro, "cr_frame", None) or getattr(coro, "gi_frame", None)
                    if fr is not None:
                        chain.append(f"{fr.f_code.co_filename.split('/spirit/')[-1]}:"
                                     f"{fr.f_code.co_name}:{fr.f_lineno}")
                    nxt = getattr(coro, "cr_await", None) or getattr(coro, "gi_yieldfrom", None)
                    if nxt is None or not hasattr(nxt, "cr_frame") and not hasattr(nxt, "gi_frame"):
                        if nxt is not None:
                            chain.append(f"<awaiting {type(nxt).__name__}>")
                        break
                    coro = nxt
                waiting = {self.pname(pid): (p.pending_choice_future is not None
                                             and not p.pending_choice_future.done())
                           for pid, p in session.players.items()}
                sig = chain[-2] if len(chain) >= 2 else (chain[-1] if chain else "?")
                self.fail("stall", f"no progress for {STALL_SECONDS:.0f}s at {sig}",
                          f"await chain: {' -> '.join(chain)}; pending prompts: {waiting}",
                          tb="\n".join(chain))
                break
        if self.capped:
            outcome = "turn_cap"
        if not task.done():
            session.cleanup()
            try:
                await asyncio.wait_for(task, 5)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        if outcome == "turn_cap":
            self.fail("turn_cap", f"game reached turn cap {self.turn_cap}",
                      f"turn {self.turn()} with no winner")
        # final structural check
        self.check_invariants("final")
        if outcome == "finished" and session.game_result is None:
            self.fail("invariant", "gameplay ended without a result",
                      f"phase={session.game_phase}")
        # let stray tasks settle / surface their exceptions
        for t in list(session._background_tasks):
            t.cancel()
        await asyncio.sleep(0)
        return outcome

    def run(self) -> Dict[str, Any]:
        eng = load_engine()
        gs = eng["gs"]
        random.seed(self.seed)
        id_rng = random.Random(self.seed ^ 0x5EED5EED)
        orig_uuid4 = uuid.uuid4
        uuid.uuid4 = lambda: uuid.UUID(int=id_rng.getrandbits(128), version=4)
        orig_choose = gs.choose_action
        gs.choose_action = self.ai_choose_action
        handler = _CaptureHandler(self)
        root = logging.getLogger()
        root.addHandler(handler)
        t0 = time.time()

        def on_alarm(signum, frame):
            stack = traceback.extract_stack(frame)
            sig, cards = tb_signature("GameTimeout", stack)
            self.fail("timeout", f"hard timeout {HARD_TIMEOUT_SECONDS:.0f}s in {sig.split(' @ ')[-1]}",
                      "game exceeded wall-clock budget (CPU-bound loop?)", cards,
                      tb="".join(traceback.format_list(stack)))
            raise GameTimeout()
        old = signal.signal(signal.SIGALRM, on_alarm)
        signal.setitimer(signal.ITIMER_REAL, HARD_TIMEOUT_SECONDS)
        outcome = "finished"
        try:
            outcome = asyncio.run(self.run_async())
        except GameTimeout:
            outcome = "timeout"
        except BaseException as e:  # harness-level crash
            if isinstance(e, KeyboardInterrupt):
                raise
            tb = traceback.format_exc()
            frames = traceback.extract_tb(e.__traceback__)
            sig, cards = tb_signature(type(e).__name__, frames)
            kind = "harness" if any("stress_bots" in f.filename for f in frames[-1:]) else "exception"
            self.fail(kind, "uncaught: " + sig, str(e), cards, tb=tb)
            outcome = "crash"
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
            root.removeHandler(handler)
            uuid.uuid4 = orig_uuid4
            gs.choose_action = orig_choose
        if any(f["kind"] == "timeout" for f in self.failures):
            outcome = "timeout"
        s = self.session
        result = (s.game_result if s is not None else None) or {}
        return {
            "seed": self.seed, "mode": self.mode, "decks": list(self.deck_ids),
            "outcome": outcome, "turns": self.turn(),
            "winner": {P1: "P1", P2: "P2"}.get(result.get("winner"), None),
            "reason": result.get("reason"), "seconds": round(time.time() - t0, 2),
            "main_offers": self.main_offers, "prompts": self.prompts,
            "prizes": {self.pname(pid): st.get("prizecardstaken", 0)
                       for pid, st in (s.game_stats.items() if s is not None else [])},
            "failures": self.failures, "warnings": dict(self.warnings),
        }


def _is_stadium_msg(msg: str) -> bool:
    du = load_engine()["du"]
    for u in UUID_RE.findall(msg):
        if isinstance(du.def_for(u.lower()), du.StadiumCardDef):
            return True
    return False


class _CaptureHandler(logging.Handler):
    """ERROR records (with or without traceback) become failures; WARNINGs
    are counted by normalized message."""

    def __init__(self, run: GameRun):
        super().__init__(level=logging.WARNING)
        self.run = run

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if record.levelno >= logging.ERROR:
            if record.exc_info and record.exc_info[1] is not None:
                et, ev, etb = record.exc_info
                if isinstance(ev, GameTimeout):
                    return
                frames = traceback.extract_tb(etb)
                sig, cards = tb_signature(et.__name__, frames)
                self.run.fail("exception", sig, f"{normalize_msg(msg)} | {et.__name__}: {ev}", cards,
                              tb="".join(traceback.format_exception(et, ev, etb)))
            else:
                self.run.fail("error_log", normalize_msg(msg), msg)
        else:
            if "has no scripted effect" in msg and _is_stadium_msg(msg):
                return  # 79 Stadiums are passive-only by design (game_session._execute_play_stadium)
            self.run.warnings[normalize_msg(name_guids(msg))] += 1
            if self.run.verbose:
                print(f"  [warn] {msg[:300]}", flush=True)


ACTION_WEIGHTS = {
    "DefaultPokemonPlayAbility": 3.0, "EvolvePokemonPlayAbility": 3.0,
    "DefaultEnergyPlayAbility": 3.0, "DefaultToolPlayAbility": 1.5,
    "UsePokemonAbility": 1.5, "UseTrainerCard": 1.0,
    "DefaultStadiumPlayAbility": 1.0, "BaseRetreat": 0.4, "UsePokemonAttack": 1.0,
}

PROMPT_NAMES = {
    "SelectionWithTargetsAndActionsRequired", "SelectionWithTargetsRequired",
    "CustomChoiceRequired", "CoinFlipChoiceRequired", "GoFirstChoiceRequired",
}


# ----------------------------------------------------------------------
# Batch driver
# ----------------------------------------------------------------------

_W: Dict[str, Any] = {}


def _init_worker(decks_path: str, mode: str, turn_cap: int):
    load_engine()
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(logging.NullHandler())
    root.setLevel(logging.WARNING)
    _W["decks"] = parse_decklists(decks_path)
    _W["ids"] = sorted(_W["decks"])
    _W["resolver"] = DeckResolver()
    _W["mode"] = mode
    _W["turn_cap"] = turn_cap


def deck_pair_for(seed: int, ids: List[int]) -> Tuple[int, int]:
    r = random.Random(seed * 104729 + 3)
    a, b = r.sample(ids, 2)
    return a, b


def mode_for(seed: int, mode: str) -> str:
    if mode != "rotate":
        return mode
    return ("net", "net", "mixed", "ai")[seed % 4]


def play_seed(seed: int, verbose: bool = False) -> Dict[str, Any]:
    decks, ids, resolver = _W["decks"], _W["ids"], _W["resolver"]
    a, b = deck_pair_for(seed, ids)
    da, db = resolver.resolve(a, decks[a]), resolver.resolve(b, decks[b])
    run = GameRun(seed, (a, b), (da, db), mode_for(seed, _W["mode"]), verbose=verbose,
                  turn_cap=_W["turn_cap"])
    try:
        return run.run()
    except BaseException as e:
        return {"seed": seed, "mode": run.mode, "decks": [a, b], "outcome": "crash", "turns": 0,
                "winner": None, "reason": None, "seconds": 0, "main_offers": 0, "prompts": 0,
                "failures": [{"kind": "harness", "signature": f"[harness] worker crash {type(e).__name__}",
                              "message": str(e), "cards": [], "turn": 0, "phase": "",
                              "recent": [], "traceback": traceback.format_exc()}],
                "warnings": {}}


def aggregate(results: List[Dict[str, Any]], out_dir: str, args) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    groups: Dict[str, Dict[str, Any]] = {}
    warnings: collections.Counter = collections.Counter()
    warn_games: collections.Counter = collections.Counter()
    outcomes = collections.Counter(r["outcome"] for r in results)
    for r in results:
        for w, c in (r.get("warnings") or {}).items():
            warnings[w] += c
            warn_games[w] += 1
        for f in r["failures"]:
            g = groups.setdefault(f["signature"], {
                "signature": f["signature"], "kind": f["kind"], "games": 0,
                "cards": collections.Counter(), "examples": []})
            g["games"] += 1
            for c in f["cards"]:
                g["cards"][c] += 1
            if len(g["examples"]) < 3:
                g["examples"].append({
                    "seed": r["seed"], "mode": r["mode"], "decks": r["decks"],
                    "turn": f["turn"], "message": f["message"], "recent": f["recent"],
                    "traceback": f["traceback"],
                    "replay": f"python3 -m spirit.tools.stress_bots --replay {r['seed']} --mode {r['mode']}"})
    ranked = sorted(groups.values(), key=lambda g: (-g["games"], g["signature"]))
    for g in ranked:
        g["cards"] = [c for c, _ in g["cards"].most_common(10)]
    # Coarser view: invariant name without the specific card.
    families: Dict[str, Dict[str, Any]] = {}
    for g in ranked:
        fam = re.sub(r":\s[^:]+$", "", g["signature"]) if g["kind"] == "invariant" else g["signature"]
        fam = re.sub(r"\((deck|hand|discard|prizePile|lostZone)\)", "(zone)", fam)
        f = families.setdefault(fam, {"family": fam, "games": 0, "signatures": []})
        f["games"] += g["games"]
        f["signatures"].append(g["signature"])
    finished = [r for r in results if r["outcome"] == "finished"]
    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "args": vars(args),
        "games": len(results),
        "outcomes": dict(outcomes),
        "avg_turns_finished": round(sum(r["turns"] for r in finished) / len(finished), 1) if finished else 0,
        "avg_turns_all": round(sum(r["turns"] for r in results) / len(results), 1) if results else 0,
        "avg_seconds": round(sum(r["seconds"] for r in results) / len(results), 2) if results else 0,
        "games_with_failures": sum(1 for r in results if r["failures"]),
        "win_reasons": dict(collections.Counter(normalize_msg(r["reason"] or "-") for r in results)),
        "families": sorted(families.values(), key=lambda f: -f["games"]),
        "signatures": ranked,
        "warnings": [{"message": w, "count": c, "games": warn_games[w]}
                     for w, c in warnings.most_common(60)],
        "games_detail": [{k: r[k] for k in ("seed", "mode", "decks", "outcome", "turns", "winner",
                                             "reason", "seconds")} |
                         {"failures": [f["signature"] for f in r["failures"]]} for r in results],
    }
    with open(os.path.join(out_dir, "report.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)
    lines = [
        f"Stress run {report['generated']}: {report['games']} games, outcomes {report['outcomes']}",
        f"avg turns (finished) {report['avg_turns_finished']}, avg {report['avg_seconds']}s/game, "
        f"{report['games_with_failures']} games with >=1 failure",
        "",
        "Failure signatures (games affected):",
    ]
    for g in ranked:
        ex = g["examples"][0]
        lines.append(f"  {g['games']:5d}  {g['signature']}")
        lines.append(f"         cards: {', '.join(g['cards'][:6]) or '-'}")
        lines.append(f"         e.g. seed {ex['seed']} mode {ex['mode']} decks {ex['decks']} turn {ex['turn']}: "
                     f"{ex['message'][:160]}")
    lines.append("")
    lines.append("Families (summed over card-specific signatures):")
    for f in report["families"]:
        lines.append(f"  {f['games']:5d}  {f['family']}  ({len(f['signatures'])} signature(s))")
    lines.append("")
    lines.append("Top engine warnings (count / games):")
    for w in report["warnings"][:25]:
        lines.append(f"  {w['count']:6d} / {w['games']:4d}  {w['message']}")
    with open(os.path.join(out_dir, "summary.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(out_dir, "results.jsonl"), "w") as fh:
        for r in results:
            fh.write(json.dumps(r, default=str) + "\n")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1, help="base seed; game i uses seed*100000+i")
    ap.add_argument("--replay", type=int, default=None, help="re-run one game seed verbosely")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--decks", default=DEFAULT_DECKS)
    ap.add_argument("--mode", default="net", choices=("net", "ai", "mixed", "rotate"))
    ap.add_argument("--minutes", type=float, default=None,
                    help="keep playing until this much wall time has passed (overrides --games)")
    ap.add_argument("--turn-cap", type=int, default=TURN_CAP)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--merge", action="store_true",
                    help="append to existing results.jsonl in --out before aggregating")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-aliases", action="store_true",
                    help="resolve decklists without NAME_ALIASES (reproduces the first run)")
    args = ap.parse_args(argv)
    global USE_ALIASES
    USE_ALIASES = not args.no_aliases

    if args.replay is not None:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
        _init_worker(args.decks, args.mode if args.mode != "rotate" else mode_for(args.replay, "rotate"),
                     args.turn_cap)
        a, b = deck_pair_for(args.replay, _W["ids"])
        for d in (a, b):
            info = _W["resolver"].resolve(d, _W["decks"][d])
            print(f"deck {d}: type {info['type']} notes: {info['notes']}")
        res = play_seed(args.replay, verbose=True)
        print(json.dumps({k: v for k, v in res.items() if k != "failures"}, indent=1, default=str))
        for f in res["failures"]:
            print(f"\n=== {f['signature']} (turn {f['turn']})\n{f['message']}\n{f['traceback']}")
        return 0

    load_engine()
    results: List[Dict[str, Any]] = []
    if args.merge and os.path.exists(os.path.join(args.out, "results.jsonl")):
        for line in open(os.path.join(args.out, "results.jsonl")):
            results.append(json.loads(line))
    done_seeds = {r["seed"] for r in results}
    deadline = time.time() + args.minutes * 60 if args.minutes else None
    total = 10 ** 9 if deadline else args.games
    seeds = (s for s in (args.seed * 100000 + i for i in range(total)) if s not in done_seeds)
    t0 = time.time()
    n = 0

    def report_progress(r):
        nonlocal n
        n += 1
        results.append(r)
        if not args.quiet:
            fl = ", ".join(f["signature"][:70] for f in r["failures"][:2])
            print(f"[{n}] seed {r['seed']} {r['mode']} decks {r['decks']} {r['outcome']} "
                  f"T{r['turns']} {r['seconds']}s {('FAIL: ' + fl) if fl else ''}", flush=True)
        if n % 50 == 0:
            aggregate(results, args.out, args)

    ctx = multiprocessing.get_context("fork")
    if args.workers <= 1:
        _init_worker(args.decks, args.mode, args.turn_cap)
        for s in seeds:
            if deadline and time.time() > deadline:
                break
            report_progress(play_seed(s))
    else:
        with ctx.Pool(args.workers, initializer=_init_worker,
                      initargs=(args.decks, args.mode, args.turn_cap),
                      maxtasksperchild=40) as pool:
            def bounded():
                for s in seeds:
                    if deadline and time.time() > deadline:
                        return
                    yield s
            for r in pool.imap_unordered(play_seed, bounded(), chunksize=1):
                report_progress(r)
                if deadline and time.time() > deadline + 300:
                    pool.terminate()
                    break
    rep = aggregate(results, args.out, args)
    print(open(os.path.join(args.out, "summary.txt")).read())
    print(f"wall {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
