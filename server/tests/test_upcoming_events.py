"""Tests for upcoming_events_block: live recomputation, opportunistic
correction, stale-stored-status gap, and real text content."""
from __future__ import annotations

import datetime
import os

import pytest

from airunner_services.database.session import reset_engine


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Ensure test DB reachable and initialise public schema."""
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip("No test database configured")
    if not db_url.startswith("postgres"):
        pytest.skip("Upcoming events tests require PostgreSQL")
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DB_TENANCY", "multi")
    reset_engine()
    from airunner_services.database.setup_database import setup_database

    try:
        setup_database()
    except Exception:
        pytest.skip("Database unavailable")
    return db_url


def test_block_contains_real_event_text_and_dates(
    _db: str,
) -> None:
    """Returned block contains actual fact text and ISO dates."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )
    from airunner_services.llm.managers.prompt_builder.upcoming_events import (
        upcoming_events_block,
    )

    chatbot_id = 99999
    tenant_key = f"uev_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                session.add(
                    KnowledgeFact(
                        fact_text="release deadline",
                        chatbot_id=chatbot_id,
                        subject="user",
                        event_date=datetime.date(2099, 9, 1),
                        temporal_status="upcoming",
                        recurring=False,
                    )
                )
                session.add(
                    KnowledgeFact(
                        fact_text="on vacation",
                        chatbot_id=chatbot_id,
                        subject="user",
                        event_date=datetime.date(2099, 7, 20),
                        event_end_date=datetime.date(2099, 7, 30),
                        temporal_status="in_progress",
                        recurring=False,
                    )
                )
                session.flush()
            block = upcoming_events_block(chatbot_id)

        assert "Known upcoming/current events:" in block
        assert "release deadline" in block
        assert "2099-09-01" in block
        assert "on vacation" in block
        assert "2099-07-20" in block
        assert "2099-07-30" in block
    finally:
        reset_engine()
        _drop_schema(tenant_key)


def test_stale_upcoming_excluded_and_corrected(
    _db: str,
) -> None:
    """Past event_date + stale 'upcoming' → excluded, stored corrected."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )

    chatbot_id = 99998
    tenant_key = f"uev2_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                session.add(
                    KnowledgeFact(
                        fact_text="ancient deadline",
                        chatbot_id=chatbot_id,
                        subject="user",
                        event_date=datetime.date(2020, 6, 1),
                        temporal_status="upcoming",
                        recurring=False,
                    )
                )
                session.flush()

            from airunner_services.llm.managers.prompt_builder.upcoming_events import (
                upcoming_events_block,
            )
            block = upcoming_events_block(chatbot_id)

        assert block == ""

        with tenant_scope(tenant_key):
            with session_scope() as session:
                fact = (
                    session.query(KnowledgeFact)
                    .filter(KnowledgeFact.chatbot_id == chatbot_id)
                    .one()
                )
                assert fact.temporal_status == "resolved"
    finally:
        reset_engine()
        _drop_schema(tenant_key)


def test_candidate_query_broad_and_corrects_stored(
    _db: str,
) -> None:
    """Candidate query picks up both rows; live recomputation excludes
    the past one and corrects it."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )

    chatbot_id = 99997
    tenant_key = f"uev3_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                session.add(
                    KnowledgeFact(
                        fact_text="future event",
                        chatbot_id=chatbot_id,
                        subject="user",
                        event_date=datetime.date(2099, 1, 1),
                        temporal_status="upcoming",
                        recurring=False,
                    )
                )
                session.add(
                    KnowledgeFact(
                        fact_text="past stale",
                        chatbot_id=chatbot_id,
                        subject="user",
                        event_date=datetime.date(2020, 1, 1),
                        temporal_status="upcoming",
                        recurring=False,
                    )
                )
                session.flush()

            with session_scope() as session:
                candidates = (
                    session.query(KnowledgeFact)
                    .filter(
                        KnowledgeFact.chatbot_id == chatbot_id,
                        KnowledgeFact.event_date.isnot(None),
                        KnowledgeFact.temporal_status != "durable",
                        KnowledgeFact.deleted.is_(False),
                    )
                    .count()
                )
                assert candidates == 2

            from airunner_services.llm.managers.prompt_builder.upcoming_events import (
                upcoming_events_block,
            )
            block = upcoming_events_block(chatbot_id)

        assert "future event" in block
        assert "2099-01-01" in block
        assert "past stale" not in block

        with tenant_scope(tenant_key):
            with session_scope() as session:
                past = (
                    session.query(KnowledgeFact)
                    .filter(
                        KnowledgeFact.chatbot_id == chatbot_id,
                        KnowledgeFact.event_date
                        == datetime.date(2020, 1, 1),
                    )
                    .one()
                )
                assert past.temporal_status == "resolved"
                future = (
                    session.query(KnowledgeFact)
                    .filter(
                        KnowledgeFact.chatbot_id == chatbot_id,
                        KnowledgeFact.event_date
                        == datetime.date(2099, 1, 1),
                    )
                    .one()
                )
                assert future.temporal_status == "upcoming"
    finally:
        reset_engine()
        _drop_schema(tenant_key)


def _drop_schema(tenant_key: str) -> None:
    """Drop scratch tenant schema."""
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


def test_events_block_appears_without_narrative(
    _db: str,
) -> None:
    """_agent_memory_part returns events block even when no
    AgentMemory row exists (e.g. brand-new chatbot)."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )

    chatbot_id = 99996
    tenant_key = f"uev5_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            # Seed an upcoming fact — no AgentMemory row.
            with session_scope() as session:
                session.add(
                    KnowledgeFact(
                        fact_text="upcoming without narrative",
                        chatbot_id=chatbot_id,
                        subject="user",
                        event_date=datetime.date(2099, 12, 1),
                        temporal_status="upcoming",
                        recurring=False,
                    )
                )
                session.flush()

            # Mock an owner object with just a chatbot id.
            owner = type("Owner", (), {})()
            owner.chatbot = type("Chatbot", (), {})()
            owner.chatbot.id = chatbot_id

            from airunner_services.llm.managers.prompt_builder.parts import (
                _agent_memory_part,
            )

            result = _agent_memory_part(owner)

        assert result is not None, (
            "Should return events block even without narrative"
        )
        assert "Known upcoming/current events:" in result
        assert "upcoming without narrative" in result
        assert "2099-12-01" in result

    finally:
        reset_engine()
        _drop_schema(tenant_key)
