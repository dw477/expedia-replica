"""Account creation contracts, two-store persistence, and automatic sessions."""

import base64
import csv
import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.controllers import database as storage
from backend.controllers.authentication import (
    AccountExistsError,
    AuthenticationController,
    AuthenticationDataError,
)
from backend.controllers.database import DEFAULT_DATA_DIRECTORY, DatabaseController
from backend.controllers.passwords import verify_password
from backend.models import AuthSession, User

HEADERS = {"X-Requested-With": "XMLHttpRequest"}
PAYLOAD = {
    "username": "newtraveler",
    "display_name": "New Traveler",
    "password": "Abcdef1!",
}


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIRECTORY, source)
    path = tmp_path / "expedia.sqlite3"
    DatabaseController(path).initialize(source)
    return path, source


@pytest.fixture
def client(setup):
    with TestClient(create_app(*setup)) as test_client:
        yield test_client


def register(client, **changes):
    return client.post(
        "/api/auth/register", json={**PAYLOAD, **changes}, headers=HEADERS
    )


def test_create_account_auto_signs_in_and_persists_after_restart(client, setup):
    response = register(
        client, username="  NewTraveler  ", display_name="  New Traveler  "
    )
    assert response.status_code == 201
    user = response.json()
    assert set(user) == {"user_id", "display_name"}
    assert user["display_name"] == "New Traveler"
    assert len(user["user_id"]) == 33
    assert user["user_id"].startswith("U")
    assert user["user_id"] not in {f"U00{i}" for i in range(1, 7)}
    assert response.headers["cache-control"] == "no-store"
    for attribute in ["HttpOnly", "SameSite=lax", "Path=/api", "Max-Age=28800"]:
        assert attribute in response.headers["set-cookie"]
    assert client.get("/api/auth/me").json() == user
    assert client.get("/api/users").json() == [user]
    assert client.get("/api/bookings").json() == []
    assert client.get("/api/bookings", params={"user_id": "U001"}).status_code == 403
    booking = client.post("/api/bookings", json={"trip_id": "T001"}, headers=HEADERS)
    assert booking.status_code == 201
    assert booking.json()["user_id"] == user["user_id"]
    database = DatabaseController(setup[0])
    account = database.list_user_accounts(setup[1])[-1]
    assert account.username == "newtraveler"
    assert verify_password(PAYLOAD["password"], account.password_hash)
    assert PAYLOAD["password"] not in (setup[1] / "users.csv").read_text()
    token = client.cookies.get("expedia_session")
    assert (
        database.list(AuthSession)[0].session_id
        == hashlib.sha256(token.encode()).hexdigest()
    )
    assert not database.initialize(setup[1])
    with TestClient(create_app(*setup)) as restarted:
        restarted.cookies.set("expedia_session", token, path="/api")
        assert restarted.get("/api/auth/me").json() == user
        assert len(restarted.get("/api/bookings").json()) == 1
        assert restarted.post("/api/auth/logout", headers=HEADERS).status_code == 204
        assert (
            restarted.post(
                "/api/auth/login",
                json={"username": "NEWTRAVELER", "password": PAYLOAD["password"]},
                headers=HEADERS,
            ).json()
            == user
        )


@pytest.mark.parametrize(
    "password",
    [
        "Abcde1!",
        "abcdef1!",
        "Abcdefg!",
        "Abcdef12",
        "Abcdef1#",
        "Abcdef1! ",
        "Abcdef1!\n",
        "Abcdé12!",
        "A1!" + "a" * 254,
    ],
)
def test_password_policy_rejects_invalid_input_without_writes(client, setup, password):
    original = (setup[1] / "users.csv").read_bytes()
    response = register(client, password=password)
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])
    assert "set-cookie" not in response.headers
    assert (setup[1] / "users.csv").read_bytes() == original
    assert len(DatabaseController(setup[0]).list(User)) == 6
    assert DatabaseController(setup[0]).list(AuthSession) == []


