"""Targeted bot-vs-bot stress test for Pokemon Dolls (Lillie's Poke Doll,
Robo Substitute) meeting Ability locks (Hex Maniac, Silent Lab, Path to the
Peak, Jamming Tower, Garbotoxin Garbodor).

Built on spirit/tools/stress_bots.py (same real-wire fake clients, invariant
checks, stall detection, seeded replay) with:

* a deck pool = every Limitless list holding a doll + "lock variants" of
  random lists with both dolls, Hex Maniac, a lock Stadium / Garbodor line,
  gust (Boss's Orders, Guzma, Counter Catcher), Scoop Up Net / Rescue
  Stretcher and Clefairy CEC 144 swapped in for non-essential Trainers;
* a doll-biased policy (bench dolls, put them away, gust them, target them
  with tools/attacks/recovery, promote them after KOs, play locks while a
  doll is in play);
* extra doll checks: a client-side model of each fake client (built only from
  SerializedGameState / EntityIntroduced / EntityMoved / AttributeModified)
  is compared with the server board at every prompt: zone desync, a doll in
  play that the client still types as Trainer, rule-action offers missing or
  wrongly offered, retreat/evolve offers on dolls, prizes taken for a doll,
  prompts with zero valid targets, re-offer warning loops, offers that loop
  without changing the board, prompts inside an open Start/StopSequence,
  AttributeModified for a card the viewer holds face-down / never saw;
* simulated reconnects (RECONNECT_RATE per main offer): the per-client sync
  caches are cleared and the client model is rebuilt from a fresh
  SerializedGameState before the pending offer is "replayed", as
  GameSession.reconnect_player / _resume_reconnect_cycle do.

Findings of the first run (2026-10-12) are pinned in
tests/test_doll_stress_findings.py.

Usage (repo root, PYTHONPATH=/home/claude/stubs:.):
  python3 -m spirit.tools.stress_dolls --build-pool
  python3 -m spirit.tools.stress_dolls --games 1000 --workers 4 --seed 31
  python3 -m spirit.tools.stress_dolls --replay 3100017 [--mode net]
"""

import os
import sys

if __name__ == "__main__" and os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-m", "spirit.tools.stress_dolls"] + sys.argv[1:])

import argparse
import asyncio
import collections
import json
import logging
import multiprocessing
import random
import re
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

from spirit.tools import stress_bots as sb

OUT_DIR = "/home/claude/bughunt/stress_doll"
POOL_PATH = os.path.join(OUT_DIR, "doll_pool.txt")

# Limitless "Robo Substitute PHF 102" -> engine display name.
sb.NAME_ALIASES.setdefault("Robo Substitute", "Robo Substitute Team Flare Gear")  # older stress_bots

LILLIE = "Lillie's Poké Doll"
ROBO = "Robo Substitute Team Flare Gear"
DOLL_NAMES = {LILLIE, ROBO, "Snorlax Doll"}
LOCK_TRAINERS = {"Hex Maniac", "Silent Lab", "Path to the Peak", "Jamming Tower"}
LOCK_POKEMON = {"Garbodor", "Galarian Weezing", "Trubbish"}
GUST = {"Boss's Orders", "Guzma", "Counter Catcher", "Lysandre", "Pokémon Catcher",
        "Guzma & Hala", "Cross Switcher", "Great Catcher", "Escape Rope"}
RECOVERY = {"Scoop Up Net", "Rescue Stretcher", "Night Stretcher", "Super Rod",
            "Scoop Up Cyclone", "AZ", "Acerola", "Super Scoop Up", "Pal Pad"}
SWITCHERS = {"Switch", "Escape Rope", "Float Stone", "Switch Cart", "Escape Board",
             "Air Balloon", "U-Turn Board", "Guzma", "Cross Switcher"}
TOOL_REMOVERS = {"Field Blower", "Tool Scrapper", "Tool Jammer"}

# Lines swapped into "lock variants" (Limitless spelling, resolvable names).
VARIANT_CORE = [
    (2, "Lillie's Poké Doll", "CEC", "197"),
    (2, "Robo Substitute", "PHF", "102"),
    (2, "Hex Maniac", "AOR", "75"),
]
VARIANT_LOCKS = [
    [(2, "Silent Lab", "PRC", "140")],
    [(2, "Path to the Peak", "CRE", "148")],
    [(2, "Jamming Tower", "TEU", "153")],
    [(2, "Trubbish", "BKP", "56"), (2, "Garbodor", "BKP", "57")],
]
VARIANT_TOOLS = [
    (1, "Boss's Orders", "RCL", "154"),
    (1, "Guzma", "BUS", "115"),
    (1, "Counter Catcher", "CIN", "91"),
    (1, "Scoop Up Net", "RCL", "165"),
    (1, "Rescue Stretcher", "GRI", "130"),
    (1, "Clefairy", "CEC", "144"),
    (1, "Field Blower", "GRI", "125"),
]


# ----------------------------------------------------------------------
# Deck pool
# ----------------------------------------------------------------------

def _card_kind(resolver, name: str, num: str) -> str:
    du = sb.load_engine()["du"]
    name = sb.NAME_ALIASES.get(name, name)
    cands = resolver.by_name_num.get((name, re.sub(r"\D", "", num))) or resolver.by_name.get(name) or []
    if not cands:
        if resolver._basic_energy_type(name) is not None:
            return "energy"
        return "unknown"
    d = cands[0]
    if isinstance(d, du.PokemonCardDef):
        return "pokemon"
    if isinstance(d, du.EnergyCardDef):
        return "energy"
    if isinstance(d, du.SupporterCardDef):
        return "supporter"
    if isinstance(d, du.StadiumCardDef):
        return "stadium"
    return "item"


