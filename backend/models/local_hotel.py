"""Immutable local place storage and simulated classroom night results."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.models.location import ZipLocation


def validate_provider_id(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Provider ID must be non-empty text")


@dataclass(frozen=True)
class SavedHotel:
    hotel_id: str
    name: str | None
    address: str | None
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        validate_provider_id(self.hotel_id)
        for value in (self.name, self.address):
            if value is not None and not isinstance(value, str):
                raise ValueError("Name and address must be text or null")
        for value, limit in ((self.latitude, 90), (self.longitude, 180)):
            if type(value) not in (int, float) or not -limit <= value <= limit:
                raise ValueError("Coordinates must be finite numbers within bounds")


@dataclass(frozen=True)
class HotelZipAssociation:
    hotel_id: str
    location: ZipLocation
    distance_m: int

    def __post_init__(self) -> None:
        validate_provider_id(self.hotel_id)
        if not isinstance(self.location, ZipLocation):
            raise ValueError("A validated ZIP location is required")
        if type(self.distance_m) is not int or not 0 <= self.distance_m <= 5000:
            raise ValueError("Distance must be an integer within the search radius")


@dataclass(frozen=True)
class DemoHotelNight:
    hotel_id: str
    stay_date: date
    nightly_rate_cents: int
    rooms_available: int

    def __post_init__(self) -> None:
        validate_provider_id(self.hotel_id)
        if type(self.stay_date) is not date:
            raise ValueError("Stay date must be a date")
        for value in (self.nightly_rate_cents, self.rooms_available):
            if type(value) is not int or value < 0:
                raise ValueError("Rate and available rooms must be nonnegative integers")

    @property
    def nightly_rate_usd(self) -> Decimal:
        return (Decimal(self.nightly_rate_cents) / 100).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class LocalHotelResult:
    hotel: SavedHotel
    association: HotelZipAssociation
    demo_nights: tuple[DemoHotelNight, ...]
