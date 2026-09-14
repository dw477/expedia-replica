"""Search SQLite-backed hotel and trip data without a web framework."""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from backend.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseError,
    connect_database,
    initialize_database,
)



class SearchDataError(ValueError):
    """Raised when the supplied CSV data cannot produce valid search results."""


@dataclass(frozen=True)
class HotelAvailability:
    """A hotel stay offered for a fixed check-in and check-out date."""

    trip_id: str
    trip_name: str
    hotel_name: str
    city: str
    state: str
    check_in: date
    check_out: date
    nightly_rate_usd: Decimal

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def stay_price_usd(self) -> Decimal:
        return self.nightly_rate_usd * self.nights


def search_available_stays(
    hotel_name: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
) -> list[HotelAvailability]:
    """Return fixed-date stays whose hotel name contains the query.

    Matching ignores surrounding whitespace and capitalization. Results retain the
    starter ordering so the supplied data determines presentation.
    """

    normalized_hotel_name = hotel_name.strip().casefold()
    if not normalized_hotel_name:
        return []

    try:
        initialize_database(database_path, data_directory)
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                """
                SELECT
                    t.trip_id,
                    t.trip_name,
                    h.hotel_name,
                    h.city,
                    h.state,
                    t.check_in,
                    t.check_out,
                    h.nightly_rate_cents
                FROM trips AS t
                JOIN hotels AS h ON h.hotel_id = t.hotel_id
                ORDER BY t.trip_id
                """
            ).fetchall()
        finally:
            connection.close()
    except (DatabaseError, sqlite3.Error) as error:
        raise SearchDataError(f"Could not search hotel stays: {error}") from error

    results = []
    for row in rows:
        if normalized_hotel_name not in row["hotel_name"].casefold():
            continue
        try:
            check_in = date.fromisoformat(row["check_in"])
            check_out = date.fromisoformat(row["check_out"])
        except (TypeError, ValueError) as error:
            raise SearchDataError(
                f"Trip {row['trip_id']!r} contains an invalid date"
            ) from error

        results.append(
            HotelAvailability(
                trip_id=row["trip_id"],
                trip_name=row["trip_name"],
                hotel_name=row["hotel_name"],
                city=row["city"],
                state=row["state"],
                check_in=check_in,
                check_out=check_out,
                nightly_rate_usd=Decimal(row["nightly_rate_cents"]) / 100,
            )
        )

    return results


def format_availability_table(
    hotel_name: str, stays: Iterable[HotelAvailability]
) -> str:
    """Format matching stays as a readable plain-text table."""

    rows = list(stays)
    display_hotel_name = hotel_name.strip()
    if not rows:
        if not display_hotel_name:
            return "No hotel name was provided. Enter a hotel name to search for stays."
        return f"No available hotel stays found for {display_hotel_name}."

    headers = (
        "Hotel",
        "Trip",
        "Check-in",
        "Check-out",
        "Nights",
        "Nightly rate",
        "Stay price",
    )
    table_rows = [
        (
            stay.hotel_name,
            stay.trip_name,
            stay.check_in.isoformat(),
            stay.check_out.isoformat(),
            str(stay.nights),
            _format_usd(stay.nightly_rate_usd),
            _format_usd(stay.stay_price_usd),
        )
        for stay in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in table_rows))
        for index in range(len(headers))
    ]

    def render_row(values: tuple[str, ...]) -> str:
        return " | ".join(
            value.ljust(widths[index]) for index, value in enumerate(values)
        )

    separator = "-+-".join("-" * width for width in widths)
    title = f"Available hotel stays matching {display_hotel_name}"
    rendered_rows = [render_row(row) for row in table_rows]
    return "\n".join([title, render_row(headers), separator, *rendered_rows])


def _format_usd(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search available stays by hotel name."
    )
    parser.add_argument(
        "hotel_name", help="Hotel name to search, for example: Harbor Lantern"
    )
    arguments = parser.parse_args()
    stays = search_available_stays(arguments.hotel_name)
    print(format_availability_table(arguments.hotel_name, stays))


if __name__ == "__main__":
    main()