@pytest.mark.parametrize("special", list("!@$%&?"))
def test_each_agreed_special_character_is_accepted(client, special):
    assert register(client, password=f"Abcdef1{special}").status_code == 201


def test_password_does_not_require_lowercase_and_accepts_maximum_length(client):
    assert register(client, password="A1!" + "A" * 253).status_code == 201


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "ab"},
        {"username": "x" * 65},
        {"username": "-abc"},
        {"username": "abc name"},
        {"username": "abc\n" + "xyz"},
        {"display_name": "  "},
        {"user_id": "my-id"},
        {"email": "x@example.com"},
    ],
)
def test_registration_rejects_invalid_fields_and_unknown_fields(client, changes):
    assert register(client, **changes).status_code == 422


def test_display_name_is_required_and_csrf_header_is_required(client):
    assert client.post("/api/auth/register", json=PAYLOAD).status_code == 403
    assert (
        client.post(
            "/api/auth/register",
            json={"username": "newtraveler", "password": "Abcdef1!"},
            headers=HEADERS,
        ).status_code
        == 422
    )


def test_duplicate_username_keeps_existing_session_and_data(client, setup):
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "traveler6", "password": "TravelDemo6!"},
            headers=HEADERS,
        ).status_code
        == 200
    )
    token = client.cookies.get("expedia_session")
    original = (setup[1] / "users.csv").read_bytes()
    response = register(client, username=" TRAVELER6 ")
    assert response.status_code == 409
    assert client.cookies.get("expedia_session") == token
    assert client.get("/api/auth/me").json()["user_id"] == "U006"
    assert (setup[1] / "users.csv").read_bytes() == original
    assert len(DatabaseController(setup[0]).list(User)) == 6


def test_successful_registration_revokes_previous_browser_session(client, setup):
    client.post(
        "/api/auth/login",
        json={"username": "traveler6", "password": "TravelDemo6!"},
        headers=HEADERS,
    )
    previous = client.cookies.get("expedia_session")
    assert register(client).status_code == 201
    sessions = DatabaseController(setup[0]).list(AuthSession)
    assert len(sessions) == 1
    assert sessions[0].session_id != hashlib.sha256(previous.encode()).hexdigest()


def test_deleted_identity_stays_deleted_and_username_stays_reserved(client, setup):
    database = DatabaseController(setup[0])
    database.delete(User, "U006")
    assert register(client, username="traveler6").status_code == 409
    assert "U006" not in {user.user_id for user in database.list(User)}


def test_parallel_registration_allocates_unique_ids_and_one_duplicate_winner(setup):
    def create(username):
        try:
            return AuthenticationController(*setup).register(
                username, "Traveler", PAYLOAD["password"]
            )[0]
        except AccountExistsError:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        users = list(
            pool.map(create, ["parallel1", "parallel2", "parallel3", "parallel3"])
        )
    successful = [user for user in users if user is not None]
    assert len(successful) == 3
    assert len({user.user_id for user in successful}) == 3
    assert len(DatabaseController(setup[0]).list_user_accounts(setup[1])) == 9
    assert len(DatabaseController(setup[0]).list(AuthSession)) == 3


def test_failed_csv_save_rolls_back_identity_and_session_then_can_retry(
    setup, monkeypatch
):
    path, source = setup
    original = (source / "users.csv").read_bytes()
    atomic_write = storage._atomic_write
    failed = False

    def fail_once(target, content):
        nonlocal failed
        if target == source / "users.csv" and not failed:
            failed = True
            # Failure after publication exercises restoration, not just a no-op.
            atomic_write(target, content)
            raise OSError("Simulated storage failure")
        atomic_write(target, content)

    monkeypatch.setattr(storage, "_atomic_write", fail_once)
    with pytest.raises(AuthenticationDataError):
        AuthenticationController(*setup).register(
            "newtraveler", "New Traveler", PAYLOAD["password"]
        )
    assert (source / "users.csv").read_bytes() == original
    assert len(DatabaseController(path).list(User)) == 6
    assert DatabaseController(path).list(AuthSession) == []
    assert not (source / ".users.csv.registration.json").exists()
    AuthenticationController(*setup).register(
        "newtraveler", "New Traveler", PAYLOAD["password"]
    )
    assert len(DatabaseController(path).list(User)) == 7


