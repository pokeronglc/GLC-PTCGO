"""Attribute ids the stock client reads for its stats screens (decoded from
pie-src.dll, Oct 14):

* Deck manager "Stats" panel (e.m ctor): DECK attributes, nullable int.
* Profile > Statistics > Game Stats (i.n): ACCOUNT attributes, nullable int;
  TotalTimePlayed is in seconds (TimeSpan.FromSeconds).

Collection Stats are computed by the client from the collection itself.
"""
DECK_OVERALL_PLAYED = 201590
DECK_OVERALL_WINS = 201600
DECK_PLAYED_SINCE_EDIT = 201650
DECK_WINS_SINCE_EDIT = 201660

ACCOUNT_CARDS_DRAWN = 200030
ACCOUNT_DAMAGE_DEALT = 200040
ACCOUNT_DAMAGE_TAKEN = 200050
ACCOUNT_GAMES_PLAYED = 200060
ACCOUNT_TIME_PLAYED = 200080      # seconds
ACCOUNT_UPSET_WINS = 200085
ACCOUNT_GAME_POINTS = 200120
ACCOUNT_TOURNAMENT_POINTS = 200125

DECK_STAT_IDS = (DECK_OVERALL_PLAYED, DECK_OVERALL_WINS,
                 DECK_PLAYED_SINCE_EDIT, DECK_WINS_SINCE_EDIT)


def deck_stat_attributes(stats):
    """[{name, value}] for a deck's four counters (stats: stats_data dict)."""
    stats = stats or {}
    return [
        {"name": DECK_OVERALL_WINS, "value": int(stats.get("overall_wins") or 0)},
        {"name": DECK_OVERALL_PLAYED, "value": int(stats.get("overall_played") or 0)},
        {"name": DECK_WINS_SINCE_EDIT, "value": int(stats.get("wins_since_last_edit") or 0)},
        {"name": DECK_PLAYED_SINCE_EDIT, "value": int(stats.get("played_since_last_edit") or 0)},
    ]


def with_deck_stats(attributes, stats):
    """Deck attribute list with the stat attributes replaced by `stats`
    (the client echoes old values back when it saves a deck)."""
    kept = [a for a in (attributes or [])
            if not (isinstance(a, dict) and _attr_id(a) in DECK_STAT_IDS)]
    return kept + deck_stat_attributes(stats)


def _attr_id(attribute):
    try:
        return int(attribute.get("name"))
    except (TypeError, ValueError):
        return None


def account_stat_attributes(stats, game_points=0, tournament_points=0):
    stats = stats or {}
    return [
        {"name": ACCOUNT_CARDS_DRAWN, "value": int(stats.get("cards_drawn") or 0)},
        {"name": ACCOUNT_DAMAGE_DEALT, "value": int(stats.get("damage_dealt") or 0)},
        {"name": ACCOUNT_DAMAGE_TAKEN, "value": int(stats.get("damage_taken") or 0)},
        {"name": ACCOUNT_GAMES_PLAYED, "value": int(stats.get("games_played") or 0)},
        {"name": ACCOUNT_TIME_PLAYED, "value": int(stats.get("seconds_played") or 0)},
        {"name": ACCOUNT_UPSET_WINS, "value": int(stats.get("upset_wins") or 0)},
        {"name": ACCOUNT_GAME_POINTS, "value": int(game_points or 0)},
        {"name": ACCOUNT_TOURNAMENT_POINTS, "value": int(tournament_points or 0)},
    ]


def deck_cards_changed(old_deck, new_deck):
    """Whether a save changed the deck's cards (not just its name/sleeve)."""
    def piles(deck):
        piles = (deck or {}).get("piles") or {}
        if not isinstance(piles, dict):
            return piles
        return {k: sorted(str(x).lower() for x in v) if isinstance(v, list) else v
                for k, v in piles.items()}
    return piles(old_deck) != piles(new_deck)
