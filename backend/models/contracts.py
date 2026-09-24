"""Source of truth for the Controller–View JSON contract (also in OpenAPI)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.authentication import (
    USERNAME_PATTERN,
    validate_registration_password,
)
from backend.models.entities import BookingStatus


class HealthResponse(BaseModel):
    status: Literal["ok"]
    geoapify: Literal["key is configured", "key is not configured"]


ZipPostcode = Annotated[str, Field(min_length=5, max_length=5, pattern=r"^[0-9]{5}$")]


class ZipLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    postcode: ZipPostcode
    country_code: Literal["us"]
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    locality: str | None = None


class ZipLookupErrorResponse(BaseModel):
    detail: str


class HotelAvailabilityResponse(BaseModel):
    """Availability with this user's applicable nightly rate and derived total."""

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


class SearchRequest(BaseModel):
    """A submitted search; identity always comes from the session cookie."""

    model_config = ConfigDict(extra="forbid")

    hotel_name: str


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


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64, pattern=f"^{USERNAME_PATTERN}$")
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=256, repr=False)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("display_name", mode="before")
    @classmethod
    def trim_display_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_registration_password(value)
