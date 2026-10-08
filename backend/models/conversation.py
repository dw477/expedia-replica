"""Immutable durable chat messages and distinctly labeled workflow records."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

ConversationRole = Literal["user", "assistant", "system"]
ConversationRecordType = Literal[
    "message", "generated_sql", "executed_sql", "result_summary", "error"
]


def validate_conversation_id(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Conversation IDs must be UUIDs.") from None
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("Conversation IDs must be canonical version 4 UUIDs.")
    return value


@dataclass(frozen=True)
class ConversationRecord:
    message_id: str
    conversation_id: str
    timestamp: int  # Unix milliseconds, UTC.
    role: ConversationRole
    content: str
    record_type: ConversationRecordType = "message"

    def __post_init__(self) -> None:
        validate_conversation_id(self.message_id)
        validate_conversation_id(self.conversation_id)
        if type(self.timestamp) is not int or self.timestamp < 0:
            raise ValueError("Conversation timestamps must be Unix milliseconds.")
        if self.role not in ("user", "assistant", "system"):
            raise ValueError("Invalid conversation record role.")
        if self.record_type not in (
            "message", "generated_sql", "executed_sql", "result_summary", "error"
        ):
            raise ValueError("Invalid conversation record type.")
        if (self.record_type == "message") != (self.role in ("user", "assistant")):
            raise ValueError("Messages use user/assistant; workflow records use system.")
        if not isinstance(self.content, str) or not self.content.strip() or len(self.content) > 16000:
            raise ValueError("Conversation records require bounded nonblank content.")
