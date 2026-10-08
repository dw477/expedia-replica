"""Real SQLite guard, prompt, two-request flow, and durable audit tests."""

import json
import re
from dataclasses import FrozenInstanceError
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.controllers import chat, chat_prompt, database as storage, http
from backend.controllers.database import (
    DatabaseController, DatabaseError, HotelQueryRejectedError, HotelQueryTimeoutError,
    connect_database,
)
from backend.controllers.local_hotels import LocalHotelsController
from backend.models.chat import ChatMessage
from backend.models.conversation import ConversationRecord
from backend.models.hotel_query import HotelQuery, HotelQueryResult
from backend.models.local_hotel import SavedHotel, HotelZipAssociation
from backend.models.location import ZipLocation

HEADERS = {"X-Requested-With": "XMLHttpRequest"}
QUESTION = "Cheapest hotel in ZIP 02108 on October 10, 2026?"
SQL = """SELECT h.hotel_id, h.name, z.postcode, n.stay_date,
       n.nightly_rate_cents / 100.0 AS nightly_rate_usd, n.rooms_available
FROM saved_hotels h
JOIN saved_hotel_zip_locations z ON h.hotel_id = z.hotel_id
JOIN demo_hotel_nights n ON h.hotel_id = n.hotel_id
WHERE z.postcode = '02108' AND n.stay_date = '2026-10-10'
  AND n.rooms_available >= 1
ORDER BY n.nightly_rate_cents, h.hotel_id"""


@pytest.fixture
def database(tmp_path):
    db = DatabaseController(tmp_path / "hotel-assistant.sqlite3")
    db.initialize()
    local = LocalHotelsController(db.database_path)
    for identifier, postcode in (("cheap", "02108"), ("costly", "02108"), ("other", "16802")):
        local.save(SavedHotel(identifier, identifier.title(), None, 0, 0),
                   HotelZipAssociation(identifier, ZipLocation(postcode, "us", 0, 0), 0))
    with connect_database(db.database_path) as connection:
        connection.execute("UPDATE demo_hotel_nights SET nightly_rate_cents=12345 WHERE hotel_id='costly'")
    return db


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(chat, "get_gemini_api_key", lambda: "synthetic-test-key")
    monkeypatch.setattr(chat, "get_gemini_model", lambda: "synthetic-model")
    client = MagicMock()
    client.__enter__.return_value = client
    client.interactions.create.side_effect = [
        SimpleNamespace(status="completed", output_text=SQL),
        SimpleNamespace(status="completed", output_text=json.dumps({"reply": "Cheap is $100.00 with 20 rooms. Simulated classroom data.", "suggestions": ["Compare rooms at Cheap and Costly in ZIP 02108", "Which hotels have two rooms on October 10, 2026?"]})),
    ]
    monkeypatch.setattr(chat.genai, "Client", lambda **_: client)
    return client


def test_query_and_records_are_immutable_and_validated():
    query = HotelQuery(" SELECT hotel_id FROM saved_hotels; ")
    with pytest.raises(FrozenInstanceError):
        query.sql = "DELETE FROM saved_hotels"
    for value in ("", "x" * 8001, "SELECT\x00"):
        with pytest.raises(ValueError):
            HotelQuery(value)
    for rows in (((b"binary",),), ((float("inf"),),), ((1, 2),)):
        with pytest.raises(ValueError):
            HotelQueryResult(("value",), rows)
    with pytest.raises(ValueError):
        ConversationRecord(str(uuid4()), str(uuid4()), 0, "user", "sql", "generated_sql")


def test_prompt_matches_schema_and_two_joins(database):
    prompt = chat_prompt.load_hotel_assistant_prompt()
    with connect_database(database.database_path) as connection:
        for table in ("saved_hotels", "saved_hotel_zip_locations", "demo_hotel_nights"):
            for row in connection.execute(f"PRAGMA table_info({table})"):
                assert f"`{row['name']}`" in prompt
    examples = re.findall(r"```sql\n(.*?)\n```", prompt, re.S)
    assert len(examples) == 2
    assert len(database.execute_hotel_query(HotelQuery(examples[0])).rows) == 2
    stays = database.execute_hotel_query(HotelQuery(examples[1]))
    assert [row[-1] for row in stays.rows] == [200.0, 246.9]
    assert "availability is unknown" in prompt


