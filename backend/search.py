"""Compatibility imports for search; CLI presentation lives in the View."""

from backend.controllers.search import SearchDataError, search_available_stays
from backend.models import HotelAvailability
from frontend.cli import format_availability_table, main

__all__ = [
    "SearchDataError",
    "HotelAvailability",
    "search_available_stays",
    "format_availability_table",
]


if __name__ == "__main__":
    main()
