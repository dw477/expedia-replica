"""SQLite representation of entity fields, relationships, and constraints."""

# backend/models/schema.py is the source of truth for the SQLite schema. Tables are deliberately
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
        status TEXT NOT NULL CHECK (status IN ('confirmed', 'cancelled')),
        nightly_rate_cents INTEGER NOT NULL CHECK (nightly_rate_cents >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        expires_at INTEGER NOT NULL CHECK (expires_at >= 0),
        credential_version TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at)",
    """
    CREATE TABLE IF NOT EXISTS search_history (
        search_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        search_query TEXT NOT NULL CHECK (length(trim(search_query)) > 0),
        searched_at INTEGER NOT NULL CHECK (searched_at >= 0)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_search_history_user_time_query
    ON search_history(user_id, searched_at, search_query)
    """,
    "CREATE INDEX IF NOT EXISTS idx_hotels_name ON hotels(hotel_name)",
    "CREATE INDEX IF NOT EXISTS idx_trips_hotel_id ON trips(hotel_id)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_user_id ON bookings(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_bookings_trip_id ON bookings(trip_id)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_unique_confirmed
    ON bookings(user_id, trip_id)
    WHERE status = 'confirmed'
    """,
)

# Used only when upgrading a database that predates stored booking rates.
BOOKING_RATE_MIGRATION = (
    "ALTER TABLE bookings ADD COLUMN nightly_rate_cents INTEGER NOT NULL "
    "DEFAULT 0 CHECK (nightly_rate_cents >= 0)"
)
