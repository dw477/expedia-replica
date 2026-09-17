"""FastAPI boundary for SQLite-backed hotel availability search."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, status

from backend.controllers.bookings import (
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
from backend.controllers.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseController,
    DatabaseError,
)
from backend.controllers.search import SearchDataError, search_available_stays
from backend.models.contracts import (
    BookingCreateRequest,
    BookingResponse,
    BookingStatusRequest,
    HotelAvailabilityResponse,
    UserResponse,
)


def create_app(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
) -> FastAPI:
    """Create an API configured for a specific database and seed directory."""

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            DatabaseController(database_path).initialize(data_directory)
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

    @application.patch("/api/bookings/{booking_id}", response_model=BookingResponse)
    def patch_booking(
        booking_id: str, request: BookingStatusRequest
    ) -> BookingResponse:
        try:
            booking = update_booking_status(booking_id, request.status, database_path)
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
