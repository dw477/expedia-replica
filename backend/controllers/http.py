"""FastAPI boundary for SQLite-backed hotel availability search."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.controllers.authentication import (
    SESSION_LIFETIME_SECONDS,
    AccountExistsError,
    AuthenticationController,
    AuthenticationDataError,
    AuthenticationRequiredError,
    InvalidCredentialsError,
)
from backend.controllers.bookings import (
    BookingConflictError,
    BookingDataError,
    BookingHistoryEntry,
    BookingNotFoundError,
    create_booking,
    delete_booking,
    list_booking_history,
    update_booking_status,
)
from backend.controllers.configuration import geoapify_key_is_configured
from backend.controllers.chat import (
    ChatConfigurationError,
    ChatDataError,
    ChatProviderError,
    ChatTimeoutError,
    ChatUnavailableError,
    reply_to_chat,
)
from backend.controllers.chat_prompt import load_hotel_assistant_prompt
from backend.controllers.database import (
    DEFAULT_DATA_DIRECTORY,
    DEFAULT_DATABASE_PATH,
    DatabaseController,
    DatabaseError,
    RecordNotFoundError,
)
from backend.controllers.geocoding import (
    ZipConfigurationError,
    ZipLookupError,
    lookup_zip,
)
from backend.controllers.nearby_hotels import (
    NearbyHotelConfigurationError,
    NearbyHotelLookupError,
    search_hotels_near_zip,
)
from backend.controllers.local_hotels import LocalHotelsController
from backend.models.local_hotel import HotelZipAssociation, LocalHotelResult, SavedHotel
from backend.models.location import ZipLocation
from backend.controllers.search import SearchDataError, search_available_stays
from backend.models import User
from backend.models.chat import ChatMessage
from backend.models.contracts import (
    BookingCreateRequest,
    BookingResponse,
    BookingStatusRequest,
    ChatRequest,
    ChatResponse,
    ChatErrorResponse,
    HealthResponse,
    HotelAvailabilityResponse,
    LoginRequest,
    LocalHotelSaveRequest,
    LocalHotelDeleteRequest,
    LocalHotelResponse,
    DemoHotelNightResponse,
    NearbyHotelResponse,
    RegistrationRequest,
    SearchRequest,
    UserResponse,
    ZipLocationResponse,
    ZipLookupErrorResponse,
    ZipPostcode,
)


def create_app(
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    data_directory: str | Path = DEFAULT_DATA_DIRECTORY,
    *,
    cookie_secure: bool | None = None,
) -> FastAPI:
    """Create an API configured for a specific database and seed directory."""

    secure = (
        cookie_secure
        if cookie_secure is not None
        else os.environ.get("EXPEDIA_SECURE_COOKIES", "false").lower()
        in {"1", "true", "yes"}
    )
    cookie_name = "expedia_session"
    geoapify_configured = False
    hotel_assistant_prompt = ""

    def authentication() -> AuthenticationController:
        return AuthenticationController(database_path, data_directory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal geoapify_configured, hotel_assistant_prompt
        geoapify_configured = geoapify_key_is_configured()
        hotel_assistant_prompt = load_hotel_assistant_prompt()
        try:
            DatabaseController(database_path).initialize(data_directory)
        except DatabaseError as error:
            raise RuntimeError(f"Database startup failed: {error}") from error
        yield

    application = FastAPI(title="Expedia Assignment API", lifespan=lifespan)

    @application.get("/api/health", response_model=HealthResponse)
    def health(response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(
            status="ok",
            geoapify=(
                "key is configured" if geoapify_configured else "key is not configured"
            ),
        )

    @application.post(
        "/api/chat",
        response_model=ChatResponse,
        responses={
            403: {"model": ChatErrorResponse, "description": "Same-origin header required"},
            500: {"model": ChatErrorResponse, "description": "Chat storage failure"},
            502: {"model": ChatErrorResponse, "description": "Chat provider failure"},
            503: {"model": ChatErrorResponse, "description": "Chat configuration unavailable"},
        },
    )
    def chat(request: ChatRequest) -> ChatResponse:
        try:
            result = reply_to_chat(
                tuple(
                    ChatMessage(message.role, message.content)
                    for message in request.messages
                ),
                database_path=database_path,
                conversation_id=str(request.conversation_id) if request.conversation_id else None,
                prompt=hotel_assistant_prompt,
            )
        except ChatDataError:
            raise HTTPException(
                status_code=500,
                detail="The travel assistant could not access its saved data. Please try again.",
            ) from None
        except ChatConfigurationError:
            raise HTTPException(
                status_code=503,
                detail="The travel assistant is unavailable. Configure GEMINI_API_KEY and restart the backend.",
            ) from None
        except ChatUnavailableError:
            raise HTTPException(
                status_code=502,
                detail="Gemini is temporarily unavailable. Please try again in a moment.",
            ) from None
        except ChatTimeoutError:
            raise HTTPException(
                status_code=502,
                detail="Gemini took too long to reply. Please try again.",
            ) from None
        except ChatProviderError:
            raise HTTPException(
                status_code=502,
                detail="The travel assistant could not reply. Please try again.",
            ) from None
        return ChatResponse.model_validate(result)

    zip_error_responses = {
        404: {"model": ZipLookupErrorResponse, "description": "ZIP unresolved"},
        502: {"model": ZipLookupErrorResponse, "description": "Provider failure"},
        503: {"model": ZipLookupErrorResponse, "description": "Configuration unavailable"},
    }

    def resolve_zip_location(postcode: str) -> ZipLocationResponse:
        try:
            location = lookup_zip(postcode)
        except ZipConfigurationError:
            raise HTTPException(
                status_code=503,
                detail="Geoapify configuration is unavailable. Configure GEOAPIFY_API_KEY and restart the backend.",
            ) from None
        except ZipLookupError:
            raise HTTPException(
                status_code=502, detail="The location provider request failed."
            ) from None
        if location is None:
            raise HTTPException(
                status_code=404,
                detail=f"No matching U.S. location was found for ZIP {postcode}.",
            )
        return ZipLocationResponse.model_validate(location)

    @application.get(
        "/api/demo/zip-location",
        response_model=ZipLocationResponse,
        responses=zip_error_responses,
    )
    def demo_zip_location() -> ZipLocationResponse:
        return resolve_zip_location("16802")

    @application.get(
        "/api/zip-location",
        response_model=ZipLocationResponse,
        responses=zip_error_responses,
    )
    def zip_location(postcode: Annotated[ZipPostcode, Query()]) -> ZipLocationResponse:
        return resolve_zip_location(postcode)

    @application.get(
        "/api/zip-hotels",
        response_model=list[NearbyHotelResponse],
        responses=zip_error_responses,
    )
    def zip_hotels(postcode: Annotated[ZipPostcode, Query()]) -> list[NearbyHotelResponse]:
        """List live hotels within 5 km of this ZIP's returned point."""
        try:
            hotels = search_hotels_near_zip(postcode)
        except (ZipConfigurationError, NearbyHotelConfigurationError):
            raise HTTPException(
                status_code=503,
                detail="Geoapify configuration is unavailable. Configure GEOAPIFY_API_KEY and restart the backend.",
            ) from None
        except (ZipLookupError, NearbyHotelLookupError):
            raise HTTPException(
                status_code=502, detail="The hotel provider request failed."
            ) from None
        if hotels is None:
            raise HTTPException(
                status_code=404,
                detail=f"No matching U.S. location was found for ZIP {postcode}.",
            )
        return [NearbyHotelResponse.model_validate(hotel) for hotel in hotels]

    def local_hotel_response(result: LocalHotelResult) -> LocalHotelResponse:
        hotel = result.hotel
        return LocalHotelResponse(
            place_id=hotel.hotel_id, name=hotel.name, address=hotel.address,
            latitude=hotel.latitude, longitude=hotel.longitude,
            distance_m=result.association.distance_m,
            location=ZipLocationResponse.model_validate(result.association.location),
            demo_nights=[DemoHotelNightResponse.model_validate(night) for night in result.demo_nights],
        )

    @application.get("/api/local-hotels", response_model=list[LocalHotelResponse])
    def local_hotels(postcode: Annotated[ZipPostcode, Query()]) -> list[LocalHotelResponse]:
        try:
            return [local_hotel_response(item) for item in
                    LocalHotelsController(database_path).list_for_zip(postcode)]
        except DatabaseError:
            raise HTTPException(500, "Saved hotels could not be loaded. Please try again.") from None

    @application.get("/api/local-hotels/ids", response_model=list[str])
    def local_hotel_ids() -> list[str]:
        try:
            return LocalHotelsController(database_path).list_ids()
        except DatabaseError:
            raise HTTPException(500, "Saved hotel status could not be loaded. Please try again.") from None

    @application.post("/api/local-hotels", response_model=LocalHotelResponse, status_code=201)
    def save_local_hotel(payload: LocalHotelSaveRequest) -> LocalHotelResponse:
        try:
            hotel = SavedHotel(
                payload.hotel.place_id, payload.hotel.name, payload.hotel.address,
                payload.hotel.latitude, payload.hotel.longitude,
            )
            context = HotelZipAssociation(
                hotel.hotel_id, ZipLocation(**payload.location.model_dump()), payload.hotel.distance_m,
            )
            return local_hotel_response(LocalHotelsController(database_path).save(hotel, context))
        except ValueError:
            raise HTTPException(422, "A valid hotel and searched ZIP location are required.") from None
        except DatabaseError:
            raise HTTPException(500, "The hotel could not be saved. Please try again.") from None

    @application.delete("/api/local-hotels", status_code=204)
    def remove_local_hotel(payload: LocalHotelDeleteRequest) -> Response:
        # A JSON ID avoids URL decoding/normalization of opaque provider IDs.
        try:
            LocalHotelsController(database_path).remove(payload.place_id)
        except RecordNotFoundError:
            raise HTTPException(404, "Saved hotel was not found.") from None
        except DatabaseError:
            raise HTTPException(500, "The hotel could not be removed. Please try again.") from None
        return Response(status_code=204)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError):
        # Validation errors must never reflect submitted credentials back to clients.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {key: item[key] for key in ("loc", "msg", "type")}
                    for item in error.errors()
                ]
            },
        )

    @application.middleware("http")
    async def protect_mutations(request: Request, call_next):
        # A cross-site browser cannot attach this header without an approved CORS
        # preflight. The app intentionally serves the View and API on one origin.
        if request.url.path.startswith("/api/") and request.method not in {
            "GET",
            "HEAD",
            "OPTIONS",
        }:
            if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "A same-origin request is required."},
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if request.url.path.startswith(
            (
                "/api/auth/", "/api/bookings", "/api/users", "/api/stays",
                "/api/demo/zip-location", "/api/zip-location",
                "/api/zip-hotels", "/api/local-hotels",
                "/api/chat",
            )
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    def require_user(request: Request) -> User:
        try:
            return authentication().current_user(request.cookies.get(cookie_name))
        except AuthenticationRequiredError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        except AuthenticationDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

    def optional_user(request: Request) -> User | None:
        # Public searches need no cookie. A supplied invalid cookie must surface
        # session expiry so the View clears private results instead of mispricing.
        return require_user(request) if request.cookies.get(cookie_name) else None

    def user_response(user: User) -> UserResponse:
        return UserResponse(user_id=user.user_id, display_name=user.display_name)

    def set_session_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            cookie_name,
            token,
            max_age=SESSION_LIFETIME_SECONDS,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/api",
        )
        response.headers["Cache-Control"] = "no-store"

    @application.post(
        "/api/auth/register",
        response_model=UserResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def register(
        request: Request, response: Response, account: RegistrationRequest
    ) -> UserResponse:
        try:
            user, token = authentication().register(
                account.username,
                account.display_name,
                account.password,
                request.cookies.get(cookie_name),
            )
        except AccountExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except AuthenticationDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        set_session_cookie(response, token)
        return user_response(user)

    @application.post("/api/auth/login", response_model=UserResponse)
    def login(
        request: Request, response: Response, credentials: LoginRequest
    ) -> UserResponse:
        try:
            user, token = authentication().login(
                credentials.username,
                credentials.password,
                request.cookies.get(cookie_name),
            )
        except InvalidCredentialsError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        except AuthenticationDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        set_session_cookie(response, token)
        return user_response(user)

    @application.get("/api/auth/me", response_model=UserResponse)
    def current_user(
        response: Response, user: User = Depends(require_user)
    ) -> UserResponse:
        response.headers["Cache-Control"] = "no-store"
        return user_response(user)

    @application.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(request: Request) -> Response:
        try:
            authentication().logout(request.cookies.get(cookie_name))
        except AuthenticationDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(
            cookie_name, path="/api", secure=secure, httponly=True, samesite="lax"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/stays", response_model=list[HotelAvailabilityResponse])
    def get_available_stays(
        hotel_name: str = Query(min_length=1, description="Hotel name to search"),
        user: User | None = Depends(optional_user),
    ) -> list[HotelAvailabilityResponse]:
        """Read current prices without recording a submitted search."""
        return available_stays(hotel_name, user, record_search=False)

    @application.post("/api/stays", response_model=list[HotelAvailabilityResponse])
    def submit_search(
        search: SearchRequest, user: User | None = Depends(optional_user)
    ) -> list[HotelAvailabilityResponse]:
        """Record a signed-in non-empty search and return prices including it."""
        return available_stays(search.hotel_name, user, record_search=True)

    def available_stays(
        hotel_name: str, user: User | None, *, record_search: bool
    ) -> list[HotelAvailabilityResponse]:
        try:
            stays = search_available_stays(
                hotel_name,
                database_path=database_path,
                data_directory=data_directory,
                user_id=user.user_id if user else None,
                record_search=record_search,
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
    def get_users(user: User = Depends(require_user)) -> list[UserResponse]:
        """Compatibility route: expose only the signed-in user's public identity."""
        return [user_response(user)]

    @application.get("/api/bookings", response_model=list[BookingResponse])
    def get_booking_history(
        user_id: str | None = Query(default=None, min_length=1, max_length=64),
        user: User = Depends(require_user),
    ) -> list[BookingResponse]:
        if user_id is not None and user_id != user.user_id:
            raise HTTPException(
                status_code=403, detail="You can only view your own bookings."
            )
        try:
            bookings = list_booking_history(user.user_id, database_path)
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
    def post_booking(
        request: BookingCreateRequest, user: User = Depends(require_user)
    ) -> BookingResponse:
        if request.user_id is not None and request.user_id != user.user_id:
            raise HTTPException(
                status_code=403, detail="You can only book for your signed-in account."
            )
        try:
            booking = create_booking(user.user_id, request.trip_id, database_path)
        except BookingNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except BookingConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except BookingDataError as error:
            raise HTTPException(status_code=500, detail=str(error)) from error
        return _booking_response(booking)

    @application.patch("/api/bookings/{booking_id}", response_model=BookingResponse)
    def patch_booking(
        booking_id: str,
        request: BookingStatusRequest,
        user: User = Depends(require_user),
    ) -> BookingResponse:
        try:
            booking = update_booking_status(
                booking_id, request.status, database_path, owner_user_id=user.user_id
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
    def remove_booking(booking_id: str, user: User = Depends(require_user)) -> Response:
        try:
            delete_booking(booking_id, database_path, owner_user_id=user.user_id)
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
