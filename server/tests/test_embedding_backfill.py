"""Tests for embedding_backfill — Part 5."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from airunner_services.database.session import reset_engine


# -- compute_turn_embedding ------------------------------------------------


def test_compute_success() -> None:
    fake = b"\x01\x02\x03"
    with patch(
        "projects.uwuchat.server.embedding_provider"
        ".get_embedding_provider"
    ), patch(
        "airunner_services.llm.managers.agent.pgvector_store"
        ".embed_texts",
        return_value=[[0.1, 0.2]],
    ), patch(
        "airunner_services.utils.crypto.fhe_helpers.l2_normalize",
        return_value=[0.1, 0.2],
    ), patch(
        "airunner_services.utils.crypto.fhe_helpers"
        ".encrypt_embedding",
        return_value=fake,
    ), patch(
        "airunner_services.data.tenant.get_account_id",
        return_value=1,
    ), patch(
        "airunner_services.knowledge_crud"
        "._get_or_create_public_context",
    ):
        from airunner_services.embedding_backfill import (
            compute_turn_embedding,
        )
        assert compute_turn_embedding("test") == fake


def test_compute_no_account() -> None:
    with patch(
        "projects.uwuchat.server.embedding_provider"
        ".get_embedding_provider"
    ), patch(
        "airunner_services.llm.managers.agent.pgvector_store"
        ".embed_texts",
        return_value=[[0.1]],
    ), patch(
        "airunner_services.data.tenant.get_account_id",
        return_value=None,
    ):
        from airunner_services.embedding_backfill import (
            compute_turn_embedding,
        )
        assert compute_turn_embedding("test") is None


def test_compute_embed_raises() -> None:
    with patch(
        "projects.uwuchat.server.embedding_provider"
        ".get_embedding_provider"
    ), patch(
        "airunner_services.llm.managers.agent.pgvector_store"
        ".embed_texts",
        side_effect=RuntimeError("down"),
    ):
        from airunner_services.embedding_backfill import (
            compute_turn_embedding,
        )
        assert compute_turn_embedding("test") is None


def test_compute_empty() -> None:
    with patch(
        "projects.uwuchat.server.embedding_provider"
        ".get_embedding_provider"
    ), patch(
        "airunner_services.llm.managers.agent.pgvector_store"
        ".embed_texts",
        return_value=[],
    ):
        from airunner_services.embedding_backfill import (
            compute_turn_embedding,
        )
        assert compute_turn_embedding("test") is None


def test_compute_none() -> None:
    with patch(
        "projects.uwuchat.server.embedding_provider"
        ".get_embedding_provider"
    ), patch(
        "airunner_services.llm.managers.agent.pgvector_store"
        ".embed_texts",
        return_value=[None],
    ):
        from airunner_services.embedding_backfill import (
            compute_turn_embedding,
        )
        assert compute_turn_embedding("test") is None


# -- DB fixture ------------------------------------------------------------


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


# -- Real fact backfill (mocked embedding boundary only) -------------------


def test_backfill_facts_real_embedding(_db: str) -> None:
    """Seed 5 facts with NULL embedding_enc, run real
    index_all_facts, verify DB shows non-null embedding_enc."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )

    chatbot_id = 99997
    tenant_key = f"emb_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                for i in range(5):
                    session.add(
                        KnowledgeFact(
                            fact_text=f"fact {i}",
                            chatbot_id=chatbot_id,
                            subject="user",
                            source_type="user_stated",
                            embedding_enc=None,
                        )
                    )
                session.flush()

            with patch(
                "airunner_services.data.tenant.get_account_id",
                return_value=1,
            ), patch(
                "airunner_services.knowledge_crud"
                "._get_or_create_public_context",
            ), patch(
                "airunner_services.llm.managers.agent"
                ".pgvector_store.embed_texts",
                return_value=[[0.1, 0.2] for _ in range(5)],
            ), patch(
                "airunner_services.utils.crypto.fhe_helpers"
                ".l2_normalize",
                side_effect=lambda v: v,
            ), patch(
                "airunner_services.utils.crypto.fhe_helpers"
                ".encrypt_embedding",
                return_value=b"\x01",
            ):
                from airunner_services.embedding_backfill import (
                    backfill_fact_embeddings,
                )
                result = backfill_fact_embeddings(
                    embedding_model=MagicMock()
                )

            assert result["total_embedded"] == 5

            with session_scope() as session:
                still_null = (
                    session.query(KnowledgeFact)
                    .filter(
                        KnowledgeFact.embedding_enc.is_(None),
                        KnowledgeFact.deleted.is_(False),
                    )
                    .count()
                )
                assert still_null == 0
    finally:
        reset_engine()
        _drop_schema(tenant_key)


