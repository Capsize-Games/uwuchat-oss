"""Unit tests for the service-owned JobTracker.

Covers the full job lifecycle (create, progress, metadata, complete,
fail, cancel), result waiting, cleanup of terminal jobs, and the
singleton behaviour.
"""

from __future__ import annotations

import asyncio

import pytest

from airunner_services.utils.job_tracker import (
    JobState,
    JobStatus,
    JobTracker,
)


@pytest.fixture()
def tracker() -> JobTracker:
    """Return one isolated tracker instance for each test.

    ``JobTracker`` is a process-wide singleton, so clear any state
    left behind by the previous test to keep assertions isolated.
    """
    instance = JobTracker()
    instance._jobs.clear()
    instance._futures.clear()
    return instance


class TestJobLifecycle:
    """Tests for the happy-path job lifecycle."""

    async def test_create_job_returns_pending_state(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job(metadata={"k": "v"}, account_id=7)
        state = await tracker.get_status(job_id)
        assert state is not None
        assert state.status == JobStatus.PENDING
        assert state.progress == 0.0
        assert state.account_id == 7
        assert state.metadata == {"k": "v"}
        assert state.result is None
        assert state.error is None

    async def test_update_progress_sets_status(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        await tracker.update_progress(job_id, 42.5, JobStatus.RUNNING)
        state = await tracker.get_status(job_id)
        assert state is not None
        assert state.progress == 42.5
        assert state.status == JobStatus.RUNNING

    async def test_update_metadata_merges(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job(metadata={"a": 1})
        await tracker.update_metadata(job_id, {"b": 2})
        state = await tracker.get_status(job_id)
        assert state is not None
        assert state.metadata == {"a": 1, "b": 2}

    async def test_complete_job_resolves_future(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        result = await tracker.complete_job(job_id, {"ok": True})
        state = await tracker.get_status(job_id)
        assert result is None
        assert state is not None
        assert state.status == JobStatus.COMPLETED
        assert state.progress == 100.0
        assert state.result == {"ok": True}
        assert await tracker.get_result(job_id) == {"ok": True}

    async def test_get_result_waits_for_completion(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()

        async def complete_later() -> None:
            await asyncio.sleep(0.01)
            await tracker.complete_job(job_id, "done")

        task = asyncio.ensure_future(complete_later())
        assert await tracker.get_result(job_id, timeout=5.0) == "done"
        await task


class TestJobFailures:
    """Tests for failure and cancellation paths."""

    async def test_fail_job_records_error(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        await tracker.fail_job(job_id, "boom")
        state = await tracker.get_status(job_id)
        assert state is not None
        assert state.status == JobStatus.FAILED
        assert state.error == "boom"

    async def test_fail_job_raises_on_get_result(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        await tracker.fail_job(job_id, "boom")
        with pytest.raises(Exception, match="boom"):
            await tracker.get_result(job_id)

    async def test_cancel_job_sets_cancelled_status(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        assert await tracker.cancel_job(job_id) is True
        state = await tracker.get_status(job_id)
        assert state is not None
        assert state.status == JobStatus.CANCELLED

    async def test_cancel_completed_job_returns_false(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        await tracker.complete_job(job_id, "done")
        assert await tracker.cancel_job(job_id) is False

    async def test_cancelled_get_result_raises(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        await tracker.cancel_job(job_id)
        with pytest.raises(Exception, match="cancelled"):
            await tracker.get_result(job_id)

    async def test_get_result_times_out_for_pending_job(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        with pytest.raises(asyncio.TimeoutError):
            await tracker.get_result(job_id, timeout=0.01)


class TestJobLookups:
    """Tests for unknown-job handling and listing."""

    async def test_unknown_job_status_returns_none(
        self,
        tracker: JobTracker,
    ) -> None:
        assert await tracker.get_status("missing") is None

    async def test_unknown_job_updates_are_noops(
        self,
        tracker: JobTracker,
    ) -> None:
        assert await tracker.update_progress("missing", 50.0) is None
        assert await tracker.update_metadata("missing", {"a": 1}) is None
        assert await tracker.complete_job("missing", "x") is None
        assert await tracker.fail_job("missing", "x") is None
        assert await tracker.cancel_job("missing") is False

    async def test_unknown_job_get_result_raises(
        self,
        tracker: JobTracker,
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            await tracker.get_result("missing")

    async def test_get_all_jobs_returns_shallow_copy(
        self,
        tracker: JobTracker,
    ) -> None:
        await tracker.create_job()
        jobs = tracker.get_all_jobs()
        assert len(jobs) == 1
        jobs.clear()
        assert len(tracker.get_all_jobs()) == 1


class TestJobCleanup:
    """Tests for old terminal-job cleanup."""

    async def test_cleanup_removes_old_terminal_jobs(
        self,
        tracker: JobTracker,
    ) -> None:
        done_id = await tracker.create_job()
        await tracker.complete_job(done_id, "done")
        running_id = await tracker.create_job()
        await tracker.update_progress(running_id, 1.0, JobStatus.RUNNING)

        await tracker.cleanup_old_jobs(max_age_seconds=-1)

        assert await tracker.get_status(done_id) is None
        assert await tracker.get_status(running_id) is not None

    async def test_cleanup_keeps_fresh_terminal_jobs(
        self,
        tracker: JobTracker,
    ) -> None:
        job_id = await tracker.create_job()
        await tracker.complete_job(job_id, "done")
        await tracker.cleanup_old_jobs(max_age_seconds=3600)
        assert await tracker.get_status(job_id) is not None


class TestJobState:
    """Tests for JobState serialization."""

    def test_to_dict_contains_all_fields(self) -> None:
        state = JobState(job_id="j1", status=JobStatus.PENDING)
        data = state.to_dict()
        assert data["job_id"] == "j1"
        assert data["status"] == "pending"
        assert data["progress"] == 0.0
        assert data["result"] is None
        assert data["error"] is None
        assert "created_at" in data
        assert "updated_at" in data
        assert data["metadata"] == {}

    def test_job_status_values(self) -> None:
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"
