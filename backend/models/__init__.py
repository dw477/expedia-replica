"""Models have no dependency on controllers or the View."""

from backend.models.authentication import AuthSession, UserAccount
from backend.models.entities import Booking, BookingStatus, Hotel, Trip, User
from backend.models.nearby_hotel import NearbyHotel
from backend.models.results import BookingHistoryEntry, HotelAvailability

__all__ = [
    "AuthSession",
    "UserAccount",
    "Booking",
    "BookingStatus",
    "Hotel",
    "Trip",
    "User",
    "BookingHistoryEntry",
    "HotelAvailability",
    "NearbyHotel",
]
