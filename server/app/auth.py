"""Local password accounts, HR-issued invitations and server-owned roles."""

import hashlib
import ipaddress
import secrets
import threading
import time
from typing import Literal

from fastapi import Depends, HTTPException, Request, Response
from pydantic import Field, SecretStr, field_validator, model_validator
from sqlalchemy import delete, func, select

from .db import AccountSession, AuthAttempt, Employee, Invitation, LoginSession, UserAccount
from .schemas import Identifier, StrictModel

SESSION_SECONDS = 8 * 60 * 60
INVITATION_SECONDS = 24 * 60 * 60
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**17, 8, 1
# Each derivation uses about 128 MiB. Bound concurrent unauthenticated work so
# a burst cannot allocate one such buffer for every FastAPI worker thread.
_password_slots = threading.BoundedSemaphore(2)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_bytes(16)
    derived = _derive_password(password, salt)
    return f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${derived.hex()}'


def _derive_password(password, salt):
    with _password_slots:
        return hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                              dklen=32, maxmem=256 * 1024 * 1024)


def verify_password(password, stored):
    if stored is None:
        # Unknown usernames perform the same expensive operation as known ones.
        hash_password(password)
        return False
    try:
        algorithm, n, r, p, salt, expected = stored.split('$')
        if (algorithm, int(n), int(r), int(p)) != ('scrypt', SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        derived = _derive_password(password, bytes.fromhex(salt))
        return secrets.compare_digest(derived.hex(), expected)
    except (ValueError, TypeError):
        return False


class Credentials(StrictModel):
    username: str = Field(min_length=3, max_length=80, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.@-]*$')
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value):
        return value.lower()


class LoginInput(Credentials):
    role: Literal['employee', 'hr']


class SetupInput(Credentials):
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator('display_name')
    @classmethod
    def nonblank_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Укажите имя')
        return value


class RegisterInput(LoginInput):
    invite_code: str = Field(min_length=32, max_length=128)


class InvitationInput(StrictModel):
    role: Literal['employee', 'hr']
    employee_id: Identifier | None = None

    @model_validator(mode='after')
    def role_link(self):
        if (self.role == 'employee') != (self.employee_id is not None):
            raise ValueError('Сотруднику нужен employee_id; приглашение HR не привязывается к профилю')
        return self


def public_account(account):
    return {'role': account.role, 'employee_id': account.employee_id,
            'username': account.username, 'display_name': account.display_name}


def authenticated_account(db, token, *, allow_demo=False):
    token_hash = digest(token)
    session = db.get(LoginSession, token_hash)
    if session is None or session.expires_at <= time.time():
        raise HTTPException(401, 'Войдите в приложение')
    link = db.get(AccountSession, token_hash)
    if link:
        account = db.get(UserAccount, link.account_id)
        if account is None or account.role not in {'employee', 'hr'}:
            raise HTTPException(401, 'Войдите в приложение')
        if account.role == 'employee' and (not account.employee_id or db.get(Employee, account.employee_id) is None):
            raise HTTPException(401, 'Профиль учётной записи недоступен')
        return public_account(account)
    if allow_demo:
        return {'role': session.role, 'employee_id': session.employee_id}
    raise HTTPException(401, 'Войдите в приложение')


def reserve_attempt(sessions, request, username=None):
    """Persist quota before credential validation, including failed attempts."""
    host = request.client.host if request.client else 'unknown'
    scopes = [(f'ip:{host}', 20)]
    if username:
        # Keep usernames out of the throttle audit table.
        scopes.append((f'user:{digest(username)}', 10))
    with sessions() as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        now = time.time()
        for scope, limit in scopes:
            count = db.scalar(select(func.count()).select_from(AuthAttempt).where(
                AuthAttempt.scope == scope, AuthAttempt.created_at > now - 60))
            if count >= limit:
                raise HTTPException(429, 'Слишком много попыток входа. Повторите через минуту.', headers={'Retry-After': '60'})
        db.execute(delete(AuthAttempt).where(AuthAttempt.created_at <= now - 3600))
        db.add_all([AuthAttempt(scope=scope, created_at=now) for scope, _ in scopes])
        db.commit()


def issue_session(db, account, request, response, settings):
    old = db.get(LoginSession, digest(request.cookies.get('cq_session', '')))
    if old:
        db.delete(old)
        db.flush()
    token = secrets.token_urlsafe(32)
    token_hash = digest(token)
    db.add(LoginSession(token_hash=token_hash, role=account.role, employee_id=account.employee_id,
                        expires_at=time.time() + SESSION_SECONDS))
    db.flush()
    db.add(AccountSession(token_hash=token_hash, account_id=account.id))
    response.set_cookie('cq_session', token, httponly=True, secure=settings.cookie_secure,
                        samesite='strict', max_age=SESSION_SECONDS)
    return public_account(account)


