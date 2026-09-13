"""Tests for resource_guards registry and ChatbotGuard rules.

Covers the nine scenarios from the identity-guardrails-lockdown plan:

1. Create with ``use_guardrails=false`` → forced ``True``
2. Update with ``use_guardrails=false`` → forced ``True``
3. Update identity fields → silently stripped
4. Delete → rejected
5. Reset-defaults → rejected
6. Block ordinary chatbot → succeeds
7. Block system bot → silently dropped
8. ``is_system_bot`` / ``omnipotent_knowledge`` → stripped
9. Control: no guard → behaviour identical to pre-guard
"""

from __future__ import annotations

from typing import Any

import pytest

from airunner_services.api.resource_guards import (
    ResourceGuardRejected,
    clear_registry,
    get_guard,
    register_guard,
)


# -- helpers ---------------------------------------------------------------


class _FakeChatbot:
    """Minimal stub that exposes the fields the guard inspects."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _make_chatbot(**overrides: Any) -> _FakeChatbot:
    defaults: dict[str, Any] = {
        "id": 1,
        "name": "TestBot",
        "botname": "testbot",
        "bot_personality": "cheerful",
        "gender": "Male",
        "use_guardrails": True,
        "is_system_bot": False,
        "omnipotent_knowledge": False,
        "has_blocked_user": False,
        "blocked_by_user": False,
    }
    defaults.update(overrides)
    return _FakeChatbot(**defaults)


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Ensure the registry is empty before each test."""
    clear_registry()
    yield
    clear_registry()


# -- registry tests --------------------------------------------------------


class TestRegistry:
    """Register, get, and clear guards."""

    def test_get_guard_returns_none_when_empty(self) -> None:
        assert get_guard("Chatbot") is None

    def test_register_and_retrieve(self) -> None:
        from projects.uwuchat.server.security import ChatbotGuard

        guard = ChatbotGuard()
        register_guard(guard)
        assert get_guard("Chatbot") is guard

    def test_clear_removes_all(self) -> None:
        from projects.uwuchat.server.security import ChatbotGuard

        register_guard(ChatbotGuard())
        clear_registry()
        assert get_guard("Chatbot") is None


# -- ChatbotGuard unit tests -----------------------------------------------


class TestSanitizeCreate:
    """Values supplied at creation are sanitised."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import ChatbotGuard

        self.guard = ChatbotGuard()

    # --- scenario 1 -------------------------------------------------------

    def test_use_guardrails_false_is_forced_true(self) -> None:
        values = self.guard.sanitize_create({"use_guardrails": False})
        assert values["use_guardrails"] is True

    def test_use_guardrails_true_stays_true(self) -> None:
        values = self.guard.sanitize_create({"use_guardrails": True})
        assert values["use_guardrails"] is True

    def test_use_guardrails_absent_not_added(self) -> None:
        values = self.guard.sanitize_create({"botname": "hello"})
        assert "use_guardrails" not in values
        assert values["botname"] == "hello"

    # --- scenario 8 -------------------------------------------------------

    def test_is_system_bot_stripped(self) -> None:
        values = self.guard.sanitize_create(
            {"botname": "x", "is_system_bot": True}
        )
        assert "is_system_bot" not in values

    def test_omnipotent_knowledge_stripped(self) -> None:
        values = self.guard.sanitize_create(
            {"botname": "x", "omnipotent_knowledge": True}
        )
        assert "omnipotent_knowledge" not in values

    def test_identity_fields_passed_through_on_create(self) -> None:
        """Identity fields are NOT stripped during creation."""
        values = self.guard.sanitize_create(
            {"name": "NewBot", "botname": "nb",
             "bot_personality": "curious", "gender": "Female"}
        )
        assert values["name"] == "NewBot"
        assert values["botname"] == "nb"
        assert values["bot_personality"] == "curious"
        assert values["gender"] == "Female"


class TestSanitizeUpdate:
    """Values supplied at update are sanitised."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import ChatbotGuard

        self.guard = ChatbotGuard()

    # --- scenario 2 -------------------------------------------------------

    def test_use_guardrails_false_is_forced_true(self) -> None:
        bot = _make_chatbot(use_guardrails=True)
        values = self.guard.sanitize_update(bot, {"use_guardrails": False})
        assert values["use_guardrails"] is True

    # --- scenario 3 -------------------------------------------------------

    def test_identity_fields_stripped(self) -> None:
        bot = _make_chatbot(name="Original")
        values = self.guard.sanitize_update(
            bot,
            {
                "name": "Hacked",
                "botname": "hacked",
                "bot_personality": "evil",
                "gender": "Other",
            },
        )
        for field in ("name", "botname", "bot_personality", "gender"):
            assert field not in values, f"{field} was not stripped"

    def test_other_fields_preserved_alongside_identity_stripping(
        self,
    ) -> None:
        bot = _make_chatbot()
        values = self.guard.sanitize_update(
            bot,
            {"name": "Hacked", "use_mood": False},
        )
        assert "name" not in values
        assert values["use_mood"] is False

    # --- scenario 6 -------------------------------------------------------

    def test_block_ordinary_chatbot_succeeds(self) -> None:
        bot = _make_chatbot(is_system_bot=False)
        values = self.guard.sanitize_update(
            bot, {"has_blocked_user": True}
        )
        assert values["has_blocked_user"] is True

    def test_unblock_ordinary_chatbot_succeeds(self) -> None:
        bot = _make_chatbot(is_system_bot=False)
        values = self.guard.sanitize_update(
            bot, {"has_blocked_user": False, "blocked_by_user": False}
        )
        assert values["has_blocked_user"] is False
        assert values["blocked_by_user"] is False

    # --- scenario 7 -------------------------------------------------------

    def test_block_system_bot_dropped(self) -> None:
        bot = _make_chatbot(is_system_bot=True)
        values = self.guard.sanitize_update(
            bot, {"has_blocked_user": True}
        )
        assert "has_blocked_user" not in values

    def test_blocked_by_user_system_bot_dropped(self) -> None:
        bot = _make_chatbot(is_system_bot=True)
        values = self.guard.sanitize_update(
            bot, {"blocked_by_user": True}
        )
        assert "blocked_by_user" not in values

    # --- scenario 8 -------------------------------------------------------

    def test_is_system_bot_stripped_on_update(self) -> None:
        bot = _make_chatbot(is_system_bot=False)
        values = self.guard.sanitize_update(
            bot, {"is_system_bot": True}
        )
        assert "is_system_bot" not in values

    def test_omnipotent_knowledge_stripped_on_update(self) -> None:
        bot = _make_chatbot()
        values = self.guard.sanitize_update(
            bot, {"omnipotent_knowledge": True}
        )
        assert "omnipotent_knowledge" not in values


