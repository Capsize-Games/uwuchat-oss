"""Input validation helpers for user-supplied text fields."""

from __future__ import annotations

import re
import unicodedata

from airunner_services.llm.safety.constants import (
    INJECTION_PATTERNS,
    MAX_CHATBOT_BACKGROUND_LEN,
    MAX_CHATBOT_NAME_LEN,
    MAX_GENERIC_FIELD_LEN,
    MAX_USER_MESSAGE_LEN,
)
from airunner_services.llm.safety.illegal_keywords import ILLEGAL_KEYWORDS

_INJECTION_RE = re.compile(
    "|".join(INJECTION_PATTERNS),
    re.IGNORECASE,
)

# Intentionally strips bidi-override control chars (an injection
# defense) -- their presence here is the fix, not a vulnerability.
_STRIP_CHARS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f‪-‮]"  # nosec B613
)

_FIELD_LIMITS: dict[str, int] = {
    "name": MAX_CHATBOT_NAME_LEN,
    "botname": MAX_CHATBOT_NAME_LEN,
    "bot_personality": MAX_CHATBOT_BACKGROUND_LEN,
}


class ValidationError(ValueError):
    """Raised when user input fails a safety check."""


def sanitize(text: str) -> str:
    """Strip control chars and Unicode direction overrides."""
    text = _STRIP_CHARS.sub("", text)
    return unicodedata.normalize("NFC", text)


def _check_length(text: str, max_len: int, field: str) -> None:
    if len(text) > max_len:
        raise ValidationError(
            f"{field} exceeds maximum length of {max_len}."
        )


def _check_injection(text: str) -> None:
    if _INJECTION_RE.search(text):
        raise ValidationError("Input contains disallowed content.")


def _check_illegal_keywords(text: str) -> None:
    lower = text.lower()
    for kw in ILLEGAL_KEYWORDS:
        if kw in lower:
            raise ValidationError("Input contains disallowed content.")


def validate_chatbot_field(field: str, value: str) -> str:
    """Validate and sanitize one chatbot create/update field.

    Returns the sanitized value on success.
    Raises ValidationError on any failure.
    """
    value = sanitize(value)
    max_len = _FIELD_LIMITS.get(field, MAX_GENERIC_FIELD_LEN)
    _check_length(value, max_len, field)
    _check_injection(value)
    _check_illegal_keywords(value)
    return value


def validate_message_text(text: str) -> str:
    """Validate and sanitize an incoming user chat message.

    Returns the sanitized text on success.
    Raises ValidationError on failure.
    """
    text = sanitize(text)
    _check_length(text, MAX_USER_MESSAGE_LEN, "message")
    return text
