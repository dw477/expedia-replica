"""Two-stage hotel assistant with guarded reads and durable workflow records."""

import json
import logging
import time
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

import httpx
from google import genai

from backend.controllers.configuration import get_gemini_api_key, get_gemini_model
from backend.controllers.chat_prompt import load_hotel_assistant_prompt
from backend.controllers.database import (
    DEFAULT_DATABASE_PATH,
    DatabaseController,
    DatabaseError,
    HotelQueryRejectedError,
    HotelQueryTimeoutError,
)
from backend.models.chat import MAX_CHAT_CHARACTERS, ChatConversation, ChatMessage, ChatReply
from backend.models.contracts import ChatResponse
from backend.models.conversation import ConversationRecord, validate_conversation_id
from backend.models.hotel_query import HotelQuery

CHAT_TIMEOUT_SECONDS = 30
logger = logging.getLogger(__name__)
SQL_INSTRUCTION = "Follow the FIRST REQUEST instructions. Return only one hotel SELECT query."
ANSWER_INSTRUCTION = (
    "Follow the SECOND REQUEST instructions. Answer the original question using "
    "only the retrieved rows. Explicitly acknowledge empty results, unknown "
    "availability for missing dates, and simulated classroom data. Return JSON "
    "with a plain-text reply and up to three short, distinct suggested questions "
    "based on the current question and the answer you just wrote."
)


class ChatProviderError(Exception):
    """The provider failed or did not return a usable text reply."""


class ChatConfigurationError(ChatProviderError):
    """Backend-only LLM credentials are unavailable."""


class ChatUnavailableError(ChatProviderError):
    """The provider reported a temporary service outage."""


class ChatTimeoutError(ChatProviderError):
    """The provider did not respond within the request timeout."""


class ChatQueryError(ChatProviderError):
    """The generated SQL could not be safely executed."""


class ChatDataError(RuntimeError):
    """Hotel storage or durable conversation logging failed."""


