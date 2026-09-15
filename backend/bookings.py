"""Framework-free booking operations backed by SQLite."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from backend.database import DEFAULT_DATABASE_PATH, DatabaseError, connect_database


class BookingDataError(RuntimeError):
    """Raised when booking data cannot be read or persisted."""


class BookingNotFoundError(BookingDataError):
    """Raised when a requested booking, user, or trip does not exist."""


class BookingConflictError(BookingDataError):
    """Raised when a requested booking would duplicate an active booking."""


@dataclass(frozen=True)
class UserSummary:
    user_id: str
    display_name: str


@dataclass(frozen=True)
class BookingHistoryEntry:
    booking_id: str
    user_id: str
    display_name: str
    trip_id: str
    trip_name: str
    hotel_name: str
    city: str
    state: str
    check_in: date
    check_out: date
    nightly_rate_usd: Decimal
    booked_on: date
    status: str

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def stay_price_usd(self) -> Decimal:
        return self.nightly_rate_usd * self.nights


BOOKING_DETAILS_QUERY = """
    SELECT
        b.booking_id,
        b.user_id,
        u.display_name,
        b.trip_id,
        t.trip_name,
        h.hotel_name,
        h.city,
        h.state,
        t.check_in,
        t.check_out,
        h.nightly_rate_cents,
        b.booked_on,
        b.status
    FROM bookings AS b
    JOIN users AS u ON u.user_id = b.user_id
    JOIN trips AS t ON t.trip_id = b.trip_id
    JOIN hotels AS h ON h.hotel_id = t.hotel_id
"""


def list_users(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[UserSummary]:
    """Return the demo travelers available for booking and history views."""

    connection = _connect(database_path)
    try:
        rows = connection.execute(
            "SELECT user_id, display_name FROM users ORDER BY user_id"
        ).fetchall()
        return [UserSummary(row["user_id"], row["display_name"]) for row in rows]
    except sqlite3.Error as error:
        raise BookingDataError(f"Could not load travelers: {error}") from error
    finally:
        connection.close()


def list_booking_history(
    user_id: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[BookingHistoryEntry]:
    """Return one traveler's bookings, newest first."""

    connection = _connect(database_path)
    try:
        _require_record(connection, "users", "user_id", user_id, "Traveler")
        rows = connection.execute(
            f"{BOOKING_DETAILS_QUERY} WHERE b.user_id = ? "
            "ORDER BY b.booked_on DESC, b.booking_id DESC",
            (user_id,),
        ).fetchall()
        return [_booking_from_row(row) for row in rows]
    except sqlite3.Error as error:
        raise BookingDataError(f"Could not load booking history: {error}") from error
    finally:
        connection.close()


def create_booking(
    user_id: str,
    trip_id: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    booked_on: date | None = None,
) -> BookingHistoryEntry:
    """Create a confirmed booking and return its joined history representation."""

    connection = _connect(database_path)
    try:
        with connection:
            _require_record(connection, "users", "user_id", user_id, "Traveler")
            _require_record(connection, "trips", "trip_id", trip_id, "Trip")
            duplicate = connection.execute(
                """
                SELECT booking_id
                FROM bookings
                WHERE user_id = ? AND trip_id = ? AND status = 'confirmed'
                """,
                (user_id, trip_id),
            ).fetchone()
            if duplicate is not None:
                raise BookingConflictError(
                    "This traveler already has a confirmed booking for that stay."
                )

            booking_id = f"B{uuid4().hex[:12].upper()}"
            connection.execute(
                """
                INSERT INTO bookings(booking_id, user_id, trip_id, booked_on, status)
                VALUES (?, ?, ?, ?, 'confirmed')
                """,
                (booking_id, user_id, trip_id, (booked_on or date.today()).isoformat()),
            )
            row = connection.execute(
                f"{BOOKING_DETAILS_QUERY} WHERE b.booking_id = ?", (booking_id,)
            ).fetchone()
        return _booking_from_row(row)
    except (BookingConflictError, BookingNotFoundError):
        raise
    except sqlite3.Error as error:
        raise BookingDataError(f"Could not create booking: {error}") from error
    finally:
        connection.close()


def update_booking_status(
    booking_id: str,
    status: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> BookingHistoryEntry:
    """Update a booking's status and return the updated booking."""

    if status not in {"confirmed", "cancelled"}:
        raise ValueError(f"Unsupported booking status {status!r}")

    connection = _connect(database_path)
    try:
        with connection:
            existing = connection.execute(
                "SELECT user_id, trip_id FROM bookings WHERE booking_id = ?",
                (booking_id,),
            ).fetchone()
            if existing is None:
                raise BookingNotFoundError(f"Booking {booking_id!r} was not found.")
            if status == "confirmed":
                duplicate = connection.execute(
                    """
                    SELECT booking_id
                    FROM bookings
                    WHERE user_id = ?
                      AND trip_id = ?
                      AND status = 'confirmed'
                      AND booking_id != ?
                    """,
                    (existing["user_id"], existing["trip_id"], booking_id),
                ).fetchone()
                if duplicate is not None:
                    raise BookingConflictError(
                        "This traveler already has a confirmed booking for that stay."
                    )
            result = connection.execute(
                "UPDATE bookings SET status = ? WHERE booking_id = ?",
                (status, booking_id),
            )
            row = connection.execute(
                f"{BOOKING_DETAILS_QUERY} WHERE b.booking_id = ?", (booking_id,)
            ).fetchone()
        return _booking_from_row(row)
    except (BookingConflictError, BookingNotFoundError):
        raise
    except sqlite3.Error as error:
        raise BookingDataError(f"Could not update booking: {error}") from error
    finally:
        connection.close()


def delete_booking(
    booking_id: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> None:
    """Permanently remove a booking."""

    connection = _connect(database_path)
    try:
        with connection:
            result = connection.execute(
                "DELETE FROM bookings WHERE booking_id = ?", (booking_id,)
            )
            if result.rowcount == 0:
                raise BookingNotFoundError(f"Booking {booking_id!r} was not found.")
    except BookingNotFoundError:
        raise
    except sqlite3.Error as error:
        raise BookingDataError(f"Could not delete booking: {error}") from error
    finally:
        connection.close()


def _connect(database_path: str | Path) -> sqlite3.Connection:
    try:
        return connect_database(database_path)
    except DatabaseError as error:
        raise BookingDataError(str(error)) from error


def _require_record(
    connection: sqlite3.Connection,
    table: str,
    id_column: str,
    record_id: str,
    label: str,
) -> None:
    # Table and column names are internal constants; values remain parameterized.
    row = connection.execute(
        f"SELECT 1 FROM {table} WHERE {id_column} = ?", (record_id,)
    ).fetchone()
    if row is None:
        raise BookingNotFoundError(f"{label} {record_id!r} was not found.")


def _booking_from_row(row: sqlite3.Row | None) -> BookingHistoryEntry:
    if row is None:
        raise BookingDataError("The saved booking could not be reloaded.")
    try:
        return BookingHistoryEntry(
            booking_id=row["booking_id"],
            user_id=row["user_id"],
            display_name=row["display_name"],
            trip_id=row["trip_id"],
            trip_name=row["trip_name"],
            hotel_name=row["hotel_name"],
            city=row["city"],
            state=row["state"],
            check_in=date.fromisoformat(row["check_in"]),
            check_out=date.fromisoformat(row["check_out"]),
            nightly_rate_usd=Decimal(row["nightly_rate_cents"]) / 100,
            booked_on=date.fromisoformat(row["booked_on"]),
            status=row["status"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BookingDataError("A booking contains invalid stored data.") from error
