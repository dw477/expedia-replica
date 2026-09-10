"""FastAPI boundary for the existing hotel availability search."""

from datetime import date
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from backend.search import SearchDataError, search_available_stays


app = FastAPI(title="Expedia Assignment API")


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


@app.get("/api/stays", response_model=list[HotelAvailabilityResponse])
def get_available_stays(
    hotel_name: str = Query(min_length=1, description="Hotel name to search"),
) -> list[HotelAvailabilityResponse]:
    """Expose the framework-free availability search as JSON."""

    try:
        stays = search_available_stays(hotel_name)
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
