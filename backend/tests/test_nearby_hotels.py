import logging
import traceback
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.controllers import geocoding, http, nearby_hotels
from backend.models.location import ZipLocation
from backend.models.nearby_hotel import NearbyHotel


def place(place_id, name, latitude, longitude, address=None):
    return {
        "properties": {
            "place_id": place_id,
            "name": name,
            "lat": latitude,
            "lon": longitude,
            "formatted": address,
        }
    }


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(geocoding, "get_geoapify_api_key", lambda: "synthetic-key")
    monkeypatch.setattr(nearby_hotels, "get_geoapify_api_key", lambda: "synthetic-key")
    original_client = httpx.Client

    def install(handler):
        def make_client(**kwargs):
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(httpx, "Client", make_client)

    return install


def test_live_search_uses_returned_zip_point_and_only_keeps_nearby_hotels(provider, caplog):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.scheme == "https"
        assert request.url.host == "api.geoapify.com"
        assert all(value == 10.0 for value in request.extensions["timeout"].values())
        if request.url.path == "/v1/geocode/search":
            assert request.url.params["postcode"] == "02108"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "postcode": "02108",
                            "country_code": "us",
                            "result_type": "postcode",
                            "lat": 40.0,
                            "lon": -77.0,
                        }
                    ]
                },
            )
        assert request.url.path == "/v2/places"
        assert dict(request.url.params) == {
            "categories": "accommodation.hotel",
            "filter": "circle:-77.0,40.0,5000",
            "limit": "500",
            "apiKey": "synthetic-key",
            "offset": "0",
        }
        return httpx.Response(
            200,
            json={
                "features": [
                    place("near", "Hotel Near", 40.01, -77.0, "1 Main St"),
                    place("center", "Hotel Center", 40.0, -77.0),
                    place("far", "Hotel Far", 40.06, -77.0),
                    place("bad", "", 40.0, -77.0),
                ]
            },
        )

    provider(respond)
    with caplog.at_level(logging.INFO):
        hotels = nearby_hotels.search_hotels_near_zip("02108")

    assert len(requests) == 2
    assert [hotel.place_id for hotel in hotels] == ["center", "near"]
    assert hotels[0].distance_m == 0
    assert hotels[1].distance_m == 1112
    assert hotels[1].address == "1 Main St"
    assert "synthetic-key" not in caplog.text
    with pytest.raises(FrozenInstanceError):
        hotels[0].name = "changed"


def test_full_pages_are_fetched_and_duplicate_ids_are_removed(provider, monkeypatch):
    monkeypatch.setattr(nearby_hotels, "lookup_zip", Mock(return_value=ZipLocation("16802", "us", 40.0, -77.0)))
    monkeypatch.setattr(nearby_hotels, "_PAGE_SIZE", 2)
    offsets = []

    def respond(request):
        offsets.append(request.url.params["offset"])
        features = (
            [place("first", "First", 40.0, -77.0), place("second", "Second", 40.01, -77.0)]
            if request.url.params["offset"] == "0"
            else [place("first", "First", 40.0, -77.0)]
        )
        return httpx.Response(200, json={"features": features})

    provider(respond)
    hotels = nearby_hotels.search_hotels_near_zip("16802")

    assert offsets == ["0", "2"]
    assert [hotel.place_id for hotel in hotels] == ["first", "second"]


def test_page_limit_fails_instead_of_returning_partial_results(provider, monkeypatch):
    monkeypatch.setattr(
        nearby_hotels,
        "lookup_zip",
        lambda _: ZipLocation("16802", "us", 40.0, -77.0),
    )
    monkeypatch.setattr(nearby_hotels, "_PAGE_SIZE", 1)
    monkeypatch.setattr(nearby_hotels, "_MAX_PAGES", 2)
    provider(lambda _: httpx.Response(200, json={"features": [place("same", "Same", 40.0, -77.0)]}))

    with pytest.raises(nearby_hotels.NearbyHotelLookupError, match="limit"):
        nearby_hotels.search_hotels_near_zip("16802")


@pytest.mark.parametrize("body", ["not JSON", "null", "[]", "{}", '{"features":null}'])
def test_invalid_provider_envelopes_fail_safely(provider, monkeypatch, body):
    monkeypatch.setattr(nearby_hotels, "lookup_zip", lambda _: ZipLocation("16802", "us", 40.0, -77.0))
    provider(lambda _: httpx.Response(200, text=body))
    with pytest.raises(nearby_hotels.NearbyHotelLookupError):
        nearby_hotels.search_hotels_near_zip("16802")


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_provider_http_errors_never_expose_the_key(provider, monkeypatch, status, caplog):
    monkeypatch.setattr(nearby_hotels, "lookup_zip", lambda _: ZipLocation("16802", "us", 40.0, -77.0))
    provider(lambda _: httpx.Response(status, text="synthetic-key"))
    with caplog.at_level(logging.INFO), pytest.raises(nearby_hotels.NearbyHotelLookupError) as error:
        nearby_hotels.search_hotels_near_zip("16802")
    diagnostic = "".join(traceback.format_exception(error.value)) + caplog.text
    assert "synthetic-key" not in diagnostic
    assert "api.geoapify.com" not in diagnostic


