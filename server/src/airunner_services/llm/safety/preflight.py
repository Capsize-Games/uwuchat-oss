"""Pre-flight safety filter: runs before every LLM inference call."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from airunner_services.llm.safety.constants import (
    INJECTION_PATTERNS,
    SELF_HARM_KEYWORDS,
)
from airunner_services.llm.safety.illegal_keywords import ILLEGAL_KEYWORDS

logger = logging.getLogger(__name__)

_INJECTION_RE = re.compile(
    "|".join(INJECTION_PATTERNS),
    re.IGNORECASE,
)


class PreflightOutcome(str, Enum):
    PASS = "pass"
    CRISIS = "crisis"
    IN_CHARACTER_DEFLECT = "deflect"
    HARD_BLOCK = "hard_block"


@dataclass
class PreflightResult:
    outcome: PreflightOutcome
    reason: Optional[str] = None


def run_preflight(message: str) -> PreflightResult:
    """Run all safety checks on a user message.

    Returns immediately on first match — checks run cheapest-first.
    """
    result = _check_illegal(message)
    if result:
        return result
    result = _check_self_harm(message)
    if result:
        return result
    result = _check_injection(message)
    if result:
        return result
    result = _check_llm_guard(message)
    if result:
        return result
    return PreflightResult(outcome=PreflightOutcome.PASS)


def _check_illegal(message: str) -> Optional[PreflightResult]:
    lower = message.lower()
    for kw in ILLEGAL_KEYWORDS:
        if kw in lower:
            logger.warning(
                "Illegal keyword match — user_hash=%s",
                hash(message) & 0xFFFF,
            )
            return PreflightResult(
                outcome=PreflightOutcome.HARD_BLOCK,
                reason="illegal_keyword",
            )
    return None


def _check_self_harm(message: str) -> Optional[PreflightResult]:
    lower = message.lower()
    for kw in SELF_HARM_KEYWORDS:
        if kw in lower:
            return PreflightResult(
                outcome=PreflightOutcome.CRISIS,
                reason="self_harm_keyword",
            )
    return None


def _check_injection(message: str) -> Optional[PreflightResult]:
    if _INJECTION_RE.search(message):
        return PreflightResult(
            outcome=PreflightOutcome.IN_CHARACTER_DEFLECT,
            reason="injection_pattern",
        )
    return None


def _llm_guard_enabled() -> bool:
    try:
        from airunner_services.conf import settings

        return bool(getattr(settings, "AIRUNNER_LLM_GUARD_ENABLED", False))
    except Exception:
        return False


def _check_llm_guard(message: str) -> Optional[PreflightResult]:
    """Run llm-guard ONNX scanners when enabled and available."""
    if not _llm_guard_enabled():
        return None
    try:
        from airunner_services.llm.safety._llm_guard_scanners import (
            scan_message,
        )

        return scan_message(message)
    except ImportError:
        return None
    except Exception as exc:
        logger.warning("llm-guard scan failed: %s", exc)
        return None
