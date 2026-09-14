import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "expedia.sqlite3")) as test_client:
        yield test_client


def test_search_endpoint_returns_existing_calculated_results(client):
    response = client.get("/api/stays", params={"hotel_name": "Harbor Lantern"})

    assert response.status_code == 200
    results = response.json()
    assert [result["trip_id"] for result in results] == ["T001", "T009"]
    assert results[0] == {
        "trip_id": "T001",
        "trip_name": "Boston Harbor Weekend",
        "hotel_name": "Harbor Lantern Hotel",
        "city": "Boston",
        "state": "MA",
        "check_in": "2026-09-18",
        "check_out": "2026-09-20",
        "nights": 2,
        "nightly_rate_usd": "150",
        "stay_price_usd": "300",
    }


def test_search_endpoint_returns_empty_json_for_no_matches(client):
    response = client.get("/api/stays", params={"hotel_name": "Atlantis Hotel"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_endpoint_requires_a_hotel_name_parameter(client):
    response = client.get("/api/stays")

    assert response.status_code == 422