class TestBeforeDelete:
    """Deletion is always blocked."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import ChatbotGuard

        self.guard = ChatbotGuard()

    # --- scenario 4 -------------------------------------------------------

    def test_delete_ordinary_chatbot_raises(self) -> None:
        bot = _make_chatbot(is_system_bot=False)
        with pytest.raises(ResourceGuardRejected):
            self.guard.before_delete(bot)

    def test_delete_system_bot_raises(self) -> None:
        bot = _make_chatbot(is_system_bot=True)
        with pytest.raises(ResourceGuardRejected):
            self.guard.before_delete(bot)


class TestBeforeResetDefaults:
    """Reset-defaults is always blocked."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import ChatbotGuard

        self.guard = ChatbotGuard()

    # --- scenario 5 -------------------------------------------------------

    def test_reset_defaults_raises(self) -> None:
        bot = _make_chatbot()
        with pytest.raises(ResourceGuardRejected):
            self.guard.before_reset_defaults(bot)


# -- control test (scenario 9) ---------------------------------------------
# When no guard is registered, every operation is a no-op.  This is
# implicit in the design (get_guard returns None, so no hooks are
# called), but the test makes the invariant explicit.


class TestNoGuardNoBehaviour:
    """Control: no guard → byte-for-byte identical to pre-guard code."""

    def test_sanitize_create_passthrough(self) -> None:
        from airunner_services.api.routes.rpc_settings import (
            _sanitize_for_resource,
        )

        values = {"use_guardrails": False, "name": "Test"}
        result = _sanitize_for_resource("Chatbot", None, values)
        assert result == values  # no change

    def test_sanitize_update_passthrough(self) -> None:
        from airunner_services.api.routes.rpc_settings import (
            _sanitize_for_resource,
        )

        bot = _make_chatbot()
        values = {"use_guardrails": False, "botname": "hacked"}
        result = _sanitize_for_resource("Chatbot", bot, values)
        assert result == values  # no change

    def test_before_delete_passthrough(self) -> None:
        from airunner_services.api.routes.rpc_settings import (
            _check_before_delete,
        )

        bot = _make_chatbot()
        # Should not raise
        _check_before_delete("Chatbot", bot)

    def test_before_reset_defaults_passthrough(self) -> None:
        from airunner_services.api.routes.rpc_settings import (
            _check_before_reset_defaults,
        )

        bot = _make_chatbot()
        # Should not raise
        _check_before_reset_defaults("Chatbot", bot)

    def test_guard_not_registered_for_other_resource(self) -> None:
        """A resource without a guard (e.g. 'User') behaves unchanged."""
        from airunner_services.api.routes.rpc_settings import (
            _sanitize_for_resource,
        )

        values = {"gems": 9999}
        result = _sanitize_for_resource("User", None, values)
        assert result == values  # no change


