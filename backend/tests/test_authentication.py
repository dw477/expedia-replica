"""Authentication, cookie sessions, CSV authority, and booking authorization."""

import csv
import hashlib
import shutil
import sqlite3
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.controllers.database import DEFAULT_DATA_DIRECTORY, DatabaseController
from backend.controllers.passwords import hash_password, verify_password
from backend.models import AuthSession, Booking, User

HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIRECTORY, source)
    path = tmp_path / "expedia.sqlite3"
    return path, source


@pytest.fixture
def client(setup):
    path, source = setup
    with TestClient(create_app(path, source)) as test_client:
        yield test_client


def login(client, number=6, **changes):
    payload = {
        "username": f"traveler{number}",
        "password": f"TravelDemo{number}!",
        **changes,
    }
    return client.post("/api/auth/login", json=payload, headers=HEADERS)


def edit_account(source, **changes):
    path = source / "users.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        names = reader.fieldnames
        rows = list(reader)
    rows[-1].update(changes)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def test_login_cookie_restores_session_and_logout_revokes_it(client, setup):
    assert client.get("/api/auth/me").status_code == 401
    response = login(client)
    assert response.status_code == 200
    assert response.json() == {"user_id": "U006", "display_name": "Demo Traveler 6"}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=28800" in cookie
    assert "Path=/api" in cookie
    assert response.headers["cache-control"] == "no-store"
    token = client.cookies.get("expedia_session")
    session = DatabaseController(setup[0]).list(AuthSession)[0]
    assert session.session_id == hashlib.sha256(token.encode()).hexdigest()
    assert token not in repr(session)
    assert client.get("/api/auth/me").json() == response.json()
    assert client.get("/api/users").json() == [response.json()]
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 204
    assert client.cookies.get("expedia_session") is None
    client.cookies.set("expedia_session", token, path="/api")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 204
    assert DatabaseController(setup[0]).list(AuthSession) == []


@pytest.mark.parametrize(
    "credentials",
    [
        {"password": "wrong"},
        {"username": "unknown"},
        {"password": "TravelDemo6! "},
        {"password": "traveldemo6!"},
    ],
)
def test_bad_credentials_use_same_error_and_do_not_create_sessions(
    client, setup, credentials
):
    response = login(client, **credentials)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}
    assert "set-cookie" not in response.headers
    assert DatabaseController(setup[0]).list(AuthSession) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "traveler6"},
        {"username": "traveler6", "password": ""},
        {"username": "traveler6", "password": "a" * 257},
        {"username": "traveler6", "password": "TravelDemo6!", "user_id": "U001"},
    ],
)
def test_login_requires_username_password_contract(client, payload):
    assert (
        client.post("/api/auth/login", json=payload, headers=HEADERS).status_code == 422
    )


def test_username_matching_ignores_case_and_surrounding_whitespace(client):
    assert login(client, username="  TRAVELER6  ").status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/users", None),
        ("GET", "/api/bookings", None),
        ("POST", "/api/bookings", {"trip_id": "T001"}),
        ("PATCH", "/api/bookings/B001", {"status": "cancelled"}),
        ("DELETE", "/api/bookings/B001", None),
    ],
)
def test_account_routes_require_a_session(client, method, path, payload):
    assert (
        client.request(method, path, json=payload, headers=HEADERS).status_code == 401
    )


def test_search_remains_public(client):
    assert (
        client.get("/api/stays", params={"hotel_name": "Harbor Lantern"}).status_code
        == 200
    )


def test_account_cannot_impersonate_or_change_another_traveler(client, setup):
    assert login(client).status_code == 200
    assert client.get("/api/bookings", params={"user_id": "U001"}).status_code == 403
    assert (
        client.post(
            "/api/bookings",
            json={"user_id": "U001", "trip_id": "T001"},
            headers=HEADERS,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/bookings/B001", json={"status": "cancelled"}, headers=HEADERS
        ).status_code
        == 404
    )
    assert client.delete("/api/bookings/B001", headers=HEADERS).status_code == 404
    assert DatabaseController(setup[0]).get(Booking, "B001").status == "confirmed"
    assert client.get("/api/bookings").json() == []


def test_authenticated_booking_uses_session_identity(client):
    assert login(client).status_code == 200
    response = client.post("/api/bookings", json={"trip_id": "T001"}, headers=HEADERS)
    assert response.status_code == 201
    booking = response.json()
    assert booking["user_id"] == "U006"
    assert client.get("/api/bookings").json() == [booking]
    assert (
        client.patch(
            f"/api/bookings/{booking['booking_id']}",
            json={"status": "cancelled"},
            headers=HEADERS,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/bookings/{booking['booking_id']}", headers=HEADERS
        ).status_code
        == 204
    )


