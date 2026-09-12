"""Shared password-strength policy using zxcvbn entropy estimation.

Applies at all four call sites that accept a new or changed password
(register, admin create-local-account, change-password,
password-reset-confirm) so none can drift onto a length-only check.

Policy
------
* Minimum length: 8 characters (floor, checked first).
* Minimum zxcvbn score: 3 on the 0–4 scale (reject 0–2).
* Rejection reason includes zxcvbn's ``feedback.warning`` and
  ``feedback.suggestions`` so the user knows *why* to fix it.
"""

from __future__ import annotations

from typing import NamedTuple

# Shared constant — not a literal ``3`` in each call site.
MIN_ZXCVBN_SCORE: int = 3
"""Minimum acceptable zxcvbn score (0–4 scale)."""

MIN_PASSWORD_LENGTH: int = 8
"""Absolute minimum password length, checked before zxcvbn."""


class PasswordValidationError(ValueError):
    """Raised when a password fails the strength policy.

    *reason* is a user-facing string built from zxcvbn feedback.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ValidationResult(NamedTuple):
    """Outcome of ``validate_password_strength``."""

    is_valid: bool
    reason: str
    score: int
    warning: str
    suggestions: list[str]


def validate_password_strength(password: str) -> ValidationResult:
    """Validate *password* against the strength policy.

    Returns a ``ValidationResult``.  Callers raise
    :class:`PasswordValidationError` (or their own HTTP/validation
    exception) when ``is_valid`` is False.
    """
    # Length floor (checked first — cheapest).
    if len(password) < MIN_PASSWORD_LENGTH:
        return ValidationResult(
            is_valid=False,
            reason=f"Password must be at least {MIN_PASSWORD_LENGTH} "
                   "characters",
            score=0,
            warning="",
            suggestions=[],
        )

    import zxcvbn

    result = zxcvbn.zxcvbn(password)
    score = result.get("score", 0)

    if score >= MIN_ZXCVBN_SCORE:
        return ValidationResult(
            is_valid=True,
            reason="",
            score=score,
            warning="",
            suggestions=[],
        )

    # Build a specific rejection reason from zxcvbn feedback.
    feedback = result.get("feedback", {})
    warning = feedback.get("warning", "")
    suggestions = feedback.get("suggestions", [])

    parts: list[str] = ["Password is too weak."]
    if warning:
        parts.append(warning)
    if suggestions:
        parts.append(" ".join(suggestions))
    reason = " ".join(parts)

    return ValidationResult(
        is_valid=False,
        reason=reason,
        score=score,
        warning=warning or "",
        suggestions=suggestions or [],
    )


__all__ = [
    "MIN_PASSWORD_LENGTH",
    "MIN_ZXCVBN_SCORE",
    "PasswordValidationError",
    "ValidationResult",
    "validate_password_strength",
]
