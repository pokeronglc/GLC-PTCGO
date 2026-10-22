"""Deck stats (deck manager "Stats" panel) and lifetime player stats
(Profile > Statistics > Game Stats).

The client reads both from attributes the server already sends -- it never
asks for them -- so these helpers only keep the numbers and build the
attribute lists (see spirit.game.player_stats for the attribute ids).
"""
import logging

from spirit.database import db_session, Deck, PlayerStats

DECK_STAT_FIELDS = ("overall_wins", "overall_played",
                    "wins_since_last_edit", "played_since_last_edit")
PLAYER_STAT_FIELDS = ("cards_drawn", "damage_dealt", "damage_taken",
                      "games_played", "seconds_played", "upset_wins")


def _deck_stats(d):
    return {f: int(getattr(d, f) or 0) for f in DECK_STAT_FIELDS}


def record_deck_result(account_id, deck_id, won):
    """+1 played (and +1 win) on the player's deck; returns the new counters,
    or None when the deck isn't one of the player's saved decks."""
    if not deck_id:
        return None
    try:
        with db_session() as session:
            d = session.query(Deck).filter_by(id=deck_id, account_id=account_id).first()
            if d is None:
                return None
            d.overall_played = (d.overall_played or 0) + 1
            d.played_since_last_edit = (d.played_since_last_edit or 0) + 1
            if won:
                d.overall_wins = (d.overall_wins or 0) + 1
                d.wins_since_last_edit = (d.wins_since_last_edit or 0) + 1
            session.flush()
            return _deck_stats(d)
    except Exception as e:
        logging.error(f"Error recording deck result {deck_id} for {account_id}: {e}")
        return None


def reset_deck_edit_stats(account_id, deck_id):
    """The deck's cards changed: "since last edit" counters start over."""
    try:
        with db_session() as session:
            d = session.query(Deck).filter_by(id=deck_id, account_id=account_id).first()
            if d is None:
                return None
            d.wins_since_last_edit = 0
            d.played_since_last_edit = 0
            session.flush()
            return _deck_stats(d)
    except Exception as e:
        logging.error(f"Error resetting deck stats {deck_id}: {e}")
        return None


def get_deck_stats(account_id, deck_id):
    try:
        with db_session() as session:
            d = session.query(Deck).filter_by(id=deck_id, account_id=account_id).first()
            return _deck_stats(d) if d is not None else None
    except Exception as e:
        logging.error(f"Error reading deck stats {deck_id}: {e}")
        return None


def get_player_stats(account_id):
    try:
        with db_session() as session:
            row = session.query(PlayerStats).filter_by(account_id=account_id).first()
            return {f: int(getattr(row, f) or 0) if row else 0 for f in PLAYER_STAT_FIELDS}
    except Exception as e:
        logging.error(f"Error reading player stats for {account_id}: {e}")
        return {f: 0 for f in PLAYER_STAT_FIELDS}


def add_player_stats(account_id, **amounts):
    """Adds the given amounts (PLAYER_STAT_FIELDS names) to the lifetime totals."""
    try:
        with db_session() as session:
            row = session.query(PlayerStats).filter_by(account_id=account_id).first()
            if row is None:
                row = PlayerStats(account_id=account_id,
                                  **{f: 0 for f in PLAYER_STAT_FIELDS})
                session.add(row)
            for field, amount in amounts.items():
                if field in PLAYER_STAT_FIELDS and amount:
                    setattr(row, field, int(getattr(row, field) or 0) + int(amount))
            session.flush()
            return {f: int(getattr(row, f) or 0) for f in PLAYER_STAT_FIELDS}
    except Exception as e:
        logging.error(f"Error adding player stats for {account_id}: {e}")
        return None
