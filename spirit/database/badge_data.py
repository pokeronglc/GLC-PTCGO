"""Badge board (owner request Oct 23).

Win 4 Versus games in a row with decks of the same type and you earn that
type's badge for good (one badge per type, like Gym badges).

  * Only Versus matchmaking games against another player count: not bot
    games, friend challenges or tournaments (see is_badge_game).
  * Any Versus game that isn't a win with that type starts the count again:
    a loss, or a game with a deck of a different type.
  * Every win counts, including when the opponent concedes or disconnects.

Stored with plain sqlite in two small tables created on first use, so no
database migration is needed. Counting starts from the update that added it.
"""
import logging
import sqlite3
import time

from spirit.database import connection

STREAK_FOR_BADGE = 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS badge_streaks (
    account_id TEXT PRIMARY KEY,
    deck_type  TEXT NOT NULL,
    wins       INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS badges (
    account_id TEXT NOT NULL,
    deck_type  TEXT NOT NULL,
    earned_at  INTEGER NOT NULL,
    PRIMARY KEY (account_id, deck_type)
);
"""


def _connect(readonly=False):
    if readonly:
        return sqlite3.connect(f"file:{connection.DB_PATH}?mode=ro", uri=True, timeout=10)
    con = sqlite3.connect(connection.DB_PATH, timeout=30)
    con.executescript(_SCHEMA)
    return con


def is_badge_game(pairing) -> bool:
    """Versus matchmaking between two players (queue OneVsOne*), not a
    tournament game played through the same queue."""
    pairing = pairing or {}
    if pairing.get("is_solo") or pairing.get("tournament") or pairing.get("legacy_tournament"):
        return False
    return str(pairing.get("queue_name") or "").startswith("OneVsOne")


def record_versus_result(account_id, deck_type, won):
    """Update the player's streak; returns the badge type newly earned by
    this game, or None."""
    if not account_id:
        return None
    deck_type = deck_type if deck_type and deck_type != "Unknown" else None
    con = _connect()
    try:
        with con:
            row = con.execute("SELECT deck_type, wins FROM badge_streaks WHERE account_id = ?",
                              (account_id,)).fetchone()
            if not won or deck_type is None:
                wins, kind = 0, deck_type or (row[0] if row else "")
            elif row and row[0] == deck_type:
                wins, kind = row[1] + 1, deck_type
            else:
                wins, kind = 1, deck_type
            con.execute("INSERT INTO badge_streaks (account_id, deck_type, wins) VALUES (?,?,?) "
                        "ON CONFLICT(account_id) DO UPDATE SET deck_type = excluded.deck_type, "
                        "wins = excluded.wins", (account_id, kind, wins))
            if won and deck_type and wins >= STREAK_FOR_BADGE:
                cur = con.execute("INSERT OR IGNORE INTO badges (account_id, deck_type, earned_at) "
                                  "VALUES (?,?,?)", (account_id, deck_type, int(time.time())))
                if cur.rowcount:
                    return deck_type
        return None
    finally:
        con.close()


def get_badge_board():
    """[{player, badges: [type, ...] in the order earned, latest}], most
    badges first; guest accounts left out."""
    try:
        con = _connect(readonly=True)
    except sqlite3.Error:
        return []
    try:
        try:
            rows = con.execute("""
                SELECT a.username, a.screen_name, b.deck_type, b.earned_at
                FROM badges b JOIN accounts a ON a.account_id = b.account_id
                ORDER BY b.earned_at""").fetchall()
        except sqlite3.OperationalError:
            return []                    # no badge earned yet: table not created
    finally:
        con.close()
    players = {}
    for username, screen_name, deck_type, earned_at in rows:
        if any(str(n or "").lower().startswith("guest_") for n in (username, screen_name)):
            continue
        name = screen_name or username
        entry = players.setdefault(name, {"player": name, "badges": [], "latest": 0})
        entry["badges"].append(deck_type)
        entry["latest"] = max(entry["latest"], int(earned_at))
    board = sorted(players.values(),
                   key=lambda p: (-len(p["badges"]), p["latest"], p["player"].lower()))
    return board
