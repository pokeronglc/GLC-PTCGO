import json
import os
import logging
from spirit.database import db_session, Account, Wallet, Deck, Collection, ArchetypeFlag
from spirit.game.format_manager import is_basic_energy_card
from spirit.game.scripts.cards import loader as card_loader
from spirit.game.scripts.products import loader as product_loader

# Resources granted to a brand-new account
STARTING_COINS = 1000
STARTING_GEMS = 0
STARTING_TICKETS = 100

# Coins awarded when a match completes (winner / loser rates)
COINS_PER_WIN = 1000
COINS_PER_LOSS = 200


def get_account_settings(account_id):
    """The account's persisted client settings dict {settingNumber(str): value} (attr 10230)."""
    try:
        with db_session() as session:
            account = session.query(Account).filter_by(account_id=account_id).first()
            return dict(account.settings_json or {}) if account else {}
    except Exception as e:
        logging.error(f"Error reading account settings for {account_id}: {e}")
        return {}


def get_screen_name(account_id):
    """The account's display name (screen_name, falling back to username)."""
    try:
        with db_session() as session:
            account = session.query(Account).filter_by(account_id=account_id).first()
            return (account.screen_name or account.username) if account else ""
    except Exception as e:
        logging.error(f"Error reading screen name for {account_id}: {e}")
        return ""


def merge_account_settings(account_id, new_settings):
    """Merges incoming {settingNumber: value} into the stored settings and persists."""
    try:
        with db_session() as session:
            account = session.query(Account).filter_by(account_id=account_id).first()
            if not account:
                return {}
            merged = dict(account.settings_json or {})
            for key, value in (new_settings or {}).items():
                merged[str(key)] = int(value)
            account.settings_json = merged  # reassign so JSONEncodedDict registers the change
            return merged
    except Exception as e:
        logging.error(f"Error merging account settings for {account_id}: {e}")
        return {}

def _wallet_to_dict(w):
    return {
        "account_id": w.account_id,
        "coins": w.coins,
        "gems": w.gems,
        "tickets": w.tickets
    }

def _deck_to_dict(d):
    return {
        "id": d.id,
        "account_id": d.account_id,
        "name": d.name,
        "deck_data": d.deck_data,
        "is_avatar": 1 if d.is_avatar else 0,
        "overall_wins": d.overall_wins,
        "overall_played": d.overall_played,
        "wins_since_last_edit": d.wins_since_last_edit,
        "played_since_last_edit": d.played_since_last_edit
    }

def _collection_to_dict(c):
    return {
        "account_id": c.account_id,
        "archetype_id": c.archetype_id,
        "tradable_count": c.tradable_count,
        "nontradable_count": c.nontradable_count
    }

def get_wallet_by_account_id(account_id):
    """Fetches the wallet for an account, or creates a default one if it doesn't exist."""
    try:
        with db_session() as session:
            w = session.query(Wallet).filter_by(account_id=account_id).first()
            if w:
                return _wallet_to_dict(w)
            else:
                # Create a default wallet
                new_w = Wallet(
                    account_id=account_id,
                    coins=STARTING_COINS,
                    gems=STARTING_GEMS,
                    tickets=STARTING_TICKETS
                )
                session.add(new_w)
                session.flush()
                return _wallet_to_dict(new_w)
    except Exception as e:
        logging.error(f"Error getting/creating wallet for {account_id}: {e}")
        return None

def update_wallet(account_id, coins, gems, tickets):
    """Updates an account's wallet."""
    try:
        with db_session() as session:
            w = session.query(Wallet).filter_by(account_id=account_id).first()
            if w:
                w.coins = coins
                w.gems = gems
                w.tickets = tickets
                return True
            else:
                new_w = Wallet(
                    account_id=account_id,
                    coins=coins,
                    gems=gems,
                    tickets=tickets
                )
                session.add(new_w)
                return True
    except Exception as e:
        logging.error(f"Error updating wallet for {account_id}: {e}")
        return False

