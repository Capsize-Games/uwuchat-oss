"""llm-guard ONNX scanner integration.

Lazy-loaded on first call. If llm-guard is not installed or models are
not downloaded, the caller catches ImportError / Exception gracefully.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from airunner_services.llm.safety.constants import BAN_TOPICS
from airunner_services.llm.safety.preflight import (
    PreflightOutcome,
    PreflightResult,
)

logger = logging.getLogger(__name__)

_injection_scanner = None
_toxicity_scanner = None
_ban_topics_scanner = None


def _model_path() -> str:
    from airunner_services.conf import settings

    return getattr(
        settings,
        "AIRUNNER_LLM_GUARD_MODEL_PATH",
        os.path.expanduser(
            "~/.local/share/airunner/text/models/llm_guard/"
        ),
    )


def _get_injection_scanner():
    global _injection_scanner
    if _injection_scanner is None:
        from llm_guard.input_scanners import PromptInjection
        from llm_guard.input_scanners.prompt_injection import (
            MatchType,
        )

        _injection_scanner = PromptInjection(
            threshold=0.75,
            match_type=MatchType.SENTENCE,
        )
    return _injection_scanner


def _get_toxicity_scanner():
    global _toxicity_scanner
    if _toxicity_scanner is None:
        from llm_guard.input_scanners import Toxicity

        _toxicity_scanner = Toxicity(threshold=0.80)
    return _toxicity_scanner


def _get_ban_topics_scanner():
    global _ban_topics_scanner
    if _ban_topics_scanner is None:
        from llm_guard.input_scanners import BanTopics

        _ban_topics_scanner = BanTopics(
            topics=BAN_TOPICS,
            threshold=0.75,
        )
    return _ban_topics_scanner


def scan_message(message: str) -> Optional[PreflightResult]:
    """Run all llm-guard scanners. Returns result on first hit."""
    result = _scan_injection(message)
    if result:
        return result
    result = _scan_toxicity(message)
    if result:
        return result
    return _scan_ban_topics(message)


def _scan_injection(message: str) -> Optional[PreflightResult]:
    scanner = _get_injection_scanner()
    _, is_valid, _ = scanner.scan("", message)
    if not is_valid:
        return PreflightResult(
            outcome=PreflightOutcome.IN_CHARACTER_DEFLECT,
            reason="llm_guard_injection",
        )
    return None


def _scan_toxicity(message: str) -> Optional[PreflightResult]:
    scanner = _get_toxicity_scanner()
    _, is_valid, _ = scanner.scan("", message)
    if not is_valid:
        return PreflightResult(
            outcome=PreflightOutcome.IN_CHARACTER_DEFLECT,
            reason="llm_guard_toxicity",
        )
    return None


def _scan_ban_topics(message: str) -> Optional[PreflightResult]:
    scanner = _get_ban_topics_scanner()
    _, is_valid, _ = scanner.scan("", message)
    if not is_valid:
        return PreflightResult(
            outcome=PreflightOutcome.IN_CHARACTER_DEFLECT,
            reason="llm_guard_ban_topics",
        )
    return None