def test_join_filters_price_conversion_and_missing_dates(database):
    result = database.execute_hotel_query(HotelQuery(SQL + ";"))
    assert result.rows == (
        ("cheap", "Cheap", "02108", "2026-10-10", 100.0, 20),
        ("costly", "Costly", "02108", "2026-10-10", 123.45, 20),
    )
    with connect_database(database.database_path) as connection:
        connection.execute("UPDATE demo_hotel_nights SET rooms_available=0 WHERE hotel_id='cheap'")
    assert len(database.execute_hotel_query(HotelQuery(SQL)).rows) == 1
    assert database.execute_hotel_query(HotelQuery(SQL.replace("2026-10-10", "2026-10-15"))).rows == ()
    unknown = database.execute_hotel_query(HotelQuery("""
        SELECT h.hotel_id, n.rooms_available FROM saved_hotels h
        JOIN saved_hotel_zip_locations z ON h.hotel_id = z.hotel_id
        LEFT JOIN demo_hotel_nights n ON h.hotel_id = n.hotel_id AND n.stay_date = '2026-10-15'
        WHERE z.postcode = '02108' ORDER BY h.hotel_id
    """))
    assert unknown.rows == (("cheap", None), ("costly", None))


def test_stay_requires_every_date_and_room_count(database):
    prompt = chat_prompt.load_hotel_assistant_prompt()
    sql = re.findall(r"```sql\n(.*?)\n```", prompt, re.S)[1]
    with connect_database(database.database_path) as connection:
        connection.execute("DELETE FROM demo_hotel_nights WHERE hotel_id='cheap' AND stay_date='2026-10-11'")
        connection.execute("UPDATE demo_hotel_nights SET rooms_available=0 WHERE hotel_id='costly' AND stay_date='2026-10-11'")
    assert database.execute_hotel_query(HotelQuery(sql)).rows == ()


@pytest.mark.parametrize("sql", [
    "DELETE FROM saved_hotels", "UPDATE demo_hotel_nights SET rooms_available=0",
    "INSERT INTO saved_hotels(hotel_id) VALUES ('fake')", "DROP TABLE saved_hotels",
    "PRAGMA table_info(users)", "ATTACH DATABASE ':memory:' AS other",
    "SELECT * FROM users", "SELECT * FROM auth_sessions", "SELECT * FROM bookings",
    "SELECT * FROM conversation_history", "SELECT * FROM search_history",
    "SELECT * FROM sqlite_master", "SELECT * FROM pragma_table_info('users')",
    "SELECT load_extension('unsafe') FROM saved_hotels",
    "SELECT randomblob(1000000000) FROM saved_hotels",
    "SELECT * FROM saved_hotels; DELETE FROM saved_hotels",
    "SELECT * FROM saved_hotels UNION SELECT * FROM users",
    "SELECT (SELECT display_name FROM users LIMIT 1) FROM saved_hotels",
    "WITH private AS (SELECT * FROM users) SELECT * FROM private",
    "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT * FROM r",
    "SELECT hotel_id FROM saved_hotels) AS x LIMIT 999 /*",
    "SELECT X'ff' FROM saved_hotels", "SELECT 1e999 FROM saved_hotels",
])
def test_guard_denies_writes_private_reads_and_bypasses(database, sql):
    before = database.list_saved_hotel_ids()
    with pytest.raises(HotelQueryRejectedError):
        database.execute_hotel_query(HotelQuery(sql))
    assert database.list_saved_hotel_ids() == before
    assert database.execute_hotel_query(HotelQuery(SQL)).rows[0][-1] == 20


def test_nonrecursive_cte_and_comments_are_parsed_by_sqlite(database):
    query = HotelQuery("WITH hotels AS (SELECT hotel_id FROM saved_hotels) SELECT * FROM hotels -- hi")
    assert len(database.execute_hotel_query(query).rows) == 3


def test_backend_limits_rows_and_reports_truncation(database):
    query = HotelQuery("SELECT a.hotel_id FROM demo_hotel_nights a CROSS JOIN demo_hotel_nights b")
    result = database.execute_hotel_query(query)
    assert len(result.rows) == 100 and result.truncated is True


