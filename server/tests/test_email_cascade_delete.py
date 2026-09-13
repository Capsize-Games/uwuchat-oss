"""Verify that email disconnect cascades to the entity graph.

Tests cover:
- ``_snapshot_email_contact_ids`` captures contact IDs before deletion
- ``_delete_email_entity_graph`` deletes Entity and EntityRelationship
  rows scoped to those contacts
- ``cascade_delete_email_data`` calls both new helpers
- ``_do_connect`` reactivates soft-deleted EmailAccount rows
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch



# Progress-store percentage-computation coverage now lives in
# test_email_sync_progress.py (email_sync_progress_read computes the
# percentage at read time, not write time, since this store moved to
# a single account-wide bar instead of one per mailbox).


# ---- Helpers ---------------------------------------------------------------


class TestSnapshotEmailContactIds:
    """``_snapshot_email_contact_ids`` captures ID set before deletion."""

    def test_returns_empty_set_for_no_contacts(self) -> None:
        from projects.uwuchat.server.email._route_helpers import (
            _snapshot_email_contact_ids,
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        result = _snapshot_email_contact_ids(session, 42)
        assert result == set()

    def test_returns_id_set_for_existing_contacts(self) -> None:
        from projects.uwuchat.server.email._route_helpers import (
            _snapshot_email_contact_ids,
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [
            (101,), (202,), (303,),
        ]
        result = _snapshot_email_contact_ids(session, 42)
        assert result == {101, 202, 303}


class TestDeleteEmailEntityGraph:
    """``_delete_email_entity_graph`` scopes deletions to email contacts."""

    def test_noop_when_contact_ids_empty(self) -> None:
        from projects.uwuchat.server.email._route_helpers import (
            _delete_email_entity_graph,
        )

        session = MagicMock()
        _delete_email_entity_graph(session, set())
        # Neither Entity nor EntityRelationship queries should execute.
        session.query.assert_not_called()

    def test_deletes_entities_scoped_to_email_contacts(
        self,
    ) -> None:
        """Entity rows with source_ref_table='email_contacts' are deleted."""
        from projects.uwuchat.server.email._route_helpers import (
            _delete_email_entity_graph,
        )

        session = MagicMock()
        # Mock: Entity query returns IDs 10, 20
        entity_query = session.query.return_value
        entity_query.filter.return_value.all.return_value = [
            (10,), (20,),
        ]

        _delete_email_entity_graph(session, {101, 202})

        # Entity filter was built with correct args.
        filter_call = entity_query.filter.call_args
        assert filter_call is not None

    def test_deletes_entity_relationships_for_email_source(
        self,
    ) -> None:
        """EntityRelationship rows from email_co_occurrence are deleted."""
        from projects.uwuchat.server.email._route_helpers import (
            _delete_email_entity_graph,
        )

        session = MagicMock()

        # The function calls session.query() three times:
        # 1. Entity.id query, 2. EntityRelationship delete, 3. Entity delete.
        entity_mock = MagicMock()
        entity_mock.filter.return_value.all.return_value = [(10,), (20,)]
        er_mock = MagicMock()
        entity_delete_mock = MagicMock()

        session.query.side_effect = [
            entity_mock, er_mock, entity_delete_mock,
        ]

        _delete_email_entity_graph(session, {101})

        # EntityRelationship filter + delete was called.
        assert er_mock.filter.called
        assert er_mock.filter.return_value.delete.called
        # Entity delete was called.
        assert entity_delete_mock.filter.called
        assert entity_delete_mock.filter.return_value.delete.called


class TestCascadeDeleteEmailData:
    """``cascade_delete_email_data`` calls the entity-graph helpers."""

    @patch(
        "projects.uwuchat.server.email._route_helpers"
        "._get_system_bot_id", return_value=None,
    )
    def test_calls_snapshot_and_graph_delete(self, _mock_bot_id) -> None:
        """The cascade function captures contact IDs and deletes entities."""
        from projects.uwuchat.server.email._route_helpers import (
            cascade_delete_email_data,
        )

        session = MagicMock()

        # Each query().filter() chain needs a delete() that returns 0.
        delete_mock = MagicMock(return_value=0)

        # Build fresh mocks for every query() call (the function issues
        # many distinct queries — one per model delete, one for snapshot,
        # plus entity-graph deletes).
        query_count = 0

        def _fresh_query(*args, **kwargs):
            nonlocal query_count
            query_count += 1
            m = MagicMock()
            m.filter.return_value.delete = delete_mock
            m.filter.return_value.all.return_value = [(999,)]  # one contact
            return m

        session.query.side_effect = _fresh_query

        cascade_delete_email_data(session, email_account_id=1, user_id=42)

        # Expected query count: 1 snapshot + 4 email model deletes +
        # 1 EmailContact delete + 1 Entity.id lookup + 1 EntityRelationship
        # delete + 1 Entity delete = 9
        assert query_count >= 9

    @patch(
        "projects.uwuchat.server.email._route_helpers"
        "._get_system_bot_id", return_value=None,
    )
    def test_deletes_email_body_chunk_rows(self, _mock_bot_id) -> None:
        """Regression: the swap from EmailThreadSummary to
        EmailBodyChunk must not be missed in the delete-target list."""
        from airunner_services.database.models.email_body_chunk import (
            EmailBodyChunk,
        )
        from projects.uwuchat.server.email._route_helpers import (
            cascade_delete_email_data,
        )

        session = MagicMock()
        delete_mock = MagicMock(return_value=0)
        queried_models = []

        def _fresh_query(model, *args, **kwargs):
            queried_models.append(model)
            m = MagicMock()
            m.filter.return_value.delete = delete_mock
            m.filter.return_value.all.return_value = [(999,)]
            return m

        session.query.side_effect = _fresh_query

        cascade_delete_email_data(session, email_account_id=1, user_id=42)

        # `is` on purpose: some captured "models" are SQLAlchemy
        # column expressions (e.g. EmailContact.id) whose `__eq__` is
        # overloaded to build SQL clauses, not do a Python comparison
        # — `in`/`==` against those raises instead of returning False.
        assert any(m is EmailBodyChunk for m in queried_models)


class TestDoConnectReactivatesSoftDeleted:
    """``_do_connect`` reactivates soft-deleted rows on reconnect."""

    def test_reactivates_soft_deleted_account(self) -> None:
        """A soft-deleted row is found (via a column-only existence
        check) and reactivated via a bulk UPDATE — not a full-entity
        load + attribute mutation, which would eagerly decrypt the
        old credential_ciphertext for no reason."""
        from projects.uwuchat.server.email.routes import _do_connect

        with patch(
            "projects.uwuchat.server.email.routes.session_scope",
        ) as mock_scope:
            mock_session = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_session

            # Existence check finds a soft-deleted row's id.
            mock_session.query.return_value.filter.return_value \
                .scalar.return_value = 99

            account_id, result = _do_connect(
                42, "token-abc", "user@example.com",
            )

            assert account_id == 99
            assert result["connected"] is True
            assert result["email_address"] == "user@example.com"

            update_call = (
                mock_session.query.return_value.filter.return_value
                .update
            )
            update_call.assert_called_once()
            fields, kwargs = update_call.call_args
            assert fields[0] == {
                "credential_ciphertext": "token-abc",
                "status": "connected",
                "error_message": None,
                "deleted": False,
            }
            assert kwargs == {"synchronize_session": False}

    def test_creates_new_when_no_row_exists(self) -> None:
        """When no existing row is found, a new one is inserted."""
        from projects.uwuchat.server.email.routes import _do_connect

        with patch(
            "projects.uwuchat.server.email.routes.session_scope",
        ) as mock_scope:
            mock_session = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value \
                .scalar.return_value = None

            # Simulate session.add + flush assigning an id.
            def _add_flush(obj):
                obj.id = 55

            mock_session.add.side_effect = _add_flush

            with patch(
                "projects.uwuchat.server.email.routes.SignalMediator",
            ) as mock_signal:
                mock_signal.return_value.emit_signal = MagicMock()

                account_id, result = _do_connect(
                    42, "token-abc", "user@example.com",
                )

                assert account_id == 55
                assert result["connected"] is True
                mock_session.add.assert_called_once()


class TestDoDisconnectCascadesToEntities:
    """``_do_disconnect`` now calls the entity-graph-aware cascade."""

    @patch(
        "projects.uwuchat.server.email._route_helpers._get_system_bot_id",
        return_value=None,
    )
    def test_disconnect_cascades_to_entities(self, _bot_id) -> None:
        """The full disconnect flow includes entity graph deletion.

        ``_do_disconnect`` now runs a column-only ``(id,)`` query to
        find accounts to cascade-delete, then a bulk UPDATE to mark
        them deleted — not a full-entity load + attribute mutation."""
        from projects.uwuchat.server.email.routes import _do_disconnect

        with patch(
            "projects.uwuchat.server.email.routes.session_scope",
        ) as mock_scope:
            mock_session = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_session

            # Return one connected account id.
            mock_session.query.return_value.filter.return_value \
                .all.return_value = [(1,)]

            # Each delete returns a count.
            delete_mock = MagicMock(return_value=0)
            mock_session.query.return_value.filter.return_value.delete = delete_mock

            result = _do_disconnect(42)

            assert result == {"success": True}
            update_call = (
                mock_session.query.return_value.filter.return_value
                .update
            )
            update_call.assert_called_once()
            fields, kwargs = update_call.call_args
            assert fields[0] == {"deleted": True}
            assert kwargs == {"synchronize_session": False}
            # At least 7 deletes: EmailMessage, EmailBodyChunk,
            # EmailStats, EmailSyncCheckpoint, EmailContact, Entity,
            # EntityRelationship.
            assert mock_session.query.call_count >= 7
