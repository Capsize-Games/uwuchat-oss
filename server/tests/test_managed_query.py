"""Tests for ManagedQuery and TransactionHandle on the new query-builder API.

These tests validate the builder construction, terminal methods, and
that the expunge / dataclass conversion happens without raising
DetachedInstanceError.
"""

from __future__ import annotations

import pytest

from airunner_services.database.models.conversation import Conversation


class TestManagedQueryConstruction:
    """Builder methods chain and terminal methods execute."""

    def test_builder_filter_order_limit(self):
        """Verify filter, order_by, offset, limit chain."""
        q = (
            Conversation.objects.query()
            .filter(
                Conversation.user_name == "test",
            )
            .order_by(
                Conversation.created_at.desc(),
            )
            .offset(10)
            .limit(5)
        )

        assert q._filters
        assert q._order_by_clauses
        assert q._offset_val == 10
        assert q._limit_val == 5

    def test_builder_all_returns_dataclasses(self):
        """all() returns Conversation dataclass instances."""
        rows = Conversation.objects.query().limit(1).all()
        assert isinstance(rows, list)
        if rows:
            # Dataclasses have attribute access, not column proxies
            assert hasattr(rows[0], "id")
            assert hasattr(rows[0], "title")
            assert hasattr(rows[0], "user_name")

    def test_builder_first_returns_dataclass_or_none(self):
        """first() returns a Conversation dataclass or None."""
        row = Conversation.objects.query().limit(1).first()
        if row is not None:
            assert hasattr(row, "id")

    def test_builder_count_returns_int(self):
        """count() returns an integer."""
        count = Conversation.objects.query().count()
        assert isinstance(count, int)

    def test_builder_filter_by(self):
        """filter_by works with keyword arguments."""
        count = (
            Conversation.objects.query()
            .filter_by(user_name="nonexistent_user_12345")
            .count()
        )
        assert count == 0

    def test_builder_multi_entity_all(self):
        """Multi-entity query returns Row objects."""
        from sqlalchemy import func

        rows = (
            Conversation.objects.query(
                Conversation.user_name,
                func.count(Conversation.id),
            )
            .group_by(Conversation.user_name)
            .limit(5)
            .all()
        )
        assert isinstance(rows, list)


class TestManagedQueryNoDetachedInstanceError:
    """Verify no DetachedInstanceError from expire_on_commit."""

    def test_all_does_not_raise_detached(self):
        """all() returns usable dataclasses."""
        rows = Conversation.objects.query().limit(1).all()
        for row in rows:
            # Accessing attributes after session close should work
            _ = row.id
            _ = row.title
            _ = row.user_name
            _ = row.chatbot_name
            _ = row.value

    def test_first_does_not_raise_detached(self):
        """first() returns usable dataclass."""
        row = Conversation.objects.query().limit(1).first()
        if row:
            _ = row.id
            _ = row.title

    def test_scalar_returns_value(self):
        """scalar() returns first column of first row."""
        val = (
            Conversation.objects.query(Conversation.id)
            .order_by(Conversation.id.asc())
            .limit(1)
            .scalar()
        )
        if val is not None:
            assert isinstance(val, int)

    def test_scalars_returns_list(self):
        """scalars() returns first column of all rows."""
        vals = Conversation.objects.query(Conversation.id).limit(3).scalars()
        assert isinstance(vals, list)


class TestTransactionHandle:
    """Multi-step operations within a transaction context."""

    def test_transaction_add_and_read(self):
        """Create a row and read it back within the transaction."""
        with Conversation.objects.transaction() as tx:
            conv = Conversation(
                title="test_tx_title",
                user_name="test_tx_user",
                chatbot_name="test_tx_bot",
            )
            tx.add(conv)
            tx.flush()

            # Read back
            found = (
                tx.query(Conversation)
                .filter(Conversation.title == "test_tx_title")
                .first()
            )
            assert found is not None
            assert found.title == "test_tx_title"

        # Clean up
        Conversation.objects.query().filter(
            Conversation.title == "test_tx_title",
        ).delete(synchronize_session=False)

    def test_transaction_deletes_within_block(self):
        """Delete a row inside a transaction."""
        with Conversation.objects.transaction() as tx:
            conv = Conversation(
                title="test_tx_delete",
                user_name="test_tx_user",
                chatbot_name="test_tx_bot",
            )
            tx.add(conv)
            tx.flush()

            tx.delete(conv)
            tx.flush()

            found = (
                tx.query(Conversation)
                .filter(Conversation.title == "test_tx_delete")
                .first()
            )
            assert found is None


class TestConversationInspectorRoutePattern:
    """Validate the pattern used by the conversation inspector."""

    def test_list_with_search(self):
        """Filter conversations matching the route's query pattern."""
        from sqlalchemy import or_

        builder = Conversation.objects.query().order_by(
            Conversation.created_at.desc(),
        )
        search = "test"
        q = f"%{search}%"
        builder = builder.filter(
            or_(
                Conversation.title.ilike(q),
                Conversation.user_name.ilike(q),
            ),
        )
        rows = builder.limit(5).all()
        assert isinstance(rows, list)

    def test_flow_single_conversation(self):
        """Query a single conversation by id (flow endpoint pattern)."""
        # First get any conversation id
        conv = Conversation.objects.query().limit(1).first()
        if conv is None:
            pytest.skip("No conversations in database")

        # Then query it by id (the flow endpoint pattern)
        found = (
            Conversation.objects.query()
            .filter(Conversation.id == conv.id)
            .first()
        )
        assert found is not None
        assert found.id == conv.id