def has_doll(lines) -> bool:
    return any(sb.NAME_ALIASES.get(n, n) in DOLL_NAMES for _, n, _, _ in lines)


def make_variant(lines, resolver, rng: random.Random, add: List[Tuple]) -> List[Tuple]:
    """Replace non-essential Trainer lines with `add` (60 cards kept)."""
    need = sum(c for c, *_ in add)
    add_names = {n for _, n, _, _ in add}
    out = [l for l in lines if l[1] not in add_names]
    removable = [i for i, l in enumerate(out)
                 if _card_kind(resolver, l[1], l[3]) in ("item", "stadium", "supporter")
                 and sb.NAME_ALIASES.get(l[1], l[1]) not in DOLL_NAMES
                 and l[1] not in ("Professor's Research", "Quick Ball", "Ultra Ball",
                                  "Nest Ball", "Level Ball", "Rare Candy", "Arven",
                                  "Iono", "Cynthia", "N", "Professor Sycamore")]
    rng.shuffle(removable)
    total = sum(l[0] for l in out)
    drop = set()
    for i in removable:
        if total - need >= 60 or total + need <= 60:
            break
        drop.add(i)
        total -= out[i][0]
    out = [l for i, l in enumerate(out) if i not in drop]
    # still over? trim energy / other lines from the end
    total = sum(l[0] for l in out) + need
    while total > 60 and out:
        c, n, s, num = out[-1]
        if c > 1:
            out[-1] = (c - 1, n, s, num)
        else:
            out.pop()
        total -= 1
    return out + list(add)


def build_pool(src: str, dst: str, n_variants: int = 160, seed: int = 4242) -> Dict[str, Any]:
    decks = sb.parse_decklists(src)
    resolver = sb.DeckResolver()
    rng = random.Random(seed)
    out_decks: Dict[int, List[Tuple]] = {}
    meta: Dict[int, str] = {}
    doll_ids = [d for d, lines in decks.items() if has_doll(lines)]
    for d in doll_ids:
        out_decks[d] = decks[d]
        meta[d] = "limitless-doll"
    # Doll decks + an Ability lock.
    nid = 5000
    for d in doll_ids:
        add = list(rng.choice(VARIANT_LOCKS)) + [(1, "Hex Maniac", "AOR", "75")]
        if not any(n == "Robo Substitute" for _, n, _, _ in decks[d]):
            add.append((1, "Robo Substitute", "PHF", "102"))
        out_decks[nid] = make_variant(decks[d], resolver, rng, add)
        meta[nid] = f"doll+lock of {d}"
        nid += 1
    others = [d for d in sorted(decks) if d not in doll_ids]
    for d in rng.sample(others, min(n_variants, len(others))):
        add = list(VARIANT_CORE) + list(rng.choice(VARIANT_LOCKS)) \
            + rng.sample(VARIANT_TOOLS, 4)
        out_decks[nid] = make_variant(decks[d], resolver, rng, add)
        meta[nid] = f"variant of {d}"
        nid += 1
    with open(dst, "w", encoding="utf-8") as fh:
        for d, lines in out_decks.items():
            fh.write(f"=== DECK {d}\n")
            for c, n, s, num in lines:
                fh.write(f"{c} {n} {s} {num}\n")
    with open(dst + ".meta.json", "w") as fh:
        json.dump({str(k): v for k, v in meta.items()}, fh, indent=0)
    # resolution sanity
    unresolved = collections.Counter()
    for d, lines in out_decks.items():
        r = resolver.resolve(d, lines)
        for n in r["notes"]:
            if n.startswith("UNRESOLVED"):
                unresolved[n] += 1
    return {"decks": len(out_decks), "limitless_doll_decks": len(doll_ids),
            "unresolved": unresolved.most_common(20)}


# ----------------------------------------------------------------------
# Client model (what a fake client knows, from the wire only)
# ----------------------------------------------------------------------

CARD_TYPE = 200300
NAME_ATTR = 10140
POKEMON_T, TRAINER_T = 0, 2


