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


def test_demo_schema_upgrade_is_additive_and_repeatable(tmp_path):
    path = tmp_path / 'existing.sqlite3'
    initialize_database(path)
    with connect_database(path) as connection:
        connection.execute('DROP TABLE demo_hotel_nights')
        connection.execute('DROP TABLE saved_hotels')
        connection.execute("UPDATE app_metadata SET value = '3' WHERE key = 'schema_version'")
        before = {
            table: [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1')]
            for table in ('hotels', 'users', 'trips', 'bookings')
        }
    assert initialize_database(path) is False
    with connect_database(path) as connection:
        for table, rows in before.items():
            assert [tuple(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY 1')] == rows
        connection.execute(
            'INSERT INTO saved_hotels VALUES (?, NULL, NULL, ?, ?)',
            (' Provider-ID:001 ', 90, -180),
        )
        connection.execute(
            'INSERT INTO demo_hotel_nights(hotel_id, stay_date) VALUES (?, ?)',
            (' Provider-ID:001 ', '2028-02-29'),
        )
    assert initialize_database(path) is False
    with connect_database(path) as connection:
        assert tuple(connection.execute('SELECT * FROM saved_hotels').fetchone()) == (
            ' Provider-ID:001 ', None, None, 90, -180,
        )
        assert tuple(connection.execute('SELECT * FROM demo_hotel_nights').fetchone()) == (
            ' Provider-ID:001 ', '2028-02-29', 10000, 20,
        )


@pytest.mark.parametrize('latitude,longitude', [
    (None, 0), (0, None), (91, 0), (0, -181), ('invalid', 0),
    (float('inf'), 0), (float('nan'), 0),
])
def test_saved_hotels_reject_invalid_coordinates(tmp_path, latitude, longitude):
    path = tmp_path / 'fresh.sqlite3'
    initialize_database(path)
    with connect_database(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('INSERT INTO saved_hotels VALUES (?, NULL, NULL, ?, ?)',
                               ('id', latitude, longitude))


@pytest.mark.parametrize('stay_date,rate,rooms', [
    ('2026-02-29', 10000, 20), ('2026-04-31', 10000, 20),
    ('2026-1-01', 10000, 20), ('invalid', 10000, 20),
    (None, 10000, 20), ('2026-10-01', -1, 20),
    ('2026-10-01', 10000, -1), ('2026-10-01', 1.5, 20),
    ('2026-10-01', 10000, 1.5), ('2026-10-01', None, 20),
])
def test_demo_nights_reject_invalid_fields(tmp_path, stay_date, rate, rooms):
    path = tmp_path / 'fresh.sqlite3'
    initialize_database(path)
    with connect_database(path) as connection:
        connection.execute("INSERT INTO saved_hotels VALUES ('id', NULL, NULL, 0, 0)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('INSERT INTO demo_hotel_nights VALUES (?, ?, ?, ?)',
                               ('id', stay_date, rate, rooms))


def test_demo_schema_keys_and_foreign_keys(tmp_path):
    path = tmp_path / 'fresh.sqlite3'
    initialize_database(path)
    with connect_database(path) as connection:
        connection.execute("INSERT INTO saved_hotels VALUES ('id', NULL, NULL, 0, 0)")
        connection.execute("INSERT INTO demo_hotel_nights VALUES ('id', '2026-10-01', 0, 0)")
        for statement in (
            "INSERT INTO saved_hotels VALUES ('id', 'Duplicate', NULL, 0, 0)",
            "INSERT INTO demo_hotel_nights(hotel_id, stay_date) VALUES ('id', '2026-10-01')",
            "INSERT INTO demo_hotel_nights(hotel_id, stay_date) VALUES ('missing', '2026-10-02')",
            "DELETE FROM saved_hotels WHERE hotel_id = 'id'",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
        connection.execute("INSERT INTO demo_hotel_nights(hotel_id, stay_date) VALUES ('id', '2026-10-02')")
