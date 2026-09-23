"""Interactive local administrator tool for a first or additional HR account."""

import argparse
import getpass
import os
import secrets
import sys
import time

from pydantic import ValidationError
from sqlalchemy import select

from .auth import SetupInput, hash_password
from .config import ROOT, Settings
from .db import UserAccount, connect


def local_database_url():
    settings = Settings()
    kit = os.getenv('CAREER_QUEST_KIT_DIR', '').strip()
    bundled = ROOT / 'career_quest_dataset/case_1/career_quest_dataset'
    if not os.getenv('DATABASE_URL') and (kit or bundled.is_dir()):
        return f'sqlite:///{(ROOT / "data/career-quest-kit.db").as_posix()}'
    return settings.database_url


def main():
    argparse.ArgumentParser(description='Create a local Career Quest HR account interactively.').parse_args()
    if not sys.stdin.isatty():
        print('Run this tool in an interactive local terminal; passwords cannot be passed as arguments.')
        return 1

    # Select the same database as start.bat, honoring DATABASE_URL and the local Kit.
    database_url = local_database_url()
    print(f'Database: {database_url.removeprefix("sqlite:///")}')
    username = input('New HR username: ')
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
    engine, sessions = connect(database_url)
    try:
        with sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            if db.scalar(select(UserAccount.id).where(UserAccount.username == body.username).limit(1)):
                print('Username is already in use. Choose a different username; existing accounts were not changed.')
                return 1
            db.add(UserAccount(id=secrets.token_hex(16), username=body.username,
                               display_name=body.display_name, password_hash=password_hash,
                               role='hr', employee_id=None, created_at=time.time()))
            db.commit()
        print('HR account created. Start Career Quest and sign in with the HR role and new credentials.')
        return 0
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