def grant_coins(account_id, amount):
    """Adds coins to an account's wallet; returns the new balance or None."""
    try:
        with db_session() as session:
            w = session.query(Wallet).filter_by(account_id=account_id).first()
            if not w:
                w = Wallet(
                    account_id=account_id,
                    coins=STARTING_COINS,
                    gems=STARTING_GEMS,
                    tickets=STARTING_TICKETS
                )
                session.add(w)
            w.coins = (w.coins or 0) + amount
            session.flush()
            return w.coins
    except Exception as e:
        logging.error(f"Error granting {amount} coins to {account_id}: {e}")
        return None

def get_decks_by_account_id(account_id, is_avatar=False):
    """Fetches decks for an account."""
    try:
        with db_session() as session:
            rows = session.query(Deck).filter_by(account_id=account_id, is_avatar=is_avatar).all()
            return [_deck_to_dict(r) for r in rows]
    except Exception as e:
        logging.error(f"Error fetching decks for {account_id}: {e}")
        return []

def save_deck(account_id, deck_id, name, deck_data, is_avatar=False):
    """Saves or updates a deck for an account."""
    try:
        with db_session() as session:
            d = session.query(Deck).filter_by(id=deck_id).first()
            if d:
                d.account_id = account_id
                d.name = name
                d.deck_data = deck_data
                d.is_avatar = is_avatar
            else:
                new_d = Deck(
                    id=deck_id,
                    account_id=account_id,
                    name=name,
                    deck_data=deck_data,
                    is_avatar=is_avatar
                )
                session.add(new_d)
            return True
    except Exception as e:
        logging.error(f"Error saving deck {deck_id} for {account_id}: {e}")
        return False

def delete_deck(account_id, deck_id):
    """Deletes a deck for an account."""
    try:
        with db_session() as session:
            d = session.query(Deck).filter_by(id=deck_id, account_id=account_id).first()
            if d:
                session.delete(d)
                return True
            return False
    except Exception as e:
        logging.error(f"Error deleting deck {deck_id} for {account_id}: {e}")
        return False

_JSON_CACHE = {}

def _get_json_data(filename):
    """Helper to load and cache JSON data from the json_data folder."""
    if filename not in _JSON_CACHE:
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'json_data', f'{filename}.json'))
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    _JSON_CACHE[filename] = json.load(f)
                logging.info(f"[DB] Cached {len(_JSON_CACHE[filename])} entries from {filename}.json")
            except Exception as e:
                logging.error(f"[DB] Failed to load {filename}.json: {e}")
                _JSON_CACHE[filename] = []
        else:
            logging.warning(f"[DB] {filename}.json not found at {path}")
            _JSON_CACHE[filename] = []
    return _JSON_CACHE[filename]

def get_collection_by_account_id(account_id):
    """Fetches the collection for an account."""
    try:
        with db_session() as session:
            rows = session.query(Collection).filter_by(account_id=account_id).all()
            return [_collection_to_dict(r) for r in rows]
    except Exception as e:
        logging.error(f"Error fetching collection for {account_id}: {e}")
        return []

_FREE_ENERGY_GUIDS = None

# Cards deliberately retired from the server catalog. Existing accounts may
# still own their GUIDs in SQLite, so suppress those orphaned stacks instead of
# sending references for archetypes the client can no longer resolve.
_RETIRED_CARD_GUIDS = {
    "51f085aa-d4f0-5f9e-9300-fef9284fed99",  # Electabuzz (BASE1 20)
    "85fdd137-f5d8-5ea2-8b0a-e3655b04f2d3",  # Hitmonchan (BASE1 7)
    "3f1b7976-fea8-502d-9423-b00d63a1bed0",  # Scyther (BASE2 10)
    "ee872288-f81c-4444-465a-42bc8ca232af",  # Custom Card (CUSTOM 1)
}

# Cards removed by the Gym Leader Challenge prune (spirit/tools/prune_to_glc.py)
# are retired the same way, so collections from before the prune stay valid.
GLC_REMOVED_CARDS_PATH = os.path.join(
    os.path.dirname(__file__), "json_data", "glc_removed_cards.json"
)


