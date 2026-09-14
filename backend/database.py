"""SQLite connection, schema, and one-time starter-data initialization."""

from __future__ import annotations

import csv
import os
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIRECTORY = PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = Path(
    os.environ.get(
        "EXPEDIA_DATABASE_PATH", PROJECT_ROOT / "backend" / "expedia.sqlite3"
    )
)


class DatabaseError(RuntimeError):
    """Raised when the application database cannot be prepared or queried."""


# This module is the source of truth for the SQLite schema. Tables are deliberately
# created without destructive migrations so an existing development database keeps
# application changes made after the starter CSVs are imported.
SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS app_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hotels (
        hotel_id TEXT PRIMARY KEY,
        hotel_name TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        nightly_rate_cents INTEGER NOT NULL CHECK (nightly_rate_cents >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trips (
        trip_id TEXT PRIMARY KEY,
        hotel_id TEXT NOT NULL REFERENCES hotels(hotel_id),
        trip_name TEXT NOT NULL,
        check_in TEXT NOT NULL CHECK (date(check_in) IS NOT NULL),
        check_out TEXT NOT NULL CHECK (
            date(check_out) IS NOT NULL AND check_out > check_in
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bookings (
        booking_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        trip_id TEXT NOT NULL REFERENCES trips(trip_id),
        booked_on TEXT NOT NULL CHECK (date(booked_on) IS NOT NULL),
        status TEXT NOT NULL CHECK (status IN ('confirmed', 'cancelled'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hotels_name ON hotels(hotel_name)",
    "CREATE INDEX IF NOT EXISTS idx_trips_hotel_id ON trips(hotel_id)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_trip_id ON bookings(trip_id)",
)


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

        seed_marker = connection.execute(
            "SELECT value FROM app_metadata WHERE key = 'starter_data_seeded'"
        ).fetchone()
        if seed_marker is not None:
            connection.commit()
            return False

        _seed_database(connection, Path(data_directory))
        connection.execute(
            "INSERT INTO app_metadata(key, value) VALUES (?, ?)",
            ("starter_data_seeded", "1"),
        )
        connection.execute(
            "INSERT INTO app_metadata(key, value) VALUES (?, ?)",
            ("schema_version", "1"),
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
    hotels = list(
        _read_csv(
            data_directory / "hotels.csv",
            ("hotel_id", "hotel_name", "city", "state", "nightly_rate_usd"),
        )
    )
    users = list(
        _read_csv(data_directory / "users.csv", ("user_id", "display_name"))
    )
    trips = list(
        _read_csv(
            data_directory / "trips.csv",
            ("trip_id", "hotel_id", "trip_name", "check_in", "check_out"),
        )
    )
    bookings = list(
        _read_csv(
            data_directory / "bookings.csv",
            ("booking_id", "user_id", "trip_id", "booked_on", "status"),
        )
    )

    connection.executemany(
        """
        INSERT INTO hotels(
            hotel_id, hotel_name, city, state, nightly_rate_cents
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                _required(row, "hotel_id", source),
                _required(row, "hotel_name", source),
                _required(row, "city", source),
                _required(row, "state", source),
                _money_to_cents(row, "nightly_rate_usd", source),
            )
            for source, row in hotels
        ],
    )
    connection.executemany(
        "INSERT INTO users(user_id, display_name) VALUES (?, ?)",
        [
            (
                _required(row, "user_id", source),
                _required(row, "display_name", source),
            )
            for source, row in users
        ],
    )
    connection.executemany(
        """
        INSERT INTO trips(
            trip_id, hotel_id, trip_name, check_in, check_out
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                _required(row, "trip_id", source),
                _required(row, "hotel_id", source),
                _required(row, "trip_name", source),
                _iso_date(row, "check_in", source),
                _iso_date(row, "check_out", source),
            )
            for source, row in trips
        ],
    )
    connection.executemany(
        """
        INSERT INTO bookings(
            booking_id, user_id, trip_id, booked_on, status
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                _required(row, "booking_id", source),
                _required(row, "user_id", source),
                _required(row, "trip_id", source),
                _iso_date(row, "booked_on", source),
                _booking_status(row, source),
            )
            for source, row in bookings
        ],
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
    except InvalidOperation as error:
        raise ValueError(f"{source} has invalid {field} {value!r}") from error
    cents = amount * 100
    if amount < 0 or cents != cents.to_integral_value():
        raise ValueError(f"{source} has invalid {field} {value!r}")
    return int(cents)


def _booking_status(row: dict[str, str], source: str) -> str:
    status = _required(row, "status", source)
    if status not in {"confirmed", "cancelled"}:
        raise ValueError(f"{source} has invalid status {status!r}")
    return status


def main() -> None:
    seeded = initialize_database()
    action = "Seeded" if seeded else "Already initialized"
    print(f"{action}: {DEFAULT_DATABASE_PATH}")


if __name__ == "__main__":
    main()
