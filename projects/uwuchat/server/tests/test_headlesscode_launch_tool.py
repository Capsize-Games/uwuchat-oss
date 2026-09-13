"""Unit tests for the launch_headlesscode_session tool.

Covers: agent-context validation, the credits gate, the explicit
user-confirmation gate, project-registry validation, and the
enqueue-to-Celery path.  All DB and broker interactions are mocked —
no real database or Redis needed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import projects.uwuchat.server.tools.code_tools.launch_session as mod

AGENT = SimpleNamespace(
    user=SimpleNamespace(id=7),
    chatbot=SimpleNamespace(id=3),
)
PROJECT = SimpleNamespace(
    id=11, name="acme-web", repo_path="/srv/acme",
    workspace_root="/srv/acme",
)


def _call(**kwargs) -> str:
    """Invoke the tool with the standard agent and overridable args."""
    return mod.launch_headlesscode_session(agent=AGENT, **kwargs)


@pytest.fixture()
def ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic tenant/account context for every test."""
    monkeypatch.setattr(mod, "get_account_id", lambda: 42)
    monkeypatch.setattr(mod, "get_tenant_key", lambda: "tenant_x")


def test_missing_agent_returns_error() -> None:
    """No agent context degrades to a friendly error, no enqueue."""
    result = mod.launch_headlesscode_session(
        project_name="acme-web", task="fix bug",
    )
    assert "session context" in result


def test_unregistered_project_returns_error(
    ctx: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown project names return the registered-project list."""
    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [],
    )
    result = _call(project_name="nope", task="fix bug")
    assert "isn't a registered project" in result


def test_no_credits_blocks_launch(
    ctx: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """has_credits=False blocks even a confirmed cloud launch."""
    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [PROJECT],
    )
    monkeypatch.setattr(mod, "has_credits", lambda account_id: False)
    monkeypatch.setattr(
        mod, "_uses_local_backend", lambda mode: False,
    )
    result = _call(
        project_name="acme-web", task="fix bug", confirmed=True,
    )
    assert "no code credits" in result


def test_local_backend_skips_credits_gate(
    ctx: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local-backend session launches with zero credits.

    The local daemon (Qwen 3.5 9B) has no dollar cost, so has_credits
    must never be consulted — even with a zero balance and no account
    context, the confirmed launch enqueues.
    """
    from unittest.mock import Mock

    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [PROJECT],
    )
    # Force local backend + prove has_credits is never called.
    monkeypatch.setattr(mod, "_uses_local_backend", lambda mode: True)
    has_credits = Mock()
    monkeypatch.setattr(mod, "has_credits", has_credits)
    monkeypatch.setattr(
        mod, "consume_pending_confirmation", lambda idem_key: True,
    )
    monkeypatch.setattr(
        mod, "launch_idempotency_key", lambda *a: "idem-local",
    )
    monkeypatch.setattr(
        mod, "_resolve_conversation_id", lambda chatbot_id: 77,
    )
    monkeypatch.setattr(
        mod, "_resolve_effective_mode", lambda conv_id, tool_mode: "code",
    )
    import projects.uwuchat.server.tasks.headlesscode_tasks as ht

    apply_async = Mock()
    monkeypatch.setattr(
        ht.launch_headlesscode_session_task, "apply_async", apply_async,
    )
    result = _call(
        project_name="acme-web", task="fix the login bug",
        confirmed=True,
    )
    assert "Started a headlesscode session on 'acme-web'" in result
    has_credits.assert_not_called()
    args = apply_async.call_args.kwargs["args"]
    # account_id is 0 for local sessions (no account lookup needed).
    assert args == [
        11, 3, "fix the login bug", "code", "tenant_x", 0, "idem-local",
        77, "acme-web",
    ]


class TestUsesLocalBackend:
    """_uses_local_backend mirrors headlesscode's local-backend env
    contract (HEADLESSCODE_CODE_MODE_BACKEND + LOCAL_BACKEND_MODES)."""

    def test_cloud_default_is_not_local(self, monkeypatch) -> None:
        """No env → the backend defaults to openrouter (paid)."""
        monkeypatch.delenv(
            "HEADLESSCODE_CODE_MODE_BACKEND", raising=False,
        )
        assert mod._uses_local_backend("code") is False

    def test_ollama_backend_code_mode_is_local(self, monkeypatch) -> None:
        """HEADLESSCODE_CODE_MODE_BACKEND=ollama + mode code → local."""
        monkeypatch.setenv("HEADLESSCODE_CODE_MODE_BACKEND", "ollama")
        monkeypatch.delenv(
            "HEADLESSCODE_LOCAL_BACKEND_MODES", raising=False,
        )
        assert mod._uses_local_backend("code") is True

    def test_ollama_backend_non_code_mode_not_local(
        self, monkeypatch,
    ) -> None:
        """Local-backend modes default to 'code'; 'architect' is cloud."""
        monkeypatch.setenv("HEADLESSCODE_CODE_MODE_BACKEND", "ollama")
        monkeypatch.delenv(
            "HEADLESSCODE_LOCAL_BACKEND_MODES", raising=False,
        )
        assert mod._uses_local_backend("architect") is False

    def test_ollama_backend_custom_modes_include_architect(
        self, monkeypatch,
    ) -> None:
        """HEADLESSCODE_LOCAL_BACKEND_MODES can widen the allow-list."""
        monkeypatch.setenv("HEADLESSCODE_CODE_MODE_BACKEND", "ollama")
        monkeypatch.setenv(
            "HEADLESSCODE_LOCAL_BACKEND_MODES", "code,architect",
        )
        assert mod._uses_local_backend("architect") is True


