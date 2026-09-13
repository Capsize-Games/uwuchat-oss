"""One-time backfill: resolve event dates for existing KnowledgeFacts.

Processes rows where ``event_date IS NULL`` in batches, running the
Stage A+B classification/extraction pipeline.  Uses keyset pagination
on the ``id`` primary key so that rows are never skipped when a
resolved row drops out of the filtered set mid-run.  Idempotent and
safe to re-run — already-resolved rows are skipped.

Usage:
    docker compose exec server python -c "
    from airunner_services.fact_date_backfill import backfill_fact_dates
    backfill_fact_dates(batch_size=50)
    "
"""
from __future__ import annotations

import datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def backfill_fact_dates(
    batch_size: int = 50,
    chatbot_id: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    """Resolve event dates for existing KnowledgeFact rows.

    Uses keyset pagination on ``id`` — stable against the filtered
    set shrinking as rows are resolved.

    Args:
        batch_size: Rows per batch (limits memory and per-batch cost).
        chatbot_id: Optional scope to a single chatbot.
        dry_run: When True, classify but don't write.

    Returns:
        Dict with counts: ``total_processed``, ``hard_date``,
        ``no_date``, ``soft_aspirational``, ``resolved``, ``errors``.
    """
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )
    from airunner_services.database.session import session_scope
    from airunner_services.fact_date_extractor import (
        _classify_date_stage_a,
        _extract_dates_stage_b,
    )
    from airunner_services.fact_lifecycle import compute_temporal_status

    counts = {
        "total_processed": 0,
        "hard_date": 0,
        "no_date": 0,
        "soft_aspirational": 0,
        "resolved": 0,
        "errors": 0,
    }

    last_id = 0
    while True:
        with session_scope() as session:
            query = session.query(KnowledgeFact).filter(
                KnowledgeFact.id > last_id,
                KnowledgeFact.event_date.is_(None),
                KnowledgeFact.deleted.is_(False),
            )
            if chatbot_id is not None:
                query = query.filter(
                    KnowledgeFact.chatbot_id == chatbot_id
                )
            batch = (
                query.order_by(KnowledgeFact.id)
                .limit(batch_size)
                .all()
            )

            if not batch:
                break

            # Track the max id in this batch for keyset pagination.
            last_id = max(fact.id for fact in batch)

            for fact in batch:
                counts["total_processed"] += 1

                try:
                    # Stage A — classify, anchored to created_at.
                    reference_date = fact.created_at.date() if (
                        fact.created_at
                    ) else datetime.date.today()
                    classification = _classify_date_stage_a(
                        fact.fact_text, reference_date
                    )
                    if classification == "hard_date":
                        counts["hard_date"] += 1
                    elif classification == "soft_aspirational":
                        counts["soft_aspirational"] += 1
                    else:
                        counts["no_date"] += 1
                        continue

                    # Stage B — extract.
                    extracted = _extract_dates_stage_b(
                        fact.fact_text, reference_date
                    )
                    if extracted is None:
                        counts["errors"] += 1
                        continue

                    # Compute temporal_status.
                    event_date_str = extracted.get("event_date")
                    event_end_date_str = extracted.get(
                        "event_end_date"
                    )
                    event_date = (
                        datetime.date.fromisoformat(event_date_str)
                        if event_date_str
                        else None
                    )
                    event_end_date = (
                        datetime.date.fromisoformat(
                            event_end_date_str
                        )
                        if event_end_date_str
                        else None
                    )
                    recurring = bool(
                        extracted.get("recurring", False)
                    )
                    temporal_status = compute_temporal_status(
                        event_date=event_date,
                        event_end_date=event_end_date,
                        recurring=recurring,
                        reference_date=reference_date,
                    )

                    if not dry_run:
                        fact.event_date = event_date
                        fact.event_end_date = event_end_date
                        fact.event_time = extracted.get(
                            "event_time"
                        )
                        fact.recurring = recurring
                        fact.temporal_status = temporal_status
                        fact.updated_at = datetime.datetime.now(
                            datetime.UTC
                        )

                    counts["resolved"] += 1

                except Exception:
                    logger.warning(
                        "Backfill failed for fact %d",
                        fact.id,
                        exc_info=True,
                    )
                    counts["errors"] += 1

            if not dry_run:
                session.flush()

        logger.info(
            "Backfill batch complete: last_id=%d, counts=%s",
            last_id, counts,
        )

    logger.info("Backfill complete: %s", counts)
    return counts