@pytest.mark.parametrize("committed", [False, True])
def test_interrupted_save_recovers_using_committed_identity(setup, committed):
    path, source = setup
    csv_path = source / "users.csv"
    original = csv_path.read_bytes()
    database = DatabaseController(path)
    account = database.list_user_accounts(source)[0]
    user_id = "Uinterrupted"
    with csv_path.open("a", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerow(
            [user_id, "Interrupted", "interrupted", account.password_hash]
        )
    journal = source / ".users.csv.registration.json"
    journal.write_text(
        json.dumps(
            {
                "user_id": user_id,
                "original_csv": base64.b64encode(original).decode("ascii"),
            }
        )
    )
    if committed:
        database.create(User(user_id, "Interrupted"))
    accounts = database.list_user_accounts(source)
    assert (user_id in {item.user_id for item in accounts}) == committed
    assert not journal.exists()
    if not committed:
        assert csv_path.read_bytes() == original
    assert len(database.list(User)) == 6 + int(committed)


def test_database_id_collision_does_not_leave_a_recovery_journal(setup, monkeypatch):
    from uuid import UUID

    from backend.controllers import authentication

    generated = UUID("12345678-1234-1234-1234-123456789012")
    database = DatabaseController(setup[0])
    database.create(User(f"U{generated.hex.upper()}", "Existing"))
    original = (setup[1] / "users.csv").read_bytes()
    monkeypatch.setattr(authentication, "uuid4", lambda: generated)
    with pytest.raises(AuthenticationDataError):
        AuthenticationController(*setup).register(
            "newtraveler", "New Traveler", PAYLOAD["password"]
        )
    assert (setup[1] / "users.csv").read_bytes() == original
    assert not (setup[1] / ".users.csv.registration.json").exists()
    assert len(database.list_user_accounts(setup[1])) == 6


def test_openapi_registration_contract_has_exact_fields(client):
    schema = client.get("/openapi.json").json()
    request = schema["components"]["schemas"]["RegistrationRequest"]
    assert set(request["properties"]) == {"username", "display_name", "password"}
    assert request["additionalProperties"] is False
    assert set(request["required"]) == {"username", "display_name", "password"}
    assert "201" in schema["paths"]["/api/auth/register"]["post"]["responses"]


def test_storage_failure_is_http_500_and_preserves_previous_session(
    client, setup, monkeypatch
):
    client.post(
        "/api/auth/login",
        json={"username": "traveler6", "password": "TravelDemo6!"},
        headers=HEADERS,
    )
    token = client.cookies.get("expedia_session")

    def unavailable(*args, **kwargs):
        raise storage.DatabaseError("Simulated persistence error")

    monkeypatch.setattr(DatabaseController, "register_user_account", unavailable)
    response = register(client)
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Account creation is unavailable. Please try again."
    }
    assert response.headers["cache-control"] == "no-store"
    assert client.cookies.get("expedia_session") == token
    assert client.get("/api/auth/me").json()["user_id"] == "U006"


def test_post_commit_journal_cleanup_failure_keeps_account_and_recovers(
    setup, monkeypatch
):
    from pathlib import Path

    journal = setup[1] / ".users.csv.registration.json"
    original_unlink = Path.unlink
    failed = False

    def interrupted_cleanup(path, *args, **kwargs):
        nonlocal failed
        if path == journal and not failed:
            failed = True
            raise OSError("Simulated cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", interrupted_cleanup)
    auth = AuthenticationController(*setup)
    user, token = auth.register("newtraveler", "New Traveler", PAYLOAD["password"])
    assert journal.exists()
    assert AuthenticationController(*setup).current_user(token) == user
    assert not journal.exists()
    assert len(DatabaseController(setup[0]).list(User)) == 7
