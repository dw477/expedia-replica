"""Entity and database-controller contracts, independent of HTTP and UI."""

import csv
import shutil
import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from backend.controllers.database import (
    DEFAULT_DATA_DIRECTORY,
    DatabaseController,
    DatabaseError,
    RecordConflictError,
    RecordNotFoundError,
    ReferenceConflictError,
)
from backend.models import Booking, Hotel, Trip, User


@pytest.fixture
def database(tmp_path):
    controller = DatabaseController(tmp_path / "expedia.sqlite3")
    assert controller.initialize() is True
    return controller


@pytest.mark.parametrize(
    ("entity", "changes"),
    [
        (
            Hotel("H999", "Test Hotel", "Boston", "MA", Decimal("19.99")),
            {"nightly_rate_usd": Decimal("20.01")},
        ),
        (User("U999", "Test Traveler"), {"display_name": "Updated Traveler"}),
        (
            Trip("T999", "H001", "Test Stay", date(2026, 10, 1), date(2026, 10, 3)),
            {"hotel_id": "H002"},
        ),
        (
            Booking(
                "B999", "U006", "T001", date(2026, 9, 17), "confirmed", Decimal("150")
            ),
            {"status": "cancelled"},
        ),
    ],
)
def test_all_models_support_persistent_crud(database, entity, changes):
    model = type(entity)
    record_id = next(iter(vars(entity).values()))
    assert database.create(entity) == entity
    reopened = DatabaseController(database.database_path)
    assert reopened.get(model, record_id) == entity
    assert entity in reopened.list(model)
    updated = replace(entity, **changes)
    assert reopened.update(updated) == updated
    assert database.get(model, record_id) == updated
    reopened.delete(model, record_id)
    with pytest.raises(RecordNotFoundError):
        database.get(model, record_id)


@pytest.mark.parametrize(
    ("model", "record_id"), [(Hotel, "H001"), (User, "U001"), (Trip, "T001")]
)
def test_referenced_parents_cannot_be_deleted(database, model, record_id):
    before = database.get(model, record_id)
    with pytest.raises(ReferenceConflictError):
        database.delete(model, record_id)
    assert database.get(model, record_id) == before


@pytest.mark.parametrize(
    "entity",
    [
        Trip("T999", "missing", "Test Stay", date(2026, 10, 1), date(2026, 10, 3)),
        Booking(
            "B999", "missing", "T001", date(2026, 9, 17), "confirmed", Decimal("150")
        ),
        Booking(
            "B999", "U006", "missing", date(2026, 9, 17), "confirmed", Decimal("150")
        ),
    ],
)
def test_missing_references_reject_creation(database, entity):
    with pytest.raises(RecordNotFoundError):
        database.create(entity)
    assert entity not in database.list(type(entity))


def test_missing_reference_update_keeps_original(database):
    trip = database.get(Trip, "T001")
    with pytest.raises(RecordNotFoundError):
        database.update(replace(trip, hotel_id="missing"))
    assert database.get(Trip, "T001") == trip


def test_failed_workflow_rolls_back_all_writes(database):
    with pytest.raises(RecordConflictError):
        with database.transaction():
            database.create(User("U999", "Test Traveler"))
            database.create(User("U001", "Duplicate ID"))
    with pytest.raises(RecordNotFoundError):
        database.get(User, "U999")
    assert database.get(User, "U001").display_name == "Demo Traveler 1"


def test_read_transaction_cannot_mutate(database):
    with pytest.raises(DatabaseError, match="Cannot write"):
        with database.transaction(write=False):
            database.delete(Booking, "B001")
    assert database.get(Booking, "B001").status == "confirmed"


def test_missing_entities_reject_update_and_delete(database):
    with pytest.raises(RecordNotFoundError):
        database.update(User("missing", "Missing"))
    with pytest.raises(RecordNotFoundError):
        database.delete(User, "missing")


@pytest.mark.parametrize(
    "rate",
    [
        Decimal("-1"),
        Decimal("0.001"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("1e20"),
        Decimal("1e999999999"),
        Decimal("1.00000000000000000000000000000001"),
        10.5,
    ],
)
def test_hotel_rejects_invalid_money(rate):
    with pytest.raises(ValueError):
        Hotel("H999", "Test Hotel", "Boston", "MA", rate)


def test_entities_reject_invalid_dates_status_and_blank_ids():
    with pytest.raises(ValueError):
        Trip("T999", "H001", "Test Stay", date(2026, 10, 3), date(2026, 10, 1))
    with pytest.raises(ValueError):
        Booking("B999", "U001", "T001", "2026-09-17", "confirmed", Decimal("150"))
    with pytest.raises(ValueError):
        Booking("B999", "U001", "T001", date(2026, 9, 17), "unknown", Decimal("150"))
    with pytest.raises(ValueError):
        User(" ", "Test Traveler")


def test_initialization_audits_existing_references(database):
    connection = sqlite3.connect(database.database_path)
    try:
        connection.execute(
            "UPDATE trips SET hotel_id = 'missing' WHERE trip_id = 'T001'"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(DatabaseError, match="invalid foreign-key references"):
        database.initialize()


@pytest.mark.parametrize("invalid_value", ["missing", "NaN", "-1", "0.001"])
def test_invalid_csv_seed_is_atomic_and_can_be_retried(tmp_path, invalid_value):
    source = tmp_path / "data"
    shutil.copytree(DEFAULT_DATA_DIRECTORY, source)
    path = source / ("trips.csv" if invalid_value == "missing" else "hotels.csv")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))
    rows[1][1 if invalid_value == "missing" else 4] = invalid_value
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        csv.writer(stream).writerows(rows)
    controller = DatabaseController(tmp_path / "invalid.sqlite3")
    with pytest.raises(DatabaseError):
        controller.initialize(source)
    assert controller.initialize() is True
    assert len(controller.list(Hotel)) == 8
    assert len(controller.list(Booking)) == 6
