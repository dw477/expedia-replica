"""Compatibility imports; new code uses backend.controllers.bookings."""

from backend.controllers.bookings import (
    BookingConflictError,
    BookingDataError,
    BookingNotFoundError,
    create_booking,
    delete_booking,
    list_booking_history,
    list_users,
    update_booking_status,
)
from backend.models import BookingHistoryEntry
from backend.models import User as UserSummary

__all__ = [
    "BookingConflictError",
    "BookingDataError",
    "BookingNotFoundError",
    "BookingHistoryEntry",
    "UserSummary",
    "create_booking",
    "delete_booking",
    "list_booking_history",
    "list_users",
    "update_booking_status",
]
