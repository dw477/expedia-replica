"""Password hashing and verification without plaintext persistence."""

import hashlib
import hmac
import re
import secrets

from backend.models.authentication import PASSWORD_HASH_PATTERN

PASSWORD_ITERATIONS = 600_000
MAX_PASSWORD_LENGTH = 256


def hash_password(password: str) -> str:
    """Return a random-salted hash; preserve password case and whitespace."""
    if not isinstance(password, str) or not 1 <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("Password must contain 1–256 characters")
    try:
        password_bytes = password.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("Password must contain valid Unicode") from error
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password_bytes, bytes.fromhex(salt), PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Fail closed for invalid hash formats; compare derived digests in constant time."""
    if not isinstance(password, str) or not 1 <= len(password) <= MAX_PASSWORD_LENGTH:
        return False
    if re.fullmatch(PASSWORD_HASH_PATTERN, encoded) is None:
        return False
    try:
        password_bytes = password.encode("utf-8")
    except UnicodeError:
        return False
    _, _, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac(
        "sha256", password_bytes, bytes.fromhex(salt), PASSWORD_ITERATIONS
    )
    return hmac.compare_digest(actual, bytes.fromhex(expected))
