"""User-specific daily surge policy shared by searches and new bookings."""

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from backend.controllers.database import DatabaseController
from backend.models import Hotel
from backend.models.search import normalize_query

EST = timezone(timedelta(hours=-5), "EST")


def current_timestamp() -> int:
    return int(time.time())


def surged_queries(
    database: DatabaseController, user_id: str | None, now: int
) -> tuple[str, ...]:
    """Read this user's qualifying queries within the caller's transaction."""
    if user_id is None:
        return ()
    midnight = datetime.fromtimestamp(now, EST).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    counts = database.list_search_counts(
        user_id, int(midnight.timestamp()), int((midnight + timedelta(days=1)).timestamp())
    )
    return tuple(item.search_query for item in counts if item.search_count >= 4)


def nightly_rate(hotel: Hotel, queries: tuple[str, ...]) -> Decimal:
    """Any qualifying matching query surges this hotel once, from its base rate."""
    name = normalize_query(hotel.hotel_name)
    if any(query in name for query in queries):
        return (hotel.nightly_rate_usd * Decimal("1.2")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return hotel.nightly_rate_usd
