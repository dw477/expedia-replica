"""Resolve U.S. ZIP codes without persistence or presentation dependencies."""

import logging

import httpx

from backend.controllers.configuration import get_geoapify_api_key
from backend.models.location import ZipLocation, validate_postcode

_ENDPOINT = "https://api.geoapify.com/v1/geocode/search"


def _omit_geoapify_request_log(record: logging.LogRecord) -> bool:
    # HTTPX's INFO request log includes query-string credentials. Suppress only
    # this provider's entries, including when the application enables INFO logs.
    return "api.geoapify.com" not in record.getMessage()


logging.getLogger("httpx").addFilter(_omit_geoapify_request_log)


class ZipLookupError(RuntimeError):
    """Configuration, transport, HTTP, or response-format failure (safe message)."""


class ZipConfigurationError(ZipLookupError):
    """The backend key is missing or its configuration could not be read."""


def lookup_zip(postcode: str) -> ZipLocation | None:
    """Return a validated matching postcode, None if unresolved, or raise.

    Invalid input raises ValueError. Provider/configuration failures raise
    ZipLookupError without credential-bearing exception chains or response bodies.
    """
    validate_postcode(postcode)
    try:
        api_key = get_geoapify_api_key()
    except (OSError, UnicodeError):
        raise ZipConfigurationError("Geoapify configuration could not be read.") from None
    if not api_key:
        raise ZipConfigurationError("Geoapify key is not configured.")

    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.get(
                _ENDPOINT,
                params={
                    "postcode": postcode,
                    "type": "postcode",
                    "filter": "countrycode:us",
                    "format": "json",
                    "apiKey": api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise ZipLookupError("Geoapify ZIP lookup request failed.") from None

    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ZipLookupError("Geoapify returned an invalid ZIP lookup response.")
    for result in payload["results"]:
        if not isinstance(result, dict):
            continue
        country_code = result.get("country_code")
        if (
            result.get("postcode") != postcode
            or not isinstance(country_code, str)
            or country_code.lower() != "us"
            or result.get("result_type") != "postcode"
        ):
            continue
        locality = next(
            (
                value.strip()
                for field in ("city", "town", "village")
                if isinstance(value := result.get(field), str) and value.strip()
            ),
            None,
        )
        try:
            return ZipLocation(
                postcode=postcode,
                country_code="us",
                latitude=result.get("lat"),
                longitude=result.get("lon"),
                locality=locality,
            )
        except ValueError:
            continue
    return None