def test_backend_limits_serialized_result_size(database):
    with connect_database(database.database_path) as connection:
        connection.execute("UPDATE saved_hotels SET name=?", ("x" * 8000,))
    result = database.execute_hotel_query(HotelQuery("SELECT h.name FROM saved_hotels h CROSS JOIN demo_hotel_nights n"))
    assert len(result.rows) < 5 and result.truncated is True


def test_expensive_query_times_out_and_next_query_works(database, monkeypatch):
    monkeypatch.setattr(storage, "HOTEL_QUERY_TIMEOUT_SECONDS", 0.01)
    query = HotelQuery("""SELECT sum(a.rooms_available * b.rooms_available)
        FROM demo_hotel_nights a CROSS JOIN demo_hotel_nights b
        CROSS JOIN demo_hotel_nights c CROSS JOIN demo_hotel_nights d
        CROSS JOIN demo_hotel_nights e CROSS JOIN demo_hotel_nights f""")
    with pytest.raises(HotelQueryTimeoutError):
        database.execute_hotel_query(query)
    assert len(database.execute_hotel_query(HotelQuery(SQL)).rows) == 2


def test_two_requests_and_logs_are_committed_as_each_step_occurs(database, provider):
    identifier = str(uuid4())
    calls = []
    responses = iter(provider.interactions.create.side_effect)

    def respond(**options):
        calls.append(options)
        records = database.list_conversation_records(identifier)
        if len(calls) == 1:
            assert [r.role for r in records] == ["user"]
        else:
            assert [r.record_type for r in records] == ["message", "generated_sql", "executed_sql", "result_summary"]
            context = json.loads(options["input"][-1]["content"][0]["text"])
            assert context["question"] == QUESTION
            assert context["rows"][0] == ["cheap", "Cheap", "02108", "2026-10-10", 100.0, 20]
        assert "saved_hotel_zip_locations" in options["system_instruction"]
        assert options["store"] is False
        return next(responses)

    provider.interactions.create.side_effect = respond
    result = chat.reply_to_chat((ChatMessage("user", QUESTION),), database_path=database.database_path, conversation_id=identifier)
    assert result.reply.startswith("Cheap") and len(calls) == 2
    records = database.list_conversation_records(identifier)
    assert [r.role for r in records] == ["user", "system", "system", "system", "assistant"]
    assert records[1].content == SQL
    assert records[2].content == HotelQuery(SQL).limited_sql
    assert json.loads(records[3].content)["row_count"] == 2
    assert all(r.conversation_id == identifier and r.timestamp > 0 for r in records)
    assert len({r.message_id for r in records}) == 5
    assert DatabaseController(database.database_path).initialize() is False
    assert DatabaseController(database.database_path).list_conversation_records(identifier) == records


def test_empty_rows_still_reach_answer_request(database, provider):
    provider.interactions.create.side_effect = [
        SimpleNamespace(status="completed", output_text=SQL.replace("02108", "00000")),
        SimpleNamespace(status="completed", output_text=json.dumps({"reply": "No saved records matched. Simulated classroom data.", "suggestions": ["Which saved ZIPs can I search?"]})),
    ]
    reply = chat.reply_to_chat((ChatMessage("user", QUESTION),), database_path=database.database_path)
    context = json.loads(provider.interactions.create.call_args.kwargs["input"][-1]["content"][0]["text"])
    assert context["rows"] == [] and "No saved records" in reply.reply
    assert "empty results" in provider.interactions.create.call_args.kwargs["system_instruction"]


