"""Integration test for the fact-date backfill.

Seeds > batch_size facts with a mocked classifier, runs the backfill,
and asserts every row was visited exactly once across multiple
batches.  Also checks that a re-run does no redundant writes.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from airunner_services.database.session import reset_engine

_TOTAL_FACTS = 75
_BATCH_SIZE = 25

# Track which fact IDs were classified (to verify no skipped rows).
_classified_ids: set[int] = set()


def _mock_classifier(fact_text: str, reference_date) -> str:
    """IDs ending in 0, 3, or 7 → hard_date; rest → no_date."""
    import re

    match = re.search(r"FACT-(\d+)", fact_text)
    if match:
        fid = int(match.group(1))
        _classified_ids.add(fid)
        if fid % 10 in (0, 3, 7):
            return "hard_date"
    return "no_date"


def _mock_extractor(fact_text: str, reference_date) -> dict:
    """Return a plausible extraction for hard_date facts."""
    return {
        "event_date": "2026-08-01",
        "event_end_date": None,
        "event_time": None,
        "recurring": False,
    }


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Ensure a test database is reachable and initialise public schema."""
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip("No test database configured")
    if not db_url.startswith("postgres"):
        pytest.skip("Backfill tests require PostgreSQL")
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DB_TENANCY", "multi")
    reset_engine()

    from airunner_services.database.setup_database import setup_database

    try:
        setup_database()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Database unavailable: {exc}")
    return db_url


def test_backfill_keyset_pagination_visits_every_row(
    _db: str,
) -> None:
    """Seed 75 facts, run backfill with batch_size=25.

    Verifies every row is visited exactly once across 3 batches,
    and a re-run does no additional writes.
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )

    _classified_ids.clear()
    tenant_key = f"backfill_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            # Seed 75 facts with event_date=NULL.
            with session_scope() as session:
                for i in range(_TOTAL_FACTS):
                    session.add(
                        KnowledgeFact(
                            fact_text=f"FACT-{i}: test fact {i}",
                            chatbot_id=1,
                            subject="user",
                            source_type="user_stated",
                            event_date=None,
                            temporal_status="durable",
                            recurring=False,
                        )
                    )
                session.flush()

                null_count = (
                    session.query(KnowledgeFact)
                    .filter(
                        KnowledgeFact.event_date.is_(None),
                        KnowledgeFact.deleted.is_(False),
                    )
                    .count()
                )
                assert null_count == _TOTAL_FACTS

            # Run backfill with mocked classifier.
            with patch(
                "airunner_services.fact_date_extractor"
                "._classify_date_stage_a",
                side_effect=_mock_classifier,
            ), patch(
                "airunner_services.fact_date_extractor"
                "._extract_dates_stage_b",
                side_effect=_mock_extractor,
            ):
                from airunner_services.fact_date_backfill import (
                    backfill_fact_dates,
                )

                result = backfill_fact_dates(batch_size=_BATCH_SIZE)

            # Every seeded row must have been classified exactly once.
            assert result["total_processed"] == _TOTAL_FACTS
            assert len(_classified_ids) == _TOTAL_FACTS

            hard_expected = sum(
                1
                for i in range(_TOTAL_FACTS)
                if i % 10 in (0, 3, 7)
            )
            assert result["hard_date"] == hard_expected

            # Verify DB state.
            with session_scope() as session:
                resolved = (
                    session.query(KnowledgeFact)
                    .filter(
                        KnowledgeFact.event_date.isnot(None),
                        KnowledgeFact.deleted.is_(False),
                    )
                    .count()
                )
                assert resolved == hard_expected

                still_null = (
                    session.query(KnowledgeFact)
                    .filter(
                        KnowledgeFact.event_date.is_(None),
                        KnowledgeFact.deleted.is_(False),
                    )
                    .count()
                )
                assert still_null == _TOTAL_FACTS - hard_expected

            # Re-run: hard_date rows now skipped (event_date set).
            # no_date rows still have NULL event_date and get
            # re-classified (same result, no new writes).
            _classified_ids.clear()
            with patch(
                "airunner_services.fact_date_extractor"
                "._classify_date_stage_a",
                side_effect=_mock_classifier,
            ), patch(
                "airunner_services.fact_date_extractor"
                "._extract_dates_stage_b",
                side_effect=_mock_extractor,
            ):
                result2 = backfill_fact_dates(batch_size=_BATCH_SIZE)

            no_date_count = _TOTAL_FACTS - hard_expected
            assert result2["total_processed"] == no_date_count
            assert result2["hard_date"] == 0
            assert result2["resolved"] == 0

    finally:
        reset_engine()
        _drop_schema(tenant_key)


def _drop_schema(tenant_key: str) -> None:
    """Drop the scratch tenant schema."""
    from airunner_services.data.tenant import tenant_schema_for_key
    from airunner_services.database.session import _tenant_db_url
    from airunner_services.database.db.engine import (
        create_configured_engine,
    )

    schema = tenant_schema_for_key(tenant_key)
    db_url = os.environ.get("AIRUNNER_DATABASE_URL", "")
    if not db_url:
        return

    tenant_url = _tenant_db_url(db_url, schema)
    engine = create_configured_engine(tenant_url)
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(
                text(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            )
    finally:
        engine.dispose()
