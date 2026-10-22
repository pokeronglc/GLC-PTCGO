import logging

from spirit.network.protocol import WargFlags
from spirit.network.message_names import InboundMsg, OutboundMsg
from spirit.database.accounts import get_account_by_username, create_account, verify_password
from spirit.game.attributes import AttrID
from spirit.game.season_manager import VersusSeasonManager
from spirit.game.models.versus import client_tiers

# High enough that no balance here reaches it, but the client computes
# Convert.ToInt16(cap * 0.8) for the 'approaching the limit' badge
# (GlobalNavCurrencyNotificationBehaviour), so cap * 0.8 must stay <= 32767.
CURRENCY_CAP = 40_000


def currency_caps_packet() -> dict:
    """CurrencyCaps for every wallet currency (client reads a missing cap as 0)."""
    return {
        "messageName": OutboundMsg.CURRENCY_CAPS.value,
        "currencies": [
            {"name": attr.value, "value": CURRENCY_CAP}
            for attr in (AttrID.TRAINER_TOKENS, AttrID.GEMS, AttrID.EVENT_TICKETS)
        ],
    }
from spirit.game.account_attributes import build_account_attributes, anchor_versus_animation
from .base import BaseHandler, handle
from spirit.server.state import consume_ticket, sweep_expired_tickets
from .social import SocialHandler
from spirit.game.models.player import Player
from spirit.game.session.manager import GameSessionManager
from spirit.game.session.constants import GamePhase
from spirit.database.async_utils import run_db
from spirit.database.daily_rewards import process_daily_login
from spirit.database.player_data import grant_all_cards, strip_economy
from spirit.game.daily_rewards import DailyRewardManager
from spirit.server import metrics
from spirit.config import GRANT_ALL_CARDS_ON_LOGIN, NO_ECONOMY


def _get_or_create_account(username, password):
    account = get_account_by_username(username)
    if not account:
        account = create_account(username, password)
    return account



# Ping thresholds sent to the client (see NetworkStatusIndicatorConfiguration
# below): the client disconnects itself after ERROR_MS * ERROR_COUNT of latency.
NETWORK_PING_WARNING_MS = 3000
NETWORK_PING_ERROR_MS = 10000
NETWORK_PING_ERROR_COUNT = 3

