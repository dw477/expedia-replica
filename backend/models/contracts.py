"""Source of truth for the Controller–View JSON contract (also in OpenAPI)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, UUID4, field_validator

from backend.models.authentication import (
    USERNAME_PATTERN,
    validate_registration_password,
)
from backend.models.entities import BookingStatus
from backend.models.chat import (
    MAX_CHAT_MESSAGES,
    MAX_CHAT_MESSAGE_LENGTH,
    MAX_CHAT_SUGGESTIONS,
    MAX_CHAT_SUGGESTION_LENGTH,
    ChatConversation,
    ChatMessage,
    ChatReply,
    ChatRole,
)


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: ChatRole
    content: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value: str) -> str:
        return ChatMessage("user", value).content


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessageRequest] = Field(min_length=1, max_length=MAX_CHAT_MESSAGES)
    conversation_id: UUID4 | None = Field(
        default=None,
        description="Page-memory UUID for grouping durable messages and workflow records; not an access token.",
    )

    @field_validator("messages")
    @classmethod
    def valid_conversation(cls, value: list[ChatMessageRequest]) -> list[ChatMessageRequest]:
        ChatConversation(
            tuple(ChatMessage(message.role, message.content) for message in value)
        )
        return value


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    reply: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE_LENGTH)
    suggestions: list[Annotated[str, Field(min_length=1, max_length=MAX_CHAT_SUGGESTION_LENGTH)]] = Field(
        max_length=MAX_CHAT_SUGGESTIONS,
        description="Distinct follow-up questions based on the latest user question and this reply.",
    )

    @field_validator("reply")
    @classmethod
    def valid_reply(cls, value: str) -> str:
        return ChatMessage("assistant", value).content

    @field_validator("suggestions")
    @classmethod
    def valid_suggestions(cls, value: list[str]) -> list[str]:
        return list(ChatReply("Validated reply", tuple(value)).suggestions)


class ChatErrorResponse(BaseModel):
    detail: str = Field(
        description="Fixed safe error message; provider outages and timeouts have distinct explanations.",
        examples=[
            "Gemini is temporarily unavailable. Please try again in a moment.",
            "Gemini took too long to reply. Please try again.",
            "The travel assistant could not reply. Please try again.",
        ],
    )


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


class NearbyHotelResponse(BaseModel):
    """A live hotel place near a ZIP point, without booking or price data."""

    model_config = ConfigDict(from_attributes=True)

    place_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    address: str | None
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    distance_m: int = Field(ge=0, le=5000)


class LocalHotelFields(BaseModel):
    """Provider identity is never trimmed, case-folded, or converted to an A1 ID."""

    model_config = ConfigDict(extra="forbid")

    place_id: str = Field(min_length=1)
    name: str | None = None
    address: str | None = None
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    distance_m: int = Field(ge=0, le=5000, strict=True)

    @field_validator("place_id")
    @classmethod
    def nonblank_provider_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Provider ID must be non-empty text")
        return value


class LocalZipContextRequest(ZipLocationResponse):
    model_config = ConfigDict(extra="forbid")

    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)


class LocalHotelSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hotel: LocalHotelFields
    location: LocalZipContextRequest


class LocalHotelDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: str = Field(min_length=1)

    @field_validator("place_id")
    @classmethod
    def nonblank_provider_id(cls, value: str) -> str:
        return LocalHotelFields.nonblank_provider_id(value)


class DemoHotelNightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stay_date: date
    nightly_rate_usd: Decimal
    rooms_available: int = Field(ge=0)


class LocalHotelResponse(LocalHotelFields):
    """Stored search context and fictional nights, separate from the frozen API."""

    location: ZipLocationResponse
    demo_nights: list[DemoHotelNightResponse]


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
