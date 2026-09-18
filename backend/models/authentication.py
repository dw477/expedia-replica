"""CSV account and persisted session contracts; secrets never enter API outputs."""

import re
from dataclasses import dataclass, field

USERNAME_PATTERN = r"[a-z0-9][a-z0-9_.-]{2,63}"
PASSWORD_HASH_PATTERN = r"pbkdf2_sha256\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}"
REGISTRATION_PASSWORD_PATTERN = (
    r"(?=.*[A-Z])(?=.*[0-9])(?=.*[!@$%&?])[A-Za-z0-9!@$%&?]{8,256}"
)


def validate_registration_password(password: str) -> str:
    """New passwords use only letters, digits, and the agreed special characters."""
    if re.fullmatch(REGISTRATION_PASSWORD_PATTERN, password) is None:
        raise ValueError(
            "Password must be 8–256 characters and include an uppercase letter, a digit, "
            "and one of !@$%&?. Only letters, digits, and those special characters are allowed."
        )
    return password


USER_ACCOUNT_COLUMNS = ("user_id", "display_name", "username", "password_hash")


@dataclass(frozen=True)
class UserAccount:
    user_id: str
    display_name: str
    username: str
    password_hash: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.user_id, self.display_name):
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise ValueError("Account IDs and names must be non-empty trimmed text")
        if (
            not isinstance(self.username, str)
            or re.fullmatch(USERNAME_PATTERN, self.username) is None
        ):
            raise ValueError(
                "username must be 3–64 lowercase letters, digits, dots, underscores, or hyphens"
            )
        if (
            not isinstance(self.password_hash, str)
            or re.fullmatch(PASSWORD_HASH_PATTERN, self.password_hash) is None
        ):
            raise ValueError(
                "password_hash must be a salted PBKDF2-SHA256 hash with 600000 iterations"
            )


@dataclass(frozen=True)
class AuthSession:
    session_id: str = field(repr=False)
    user_id: str
    expires_at: int
    credential_version: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in (self.session_id, self.credential_version):
            if (
                not isinstance(value, str)
                or re.fullmatch(r"[0-9a-f]{64}", value) is None
            ):
                raise ValueError(
                    "Session identifiers and credential versions must be SHA256 hex digests"
                )
        if (
            not isinstance(self.user_id, str)
            or not self.user_id.strip()
            or self.user_id != self.user_id.strip()
        ):
            raise ValueError("Session user_id must be non-empty trimmed text")
        if type(self.expires_at) is not int or self.expires_at < 0:
            raise ValueError("Session expiry must be a non-negative Unix timestamp")
