"""Booking workflow using only typed database-controller operations."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Iterator, cast
from uuid import uuid4

from backend.controllers import pricing
from backend.controllers.database import (
    DEFAULT_DATABASE_PATH,
    DatabaseController,
    DatabaseError,
    RecordConflictError,
    RecordNotFoundError,
)
from backend.models import (
    Booking,
    BookingHistoryEntry,
    BookingStatus,
    Hotel,
    Trip,
    User,
)


class BookingDataError(RuntimeError):
    """Booking data cannot be read or persisted."""


class BookingNotFoundError(BookingDataError):
    """A requested booking, user, or trip does not exist."""


class BookingConflictError(BookingDataError):
    """The requested booking conflicts with an existing confirmed booking."""


@contextmanager
def _booking_errors() -> Iterator[None]:
    try:
        yield
    except RecordNotFoundError as error:
        raise BookingNotFoundError(str(error)) from error
    except RecordConflictError as error:
        raise BookingConflictError(
            "This traveler already has a confirmed booking for that stay."
        ) from error
    except DatabaseError as error:
        raise BookingDataError(str(error)) from error


def _history_entry(
    database: DatabaseController, booking: Booking
) -> BookingHistoryEntry:
    user = database.get(User, booking.user_id)
    trip = database.get(Trip, booking.trip_id)
    hotel = database.get(Hotel, trip.hotel_id)
    return BookingHistoryEntry(
        booking_id=booking.booking_id,
        user_id=user.user_id,
        display_name=user.display_name,
        trip_id=trip.trip_id,
        trip_name=trip.trip_name,
        hotel_name=hotel.hotel_name,
        city=hotel.city,
        state=hotel.state,
        check_in=trip.check_in,
        check_out=trip.check_out,
        nightly_rate_usd=booking.nightly_rate_usd,
        booked_on=booking.booked_on,
        status=booking.status,
    )


def list_users(database_path: str | Path = DEFAULT_DATABASE_PATH) -> list[User]:
    """Return demo travelers ordered by user ID."""
    with _booking_errors():
        return DatabaseController(database_path).list(User)


def list_booking_history(
    user_id: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
) -> list[BookingHistoryEntry]:
    """Return one existing traveler's history, newest date/ID first."""
    database = DatabaseController(database_path)
    with _booking_errors(), database.transaction(write=False):
        database.get(User, user_id)
        bookings = [item for item in database.list(Booking) if item.user_id == user_id]
        bookings.sort(key=lambda item: (item.booked_on, item.booking_id), reverse=True)
        return [_history_entry(database, booking) for booking in bookings]


def create_booking(
    user_id: str,
    trip_id: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    booked_on: date | None = None,
) -> BookingHistoryEntry:
    """Generate an ID and create a confirmed booking; SQLite enforces uniqueness."""
    database = DatabaseController(database_path)
    with _booking_errors(), database.transaction():
        trip = database.get(Trip, trip_id)
        hotel = database.get(Hotel, trip.hotel_id)
        queries = pricing.surged_queries(
            database, user_id, pricing.current_timestamp()
        )
        booking = Booking(
            f"B{uuid4().hex.upper()}",
            user_id,
            trip_id,
            booked_on or date.today(),
            "confirmed",
            pricing.nightly_rate(hotel, queries),
        )
        saved = database.create(booking)
        return _history_entry(database, saved)


def update_booking_status(
    booking_id: str,
    status: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    *,
    owner_user_id: str | None = None,
) -> BookingHistoryEntry:
    """Cancel or restore a booking without discarding history."""
    if status not in {"confirmed", "cancelled"}:
        raise ValueError(f"Unsupported booking status {status!r}")
    database = DatabaseController(database_path)
    with _booking_errors(), database.transaction():
        existing = database.get(Booking, booking_id)
        if owner_user_id is not None and existing.user_id != owner_user_id:
            raise BookingNotFoundError(f"Booking {booking_id!r} was not found.")
        saved = database.update(replace(existing, status=cast(BookingStatus, status)))
        return _history_entry(database, saved)


def delete_booking(
    booking_id: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    *,
    owner_user_id: str | None = None,
) -> None:
    """Permanently remove the booking; return None on success."""
    database = DatabaseController(database_path)
    with _booking_errors(), database.transaction():
        existing = database.get(Booking, booking_id)
        if owner_user_id is not None and existing.user_id != owner_user_id:
            raise BookingNotFoundError(f"Booking {booking_id!r} was not found.")
        database.delete(Booking, booking_id)
