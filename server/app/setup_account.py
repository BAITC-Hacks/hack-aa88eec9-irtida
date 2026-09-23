"""Interactive first-HR setup for containers; never accepts password arguments."""

import argparse
import getpass
import sys

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from .auth import SetupInput, create_first_hr, hash_password
from .config import Settings
from .db import UserAccount, connect


def main():
    argparse.ArgumentParser(description='Create the first Career Quest HR account interactively.').parse_args()
    if not sys.stdin.isatty():
        print('Run this command in an interactive terminal; passwords are never accepted as command arguments.')
        return 1
    engine, sessions = connect(Settings().database_url)
    try:
        with sessions() as db:
            if db.scalar(select(UserAccount.id).limit(1)) is not None:
                print('Initial setup is already complete. Sign in with the existing account.')
                return 1
        username = input('Username: ')
        display_name = input('Display name: ')
        password = getpass.getpass('Password (12-128 characters): ')
        confirmation = getpass.getpass('Repeat password: ')
        if password != confirmation:
            print('Passwords do not match. No account was created.')
            return 1
        try:
            body = SetupInput(username=username, password=password, display_name=display_name)
        except ValidationError as exc:
            print('Invalid account: ' + '; '.join(error['msg'] for error in exc.errors(include_input=False)))
            return 1
        password_hash = hash_password(body.password.get_secret_value())
        with sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            try:
                create_first_hr(db, body, password_hash)
            except HTTPException as exc:
                print(exc.detail)
                return 1
            db.commit()
        print('First HR account created. Sign in through the application.')
        return 0
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
