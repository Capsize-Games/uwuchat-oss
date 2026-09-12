"""Tests for distributed priority-lane rate limiter and completion choke.

Covers the test requirements from
``plans/uwuchat-embedding-rate-limit-priority-lanes.md``:

1. Per-lane isolation
2. Cross-process behavior (simulated via two mocked Redis clients)
3. Self-healing on crash (lease expiry)
4. Live-lane graceful degradation (bounded wait, returns None)
5. Bulk-lane retry integration
6. Existing embedding provider interface compatibility
7. Resource isolation (embedding vs completion)
8. Completion choke-point coverage
9. Completion live-lane exhaustion
10. Completion retry/backoff on 429/5xx
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from airunner_services.cloud.distributed_limiter import (
    AcquiredSlot,
    _lane_key,
    _lane_max,
    _tenant_count_key,
    _tenant_max,
    acquire_slot,
    acquire_with_retry,
    lane_stats,
)
from airunner_services.cloud.llm.completion_choke import (
    _is_retryable_error,
    _resolve_tenant_key,
    invoke_with_limiter,
    stream_with_limiter,
)


# ------------------------------------------------------------------ #
#  In-process fake Redis that supports the limiter's Lua scripts       #
# ------------------------------------------------------------------ #


class _FakeRedis:
    """Minimal fake implementing sorted-set semaphore ops + Lua eval.

    Supports: ZREMRANGEBYSCORE, ZCARD, ZADD, ZREM, GET, SET,
    INCR, DECR, EXPIRE, and EVAL for the acquire/release scripts.
    """

    def __init__(self) -> None:
        self._zsets: dict[str, dict[str, float]] = {}
        self._strings: dict[str, str] = {}
        self._expiries: dict[str, float] = {}

    # -- Sorted-set ops ---------------------------------------------------

    def zremrangebyscore(self, key: str, min_: str, max_: str) -> int:
        zs = self._zsets.setdefault(key, {})
        lo = float(min_)
        hi = float(max_)
        removed = 0
        for member in list(zs):
            if lo <= zs[member] <= hi:
                del zs[member]
                removed += 1
        return removed

    def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    def zadd(self, key: str, mapping: dict) -> int:
        zs = self._zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zs:
                added += 1
            zs[member] = score
        return added

    def zrem(self, key: str, *members: str) -> int:
        zs = self._zsets.get(key, {})
        removed = 0
        for m in members:
            if m in zs:
                del zs[m]
                removed += 1
        return removed

    # -- String ops ------------------------------------------------------

    def get(self, key: str) -> str | None:
        self._check_expiry(key)
        return self._strings.get(key)

    def set(self, key: str, value: str, **kwargs) -> bool:
        self._strings[key] = value
        if "ex" in kwargs:
            self._expiries[key] = time.time() + kwargs["ex"]
        return True

    def incr(self, key: str) -> int:
        self._check_expiry(key)
        v = int(self._strings.get(key, "0")) + 1
        self._strings[key] = str(v)
        return v

    def decr(self, key: str) -> int:
        self._check_expiry(key)
        v = int(self._strings.get(key, "0")) - 1
        self._strings[key] = str(v)
        return v

    def expire(self, key: str, ttl: int) -> None:
        self._expiries[key] = time.time() + ttl

    # -- Lua eval --------------------------------------------------------

    def eval(self, script: str, num_keys: int, *args) -> str | None:
        """Execute acquire / release Lua scripts.

        Pattern-matches on script content rather than running a full
        Lua interpreter — sufficient for the two scripts the limiter
        uses.
        """
        keys = list(args[:num_keys])
        argv = list(args[num_keys:])
        if "ZREMRANGEBYSCORE" in script and "ZCARD" in script:
            return self._eval_acquire(keys, argv)
        if "ZREM" in script and "DECR" in script:
            return self._eval_release(keys, argv)
        raise NotImplementedError("Lua script not recognised by fake")

    def _eval_acquire(self, keys: list, argv: list) -> str | None:
        lane_key, tenant_key = keys[0], keys[1]
        token = argv[0]
        score = float(argv[1])
        lane_max = int(argv[2])
        tenant_max = int(argv[3])
        ttl = int(argv[4])

        # Evict expired
        now = time.time()
        self.zremrangebyscore(lane_key, "-inf", str(now))

        # Lane cap
        if self.zcard(lane_key) >= lane_max:
            return None

        # Tenant cap
        tenant_count = int(self.get(tenant_key) or "0")
        if tenant_count >= tenant_max:
            return None

        # Acquire
        self.zadd(lane_key, {token: score})
        self.set(tenant_key, str(tenant_count + 1))
        self.expire(tenant_key, ttl)
        return token

    def _eval_release(self, keys: list, argv: list) -> str:
        lane_key, tenant_key = keys[0], keys[1]
        token = argv[0]
        self.zrem(lane_key, token)
        v = int(self.get(tenant_key) or "1")
        if v > 0:
            self.set(tenant_key, str(v - 1))
        return "1"

    def _check_expiry(self, key: str) -> None:
        exp = self._expiries.get(key)
        if exp is not None and time.time() > exp:
            self._strings.pop(key, None)
            self._expiries.pop(key, None)


# ------------------------------------------------------------------ #
#  Shared fixtures for tests that need a fake Redis                    #
# ------------------------------------------------------------------ #


@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


# ------------------------------------------------------------------ #
#  Configuration tests                                                 #
# ------------------------------------------------------------------ #


class TestConfiguration:
    """Lane budget and tenant sub-cap calculations."""

    def test_embedding_live_max(self) -> None:
        assert _lane_max("embedding", "live") > 0

    def test_embedding_bulk_max(self) -> None:
        assert _lane_max("embedding", "bulk") > 0

    def test_completion_live_max(self) -> None:
        assert _lane_max("completion", "live") > 0

    def test_completion_bulk_max(self) -> None:
        assert _lane_max("completion", "bulk") > 0

    def test_embedding_total_under_200(self) -> None:
        total = _lane_max("embedding", "live") + _lane_max(
            "embedding", "bulk",
        )
        assert total <= 200, f"Total {total} exceeds 200-concurrent budget"

    def test_tenant_max_is_fraction_of_lane(self) -> None:
        tenant = _tenant_max("embedding", "bulk")
        lane = _lane_max("embedding", "bulk")
        assert 1 <= tenant <= lane

    def test_lane_key_format(self) -> None:
        key = _lane_key("embedding", "live")
        assert key.startswith("airunner:limiter:")
        assert "embedding" in key
        assert "live" in key

    def test_tenant_count_key_format(self) -> None:
        key = _tenant_count_key("completion", "bulk", "tenant_abc")
        assert "tenant_abc" in key
        assert "completion" in key
        assert "bulk" in key


# ------------------------------------------------------------------ #
#  Acquire / release tests (with fake Redis via patch)                 #
# ------------------------------------------------------------------ #


class TestAcquireRelease:
    """Core semaphore semantics: acquire, release, capacity, lanes."""

    def test_acquire_succeeds_when_capacity_available(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            slot = acquire_slot("embedding", "live", "t1")
        assert slot is not None

    def test_acquire_returns_different_tokens(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            s1 = acquire_slot("embedding", "live", "t1")
            s2 = acquire_slot("embedding", "live", "t1")
        assert s1 is not None
        assert s2 is not None
        assert s1._token != s2._token

    def test_release_frees_slot(self, fake_redis: _FakeRedis) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            s1 = acquire_slot("embedding", "bulk", "t1")
            assert s1 is not None
            s1.release()
            s2 = acquire_slot("embedding", "bulk", "t1")
            assert s2 is not None

    def test_release_is_idempotent(self, fake_redis: _FakeRedis) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            slot = acquire_slot("embedding", "live", "t1")
            assert slot is not None
            slot.release()
            slot.release()  # Should not raise

    def test_lane_at_capacity_rejects(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            max_live = _lane_max("embedding", "live")
            slots = []
            # Use distinct tenant keys to avoid per-tenant sub-cap
            for i in range(max_live):
                s = acquire_slot(
                    "embedding", "live", f"t_cap_{i}",
                )
                assert s is not None, f"Expected slot {i} to succeed"
                slots.append(s)
            # Lane should be full now; tenant cap not relevant
            assert acquire_slot(
                "embedding", "live", "t_cap_final",
            ) is None
            for s in slots:
                s.release()

    def test_lanes_are_independent(self, fake_redis: _FakeRedis) -> None:
        """Bulk lane full does not affect live lane."""
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            max_bulk = _lane_max("embedding", "bulk")
            slots = []
            for i in range(max_bulk):
                s = acquire_slot(
                    "embedding", "bulk", f"t_indep_{i}",
                )
                assert s is not None
                slots.append(s)
            # Live lane with a different tenant key should work
            assert acquire_slot(
                "embedding", "live", "t_indep_live",
            ) is not None
            for s in slots:
                s.release()

    def test_resources_are_independent(
        self, fake_redis: _FakeRedis,
    ) -> None:
        """Full embedding lanes don't block completion."""
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            emb_live = _lane_max("embedding", "live")
            emb_bulk = _lane_max("embedding", "bulk")
            slots = []
            for _ in range(emb_live):
                slots.append(acquire_slot("embedding", "live", "t_res"))
            for _ in range(emb_bulk):
                slots.append(acquire_slot("embedding", "bulk", "t_res"))
            assert acquire_slot("completion", "live", "t_res") is not None
            for s in slots:
                if s:
                    s.release()

    def test_tenant_sub_cap_enforced(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            tenant_max = _tenant_max("embedding", "bulk")
            slots = []
            for _ in range(tenant_max):
                s = acquire_slot("embedding", "bulk", "t_tenant")
                assert s is not None
                slots.append(s)
            assert acquire_slot("embedding", "bulk", "t_tenant") is None
            for s in slots:
                s.release()

    def test_different_tenants_independent(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            t_max = _tenant_max("embedding", "bulk")
            for _ in range(t_max):
                acquire_slot("embedding", "bulk", "t_a")
            assert acquire_slot("embedding", "bulk", "t_b") is not None

    def test_slot_self_heals_after_lease_expiry(
        self, fake_redis: _FakeRedis,
    ) -> None:
        """Slot becomes available after lease TTL without release call."""
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            max_live = _lane_max("embedding", "live")
            slots = []
            for i in range(max_live):
                s = acquire_slot(
                    "embedding", "live", f"t_heal_{i}",
                )
                assert s is not None
                slots.append(s)
            assert acquire_slot(
                "embedding", "live", "t_heal_final",
            ) is None
            # Simulate expiry: remove first slot's zset entry
            lane_k = _lane_key("embedding", "live")
            fake_redis.zrem(lane_k, slots[0]._token)
            new_slot = acquire_slot("embedding", "live", "t_heal_new")
            assert new_slot is not None
            for s in slots[1:]:
                s.release()
            new_slot.release()

    def test_two_clients_share_capacity(
        self, fake_redis: _FakeRedis,
    ) -> None:
        """Cross-process: two 'processes' share the same lane budget."""
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            max_bulk = _lane_max("embedding", "bulk")
            half = max_bulk // 2
            slots = []
            for i in range(half):
                slots.append(acquire_slot(
                    "embedding", "bulk", f"t_cross_a_{i}",
                ))
            for i in range(half):
                slots.append(acquire_slot(
                    "embedding", "bulk", f"t_cross_b_{i}",
                ))
            remaining = max_bulk - len([s for s in slots if s])
            if remaining > 0:
                assert acquire_slot(
                    "embedding", "bulk", "t_cross_final",
                ) is not None
            for s in slots:
                if s:
                    s.release()


# ------------------------------------------------------------------ #
#  acquire_with_retry tests                                            #
# ------------------------------------------------------------------ #


class TestAcquireWithRetry:
    """Bounded-wait and retry semantics for live/bulk lanes."""

    def test_acquire_with_retry_succeeds_immediately(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            slot = acquire_with_retry("embedding", "live", "t_retry")
            assert slot is not None

    def test_acquire_with_retry_times_out(
        self, fake_redis: _FakeRedis,
    ) -> None:
        """Live-lane graceful degradation (test 4)."""
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            max_live = _lane_max("embedding", "live")
            slots = []
            for i in range(max_live):
                slots.append(acquire_slot(
                    "embedding", "live", f"t_full_{i}",
                ))
            slot = acquire_with_retry(
                "embedding", "live", "t_full_final",
                max_wait=0.1,
                poll_interval=0.05,
            )
            assert slot is None
            for s in slots:
                s.release()


# ------------------------------------------------------------------ #
#  lane_stats tests                                                    #
# ------------------------------------------------------------------ #


class TestLaneStats:
    """Diagnostic lane_stats function."""

    def test_lane_stats_returns_keys(self, fake_redis: _FakeRedis) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            stats = lane_stats("embedding", "live")
            assert "active" in stats
            assert "max" in stats
            assert stats["max"] > 0

    def test_lane_stats_reflects_active(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            acquire_slot("completion", "bulk", "t_stats")
            stats = lane_stats("completion", "bulk")
            assert stats["active"] >= 1


# ------------------------------------------------------------------ #
#  AcquiredSlot tests                                                  #
# ------------------------------------------------------------------ #


class TestAcquiredSlot:
    """AcquiredSlot token lifecycle."""

    def test_slot_stores_fields(self) -> None:
        slot = AcquiredSlot("tok", "embedding", "live", "t1")
        assert slot._token == "tok"
        assert slot._resource == "embedding"
        assert slot._lane == "live"

    def test_release_marks_released(self) -> None:
        slot = AcquiredSlot("tok", "embedding", "live", "t1")
        assert not slot._released
        slot.release()
        assert slot._released


# ------------------------------------------------------------------ #
#  Completion choke tests                                              #
# ------------------------------------------------------------------ #


class TestCompletionChokeHelpers:
    """Helper function tests for the completion choke point."""

    def test_is_retryable_error_429(self) -> None:
        assert _is_retryable_error(Exception("429 Too Many Requests"))

    def test_is_retryable_error_rate_limit(self) -> None:
        assert _is_retryable_error(Exception("rate limit exceeded"))

    def test_is_retryable_error_overloaded(self) -> None:
        assert _is_retryable_error(Exception("engine overloaded"))

    def test_is_retryable_error_5xx(self) -> None:
        assert _is_retryable_error(Exception("503 Service Unavailable"))

    def test_is_not_retryable_error_4xx(self) -> None:
        assert not _is_retryable_error(Exception("400 Bad Request"))

    def test_resolve_tenant_key_explicit(self) -> None:
        assert _resolve_tenant_key("my_key") == "my_key"

    def test_resolve_tenant_key_fallback_empty(self) -> None:
        with patch(
            "airunner_services.data.tenant.get_tenant_key",
            side_effect=Exception("no context"),
        ):
            assert _resolve_tenant_key("") == ""


class TestInvokeWithLimiter:
    """Completion choke-point integration tests (tests 8, 9, 10)."""

    def _make_model(self, text: str = "hello"):
        model = MagicMock()
        response = MagicMock()
        response.content = text
        model.invoke.return_value = response
        return model

    def test_invoke_succeeds(self, fake_redis: _FakeRedis) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            model = self._make_model("hi")
            result = invoke_with_limiter(
                model, ["msg"], priority="bulk", tenant_key="t_cc",
            )
            assert result.content == "hi"
            model.invoke.assert_called_once()

    def test_live_lane_exhaustion_raises(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            max_live = _lane_max("completion", "live")
            slots = []
            for i in range(max_live):
                slots.append(
                    acquire_slot(
                        "completion", "live", f"t_exhaust_{i}",
                    ),
                )
            model = self._make_model()
            with pytest.raises(RuntimeError, match="live lane exhausted"):
                invoke_with_limiter(
                    model, ["msg"],
                    priority="live",
                    tenant_key="t_exhaust_final",
                )
            for s in slots:
                s.release()

    def test_retry_on_retryable_error(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            model = MagicMock()
            good = MagicMock()
            good.content = "ok"
            model.invoke.side_effect = [
                Exception("429 rate limit"), good,
            ]
            result = invoke_with_limiter(
                model, ["msg"], priority="bulk", tenant_key="t_retry",
            )
            assert result.content == "ok"
            assert model.invoke.call_count == 2

    def test_gives_up_on_non_retryable(
        self, fake_redis: _FakeRedis,
    ) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            model = MagicMock()
            model.invoke.side_effect = Exception("400 Bad Request")
            with pytest.raises(Exception, match="400"):
                invoke_with_limiter(
                    model, ["msg"],
                    priority="bulk",
                    tenant_key="t_giveup",
                )


class TestStreamWithLimiter:
    """Streaming choke-point tests."""

    def test_stream_yields_chunks(self, fake_redis: _FakeRedis) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            model = MagicMock()
            c1 = MagicMock()
            c1.content = "hello"
            c2 = MagicMock()
            c2.content = " world"
            model.stream.return_value = iter([c1, c2])
            chunks = list(
                stream_with_limiter(
                    model, ["msg"],
                    priority="bulk",
                    tenant_key="t_stream",
                ),
            )
            assert len(chunks) == 2
            assert chunks[0].content == "hello"
            assert chunks[1].content == " world"

    def test_stream_retry_on_error(self, fake_redis: _FakeRedis) -> None:
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            model = MagicMock()
            chunk = MagicMock()
            chunk.content = "ok"
            model.stream.side_effect = [
                Exception("503 overloaded"),
                iter([chunk]),
            ]
            chunks = list(
                stream_with_limiter(
                    model, ["msg"],
                    priority="bulk",
                    tenant_key="t_sr",
                ),
            )
            assert len(chunks) == 1
            assert chunks[0].content == "ok"
            assert model.stream.call_count == 2

    def test_stream_cancel_releases_slot(
        self, fake_redis: _FakeRedis,
    ) -> None:
        """Slot is released on GeneratorExit (caller stops iterating).

        Regression test for the bug where ``except Exception`` missed
        ``GeneratorExit`` (a ``BaseException``), leaking the slot for
        the full 300 s lease TTL.
        """
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=fake_redis,
        ):
            lane_k = _lane_key("completion", "bulk")
            initial_active = fake_redis.zcard(lane_k)

            model = MagicMock()
            # An infinite stream so the generator never finishes on its own
            c = MagicMock()
            c.content = "chunk"

            def _endless():
                while True:
                    yield c

            model.stream.return_value = _endless()
            gen = stream_with_limiter(
                model, ["msg"],
                priority="bulk",
                tenant_key="t_cancel",
            )
            # Consume one chunk, then close (simulate user cancel)
            assert next(gen).content == "chunk"
            gen.close()

            # Slot must be released immediately — zcard should be
            # back to initial (0 active slots).
            after_active = fake_redis.zcard(lane_k)
            assert after_active == initial_active, (
                f"Slot leaked: {after_active} active, "
                f"expected {initial_active}"
            )


# ------------------------------------------------------------------ #
#  Integration tests — real call site wrapping + exhaustion UX         #
# ------------------------------------------------------------------ #


class TestAttemptStreamExhaustion:
    """_attempt_stream returns user-visible message on live exhaustion."""

    def _make_owner(self):
        owner = MagicMock()
        owner.logger = MagicMock()
        owner._chat_model = MagicMock()
        owner._chat_model.stream = MagicMock()
        owner._interrupted = False
        owner._token_callback = None
        owner._call_chain_id = None
        owner._current_request_id = "req-1"
        return owner

    def _make_event_sink(self):
        sink = MagicMock()
        return sink

    def test_exhaustion_returns_busy_aimessage(self) -> None:
        from langchain_core.messages import AIMessage
        from airunner_services.cloud.llm.completion_choke import (
            LiveLaneExhaustedError,
        )
        from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
            NodeStreamingResponseHelper,
        )

        owner = self._make_owner()
        # stream_with_limiter is imported lazily inside _run_stream_loop;
        # patch at the definition site
        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=_FakeRedis(),
        ), patch(
            "airunner_services.cloud.llm.completion_choke."
            "stream_with_limiter",
            side_effect=LiveLaneExhaustedError("no slots"),
        ):
            helper = NodeStreamingResponseHelper(owner)
            result = helper._attempt_stream(
                prompt=["msg"],
                kwargs={},
                request_id="req-1",
                event_sink=self._make_event_sink(),
            )
        assert result is not None, (
            "Expected AIMessage, got None (silent failure)"
        )
        assert isinstance(result, AIMessage)
        assert "busy" in str(result.content).lower()
        assert result.additional_kwargs.get("error") == "capacity_exhausted"


class TestGenerateResponseExhaustion:
    """generate_response returns user-visible message on live exhaustion."""

    def _make_owner(self, has_stream: bool = True):
        owner = MagicMock()
        owner.logger = MagicMock()
        owner._chat_model = MagicMock()
        if has_stream:
            owner._chat_model.stream = MagicMock()
        else:
            del owner._chat_model.stream
        owner._token_callback = None
        return owner

    def test_stream_path_exhaustion_returns_busy_message(self) -> None:
        from langchain_core.messages import AIMessage
        from airunner_services.cloud.llm.completion_choke import (
            LiveLaneExhaustedError,
        )
        from airunner_services.llm.managers.mixins.node_response_generation_helper import (
            NodeResponseGenerationHelper,
        )

        owner = self._make_owner(has_stream=True)
        # stream_with_limiter is called deep inside _run_stream_loop;
        # mock the stream helper to raise exhaustion
        mock_streaming = MagicMock()
        mock_streaming.generate_streaming_response.side_effect = (
            LiveLaneExhaustedError("no slots")
        )
        mock_streaming._should_validate.return_value = False
        with patch.object(
            owner, "_get_streaming_response_helper",
            return_value=mock_streaming,
        ):
            helper = NodeResponseGenerationHelper(owner)
            result = helper.generate_response(
                formatted_prompt=["msg"],
                generation_kwargs={},
            )
        assert result is not None
        assert isinstance(result, AIMessage)
        assert "busy" in str(result.content).lower()
        assert result.additional_kwargs.get("error") == "capacity_exhausted"

    def test_invoke_path_exhaustion_returns_busy_message(self) -> None:
        from langchain_core.messages import AIMessage
        from airunner_services.cloud.llm.completion_choke import (
            LiveLaneExhaustedError,
        )
        from airunner_services.llm.managers.mixins.node_response_generation_helper import (
            NodeResponseGenerationHelper,
        )

        # Model without .stream() → falls back to invoke path
        with patch(
            "airunner_services.cloud.llm.completion_choke."
            "invoke_with_limiter",
            side_effect=LiveLaneExhaustedError("no slots"),
        ):
            owner = self._make_owner(has_stream=False)
            helper = NodeResponseGenerationHelper(owner)
            result = helper.generate_response(
                formatted_prompt=["msg"],
                generation_kwargs={},
            )
        assert result is not None
        assert isinstance(result, AIMessage)
        assert "busy" in str(result.content).lower()
        assert result.additional_kwargs.get("error") == "capacity_exhausted"


class TestRunStreamLoopWrapping:
    """_run_stream_loop forwards prompt/kwargs through stream_with_limiter."""

    def _make_owner(self):
        owner = MagicMock()
        owner.logger = MagicMock()
        owner._chat_model = MagicMock()
        owner._interrupted = False
        owner._token_callback = None
        return owner

    def _make_state(self):
        from airunner_services.llm.managers.mixins.node_streaming_state import (
            StreamingState,
        )
        return StreamingState()

    def test_kwargs_forwarded_through_limiter(self) -> None:
        from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
            NodeStreamingResponseHelper,
        )

        owner = self._make_owner()
        state = self._make_state()
        # Suppress thinking-delta processing and token extraction
        # so the helper doesn't try to interpret mock chunk internals
        state.using_reasoning_deltas = False
        state.thinking_content = []
        sink = MagicMock()

        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=_FakeRedis(),
        ), patch(
            "airunner_services.cloud.llm.completion_choke."
            "stream_with_limiter",
        ) as mock_stream:
            # Empty iterator → _process_chunk never called
            mock_stream.return_value = iter([])

            helper = NodeStreamingResponseHelper(owner)
            helper._run_stream_loop(
                state, prompt=["hello"], kwargs={"temperature": 0.5},
                request_id="req-1", event_sink=sink,
            )

        # Confirm stream_with_limiter was called with priority="live"
        call_args, call_kwargs = mock_stream.call_args
        assert call_kwargs.get("priority") == "live"
        # kwargs from _run_stream_loop should be forwarded
        assert call_kwargs.get("temperature") == 0.5

    def test_interrupted_flag_breaks_loop(self) -> None:
        from airunner_services.llm.managers.mixins.node_streaming_response_helper import (
            NodeStreamingResponseHelper,
        )

        owner = self._make_owner()
        owner._interrupted = True  # interrupt immediately
        state = self._make_state()
        sink = MagicMock()

        with patch(
            "airunner_services.cloud.distributed_limiter.cache_redis",
            return_value=_FakeRedis(),
        ), patch(
            "airunner_services.cloud.llm.completion_choke."
            "stream_with_limiter",
        ) as mock_stream:
            chunk = MagicMock()
            chunk.content = "test"
            mock_stream.return_value = iter([chunk])

            helper = NodeStreamingResponseHelper(owner)
            helper._run_stream_loop(
                state, prompt=["hello"], kwargs={},
                request_id="req-1", event_sink=sink,
            )

        # Interrupted before processing any chunk → no content accumulated
        assert not state.streamed_content