def test_unconfirmed_asks_for_confirmation(
    ctx: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call returns a confirmation request, nothing enqueued.

    Also asserts the real server-side marker gets set (not just a
    prompt-level suggestion) — that marker is what makes a later
    confirmed=true call legitimate.
    """
    from unittest.mock import Mock

    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [PROJECT],
    )
    monkeypatch.setattr(mod, "has_credits", lambda account_id: True)
    import projects.uwuchat.server.tasks.headlesscode_tasks as ht

    apply_async = Mock()
    monkeypatch.setattr(
        ht.launch_headlesscode_session_task, "apply_async", apply_async,
    )
    mark = Mock()
    monkeypatch.setattr(mod, "mark_pending_confirmation", mark)
    result = _call(project_name="acme-web", task="fix bug")
    assert "CONFIRM_REQUIRED" in result
    apply_async.assert_not_called()
    mark.assert_called_once()


def test_confirmed_without_prior_ask_is_rejected(
    ctx: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """confirmed=true with no matching prior ask does NOT launch.

    This is the real fix for the reviewed gap: the model cannot just
    set confirmed=true on its first call and spend credits.
    """
    from unittest.mock import Mock

    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [PROJECT],
    )
    monkeypatch.setattr(mod, "has_credits", lambda account_id: True)
    monkeypatch.setattr(
        mod, "consume_pending_confirmation", lambda idem_key: False,
    )
    import projects.uwuchat.server.tasks.headlesscode_tasks as ht

    apply_async = Mock()
    monkeypatch.setattr(
        ht.launch_headlesscode_session_task, "apply_async", apply_async,
    )
    result = _call(
        project_name="acme-web", task="fix bug", confirmed=True,
    )
    assert "need to ask the user to confirm first" in result
    apply_async.assert_not_called()


def test_empty_task_returns_error(
    ctx: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blank task is rejected before enqueueing anything."""
    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [PROJECT],
    )
    monkeypatch.setattr(mod, "has_credits", lambda account_id: True)
    result = _call(
        project_name="acme-web", task="   ", confirmed=True,
    )
    assert "without knowing what to work on" in result


def test_confirmed_enqueues_task(
    ctx: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A confirmed launch (with a prior real ask) enqueues the task."""
    from unittest.mock import Mock

    monkeypatch.setattr(
        mod.HeadlesscodeProject.objects, "filter_by",
        lambda **kw: [PROJECT],
    )
    monkeypatch.setattr(mod, "has_credits", lambda account_id: True)
    monkeypatch.setattr(
        mod, "consume_pending_confirmation", lambda idem_key: True,
    )
    monkeypatch.setattr(
        mod, "launch_idempotency_key", lambda *a: "idem-abc123",
    )
    monkeypatch.setattr(
        mod, "_resolve_conversation_id", lambda chatbot_id: 77,
    )
    monkeypatch.setattr(
        mod, "_resolve_effective_mode", lambda conv_id, tool_mode: "code",
    )
    import projects.uwuchat.server.tasks.headlesscode_tasks as ht

    apply_async = Mock()
    monkeypatch.setattr(
        ht.launch_headlesscode_session_task, "apply_async", apply_async,
    )
    result = _call(
        project_name="acme-web", task="  fix the login bug  ",
        confirmed=True,
    )
    assert "Started a headlesscode session on 'acme-web'" in result
    apply_async.assert_called_once()
    args = apply_async.call_args.kwargs["args"]
    assert args == [
        11, 3, "fix the login bug", "code", "tenant_x", 42, "idem-abc123",
        77, "acme-web",
    ]


class TestResolveEffectiveMode:
    """The conversation's mode-picker selection wins over the tool's
    own ``mode`` argument — see code_mode_service.py's
    ``code_mode_slug``."""

    def test_uses_conversation_slug_when_resolved(self) -> None:
        conv = MagicMock(user_data={"code_mode_slug": "architect"})
        with patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.get",
            return_value=conv,
        ):
            result = mod._resolve_effective_mode(5, None)
        assert result == "architect"

    def test_conversation_slug_wins_over_tool_mode(self) -> None:
        conv = MagicMock(user_data={"code_mode_slug": "architect"})
        with patch(
            "airunner_services.database.models.conversation.Conversation"
            ".objects.get",
            return_value=conv,
        ):
            result = mod._resolve_effective_mode(5, "code")
        assert result == "architect"

    def test_falls_back_to_tool_mode_when_no_conversation(self) -> None:
        result = mod._resolve_effective_mode(None, "architect")
        assert result == "architect"

    def test_falls_back_to_code_when_nothing_resolved(self) -> None:
        result = mod._resolve_effective_mode(None, None)
        assert result == "code"
