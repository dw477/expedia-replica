"""Immutable location results from a places provider, separate from bookable hotels."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class NearbyHotel:
    place_id: str
    name: str
    address: str | None
    latitude: float
    longitude: float
    distance_m: int

    def __post_init__(self) -> None:
        if not isinstance(self.place_id, str) or not self.place_id.strip():
            raise ValueError("place_id must be non-empty text")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty text")
        if self.address is not None and (
            not isinstance(self.address, str) or not self.address.strip()
        ):
            raise ValueError("address must be non-empty text when present")
        for value, limit in ((self.latitude, 90), (self.longitude, 180)):
            if (
                type(value) not in (int, float)
                or abs(value) > limit
                or not isfinite(value)
            ):
                raise ValueError("coordinates must be finite numbers within bounds")
        if type(self.distance_m) is not int or not 0 <= self.distance_m <= 5000:
            raise ValueError("distance_m must be an integer within the search radius")
