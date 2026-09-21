"""Search recording, hotel-wide user surge, and immutable booking prices."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.controllers import pricing
from backend.controllers.bookings import (
    create_booking,
    list_booking_history,
    update_booking_status,
)
from backend.controllers.database import (
    DatabaseController,
    DatabaseError,
    RecordNotFoundError,
    ReferenceConflictError,
)
from backend.controllers.search import SearchDataError, search_available_stays
from backend.models import Booking, Hotel, Trip, User
from backend.models.search import SearchHistory

HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def database(tmp_path, monkeypatch):
    database = DatabaseController(tmp_path / "expedia.sqlite3")
    database.initialize()
    monkeypatch.setattr(pricing, "current_timestamp", lambda: 1_789_754_400)
    return database


def search(database, query="Harbor", user_id="U006", **kwargs):
    return search_available_stays(
        query, database.database_path, user_id=user_id, **kwargs
    )


def test_current_search_triggers_fourth_price_without_compounding(database):
    rates = [search(database)[0].nightly_rate_usd for _ in range(6)]
    assert rates == [Decimal("150")] * 3 + [Decimal("180")] * 3
    assert search(database)[0].stay_price_usd == Decimal("360")
    assert database.get(Hotel, "H001").nightly_rate_usd == Decimal("150")
    assert len(database.list(SearchHistory)) == 7


def test_case_and_all_extra_whitespace_share_query_and_matching(database):
    for query in (
        "Harbor Lantern", " HARBOR  LANTERN ", "harbor\tlantern", "Harbor\n Lantern"
    ):
        results = search(database, query)
        assert [stay.trip_id for stay in results] == ["T001", "T009"]
    assert results[0].nightly_rate_usd == Decimal("180")
    assert {row.search_query for row in database.list(SearchHistory)} == {
        "harbor lantern"
    }


def test_queries_count_separately_but_any_qualifying_query_surges_hotel(database):
    for query in ("Harbor", "Harbor", "Lantern", "Lantern", "Harbor Lantern"):
        assert search(database, query)[0].nightly_rate_usd == Decimal("150")
    search(database, "Harbor")
    search(database, "Harbor")
    assert search(database, "Harbor Lantern")[0].nightly_rate_usd == Decimal("180")
    other_user = search(database, "Harbor", user_id="U005")[0]
    assert other_user.nightly_rate_usd == Decimal("150")
    assert search(database, "Maple")[0].nightly_rate_usd == Decimal("120")


def test_empty_anonymous_and_read_only_searches_do_not_record(database):
    assert search(database, " \t\n") == []
    for _ in range(5):
        assert search(database, user_id=None)[0].nightly_rate_usd == Decimal("150")
        search(database, record_search=False)
    assert database.list(SearchHistory) == []
    assert search(database, "No such hotel") == []
    row = database.list(SearchHistory)[0]
    assert row.user_id == "U006"
    assert row.search_query == "no such hotel"
    assert row.searched_at == pricing.current_timestamp()


def test_est_midnight_resets_counts_and_utc_midnight_does_not(database, monkeypatch):
    def at(iso):
        timestamp = int(
            datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp()
        )
        monkeypatch.setattr(pricing, "current_timestamp", lambda: timestamp)

    at("2026-09-18T23:59:59")
    for _ in range(3):
        search(database)
    at("2026-09-19T00:00:00")
    assert search(database)[0].nightly_rate_usd == Decimal("180")
    at("2026-09-19T04:59:59")  # Still the previous EST day, even in summer.
    assert search(database)[0].nightly_rate_usd == Decimal("180")
    at("2026-09-19T05:00:00")
    assert search(database)[0].nightly_rate_usd == Decimal("150")
    booking = create_booking("U006", "T001", database.database_path)
    assert booking.nightly_rate_usd == Decimal("150")


@pytest.mark.parametrize(
    ("base", "expected"),
    [("10.02", "12.02"), ("10.03", "12.04"), ("0", "0.00")],
)
def test_surge_rounds_nightly_rate_before_multiplying_nights(database, base, expected):
    database.update(
        replace(database.get(Hotel, "H001"), nightly_rate_usd=Decimal(base))
    )
    for _ in range(4):
        result = search(database)[0]
    assert result.nightly_rate_usd == Decimal(expected)
    assert result.stay_price_usd == Decimal(expected) * 2
    booking = create_booking("U006", "T001", database.database_path)
    assert booking.nightly_rate_usd == Decimal(expected)


def test_only_future_bookings_for_this_users_matching_hotels_surge(
    database, monkeypatch
):
    path = database.database_path
    original = create_booking("U006", "T001", path)
    for _ in range(4):
        search(database)
    # Booking needs only the trip: changing/omitting the query cannot bypass surge.
    surged = create_booking("U006", "T009", path)
    assert surged.nightly_rate_usd == Decimal("180")
    assert create_booking("U005", "T001", path).nightly_rate_usd == Decimal("150")
    assert create_booking("U006", "T002", path).nightly_rate_usd == Decimal("120")
    assert len(database.list(SearchHistory)) == 4  # Booking is not a search.
    monkeypatch.setattr(pricing, "current_timestamp", lambda: 1_789_754_400 + 86400)
    database.update(
        replace(database.get(Hotel, "H001"), nightly_rate_usd=Decimal("999"))
    )
    history = {entry.booking_id: entry for entry in list_booking_history("U006", path)}
    assert history[original.booking_id].nightly_rate_usd == Decimal("150")
    assert history[surged.booking_id].nightly_rate_usd == Decimal("180")
    update_booking_status(surged.booking_id, "cancelled", path)
    restored = update_booking_status(surged.booking_id, "confirmed", path)
    assert restored.nightly_rate_usd == Decimal("180")
    assert database.get(Booking, "B001").nightly_rate_usd == Decimal("150")


def test_simultaneous_searches_have_one_serial_threshold(database):
    with ThreadPoolExecutor(max_workers=6) as pool:
        rates = list(
            pool.map(lambda _: search(database)[0].nightly_rate_usd, range(6))
        )
    assert sorted(rates) == [Decimal("150")] * 3 + [Decimal("180")] * 3
    assert len(database.list(SearchHistory)) == 6


def test_search_history_references_and_atomic_failure(database, monkeypatch):
    with pytest.raises(RecordNotFoundError):
        database.create(SearchHistory("Sbad", "missing", "harbor", 100))
    search(database)
    with pytest.raises(ReferenceConflictError):
        database.delete(User, "U006")
    original_list = DatabaseController.list

    def broken_list(self, model):
        if model is Trip:
            raise DatabaseError("Unavailable")
        return original_list(self, model)

    monkeypatch.setattr(DatabaseController, "list", broken_list)
    with pytest.raises(SearchDataError):
        search(database)
    assert len(database.list(SearchHistory)) == 1


def test_upgrade_preserves_existing_prices_and_does_not_reseed(database):
    path = database.database_path
    database.delete(Booking, "B002")
    database.update(replace(database.get(Booking, "B001"), status="cancelled"))
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE bookings DROP COLUMN nightly_rate_cents")
        connection.execute("DROP TABLE search_history")
        connection.execute(
            "UPDATE app_metadata SET value = '2' WHERE key = 'schema_version'"
        )
    assert database.initialize() is False
    assert database.get(Booking, "B001").status == "cancelled"
    assert database.get(Booking, "B001").nightly_rate_usd == Decimal("150")
    with pytest.raises(RecordNotFoundError):
        database.get(Booking, "B002")
    for _ in range(4):
        search(database)
    booking = create_booking("U006", "T001", path)
    database.initialize()
    assert database.get(Booking, booking.booking_id).nightly_rate_usd == Decimal("180")
    assert len(database.list(SearchHistory)) == 4


def test_api_records_submissions_and_returns_session_specific_booking_prices(database):
    with TestClient(create_app(database.database_path)) as client:
        payload = {"hotel_name": "Harbor"}
        assert client.post("/api/stays", json=payload).status_code == 403
        for _ in range(4):
            response = client.post("/api/stays", json=payload, headers=HEADERS)
            assert response.status_code == 200
        assert database.list(SearchHistory) == []
        response = client.post(
            "/api/auth/login",
            json={"username": "traveler6", "password": "TravelDemo6!"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        for _ in range(5):
            assert client.get("/api/stays", params=payload).status_code == 200
        assert database.list(SearchHistory) == []
        for i in range(4):
            response = client.post("/api/stays", json=payload, headers=HEADERS)
            assert response.status_code == 200
            assert Decimal(response.json()[0]["nightly_rate_usd"]) == (
                150 if i < 3 else 180
            )
            assert response.headers["cache-control"] == "no-store"
        assert client.post(
            "/api/stays", json={"hotel_name": "  "}, headers=HEADERS
        ).json() == []
        assert client.post(
            "/api/stays", json={**payload, "user_id": "U001"}, headers=HEADERS
        ).status_code == 422
        assert len(database.list(SearchHistory)) == 4
        response = client.post("/api/bookings", json={"trip_id": "T001"}, headers=HEADERS)
        assert response.status_code == 201
        assert response.json()["nightly_rate_usd"] == "180"
        assert response.json()["stay_price_usd"] == "360"
        refreshed = client.get("/api/stays", params={"hotel_name": "Lantern"})
        assert Decimal(refreshed.json()[0]["nightly_rate_usd"]) == 180
        token = client.cookies.get("expedia_session")
        assert client.post("/api/auth/logout", headers=HEADERS).status_code == 204
        anonymous = client.post("/api/stays", json=payload, headers=HEADERS)
        assert Decimal(anonymous.json()[0]["nightly_rate_usd"]) == 150
        client.cookies.set("expedia_session", token, path="/api")
        assert client.post("/api/stays", json=payload, headers=HEADERS).status_code == 401
        assert len(database.list(SearchHistory)) == 4


def test_openapi_submission_contract(database):
    with TestClient(create_app(database.database_path)) as client:
        schema = client.get("/openapi.json").json()
        assert {"get", "post"} <= schema["paths"]["/api/stays"].keys()
        request = schema["components"]["schemas"]["SearchRequest"]
        assert request["required"] == ["hotel_name"]
        assert request["additionalProperties"] is False


def test_multiple_qualifying_queries_do_not_compound_and_rebooking_uses_surge(database):
    original = create_booking("U006", "T001", database.database_path)
    for query in ("Harbor", "Lantern"):
        for _ in range(4):
            search(database, query)
    assert search(database, "Harbor Lantern")[0].nightly_rate_usd == Decimal("180")
    cancelled = update_booking_status(
        original.booking_id, "cancelled", database.database_path
    )
    assert cancelled.nightly_rate_usd == Decimal("150")
    rebooked = create_booking("U006", "T001", database.database_path)
    assert rebooked.nightly_rate_usd == Decimal("180")


def test_api_search_storage_failures_do_not_return_base_price(database, monkeypatch):
    with TestClient(create_app(database.database_path)) as client:
        client.post(
            "/api/auth/login",
            json={"username": "traveler6", "password": "TravelDemo6!"},
            headers=HEADERS,
        )

        def unavailable(*args):
            raise DatabaseError("History storage is unavailable")

        monkeypatch.setattr(DatabaseController, "list_search_counts", unavailable)
        response = client.post(
            "/api/stays", json={"hotel_name": "Harbor"}, headers=HEADERS
        )
        assert response.status_code == 500
        assert response.headers["cache-control"] == "no-store"
        assert database.list(SearchHistory) == []
        response = client.post(
            "/api/bookings", json={"trip_id": "T001"}, headers=HEADERS
        )
        assert response.status_code == 500
        assert not any(booking.user_id == "U006" for booking in database.list(Booking))
