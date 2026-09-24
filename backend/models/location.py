"""A postcode location, independent of priced Hotel entities."""

import re
from dataclasses import dataclass


def validate_postcode(postcode: str) -> None:
    if not isinstance(postcode, str) or re.fullmatch(r"[0-9]{5}", postcode) is None:
        raise ValueError("Postcode must be a five-digit ZIP string.")


@dataclass(frozen=True)
class ZipLocation:
    postcode: str
    country_code: str
    latitude: float
    longitude: float
    locality: str | None = None

    def __post_init__(self) -> None:
        validate_postcode(self.postcode)
        if self.country_code != "us":
            raise ValueError("Country code must be us.")
        for value, limit in ((self.latitude, 90), (self.longitude, 180)):
            # Bounds also exclude NaN/infinity; bool is not a coordinate.
            if type(value) not in (int, float) or not -limit <= value <= limit:
                raise ValueError("Coordinates must be finite numbers within bounds.")
        if self.locality is not None and (
            not isinstance(self.locality, str)
            or not self.locality.strip()
            or self.locality != self.locality.strip()
        ):
            raise ValueError("Locality must be non-empty, trimmed text when present.")
