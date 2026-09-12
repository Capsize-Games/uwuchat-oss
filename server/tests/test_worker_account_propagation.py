"""Tests for account_id propagation across the enqueue→worker-thread
boundary (Part 3 regression coverage).

The contextvar-across-thread code in ``Worker`` is the kind most prone
to silent regression — someone touches ``run_thread`` or
``get_last_item`` in six months without knowing this invariant exists.
"""

from __future__ import annotations

from typing import Any


from airunner_services.data.tenant import (
    account_id_scope,
    get_account_id,
    get_tenant_key,
)
from airunner_services.workers.worker import Worker


class _TestWorker(Worker):
    """Minimal concrete worker that records the account_id and tenant_key
    seen in ``handle_message``."""

    queue_type = Worker.queue_type.GET_NEXT_ITEM

    def __init__(self) -> None:
        super().__init__()
        self.seen_account_ids: list[int | None] = []
        self.seen_tenant_keys: list[str | None] = []

    def handle_message(self, message: Any) -> None:
        """Record the active contextvar values seen on the worker
        thread — the exact values that would reach
        ``PipelineTokenUsage.account_id``."""
        self.seen_account_ids.append(get_account_id())
        self.seen_tenant_keys.append(get_tenant_key())


class TestAccountIdPropagation:
    """account_id survives enqueue, does not bleed across items."""

    def test_account_id_survives_enqueue_to_handle_message(self) -> None:
        """Enqueue under account_id=42 → handle_message sees 42."""
        worker = _TestWorker()
        with account_id_scope(42):
            worker.add_to_queue({"test": "a"})
        worker.run_thread()
        assert worker.seen_account_ids == [42]

    def test_tenant_key_also_survives(self) -> None:
        """Sanity: tenant_key propagation (existing behaviour)
        still works alongside the new account_id path."""
        worker = _TestWorker()
        from airunner_services.data.tenant import (
            set_tenant_key,
            reset_tenant_key,
        )

        token = set_tenant_key("test-tenant")
        try:
            with account_id_scope(7):
                worker.add_to_queue({"test": "b"})
        finally:
            reset_tenant_key(token)
        worker.run_thread()
        assert worker.seen_account_ids == [7]
        assert worker.seen_tenant_keys == ["test-tenant"]

    def test_account_id_does_not_bleed_into_next_item(self) -> None:
        """Enqueue item A with account_id=42, then item B with no
        account_id scope → item B sees None, not stale 42."""
        worker = _TestWorker()
        with account_id_scope(42):
            worker.add_to_queue({"test": "with_id"})
        worker.add_to_queue({"test": "no_id"})
        worker.run_thread()
        worker.run_thread()
        assert worker.seen_account_ids == [42, None]

    def test_no_account_id_yields_none(self) -> None:
        """When nothing sets the account_id ContextVar,
        handle_message sees None."""
        worker = _TestWorker()
        worker.add_to_queue({"test": "anon"})
        worker.run_thread()
        assert worker.seen_account_ids == [None]