def test_expired_and_forged_sessions_are_rejected(client, setup):
    assert login(client).status_code == 200
    database = DatabaseController(setup[0])
    session = database.list(AuthSession)[0]
    database.update(replace(session, expires_at=int(time.time()) - 1))
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/bookings").status_code == 401
    assert login(client).status_code == 200
    assert len(database.list(AuthSession)) == 1  # Expired rows were pruned.
    client.cookies.clear()
    client.cookies.set("expedia_session", "a" * 43, path="/api")
    assert client.get("/api/auth/me").status_code == 401


def test_successful_login_rotates_and_revokes_previous_cookie(client):
    assert login(client).status_code == 200
    old = client.cookies.get("expedia_session")
    assert login(client, 1).status_code == 200
    assert client.cookies.get("expedia_session") != old
    client.cookies.clear()
    client.cookies.set("expedia_session", old, path="/api")
    assert client.get("/api/auth/me").status_code == 401


def test_session_survives_application_restart(setup):
    path, source = setup
    with TestClient(create_app(path, source)) as first:
        assert login(first).status_code == 200
        token = first.cookies.get("expedia_session")
    with TestClient(create_app(path, source)) as restarted:
        restarted.cookies.set("expedia_session", token, path="/api")
        assert restarted.get("/api/auth/me").json()["user_id"] == "U006"


def test_csv_password_changes_apply_without_reseeding_and_revoke_sessions(
    client, setup
):
    assert login(client).status_code == 200
    edit_account(setup[1], password_hash=hash_password(" updated password! "))
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401
    assert login(client, password="updated password!").status_code == 401
    assert login(client, password=" updated password! ").status_code == 200


def test_malformed_or_duplicate_csv_credentials_fail_closed(client, setup):
    edit_account(setup[1], password_hash="plaintext")
    assert login(client).status_code == 500
    assert client.cookies.get("expedia_session") is None
    edit_account(
        setup[1], password_hash=hash_password("new password"), username="traveler1"
    )
    assert login(client).status_code == 500


def test_missing_csv_fails_closed(client, setup):
    (setup[1] / "users.csv").unlink()
    assert login(client).status_code == 500


def test_deleting_identity_disables_csv_login(client, setup):
    DatabaseController(setup[0]).delete(User, "U006")
    assert login(client).status_code == 401


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/auth/login", {"username": "traveler6", "password": "TravelDemo6!"}),
        ("/api/auth/logout", None),
        ("/api/bookings", {"trip_id": "T001"}),
    ],
)
def test_mutations_require_csrf_header(client, path, payload):
    assert login(client).status_code == 200
    assert client.post(path, json=payload).status_code == 403


def test_secure_cookie_mode(setup):
    with TestClient(
        create_app(*setup, cookie_secure=True), base_url="https://testserver"
    ) as client:
        response = login(client)
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert client.get("/api/auth/me").status_code == 200


def test_existing_database_upgrade_preserves_booking_changes(setup):
    path, source = setup
    database = DatabaseController(path)
    database.initialize(source)
    database.delete(Booking, "B002")
    database.update(replace(database.get(Booking, "B001"), status="cancelled"))
    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TABLE auth_sessions")
        connection.execute(
            "UPDATE app_metadata SET value = '1' WHERE key = 'schema_version'"
        )
        connection.commit()
    finally:
        connection.close()
    with TestClient(create_app(path, source)) as client:
        assert login(client, 1).status_code == 200
        history = client.get("/api/bookings").json()
        assert [(item["booking_id"], item["status"]) for item in history] == [
            ("B001", "cancelled")
        ]


def test_hashes_are_salted_and_password_case_whitespace_are_preserved():
    first = hash_password(" Case sensitive password! ")
    second = hash_password(" Case sensitive password! ")
    assert first != second
    assert verify_password(" Case sensitive password! ", first)
    assert not verify_password("Case sensitive password!", first)
    assert not verify_password(" case sensitive password! ", first)
    assert not verify_password("x", "plaintext")
    assert not verify_password("\ud800", first)


@pytest.mark.parametrize("number", range(1, 7))
def test_every_documented_demo_account_can_sign_in(client, number):
    response = login(client, number)
    assert response.status_code == 200
    assert response.json() == {
        "user_id": f"U{number:03}",
        "display_name": f"Demo Traveler {number}",
    }


def test_csv_username_changes_apply_and_revoke_old_sessions(client, setup):
    assert login(client).status_code == 200
    edit_account(setup[1], username="renamed-traveler")
    assert client.get("/api/auth/me").status_code == 401
    assert login(client).status_code == 401
    assert login(client, username="renamed-traveler").status_code == 200
