"""SQLite connection, schema, and one-time starter-data initialization."""

from __future__ import annotations

import base64
import csv
import fcntl
import io
import json
import logging
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import fields
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator, TypeVar

from backend.models import AuthSession, Booking, Hotel, Trip, User, UserAccount
from backend.models.authentication import USER_ACCOUNT_COLUMNS
from backend.models.entities import validate_nightly_rate
from backend.models.schema import SCHEMA_STATEMENTS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIRECTORY = PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = Path(
    os.environ.get(
        "EXPEDIA_DATABASE_PATH", PROJECT_ROOT / "backend" / "expedia.sqlite3"
    )
)


class DatabaseError(RuntimeError):
    """Raised when the application database cannot be prepared or queried."""


def connect_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> sqlite3.Connection:
    """Open a configured SQLite connection with application safety settings."""

    path = Path(database_path)
    try:
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection
    except sqlite3.Error as error:
        raise DatabaseError(
            f"Could not open SQLite database {path}: {error}"
        ) from error


def initialize_database(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
) -> bool:
    """Create the schema and import all starter CSVs exactly once.

    Returns ``True`` when this call imports the starter records and ``False`` when
    the database was already initialized.
    """

    path = Path(database_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise DatabaseError(
            f"Could not create the SQLite database directory {path.parent}: {error}"
        ) from error

    connection = connect_database(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        connection.execute(
            "INSERT INTO app_metadata(key, value) VALUES ('schema_version', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        with _account_file_lock(Path(data_directory) / "users.csv"):
            _recover_registration(connection, Path(data_directory) / "users.csv")
            seed_marker = connection.execute(
                "SELECT value FROM app_metadata WHERE key = 'starter_data_seeded'"
            ).fetchone()
            if seed_marker is not None:
                _check_references(connection)
                connection.commit()
                return False

            _seed_database(connection, Path(data_directory))
            _check_references(connection)
            connection.execute(
                "INSERT INTO app_metadata(key, value) VALUES (?, ?)",
                ("starter_data_seeded", "1"),
            )
            connection.commit()
            return True
    except (csv.Error, OSError, sqlite3.Error, UnicodeError, ValueError) as error:
        connection.rollback()
        raise DatabaseError(
            f"Could not initialize SQLite database {path}: {error}"
        ) from error
    finally:
        connection.close()


def _seed_database(connection: sqlite3.Connection, data_directory: Path) -> None:
    sources: tuple[
        tuple[type[Hotel | User | Trip | Booking], str, tuple[str, ...]], ...
    ] = (
        (
            Hotel,
            "hotels.csv",
            ("hotel_id", "hotel_name", "city", "state", "nightly_rate_usd"),
        ),
        (User, "users.csv", USER_ACCOUNT_COLUMNS),
        (
            Trip,
            "trips.csv",
            ("trip_id", "hotel_id", "trip_name", "check_in", "check_out"),
        ),
        (
            Booking,
            "bookings.csv",
            ("booking_id", "user_id", "trip_id", "booked_on", "status"),
        ),
    )
    account_usernames: set[str] = set()
    # Parents are imported before children. Every CSV row uses the same entity
    # validation as CRUD, with source/row context added to parsing failures.
    for model, filename, names in sources:
        columns = _columns(model)
        for source, row in _read_csv(data_directory / filename, names):
            values: dict[str, Any] = {
                name: _required(row, name, source) for name in names
            }
            if model is User:
                account = UserAccount(**values)
                if account.username in account_usernames:
                    raise ValueError(f"{source} has duplicate username")
                account_usernames.add(account.username)
                values = {
                    "user_id": account.user_id,
                    "display_name": account.display_name,
                }
            if model is Hotel:
                values["nightly_rate_usd"] = (
                    Decimal(_money_to_cents(row, "nightly_rate_usd", source)) / 100
                )
            for name in ("check_in", "check_out", "booked_on"):
                if name in values:
                    values[name] = date.fromisoformat(_iso_date(row, name, source))
            try:
                entity = model(**values)
            except ValueError as error:
                raise ValueError(f"{source}: {error}") from error
            connection.execute(
                f"INSERT INTO {ENTITY_TABLES[model]} ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                _values(entity),
            )


def _read_csv(
    path: Path, expected_fields: tuple[str, ...]
) -> Iterator[tuple[str, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise ValueError(
                f"{path.name} must have columns {', '.join(expected_fields)}"
            )
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"{path.name} row {row_number} has extra columns")
            yield f"{path.name} row {row_number}", row


def _required(row: dict[str, str], field: str, source: str) -> str:
    raw_value = row.get(field)
    value = raw_value.strip() if isinstance(raw_value, str) else ""
    if not value:
        raise ValueError(f"{source} is missing {field}")
    return value


def _iso_date(row: dict[str, str], field: str, source: str) -> str:
    value = _required(row, field, source)
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{source} has invalid {field} {value!r}") from error


def _money_to_cents(row: dict[str, str], field: str, source: str) -> int:
    value = _required(row, field, source)
    try:
        amount = Decimal(value)
        validate_nightly_rate(amount)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{source} has invalid {field} {value!r}") from error
    return int(amount * 100)


@contextmanager
def _account_file_lock(path: Path) -> Iterator[None]:
    """Lock a stable sidecar inode across atomic replacements and server processes."""
    with path.with_name(f".{path.name}.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _atomic_write(path: Path, content: bytes) -> None:
    """Publish a complete durable file; temporary files are owner-readable only."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name.lstrip('.')}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _read_accounts(path: Path) -> list[UserAccount]:
    accounts = [
        UserAccount(
            **{name: _required(row, name, source) for name in USER_ACCOUNT_COLUMNS}
        )
        for source, row in _read_csv(path, USER_ACCOUNT_COLUMNS)
    ]
    if len({account.username for account in accounts}) != len(accounts):
        raise ValueError("users.csv contains duplicate usernames")
    if len({account.user_id for account in accounts}) != len(accounts):
        raise ValueError("users.csv contains duplicate user IDs")
    return accounts


def _journal_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.registration.json")


def _recover_registration(connection: sqlite3.Connection, path: Path) -> None:
    """SQLite's committed identity decides whether to keep or undo a CSV append.

    This journal bridges two stores without putting credential hashes in SQLite.
    Call only with the account-file lock held. Recovery never recreates identities.
    """
    journal = _journal_path(path)
    if not journal.exists():
        return
    payload = json.loads(journal.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"user_id", "original_csv"}:
        raise ValueError("Invalid account registration journal")
    if not isinstance(payload["user_id"], str) or not isinstance(
        payload["original_csv"], str
    ):
        raise ValueError("Invalid account registration journal fields")
    original = base64.b64decode(payload["original_csv"], validate=True)
    saved = connection.execute(
        "SELECT 1 FROM users WHERE user_id = ?", (payload["user_id"],)
    ).fetchone()
    if saved is None:
        _atomic_write(path, original)
    elif payload["user_id"] not in {
        account.user_id for account in _read_accounts(path)
    }:
        raise ValueError("Committed account is missing from users.csv")
    journal.unlink()


class RecordNotFoundError(DatabaseError):
    """A requested entity or referenced parent does not exist."""


class AccountUsernameConflictError(DatabaseError):
    """A username is already reserved in the credential CSV."""


class ReferenceConflictError(DatabaseError):
    """Deleting a parent would leave dependent rows without a reference."""


class RecordConflictError(DatabaseError):
    """An entity violates a uniqueness or persistence constraint."""


# These identifiers are internal constants. Never accept table/column names from
# callers; SQL values are always parameterized.
Entity = TypeVar("Entity", bound=Hotel | User | Trip | Booking | AuthSession)
ENTITY_TABLES: dict[type, str] = {
    Hotel: "hotels",
    User: "users",
    Trip: "trips",
    Booking: "bookings",
    AuthSession: "auth_sessions",
}
ENTITY_REFERENCES: dict[
    type,
    tuple[tuple[str, type[Hotel | User | Trip | Booking | AuthSession]], ...],
] = {
    AuthSession: (("user_id", User),),
    Trip: (("hotel_id", Hotel),),
    Booking: (("user_id", User), ("trip_id", Trip)),
}


def _check_references(connection: sqlite3.Connection) -> None:
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise ValueError("Database contains invalid foreign-key references")


def _columns(model: type[Entity]) -> tuple[str, ...]:
    if model not in ENTITY_TABLES:
        raise ValueError("Unsupported entity model")
    return tuple(
        "nightly_rate_cents" if field.name == "nightly_rate_usd" else field.name
        for field in fields(model)
    )


def _values(entity: Entity) -> tuple[Any, ...]:
    values = []
    for field in fields(entity):
        value = getattr(entity, field.name)
        if field.name == "nightly_rate_usd":
            value = int(value * 100)
        elif type(value) is date:
            value = value.isoformat()
        values.append(value)
    return tuple(values)


def _from_row(model: type[Entity], row: sqlite3.Row) -> Entity:
    values = dict(row)
    if model is Hotel:
        values["nightly_rate_usd"] = Decimal(values.pop("nightly_rate_cents")) / 100
    for name in ("check_in", "check_out", "booked_on"):
        if name in values:
            values[name] = date.fromisoformat(values[name])
    return model(**values)


class DatabaseController:
    """Typed CRUD contract for all entities; owns connections and transactions.

    Call initialize() before using a new database. Reads return immutable entities;
    create/update take complete validated entities; IDs cannot be changed by update.
    Missing records/references and constraint conflicts have explicit error types.
    """

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database_path = Path(database_path)
        self._active_connection: sqlite3.Connection | None = None
        self._transaction_write = False

    def initialize(self, data_directory: str | Path = DEFAULT_DATA_DIRECTORY) -> bool:
        return initialize_database(self.database_path, data_directory)

    def delete_expired_sessions(self, now: int) -> int:
        """Prune expired authentication rows; return the number removed."""
        if type(now) is not int or now < 0:
            raise ValueError("now must be a non-negative Unix timestamp")
        with self._connection(write=True) as connection:
            result = connection.execute(
                "DELETE FROM auth_sessions WHERE expires_at <= ?", (now,)
            )
            return result.rowcount

    def list_user_accounts(
        self,
        data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
    ) -> list[UserAccount]:
        """Read/recover CSV credentials before opening a database read transaction.

        File reads must precede long-lived database reads to avoid a reader waiting
        for a file lock while a registration writer waits to commit its database.
        """
        if self._active_connection is not None:
            raise DatabaseError(
                "Read account files before entering a database transaction"
            )
        path = Path(data_directory) / "users.csv"
        try:
            with _account_file_lock(path):
                with self._connection() as connection:
                    _recover_registration(connection, path)
                accounts = _read_accounts(path)
            active_ids = {user.user_id for user in self.list(User)}
            return [account for account in accounts if account.user_id in active_ids]
        except (csv.Error, OSError, UnicodeError, ValueError) as error:
            raise DatabaseError(
                "Could not load user accounts from users.csv"
            ) from error

    def register_user_account(
        self,
        account: UserAccount,
        session: AuthSession,
        data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
        previous_session_id: str | None = None,
    ) -> User:
        """Create CSV credentials, SQLite identity, and initial session together.

        A file lock protects username/ID uniqueness across processes. A durable
        journal restores the old CSV if SQL fails or the process stops before SQL
        commits. The SQL identity is the recovery commit marker. No credentials
        enter SQLite; only the journal's old CSV snapshot is temporarily retained.
        This operation owns its transaction; callers must not wrap it in one.
        """
        if self._active_connection is not None:
            raise DatabaseError("Account registration owns its database transaction")
        if session.user_id != account.user_id:
            raise ValueError("Registration session must reference the new account")
        path = Path(data_directory) / "users.csv"
        user = User(account.user_id, account.display_name)
        try:
            with self._connection(write=True) as connection:
                with _account_file_lock(path):
                    _recover_registration(connection, path)
                    accounts = _read_accounts(path)
                    if account.username in {item.username for item in accounts}:
                        raise AccountUsernameConflictError(
                            "That username is already in use."
                        )
                    if (
                        account.user_id in {item.user_id for item in accounts}
                        or connection.execute(
                            "SELECT 1 FROM users WHERE user_id = ?", (account.user_id,)
                        ).fetchone()
                        is not None
                    ):
                        raise RecordConflictError(
                            "The generated user ID is already in use."
                        )
                    original = path.read_bytes()
                    output = io.StringIO(newline="")
                    writer = csv.writer(output, lineterminator="\n")
                    writer.writerow(USER_ACCOUNT_COLUMNS)
                    writer.writerows(
                        (
                            item.user_id,
                            item.display_name,
                            item.username,
                            item.password_hash,
                        )
                        for item in [*accounts, account]
                    )
                    journal = _journal_path(path)
                    _atomic_write(
                        journal,
                        json.dumps(
                            {
                                "user_id": account.user_id,
                                "original_csv": base64.b64encode(original).decode(
                                    "ascii"
                                ),
                            }
                        ).encode("utf-8"),
                    )
                    try:
                        connection.execute(
                            "INSERT INTO users(user_id, display_name) VALUES (?, ?)",
                            (user.user_id, user.display_name),
                        )
                        connection.execute(
                            "INSERT INTO auth_sessions(session_id, user_id, expires_at, credential_version) VALUES (?, ?, ?, ?)",
                            _values(session),
                        )
                        if previous_session_id is not None:
                            connection.execute(
                                "DELETE FROM auth_sessions WHERE session_id = ?",
                                (previous_session_id,),
                            )
                        _atomic_write(path, output.getvalue().encode("utf-8-sig"))
                        connection.commit()
                    except BaseException:
                        connection.rollback()
                        _recover_registration(connection, path)
                        raise
                    try:
                        journal.unlink()
                    except OSError:
                        # The committed account is usable. The next credential read
                        # or startup finishes this idempotent housekeeping step.
                        logging.getLogger(__name__).warning(
                            "Account saved; registration journal cleanup deferred"
                        )
            return user
        except (csv.Error, OSError, UnicodeError, ValueError) as error:
            raise DatabaseError("Could not save the new account") from error

    @contextmanager
    def transaction(self, *, write: bool = True) -> Iterator[DatabaseController]:
        """Group CRUD calls into one atomic operation and consistent read snapshot.

        The yielded controller uses a single connection until this context exits.
        Instances are scoped to one workflow; do not share them between threads.
        Nested transactions are unsupported, and read transactions cannot mutate.
        """
        if self._active_connection is not None:
            raise DatabaseError("Nested transactions are unsupported")
        with self._connection(write=write) as connection:
            if not write:
                connection.execute("BEGIN")
            self._active_connection = connection
            self._transaction_write = write
            try:
                yield self
            finally:
                self._active_connection = None
                self._transaction_write = False

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        owns_connection = self._active_connection is None
        if not owns_connection and write and not self._transaction_write:
            raise DatabaseError("Cannot write in a read transaction")
        connection = self._active_connection or connect_database(self.database_path)
        try:
            # Acquire the write lock before reference checks, so another writer
            # cannot delete a parent between validation and persistence.
            if owns_connection and write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if owns_connection and write:
                connection.commit()
        except sqlite3.IntegrityError as error:
            if owns_connection:
                connection.rollback()
            if "FOREIGN KEY" in str(error):
                raise ReferenceConflictError(
                    "Entity is still referenced by another record"
                ) from error
            raise RecordConflictError(
                "Entity violates a uniqueness or data constraint"
            ) from error
        except sqlite3.Error as error:
            if owns_connection:
                connection.rollback()
            raise DatabaseError(f"Database operation failed: {error}") from error
        except (TypeError, ValueError, OverflowError) as error:
            if owns_connection:
                connection.rollback()
            raise DatabaseError(f"Invalid stored entity: {error}") from error
        except BaseException:
            if owns_connection:
                connection.rollback()
            raise
        finally:
            if owns_connection:
                connection.close()

    def get(self, model: type[Entity], record_id: str) -> Entity:
        columns = _columns(model)
        with self._connection() as connection:
            return self._get(connection, model, record_id, columns)

    def _get(
        self,
        connection: sqlite3.Connection,
        model: type[Entity],
        record_id: str,
        columns: tuple[str, ...] | None = None,
    ) -> Entity:
        columns = columns or _columns(model)
        row = connection.execute(
            f"SELECT {', '.join(columns)} FROM {ENTITY_TABLES[model]} WHERE {columns[0]} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(f"{model.__name__} {record_id!r} was not found.")
        return _from_row(model, row)

    def list(self, model: type[Entity]) -> list[Entity]:
        columns = _columns(model)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(columns)} FROM {ENTITY_TABLES[model]} ORDER BY {columns[0]}"
            ).fetchall()
            return [_from_row(model, row) for row in rows]

    def _check_entity_references(
        self, connection: sqlite3.Connection, entity: Entity
    ) -> None:
        for field, parent in ENTITY_REFERENCES.get(type(entity), ()):
            self._get(connection, parent, getattr(entity, field))

    def create(self, entity: Entity) -> Entity:
        model = type(entity)
        columns = _columns(model)
        with self._connection(write=True) as connection:
            self._check_entity_references(connection, entity)
            connection.execute(
                f"INSERT INTO {ENTITY_TABLES[model]} ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                _values(entity),
            )
            return self._get(connection, model, _values(entity)[0])

    def update(self, entity: Entity) -> Entity:
        model = type(entity)
        columns = _columns(model)
        values: tuple[Any, ...] = _values(entity)
        with self._connection(write=True) as connection:
            self._get(connection, model, values[0])
            self._check_entity_references(connection, entity)
            connection.execute(
                f"UPDATE {ENTITY_TABLES[model]} SET "
                f"{', '.join(f'{column} = ?' for column in columns[1:])} "
                f"WHERE {columns[0]} = ?",
                (*values[1:], values[0]),
            )
            return self._get(connection, model, values[0])

    def delete(self, model: type[Entity], record_id: str) -> None:
        columns = _columns(model)
        with self._connection(write=True) as connection:
            self._get(connection, model, record_id)
            connection.execute(
                f"DELETE FROM {ENTITY_TABLES[model]} WHERE {columns[0]} = ?",
                (record_id,),
            )
