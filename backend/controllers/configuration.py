"""Backend configuration, independent of persistence and the browser View."""

import os
from pathlib import Path

from dotenv import load_dotenv


def get_geoapify_api_key() -> str | None:
    """Read backend-only credentials; callers must never log or expose them."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    # Deployment environment variables take precedence over local configuration.
    load_dotenv(dotenv_path=env_path, override=False)
    return os.environ.get("GEOAPIFY_API_KEY", "").strip() or None


def geoapify_key_is_configured() -> bool:
    """Load root .env at startup and return only whether a key is present."""
    return get_geoapify_api_key() is not None
