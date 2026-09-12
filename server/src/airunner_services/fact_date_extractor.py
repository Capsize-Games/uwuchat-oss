"""Two-stage cheap classify-then-extract for fact date resolution.

Stage A (cheap gate): classifies a fact as ``no_date``,
``hard_date``, or ``soft_aspirational`` using the TOOL_CLASSIFICATION
tier model.  Most facts (names, job, preferences) exit here at
near-zero cost.

Stage B (structured extraction, gate-positive only): for ``hard_date``
results, extracts ``event_date``, optional ``event_end_date``,
optional ``event_time``, and ``recurring: bool`` resolved against the
fact's own ``created_at`` or a supplied reference date.

See ``plans/uwuchat-temporal-fact-lifecycle-and-rag-indexing-fix.md``
for the design rationale.
"""
from __future__ import annotations

import datetime
import json
import logging
from typing import Optional

from airunner_services.fact_date_prompts import (
    STAGE_A_PROMPT,
    STAGE_B_PROMPT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage A — cheap classification gate
# ---------------------------------------------------------------------------


def _classify_date_stage_a(
    fact_text: str,
    reference_date: datetime.date,
) -> str:
    """Run Stage A date classification via LLM.

    Args:
        fact_text: The fact text to classify.
        reference_date: The date context for relative-date resolution.

    Returns:
        One of ``"no_date"``, ``"hard_date"``, ``"soft_aspirational"``,
        or ``"error"`` if the LLM call fails.
    """
    prompt = STAGE_A_PROMPT.format(
        reference_date=reference_date.isoformat(),
        fact_text=fact_text,
    )
    result = _call_classification_llm(prompt).strip().lower()
    if result in ("no_date", "hard_date", "soft_aspirational"):
        return result
    # Best-effort: try to match the first word if the model returned
    # extra text.
    first_word = result.split()[0] if result else ""
    if first_word in ("no_date", "hard_date", "soft_aspirational"):
        return first_word
    logger.warning(
        "Stage A classification returned unrecognized: %r", result[:80]
    )
    return "no_date"


# ---------------------------------------------------------------------------
# Stage B — structured date extraction
# ---------------------------------------------------------------------------

def _extract_dates_stage_b(
    fact_text: str,
    reference_date: datetime.date,
) -> Optional[dict]:
    """Run Stage B structured date extraction via LLM.

    Args:
        fact_text: The fact text to extract dates from.
        reference_date: The date context for relative-date resolution.

    Returns:
        A dict with keys ``event_date``, ``event_end_date``,
        ``event_time``, ``recurring``, or ``None`` if the call
        fails or the response cannot be parsed.
    """
    prompt = STAGE_B_PROMPT.format(
        reference_date=reference_date.isoformat(),
        fact_text=fact_text,
    )
    raw = _call_classification_llm(prompt).strip()
    return _parse_stage_b_response(raw)


def _parse_stage_b_response(raw: str) -> Optional[dict]:
    """Parse Stage B JSON response into a structured dict.

    Tolerates models that wrap JSON in markdown fences or add
    trailing commentary.
    """
    # Strip markdown code fences if present.
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove opening fence (```json or ```)
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to find a JSON object in the text.
        import re
        match = re.search(r"\{[^{}]*\"event_date\"[^{}]*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                logger.warning(
                    "Stage B response not parseable: %r", raw[:120]
                )
                return None
        else:
            logger.warning(
                "Stage B response not parseable: %r", raw[:120]
            )
            return None

    # Validate and normalize the response.
    result: dict = {
        "event_date": None,
        "event_end_date": None,
        "event_time": None,
        "recurring": False,
    }

    for key in ("event_date", "event_end_date"):
        val = data.get(key)
        if val and isinstance(val, str):
            try:
                datetime.date.fromisoformat(val)
                result[key] = val
            except (ValueError, TypeError):
                pass

    event_time = data.get("event_time")
    if event_time and isinstance(event_time, str):
        try:
            datetime.time.fromisoformat(event_time)
            result["event_time"] = event_time
        except (ValueError, TypeError):
            pass

    recurring = data.get("recurring")
    if isinstance(recurring, bool):
        result["recurring"] = recurring

    # Must have at least an event_date to be useful.
    if result["event_date"] is None:
        return None

    return result


# ---------------------------------------------------------------------------
# Public API — the main entry point
# ---------------------------------------------------------------------------


def _call_classification_llm(prompt: str) -> str:
    """Invoke the TOOL_CLASSIFICATION tier model via the shared
    ``fact_date_llm`` module."""
    from airunner_services.fact_date_llm import (
        call_classification_llm as _llm,
    )
    return _llm(prompt)


def resolve_fact_dates(
    fact_text: str,
    reference_date: Optional[datetime.date] = None,
) -> Optional[dict]:
    """Run Stage A+B classification and extraction for one fact.

    This is the single public entry point.  Callers do not need to
    know about the two-stage internals.

    Args:
        fact_text: The fact text to resolve.
        reference_date: Date context (e.g. the conversation's current
            date at the time the fact was stated).  Defaults to today.

    Returns:
        A dict with keys ``event_date``, ``event_end_date``,
        ``event_time``, ``recurring``, ``temporal_status`` suitable
        for writing to a ``KnowledgeFact`` row, or ``None`` if the
        fact has no resolvable date.
    """
    if reference_date is None:
        reference_date = datetime.date.today()

    # Stage A — cheap gate.
    classification = _classify_date_stage_a(fact_text, reference_date)
    if classification != "hard_date":
        return None

    # Stage B — structured extraction.
    extracted = _extract_dates_stage_b(fact_text, reference_date)
    if extracted is None:
        return None

    # Compute temporal_status from the extracted dates.
    from airunner_services.fact_lifecycle import compute_temporal_status

    event_date_str = extracted.get("event_date")
    event_end_date_str = extracted.get("event_end_date")
    event_date = (
        datetime.date.fromisoformat(event_date_str)
        if event_date_str
        else None
    )
    event_end_date = (
        datetime.date.fromisoformat(event_end_date_str)
        if event_end_date_str
        else None
    )
    recurring = bool(extracted.get("recurring", False))

    temporal_status = compute_temporal_status(
        event_date=event_date,
        event_end_date=event_end_date,
        recurring=recurring,
        reference_date=reference_date,
    )

    return {
        "event_date": event_date_str,
        "event_end_date": event_end_date_str,
        "event_time": extracted.get("event_time"),
        "recurring": recurring,
        "temporal_status": temporal_status,
    }
