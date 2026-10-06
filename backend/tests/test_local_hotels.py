"""Local storage HTTP/transaction contracts; all mutation tests use temp databases."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi.testclient import TestClient

from backend.controllers.database import DatabaseController, DatabaseError, connect_database
from backend.controllers.http import create_app
from backend.controllers.local_hotels import LocalHotelsController
from backend.models.local_hotel import HotelZipAssociation, SavedHotel
from backend.models.location import ZipLocation

HEADERS = {"X-Requested-With": "XMLHttpRequest"}
HOTEL = {
    "place_id": " Provider/ID:001 ", "name": "Hotel", "address": None,
    "latitude": 42.36, "longitude": -71.06, "distance_m": 123,
}
LOCATION = {
    "postcode": "02108", "country_code": "us", "latitude": 42.35,
    "longitude": -71.05, "locality": "Boston",
}
PAYLOAD = {"hotel": HOTEL, "location": LOCATION}


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "local.sqlite3"
    with TestClient(create_app(path)) as client:
        yield client, path


def snapshot(path):
    with connect_database(path) as connection:
        return {
            table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("hotels", "users", "trips", "bookings")
        }


def test_save_persists_context_defaults_and_existing_records(setup, monkeypatch):
    client, path = setup
    before = snapshot(path)
    # Local operations never need the live provider.
    monkeypatch.setattr("backend.controllers.http.lookup_zip", lambda _: pytest.fail("Provider called"))
    assert client.get("/api/local-hotels?postcode=02108").json() == []
    saved = client.post("/api/local-hotels", json=PAYLOAD, headers=HEADERS)
    assert saved.status_code == 201
    assert saved.headers["cache-control"] == "no-store"
    body = saved.json()
    assert body["place_id"] == HOTEL["place_id"]
    assert body["location"] == LOCATION
    assert [night["stay_date"] for night in body["demo_nights"]] == [
        f"2026-10-{day}" for day in range(10, 15)
    ]
    assert all(night["nightly_rate_usd"] == "100.00" and night["rooms_available"] == 20
               for night in body["demo_nights"])
    with TestClient(create_app(path)) as reopened:
        assert reopened.get("/api/local-hotels?postcode=02108").json() == [body]
        assert reopened.get("/api/local-hotels/ids").json() == [HOTEL["place_id"]]
        assert reopened.get("/api/local-hotels?postcode=16802").json() == []
    assert snapshot(path) == before


def test_repeated_saves_preserve_rates_rooms_and_multiple_zip_contexts(setup):
    client, path = setup
    client.post("/api/local-hotels", json=PAYLOAD, headers=HEADERS)
    with connect_database(path) as connection:
        connection.execute("UPDATE demo_hotel_nights SET nightly_rate_cents=12345, rooms_available=3")
    second = {"hotel": {**HOTEL, "name": "Changed"}, "location": {**LOCATION, "postcode": "16802"}}
    assert client.post("/api/local-hotels", json=second, headers=HEADERS).status_code == 201
    assert client.post("/api/local-hotels", json=PAYLOAD, headers=HEADERS).status_code == 201
    assert DatabaseController(path).initialize() is False
    for postcode in ("02108", "16802"):
        result = client.get(f"/api/local-hotels?postcode={postcode}").json()[0]
        assert result["name"] == "Hotel"
        assert result["location"]["postcode"] == postcode
        assert len(result["demo_nights"]) == 5
        assert all(n["nightly_rate_usd"] == "123.45" and n["rooms_available"] == 3 for n in result["demo_nights"])
    with connect_database(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM saved_hotels").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM saved_hotel_zip_locations").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM demo_hotel_nights").fetchone()[0] == 5


def test_remove_deletes_all_dependent_rows_only_after_success(setup):
    client, path = setup
    before = snapshot(path)
    for postcode in ("02108", "16802"):
        client.post("/api/local-hotels", json={"hotel": HOTEL, "location": {**LOCATION, "postcode": postcode}}, headers=HEADERS)
    client.post("/api/local-hotels", json={"hotel": {**HOTEL, "place_id": "unrelated"}, "location": LOCATION}, headers=HEADERS)
    response = client.request("DELETE", "/api/local-hotels", json={"place_id": HOTEL["place_id"]}, headers=HEADERS)
    assert response.status_code == 204 and response.content == b""
    assert client.get("/api/local-hotels/ids").json() == ["unrelated"]
    assert client.get("/api/local-hotels?postcode=16802").json() == []
    assert len(client.get("/api/local-hotels?postcode=02108").json()) == 1
    with connect_database(path) as connection:
        for table in ("saved_hotels", "saved_hotel_zip_locations", "demo_hotel_nights"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE hotel_id=?", (HOTEL["place_id"],)).fetchone()[0] == 0
    assert snapshot(path) == before
    assert client.request("DELETE", "/api/local-hotels", json={"place_id": HOTEL["place_id"]}, headers=HEADERS).status_code == 404


def test_failed_delete_rolls_back_children(setup):
    client, path = setup
    client.post("/api/local-hotels", json=PAYLOAD, headers=HEADERS)
    before = client.get("/api/local-hotels?postcode=02108").json()
    with connect_database(path) as connection:
        connection.execute("CREATE TRIGGER reject_local_delete BEFORE DELETE ON saved_hotels BEGIN SELECT RAISE(ABORT, 'private failure'); END")
    response = client.request("DELETE", "/api/local-hotels", json={"place_id": HOTEL["place_id"]}, headers=HEADERS)
    assert response.status_code == 500
    assert "private failure" not in response.text
    assert client.get("/api/local-hotels?postcode=02108").json() == before


def test_failed_save_rolls_back_hotel_and_association(setup):
    client, path = setup
    with connect_database(path) as connection:
        connection.execute("CREATE TRIGGER reject_nights BEFORE INSERT ON demo_hotel_nights BEGIN SELECT RAISE(ABORT, 'private failure'); END")
    response = client.post("/api/local-hotels", json=PAYLOAD, headers=HEADERS)
    assert response.status_code == 500
    assert "private failure" not in response.text
    assert client.get("/api/local-hotels/ids").json() == []
    assert client.get("/api/local-hotels?postcode=02108").json() == []


@pytest.mark.parametrize("patch", [
    {"place_id": " "}, {"latitude": 91}, {"longitude": -181},
    {"latitude": True}, {"distance_m": -1}, {"nightly_rate_usd": "1.00"},
])
def test_invalid_save_rejected_without_writes(setup, patch):
    client, _ = setup
    assert client.post("/api/local-hotels", json={**PAYLOAD, "hotel": {**HOTEL, **patch}}, headers=HEADERS).status_code == 422
    assert client.get("/api/local-hotels/ids").json() == []


@pytest.mark.parametrize("postcode", ["1234", "123456", "１２３４５", "abcde", "16802\n"])
def test_invalid_zip_contract(setup, postcode):
    client, _ = setup
    assert client.get("/api/local-hotels", params={"postcode": postcode}).status_code == 422
    assert client.post("/api/local-hotels", json={**PAYLOAD, "location": {**LOCATION, "postcode": postcode}}, headers=HEADERS).status_code == 422


def test_no_store_csrf_validation_and_openapi(setup):
    client, _ = setup
    for method, payload in (("POST", PAYLOAD), ("DELETE", {"place_id": "x"})):
        response = client.request(method, "/api/local-hotels", json=payload)
        assert response.status_code == 403 and response.headers["cache-control"] == "no-store"
    for url in ("/api/local-hotels", "/api/local-hotels?postcode=02108", "/api/local-hotels/ids"):
        assert client.get(url).headers["cache-control"] == "no-store"
    schema = client.get("/openapi.json").json()
    assert {"get", "post", "delete"} == schema["paths"]["/api/local-hotels"].keys()
    assert set(schema["components"]["schemas"]["LocalHotelSaveRequest"]["properties"]) == {"hotel", "location"}
    assert schema["components"]["schemas"]["LocalHotelFields"]["additionalProperties"] is False
    assert "201" in schema["paths"]["/api/local-hotels"]["post"]["responses"]
    assert "204" in schema["paths"]["/api/local-hotels"]["delete"]["responses"]


def test_nullable_metadata_and_exact_case_sensitive_ids(setup):
    client, _ = setup
    for place_id in ("Case", "case"):
        response = client.post("/api/local-hotels", json={**PAYLOAD, "hotel": {**HOTEL, "place_id": place_id, "name": None}}, headers=HEADERS)
        assert response.status_code == 201 and response.json()["name"] is None
    assert client.get("/api/local-hotels/ids").json() == ["Case", "case"]


def test_storage_failure_is_sanitized(setup, monkeypatch):
    client, _ = setup
    def fail(*_):
        raise DatabaseError("private database path and details")
    monkeypatch.setattr(LocalHotelsController, "list_for_zip", fail)
    response = client.get("/api/local-hotels?postcode=02108")
    assert response.status_code == 500 and "private" not in response.text


def test_concurrent_saves_deduplicate(tmp_path):
    path = tmp_path / "concurrent.sqlite3"
    DatabaseController(path).initialize()
    hotel = SavedHotel("same", "Hotel", None, 0, 0)
    association = HotelZipAssociation("same", ZipLocation("02108", "us", 0, 0), 0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: LocalHotelsController(path).save(hotel, association), range(2)))
    assert results[0] == results[1]
    assert len(results[0].demo_nights) == 5
    assert results[0].demo_nights[0].stay_date == date(2026, 10, 10)
