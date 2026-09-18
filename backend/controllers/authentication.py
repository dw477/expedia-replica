"""CSV-backed authentication and SQLite-backed opaque browser sessions."""

import hashlib
import re
import secrets
import time
from pathlib import Path

from backend.controllers.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseController,
    DatabaseError,
    RecordNotFoundError,
)
from backend.controllers.passwords import hash_password, verify_password
from backend.models import AuthSession, User, UserAccount

SESSION_LIFETIME_SECONDS = 8 * 60 * 60
# Unknown usernames take the same password derivation path as known usernames.
# This is an unprivileged dummy hash, not an account credential.
_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


class AuthenticationError(RuntimeError):
    """Base authentication failure."""


class InvalidCredentialsError(AuthenticationError):
    """The username/password pair is invalid."""


class AuthenticationRequiredError(AuthenticationError):
    """The browser session is missing, expired, revoked, or disabled."""


class AuthenticationDataError(AuthenticationError):
    """Credential/session storage cannot be accessed safely."""


def _session_id(token: str | None) -> str | None:
    if token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _credential_version(account: UserAccount) -> str:
    return hashlib.sha256(
        f"{account.username}:{account.password_hash}".encode("utf-8")
    ).hexdigest()


class AuthenticationController:
    """Public contract: login -> (User, token), current_user -> User, logout -> None.

    Passwords/usernames are always read from users.csv through the database
    controller. Only token digests, user references, expiry, and credential versions
    enter SQLite. Raw tokens may only cross into the HTTP adapter's cookie setter.
    """

    def __init__(
        self,
        database_path: str | Path = DEFAULT_DATABASE_PATH,
        data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
    ) -> None:
        self.database = DatabaseController(database_path)
        self.data_directory = Path(data_directory)

    def login(
        self,
        username: str,
        password: str,
        previous_token: str | None = None,
    ) -> tuple[User, str]:
        try:
            accounts = self.database.list_user_accounts(self.data_directory)
            normalized = username.strip().casefold()
            account = next(
                (item for item in accounts if item.username == normalized), None
            )
            valid = verify_password(
                password, account.password_hash if account else _DUMMY_PASSWORD_HASH
            )
            if account is None or not valid:
                raise InvalidCredentialsError("Invalid username or password.")
            token = secrets.token_urlsafe(32)
            identifier = _session_id(token)
            assert identifier is not None
            now = int(time.time())
            with self.database.transaction():
                self.database.delete_expired_sessions(now)
                user = self.database.get(User, account.user_id)
                self.logout(previous_token)
                self.database.create(
                    AuthSession(
                        identifier,
                        user.user_id,
                        now + SESSION_LIFETIME_SECONDS,
                        _credential_version(account),
                    )
                )
            return user, token
        except DatabaseError as error:
            raise AuthenticationDataError(
                "Authentication is unavailable. Please try again."
            ) from error

    def current_user(self, token: str | None) -> User:
        identifier = _session_id(token)
        if identifier is None:
            raise AuthenticationRequiredError("Sign in to continue.")
        try:
            with self.database.transaction(write=False):
                session = self.database.get(AuthSession, identifier)
                if session.expires_at <= int(time.time()):
                    raise AuthenticationRequiredError(
                        "Your session expired. Sign in again."
                    )
                accounts = self.database.list_user_accounts(self.data_directory)
                account = next(
                    (item for item in accounts if item.user_id == session.user_id), None
                )
                if (
                    account is None
                    or _credential_version(account) != session.credential_version
                ):
                    raise AuthenticationRequiredError("Sign in again to continue.")
                return self.database.get(User, session.user_id)
        except RecordNotFoundError as error:
            raise AuthenticationRequiredError("Sign in to continue.") from error
        except DatabaseError as error:
            raise AuthenticationDataError(
                "Authentication is unavailable. Please try again."
            ) from error

    def logout(self, token: str | None) -> None:
        identifier = _session_id(token)
        if identifier is None:
            return
        try:
            self.database.delete(AuthSession, identifier)
        except RecordNotFoundError:
            pass
        except DatabaseError as error:
            raise AuthenticationDataError(
                "Could not sign out. Please try again."
            ) from error
