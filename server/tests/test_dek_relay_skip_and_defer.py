"""Regression test for the Tier-2 DEK relay skip-and-defer path.

Part 3, item 4 of the architecture plan requires: when a Tier-2
Celery task runs and the DEK relay has no entry (unattended periodic
trigger, or relay TTL expired), the task must NOT raise
``DataEncryptionError`` or attempt DEK-encrypted work — it must log
the skip and return cleanly.

This is the single most important test in the plan: it guards the
exact bug the architecture exists to fix.
"""

from __future__ import annotations

from unittest.mock import patch



class TestDekRelaySkipAndDefer:
    """Verify Tier-2 tasks handle an empty DEK relay gracefully."""

    def test_task_dek_scope_returns_none_on_empty_relay(self) -> None:
        """``task_dek_scope`` yields None when no relay entry exists."""
        from airunner_services.tasks.task_helpers import task_dek_scope

        with patch(
            "airunner_services.tasks.task_helpers"
            ".dek_relay_get_and_delete",
            return_value=None,
        ), patch(
            "airunner_services.data.tenant.tenant_scope",
        ):
            with task_dek_scope("test_tenant", 999) as dek:
                assert dek is None, (
                    "task_dek_scope must yield None when relay is empty"
                )

    def test_task_dek_scope_no_keyring_does_not_crash(self) -> None:
        """Even without AIRUNNER_DATA_ENCRYPTION_KEYS, empty relay
        must not raise — the skip path runs before any crypto."""
        from airunner_services.tasks.task_helpers import task_dek_scope

        with patch(
            "airunner_services.tasks.task_helpers"
            ".dek_relay_get_and_delete",
            return_value=None,
        ), patch(
            "airunner_services.data.tenant.tenant_scope",
        ):
            with task_dek_scope("test_tenant", 999) as dek:
                assert dek is None

    def test_peek_false_uses_get_and_delete(self) -> None:
        """Default (peek=False) is true read-once: GET+DEL."""
        from airunner_services.tasks.task_helpers import task_dek_scope

        with patch(
            "airunner_services.tasks.task_helpers"
            ".dek_relay_get_and_delete",
            return_value=None,
        ) as mock_get_delete, patch(
            "airunner_services.tasks.task_helpers.dek_relay_get",
        ) as mock_get, patch(
            "airunner_services.data.tenant.tenant_scope",
        ):
            with task_dek_scope("test_tenant", 999):
                pass

        mock_get_delete.assert_called_once_with(999)
        mock_get.assert_not_called()

    def test_peek_true_uses_get_without_delete(self) -> None:
        """peek=True must not consume the relay entry — multiple
        Celery tasks in the same pipeline (chord parent, children,
        callback) all need to read the same entry."""
        from airunner_services.tasks.task_helpers import task_dek_scope

        with patch(
            "airunner_services.tasks.task_helpers.dek_relay_get",
            return_value=None,
        ) as mock_get, patch(
            "airunner_services.tasks.task_helpers"
            ".dek_relay_get_and_delete",
        ) as mock_get_delete, patch(
            "airunner_services.data.tenant.tenant_scope",
        ):
            with task_dek_scope("test_tenant", 999, peek=True):
                pass

        mock_get.assert_called_once_with(999)
        mock_get_delete.assert_not_called()

    def test_wrap_unwrap_dek_for_relay_roundtrip(self) -> None:
        """``wrap_dek_for_relay`` / ``unwrap_dek_from_relay`` round-trip
        produces the original DEK bytes when the global keyring is
        available."""
        import os

        from cryptography.fernet import Fernet

        from airunner_services.tasks.task_helpers import (
            unwrap_dek_from_relay,
            wrap_dek_for_relay,
        )

        # Ensure a keyring is configured for the test.
        os.environ.setdefault(
            "AIRUNNER_DATA_ENCRYPTION_KEYS",
            Fernet.generate_key().decode("ascii"),
        )

        original_dek = Fernet.generate_key()
        wrapped = wrap_dek_for_relay(original_dek)
        unwrapped = unwrap_dek_from_relay(wrapped)

        assert unwrapped == original_dek, (
            "DEK relay wrap/unwrap round-trip must preserve the DEK"
        )
