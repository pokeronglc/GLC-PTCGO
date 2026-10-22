import logging
from typing import Dict, Any, List
from .player_abstract import GamePlayer
from spirit.game.models.avatar import get_default_avatar_items_list

class NetworkPlayer(GamePlayer):
    def __init__(self, client_handler, deck_data: Dict[str, Any]):
        super().__init__(
            account_id=client_handler.player.account_id,
            username=client_handler.player.username,
            deck_data=deck_data
        )
        self.client_handler = client_handler
        # (entity id, attr id) -> (value, originalValue) this client was last
        # sent, for the attrs in WATCHED_ATTRS (see note_sent).
        self.wire_attrs: Dict[Any, Any] = {}

    # HP and Special Conditions: the two attrs the server changes on cards
    # that leave play without telling the clients (bug hunt 7, Oct 13).
    WATCHED_ATTRS = (200490, 200340)

    def note_sent(self, packet: Dict[str, Any]):
        """Remember the watched attribute values this client now holds."""
        if packet.get("messageName") != "SequenceMessage":
            return
        msg = packet.get("msg") or {}
        name = msg.get("name")
        value = msg.get("value") or {}
        watched = self.WATCHED_ATTRS
        try:
            if name == "AttributeModified":
                attr = value.get("attribute") or {}
                if attr.get("name") in watched:
                    self.wire_attrs[(value.get("entityID"), attr["name"])] = (
                        attr.get("value"), attr.get("originalValue"))
            elif name == "EntityIntroduced":
                eid = value.get("entityID")
                for attr in value.get("attributeMap") or []:
                    if attr.get("name") in watched:
                        self.wire_attrs[(eid, attr["name"])] = (
                            attr.get("value"), attr.get("originalValue"))
            elif name == "AttributesReset":
                eid = value.get("entityID")
                for key in [k for k in self.wire_attrs if k[0] == eid]:
                    self.wire_attrs.pop(key, None)
            elif name == "SerializedGameState":
                self.wire_attrs = {}
                stack = [value.get("entities") or {}]
                while stack:
                    node = stack.pop()
                    for attr in node.get("attributes") or []:
                        if attr.get("name") in watched:
                            self.wire_attrs[(node.get("entityID"), attr["name"])] = (
                                attr.get("value"), attr.get("originalValue"))
                    stack.extend(node.get("children") or [])
        except Exception as e:  # bookkeeping must never break a send
            logging.debug(f"[Session] note_sent skipped a {name}: {e}")

    @property
    def connected(self) -> bool:
        """True while a live socket is bound; False after a disconnect detach."""
        handler = self.client_handler
        return handler is not None and getattr(handler, "running", False)

    @property
    def screen_name(self) -> str:
        """Returns the screen_name or username of the underlying TCP player."""
        player_profile = getattr(self.client_handler, "player", None) if self.client_handler else None
        if player_profile:
            return getattr(player_profile, "screen_name", None) or getattr(player_profile, "username", "Player")
        return self.username

    @property
    def avatar_items(self) -> List[str]:
        """Returns the avatar items from the active avatar deck."""
        player_profile = getattr(self.client_handler, "player", None) if self.client_handler else None
        if player_profile and getattr(player_profile, "avatar_decks", None):
            # Look for active avatar deck (attribute 201310 is "True")
            from spirit.config import BLANK_AVATARS
            for deck in ([] if BLANK_AVATARS else player_profile.avatar_decks):
                deck_data = deck.get("deck_data", {})
                attrs = deck_data.get("attributes", [])
                is_active = False
                for attr in attrs:
                    if attr.get("name") == 201310 and attr.get("value") == ["True"]:
                        is_active = True
                        break
                if is_active or len(player_profile.avatar_decks) == 1:
                    items = None
                    if "piles" in deck_data and "AvatarItems" in deck_data["piles"]:
                        items = deck_data["piles"]["AvatarItems"]
                    elif "cards" in deck_data and "AvatarItems" in deck_data["cards"]:
                        items = deck_data["cards"]["AvatarItems"]
                    if items:
                        return items
        return get_default_avatar_items_list()

    async def send_packet(self, name: str, value: Dict[str, Any], flags: int = 0):
        # Detached (disconnected) player: drop sends until they reconnect. The
        # full board is re-serialized on reconnect, so missed packets don't matter.
        if self.client_handler is None:
            return
        packet = value.copy()
        packet["messageName"] = name
        self.note_sent(packet)
        try:
            await self.client_handler.send_packet(packet, request_id=0, flags=flags)
        except Exception as e:
            logging.error(f"[Session] Failed to send packet to {self.username}: {e}")

    async def prompt_selection(self, prompt_packet: Dict[str, Any]):
        logging.info(f"[Session] Prompting NetworkPlayer {self.username} with choice.")
        await self.send_packet("SelectionWithTargetsAndActionsRequired", prompt_packet)