class ClientModel:
    def __init__(self):
        self.parent: Dict[str, Optional[str]] = {}
        self.attrs: Dict[str, Dict[int, Any]] = collections.defaultdict(dict)
        self.ename: Dict[str, str] = {}
        self.zone_name: Dict[str, str] = {}
        self.introduced: set = set()

    def _attrs(self, eid, lst):
        for a in lst or []:
            if isinstance(a, dict) and "name" in a:
                self.attrs[eid][a["name"]] = a.get("value")
                if a["name"] == NAME_ATTR and isinstance(a.get("value"), dict):
                    self.zone_name.setdefault(eid, a["value"].get("id"))

    def load_tree(self, node, parent=None):
        eid = node.get("entityID")
        self.parent[eid] = node.get("parentID", parent)
        self.ename[eid] = node.get("entityName") or ""
        if node.get("attributes") is not None:
            self.introduced.add(eid)
        else:
            self.introduced.discard(eid)
        self._attrs(eid, node.get("attributes"))
        if "PlayArea" in self.ename[eid]:
            n = self.attrs[eid].get(NAME_ATTR)
            self.zone_name[eid] = n.get("id") if isinstance(n, dict) else n
        for ch in node.get("children") or []:
            self.load_tree(ch, eid)

    def apply(self, name, value):
        if name == "SerializedGameState":
            self.parent.clear(); self.attrs.clear(); self.ename.clear(); self.zone_name.clear()
            self.introduced.clear()
            self.load_tree(value.get("entities") or {})
        elif name == "EntityIntroduced":
            eid = value.get("entityID")
            if value.get("entityName"):
                self.ename[eid] = value["entityName"]
            self.introduced.add(eid)
            self._attrs(eid, value.get("attributeMap"))
        elif name == "EntityMoved":
            self.parent[value.get("entityID")] = value.get("destinationID")
        elif name == "AttributesReset":
            self.introduced.discard(value.get("entityID"))
        elif name == "AttributeModified":
            a = value.get("attribute") or {}
            self.attrs[value.get("entityID")][a.get("name")] = a.get("value")

    def zone_of(self, eid) -> Optional[str]:
        seen = 0
        cur = self.parent.get(eid)
        while cur is not None and seen < 12:
            if cur in self.zone_name:
                return self.zone_name[cur]
            cur = self.parent.get(cur)
            seen += 1
        return None


# ----------------------------------------------------------------------
# Doll-aware game run
# ----------------------------------------------------------------------

STAT_KEYS = (
    "doll_benched", "doll_put_away_offered", "doll_put_away_used", "robo_discard_used",
    "doll_active_offers", "offers_lock_with_doll", "hex_with_doll", "lock_stadium_with_doll",
    "gust_doll", "doll_promoted", "doll_ko", "doll_ko_last_pokemon", "doll_tool",
    "recovery_on_doll", "attack_into_doll", "clefairy_doll_swap", "doll_in_play_offers",
    "sudden_death",
)


