"""Public leaderboard (owner request Oct 21): player-vs-player results summed
from each account's saved decks (decks.overall_wins / overall_played).

Guest accounts are left out (they're throwaway logins). Wins on a deck the
player has deleted are no longer counted -- that's where the totals live.
Results are cached for a short time so a busy page can't load the database.
"""
import collections
import json
import logging
import threading
import time

import sqlite3

from spirit.database import connection

CACHE_SECONDS = 30
MIN_GAMES_FOR_WIN_RATE = 20
TOP_N = 10

_lock = threading.Lock()
_cache = {"at": 0.0, "data": None}


def _is_guest(username, screen_name):
    return any(str(n or "").lower().startswith("guest_") for n in (username, screen_name))


def _player_rows():
    # Plain read-only sqlite (no ORM): a public page must never write or lock.
    con = sqlite3.connect(f"file:{connection.DB_PATH}?mode=ro", uri=True, timeout=10)
    try:
        rows = con.execute("""
            SELECT a.username, a.screen_name,
                   COALESCE(SUM(d.overall_wins), 0), COALESCE(SUM(d.overall_played), 0)
            FROM accounts a JOIN decks d ON d.account_id = a.account_id
            GROUP BY a.account_id""").fetchall()
    finally:
        con.close()
    players = []
    for username, screen_name, wins, played in rows:
        wins, played = int(wins or 0), int(played or 0)
        if played <= 0 or _is_guest(username, screen_name):
            continue
        players.append({
            "player": screen_name or username,
            "wins": wins,
            "played": played,
            "losses": max(0, played - wins),
            "win_rate": round(100.0 * wins / played, 1),
        })
    return players


# --- Deck statistics: by deck type and by card -------------------------
# Uses each saved deck's games "since last edit" so the counts match the
# cards the deck holds now (overall totals span older versions of a deck).

def _deck_rows():
    con = sqlite3.connect(f"file:{connection.DB_PATH}?mode=ro", uri=True, timeout=10)
    try:
        return con.execute("""
            SELECT a.username, a.screen_name, d.deck_data,
                   COALESCE(d.wins_since_last_edit, 0), COALESCE(d.played_since_last_edit, 0)
            FROM decks d JOIN accounts a ON a.account_id = d.account_id
            WHERE COALESCE(d.is_avatar, 0) = 0
              AND COALESCE(d.played_since_last_edit, 0) > 0""").fetchall()
    finally:
        con.close()


def _deck_guids(raw):
    try:
        data = json.loads(raw) if isinstance(raw, (str, bytes)) else (raw or {})
    except ValueError:
        return []
    piles = (data or {}).get("piles") or {}
    return [str(g).lower() for g in (piles.get("deck") or piles.get("CakePile") or [])]


def _card_info(guid):
    """(name, kind, pokemon types) for a card GUID; kind is Pokemon /
    Trainer / Energy, or None for basic Energy and unknown cards."""
    from spirit.game.data_utils import (
        PokemonCardDef, EnergyCardDef, def_for, _attr_value)
    from spirit.game.attributes import AttrID, PokemonTypes
    d = def_for(guid)
    if d is None:
        return None, None, []
    name = getattr(d, "display_name", None) or "?"
    if isinstance(d, PokemonCardDef):
        raw = _attr_value(d, AttrID.POKEMON_TYPES, "[]") or "[]"
        types = []
        for value in (json.loads(raw) if isinstance(raw, str) else raw):
            try:
                types.append(PokemonTypes(value).name.title())
            except Exception:
                pass
        return name, "Pokemon", types
    if isinstance(d, EnergyCardDef):
        special = bool(_attr_value(d, AttrID.IS_SPECIAL_ENERGY, False))
        return name, ("Energy" if special else None), []
    return name, "Trainer", []


def build_deck_stats(top=TOP_N):
    by_type = {}
    cards = {}          # (kind, name) -> totals
    total_games = 0
    for username, screen_name, raw, wins, played in _deck_rows():
        if _is_guest(username, screen_name):
            continue
        wins, played = int(wins), int(played)
        guids = _deck_guids(raw)
        if not guids:
            continue
        total_games += played
        counts = collections.Counter(guids)
        type_votes = collections.Counter()
        seen = {}
        for guid, n in counts.items():
            name, kind, types = _card_info(guid)
            for t in types:
                type_votes[t] += n
            if kind is None:
                continue
            key = (kind, name)
            seen[key] = seen.get(key, 0) + n
        deck_type = type_votes.most_common(1)[0][0] if type_votes else "Unknown"
        row = by_type.setdefault(deck_type, {"type": deck_type, "decks": 0, "games": 0, "wins": 0})
        row["decks"] += 1
        row["games"] += played
        row["wins"] += wins
        for (kind, name), copies in seen.items():
            c = cards.setdefault((kind, name), {"card": name, "kind": kind, "decks": 0,
                                                "games": 0, "wins": 0, "copies": 0})
            c["decks"] += 1
            c["games"] += played
            c["wins"] += wins
            c["copies"] += copies

    def finish(row):
        row["win_rate"] = round(100.0 * row["wins"] / row["games"], 1) if row["games"] else 0.0
        row["share"] = round(100.0 * row["games"] / total_games, 1) if total_games else 0.0
        if "copies" in row:
            row["avg_copies"] = round(row.pop("copies") / row["decks"], 1) if row["decks"] else 0
        return row

    types = sorted((finish(r) for r in by_type.values()),
                   key=lambda r: (-r["games"], r["type"]))

    def top_of(kind):
        rows = [finish(dict(c)) for (k, _), c in cards.items() if k == kind]
        rows.sort(key=lambda r: (-r["games"], -r["decks"], r["card"].lower()))
        return rows[:top]

    return {
        "deck_games": total_games,
        "by_type": types,
        "top_pokemon": top_of("Pokemon"),
        "top_trainers": top_of("Trainer"),
        "top_special_energy": top_of("Energy"),
    }


def build_leaderboard():
    players = _player_rows()
    top_wins = sorted(players, key=lambda p: (-p["wins"], p["played"], p["player"].lower()))
    rated = [p for p in players if p["played"] >= MIN_GAMES_FOR_WIN_RATE]
    best_rate = sorted(rated, key=lambda p: (-p["win_rate"], -p["played"], p["player"].lower()))
    active = sorted(players, key=lambda p: (-p["played"], -p["wins"], p["player"].lower()))
    return {
        "updated": int(time.time()),
        "min_games_for_win_rate": MIN_GAMES_FOR_WIN_RATE,
        "total_players": len(players),
        "total_games": sum(p["played"] for p in players) // 2,
        "top_wins": top_wins[:TOP_N],
        "best_win_rate": best_rate[:TOP_N],
        "most_active": active[:TOP_N],
        **_safe_deck_stats(),
    }


def _safe_deck_stats():
    try:
        return build_deck_stats()
    except Exception as e:
        logging.error(f"[Leaderboard] Deck stats failed: {e}")
        return {"by_type": [], "top_pokemon": [], "top_trainers": [], "top_special_energy": []}


def get_leaderboard():
    """Cached leaderboard; on a database error, serves the last good copy."""
    now = time.time()
    with _lock:
        if _cache["data"] is not None and now - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
    try:
        data = build_leaderboard()
    except Exception as e:
        logging.error(f"[Leaderboard] Failed to build: {e}")
        with _lock:
            return _cache["data"] or {"error": "unavailable", "top_wins": [],
                                      "best_win_rate": [], "most_active": []}
    with _lock:
        _cache["at"], _cache["data"] = now, data
    return data
