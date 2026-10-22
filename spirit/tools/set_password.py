"""Change an account's password (game login and admin page share it).

Usage (on the server, from the project folder):
    ./venv/bin/python -m spirit.tools.set_password <username>

You're asked for the new password twice; it isn't shown or saved in the
shell history.  Works while the server is running; the next login uses it.
"""
import getpass
import sys

from sqlalchemy import func

from spirit.database import db_session, Account
from spirit.database.accounts import hash_password

MIN_LENGTH = 12


def set_password(username: str, password: str) -> bool:
    with db_session() as session:
        acc = session.query(Account).filter(
            func.lower(Account.username) == username.lower()).first()
        if not acc:
            return False
        acc.password_hash = hash_password(password)
        return True


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    username = argv[1]
    password = getpass.getpass(f"New password for {username}: ")
    if len(password) < MIN_LENGTH:
        print(f"Too short: use at least {MIN_LENGTH} characters.")
        return 1
    if getpass.getpass("Type it again: ") != password:
        print("The two passwords didn't match. Nothing was changed.")
        return 1
    if not set_password(username, password):
        print(f"No account called '{username}'. Nothing was changed.")
        return 1
    print(f"Password changed for {username}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
