import logging
import uuid
import hashlib
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from spirit.database import db_session, Account
from spirit.game.starter_content import grant_starter_content

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def _account_to_dict(acc):
    if not acc:
        return None
    return {
        "id": acc.id,
        "account_id": acc.account_id,
        "username": acc.username,
        "password_hash": acc.password_hash,
        "screen_name": acc.screen_name,
        "created_at": acc.created_at
    }

def get_account_by_username(username):
    """Fetches an account from the database by username."""
    try:
        with db_session() as session:
            acc = session.query(Account).filter(func.lower(Account.username) == username.lower()).first()
            return _account_to_dict(acc)
    except Exception as e:
        logging.error(f"Error fetching account by username {username}: {e}")
        return None

def get_account_by_id(account_id):
    """Fetches an account from the database by account_id."""
    try:
        with db_session() as session:
            acc = session.query(Account).filter_by(account_id=account_id).first()
            return _account_to_dict(acc)
    except Exception as e:
        logging.error(f"Error fetching account by ID {account_id}: {e}")
        return None

def create_account(username, password):
    """Creates a new account (used for auto-registration)."""
    try:
        with db_session() as session:
            acc_id = str(uuid.uuid4())
            pwd_hash = hash_password(password)

            new_acc = Account(
                account_id=acc_id,
                username=username,
                password_hash=pwd_hash,
                screen_name=username
            )
            session.add(new_acc)
            session.flush()  # Populates id and created_at
            acc_dict = _account_to_dict(new_acc)
    except IntegrityError:
        # Username already exists
        return None
    except Exception as e:
        logging.error(f"Error creating account: {e}")
        return None

    # Grant packs/cosmetics outside the session (grant opens its own sessions).
    # Saved decks are intentionally not created for new accounts.
    try:
        grant_starter_content(acc_dict["account_id"])
    except Exception as e:
        logging.error(f"Error granting starter content to new account {username}: {e}")

    return acc_dict

def verify_password(stored_hash, provided_password):
    """Verifies a given password against the stored hash."""
    return stored_hash == hash_password(provided_password)


# ---------------------------------------------------------------------------
# Guest (DeviceID) accounts.
#
# The client's device login carries no user name, so these accounts are keyed
# by the connecting IP address.  They used to be named "guest_<IP>", and that
# name was also the public screen name: every player could read a guest's IP
# address.  The key is now a keyed hash of the IP (not reversible without the
# server's private salt) and the screen name is a neutral "Guest-XXXXXX".
# ---------------------------------------------------------------------------
import hashlib as _hashlib
import hmac as _hmac
import os as _os
import secrets as _secrets

_GUEST_SALT_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "guest_salt.key")
_guest_salt_cache = []


def _guest_salt() -> bytes:
    if not _guest_salt_cache:
        try:
            with open(_GUEST_SALT_PATH, "rb") as handle:
                salt = handle.read().strip()
        except OSError:
            salt = b""
        if not salt:
            salt = _secrets.token_hex(32).encode()
            with open(_GUEST_SALT_PATH, "wb") as handle:
                handle.write(salt)
            try:
                _os.chmod(_GUEST_SALT_PATH, 0o600)
            except OSError:
                pass
        _guest_salt_cache.append(salt)
    return _guest_salt_cache[0]


def guest_identity(ip: str):
    """(username, screen_name) for a device login from ``ip``."""
    digest = _hmac.new(_guest_salt(), ip.encode(), _hashlib.sha256).hexdigest()
    return f"guest_{digest[:20]}", f"Guest-{digest[:6].upper()}"


def get_or_create_guest_account(ip: str, password: str):
    """Device-login account for ``ip``; renames a legacy ``guest_<IP>`` one."""
    username, screen_name = guest_identity(ip)
    account = get_account_by_username(username)
    if account:
        return account
    legacy = f"guest_{ip}"
    try:
        with db_session() as session:
            row = session.query(Account).filter_by(username=legacy).first()
            if row is not None:
                row.username = username
                row.screen_name = screen_name
    except Exception as e:
        logging.error(f"[DB] Renaming legacy guest account failed: {e}")
    account = get_account_by_username(username)
    if account:
        return account
    account = create_account(username, password)
    if account:
        try:
            with db_session() as session:
                row = session.query(Account).filter_by(username=username).first()
                if row is not None:
                    row.screen_name = screen_name
        except Exception as e:
            logging.error(f"[DB] Setting guest screen name failed: {e}")
        account = get_account_by_username(username)
    return account


def scrub_legacy_guest_names() -> int:
    """Hide the IP in every existing ``guest_<IP>`` account (run at startup)."""
    import re
    renamed = 0
    try:
        with db_session() as session:
            for row in session.query(Account).filter(Account.username.like("guest\\_%", escape="\\")):
                ip = row.username[len("guest_"):]
                if not re.fullmatch(r"[0-9a-fA-F:.]+", ip) or "." not in ip and ":" not in ip:
                    continue
                username, screen_name = guest_identity(ip)
                if session.query(Account).filter_by(username=username).first() is not None:
                    row.screen_name = screen_name
                    continue
                row.username, row.screen_name = username, screen_name
                renamed += 1
    except Exception as e:
        logging.error(f"[DB] Scrubbing guest account names failed: {e}")
    if renamed:
        logging.info(f"[DB] Hid the IP address in {renamed} guest account name(s).")
    return renamed

