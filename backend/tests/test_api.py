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


def test_booking_crud_flow(client):
    users_response = client.get("/api/users")
    assert users_response.status_code == 200
    assert users_response.json()[-1] == {
        "user_id": "U006",
        "display_name": "Demo Traveler 6",
    }

    create_response = client.post(
        "/api/bookings", json={"user_id": "U006", "trip_id": "T001"}
    )
    assert create_response.status_code == 201
    booking = create_response.json()
    assert booking["user_id"] == "U006"
    assert booking["trip_id"] == "T001"
    assert booking["status"] == "confirmed"

    history_response = client.get("/api/bookings", params={"user_id": "U006"})
    assert history_response.status_code == 200
    assert [item["booking_id"] for item in history_response.json()] == [
        booking["booking_id"]
    ]

    cancel_response = client.patch(
        f"/api/bookings/{booking['booking_id']}", json={"status": "cancelled"}
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    delete_response = client.delete(f"/api/bookings/{booking['booking_id']}")
    assert delete_response.status_code == 204
    assert client.get("/api/bookings", params={"user_id": "U006"}).json() == []


def test_booking_endpoints_return_domain_errors(client):
    duplicate = client.post(
        "/api/bookings", json={"user_id": "U001", "trip_id": "T001"}
    )
    missing_user = client.get("/api/bookings", params={"user_id": "missing"})
    missing_booking = client.delete("/api/bookings/missing")

    assert duplicate.status_code == 409
    assert missing_user.status_code == 404
    assert missing_booking.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "   ", "trip_id": "T001"},
        {"user_id": "U006", "trip_id": "   "},
        {"user_id": "U006", "trip_id": "T001", "status": "cancelled"},
    ],
)
def test_booking_create_rejects_invalid_contract_input(client, payload):
    response = client.post("/api/bookings", json=payload)
    assert response.status_code == 422
    assert client.get("/api/bookings", params={"user_id": "U006"}).json() == []


def test_booking_create_normalizes_surrounding_id_whitespace(client):
    response = client.post(
        "/api/bookings", json={"user_id": " U006 ", "trip_id": " T001 "}
    )
    assert response.status_code == 201
    assert response.json()["user_id"] == "U006"
    assert response.json()["trip_id"] == "T001"


@pytest.mark.parametrize(
    "payload", [{"status": "unknown"}, {"status": "cancelled", "trip_id": "T002"}]
)
def test_booking_status_rejects_invalid_contract_input(client, payload):
    assert client.patch("/api/bookings/B001", json=payload).status_code == 422
    history = client.get("/api/bookings", params={"user_id": "U001"}).json()
    assert (
        next(item for item in history if item["booking_id"] == "B001")["status"]
        == "confirmed"
    )