class DollRun(sb.GameRun):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.stats: collections.Counter = collections.Counter()
        self.cm = {sb.P1: ClientModel(), sb.P2: ClientModel()}
        self.last_main_sig: Dict[str, Any] = {}
        self.same_offer_streak = 0
        self.reoffer_per_turn: collections.Counter = collections.Counter()
        self.doll_wire: List[str] = []

    # -- helpers -----------------------------------------------------------
    def is_doll(self, ent_or_id) -> bool:
        board = self.session.board_state
        return sb.card_name(board, ent_or_id) in DOLL_NAMES

    def dolls_in_play(self, pid=None):
        board = self.session.board_state
        out = []
        for p in (self.session.players if pid is None else [pid]):
            out += [c for c in board.pokemon_in_play(p) if self.is_doll(c)]
        return out

    def lock_state(self) -> str:
        """Readable summary of Ability locks currently on the board."""
        board = self.session.board_state
        bits = []
        st = board.find_global_area("activeStadium")
        for c in (st.children if st else []):
            n = sb.card_name(board, c)
            if n in LOCK_TRAINERS:
                bits.append(n)
        ts = board.turn_state if hasattr(board, "turn_state") else None
        ts = ts or getattr(self.session, "turn_state", None)
        if ts is not None and ts.turn_number <= getattr(ts, "abilities_disabled_through_turn", 0):
            bits.append("Hex Maniac")
        for pid in self.session.players:
            for p in board.pokemon_in_play(pid):
                if sb.card_name(board, p) in ("Garbodor", "Galarian Weezing"):
                    bits.append(sb.card_name(board, p))
        return ",".join(bits)

    def entry_ability_title(self, entry) -> str:
        ab = sb.load_engine()["du"].ABILITIES_BY_ID.get(entry["selectableAction"]["actionID"])
        return getattr(ab, "title", "") or ""

    # -- wire -----------------------------------------------------------------
    def on_packet(self, account_id, packet):
        if packet.get("messageName") == "SequenceMessage":
            msg = packet.get("msg") or {}
            name, value = msg.get("name"), msg.get("value") or {}
            try:
                self.check_wire_generic(account_id, name, value)
                self.cm[account_id].apply(name, value)
                if name in sb.PROMPT_NAMES:
                    self.check_prompt_wire(account_id, name, value)
                self.watch_doll_msgs(account_id, name, value)
            except sb.GameTimeout:
                raise
            except Exception as e:
                self.fail("harness", f"doll wire check crashed: {type(e).__name__}", str(e),
                          tb=traceback.format_exc())
        super().on_packet(account_id, packet)

    HIDDEN_FOR_OWNER = ("deck", "prizePile")
    PUBLIC = ("activePokemonArea", "bench", "discard", "lostZone", "activeStadium",
              "activeTrainer", "outOfPlay", "revealArea", "stadium")

    def _hidden_for(self, pid, eid) -> Optional[str]:
        """Zone name if `eid` sits in a zone hidden from viewer `pid` (client view)."""
        cm = self.cm[pid]
        zone = cm.zone_of(eid)
        if zone is None:
            return None
        # owner of the zone: walk to the PlayArea and ask the server board
        board = self.session.board_state if self.session else None
        cur = cm.parent.get(eid)
        area = None
        while cur is not None:
            if cur in cm.zone_name:
                area = cur
                break
            cur = cm.parent.get(cur)
        ent = board.get_entity(area) if (board is not None and area) else None
        owner = getattr(ent, "owning_player_id", None)
        if zone in self.HIDDEN_FOR_OWNER:
            return zone
        if zone == "hand" and owner is not None and owner != pid:
            return "opp-hand"
        return None

    def check_wire_generic(self, pid, name, value):
        """Wire-shape checks the real client is sensitive to."""
        st = self.__dict__.setdefault("_seq_stack", {sb.P1: [], sb.P2: []})[pid]
        if name == "StartSequence":
            st.append(value.get("name"))
            return
        if name == "StopSequence":
            if not st or st[-1] != value.get("name"):
                self.fail("client", f"unbalanced StopSequence {value.get('name')}",
                          f"stack {st}", [])
            if st:
                st.pop()
            return
        if name in sb.PROMPT_NAMES and st:
            self.fail("client", f"prompt {name} inside open sequence {st[-1]}",
                      f"stack {st}", [])
        if self.session is None:
            return
        eid = value.get("entityID") if isinstance(value, dict) else None
        if name in ("AttributeModified", "EntityMoved") and isinstance(eid, str):
            cm = self.cm[pid]
            board = self.session.board_state
            if eid not in cm.parent:
                ent = board.get_entity(eid)
                nm = sb.card_name(board, ent) if ent is not None else eid[:8]
                self.fail("client", f"{name} for entity unknown to client",
                          f"{nm} viewer {self.pname(pid)}", [nm])
                return
            if name == "AttributeModified" and eid not in cm.introduced \
                    and "PlayArea" not in cm.ename.get(eid, "PlayArea") \
                    and "Player" not in cm.ename.get(eid, "") and "PlayMat" not in cm.ename.get(eid, ""):
                ent = board.get_entity(eid)
                nm = sb.card_name(board, ent) if ent is not None else eid[:8]
                attr = (value.get("attribute") or {}).get("name")
                self.fail("client", f"AttributeModified {attr} for un-introduced card",
                          f"{nm} viewer {self.pname(pid)} zone {cm.zone_of(eid)}", [nm])
            if name == "AttributeModified":
                hz = self._hidden_for(pid, eid)
                if hz:
                    ent = board.get_entity(eid)
                    nm = sb.card_name(board, ent) if ent is not None else eid[:8]
                    attr = (value.get("attribute") or {}).get("name")
                    key = f"attr_on_hidden:{'doll' if ent is not None and self.is_doll(ent) else 'other'}:{attr}"
                    self.stats[key] += 1
                    if ent is not None and self.is_doll(ent):
                        self.fail("client", f"AttributeModified {attr} for doll in hidden zone ({hz})",
                                  f"{nm} viewer {self.pname(pid)} zone {hz}; recent wire: {self.doll_wire[-4:]}",
                                  [nm])
                    else:
                        self.fail("client", f"AttributeModified {attr} for card in hidden zone ({hz})",
                                  f"{nm} viewer {self.pname(pid)}", [nm])

    def watch_doll_msgs(self, pid, name, value):
        if self.session is None or pid != sb.P1:
            return
        eid = value.get("entityID")
        if not eid or not isinstance(eid, str):
            return
        board = self.session.board_state
        if board.get_entity(eid) is None or not self.is_doll(eid):
            return
        if name == "EntityMoved":
            dest = self.cm[pid].zone_name.get(value.get("destinationID")) or \
                self.cm[pid].zone_of(value.get("destinationID")) or value.get("destinationID", "")[:8]
            self.doll_wire.append(f"T{self.turn()} move {sb.card_name(board, eid)} -> {dest}")
        elif name == "AttributeModified":
            a = value.get("attribute") or {}
            if a.get("name") == CARD_TYPE:
                self.doll_wire.append(f"T{self.turn()} CARD_TYPE {sb.card_name(board, eid)} = {a.get('value')}")

    def _server_zone(self, ent) -> Optional[str]:
        from spirit.game.models.board import PlayArea
        from spirit.game.attributes import AttrID
        cur = ent.parent
        while cur is not None:
            if isinstance(cur, PlayArea):
                return cur.get_attribute(AttrID.NAME)
            cur = cur.parent
        return None

    def check_prompt_wire(self, pid, name, value):
        """Wire-level doll checks at the moment a prompt reaches a client."""
        s = self.session
        if s is None:
            return
        board = s.board_state
        cm = self.cm[pid]
        # 1) every doll in play (both sides) must be typed Pokemon on this client
        #    and sit in the same zone the server has it in.
        for d in self.dolls_in_play():
            nm = sb.card_name(board, d)
            ctype = cm.attrs.get(d.entity_id, {}).get(CARD_TYPE)
            szone = self._server_zone(d)
            czone = cm.zone_of(d.entity_id)
            if czone != szone:
                if name == "SelectionWithTargetsAndActionsRequired":
                    self.fail("client", "doll zone desync at main offer",
                              f"{nm} server zone {szone} client({self.pname(pid)}) zone {czone}", [nm])
                else:
                    # Mid-effect prompt while the effect's choreography is
                    # still queued (Guzma: gust move is sent after the
                    # "choose your new Active" prompt).  Informational.
                    self.stats["doll_zone_lag_at_prompt"] += 1
            if ctype != POKEMON_T and name == "SelectionWithTargetsAndActionsRequired":
                self.fail("client", f"doll in play typed {ctype} on client at main offer",
                          f"{nm} in {szone}; client({self.pname(pid)}) CARD_TYPE={ctype}", [nm])
            elif ctype != POKEMON_T:
                self.stats["doll_trainer_typed_at_prompt"] += 1
                self.fail("client", f"doll in play still typed Trainer on client at {name}",
                          f"{nm} in {szone}; client({self.pname(pid)}) CARD_TYPE={ctype}; "
                          f"prompt={json.dumps(value)[:400]}", [nm])
        # 1b) at a main offer every card in play must be where the client has it
        if name == "SelectionWithTargetsAndActionsRequired":
            from spirit.game.models.board import CompositePokemonEntity
            for p in list(s.players):
                for mon in board.pokemon_in_play(p):
                    if isinstance(mon, CompositePokemonEntity):
                        continue
                    szone, czone = self._server_zone(mon), cm.zone_of(mon.entity_id)
                    if szone != czone:
                        nm = sb.card_name(board, mon)
                        self.fail("client", f"in-play zone desync at main offer"
                                  f"{' (doll)' if self.is_doll(mon) else ''}",
                                  f"{nm} server {szone} client({self.pname(pid)}) {czone}", [nm])
        # 2) prompts whose targets are all empty although a pick is required
        if name == "SelectionWithTargetsRequired":
            tmap = value.get("targetMap") or {}
            ttype = value.get("targetType")
            for src, nodes in tmap.items():
                for node in nodes or []:
                    inner = (node.get("selections") or [node])
                    valid = [t for sel in inner for t in (sel.get("validTargets") or [])]
                    mn = node.get("minimumToSelect", inner[0].get("minimumToSelect", 0) if inner else 0)
                    has_choice = "titles" in node or "choices" in node or node.get("name") == \
                        "MultiSelectEntityListTargetInformation"
                    if not valid and not has_choice and isinstance(mn, int) and mn > 0:
                        self.fail("prompt", f"required pick with zero valid targets ({ttype})",
                                  json.dumps(value)[:800],
                                  [sb.card_name(board, src)])
                    for t in valid:
                        if board.get_entity(t) is None:
                            self.fail("prompt", "prompt target not on server board",
                                      f"{t} in {ttype}", [])
            # doll offered as a setup placement (Items can't be placed in setup)
            if ttype == sb.load_engine()["SelectionKind"].INITIAL_BENCHED.value or \
                    "Basic Pok" in str((value.get("prompt") or {}).get("id")) and s.turn_state.turn_number == 0:
                for k in tmap:
                    if board.get_entity(k) is not None and self.is_doll(k):
                        self.fail("rules", "doll offered in setup placement",
                                  f"{sb.card_name(board, k)} offered by {value.get('prompt')}",
                                  [sb.card_name(board, k)])

    # -- main-offer checks ---------------------------------------------------------
    def check_main_offer(self, pid, target_map):
        la = sb.load_engine()["la"]
        s = self.session
        board = s.board_state
        lock = self.lock_state()
        mine = self.dolls_in_play(pid)
        if mine or self.dolls_in_play():
            self.stats["doll_in_play_offers"] += 1
            if lock:
                self.stats["offers_lock_with_doll"] += 1
        active = board.active_pokemon(pid)
        attacked = bool(getattr(s.turn_state, "attacks_used", None))
        by_entity = collections.defaultdict(list)
        for e in target_map:
            by_entity[e["entityID"]].append(e)
        for d in mine:
            nm = sb.card_name(board, d)
            entries = by_entity.get(d.entity_id, [])
            rule = [e for e in entries if e["selectableAction"]["description"] == la.ACTION_USE_ABILITY
                    and self.entry_ability_title(e) in ("Put Lillie's Poké Doll Away", "Discard Robo Substitute",
                                                        "Discard Snorlax Doll")]
            should = not attacked and (nm != LILLIE or d is active)
            if rule:
                self.stats["doll_put_away_offered"] += 1
            if should and not rule:
                self.fail("rules", f"doll rule action not offered ({'locked' if lock else 'no lock'})",
                          f"{nm} ({'Active' if d is active else 'Bench'}) lock=[{lock}] offered for it: "
                          f"{[e['selectableAction']['description'] + ':' + self.entry_ability_title(e) for e in entries]}",
                          [nm] + ([lock] if lock else []))
            if rule and nm == LILLIE and d is not active:
                self.fail("rules", "Lillie's Doll put-away offered from Bench",
                          f"lock=[{lock}]", [nm])
            if d is active:
                self.stats["doll_active_offers"] += 1
                for e in target_map:
                    if e["selectableAction"]["description"] == "BaseRetreat":
                        self.fail("rules", f"retreat offered with doll Active: {nm}",
                                  json.dumps(e)[:400], [nm])
            for e in target_map:
                if e["selectableAction"]["description"] == "EvolvePokemonPlayAbility":
                    for info in e.get("targetInfoLst") or []:
                        if d.entity_id in (info.get("validTargets") or []):
                            self.fail("rules", f"evolution onto doll offered: {nm}",
                                      f"{sb.card_name(board, e['entityID'])} -> {nm}", [nm])
        # opponent's doll rule action must never be offered to me
        for d in self.dolls_in_play(s._opponent_id(pid)):
            for e in by_entity.get(d.entity_id, []):
                self.fail("rules", "opponent's doll action offered",
                          f"{sb.card_name(board, d)}: {e['selectableAction']['description']}",
                          [sb.card_name(board, d)])
        # offers that repeat with an unchanged board after an action
        sig = (tuple(sorted((e["entityID"], e["selectableAction"]["actionID"]) for e in target_map)),
               self.board_sig())
        if self.last_main_sig.get(pid) == sig:
            self.same_offer_streak += 1
            if self.same_offer_streak >= 6:
                last = [l for l in self.recent][-6:]
                self.fail("loop", "same offer re-sent 6x with unchanged board",
                          f"lock=[{lock}] last actions: {last}",
                          [x.split(': ', 1)[-1].split(' ->')[0] for x in last if ': ' in x][:3])
        else:
            self.same_offer_streak = 0
        self.last_main_sig[pid] = sig

    def board_sig(self):
        from spirit.game.attributes import AttrID
        board = self.session.board_state
        out = []
        for pid in self.session.players:
            for zone in ("hand", "deck", "discard", "prizePile", "lostZone", "bench", "activePokemonArea"):
                a = board.find_player_area(pid, zone)
                out.append(len(a.children) if a else -1)
            for p in board.pokemon_in_play(pid):
                out.append((p.entity_id, p.get_attribute(AttrID.HP), len(p.children),
                            str(p.get_attribute(AttrID.SPECIAL_CONDITIONS))))
        st = board.find_global_area("activeStadium")
        out.append(tuple(c.entity_id for c in (st.children if st else [])))
        return tuple(out)

    RECONNECT_RATE = 0.02

    def simulate_reconnect(self, pid, value):
        """What GameSession.reconnect_player + _resend_state_to +
        _resume_reconnect_cycle do to one client, minus the socket: reset
        the per-client sync caches, install a SerializedGameState snapshot,
        then replay the pending offer unchanged."""
        s = self.session
        board = s.board_state
        s._energy_display_sent = {}
        s._fossil_type_sent = set()
        snap = board.serialize(pid)
        self.cm[pid].apply("SerializedGameState", {"entities": snap.get("entities", snap)})
        self.stats["reconnects"] += 1
        if self.dolls_in_play():
            self.stats["reconnects_with_doll"] += 1
        for d in self.dolls_in_play():
            ctype = self.cm[pid].attrs.get(d.entity_id, {}).get(CARD_TYPE)
            if ctype != POKEMON_T:
                nm = sb.card_name(board, d)
                self.fail("client", "doll in play typed Trainer after reconnect (replayed offer)",
                          f"{nm} in {self._server_zone(d)}; snapshot CARD_TYPE={ctype}; "
                          f"viewer {self.pname(pid)}", [nm])

    def answer_main(self, pid, value):
        try:
            if self.RECONNECT_RATE and self.rng.random() < self.RECONNECT_RATE:
                self.simulate_reconnect(pid, value)
            self.check_main_offer(pid, value.get("targetMap") or [])
        except sb.GameTimeout:
            raise
        except Exception as e:
            self.fail("harness", f"doll main check crashed: {type(e).__name__}", str(e),
                      tb=traceback.format_exc())
        return super().answer_main(pid, value)

    def ai_choose_action(self, session, player_id, target_map):
        try:
            self.check_main_offer(player_id, target_map)
        except sb.GameTimeout:
            raise
        except Exception as e:
            self.fail("harness", f"doll main check crashed: {type(e).__name__}", str(e),
                      tb=traceback.format_exc())
        return super().ai_choose_action(session, player_id, target_map)

    # -- doll-biased policy ----------------------------------------------------------
    def pick_main(self, pid, target_map, source_id=None):
        la = sb.load_engine()["la"]
        board = self.session.board_state
        if source_id:
            subset = [e for e in target_map if e["entityID"] == source_id]
            target_map = subset or target_map
        if not target_map:
            return None
        turn = self.turn()
        k = self.actions_this_turn[(pid, turn)]
        if self.rng.random() < min(0.85, 0.02 + 0.02 * k):
            return None
        opp = self.session._opponent_id(pid)
        opp_dolls = self.dolls_in_play(opp)
        any_doll = bool(self.dolls_in_play())
        opp_active = board.active_pokemon(opp)
        weights = []
        for e in target_map:
            desc = e["selectableAction"]["description"]
            w = sb.ACTION_WEIGHTS.get(desc, 1.0) * self._self_ko_damping(pid, e)
            nm = sb.card_name(board, e["entityID"])
            title = self.entry_ability_title(e)
            if nm in DOLL_NAMES and desc != la.ACTION_USE_ABILITY:
                w *= 8.0                      # bench a doll
            if title in ("Put Lillie's Poké Doll Away", "Discard Robo Substitute"):
                w *= 2.5
            if nm in LOCK_TRAINERS and any_doll:
                w *= 6.0
            if nm in GUST and opp_dolls:
                w *= 5.0
            if nm in RECOVERY or nm in SWITCHERS or nm in TOOL_REMOVERS:
                w *= 2.0 if any_doll else 1.0
            if nm == "Clefairy":
                w *= 3.0
            if desc == la.ACTION_USE_ATTACK and opp_active is not None and self.is_doll(opp_active):
                w *= 4.0
            weights.append(w)
        entry = self.rng.choices(target_map, weights=weights)[0]
        self.actions_this_turn[(pid, turn)] += 1
        responses = [self.target_response(info) for info in (entry.get("targetInfoLst") or [])]
        desc = entry["selectableAction"]["description"]
        if desc == la.ACTION_PLAY_ENERGY and responses and self.rng.random() < 0.5:
            active = board.active_pokemon(pid)
            valid = (entry.get("targetInfoLst") or [{}])[0].get("validTargets") or []
            if active is not None and active.entity_id in valid:
                responses[0] = {"entityList": [active.entity_id]}
        self.note_action_stats(pid, entry, responses)
        self.log_action(pid, entry, responses)
        return entry, responses

    def note_action_stats(self, pid, entry, responses):
        la = sb.load_engine()["la"]
        board = self.session.board_state
        nm = sb.card_name(board, entry["entityID"])
        desc = entry["selectableAction"]["description"]
        title = self.entry_ability_title(entry)
        tgts = [t for r in responses if isinstance(r, dict) for t in (r.get("entityList") or [])]
        tdoll = any(board.get_entity(t) is not None and self.is_doll(t) for t in tgts)
        any_doll = bool(self.dolls_in_play())
        if nm in DOLL_NAMES and desc != la.ACTION_USE_ABILITY:
            self.stats["doll_benched"] += 1
        if title == "Put Lillie's Poké Doll Away":
            self.stats["doll_put_away_used"] += 1
        if title == "Discard Robo Substitute":
            self.stats["robo_discard_used"] += 1
        if nm == "Hex Maniac" and any_doll:
            self.stats["hex_with_doll"] += 1
        if nm in ("Silent Lab", "Path to the Peak", "Jamming Tower") and any_doll:
            self.stats["lock_stadium_with_doll"] += 1
        if nm in GUST and tdoll:
            self.stats["gust_doll"] += 1
        if nm in RECOVERY and tdoll:
            self.stats["recovery_on_doll"] += 1
        if desc == "DefaultToolPlayAbility" and tdoll:
            self.stats["doll_tool"] += 1
        if nm == "Clefairy" and desc == la.ACTION_USE_ATTACK:
            self.stats["clefairy_doll_swap"] += 1
        if desc == la.ACTION_USE_ATTACK:
            opp_active = board.active_pokemon(self.session._opponent_id(pid))
            if opp_active is not None and self.is_doll(opp_active):
                self.stats["attack_into_doll"] += 1

    def _pick_count(self, valid, number, minimum):
        picks = super()._pick_count(valid, number, minimum)
        s = self.session
        if s is None or not picks:
            return picks
        board = s.board_state
        dolls = [v for v in valid if isinstance(v, str) and board.get_entity(v) is not None
                 and self.is_doll(v)]
        if dolls and not any(p in dolls for p in picks) and self.rng.random() < 0.6:
            picks[0] = self.rng.choice(dolls)
        return picks

    def answer_prompt(self, pid, name, value):
        SK = sb.load_engine()["SelectionKind"]
        if name == "SelectionWithTargetsRequired" and value.get("targetType") == SK.KNOCKOUT_POKEMON.value:
            tmap = value.get("targetMap") or {}
            board = self.session.board_state
            dolls = [k for k in tmap if board.get_entity(k) is not None and self.is_doll(k)]
            if dolls and all(not v for v in tmap.values()) and self.rng.random() < 0.6:
                pick = self.rng.choice(dolls)
                self.stats["doll_promoted"] += 1
                self.log(f"{self.pname(pid)} promote -> {sb.card_name(board, pick)}")
                return {"selection": {"entityID": pick}, "counter": value.get("counter")}
        reply = super().answer_prompt(pid, name, value)
        try:
            self._note_prompt_stats(value, reply)
        except Exception:
            pass
        return reply

    def _note_prompt_stats(self, value, reply):
        board = self.session.board_state
        sel = (reply or {}).get("selection")
        if not isinstance(sel, dict):
            return
        picks = [t for r in sel.get("targetResponses") or [] if isinstance(r, dict)
                 for t in (r.get("entityList") or [])]
        if not any(board.get_entity(t) is not None and self.is_doll(t) for t in picks):
            return
        tmap = value.get("targetMap") or {}
        src = value.get("sourceID") or (next(iter(tmap)) if tmap else None)
        nm = sb.card_name(board, src) if src else ""
        if nm in GUST:
            self.stats["gust_doll"] += 1
        elif nm in RECOVERY:
            self.stats["recovery_on_doll"] += 1
        elif nm in SWITCHERS:
            self.stats["switch_doll"] += 1
        elif nm in TOOL_REMOVERS:
            self.stats["tool_remove_on_doll"] += 1
        else:
            self.stats["other_prompt_pick_doll"] += 1

    # -- session hooks --------------------------------------------------------------
    def build_session(self):
        session = super().build_session()
        run = self
        orig_rk = session.resolve_knockouts

        async def resolve_knockouts(ctx, _ko_depth=0):
            board = session.board_state
            kos = [p for p in list(ctx.knockouts) if ctx.pokemon_is_in_play(p)]
            dolls = [p for p in kos if run.is_doll(p)]
            before = {pid: len(board.find_player_area(pid, "prizePile").children)
                      for pid in session.players}
            last = {}
            for d in dolls:
                owner = d.owning_player_id
                run.stats["doll_ko"] += 1
                if len(board.pokemon_in_play(owner)) == 1:
                    run.stats["doll_ko_last_pokemon"] += 1
                    last[owner] = True
            try:
                return await orig_rk(ctx, _ko_depth)
            finally:
                if dolls and len(dolls) == len(kos):
                    for d in dolls:
                        opp = session._opponent_id(d.owning_player_id) if d.owning_player_id else None
                        if opp and len(board.find_player_area(opp, "prizePile").children) < before[opp]:
                            nm = sb.card_name(board, d)
                            run.fail("rules", f"prize taken for KO'd doll: {nm}",
                                     f"{run.pname(opp)} prizes {before[opp]} -> "
                                     f"{len(board.find_player_area(opp, 'prizePile').children)}", [nm])
        session.resolve_knockouts = resolve_knockouts
        orig_sd = getattr(session, "_reset_sudden_death_round", None)
        if orig_sd is not None:
            async def sudden(*a, **kw):
                run.stats["sudden_death"] += 1
                return await orig_sd(*a, **kw)
            session._reset_sudden_death_round = sudden
        return session

    def run(self):
        res = super().run()
        # repeated re-offer warnings = client was re-prompted in a loop
        for w, c in (res.get("warnings") or {}).items():
            if "re-offer" in w.lower() and c >= 8:
                self.failures.append({
                    "kind": "loop", "signature": f"[loop] warning repeated {c}x: {w[:90]}",
                    "message": w, "cards": [], "turn": self.turn(), "phase": "",
                    "recent": list(self.recent), "traceback": ""})
        res["failures"] = self.failures
        res["doll_stats"] = dict(self.stats)
        res["doll_wire"] = self.doll_wire[-40:]
        return res


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