# -- Real turn backfill (mocked embedding boundary only) -------------------


def test_backfill_turns_real_db(_db: str) -> None:
    """Seed 15 turns with NULL embedding_enc, run real
    backfill_turn_embeddings, verify all get non-null."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from sqlalchemy import text
    import datetime

    chatbot_id = 99998
    total = 15
    batch_size = 5
    tenant_key = f"emb2_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                now = datetime.datetime.now(datetime.UTC)
                # Minimal chatbot for FK.
                session.execute(
                    text(
                        "INSERT INTO chatbots (id,"
                        " allow_narrative_text, knowledge_mode,"
                        " language_proficiency, is_online,"
                        " has_blocked_user, blocked_by_user,"
                        " is_deceased, is_system_bot,"
                        " omnipotent_knowledge, deleted)"
                        " VALUES (:cid, false, 'omniscient',"
                        " 'fluent', true, false, false,"
                        " false, false, false, false)"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {"cid": chatbot_id},
                )
                # Minimal conversation for FK.
                session.execute(
                    text(
                        "INSERT INTO conversations"
                        " (id, chatbot_id, session_id,"
                        " title, chatbot_name, user_name, value, created_at, deleted)"
                        " VALUES (1, :cid, 1,"
                        " 'test', 'bot', 'user', '[]', :now, false)"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {"cid": chatbot_id, "now": now},
                )
                # Seed turns.
                for i in range(total):
                    session.execute(
                        text(
                            "INSERT INTO conversation_turns"
                            " (chatbot_id, session_id,"
                            " conversation_id, role, content,"
                            " turn_index, embedding_enc,"
                            " created_at, deleted)"
                            " VALUES (:cid, 1, 1, 'user', :ct,"
                            " :ti, NULL, :now, false)"
                        ),
                        {"cid": chatbot_id, "ct": f"t{i}",
                         "ti": i, "now": now},
                    )
                session.flush()

            with patch(
                "airunner_services.data.tenant.get_account_id",
                return_value=1,
            ), patch(
                "airunner_services.knowledge_crud"
                "._get_or_create_public_context",
            ), patch(
                "airunner_services.llm.managers.agent"
                ".pgvector_store.embed_texts",
                return_value=[[0.1, 0.2] for _ in range(batch_size)],
            ), patch(
                "airunner_services.utils.crypto.fhe_helpers"
                ".l2_normalize",
                side_effect=lambda v: v,
            ), patch(
                "airunner_services.utils.crypto.fhe_helpers"
                ".encrypt_embedding",
                return_value=b"\x01",
            ):
                from airunner_services.embedding_backfill import (
                    backfill_turn_embeddings,
                )
                result = backfill_turn_embeddings(
                    embedding_model=MagicMock(),
                    batch_size=batch_size,
                )

            assert result["total_embedded"] == total

            with session_scope() as session:
                nulls = session.execute(
                    text(
                        "SELECT COUNT(*) FROM conversation_turns"
                        " WHERE embedding_enc IS NULL"
                    )
                ).scalar()
                assert nulls == 0
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


def test_index_conversation_embedding_wired(_db: str) -> None:
    """_index_conversation stores embedding_enc via
    compute_turn_embedding. Mock it to return known bytes, verify
    the resulting ConversationTurn row."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from sqlalchemy import text
    import datetime

    chatbot_id = 99996
    fake_emb = b"\xde\xad\xbe\xef"
    tenant_key = f"emb3_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                now = datetime.datetime.now(datetime.UTC)
                session.execute(
                    text(
                        "INSERT INTO chatbots (id,"
                        " allow_narrative_text, knowledge_mode,"
                        " language_proficiency, is_online,"
                        " has_blocked_user, blocked_by_user,"
                        " is_deceased, is_system_bot,"
                        " omnipotent_knowledge, deleted)"
                        " VALUES (:cid, false, 'omniscient',"
                        " 'fluent', true, false, false,"
                        " false, false, false, false)"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {"cid": chatbot_id},
                )
                session.execute(
                    text(
                        "INSERT INTO conversations"
                        " (id, chatbot_id, session_id,"
                        " title, chatbot_name, user_name,"
                        " value, created_at, deleted)"
                        " VALUES (1, :cid, 1, 'test', 'bot',"
                        " 'user', '[]', :now, false)"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {"cid": chatbot_id, "now": now},
                )
                session.flush()

            with patch(
                "airunner_services.embedding_backfill.compute_turn_embedding",
                return_value=fake_emb,
            ):
                from airunner_services.llm.memory_updater import (
                    _index_conversation,
                )
                conv = type("Conv", (), {})()
                conv.id = 1
                conv.value = [
                    {"role": "user", "content": "hello world"}
                ]
                _index_conversation(conv, chatbot_id, 1)

            with session_scope() as session:
                rows = session.execute(
                    text(
                        "SELECT embedding_enc FROM"
                        " conversation_turns"
                        " WHERE chatbot_id = :cid"
                    ),
                    {"cid": chatbot_id},
                ).fetchall()
                assert len(rows) == 1
                assert rows[0][0] == fake_emb
    finally:
        reset_engine()
        _drop_schema(tenant_key)


def test_write_time_embedding_no_backfill(_db: str) -> None:
    """Turn created through _index_conversation has non-null
    embedding_enc immediately — no backfill, real write path, only
    true external boundaries mocked."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope
    from sqlalchemy import text
    import datetime

    chatbot_id = 99995
    tenant_key = f"emb4_{os.urandom(4).hex()}"
    try:
        with tenant_scope(tenant_key):
            with session_scope() as session:
                now = datetime.datetime.now(datetime.UTC)
                session.execute(
                    text(
                        "INSERT INTO chatbots (id,"
                        " allow_narrative_text, knowledge_mode,"
                        " language_proficiency, is_online,"
                        " has_blocked_user, blocked_by_user,"
                        " is_deceased, is_system_bot,"
                        " omnipotent_knowledge, deleted)"
                        " VALUES (:cid, false, 'omniscient',"
                        " 'fluent', true, false, false,"
                        " false, false, false, false)"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {"cid": chatbot_id},
                )
                session.execute(
                    text(
                        "INSERT INTO conversations"
                        " (id, chatbot_id, session_id,"
                        " title, chatbot_name, user_name,"
                        " value, created_at, deleted)"
                        " VALUES (1, :cid, 1, 'test', 'bot',"
                        " 'user', '[]', :now, false)"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {"cid": chatbot_id, "now": now},
                )
                session.flush()

            # Mock only true external boundaries of
            # compute_turn_embedding; let the real
            # _index_conversation run.
            with patch(
                "projects.uwuchat.server.embedding_provider"
                ".get_embedding_provider"
            ), patch(
                "airunner_services.llm.managers.agent"
                ".pgvector_store.embed_texts",
                return_value=[[0.1, 0.2]],
            ), patch(
                "airunner_services.utils.crypto.fhe_helpers"
                ".l2_normalize",
                side_effect=lambda v: v,
            ), patch(
                "airunner_services.utils.crypto.fhe_helpers"
                ".encrypt_embedding",
                return_value=b"\x01",
            ), patch(
                "airunner_services.data.tenant.get_account_id",
                return_value=1,
            ), patch(
                "airunner_services.knowledge_crud"
                "._get_or_create_public_context",
            ):
                from airunner_services.llm.memory_updater import (
                    _index_conversation,
                )
                conv = type("Conv", (), {})()
                conv.id = 1
                conv.value = [
                    {"role": "user", "content": "hello"}
                ]
                _index_conversation(conv, chatbot_id, 1)

            with session_scope() as session:
                row = session.execute(
                    text(
                        "SELECT embedding_enc FROM"
                        " conversation_turns"
                        " WHERE chatbot_id = :cid"
                    ),
                    {"cid": chatbot_id},
                ).fetchone()
                assert row is not None
                assert row[0] is not None
    finally:
        reset_engine()
        _drop_schema(tenant_key)