def test_transport_error_never_exposes_the_key(provider, monkeypatch):
    monkeypatch.setattr(
        nearby_hotels,
        "lookup_zip",
        lambda _: ZipLocation("16802", "us", 40.0, -77.0),
    )

    def fail(request):
        raise httpx.ReadTimeout(str(request.url), request=request)

    provider(fail)
    with pytest.raises(nearby_hotels.NearbyHotelLookupError) as error:
        nearby_hotels.search_hotels_near_zip("16802")
    diagnostic = "".join(traceback.format_exception(error.value))
    assert "synthetic-key" not in diagnostic
    assert "api.geoapify.com" not in diagnostic


def test_unresolved_zip_does_not_call_places(provider, monkeypatch):
    monkeypatch.setattr(nearby_hotels, "lookup_zip", lambda _: None)
    provider(lambda _: pytest.fail("No place request should be made"))
    assert nearby_hotels.search_hotels_near_zip("16802") is None


def test_missing_key_does_not_call_places(provider, monkeypatch):
    monkeypatch.setattr(nearby_hotels, "lookup_zip", lambda _: ZipLocation("16802", "us", 40.0, -77.0))
    monkeypatch.setattr(nearby_hotels, "get_geoapify_api_key", lambda: None)
    provider(lambda _: pytest.fail("No place request should be made"))
    with pytest.raises(nearby_hotels.NearbyHotelConfigurationError):
        nearby_hotels.search_hotels_near_zip("16802")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(http, "geoapify_key_is_configured", lambda: False)
    with TestClient(http.create_app(tmp_path / "test.sqlite3")) as test_client:
        yield test_client


def test_http_returns_live_hotel_rows_without_bookable_fields(client, monkeypatch):
    search = Mock(return_value=[NearbyHotel("geo-1", "Hotel One", None, 40.0, -77.0, 123)])
    monkeypatch.setattr(http, "search_hotels_near_zip", search)

    response = client.get("/api/zip-hotels", params={"postcode": "02108"})

    search.assert_called_once_with("02108")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == [
        {
            "place_id": "geo-1",
            "name": "Hotel One",
            "address": None,
            "latitude": 40.0,
            "longitude": -77.0,
            "distance_m": 123,
        }
    ]


def test_http_empty_hotel_list_is_success(client, monkeypatch):
    monkeypatch.setattr(http, "search_hotels_near_zip", lambda _: [])
    response = client.get("/api/zip-hotels", params={"postcode": "16802"})
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("postcode", [None, "", "1234", "123456", "abcde", "１２３４５", " 16802"])
def test_http_rejects_bad_zips_before_lookup(client, monkeypatch, postcode):
    search = Mock()
    monkeypatch.setattr(http, "search_hotels_near_zip", search)
    response = client.get("/api/zip-hotels", params={} if postcode is None else {"postcode": postcode})
    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    search.assert_not_called()


@pytest.mark.parametrize(
    ("result", "error", "status"),
    [
        (None, None, 404),
        (None, geocoding.ZipConfigurationError("synthetic-key"), 503),
        (None, nearby_hotels.NearbyHotelConfigurationError("synthetic-key"), 503),
        (None, geocoding.ZipLookupError("synthetic-key"), 502),
        (None, nearby_hotels.NearbyHotelLookupError("synthetic-key"), 502),
    ],
)
def test_http_errors_are_safe(client, monkeypatch, result, error, status):
    monkeypatch.setattr(http, "search_hotels_near_zip", Mock(return_value=result, side_effect=error))
    response = client.get("/api/zip-hotels", params={"postcode": "16802"})
    assert response.status_code == status
    assert response.headers["Cache-Control"] == "no-store"
    assert "synthetic-key" not in response.text
    if status == 404:
        assert response.json() == {"detail": "No matching U.S. location was found for ZIP 16802."}


def test_openapi_exposes_hotel_row_contract(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/zip-hotels"]["get"]
    assert set(operation["responses"]) == {"200", "404", "422", "502", "503"}
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "items": {"$ref": "#/components/schemas/NearbyHotelResponse"},
        "title": "Response Zip Hotels Api Zip Hotels Get",
        "type": "array",
    }
    parameter, = operation["parameters"]
    assert parameter["name"] == "postcode"
    assert parameter["required"] is True
    assert parameter["schema"]["pattern"] == "^[0-9]{5}$"
    assert set(schema["components"]["schemas"]["NearbyHotelResponse"]["properties"]) == {
        "place_id", "name", "address", "latitude", "longitude", "distance_m"
    }