_W: Dict[str, Any] = {}


def _init_worker(decks_path, mode, turn_cap):
    sb._init_worker(decks_path, mode, turn_cap)
    _W.update(sb._W)


def play_seed(seed, verbose=False):
    decks, ids, resolver = _W["decks"], _W["ids"], _W["resolver"]
    a, b = sb.deck_pair_for(seed, ids)
    da, db = resolver.resolve(a, decks[a]), resolver.resolve(b, decks[b])
    run = DollRun(seed, (a, b), (da, db), sb.mode_for(seed, _W["mode"]), verbose=verbose,
                  turn_cap=_W["turn_cap"])
    try:
        return run.run()
    except BaseException as e:
        return {"seed": seed, "mode": run.mode, "decks": [a, b], "outcome": "crash", "turns": 0,
                "winner": None, "reason": None, "seconds": 0, "main_offers": 0, "prompts": 0,
                "failures": [{"kind": "harness", "signature": f"[harness] worker crash {type(e).__name__}",
                              "message": str(e), "cards": [], "turn": 0, "phase": "",
                              "recent": [], "traceback": traceback.format_exc()}],
                "warnings": {}, "doll_stats": {}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-pool", action="store_true")
    ap.add_argument("--games", type=int, default=50)
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--replay", type=int, default=None)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--decks", default=POOL_PATH)
    ap.add_argument("--mode", default="net", choices=("net", "ai", "mixed", "rotate"))
    ap.add_argument("--turn-cap", type=int, default=sb.TURN_CAP)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "run"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    os.makedirs(OUT_DIR, exist_ok=True)
    if args.build_pool:
        sb.load_engine()
        print(json.dumps(build_pool(sb.DEFAULT_DECKS, args.decks), indent=1))
        return 0
    if args.replay is not None:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
        _init_worker(args.decks, args.mode if args.mode != "rotate" else sb.mode_for(args.replay, "rotate"),
                     args.turn_cap)
        res = play_seed(args.replay, verbose=True)
        print(json.dumps({k: v for k, v in res.items() if k != "failures"}, indent=1, default=str))
        for f in res["failures"]:
            print(f"\n=== {f['signature']} (turn {f['turn']})\n{f['message']}\n{f['traceback']}")
        return 0
    sb.load_engine()
    results = []
    seeds = [args.seed * 100000 + i for i in range(args.games)]
    t0 = time.time()

    def progress(r):
        results.append(r)
        if not args.quiet:
            fl = ", ".join(f["signature"][:80] for f in r["failures"][:3])
            print(f"[{len(results)}] seed {r['seed']} {r['mode']} {r['decks']} {r['outcome']} "
                  f"T{r['turns']} {r['seconds']}s {('FAIL: ' + fl) if fl else ''}", flush=True)
        if len(results) % 50 == 0:
            write_report(results, args)

    if args.workers <= 1:
        _init_worker(args.decks, args.mode, args.turn_cap)
        for s in seeds:
            progress(play_seed(s))
    else:
        ctx = multiprocessing.get_context("fork")
        with ctx.Pool(args.workers, initializer=_init_worker,
                      initargs=(args.decks, args.mode, args.turn_cap), maxtasksperchild=25) as pool:
            for r in pool.imap_unordered(play_seed, seeds, chunksize=1):
                progress(r)
    write_report(results, args)
    print(open(os.path.join(args.out, "summary.txt")).read())
    print(f"wall {time.time() - t0:.0f}s")
    return 0


def write_report(results, args):
    rep = sb.aggregate(results, args.out, args)
    tot = collections.Counter()
    games_with = collections.Counter()
    for r in results:
        for k, v in (r.get("doll_stats") or {}).items():
            tot[k] += v
            games_with[k] += 1 if v else 0
    lines = ["", "Doll/lock exercise (total events / games with >=1):"]
    for k in sorted(set(STAT_KEYS) | set(tot)):
        lines.append(f"  {k:32s} {tot[k]:7d} / {games_with[k]:5d}")
    with open(os.path.join(args.out, "summary.txt"), "a") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(args.out, "doll_stats.json"), "w") as fh:
        json.dump({"totals": tot, "games_with": games_with}, fh, indent=1)
    return rep


if __name__ == "__main__":
    sys.exit(main())
