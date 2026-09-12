"""Grounding-check tool — deterministic claim verification.

Forced after any ToolCategory.SEARCH tool executes so the model
cannot narrate unsupported claims without being flagged first.
"""

from __future__ import annotations

import json
import threading
from typing import Annotated, Any, List

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.llm.tools.grounding_tools_helpers import (
    check_claims_against_sources,
    get_grounding_sources,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger
from airunner_services.utils.application.log_hygiene import (
    fingerprint_value,
)

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_turn_flag_cache = threading.local()


def _turn_flagged_claims() -> set:
    if not hasattr(_turn_flag_cache, "claims"):
        _turn_flag_cache.claims = set()
    return _turn_flag_cache.claims


def clear_turn_flags() -> None:
    """Clear the per-turn flag cache at the start of each generation."""
    _turn_flag_cache.claims = set()


@tool(
    name="check_grounding",
    category=ToolCategory.QA,
    description=(
        "Verify that every specific factual claim in your draft response "
        "is backed by the search results you just received.  Submit each "
        "claim you plan to make (one string per claim).  The tool returns "
        "which claims are supported and which are NOT — you MUST drop or "
        "qualify any unsupported claim before responding."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=["fact-check", "verify", "grounding", "source-check"],
    input_examples=[
        {"claims": ["The DOJ approved the merger on July 10, 2026"]},
    ],
)
def check_grounding(
    claims: Annotated[
        List[str],
        "Each specific factual claim you plan to state in your response",
    ],
    api: Any = None,
) -> str:
    """Check each claim against this turn's search/knowledge results.

    Args:
        claims: List of factual claims to verify.
        api: API instance (injected).

    Returns:
        JSON string with per-claim support verdicts.
    """
    if not claims:
        return (
            "ERROR: You must submit at least one specific factual claim "
            "to verify.  An empty claims list does not satisfy the "
            "grounding check — call check_grounding again with the "
            "specific claims you plan to state in your response."
        )
    verifiable = [c for c in claims if isinstance(c, str) and len(c.strip()) >= 12]
    if not verifiable:
        return (
            "ERROR: None of the submitted claims are long enough to "
            "verify (minimum 12 characters).  Submit each specific "
            "factual claim you plan to state, using complete sentences "
            "like 'The committee voted 5-4 to approve the measure on "
            "Tuesday' — not single words or fragments."
        )

    sources = get_grounding_sources()
    logger.info(
        "check_grounding: %d claims against %d sources",
        len(claims),
        len(sources),
    )
    results = check_claims_against_sources(claims, sources)

    unsupported = [r for r in results if not r["supported"]]
    if unsupported:
        flagged = _turn_flagged_claims()
        for r in unsupported:
            fingerprint = fingerprint_value(
                r["claim"], label="claim_fp"
            )
            if fingerprint not in flagged:
                flagged.add(fingerprint)
                logger.warning(
                    "GROUNDING_CHECK_FLAGGED: %s (best_score=%.2f)",
                    fingerprint,
                    r["best_score"],
                )

    # Emit signal when claims are flagged (for admin Inspect Flow panel)
    if unsupported and api and hasattr(api, "emit_signal"):
        from airunner_services.contract_enums import SignalCode

        flagged_fps = [
            fingerprint_value(r["claim"], label="claim_fp")
            for r in unsupported
        ]
        api.emit_signal(
            SignalCode.GROUNDING_CHECK_FLAGGED,
            {"flagged_count": len(flagged_fps), "hashes": flagged_fps},
        )

    return json.dumps(
        {
            "total_claims": len(claims),
            "supported_count": len(results) - len(unsupported),
            "unsupported_count": len(unsupported),
            "claims": results,
            "instruction": (
                "IMPORTANT: For each claim marked 'supported: false', "
                "you MUST either DROP the claim entirely from your "
                "response or soften it to reflect uncertainty in "
                "your own voice (e.g. 'I think', 'possibly', "
                "'I'm not totally sure but').  Never state an "
                "unsupported claim as a confident fact.  Do NOT "
                "reference search results, sources, tools, or "
                "the grounding check itself."
            ),
        },
        indent=2,
    )
