from datetime import date

import pytest

from backend.bookings import (
    BookingConflictError,
    BookingNotFoundError,
    create_booking,
    delete_booking,
    list_booking_history,
    list_users,
    update_booking_status,
)
from backend.database import initialize_database


@pytest.fixture
def database_path(tmp_path):
    path = tmp_path / "expedia.sqlite3"
    initialize_database(path)
    return path


def test_lists_seeded_users_and_booking_history(database_path):
    users = list_users(database_path)
    bookings = list_booking_history("U001", database_path)

    assert [user.user_id for user in users] == [
        "U001",
        "U002",
        "U003",
        "U004",
        "U005",
        "U006",
    ]
    assert [booking.booking_id for booking in bookings] == ["B002", "B001"]
    assert bookings[0].stay_price_usd == 220


def test_create_update_and_delete_booking(database_path):
    booking = create_booking(
        "U006", "T001", database_path, booked_on=date(2026, 9, 14)
    )

    assert booking.user_id == "U006"
    assert booking.trip_id == "T001"
    assert booking.status == "confirmed"
    assert booking.booked_on == date(2026, 9, 14)
    assert [item.booking_id for item in list_booking_history("U006", database_path)] == [
        booking.booking_id
    ]

    cancelled = update_booking_status(booking.booking_id, "cancelled", database_path)
    assert cancelled.status == "cancelled"

    delete_booking(booking.booking_id, database_path)
    assert list_booking_history("U006", database_path) == []


def test_rejects_duplicate_confirmed_booking(database_path):
    with pytest.raises(BookingConflictError):
        create_booking("U001", "T001", database_path)


def test_rejects_restoring_a_duplicate_confirmed_booking(database_path):
    new_booking = create_booking("U001", "T005", database_path)

    with pytest.raises(BookingConflictError):
        update_booking_status("B002", "confirmed", database_path)

    assert new_booking.status == "confirmed"


def test_reports_missing_records(database_path):
    with pytest.raises(BookingNotFoundError):
        list_booking_history("missing", database_path)
    with pytest.raises(BookingNotFoundError):
        create_booking("U006", "missing", database_path)
    with pytest.raises(BookingNotFoundError):
        update_booking_status("missing", "cancelled", database_path)
    with pytest.raises(BookingNotFoundError):
        delete_booking("missing", database_path)
