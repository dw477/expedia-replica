"""Models have no dependency on controllers or the View."""

from backend.models.entities import Booking, BookingStatus, Hotel, Trip, User
from backend.models.results import BookingHistoryEntry, HotelAvailability

__all__ = [
    "Booking",
    "BookingStatus",
    "Hotel",
    "Trip",
    "User",
    "BookingHistoryEntry",
    "HotelAvailability",
]
