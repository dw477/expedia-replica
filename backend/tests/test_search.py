from decimal import Decimal

import pytest

from backend.search import format_availability_table, search_available_stays


@pytest.mark.parametrize(
    "hotel_name", ["Harbor Lantern Hotel", "harbor lantern hotel", "  LANTERN  "]
)
def test_search_matches_hotel_name_without_case_or_surrounding_whitespace(
    hotel_name, tmp_path
):
    stays = search_available_stays(hotel_name, tmp_path / "expedia.sqlite3")

    assert [stay.trip_id for stay in stays] == ["T001", "T009"]


def test_search_calculates_nights_and_stay_price(tmp_path):
    first_stay = search_available_stays(
        "Harbor Lantern Hotel", tmp_path / "expedia.sqlite3"
    )[0]

    assert first_stay.hotel_name == "Harbor Lantern Hotel"
    assert first_stay.nights == 2
    assert first_stay.nightly_rate_usd == Decimal("150")
    assert first_stay.stay_price_usd == Decimal("300")


def test_table_has_clear_availability_labels_and_values(tmp_path):
    stays = search_available_stays("Valley Trail", tmp_path / "expedia.sqlite3")

    table = format_availability_table("Valley Trail", stays)

    assert "Available hotel stays matching Valley Trail" in table
    assert "Hotel" in table
    assert "Check-in" in table
    assert "Check-out" in table
    assert "Nightly rate" in table
    assert "Stay price" in table
    assert "Valley Trail Inn" in table
    assert "$200.00" in table


def test_table_has_clear_message_when_there_are_no_matches(tmp_path):
    stays = search_available_stays("Atlantis Hotel", tmp_path / "expedia.sqlite3")

    assert stays == []
    assert (
        format_availability_table("Atlantis Hotel", stays)
        == "No available hotel stays found for Atlantis Hotel."
    )


def test_empty_hotel_name_has_clear_message(tmp_path):
    stays = search_available_stays("   ", tmp_path / "expedia.sqlite3")

    assert stays == []
    assert "No hotel name was provided" in format_availability_table("   ", stays)
