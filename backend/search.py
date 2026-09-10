"""Search the supplied hotel and trip data without a web framework."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


DEFAULT_DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"


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
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
) -> list[HotelAvailability]:
    """Return fixed-date stays whose hotel name contains the query.

    Matching ignores surrounding whitespace and capitalization. Results retain the
    ordering of ``trips.csv`` so the supplied data determines presentation.
    """

    normalized_hotel_name = hotel_name.strip().casefold()
    if not normalized_hotel_name:
        return []

    data_path = Path(data_directory)
    hotels = _load_hotels(data_path / "hotels.csv")
    results: list[HotelAvailability] = []

    for row_number, trip in _read_csv(data_path / "trips.csv"):
        hotel_id = _required_value(trip, "hotel_id", row_number, "trips.csv")
        hotel = hotels.get(hotel_id)
        if hotel is None:
            raise SearchDataError(
                f"trips.csv row {row_number} references unknown hotel_id {hotel_id!r}"
            )

        matched_hotel_name = _required_value(
            hotel, "hotel_name", row_number, "hotels.csv"
        )
        if normalized_hotel_name not in matched_hotel_name.casefold():
            continue

        hotel_city = _required_value(hotel, "city", row_number, "hotels.csv")
        check_in = _parse_date(trip, "check_in", row_number, "trips.csv")
        check_out = _parse_date(trip, "check_out", row_number, "trips.csv")
        if check_out <= check_in:
            raise SearchDataError(
                f"trips.csv row {row_number} must have check_out after check_in"
            )

        results.append(
            HotelAvailability(
                trip_id=_required_value(trip, "trip_id", row_number, "trips.csv"),
                trip_name=_required_value(trip, "trip_name", row_number, "trips.csv"),
                hotel_name=matched_hotel_name,
                city=hotel_city,
                state=_required_value(hotel, "state", row_number, "hotels.csv"),
                check_in=check_in,
                check_out=check_out,
                nightly_rate_usd=_parse_money(
                    hotel, "nightly_rate_usd", row_number, "hotels.csv"
                ),
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
    return "\n".join(
        [title, render_row(headers), separator, *(render_row(row) for row in table_rows)]
    )


def _load_hotels(path: Path) -> dict[str, dict[str, str]]:
    hotels: dict[str, dict[str, str]] = {}
    for row_number, hotel in _read_csv(path):
        hotel_id = _required_value(hotel, "hotel_id", row_number, "hotels.csv")
        if hotel_id in hotels:
            raise SearchDataError(f"hotels.csv contains duplicate hotel_id {hotel_id!r}")
        hotels[hotel_id] = hotel
    return hotels


def _read_csv(path: Path) -> list[tuple[int, dict[str, str]]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise SearchDataError(f"{path.name} is missing its header row")
            return [(row_number, row) for row_number, row in enumerate(reader, start=2)]
    except OSError as error:
        raise SearchDataError(f"Could not read {path}: {error}") from error


def _required_value(
    row: dict[str, str], field: str, row_number: int, filename: str
) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise SearchDataError(f"{filename} row {row_number} is missing {field}")
    return value


def _parse_date(
    row: dict[str, str], field: str, row_number: int, filename: str
) -> date:
    value = _required_value(row, field, row_number, filename)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise SearchDataError(
            f"{filename} row {row_number} has invalid {field} {value!r}"
        ) from error


def _parse_money(
    row: dict[str, str], field: str, row_number: int, filename: str
) -> Decimal:
    value = _required_value(row, field, row_number, filename)
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise SearchDataError(
            f"{filename} row {row_number} has invalid {field} {value!r}"
        ) from error
    if amount < 0:
        raise SearchDataError(f"{filename} row {row_number} has negative {field}")
    return amount


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