class AuthHandler(BaseHandler):
    @handle(InboundMsg.AUTHENTICATE_CAS_TICKET)
    async def handle_authenticate_cas_ticket(self, message, request_id, flags):
        # CAS Authentication (Modern PC Login)

        username = str(message.get("accountName", ""))
        ticket = str(message.get("serviceTicket", ""))
        service = str(message.get("serviceName", ""))

        logging.info(f"[TCP] User {username} is attempting CAS login with ticket {ticket} for service {service}")
        
        # 1. Verify + consume the ticket atomically (thread-safe vs the HTTP issuer)
        sweep_expired_tickets()
        if not consume_ticket(ticket, username):
            logging.warning(f"[TCP] [{self.client.addr}] Invalid CAS ticket: {ticket} for user: {username}")
            return await self._send_auth_failed(request_id, "Invalid CAS Ticket.")

        # 2. Look up the account
        account = await run_db(get_account_by_username, username)
        if not account:
            # This shouldn't happen if the ticket was issued, but safety first
            return await self._send_auth_failed(request_id, "Account sync error.")

        # 3. Success!
        logging.info(f"[TCP] [{self.client.addr}] User '{username}' successfully authenticated via CAS.")
        await self._send_auth_success(request_id, account)

    @handle(InboundMsg.START_AUTH)
    async def handle_start_authentication(self, message, request_id, flags):
        auth_type = message.get("authType", "Unknown")
        logging.info(f"[TCP] [{self.client.addr}] Client started authentication sequence. Type: {auth_type}")
        
        if auth_type == "DeviceID":
            logging.info(f"[TCP] [{self.client.addr}] Bypassing DeviceID token exchange. Forcing Auth Success.")
            
            # Device login carries no name: key the guest account on a hash of
            # the IP so the address never appears in a public screen name.
            from spirit.database.accounts import get_or_create_guest_account
            account = await run_db(get_or_create_guest_account,
                                   self.client.addr[0], "guest_password")

            return await self._send_auth_success(request_id, account)

        response = {
            "messageName": OutboundMsg.REQ_AUTH_TOKEN.value
        }
        await self.client.send_packet(response, request_id, flags=WargFlags.CLEAR)

    @handle(InboundMsg.AUTH_GAS_TOKEN)
    async def handle_gas_auth_token(self, message, request_id, flags):
        # PC Login
        # Currently treating userID as the username field because the client's packet format is ambiguous
        username = str(message.get("userID", ""))
        password = str(message.get("token", ""))

        logging.info(f"[TCP] User {username} is attempting to login...")
        
        account = await run_db(get_account_by_username, username)

        # Auto-Register if it doesn't exist
        if not account:
            logging.info(f"[TCP] [{self.client.addr}] Auto-registering new user: {username}")
            account = await run_db(create_account, username, password)
            if not account:
                return await self._send_auth_failed(request_id, "Could not create account. Please try again.")

        # if account existed or was just created
        if not await run_db(verify_password, account['password_hash'], password):
            logging.warning(f"[TCP] [{self.client.addr}] Failed login attempt for user: {username}")
            return await self._send_auth_failed(request_id, "Incorrect password. Please try again.")

        logging.info(f"[TCP] [{self.client.addr}] User '{username}' successfully authenticated.")
        await self._send_auth_success(request_id, account)

    @handle(InboundMsg.AUTH_GAS_GUEST)
    async def handle_gas_guest(self, message, request_id, flags):
        # Guest login. NEVER trust the client-supplied uniqueID as an account
        # name: it used to look the account up by that name with no password,
        # so sending a real player's username logged in as that player. Use
        # the same IP-keyed "Guest-XXXXXX" account as the DeviceID path; it
        # can never match a real account.
        from spirit.database.accounts import get_or_create_guest_account
        logging.info(f"[TCP] [{self.client.addr}] Guest login (client ID ignored).")
        account = await run_db(get_or_create_guest_account,
                               self.client.addr[0], "guest_password")
        await self._send_auth_success(request_id, account)

    @handle(InboundMsg.AUTH_GAS_MOBILE)
    async def handle_gas_mobile(self, message, request_id, flags):
        # The mobile app is not supported, and this login had no password
        # check (any account name was accepted). Refuse it.
        logging.warning(f"[TCP] [{self.client.addr}] Refused mobile-app login "
                        f"(mobileID={str(message.get('mobileID', ''))[:40]!r}).")
        await self._send_auth_failed(
            request_id, "The mobile app is not supported. Please use the desktop version.")

    @staticmethod
    def _active_game(account_id):
        """Returns the account's live (non-finished) GameSession, or None."""
        session = GameSessionManager().get_session_by_player_id(account_id)
        if session is not None and session.game_phase != GamePhase.GAME_OVER:
            return session
        return None

    def _has_active_game(self, account_id) -> bool:
        return self._active_game(account_id) is not None

    async def _send_auth_success(self, request_id, account_data):
        # Concurrent Login Prevention
        account_id = account_data['account_id']
        username = account_data['username']

        server = self.client.server
        other_client = self.online_client(account_id, exclude_self=True)
        # Claim the account synchronously (before any await) so two concurrent logins
        # for one account can't both pass the guard during the DB-load window.
        if other_client is None and account_id in server.logins_in_flight:
            logging.warning(f"[TCP] [{self.client.addr}] Concurrent login race for '{username}' blocked.")
            await self._send_auth_failed(request_id, "The account you are trying to login is already online.")
            return
        # Claim the account before any await (two logins at once stay serialised).
        server.logins_in_flight.add(account_id)
        if other_client:
            # The newest login always wins.  After a kick or crash the old
            # socket can linger for minutes (or hang in a handler), and
            # refusing the login locked players out with "already online".
            # Mid-game this is also the reconnect path.
            kind = "Reconnect" if self._has_active_game(account_id) else "New login"
            logging.info(f"[TCP] [{self.client.addr}] {kind} for '{username}': "
                         f"replacing older session {other_client.addr}")
            await self._evict(other_client, account_id)
        try:
            await self._complete_auth_success(request_id, account_data, account_id, username)
        finally:
            server.logins_in_flight.discard(account_id)

    async def _evict(self, other_client, account_id):
        """Close an older session for this account, never blocking the new
        login for long, and make sure it no longer counts as online."""
        import asyncio
        server = self.client.server
        try:
            transport = getattr(getattr(other_client, "writer", None), "transport", None)
            if transport is not None:
                transport.abort()
        except Exception:
            pass
        try:
            await asyncio.wait_for(other_client.disconnect(), timeout=10)
        except asyncio.TimeoutError:
            logging.warning(f"[TCP] Older session {other_client.addr} slow to close; continuing login")
        except Exception as e:
            logging.warning(f"[TCP] Error closing older session {other_client.addr}: {e}")
        if server.clients_by_account.get(account_id) is other_client:
            del server.clients_by_account[account_id]

    async def _complete_auth_success(self, request_id, account_data, account_id, username):
        # One thread hop for the whole DB-heavy login load (player profile,
        # account attributes, daily login progress).
        def _load_login_state():
            # Top up missing cards before the client pulls collection so new
            # scripts land in every account without an admin grant pass.
            if GRANT_ALL_CARDS_ON_LOGIN:
                # Singleton format: exactly 1 of each card (basic Energy
                # stays plentiful), so the deck builder can't add a 2nd copy.
                grant_all_cards(account_id, count=1, is_tradable=True, exact=True)
            if NO_ECONOMY:
                strip_economy(account_id)
            player = Player(account_data)
            # Anchor the versus-ladder animation to current points BEFORE building
            # attributes, so a relog never replays the points/reward animation.
            anchor_versus_animation(account_id)
            attributes = build_account_attributes(account_id)
            daily_info = process_daily_login(account_id)
            return player, attributes, daily_info

        player, account_attributes, daily_info = await run_db(_load_login_state)
        self.client.player = player
        # Index the authenticated client so presence/challenge/login-guard are O(1).
        self.client.server.register_account(self.client)
        metrics.inc("logins_success")

        # Notify friends that we are online
        social_handler = SocialHandler(self.client)
        await social_handler.broadcast_presence("Online")

        # AuthenticationSuccessful
        response = {
            "messageName": OutboundMsg.AUTH_SUCCESS.value,
            "account": {
                "username": account_data['username'],
                "accountID": account_data['account_id'],
                "attributes": account_attributes
            },
            "sessionID": self.client.session_id,
            "supplementaryInfo": None
        }
        await self.client.send_packet(response, request_id, flags=WargFlags.CLEAR)

        # EulaSuccessful
        await self.client.send_packet({
            "messageName": OutboundMsg.EULA_SUCCESSFUL.value,
            "version": 1
        }, 0)

        # CohortsForAccount
        await self.client.send_packet({
            "messageName": OutboundMsg.COHORTS_FOR_ACCOUNT.value,
            "cohorts": {},
            "redirectScenes": {},
            "cohortFeatures": []
        }, 0)

        # PlayerStillInGame drives the client's reconnect (PlayerStillInGameObserver
        # -> ReconnectToGame) when an unfinished session survives for this account;
        # otherwise the normal PlayerNotInGame.
        active_session = self._active_game(account_id)
        if active_session is not None:
            note = getattr(active_session, "note_player_logging_in", None)
            if note is not None:
                try:
                    note(account_id)
                except Exception:
                    logging.exception("[TCP] Could not extend reconnect grace")
            await self.client.send_packet({
                "messageName": OutboundMsg.PLAYER_STILL_IN_GAME.value,
                "gameID": active_session.game_id,
            }, 0)
        else:
            await self.client.send_packet({
                "messageName": OutboundMsg.PLAYER_NOT_IN_GAME.value
            }, 0)

        # NetworkStatusIndicatorConfiguration.  NOT just the in-game signal
        # icon: the client copies pingErrorThreshold into MessageCenterBehaviour
        # and TERMINATES its own session once its Ping->Pong latency exceeds
        # pingErrorThreshold * thresholdProceduralSetting (default 3).  The old
        # 500/1000 values meant any 3-second stall (busy server, a PC freezing
        # while loading card art, a Wi-Fi hiccup) made the client hang up --
        # the "client closed the socket" disconnects.  Client defaults are
        # warning 3000 / error 80000 ms; 10 s x 3 = 30 s keeps real dead
        # connections detected while riding out ordinary stalls.
        await self.client.send_packet({
            "messageName": OutboundMsg.NETWORK_STATUS_INDICATOR_CONFIGURATION.value,
            "pingWarningThreshold": NETWORK_PING_WARNING_MS,
            "pingErrorThreshold": NETWORK_PING_ERROR_MS,
            "thresholdProceduralSetting": NETWORK_PING_ERROR_COUNT,
        }, 0)

        # DefaultTrainerChallengeDeckMessage
        await self.client.send_packet({
            "messageName": OutboundMsg.DEFAULT_TRAINER_CHALLENGE_DECK_MESSAGE.value,
            "defaultDeckName": "Mental Might"
        }, 0)

        # CurrentVersusSeason
        active_season = VersusSeasonManager().get_active_season()
        season_payload = active_season.to_client_dict() if active_season else {
            "seasonID": "Season1",
            "startTime": 1767225600000,  # non-zero, or the client re-pops the ladder reset
            "endTime": 4102444800000, # Year 2100
            "description": {"id": "CompletePTCGO Season"},
            "tiers": client_tiers([]),
            "resetRewardID": ""
        }
        await self.client.send_packet({
            "messageName": OutboundMsg.CURRENT_VERSUS_SEASON.value,
            "versusSeason": season_payload
        }, 0)

        # CurrencyCaps: the client warns before Versus whenever a balance is
        # at or above its cap, and a missing cap counts as 0.
        await self.client.send_packet(currency_caps_packet(), 0)

        # CurrentDailyRewardTrack
        await self.client.send_packet({
            "messageName": OutboundMsg.CURRENT_DAILY_REWARD_TRACK.value,
            "dailyRewardTrack": {
                "name": "Standard Track",
                "rewardTiers": [
                    {
                        "wins": 1,
                        "rewards": [
                            {
                                "name": "5 Tokens",
                                "rewardType": "Currency",
                                "rewardAmount": 5
                            }
                        ],
                        "isDefault": True,
                        "isSpecial": False
                    }
                ],
                "isDefault": True
            },
            "nextExpiry": 4102444800000
        }, 0)

        # QuestConfigurationUpdated
        await self.client.send_packet({
            "messageName": OutboundMsg.QUEST_CONFIGURATION_UPDATED.value,
            "questConfiguration": {
                "xpLevelMap": {"1": 100, "2": 200},
                "levelTierMap": {"1": 1},
                "affinityToAffinityLevelRewardsMap": {},
                "nextQuestAvailableTime": 4102444800000,
                "levelActiveQuestsMap": {"1": 1}
            }
        }, 0)

        # DailyLogin — weeksRewards outer array = days; timestamp = next reward time in ms
        await self.client.send_packet({
            "messageName": OutboundMsg.DAILY_LOGIN.value,
            "activations": daily_info["activations"],
            "timestamp": daily_info["nextRewardTimestampMs"],
            "lastLoginTimestamp": daily_info["nextRewardTimestampMs"],
            "rewardDay": daily_info["rewardDay"],
            "weeksRewards": DailyRewardManager().weeks_rewards(daily_info["activations"]),
            # No daily coin/pack rewards on a bare-bones server: no popup.
            "firstDailyLogin": daily_info["firstDailyLogin"] and not NO_ECONOMY
        }, 0)

        # AccountPropertiesUpdated
        await self.client.send_packet({
            "messageName": OutboundMsg.ACCOUNT_PROPERTIES_UPDATED.value,
            "accountID": account_data['account_id'],
            "attributes": [
                {"name": AttrID.FRIEND_CHAT_MODE.value, "value": "OpenChat"},
                {"name": AttrID.FRIEND_MODE.value, "value": "Open"},
                {"name": AttrID.FRIEND_TRADE_MODE.value, "value": "Free"},
                {"name": AttrID.GAME_CHAT_MODE.value, "value": "OpenChat"},
                {"name": AttrID.PUBLIC_CHAT_MODE.value, "value": "OpenChat"},
                {"name": AttrID.SHOPPING_MODE.value, "value": "Open"},
                {"name": AttrID.TRADE_MODE.value, "value": "Free"},
                {"name": AttrID.PRIVATE_MESSAGING_MODE.value, "value": "OpenChat"},
                {"name": AttrID.DECK_SHARE_MODE.value, "value": "Everybody"},
            ]
        }, 0)

        # DynamicVersions (Push initial versions)
        await self.client.send_packet({
            "messageName": OutboundMsg.DYNAMIC_VERSIONS.value,
            "versionData": {
                "major_version_number": "1",
                "minor_version_number": "0",
                "content_data_version": "1",
                "content_data_version_id": "0",
                "cachedDisplayVersion": "1",
                "cachedCollectionVersion": "1",
                "androidpatchversion": "1",
                "iospatchversion": "1",
                "lastUpdatedAtVersion": "1",
                "opponentsDataVersion": "1",
                "progressionDataVersion": "1",
                "cachedDarkenDataVersion": "1",
                "LatestMacPatcherVersion": "1",
                "LatestWindowsPatcherVersion": "1",
                "LatestMacClientVersion": "1",
                "LatestWindowsClientVersion": "1"
            }
        }, 0)

    async def _send_auth_failed(self, request_id, reason_text):
        """Sends an AuthenticationFailed message back to the client."""
        response = {
            "messageName": OutboundMsg.AUTH_FAILED.value,
            "reason": {
                "token": reason_text,
                "bundle": {"en": reason_text}
            }
        }
        await self.client.send_packet(response, request_id, flags=WargFlags.CLEAR)
