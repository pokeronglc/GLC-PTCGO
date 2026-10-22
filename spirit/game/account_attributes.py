from spirit.game.attributes import AttrID
from spirit.database import versus_data
from spirit.database.player_data import get_account_settings, get_screen_name, merge_account_settings
from spirit.game.season_manager import VersusSeasonManager
from spirit.database.stats_data import get_player_stats
from spirit.game.player_stats import account_stat_attributes

# Client setting numbers inside the account-settings dict (attr 10230, K.L.GetSetting)
VERSUS_LAST_SEEN_POINTS_SETTING = 109  # LastKnownSeasonPointTotal (ladder animation anchor)
# VersusSeasonDialogDisplayController (client): 108 = first-arrival dialog
# shown; 111/112 and 113/114 = last seen season start/end as (high, low)
# int32 halves of a long (K.L.SetLongAccountSetting).  When they don't match
# the current season the client pops "Versus Ladder Reset" every visit.
VERSUS_FIRST_ARRIVAL_SETTING = 108
VERSUS_SEASON_START_SETTINGS = (111, 112)
VERSUS_SEASON_END_SETTINGS = (113, 114)
# Account attribute 202101 (string[]): VisitedScene names the client checks
# before showing first-visit tips (Professor's "In this mode..." callout).
VISITED_SCENES_ATTRIBUTE = 202101
ALL_VISITED_SCENES = ["TrainerChallenge", "Versus", "Deckbuilder",
                      "TCGoldComplete", "TCLoss", "VersusUpdate"]


def _long_halves(value):
    """(high, low) signed int32 halves, as the client's SetLongAccountSetting stores."""
    value = int(value) & 0xFFFFFFFFFFFFFFFF
    def signed(v):
        return v - (1 << 32) if v >= (1 << 31) else v
    return signed(value >> 32), signed(value & 0xFFFFFFFF)


def anchor_versus_animation(account_id):
    """LOGIN-ONLY: set the client's LastKnownSeasonPointTotal (setting 109) to the
    player's current season points so the versus ladder never replays its
    points/reward animation on relog. In-session gains still animate because the
    mid-game AccountUpdated leaves 109 stale (it never re-runs this)."""
    season = VersusSeasonManager().get_active_season()
    points, _ = versus_data.get_progress(
        account_id, season.season_id if season else "")
    settings = {VERSUS_LAST_SEEN_POINTS_SETTING: points,
                VERSUS_FIRST_ARRIVAL_SETTING: 1}
    if season is not None:
        for (hi_key, lo_key), value in ((VERSUS_SEASON_START_SETTINGS, season.start_time),
                                        (VERSUS_SEASON_END_SETTINGS, season.end_time)):
            hi, lo = _long_halves(value)
            settings[hi_key] = hi
            settings[lo_key] = lo
    merge_account_settings(account_id, settings)
    return points


def build_account_attributes(account_id):
    """Full SerializableAccount attribute list (AccountUpdated ReplaceWith
    swaps the whole set, so every sender must include everything)."""

    season = VersusSeasonManager().get_active_season()
    points, all_time = versus_data.get_progress(
        account_id, season.season_id if season else "")
    return [
        {"name": AttrID.ACCOUNT_SETTINGS.value, "value": get_account_settings(account_id)},
        {"name": AttrID.SCREEN_NAME.value, "value": get_screen_name(account_id)},
        {"name": AttrID.FRIEND_CHAT_MODE.value, "value": "OpenChat"},
        {"name": AttrID.FRIEND_MODE.value, "value": "Open"},
        {"name": AttrID.FRIEND_TRADE_MODE.value, "value": "Free"},
        {"name": AttrID.GAME_CHAT_MODE.value, "value": "OpenChat"},
        {"name": AttrID.PUBLIC_CHAT_MODE.value, "value": "OpenChat"},
        {"name": AttrID.SHOPPING_MODE.value, "value": "Open"},
        {"name": AttrID.TRADE_MODE.value, "value": "Free"},
        {"name": AttrID.PRIVATE_MESSAGING_MODE.value, "value": "OpenChat"},
        {"name": AttrID.DECK_SHARE_MODE.value, "value": "Everybody"},
        {"name": AttrID.SEASON_POINTS.value, "value": points},
        {"name": AttrID.ALL_TIME_SEASON_POINTS.value, "value": all_time},
        {"name": VISITED_SCENES_ATTRIBUTE, "value": list(ALL_VISITED_SCENES)},
        # Profile > Statistics > Game Stats ("Total Game Points" = all-time
        # Versus points; Tournament Rep has no server system yet).
        *account_stat_attributes(get_player_stats(account_id), game_points=all_time),
    ]