# -- base ResourceGuard default hooks -----------------------------------
# Regression guard: before_reset_defaults and filter_read must be
# indented inside the class body so they exist on base instances.


class TestBaseResourceGuardDefaults:
    """Base ResourceGuard (no override) must have working no-op hooks."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from airunner_services.api.resource_guards import ResourceGuard

        self.guard = ResourceGuard(resource_name="TestResource")

    def test_filter_read_returns_input(self) -> None:
        """filter_read on base guard returns the record unchanged."""
        record = {"a": 1, "b": 2}
        result = self.guard.filter_read(record, False)
        assert result == record
        assert result is record  # same object, not a copy

    def test_before_reset_defaults_is_noop(self) -> None:
        """before_reset_defaults on base guard does not raise."""
        # Should complete without raising ResourceGuardRejected
        self.guard.before_reset_defaults(None)

    def test_sanitize_create_passthrough(self) -> None:
        """sanitize_create on base guard returns values unchanged."""
        values = {"foo": "bar"}
        result = self.guard.sanitize_create(values)
        assert result == values
        assert result is values

    def test_sanitize_update_passthrough(self) -> None:
        """sanitize_update on base guard returns values unchanged."""
        values = {"foo": "bar"}
        result = self.guard.sanitize_update(None, values)
        assert result == values
        assert result is values


# -- ApplicationSettingsGuard / LLMGeneratorSettingsGuard ----------------


class TestApplicationSettingsGuard:
    """UwUchat's ApplicationSettingsGuard restricts read/write."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import (
            ApplicationSettingsGuard,
        )

        self.guard = ApplicationSettingsGuard()

    def test_filter_read_non_superuser(self) -> None:
        result = self.guard.filter_read(
            {"id": 1, "detected_language": "en",
             "openai_api_key": "sk-xxx"},
            is_superuser=False,
        )
        assert result == {"id": 1, "detected_language": "en"}

    def test_filter_read_superuser_narrowed(self) -> None:
        full = {"id": 1, "detected_language": "en",
                "openai_api_key": "sk-xxx"}
        result = self.guard.filter_read(full, is_superuser=True)
        assert result == {"id": 1, "detected_language": "en"}

    def test_sanitize_update_non_superuser_strips(self) -> None:
        values = {"openai_api_key": "sk-evil",
                  "detected_language": "es"}
        result = self.guard.sanitize_update(
            None, values, is_superuser=False
        )
        assert result == {"detected_language": "es"}

    def test_sanitize_update_superuser_passthrough(self) -> None:
        values = {"openai_api_key": "sk-evil",
                  "detected_language": "es"}
        result = self.guard.sanitize_update(
            None, values, is_superuser=True
        )
        assert result == values


