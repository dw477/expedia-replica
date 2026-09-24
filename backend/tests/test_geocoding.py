import json
import logging
import traceback
from dataclasses import FrozenInstanceError, asdict

import httpx
import pytest

from backend.controllers import geocoding
from backend.models.location import ZipLocation


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(geocoding, "get_geoapify_api_key", lambda: "synthetic-key")
    original_client = httpx.Client

    def install(handler):
        def make_client(**kwargs):
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(geocoding.httpx, "Client", make_client)

    return install


@pytest.fixture
def match():
    return {
        "postcode": "16802",
        "country_code": "us",
        "result_type": "postcode",
        "lat": 40.8,
        "lon": -77.86,
        "city": " University Park ",
    }


def test_matching_location_and_private_request(provider, match, caplog):
    def respond(request):
        assert request.url.path == "/v1/geocode/search"
        assert request.url.host == "api.geoapify.com"
        assert request.url.scheme == "https"
        assert dict(request.url.params) == {
            "postcode": "16802",
            "type": "postcode",
            "filter": "countrycode:us",
            "format": "json",
            "apiKey": "synthetic-key",
        }
        assert all(value == 10.0 for value in request.extensions["timeout"].values())
        return httpx.Response(200, json={"results": [match]})

    provider(respond)
    with caplog.at_level(logging.DEBUG):
        location = geocoding.lookup_zip("16802")
    assert asdict(location) == {
        "postcode": "16802",
        "country_code": "us",
        "latitude": 40.8,
        "longitude": -77.86,
        "locality": "University Park",
    }
    assert "synthetic-key" not in caplog.text
    assert "api.geoapify.com" not in caplog.text
    with pytest.raises(FrozenInstanceError):
        location.postcode = "00000"


@pytest.mark.parametrize(
    "changes",
    [
        {"postcode": "16801"},
        {"postcode": 16802},
        {"postcode": None},
        {"country_code": "ca"},
        {"country_code": None},
        {"result_type": "city"},
        {"lat": None},
        {"lat": 91},
        {"lon": -181},
        {"lat": True},
        {"lon": "-77.86"},
    ],
)
def test_mismatched_or_invalid_location_is_unresolved(provider, match, changes):
    provider(lambda _: httpx.Response(200, json={"results": [match | changes]}))
    assert geocoding.lookup_zip("16802") is None


def test_empty_results_are_unresolved(provider):
    provider(lambda _: httpx.Response(200, json={"results": []}))
    assert geocoding.lookup_zip("16802") is None


def test_skips_mismatch_and_allows_missing_locality(provider, match):
    match.pop("city")
    match["country_code"] = "US"
    provider(
        lambda _: httpx.Response(
            200, json={"results": [None, match | {"postcode": "16801"}, match]}
        )
    )
    assert geocoding.lookup_zip("16802").locality is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_coordinates_are_rejected(provider, match, value):
    # JSON may contain non-standard numeric constants; validate after decoding.
    provider(
        lambda _: httpx.Response(
            200, content=json.dumps({"results": [match | {"lat": value}]})
        )
    )
    assert geocoding.lookup_zip("16802") is None


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_provider_http_failures_are_sanitized(provider, status, caplog):
    provider(
        lambda _: httpx.Response(
            status, text="synthetic-key", headers={"Location": "https://example.com"}
        )
    )
    with caplog.at_level(logging.INFO), pytest.raises(geocoding.ZipLookupError) as error:
        geocoding.lookup_zip("16802")
    diagnostic = "".join(traceback.format_exception(error.value)) + caplog.text
    assert "synthetic-key" not in diagnostic
    assert "api.geoapify.com" not in diagnostic
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_failures_are_sanitized(provider, error_type):
    def fail(request):
        raise error_type(str(request.url), request=request)

    provider(fail)
    with pytest.raises(geocoding.ZipLookupError) as error:
        geocoding.lookup_zip("16802")
    diagnostic = "".join(traceback.format_exception(error.value))
    assert "synthetic-key" not in diagnostic
    assert "api.geoapify.com" not in diagnostic


@pytest.mark.parametrize("body", ["not JSON", "null", "[]", "{}", '{"results":null}'])
def test_malformed_provider_responses_are_failures(provider, body):
    provider(lambda _: httpx.Response(200, text=body))
    with pytest.raises(geocoding.ZipLookupError):
        geocoding.lookup_zip("16802")


def test_missing_key_makes_no_request(provider, monkeypatch):
    provider(lambda _: pytest.fail("No request should be sent without a key"))
    monkeypatch.setattr(geocoding, "get_geoapify_api_key", lambda: None)
    with pytest.raises(geocoding.ZipConfigurationError, match="not configured"):
        geocoding.lookup_zip("16802")


@pytest.mark.parametrize(
    "postcode", [16802, None, "1680", "16802-1234", " 16802", "１６８０２"]
)
def test_invalid_input_makes_no_request(provider, postcode):
    provider(lambda _: pytest.fail("No request should be sent for invalid input"))
    with pytest.raises(ValueError):
        geocoding.lookup_zip(postcode)


def test_location_does_not_require_hotel_fields():
    assert ZipLocation("16802", "us", 40.8, -77.86).locality is None


def test_leading_zero_zip_is_preserved(provider, match):
    def respond(request):
        assert request.url.params["postcode"] == "01234"
        return httpx.Response(200, json={"results": [match | {"postcode": "01234"}]})

    provider(respond)
    assert geocoding.lookup_zip("01234").postcode == "01234"


def test_configuration_read_errors_are_sanitized(provider, monkeypatch):
    def fail():
        raise OSError("synthetic-key")

    provider(lambda _: pytest.fail("No request should be sent without configuration"))
    monkeypatch.setattr(geocoding, "get_geoapify_api_key", fail)
    with pytest.raises(geocoding.ZipConfigurationError) as error:
        geocoding.lookup_zip("16802")
    assert "synthetic-key" not in "".join(traceback.format_exception(error.value))
