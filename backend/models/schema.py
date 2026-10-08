"""SQLite representation of entity fields, relationships, and constraints."""

# backend/models/schema.py is the source of truth for the SQLite schema. Tables are deliberately
# created without destructive migrations so an existing development database keeps
# application changes made after the starter CSVs are imported.
SCHEMA_STATEMENTS = (
    # Provider place_id is stored verbatim as hotel_id; these are separate from
    # Assignment 1 hotels. Rates and inventory below are classroom demo data.
    """
    CREATE TABLE IF NOT EXISTS saved_hotels (
        hotel_id TEXT NOT NULL PRIMARY KEY,
        name TEXT,
        address TEXT,
        latitude REAL NOT NULL CHECK (
            typeof(latitude) IN ('integer', 'real') AND latitude BETWEEN -90 AND 90
        ),
        longitude REAL NOT NULL CHECK (
            typeof(longitude) IN ('integer', 'real') AND longitude BETWEEN -180 AND 180
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS demo_hotel_nights (
        hotel_id TEXT NOT NULL REFERENCES saved_hotels(hotel_id) ON DELETE RESTRICT,
        stay_date TEXT NOT NULL CHECK (
            stay_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND date(stay_date, '+0 days') IS NOT NULL
            AND date(stay_date, '+0 days') = stay_date
        ),
        nightly_rate_cents INTEGER NOT NULL DEFAULT 10000 CHECK (
            typeof(nightly_rate_cents) = 'integer' AND nightly_rate_cents >= 0
        ),
        rooms_available INTEGER NOT NULL DEFAULT 20 CHECK (
            typeof(rooms_available) = 'integer' AND rooms_available >= 0
        ),
        PRIMARY KEY (hotel_id, stay_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS saved_hotel_zip_locations (
        hotel_id TEXT NOT NULL REFERENCES saved_hotels(hotel_id) ON DELETE RESTRICT,
        postcode TEXT NOT NULL CHECK (
            postcode GLOB '[0-9][0-9][0-9][0-9][0-9]'
        ),
        country_code TEXT NOT NULL CHECK (country_code = 'us'),
        latitude REAL NOT NULL CHECK (
            typeof(latitude) IN ('integer', 'real') AND latitude BETWEEN -90 AND 90
        ),
        longitude REAL NOT NULL CHECK (
            typeof(longitude) IN ('integer', 'real') AND longitude BETWEEN -180 AND 180
        ),
        locality TEXT,
        distance_m INTEGER NOT NULL CHECK (
            typeof(distance_m) = 'integer' AND distance_m BETWEEN 0 AND 5000
        ),
        PRIMARY KEY (hotel_id, postcode)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_saved_hotel_zip ON saved_hotel_zip_locations(postcode)",
    """
    CREATE TABLE IF NOT EXISTS conversation_history (
        message_id TEXT NOT NULL PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        timestamp INTEGER NOT NULL CHECK (typeof(timestamp) = 'integer' AND timestamp >= 0),
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
        content TEXT NOT NULL CHECK (length(trim(content)) > 0 AND length(content) <= 16000),
        record_type TEXT NOT NULL CHECK (
            record_type IN ('message', 'generated_sql', 'executed_sql', 'result_summary', 'error')
            AND ((record_type = 'message' AND role IN ('user', 'assistant'))
                OR (record_type != 'message' AND role = 'system'))
        )
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_conversation_history_id ON conversation_history(conversation_id)",
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
