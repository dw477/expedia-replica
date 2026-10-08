"""Load the dedicated hotel-assistant instructions at application startup."""

from pathlib import Path

HOTEL_ASSISTANT_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "prompts" / "hotel-assistant.md"
)


def load_hotel_assistant_prompt() -> str:
    """Call once at startup; prompt edits require restarting the backend."""
    try:
        prompt = HOTEL_ASSISTANT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise ValueError("Hotel assistant instructions could not be loaded.") from None
    if not prompt:
        raise ValueError("Hotel assistant instructions must not be empty.")
    return prompt
