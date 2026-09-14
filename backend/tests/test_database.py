import sqlite3

import pytest

from backend.database import connect_database, initialize_database


def test_initialization_seeds_every_csv_table(tmp_path):
    database_path = tmp_path / "expedia.sqlite3"

    assert initialize_database(database_path) is True

    connection = connect_database(database_path)
    try:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("hotels", "users", "trips", "bookings")
        }
        booking = connection.execute(
            """
            SELECT user_id, trip_id, booked_on, status
            FROM bookings
            WHERE booking_id = ?
            """,
            ("B001",),
        ).fetchone()
    finally:
        connection.close()

    assert counts == {"hotels": 8, "users": 6, "trips": 12, "bookings": 6}
    assert tuple(booking) == ("U001", "T001", "2026-09-01", "confirmed")


def test_reinitialization_preserves_database_changes(tmp_path):
    database_path = tmp_path / "expedia.sqlite3"
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        connection.execute(
            "UPDATE bookings SET status = 'cancelled' WHERE booking_id = 'B001'"
        )
        connection.execute("DELETE FROM bookings WHERE booking_id = 'B002'")
        connection.commit()
    finally:
        connection.close()

    assert initialize_database(database_path) is False

    connection = connect_database(database_path)
    try:
        status = connection.execute(
            "SELECT status FROM bookings WHERE booking_id = 'B001'"
        ).fetchone()[0]
        deleted_booking = connection.execute(
            "SELECT booking_id FROM bookings WHERE booking_id = 'B002'"
        ).fetchone()
        booking_count = connection.execute(
            "SELECT COUNT(*) FROM bookings"
        ).fetchone()[0]
    finally:
        connection.close()

    assert status == "cancelled"
    assert deleted_booking is None
    assert booking_count == 5


def test_connections_enforce_foreign_keys(tmp_path):
    database_path = tmp_path / "expedia.sqlite3"
    initialize_database(database_path)
    connection = connect_database(database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO bookings(
                    booking_id, user_id, trip_id, booked_on, status
                ) VALUES ('B999', 'missing', 'T001', '2026-09-14', 'confirmed')
                """
            )
    finally:
        connection.close()
