"""Compatibility entry point for database setup; use controllers for new code."""

from backend.controllers.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseError,
    connect_database,
    initialize_database,
)

__all__ = [
    "DEFAULT_DATA_DIRECTORY",
    "DEFAULT_DATABASE_PATH",
    "DatabaseError",
    "connect_database",
    "initialize_database",
]


def main() -> None:
    seeded = initialize_database()
    action = "Seeded" if seeded else "Already initialized"
    print(f"{action}: {DEFAULT_DATABASE_PATH}")


if __name__ == "__main__":
    main()
