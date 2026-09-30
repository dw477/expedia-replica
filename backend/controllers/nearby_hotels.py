"""Find live hotel places around the exact point returned by ZIP lookup."""

from math import asin, cos, isfinite, radians, sin, sqrt

import httpx

from backend.controllers.configuration import get_geoapify_api_key
from backend.controllers.geocoding import lookup_zip
from backend.models.location import ZipLocation
from backend.models.nearby_hotel import NearbyHotel

_ENDPOINT = "https://api.geoapify.com/v2/places"
_RADIUS_M = 5000
_PAGE_SIZE = 500
_MAX_PAGES = 20
_EARTH_RADIUS_M = 6371008.8


class NearbyHotelLookupError(RuntimeError):
    """A safe error for transport, HTTP, or provider response failures."""


class NearbyHotelConfigurationError(NearbyHotelLookupError):
    """The backend Geoapify key is missing or unreadable."""


def _distance_m(center: ZipLocation, latitude: float, longitude: float) -> float:
    """Great-circle distance from the returned ZIP point, in meters."""
    lat1, lat2 = radians(center.latitude), radians(latitude)
    delta_lat = lat2 - lat1
    delta_lon = radians(longitude - center.longitude)
    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * _EARTH_RADIUS_M * asin(min(1, sqrt(a)))


def _hotel_from_feature(feature: object, center: ZipLocation) -> NearbyHotel | None:
    if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
        return None
    properties = feature["properties"]
    place_id = properties.get("place_id")
    name = properties.get("name")
    latitude = properties.get("lat")
    longitude = properties.get("lon")
    if (
        not isinstance(place_id, str)
        or not place_id.strip()
        or not isinstance(name, str)
        or not name.strip()
        or type(latitude) not in (int, float)
        or type(longitude) not in (int, float)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or not isfinite(latitude)
        or not isfinite(longitude)
    ):
        return None
    try:
        distance = _distance_m(center, latitude, longitude)
        if distance > _RADIUS_M:
            return None
        address = properties.get("formatted")
        return NearbyHotel(
            place_id=place_id,
            name=name.strip(),
            address=(
                address.strip()
                if isinstance(address, str) and address.strip()
                else None
            ),
            latitude=latitude,
            longitude=longitude,
            distance_m=round(distance),
        )
    except ValueError:
        # An invalid individual place must not become a hotel result.
        return None


def search_hotels_near_zip(postcode: str) -> list[NearbyHotel] | None:
    """Return hotels within 5 km of the ZIP lookup point, or None if unresolved.

    Invalid ZIPs raise ValueError through lookup_zip. Provider/configuration
    failures raise safe errors. Results are unique by provider ID and ordered by
    distance, name, then ID. Empty provider results return an empty list.
    """
    center = lookup_zip(postcode)
    if center is None:
        return None
    try:
        api_key = get_geoapify_api_key()
    except (OSError, UnicodeError):
        raise NearbyHotelConfigurationError(
            "Geoapify configuration could not be read."
        ) from None
    if not api_key:
        raise NearbyHotelConfigurationError("Geoapify key is not configured.")

    hotels: dict[str, NearbyHotel] = {}
    params = {
        "categories": "accommodation.hotel",
        "filter": f"circle:{center.longitude},{center.latitude},{_RADIUS_M}",
        "limit": _PAGE_SIZE,
        "apiKey": api_key,
    }
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            for page in range(_MAX_PAGES):
                response = client.get(
                    _ENDPOINT, params=params | {"offset": page * _PAGE_SIZE}
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(
                    payload.get("features"), list
                ):
                    raise NearbyHotelLookupError(
                        "Geoapify returned an invalid hotel response."
                    )
                features = payload["features"]
                for feature in features:
                    hotel = _hotel_from_feature(feature, center)
                    if hotel is not None:
                        hotels[hotel.place_id] = hotel
                if len(features) < _PAGE_SIZE:
                    break
            else:
                raise NearbyHotelLookupError("Geoapify hotel result limit was exceeded.")
    except (httpx.HTTPError, ValueError):
        raise NearbyHotelLookupError("Geoapify hotel request failed.") from None

    return sorted(
        hotels.values(),
        key=lambda hotel: (hotel.distance_m, hotel.name, hotel.place_id),
    )