class TestLLMGeneratorSettingsGuard:
    """UwUchat's LLMGeneratorSettingsGuard restricts read/write."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import (
            LLMGeneratorSettingsGuard,
        )

        self.guard = LLMGeneratorSettingsGuard()

    def test_filter_read_non_superuser(self) -> None:
        result = self.guard.filter_read(
            {"id": 1, "model_path": "gpt-4",
             "temperature": 1000, "top_p": 900},
            is_superuser=False,
        )
        assert result == {"id": 1, "model_path": "gpt-4"}

    def test_filter_read_superuser_narrowed(self) -> None:
        full = {"id": 1, "model_path": "gpt-4",
                "temperature": 1000, "top_p": 900}
        result = self.guard.filter_read(full, is_superuser=True)
        assert result == {"id": 1, "model_path": "gpt-4"}

    def test_sanitize_update_non_superuser_strips(self) -> None:
        values = {"temperature": 500, "model_path": "gpt-4"}
        result = self.guard.sanitize_update(
            None, values, is_superuser=False
        )
        assert result == {"model_path": "gpt-4"}

    def test_sanitize_update_superuser_passthrough(self) -> None:
        values = {"temperature": 500, "model_path": "gpt-4"}
        result = self.guard.sanitize_update(
            None, values, is_superuser=True
        )
        assert result == values


class TestPipelineConfigGuard:
    """UwUchat's PipelineConfigGuard restricts read/write to admins."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import PipelineConfigGuard

        self.guard = PipelineConfigGuard()

    def test_filter_read_non_superuser_strips_overrides(self) -> None:
        result = self.guard.filter_read(
            {"id": 1, "pipeline_key": "llm",
             "overrides": {"model": "gpt-4"}, "updated_by": "admin"},
            is_superuser=False,
        )
        assert result == {"id": 1, "pipeline_key": "llm"}

    def test_filter_read_superuser_narrowed(self) -> None:
        full = {"id": 1, "pipeline_key": "llm",
                "overrides": {"model": "gpt-4"}, "updated_by": "admin"}
        result = self.guard.filter_read(full, is_superuser=True)
        assert result == {"id": 1, "pipeline_key": "llm"}

    def test_sanitize_create_non_superuser_raises(self) -> None:
        with pytest.raises(ResourceGuardRejected):
            self.guard.sanitize_create(
                {"pipeline_key": "llm"},
                is_superuser=False,
            )

    def test_sanitize_create_superuser_passthrough(self) -> None:
        values = {"pipeline_key": "llm", "overrides": {"model": "gpt-4"}}
        result = self.guard.sanitize_create(
            values, is_superuser=True,
        )
        assert result == values

    def test_sanitize_update_non_superuser_raises(self) -> None:
        with pytest.raises(ResourceGuardRejected):
            self.guard.sanitize_update(
                None, {"overrides": {"model": "gpt-5"}},
                is_superuser=False,
            )

    def test_sanitize_update_superuser_passthrough(self) -> None:
        values = {"overrides": {"model": "gpt-5"}}
        result = self.guard.sanitize_update(
            None, values, is_superuser=True,
        )
        assert result == values

    def test_before_delete_non_superuser_raises(self) -> None:
        """Non-superusers must not delete PipelineConfig rows."""
        with pytest.raises(ResourceGuardRejected):
            self.guard.before_delete(None, is_superuser=False)

    def test_before_delete_superuser_passthrough(self) -> None:
        """Superusers are allowed to delete PipelineConfig rows."""
        # Should not raise.
        self.guard.before_delete(None, is_superuser=True)

    def test_before_reset_defaults_raises(self) -> None:
        with pytest.raises(ResourceGuardRejected):
            self.guard.before_reset_defaults(None)


class TestAllGuardsKwargsTolerance:
    """Standing regression test: every registered guard's before_delete
    must tolerate the ``is_superuser`` keyword argument that
    ``_check_before_delete`` now passes unconditionally.

    If a guard's ``before_delete`` signature lacks ``**kwargs``,
    calling it with ``is_superuser=...`` raises ``TypeError``,
    which bypasses the guard's intended ``ResourceGuardRejected``
    and degrades to a generic 500 via ``_rpc_error_response``.
    """

    def test_all_guards_accept_is_superuser_kwarg(self) -> None:
        """Iterate every guard registered in register_guards() and
        call before_delete with both is_superuser=True and False.
        Only ResourceGuardRejected is acceptable; TypeError means
        the signature wasn't updated."""
        from projects.uwuchat.server.security import (
            ApplicationSettingsGuard,
            ChatbotGuard,
            LLMGeneratorSettingsGuard,
            PipelineConfigGuard,
        )

        dummy = object()
        guards = [
            ChatbotGuard(),
            ApplicationSettingsGuard(),
            LLMGeneratorSettingsGuard(),
            PipelineConfigGuard(),
        ]

        for guard in guards:
            for is_superuser in (True, False):
                try:
                    guard.before_delete(dummy, is_superuser=is_superuser)
                except ResourceGuardRejected:
                    pass  # Expected — the guard blocked the operation.
                except TypeError as exc:
                    raise AssertionError(
                        f"{type(guard).__name__}.before_delete raised "
                        f"TypeError with is_superuser={is_superuser}: "
                        f"{exc}"
                    ) from exc
                # Any other exception type would also be a test failure.

    def test_all_guards_tolerate_missing_kwargs(self) -> None:
        """Legacy callers that don't pass is_superuser must still work."""
        from projects.uwuchat.server.security import (
            ApplicationSettingsGuard,
            ChatbotGuard,
            LLMGeneratorSettingsGuard,
            PipelineConfigGuard,
        )

        dummy = object()
        guards = [
            ChatbotGuard(),
            ApplicationSettingsGuard(),
            LLMGeneratorSettingsGuard(),
            PipelineConfigGuard(),
        ]

        for guard in guards:
            try:
                guard.before_delete(dummy)
            except ResourceGuardRejected:
                pass
            except TypeError as exc:
                raise AssertionError(
                    f"{type(guard).__name__}.before_delete raised "
                    f"TypeError without kwargs: {exc}"
                ) from exc
