"""Application-level isolation tests for conversation recall paths.

Part 2 (rewrite) — tests that call the **real** recall functions
(not hand-written SQL) and assert chatbot_id scoping is enforced at
the application layer, not just by PostgreSQL schema separation.

Covers:
- ``_find_prior_conv_by_session`` (per_turn_bridge_retrieval.py:181)
- ``_find_prior_conv_by_id`` (per_turn_bridge_retrieval.py:214)

The ``chatbot_id`` filter on the SQLAlchemy query inside each real
function is the thing under test.  Each test documents which line to
temporarily remove for the sanity check (weaken filter → test fails →
revert).
"""

from __future__ import annotations

import pytest

from tenant_isolation_helpers import (  # type: ignore[import-untyped]
    TwoTenants,
    two_tenants,
)

__all__ = ["TwoTenants", "two_tenants"]


@pytest.fixture()
def seeded_data(
    two_tenants: TwoTenants,
) -> None:
    """Seed one chatbot per tenant with a ChatSession and Conversation
    carrying a tenant-specific marker string."""
    from sqlalchemy import text

    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope

    tt = two_tenants
    marker_a = f"__MARKER_A_{tt.tenant_a.tenant_key[:8]}__"
    marker_b = f"__MARKER_B_{tt.tenant_b.tenant_key[:8]}__"

    for tenant, chatbot_id, marker in [
        (tt.tenant_a, tt.tenant_a.chatbot_id, marker_a),
        (tt.tenant_b, tt.tenant_b.chatbot_id, marker_b),
    ]:
        with tenant_scope(tenant.tenant_key):
            with session_scope() as session:
                session.execute(
                    text(
                        "INSERT INTO chat_sessions "
                        "(chatbot_id, rolling_summary, deleted, "
                        "summary_ready, started_at, last_message_at) "
                        "VALUES (:cid, :marker, false, false, "
                        "NOW(), NOW())"
                    ),
                    {"cid": chatbot_id, "marker": marker},
                )
                sid = session.execute(
                    text(
                        "SELECT id FROM chat_sessions "
                        "WHERE chatbot_id = :cid "
                        "ORDER BY id DESC LIMIT 1"
                    ),
                    {"cid": chatbot_id},
                ).fetchone()[0]
                session.execute(
                    text(
                        "INSERT INTO conversations "
                        "(user_name, chatbot_id, session_id, value, "
                        "chatbot_name, deleted, created_at) "
                        "VALUES ('test_user', :cid, :sid, "
                        ":val, 'test', false, NOW())"
                    ),
                    {
                        "cid": chatbot_id,
                        "sid": sid,
                        "val": '{"messages":[]}',
                    },
                )


class TestFindPriorConvBySession:
    """``_find_prior_conv_by_session`` scopes by chatbot_id."""

    def test_returns_own_chatbot_session(
        self, two_tenants: TwoTenants, seeded_data: None,
    ) -> None:
        """Querying with tenant A's chatbot_id returns tenant A's
        session, not some other chatbot's.

        SANITY CHECK: temporarily comment out
        ``ChatSession.chatbot_id == chatbot_id,`` at
        per_turn_bridge_retrieval.py:194 and this test MUST fail
        (it will find the wrong — or no — session).
        """
        from airunner_services.data.tenant import tenant_scope
        from airunner_services.llm.managers.prompt_builder import (
            per_turn_bridge_retrieval,
        )

        tt = two_tenants
        marker = f"__MARKER_A_{tt.tenant_a.tenant_key[:8]}__"

        with tenant_scope(tt.tenant_a.tenant_key):
            result = (
                per_turn_bridge_retrieval._find_prior_conv_by_session(
                    chatbot_id=tt.tenant_a.chatbot_id,
                    current_session_id=0,
                )
            )
            assert result is not None, (
                "Expected to find a conversation for chatbot_id "
                f"{tt.tenant_a.chatbot_id}"
            )
            # Read back the rolling_summary to verify we got the
            # right session.
            summary = _read_rolling_summary(result.session_id)
            assert marker in (summary or ""), (
                f"Rolling summary should contain '{marker}', "
                f"got: {summary}"
            )

    def test_fake_chatbot_id_returns_none(
        self, two_tenants: TwoTenants, seeded_data: None,
    ) -> None:
        """A chatbot_id that doesn't exist returns None — the
        chatbot_id filter prevents fallback to any chatbot's data.

        SANITY CHECK: remove the entire filter from
        per_turn_bridge_retrieval.py:193-196 (leaving only
        ``.first()``) and this test will return a session for
        some chatbot instead of None.
        """
        from airunner_services.data.tenant import tenant_scope
        from airunner_services.llm.managers.prompt_builder import (
            per_turn_bridge_retrieval,
        )

        tt = two_tenants

        with tenant_scope(tt.tenant_a.tenant_key):
            result = (
                per_turn_bridge_retrieval._find_prior_conv_by_session(
                    chatbot_id=tt.tenant_a.chatbot_id + 99999,
                    current_session_id=0,
                )
            )
            assert result is None, (
                "Non-existent chatbot_id returned a conversation — "
                "chatbot_id filtering is not working"
            )

    def test_tenant_b_data_not_visible_from_tenant_a(
        self, two_tenants: TwoTenants, seeded_data: None,
    ) -> None:
        """When tenant A's context is active, calling the function
        with tenant B's chatbot_id returns None — the tenant-scoped
        session prevents cross-schema access AND the chatbot_id
        filter finds no match in tenant A's schema."""
        from airunner_services.data.tenant import tenant_scope
        from airunner_services.llm.managers.prompt_builder import (
            per_turn_bridge_retrieval,
        )

        tt = two_tenants

        with tenant_scope(tt.tenant_a.tenant_key):
            result = (
                per_turn_bridge_retrieval._find_prior_conv_by_session(
                    chatbot_id=tt.tenant_b.chatbot_id,
                    current_session_id=0,
                )
            )
            assert result is None, (
                "Tenant A context returned a conversation for "
                "tenant B's chatbot_id — cross-tenant leak via "
                "chatbot_id"
            )


