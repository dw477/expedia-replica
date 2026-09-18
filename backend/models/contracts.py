"""Source of truth for the Controller–View JSON contract (also in OpenAPI)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from backend.models.entities import BookingStatus


class HotelAvailabilityResponse(BaseModel):
    """JSON representation of an existing hotel availability result."""

    trip_id: str
    trip_name: str
    hotel_name: str
    city: str
    state: str
    check_in: date
    check_out: date
    nights: int
    nightly_rate_usd: Decimal
    stay_price_usd: Decimal


class UserResponse(BaseModel):
    user_id: str
    display_name: str


class BookingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str | None = Field(default=None, min_length=1, max_length=64)
    trip_id: str = Field(min_length=1, max_length=64)


class BookingStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: BookingStatus


class BookingResponse(BaseModel):
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
    nights: int
    nightly_rate_usd: Decimal
    stay_price_usd: Decimal
    booked_on: date
    status: BookingStatus


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    # Passwords must not be stripped or case-folded.
    password: str = Field(min_length=1, max_length=256, repr=False)
