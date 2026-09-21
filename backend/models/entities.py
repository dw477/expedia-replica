"""Validated entity contracts derived from the four starter CSV files.

IDs remain text, dates are date objects, and dollar amounts use Decimal.
Relationships are references by ID, never nested mutable entity objects.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date
from decimal import Decimal
from typing import Literal

BookingStatus = Literal["confirmed", "cancelled"]


def _validate_text(entity: Hotel | User | Trip | Booking) -> None:
    for field in fields(entity):
        value = getattr(entity, field.name)
        if field.name not in {"nightly_rate_usd", "check_in", "check_out", "booked_on"}:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field.name} must be non-empty text")
            if value != value.strip():
                raise ValueError(f"{field.name} must not have surrounding whitespace")


def _validate_date(value: date, name: str) -> None:
    if type(value) is not date:
        raise ValueError(f"{name} must be a date")


def validate_nightly_rate(amount: Decimal) -> None:
    """Require exact whole cents within SQLite's signed-integer cent range."""
    if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
        raise ValueError("nightly_rate_usd must be a finite non-negative Decimal")
    # Check the bound before arithmetic so extreme Decimal exponents are rejected
    # without overflow; compare to quantized dollars before multiplying to avoid
    # accepting fractions of a cent rounded away by Decimal's precision context.
    if amount > Decimal("92233720368547758.07"):
        raise ValueError("nightly_rate_usd exceeds SQLite integer storage")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("nightly_rate_usd must have whole cents")


@dataclass(frozen=True)
class Hotel:
    hotel_id: str
    hotel_name: str
    city: str
    state: str
    nightly_rate_usd: Decimal

    def __post_init__(self) -> None:
        _validate_text(self)
        validate_nightly_rate(self.nightly_rate_usd)


@dataclass(frozen=True)
class User:
    user_id: str
    display_name: str

    def __post_init__(self) -> None:
        _validate_text(self)


@dataclass(frozen=True)
class Trip:
    trip_id: str
    hotel_id: str
    trip_name: str
    check_in: date
    check_out: date

    def __post_init__(self) -> None:
        _validate_text(self)
        _validate_date(self.check_in, "check_in")
        _validate_date(self.check_out, "check_out")
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")


@dataclass(frozen=True)
class Booking:
    booking_id: str
    user_id: str
    trip_id: str
    booked_on: date
    status: BookingStatus
    nightly_rate_usd: Decimal

    def __post_init__(self) -> None:
        _validate_text(self)
        _validate_date(self.booked_on, "booked_on")
        validate_nightly_rate(self.nightly_rate_usd)
        if self.status not in {"confirmed", "cancelled"}:
            raise ValueError("status must be confirmed or cancelled")
