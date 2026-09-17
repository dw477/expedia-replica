"""Plain-text View for the optional Python search interface."""

import argparse
from decimal import Decimal
from typing import Iterable

from backend.controllers.search import search_available_stays
from backend.models import HotelAvailability


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
