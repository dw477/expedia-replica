"""Immutable outputs shared by business controllers and interface adapters."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from backend.models.entities import BookingStatus


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


@dataclass(frozen=True)
class BookingHistoryEntry:
    booking_id: str
    user_id: str
    display_name: str
    trip_id: str
    trip_name: str
    hotel_name: str
    city: str
    state: str
    check_in: date
    check_out: date
    nightly_rate_usd: Decimal
    booked_on: date
    status: BookingStatus

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def stay_price_usd(self) -> Decimal:
        return self.nightly_rate_usd * self.nights
