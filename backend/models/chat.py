"""Immutable text-only chat contracts, independent of provider and HTTP code."""

from dataclasses import dataclass
from typing import Literal

MAX_CHAT_MESSAGES = 21
MAX_CHAT_MESSAGE_LENGTH = 8000
MAX_CHAT_CHARACTERS = 32000
MAX_CHAT_SUGGESTIONS = 3
MAX_CHAT_SUGGESTION_LENGTH = 160
ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("user", "assistant"):
            raise ValueError("Chat messages must be from the user or assistant.")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Enter a non-empty chat message.")
        if len(self.content) > MAX_CHAT_MESSAGE_LENGTH:
            raise ValueError("Chat messages must be at most 8000 characters.")
        object.__setattr__(self, "content", self.content.strip())


@dataclass(frozen=True)
class ChatConversation:
    messages: tuple[ChatMessage, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.messages, tuple)
            or not 1 <= len(self.messages) <= MAX_CHAT_MESSAGES
        ):
            raise ValueError("Send between 1 and 21 chat messages.")
        for index, message in enumerate(self.messages):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if not isinstance(message, ChatMessage) or message.role != expected_role:
                raise ValueError(
                    "Chat messages must alternate between user and assistant, "
                    "starting with user."
                )
        if self.messages[-1].role != "user":
            raise ValueError("The last chat message must be from the user.")
        if sum(len(message.content) for message in self.messages) > MAX_CHAT_CHARACTERS:
            raise ValueError("Chat context must be at most 32000 characters.")


@dataclass(frozen=True)
class ChatReply:
    reply: str
    suggestions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        message = ChatMessage("assistant", self.reply)
        object.__setattr__(self, "reply", message.content)
        if not isinstance(self.suggestions, tuple) or len(self.suggestions) > MAX_CHAT_SUGGESTIONS:
            raise ValueError("Return at most three suggested questions.")
        questions = []
        for suggestion in self.suggestions:
            if (
                not isinstance(suggestion, str)
                or not suggestion.strip()
                or len(suggestion) > MAX_CHAT_SUGGESTION_LENGTH
            ):
                raise ValueError("Suggested questions must be nonblank text of at most 160 characters.")
            questions.append(suggestion.strip())
        if len({question.casefold() for question in questions}) != len(questions):
            raise ValueError("Suggested questions must be distinct.")
        object.__setattr__(self, "suggestions", tuple(questions))