def _is_timeout(error: BaseException) -> bool:
    """Inspect wrapped transport types without reading or exposing error text."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, httpx.TimeoutException)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _request_text(
    client, model: str, inputs: list[dict], instructions: str,
    *, response_schema: dict | None = None,
) -> str:
    """Sanitize provider failures for either stage; never log raw exception text."""
    try:
        options = {}
        if response_schema is not None:
            options["response_format"] = {
                "type": "text", "mime_type": "application/json", "schema": response_schema,
            }
        interaction = client.interactions.create(
            model=model,
            input=inputs,
            system_instruction=instructions,
            generation_config={"max_output_tokens": 1024},
            store=False,
            timeout=CHAT_TIMEOUT_SECONDS,
            **options,
        )
        if interaction.status != "completed":
            raise ChatProviderError("The chat provider did not complete a reply.")
        text = interaction.output_text
        if response_schema is None:
            return ChatMessage("assistant", text).content
        # Structured envelopes include JSON escaping and suggested questions;
        # their fields receive their own stricter validation below.
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHAT_CHARACTERS:
            raise ValueError("The structured reply is unusable.")
        return text
    except Exception as error:
        return _raise_provider_error(error)


def _request_answer(client, model: str, inputs: list[dict], instructions: str) -> ChatReply:
    text = _request_text(
        client, model, inputs, instructions, response_schema=ChatResponse.model_json_schema(),
    )
    try:
        result = ChatResponse.model_validate_json(text)
        return ChatReply(result.reply, tuple(result.suggestions))
    except ValueError:
        raise ChatProviderError("The chat provider returned an unusable answer.") from None


def _raise_provider_error(error: Exception) -> NoReturn:
    # SDK/transport errors may contain credential headers or provider URLs.
    if getattr(error, "status_code", None) == 503 or getattr(error, "code", None) == 503:
        logger.warning("Chat provider is temporarily unavailable (HTTP 503)")
        raise ChatUnavailableError("The chat provider is unavailable.") from None
    if _is_timeout(error):
        logger.warning("Chat provider request timed out")
        raise ChatTimeoutError("The chat provider request timed out.") from None
    raise ChatProviderError("The chat provider request failed.") from None


def reply_to_chat(
    messages: tuple[ChatMessage, ...],
    *,
    database_path: str | Path = DEFAULT_DATABASE_PATH,
    conversation_id: str | None = None,
    prompt: str | None = None,
) -> ChatReply:
    """Propose SQL, enforce hotel-only reads, then answer from the retrieved rows.

    Only the current submitted user message is persisted; replayed browser context
    is not inserted again. Each log write commits independently, before the next
    stage, so errors never roll back the earlier record of what happened.
    """
    conversation = ChatConversation(messages)
    identifier = validate_conversation_id(
        conversation_id if conversation_id is not None else str(uuid4())
    )
    database = DatabaseController(database_path)

    def record(role, content, record_type="message"):
        database.append_conversation_record(ConversationRecord(
            str(uuid4()), identifier, time.time_ns() // 1_000_000,
            role, content, record_type,
        ))

    stage = "user_message"
    try:
        question = conversation.messages[-1].content
        record("user", question)
        stage = "configuration"
        try:
            instructions = prompt if prompt is not None else load_hotel_assistant_prompt()
            api_key = get_gemini_api_key()
            model = get_gemini_model()
        except (OSError, ValueError):
            raise ChatConfigurationError("The chat provider is not configured.") from None
        if api_key is None or not isinstance(instructions, str) or not instructions.strip():
            raise ChatConfigurationError("The chat provider is not configured.")

        inputs = [
            {
                "type": "user_input" if message.role == "user" else "model_output",
                "content": [{"type": "text", "text": message.content}],
            }
            for message in conversation.messages
        ]
        stage = "sql_generation"
        # One workflow owns the client; no database transaction spans either call.
        with genai.Client(
            api_key=api_key,
            vertexai=False,
            http_options={
                "timeout": CHAT_TIMEOUT_SECONDS * 1000,
                "retry_options": {"attempts": 0},
            },
        ) as client:
            # google-genai 2.28 treats HttpRetryOptions.attempts as a retry count
            # for Interactions, after coercing 0 to 1. Disable the resource's
            # retry configuration explicitly; transport tests enforce one call.
            client.interactions.sdk_configuration.retry_config = None
            generated_sql = _request_text(client, model, inputs, instructions + "\n\n" + SQL_INSTRUCTION)
            stage = "generated_sql_record"
            record("system", generated_sql, "generated_sql")
            stage = "sql_validation"
            query = database.validate_hotel_query(HotelQuery(generated_sql))
            stage = "executed_sql_record"
            record("system", query.limited_sql, "executed_sql")
            stage = "hotel_query"
            result = database.execute_hotel_query(query)
            stage = "result_summary_record"
            record("system", json.dumps({
                "row_count": len(result.rows), "columns": result.columns,
                "truncated": result.truncated, "empty": not result.rows,
            }), "result_summary")
            # The question is retained verbatim in this JSON; record values cannot
            # be promoted to system instructions by the application.
            answer_context = json.dumps({
                "question": question, "columns": result.columns, "rows": result.rows,
                "truncated": result.truncated, "data_label": "simulated classroom data",
                "missing_date_records": "availability is unknown",
            }, ensure_ascii=False)
            stage = "answer_generation"
            answer_inputs = inputs[:-1] + [{
                "type": "user_input", "content": [{"type": "text", "text": answer_context}],
            }]
            result = _request_answer(client, model, answer_inputs, instructions + "\n\n" + ANSWER_INSTRUCTION)
            stage = "assistant_message"
            record("assistant", result.reply)
            return result
    except Exception as error:
        if isinstance(error, ChatProviderError):
            safe_error = error
        elif isinstance(error, DatabaseError):
            safe_error = ChatDataError("The assistant's database could not be accessed.")
        elif isinstance(error, (HotelQueryRejectedError, ValueError)):
            safe_error = ChatQueryError("The generated hotel query could not be safely executed.")
        else:
            # Includes client construction/cleanup failures, which may carry secrets.
            try:
                _raise_provider_error(error)
            except ChatProviderError as classified:
                safe_error = classified
        code = "query_timeout" if isinstance(error, HotelQueryTimeoutError) else type(safe_error).__name__
        try:
            record("system", json.dumps({"stage": stage, "code": code}), "error")
        except DatabaseError:
            logger.warning("Chat workflow error could not be recorded")
            raise ChatDataError("The assistant's database could not be accessed.") from None
        raise safe_error from None
