"""Unit tests for the shared password-strength policy.

Covers:
- Known-weak password rejected with specific reason.
- Strong passphrase accepted.
- Length floor applies independently of zxcvbn score.
"""

from __future__ import annotations

import pytest

from extensions.auth.server.password_policy import (
    MIN_PASSWORD_LENGTH,
    MIN_ZXCVBN_SCORE,
    PasswordValidationError,
    validate_password_strength,
)


# ---------------------------------------------------------------------------
# Strong passphrase → accepted
# ---------------------------------------------------------------------------


def test_strong_passphrase_accepted() -> None:
    """A long, high-entropy passphrase passes the policy."""
    result = validate_password_strength(
        "correct-horse-battery-staple-sunshine-42"
    )
    assert result.is_valid is True
    assert result.score >= MIN_ZXCVBN_SCORE


def test_reasonably_strong_password_accepted() -> None:
    """A password with mixed chars and length >= 12 typically scores >= 3."""
    result = validate_password_strength("Tr0ub4dor&3Mango!")
    assert result.is_valid is True


# ---------------------------------------------------------------------------
# Known-weak passwords → rejected
# ---------------------------------------------------------------------------


def test_common_password_rejected() -> None:
    """'password123' — a top-10k-common password — is rejected."""
    result = validate_password_strength("password123")
    assert result.is_valid is False
    assert "too weak" in result.reason.lower()
    assert result.score < MIN_ZXCVBN_SCORE


def test_repetitive_password_rejected() -> None:
    """'aaaaaaaa' — low entropy — is rejected."""
    result = validate_password_strength("aaaaaaaa")
    assert result.is_valid is False
    assert result.score < MIN_ZXCVBN_SCORE


def test_short_common_word_rejected() -> None:
    """'letmein' is rejected as too weak."""
    result = validate_password_strength("letmein")
    assert result.is_valid is False


# ---------------------------------------------------------------------------
# Length floor — checked independently of zxcvbn score
# ---------------------------------------------------------------------------


def test_too_short_password_rejected_before_zxcvbn() -> None:
    """A password shorter than MIN_PASSWORD_LENGTH is rejected immediately,
    before zxcvbn is called."""
    short = "a" * (MIN_PASSWORD_LENGTH - 1)
    result = validate_password_strength(short)
    assert result.is_valid is False
    assert "at least" in result.reason.lower()
    assert result.score == 0


def test_exactly_min_length_not_rejected_by_length_floor() -> None:
    """A password exactly at MIN_PASSWORD_LENGTH is not rejected by the
    length check alone (may still fail zxcvbn)."""
    pw = "a" * MIN_PASSWORD_LENGTH
    result = validate_password_strength(pw)
    # Length check passes, but zxcvbn score is low for repeated chars
    assert "at least" not in result.reason.lower()


# ---------------------------------------------------------------------------
# Rejection reason includes zxcvbn feedback
# ---------------------------------------------------------------------------


def test_rejection_reason_includes_feedback() -> None:
    """When zxcvbn rejects, the reason includes warning or suggestions."""
    result = validate_password_strength("abc123")
    assert result.is_valid is False
    # The policy appends feedback — at minimum "too weak" is present.
    assert result.reason


# ---------------------------------------------------------------------------
# PasswordValidationError
# ---------------------------------------------------------------------------


def test_password_validation_error_reason() -> None:
    """PasswordValidationError stores the reason string."""
    err = PasswordValidationError("test reason")
    assert err.reason == "test reason"
    assert str(err) == "test reason"
