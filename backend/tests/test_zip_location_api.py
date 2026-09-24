from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.controllers import http
from backend.controllers.geocoding import ZipConfigurationError, ZipLookupError
from backend.models.location import ZipLocation


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(http, "geoapify_key_is_configured", lambda: False)
    with TestClient(http.create_app(tmp_path / "test.sqlite3")) as client:
        yield client


@pytest.mark.parametrize("locality", ["University Park", None])
def test_demo_returns_only_location_and_always_looks_up_16802(client, monkeypatch, locality):
    lookup = Mock(return_value=ZipLocation("16802", "us", 40.8, -77.86, locality))
    monkeypatch.setattr(http, "lookup_zip", lookup)

    response = client.get("/api/demo/zip-location", params={"postcode": "99999"})

    lookup.assert_called_once_with("16802")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "postcode": "16802",
        "country_code": "us",
        "latitude": 40.8,
        "longitude": -77.86,
        "locality": locality,
    }


@pytest.mark.parametrize(
    ("error_type", "status", "detail"),
    [
        (
            ZipConfigurationError,
            503,
            "Geoapify configuration is unavailable. Configure GEOAPIFY_API_KEY and restart the backend.",
        ),
        (ZipLookupError, 502, "The location provider request failed."),
    ],
)
def test_demo_failure_messages_are_fixed_and_safe(
    client, monkeypatch, error_type, status, detail, caplog
):
    # Even an accidentally unsanitized controller message must not reach clients.
    lookup = Mock(side_effect=error_type("https://example.com?apiKey=synthetic-secret"))
    monkeypatch.setattr(http, "lookup_zip", lookup)

    response = client.get("/api/demo/zip-location")

    lookup.assert_called_once_with("16802")
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert response.headers["Cache-Control"] == "no-store"
    assert "synthetic-secret" not in response.text + caplog.text
    assert "https://example.com" not in response.text + caplog.text


def test_demo_unresolved_zip_is_404(client, monkeypatch):
    lookup = Mock(return_value=None)
    monkeypatch.setattr(http, "lookup_zip", lookup)

    response = client.get("/api/demo/zip-location")

    lookup.assert_called_once_with("16802")
    assert response.status_code == 404
    assert response.json() == {
        "detail": "No matching U.S. location was found for ZIP 16802."
    }
    assert response.headers["Cache-Control"] == "no-store"


def test_demo_openapi_contract_preserves_existing_routes(client):
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/api/demo/zip-location"]["get"]["responses"]
    assert set(responses) == {"200", "404", "502", "503"}
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ZipLocationResponse"
    }
    assert set(schema["components"]["schemas"]["ZipLocationResponse"]["properties"]) == {
        "postcode", "country_code", "latitude", "longitude", "locality"
    }
    for path in ("/api/health", "/api/stays", "/api/users", "/api/bookings", "/api/auth/me"):
        assert "get" in schema["paths"][path]


@pytest.mark.parametrize("postcode", ["16802", "02108", "90210"])
def test_entered_zip_reaches_controller_and_returns_same_schema(client, monkeypatch, postcode):
    lookup = Mock(return_value=ZipLocation(postcode, "us", 40.8, -77.86, None))
    monkeypatch.setattr(http, "lookup_zip", lookup)

    response = client.get("/api/zip-location", params={"postcode": postcode})

    lookup.assert_called_once_with(postcode)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "postcode": postcode,
        "country_code": "us",
        "latitude": 40.8,
        "longitude": -77.86,
        "locality": None,
    }


@pytest.mark.parametrize(
    "postcode", [None, "", "1234", "123456", "abcde", "１２３４５", " 16802", "16802\n", "16802-1234"]
)
def test_invalid_or_missing_zip_is_rejected_before_provider(client, monkeypatch, postcode):
    lookup = Mock()
    monkeypatch.setattr(http, "lookup_zip", lookup)
    params = {} if postcode is None else {"postcode": postcode}

    response = client.get("/api/zip-location", params=params)

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    lookup.assert_not_called()


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (None, 404, "No matching U.S. location was found for ZIP 02108."),
        (ZipLookupError("synthetic-secret"), 502, "The location provider request failed."),
        (
            ZipConfigurationError("synthetic-secret"),
            503,
            "Geoapify configuration is unavailable. Configure GEOAPIFY_API_KEY and restart the backend.",
        ),
    ],
)
def test_entered_zip_errors_are_safe_and_not_cached(client, monkeypatch, error, status, detail):
    lookup = Mock(return_value=None, side_effect=error)
    monkeypatch.setattr(http, "lookup_zip", lookup)

    response = client.get("/api/zip-location", params={"postcode": "02108"})

    lookup.assert_called_once_with("02108")
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert response.headers["Cache-Control"] == "no-store"


def test_entered_zip_openapi_contract(client):
    operation = client.get("/openapi.json").json()["paths"]["/api/zip-location"]["get"]
    assert set(operation["responses"]) == {"200", "404", "422", "502", "503"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ZipLocationResponse"
    }
    parameter, = operation["parameters"]
    assert parameter["name"] == "postcode"
    assert parameter["in"] == "query"
    assert parameter["required"] is True
    assert parameter["schema"]["type"] == "string"
    assert parameter["schema"]["pattern"] == "^[0-9]{5}$"
    assert parameter["schema"]["minLength"] == parameter["schema"]["maxLength"] == 5
