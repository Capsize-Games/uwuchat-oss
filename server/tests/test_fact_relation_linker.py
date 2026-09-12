"""Tests for fact_relation_linker — Part 4."""
from __future__ import annotations

import datetime
import os
from unittest.mock import MagicMock, patch

import pytest

from airunner_services.database.session import reset_engine


def test_link_no_embedding() -> None:
    from airunner_services.fact_relation_linker import (
        link_fact_relations,
    )
    assert link_fact_relations(1, "test", 1, embedding_model=None) == 0


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip("No test database configured")
    if not db_url.startswith("postgres"):
        pytest.skip("Requires PostgreSQL")
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DB_TENANCY", "multi")
    reset_engine()
    from airunner_services.database.setup_database import setup_database
    try:
        setup_database()
    except Exception:
        pytest.skip("Database unavailable")
    return db_url


def test_link_fact_relations_real(_db: str) -> None:
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )
    from airunner_services.database.models.knowledge_fact_relation import (
        KnowledgeFactRelation,
    )

    chatbot_id = 99999
    tenant_key = f"rel_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                old = KnowledgeFact(
                    fact_text="release was scheduled for June",
                    chatbot_id=chatbot_id,
                    subject="user",
                    source_type="user_stated",
                    temporal_status="resolved",
                    event_date=datetime.date(2020, 6, 1),
                    recurring=False,
                )
                session.add(old)
                session.flush()
                old_id = old.id

                new = KnowledgeFact(
                    fact_text="the release shipped on time",
                    chatbot_id=chatbot_id,
                    subject="user",
                    source_type="user_stated",
                    temporal_status="durable",
                    recurring=False,
                )
                session.add(new)
                session.flush()
                new_id = new.id
                new_text = str(new.fact_text or "")

            mock_c = MagicMock()
            mock_c.id = old_id
            mock_c.chatbot_id = chatbot_id

            import airunner_services.fact_relation_linker as mod

            with patch.object(
                mod, "_similar_facts", return_value=[mock_c]
            ), patch.object(
                mod, "_classify_relation", return_value="supersedes"
            ):
                count = mod.link_fact_relations(
                    new_id, new_text, chatbot_id,
                    embedding_model=MagicMock(),
                )

            assert count == 1

            rels = (
                KnowledgeFactRelation.objects.query()
                .filter(
                    KnowledgeFactRelation.fact_id == new_id,
                    KnowledgeFactRelation.deleted.is_(False),
                )
                .all()
            )
            assert len(rels) == 1
            assert rels[0].relation_type == "supersedes"
            assert rels[0].related_fact_id == old_id

            with session_scope() as s2:
                orig = s2.query(KnowledgeFact).filter(
                    KnowledgeFact.id == old_id
                ).one()
                assert orig.temporal_status == "resolved"
    finally:
        reset_engine()
        _drop_schema(tenant_key)


def _drop_schema(tenant_key: str) -> None:
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
