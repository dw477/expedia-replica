"""FastAPI boundary for SQLite-backed hotel availability search."""

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from backend.bookings import (
    BookingConflictError,
    BookingDataError,
    BookingHistoryEntry,
    BookingNotFoundError,
    create_booking,
    delete_booking,
    list_booking_history,
    list_users,
    update_booking_status,
)
from backend.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseError,
    initialize_database,
)
from backend.search import SearchDataError, search_available_stays


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
    user_id: str = Field(min_length=1, max_length=64)
    trip_id: str = Field(min_length=1, max_length=64)


class BookingStatusRequest(BaseModel):
    status: Literal["confirmed", "cancelled"]


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
    status: Literal["confirmed", "cancelled"]


def create_app(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
) -> FastAPI:
    """Create an API configured for a specific database and seed directory."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            initialize_database(database_path, data_directory)
        except DatabaseError as error:
            raise RuntimeError(f"Database startup failed: {error}") from error
        yield

    application = FastAPI(title="Expedia Assignment API", lifespan=lifespan)

    @application.get("/api/stays", response_model=list[HotelAvailabilityResponse])
    def get_available_stays(
        hotel_name: str = Query(min_length=1, description="Hotel name to search"),
    ) -> list[HotelAvailabilityResponse]:
        """Expose the framework-free availability search as JSON."""

        try:
            stays = search_available_stays(
                hotel_name,
                database_path=database_path,
                data_directory=data_directory,
            )
        except SearchDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

        return [
            HotelAvailabilityResponse(
                trip_id=stay.trip_id,
                trip_name=stay.trip_name,
                hotel_name=stay.hotel_name,
                city=stay.city,
                state=stay.state,
                check_in=stay.check_in,
                check_out=stay.check_out,
                nights=stay.nights,
                nightly_rate_usd=stay.nightly_rate_usd,
                stay_price_usd=stay.stay_price_usd,
            )
            for stay in stays
        ]

    @application.get("/api/users", response_model=list[UserResponse])
    def get_users() -> list[UserResponse]:
        try:
            users = list_users(database_path)
        except BookingDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return [
            UserResponse(user_id=user.user_id, display_name=user.display_name)
            for user in users
        ]

    @application.get("/api/bookings", response_model=list[BookingResponse])
    def get_booking_history(
        user_id: str = Query(
            min_length=1, description="Traveler whose history to load"
        ),
    ) -> list[BookingResponse]:
        try:
            bookings = list_booking_history(user_id, database_path)
        except BookingNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except BookingDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return [_booking_response(booking) for booking in bookings]

    @application.post(
        "/api/bookings",
        response_model=BookingResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def post_booking(request: BookingCreateRequest) -> BookingResponse:
        try:
            booking = create_booking(request.user_id, request.trip_id, database_path)
        except BookingNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except BookingConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except BookingDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return _booking_response(booking)

    @application.patch(
        "/api/bookings/{booking_id}", response_model=BookingResponse
    )
    def patch_booking(
        booking_id: str, request: BookingStatusRequest
    ) -> BookingResponse:
        try:
            booking = update_booking_status(
                booking_id, request.status, database_path
            )
        except BookingNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except BookingConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except BookingDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return _booking_response(booking)

    @application.delete(
        "/api/bookings/{booking_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    def remove_booking(booking_id: str) -> Response:
        try:
            delete_booking(booking_id, database_path)
        except BookingNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except BookingDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


def _booking_response(booking: BookingHistoryEntry) -> BookingResponse:
    return BookingResponse(
        booking_id=booking.booking_id,
        user_id=booking.user_id,
        display_name=booking.display_name,
        trip_id=booking.trip_id,
        trip_name=booking.trip_name,
        hotel_name=booking.hotel_name,
        city=booking.city,
        state=booking.state,
        check_in=booking.check_in,
        check_out=booking.check_out,
        nights=booking.nights,
        nightly_rate_usd=booking.nightly_rate_usd,
        stay_price_usd=booking.stay_price_usd,
        booked_on=booking.booked_on,
        status=booking.status,
    )


app = create_app()
