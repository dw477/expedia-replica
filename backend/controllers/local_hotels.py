"""Local place workflows; provider searches remain independent and read-only."""

from datetime import date
from pathlib import Path

from backend.controllers.database import DEFAULT_DATABASE_PATH, DatabaseController
from backend.models.local_hotel import (
    HotelZipAssociation,
    LocalHotelResult,
    SavedHotel,
    validate_provider_id,
)
from backend.models.location import validate_postcode

# Five fictional classroom nights, inclusive of October 14. Never provider data.
DEMO_STAY_DATES = tuple(date(2026, 10, day) for day in range(10, 15))


class LocalHotelsController:
    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        self.database = DatabaseController(database_path)

    def save(self, hotel: SavedHotel, association: HotelZipAssociation) -> LocalHotelResult:
        if hotel.hotel_id != association.hotel_id:
            raise ValueError("Hotel and ZIP association must have the same provider ID")
        with self.database.transaction():
            self.database.save_local_hotel(hotel, association, DEMO_STAY_DATES)
            return next(
                item for item in self.database.list_local_hotels(association.location.postcode)
                if item.hotel.hotel_id == hotel.hotel_id
            )

    def list_for_zip(self, postcode: str) -> list[LocalHotelResult]:
        validate_postcode(postcode)
        with self.database.transaction(write=False):
            return self.database.list_local_hotels(postcode)

    def list_ids(self) -> list[str]:
        return self.database.list_saved_hotel_ids()

    def remove(self, hotel_id: str) -> None:
        validate_provider_id(hotel_id)
        with self.database.transaction():
            self.database.remove_local_hotel(hotel_id)
