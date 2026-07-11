from __future__ import annotations

import argparse
from pathlib import Path

from user_accounts import UserAccountStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Administrare utilizatori Co-pilot Facultate")
    parser.add_argument("username", help="Numele noului utilizator")
    parser.add_argument("--password", help="Parola utilizatorului")
    parser.add_argument("--token", help="Token API fix; implicit este generat automat")
    args = parser.parse_args()

    store = UserAccountStore(Path(__file__).resolve().parent / "storage")
    username, token = store.create_user(
        args.username,
        password=args.password,
        token=args.token,
    )
    print(f"Utilizator: {username}")
    print(f"Token API: {token}")
    print("Păstrează tokenul în siguranță; nu este afișat din nou.")


if __name__ == "__main__":
    main()