@pytest.mark.parametrize("stage", ["sql_generation", "sql_validation", "hotel_query", "answer_generation"])
def test_failure_retains_prior_steps_and_saves_safe_error(database, provider, stage, monkeypatch):
    identifier = str(uuid4())
    private_error = httpx.ReadTimeout("secret-key and provider URL")
    if stage == "sql_generation":
        provider.interactions.create.side_effect = private_error
    elif stage == "sql_validation":
        provider.interactions.create.side_effect = [SimpleNamespace(status="completed", output_text="SELECT * FROM auth_sessions")]
    elif stage == "hotel_query":
        def timeout(*_):
            raise HotelQueryTimeoutError("private SQLite failure")
        monkeypatch.setattr(DatabaseController, "execute_hotel_query", timeout)
    else:
        provider.interactions.create.side_effect = [SimpleNamespace(status="completed", output_text=SQL), private_error]
    with pytest.raises(chat.ChatProviderError):
        chat.reply_to_chat((ChatMessage("user", QUESTION),), database_path=database.database_path, conversation_id=identifier)
    records = database.list_conversation_records(identifier)
    assert records[0].role == "user" and records[-1].record_type == "error"
    assert json.loads(records[-1].content)["stage"] == stage
    assert "secret-key" not in records[-1].content
    assert all(r.role != "assistant" for r in records)
    if stage == "sql_validation":
        assert all(r.record_type != "executed_sql" for r in records)
        assert provider.interactions.create.call_count == 1
    if stage == "hotel_query":
        assert records[-2].record_type == "executed_sql"
        assert json.loads(records[-1].content)["code"] == "query_timeout"
        assert provider.interactions.create.call_count == 1


def test_http_groups_turns_without_reinserting_replayed_history(database, provider):
    identifier = str(uuid4())
    provider.interactions.create.side_effect = list(provider.interactions.create.side_effect) * 2
    with TestClient(http.create_app(database.database_path)) as client:
        payload = {"messages": [{"role": "user", "content": QUESTION}], "conversation_id": identifier}
        first = client.post("/api/chat", json=payload, headers=HEADERS)
        assert first.status_code == 200 and set(first.json()) == {"reply", "suggestions"}
        payload["messages"] += [{"role": "assistant", "content": first.json()["reply"]}, {"role": "user", "content": "What about two rooms?"}]
        assert client.post("/api/chat", json=payload, headers=HEADERS).status_code == 200
        latest_context = json.loads(provider.interactions.create.call_args.kwargs["input"][-1]["content"][0]["text"])
        assert latest_context["question"] == "What about two rooms?"
        for invalid_id in ("not-a-uuid", "02108", str(uuid4()).replace("-", "") + "bad"):
            assert client.post("/api/chat", json={**payload, "conversation_id": invalid_id}, headers=HEADERS).status_code == 422
    assert [r.content for r in database.list_conversation_records(identifier) if r.role == "user"] == [QUESTION, "What about two rooms?"]


def test_prompt_loaded_once_at_startup_and_reloaded_after_restart(database, provider, monkeypatch, tmp_path):
    path = tmp_path / "hotel-assistant.md"
    path.write_text("Original hotel instructions", encoding="utf-8")
    monkeypatch.setattr(chat_prompt, "HOTEL_ASSISTANT_PROMPT_PATH", path)
    payload = {"messages": [{"role": "user", "content": QUESTION}]}
    provider.interactions.create.side_effect = list(provider.interactions.create.side_effect) * 3
    with TestClient(http.create_app(database.database_path)) as client:
        path.write_text("Updated hotel instructions", encoding="utf-8")
        assert client.post("/api/chat", json=payload, headers=HEADERS).status_code == 200
        assert "Original hotel instructions" in provider.interactions.create.call_args.kwargs["system_instruction"]
    with TestClient(http.create_app(database.database_path)) as client:
        assert client.post("/api/chat", json=payload, headers=HEADERS).status_code == 200
        assert "Updated hotel instructions" in provider.interactions.create.call_args.kwargs["system_instruction"]


def test_missing_prompt_fails_startup_with_safe_error(database, monkeypatch, tmp_path):
    monkeypatch.setattr(chat_prompt, "HOTEL_ASSISTANT_PROMPT_PATH", tmp_path / "missing.md")
    with pytest.raises(ValueError, match="instructions could not be loaded"):
        with TestClient(http.create_app(database.database_path)):
            pytest.fail("Startup should fail")


def test_storage_error_is_sanitized_and_stops_provider(database, provider, monkeypatch):
    def fail(*_):
        raise DatabaseError("secret path")
    monkeypatch.setattr(DatabaseController, "append_conversation_record", fail)
    with TestClient(http.create_app(database.database_path)) as client:
        response = client.post("/api/chat", json={"messages": [{"role": "user", "content": QUESTION}]}, headers=HEADERS)
    assert response.status_code == 500 and "secret path" not in response.text
    assert response.headers["cache-control"] == "no-store"
    provider.interactions.create.assert_not_called()