def _load_glc_removed_guids():
    try:
        with open(GLC_REMOVED_CARDS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return set()
    except (OSError, ValueError) as e:
        logging.error(f"[DB] Could not read {GLC_REMOVED_CARDS_PATH}: {e}")
        return set()
    return {str(entry["guid"]).lower() for entry in data.get("cards", []) if entry.get("guid")}


_RETIRED_CARD_GUIDS |= _load_glc_removed_guids()

def _free_energy_guids():
    """GUIDs of the basic-energy 'Free_Energy' cards, which every player owns unlimited copies of."""
    global _FREE_ENERGY_GUIDS
    if _FREE_ENERGY_GUIDS:
        return _FREE_ENERGY_GUIDS
    try:
        cards_data = card_loader.load_all()
    except Exception as e:
        logging.error(f"[DB] Failed to load card scripts for free-energy list: {e}")
        return set()
    _FREE_ENERGY_GUIDS = {card.guid.lower() for card in cards_data if card.key == "Free_Energy"}
    return _FREE_ENERGY_GUIDS


def get_merged_collection_payload(account_id):
    """The player's owned collection. Only DB-owned items plus unlimited basic energy."""
    cl = []
    seen_guids = set()

    # 1. Items the account actually owns in the database
    for item in get_collection_by_account_id(account_id):
        guid = item["archetype_id"].lower()
        if guid in _RETIRED_CARD_GUIDS:
            continue
        if guid in seen_guids:
            continue
        seen_guids.add(guid)
        cl.append({
            "archetypeID": guid,
            "tradable": int(item["tradable_count"]),
            "nontradable": int(item["nontradable_count"])
        })

    # 2. Basic energy is free/unlimited for everyone (matches live PTCGO)
    for guid in _free_energy_guids():
        if guid in seen_guids:
            continue
        seen_guids.add(guid)
        cl.append({
            "archetypeID": guid,
            "tradable": 99,
            "nontradable": 0
        })

    return cl


def get_owned_counts(account_id):
    """{archetype_guid: total owned copies} for deck validation (basic energy is exempt there)."""
    return {
        item["archetype_id"].lower(): int(item["tradable_count"]) + int(item["nontradable_count"])
        for item in get_collection_by_account_id(account_id)
        if item["archetype_id"].lower() not in _RETIRED_CARD_GUIDS
    }


_ONE_COPY_SUBTYPES = frozenset({"ACE SPEC", "Prism Star", "Radiant", "V-UNION"})
BASIC_ENERGY_GRANT_COUNT = 59


def _all_cards_grant_count(card, regular_count=4):
    """Return the useful collection size for one card in the debug grant."""
    if is_basic_energy_card(card):
        return BASIC_ENERGY_GRANT_COUNT
    if _ONE_COPY_SUBTYPES.intersection(card.subtypes or []):
        return 1
    return regular_count


_GRANT_TARGETS_CACHE = {}


def _grant_targets(cards, count):
    """{guid: target copies}, cached per catalog load (runs on every login)."""
    key = (id(cards), len(cards), count)
    targets = _GRANT_TARGETS_CACHE.get(key)
    if targets is None:
        _GRANT_TARGETS_CACHE.clear()
        targets = {card.guid: _all_cards_grant_count(card, count) for card in cards}
        _GRANT_TARGETS_CACHE[key] = targets
    return targets


def grant_all_cards(account_id, count=4, is_tradable=True, exact=False):
    """Ensure useful deck-building quantities of every card in one transaction.

    Regular cards use ``count`` (normally four), every Basic Energy printing
    gets 59 copies, and cards whose deck rule permits only one get one copy.
    exact=True sets every card to exactly that many (lowering extras too):
    the singleton GLC server gives 1 of each card.

    This runs on EVERY login, so it reads plain rows and writes only what
    differs, in bulk.  Building ~12,000 ORM objects per login held the
    database write lock and the interpreter for seconds, long enough for
    every connected player to time out at once.
    """
    from sqlalchemy import insert, select, update
    try:
        cards = card_loader.load_all()
    except Exception as e:
        logging.error(f"[DB] grant_all_cards: failed to load cards: {e}")
        return 0
    targets = _grant_targets(cards, count)
    try:
        with db_session() as session:
            existing = {
                row[0]: (row[1], row[2]) for row in session.execute(
                    select(Collection.archetype_id, Collection.tradable_count,
                           Collection.nontradable_count)
                    .where(Collection.account_id == account_id))
            }
            inserts, updates = [], []
            for guid, target in targets.items():
                current = existing.get(guid)
                if current is None:
                    tradable = target if (exact or is_tradable) else 0
                    inserts.append({"account_id": account_id, "archetype_id": guid,
                                    "tradable_count": tradable,
                                    "nontradable_count": target - tradable})
                    continue
                tradable, nontradable = current
                if exact:
                    if tradable != target or nontradable:
                        updates.append((guid, target, 0))
                elif is_tradable:
                    if tradable < target:
                        updates.append((guid, target, nontradable))
                elif nontradable < target:
                    updates.append((guid, tradable, target))
            if inserts:
                session.execute(insert(Collection), inserts)
            if updates:
                session.execute(update(Collection), [
                    {"account_id": account_id, "archetype_id": guid,
                     "tradable_count": tradable, "nontradable_count": nontradable}
                    for guid, tradable, nontradable in updates])
            granted = len(targets)
    except Exception as e:
        logging.error(f"[DB] grant_all_cards failed for {account_id}: {e}")
        return 0
    if inserts or updates:
        logging.info(
            "[DB] grant_all_cards: %d new and %d updated collection rows for %s",
            len(inserts), len(updates), account_id,
        )
    return granted

def grant_all_products(account_id, count=1, is_tradable=True):
    """Debug: ensure the account owns `count` copies of every loaded product in one transaction."""
    try:
        if not product_loader.products:
            product_loader.load_all()
        products = product_loader.products
    except Exception as e:
        logging.error(f"[DB] grant_all_products: failed to load products: {e}")
        return 0
    granted = 0
    try:
        with db_session() as session:
            existing = {c.archetype_id: c for c in
                        session.query(Collection).filter_by(account_id=account_id).all()}
            for product in products:
                row = existing.get(product.guid)
                if row is None:
                    row = Collection(account_id=account_id, archetype_id=product.guid,
                                     tradable_count=0, nontradable_count=0)
                    session.add(row)
                    existing[product.guid] = row
                if is_tradable:
                    row.tradable_count = max(row.tradable_count, count)
                else:
                    row.nontradable_count = max(row.nontradable_count, count)
                granted += 1
    except Exception as e:
        logging.error(f"[DB] grant_all_products failed for {account_id}: {e}")
        return 0
    logging.info(f"[DB] grant_all_products: gave {count}x of {granted} products to {account_id}")
    return granted


def add_many_to_collection(account_id, grants, is_tradable=False):
    """Adds many {archetype_id: count} grants to a collection in ONE transaction.

    Replaces N per-row db_session round trips (account creation issued ~140) with a
    single bulk-read + upsert, mirroring grant_all_cards' pattern."""
    if not grants:
        return True
    try:
        with db_session() as session:
            existing = {c.archetype_id: c for c in
                        session.query(Collection).filter_by(account_id=account_id).all()}
            for archetype_id, count in grants.items():
                row = existing.get(archetype_id)
                if row is None:
                    row = Collection(account_id=account_id, archetype_id=archetype_id,
                                     tradable_count=0, nontradable_count=0)
                    session.add(row)
                    existing[archetype_id] = row
                if is_tradable:
                    row.tradable_count += count
                else:
                    row.nontradable_count += count
            return True
    except Exception as e:
        logging.error(f"Error bulk-adding to collection for {account_id}: {e}")
        return False


def add_to_collection(account_id, archetype_id, count=1, is_tradable=False):
    """Adds an item to the account's collection."""
    logging.info(f"[DB] Adding {count}x {archetype_id} (tradable={is_tradable}) to account {account_id}")
    try:
        with db_session() as session:
            item = session.query(Collection).filter_by(account_id=account_id, archetype_id=archetype_id).first()
            if item:
                if is_tradable:
                    item.tradable_count += count
                else:
                    item.nontradable_count += count
            else:
                new_item = Collection(
                    account_id=account_id,
                    archetype_id=archetype_id,
                    tradable_count=count if is_tradable else 0,
                    nontradable_count=0 if is_tradable else count
                )
                session.add(new_item)
            return True
    except Exception as e:
        logging.error(f"Error adding to collection for {account_id}: {e}")
        return False

def remove_from_collection(account_id, archetype_id, count=1, is_tradable=False):
    """Removes an item from the account's collection."""
    logging.info(f"[DB] Removing {count}x {archetype_id} (tradable={is_tradable}) from account {account_id}")
    try:
        with db_session() as session:
            item = session.query(Collection).filter_by(account_id=account_id, archetype_id=archetype_id).first()
            if item:
                logging.info(f"[DB] Found item in collection. Before: tradable={item.tradable_count}, nontradable={item.nontradable_count}")
                if is_tradable:
                    item.tradable_count = max(0, item.tradable_count - count)
                else:
                    item.nontradable_count = max(0, item.nontradable_count - count)
                logging.info(f"[DB] After: tradable={item.tradable_count}, nontradable={item.nontradable_count}")
                return True
            else:
                # If they didn't have a row, they were using the virtual "default seeded" copy (which gives 1x tradable / 0x nontradable).
                # To consume it and prevent it from virtually reappearing, we must create a row with 0 copies!
                logging.info(f"[DB] Item not found in DB. Creating a row with 0 copies to override virtual seeding.")
                new_item = Collection(
                    account_id=account_id,
                    archetype_id=archetype_id,
                    tradable_count=0,
                    nontradable_count=0
                )
                session.add(new_item)
                return True
    except Exception as e:
        logging.error(f"Error removing from collection for {account_id}: {e}")
        return False

def set_archetype_flag(account_id, archetype_id, wanted=None, for_trade=None, review=None):
    """Sets a flag (wanted, for_trade, review) for a given archetype and account."""
    archetype_id = str(archetype_id).lower()
    try:
        with db_session() as session:
            flag = session.query(ArchetypeFlag).filter_by(account_id=account_id, archetype_id=archetype_id).first()
            if not flag:
                flag = ArchetypeFlag(
                    account_id=account_id,
                    archetype_id=archetype_id,
                    wanted=0,
                    for_trade=0,
                    review=0
                )
                session.add(flag)
            
            if wanted is not None:
                flag.wanted = int(wanted)
            if for_trade is not None:
                flag.for_trade = int(for_trade)
            if review is not None:
                flag.review = int(review)
            
            # If all flags are 0, we delete the row to keep the DB clean
            if flag.wanted == 0 and flag.for_trade == 0 and flag.review == 0:
                session.delete(flag)
                
            return True
    except Exception as e:
        logging.error(f"Error setting archetype flag for {account_id}, {archetype_id}: {e}")
        return False

def get_archetype_flags(account_id):
    """Fetches all archetype flags for a given account."""
    try:
        with db_session() as session:
            flags = session.query(ArchetypeFlag).filter_by(account_id=account_id).all()
            return [
                {
                    "archetypeID": f.archetype_id,
                    "wanted": f.wanted,
                    "forTrade": f.for_trade,
                    "review": f.review
                }
                for f in flags
            ]
    except Exception as e:
        logging.error(f"Error getting archetype flags for {account_id}: {e}")
        return []


def strip_economy(account_id):
    """Bare-bones server (config.NO_ECONOMY): zero the wallet and remove any
    booster packs left over from before, so nothing points at the old shop."""
    from spirit.game.attributes import ProductType
    try:
        if not product_loader.products:
            product_loader.load_all()
        packs = {p.guid.lower() for p in product_loader.products
                 if p.product_type == ProductType.PACKS.value}
        with db_session() as session:
            wallet = session.query(Wallet).filter_by(account_id=account_id).first()
            if wallet and (wallet.coins or wallet.gems or wallet.tickets):
                wallet.coins = wallet.gems = wallet.tickets = 0
            if packs:
                for row in session.query(Collection).filter_by(account_id=account_id).all():
                    if row.archetype_id.lower() in packs:
                        session.delete(row)
        return True
    except Exception as e:
        logging.error(f"Error stripping economy for {account_id}: {e}")
        return False
