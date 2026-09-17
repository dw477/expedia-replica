"""Hotel-name matching through the database controller's entity contract."""

from pathlib import Path

from backend.controllers.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseController,
    DatabaseError,
)
from backend.models import Hotel, HotelAvailability, Trip


class SearchDataError(ValueError):
    """Search data could not be read or validated."""


def search_available_stays(
    hotel_name: str,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
) -> list[HotelAvailability]:
    """Return stays in trip-ID order using a case-insensitive substring match.

    Blank input returns an empty list. This preserves the original search contract;
    cities and live availability are outside this controller's scope.
    """
    normalized = hotel_name.strip().casefold()
    if not normalized:
        return []
    database = DatabaseController(database_path)
    try:
        database.initialize(data_directory)
        with database.transaction(write=False):
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
                    nightly_rate_usd=hotels[trip.hotel_id].nightly_rate_usd,
                )
                for trip in database.list(Trip)
                if normalized in hotels[trip.hotel_id].hotel_name.casefold()
            ]
    except (DatabaseError, KeyError) as error:
        raise SearchDataError(f"Could not search hotel stays: {error}") from error
