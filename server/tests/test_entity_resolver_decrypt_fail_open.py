"""Regression test: entity resolution must not crash the whole sync
pipeline when an existing Entity row can't be decrypted.

Context: a legacy Entity row encrypted under a since-rotated/expired
DEK raises ``DataEncryptionError`` the moment SQLAlchemy hydrates it
(``UserEncryptedText.process_result_value``), not lazily on attribute
access. Before this fix, ``_resolve_entity_uncached``'s lookup query
had no guard for this — a single stale row killed the entire email
sync task silently, with no traceback in the default log level and no
completion ever written, leaving the client's progress bar stuck
"active" forever (even across page reloads).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestResolveEntityDecryptFailOpen:
    def test_undecryptable_existing_row_treated_as_not_found(
        self,
    ) -> None:
        """A DataEncryptionError from the lookup query must be caught
        and treated as 'no existing row', not propagate and crash."""
        from airunner_services.entity_resolver import (
            _resolve_entity_uncached,
        )
        from airunner_services.utils.crypto.data_encryption import (
            DataEncryptionError,
        )

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.side_effect = (
            DataEncryptionError("undecryptable")
        )

        new_row = MagicMock()
        new_row.id = 42

        def _add(row):
            row.id = 42

        mock_session.add.side_effect = _add

        with patch(
            "airunner_services.entity_resolver.session_scope",
        ) as mock_scope:
            mock_scope.return_value.__enter__.return_value = mock_session

            result = _resolve_entity_uncached(
                "Some Contact", 1, "deadbeef", "person",
                "email_contact", "email_contacts", 7,
            )

        # Falls through to the create path instead of raising.
        assert mock_session.add.called
        assert result == 42

    def test_normal_lookup_still_returns_existing_id(self) -> None:
        """No regression on the happy path: a real hit still short-
        circuits without attempting to create a duplicate."""
        from airunner_services.entity_resolver import (
            _resolve_entity_uncached,
        )

        existing = MagicMock()
        existing.id = 99
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = existing

        with patch(
            "airunner_services.entity_resolver.session_scope",
        ) as mock_scope:
            mock_scope.return_value.__enter__.return_value = mock_session

            result = _resolve_entity_uncached(
                "Some Contact", 1, "deadbeef", "person",
                "email_contact", "email_contacts", 7,
            )

        assert result == 99
        mock_session.add.assert_not_called()