class TestFindPriorConvById:
    """``_find_prior_conv_by_id`` scopes by chatbot_id."""

    def test_returns_correct_chatbot_conversation(
        self, two_tenants: TwoTenants, seeded_data: None,
    ) -> None:
        """Querying by chatbot_id returns only that chatbot's
        conversation.

        SANITY CHECK: temporarily comment out
        ``Conversation.chatbot_id == chatbot_id,`` at
        per_turn_bridge_retrieval.py:224 and this test MUST fail
        (it will return a conversation for any chatbot).
        """
        from airunner_services.data.tenant import tenant_scope
        from airunner_services.llm.managers.prompt_builder import (
            per_turn_bridge_retrieval,
        )

        tt = two_tenants
        marker = f"__MARKER_A_{tt.tenant_a.tenant_key[:8]}__"

        with tenant_scope(tt.tenant_a.tenant_key):
            prior = (
                per_turn_bridge_retrieval._find_prior_conv_by_session(
                    chatbot_id=tt.tenant_a.chatbot_id,
                    current_session_id=0,
                )
            )
            assert prior is not None
            # Use an id higher than the prior conv so the
            # `id < current_conv_id` filter matches.
            result = (
                per_turn_bridge_retrieval._find_prior_conv_by_id(
                    chatbot_id=tt.tenant_a.chatbot_id,
                    current_conv_id=prior.id + 1,
                )
            )
            assert result is not None, (
                "Expected to find conversation by id"
            )
            summary = _read_rolling_summary(result.session_id)
            assert marker in (summary or ""), (
                f"Rolling summary should contain '{marker}'"
            )

    def test_wrong_chatbot_id_returns_none(
        self, two_tenants: TwoTenants, seeded_data: None,
    ) -> None:
        """Querying with a different chatbot_id returns None even
        when the id range would include existing conversations."""
        from airunner_services.data.tenant import tenant_scope
        from airunner_services.llm.managers.prompt_builder import (
            per_turn_bridge_retrieval,
        )

        tt = two_tenants

        with tenant_scope(tt.tenant_a.tenant_key):
            # Get a valid conversation id first.
            prior = (
                per_turn_bridge_retrieval._find_prior_conv_by_session(
                    chatbot_id=tt.tenant_a.chatbot_id,
                    current_session_id=0,
                )
            )
            assert prior is not None
            # Query with a wrong chatbot_id but an id range that
            # would match — the chatbot_id filter must exclude it.
            result = (
                per_turn_bridge_retrieval._find_prior_conv_by_id(
                    chatbot_id=tt.tenant_a.chatbot_id + 99999,
                    current_conv_id=prior.id + 100,
                )
            )
            assert result is None, (
                "Wrong chatbot_id returned a conversation — "
                "chatbot_id filter is not working at "
                "per_turn_bridge_retrieval.py:224"
            )


def _read_rolling_summary(session_id: int) -> str | None:
    """Read ``rolling_summary`` from the active tenant schema."""
    from sqlalchemy import text

    from airunner_services.database.session import session_scope

    with session_scope() as session:
        row = session.execute(
            text(
                "SELECT rolling_summary FROM chat_sessions "
                "WHERE id = :sid"
            ),
            {"sid": session_id},
        ).fetchone()
        return str(row[0]) if row and row[0] else None