def create_first_hr(db, body, password_hash):
    """Caller holds BEGIN IMMEDIATE; shared by loopback setup and terminal CLI."""
    if db.scalar(select(UserAccount.id).limit(1)) is not None:
        raise HTTPException(409, 'Первичная настройка уже выполнена. Войдите в существующую учётную запись')
    account = UserAccount(id=secrets.token_hex(16), username=body.username, display_name=body.display_name,
                          password_hash=password_hash, role='hr', employee_id=None, created_at=time.time())
    db.add(account)
    db.flush()
    return account


def install_auth_routes(app, settings, hr_dependency):
    api = '/api/v1'

    @app.get(f'{api}/auth/status')
    def status():
        with app.state.sessions() as db:
            setup_required = db.scalar(select(UserAccount.id).limit(1)) is None
        return {'setup_required': setup_required, 'registration': 'invite', 'demo_enabled': settings.demo_mode}

    @app.post(f'{api}/auth/setup')
    def setup(body: SetupInput, request: Request, response: Response):
        host = request.client.host if request.client else ''
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = settings.allow_test_setup and host == 'testclient'
        if not local:
            raise HTTPException(403, 'Первичная настройка доступна только на компьютере сервера')
        reserve_attempt(app.state.sessions, request, body.username)
        password_hash = hash_password(body.password.get_secret_value())
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            account = create_first_hr(db, body, password_hash)
            result = issue_session(db, account, request, response, settings)
            db.commit()
            return result

    @app.post(f'{api}/auth/login')
    def login(body: LoginInput, request: Request, response: Response):
        reserve_attempt(app.state.sessions, request, body.username)
        with app.state.sessions() as db:
            account = db.scalar(select(UserAccount).where(UserAccount.username == body.username))
            valid = verify_password(body.password.get_secret_value(), account.password_hash if account else None)
            if not valid or account.role != body.role:
                raise HTTPException(401, 'Неверные имя пользователя, пароль или роль')
            account_id, checked_hash = account.id, account.password_hash
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            account = db.get(UserAccount, account_id)
            if not account or account.password_hash != checked_hash or account.role != body.role:
                raise HTTPException(401, 'Учётная запись изменилась. Повторите вход')
            result = issue_session(db, account, request, response, settings)
            db.commit()
            return result

    @app.post(f'{api}/auth/register')
    def register(body: RegisterInput, request: Request, response: Response):
        reserve_attempt(app.state.sessions, request, body.username)
        password_hash = hash_password(body.password.get_secret_value())
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            invitation = db.get(Invitation, digest(body.invite_code))
            now = time.time()
            if not invitation or invitation.used_at is not None or invitation.expires_at <= now:
                raise HTTPException(422, 'Приглашение недействительно, уже использовано или истекло')
            if invitation.role != body.role:
                raise HTTPException(403, 'Выбранная роль не соответствует приглашению')
            if db.scalar(select(UserAccount.id).where(UserAccount.username == body.username)):
                raise HTTPException(409, 'Имя пользователя уже занято')
            employee = db.get(Employee, invitation.employee_id) if invitation.employee_id else None
            if invitation.role == 'employee':
                if employee is None:
                    raise HTTPException(422, 'Профиль из приглашения недоступен')
                if db.scalar(select(UserAccount.id).where(UserAccount.employee_id == employee.id)):
                    raise HTTPException(409, 'Для этого сотрудника уже создана учётная запись')
            account = UserAccount(id=secrets.token_hex(16), username=body.username,
                                  display_name=employee.profile['name'] if employee else body.username,
                                  password_hash=password_hash, role=invitation.role,
                                  employee_id=invitation.employee_id, created_at=now)
            db.add(account)
            invitation.used_at = now
            db.flush()
            result = issue_session(db, account, request, response, settings)
            db.commit()
            return result

    @app.get(f'{api}/hr/accounts')
    def accounts(_account=Depends(hr_dependency)):
        with app.state.sessions() as db:
            return [{'id': account.id, **public_account(account), 'created_at': account.created_at}
                    for account in db.scalars(select(UserAccount).order_by(UserAccount.username))]

    @app.post(f'{api}/hr/invitations')
    def invite(body: InvitationInput, _account=Depends(hr_dependency)):
        with app.state.sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            if body.employee_id is not None:
                if db.get(Employee, body.employee_id) is None:
                    raise HTTPException(404, 'Сотрудник не найден')
                if db.scalar(select(UserAccount.id).where(UserAccount.employee_id == body.employee_id)):
                    raise HTTPException(409, 'Для этого сотрудника уже создана учётная запись')
            code = secrets.token_urlsafe(32)
            now = time.time()
            expires_at = now + INVITATION_SECONDS
            db.add(Invitation(code_hash=digest(code), role=body.role, employee_id=body.employee_id,
                              created_at=now, expires_at=expires_at, used_at=None))
            db.commit()
            return {'invite_code': code, 'role': body.role, 'employee_id': body.employee_id, 'expires_at': expires_at}
