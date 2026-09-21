"""Hotel-name matching through the database controller's entity contract."""

from pathlib import Path
from uuid import uuid4

from backend.controllers import pricing
from backend.controllers.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseController,
    DatabaseError,
)
from backend.models import Hotel, HotelAvailability, Trip
from backend.models.search import SearchHistory, normalize_query


class SearchDataError(ValueError):
    """Search data could not be read or validated."""


def search_available_stays(
    hotel_name: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
    *,
    user_id: str | None = None,
    record_search: bool = True,
) -> list[HotelAvailability]:
    """Return stays in trip-ID order with normalized matching and user pricing.

    Record non-empty submissions only when user_id is supplied. Read-only refreshes
    use record_search=False. Insert, daily count, and prices share one transaction,
    so the current submission participates in the fourth-search threshold.
    """
    normalized = normalize_query(hotel_name)
    if not normalized:
        return []
    database = DatabaseController(database_path)
    try:
        database.initialize(data_directory)
        with database.transaction(write=user_id is not None and record_search):
            now = pricing.current_timestamp()
            if user_id is not None and record_search:
                database.create(
                    SearchHistory(f"S{uuid4().hex}", user_id, normalized, now)
                )
            queries = pricing.surged_queries(database, user_id, now)
            hotels = {hotel.hotel_id: hotel for hotel in database.list(Hotel)}
            return [
                HotelAvailability(
                    trip_id=trip.trip_id,
                    trip_name=trip.trip_name,
                    hotel_name=hotels[trip.hotel_id].hotel_name,
                    city=hotels[trip.hotel_id].city,
                    state=hotels[trip.hotel_id].state,
                    check_in=trip.check_in,
                    check_out=trip.check_out,
                    nightly_rate_usd=pricing.nightly_rate(
                        hotels[trip.hotel_id], queries
                    ),
                )
                for trip in database.list(Trip)
                if normalized in normalize_query(hotels[trip.hotel_id].hotel_name)
            ]
    except (DatabaseError, KeyError) as error:
        raise SearchDataError(f"Could not search hotel stays: {error}") from error
