"""Tests for round-2 resource guard additions.

Covers:
- Part 1: ``_SECRET_FIELD_PATTERN`` redaction in ``_record_from_item``
- Part 2: ``expose_resource`` / ``is_exposed`` / ``resource_store_table``
  gating
- Part 4: ``UserGuard.check_ownership`` and currency-field stripping
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from airunner_services.api.resource_guards import (
    ResourceGuardRejected,
    clear_registry,
    expose_resource,
    is_exposed,
)
from airunner_services.api.routes.rpc_settings import (
    _SECRET_FIELD_PATTERN,
    _record_from_item,
)


# -- helpers ---------------------------------------------------------------


@dataclass
class _FakeColumn:
    name: str


class _FakeTable:
    def __init__(self, column_names: list[str]) -> None:
        self.columns = [_FakeColumn(n) for n in column_names]


class _FakeRow:
    """Stub ORM row whose attributes are stored in a dict."""

    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs
        self.__table__ = _FakeTable(list(kwargs.keys()))

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data[name]


def _make_row(**kwargs: Any) -> _FakeRow:
    return _FakeRow(**kwargs)


@pytest.fixture(autouse=True)
def _clean() -> None:
    """Ensure the registry and exposure set are empty before each test."""
    clear_registry()
    yield
    clear_registry()


# -- Part 1: secret-field redaction ----------------------------------------


class TestSecretFieldPattern:
    """Verify the credential-pattern regex covers real API-key fields
    and does not produce false positives for non-secret columns."""

    def test_api_key_fields_match(self) -> None:
        for name in (
            "hf_api_key_read_key",
            "hf_api_key_write_key",
            "civit_ai_api_key",
            "openai_api_key",
            "api_key",
        ):
            assert _SECRET_FIELD_PATTERN.search(name), (
                f"expected {name!r} to match secret pattern"
            )

    def test_token_secret_password_fields_match(self) -> None:
        for name in (
            "access_token",
            "refresh_token",
            "client_secret",
            "my_secret",
            "private_key",
            "db_password",
        ):
            assert _SECRET_FIELD_PATTERN.search(name), (
                f"expected {name!r} to match secret pattern"
            )

    def test_non_secret_fields_do_not_match(self) -> None:
        for name in (
            "id",
            "username",
            "detected_language",
            "use_cuda",
            "api_version",
            "keyboard_shortcut",
            "keystroke_delay",
            "shortcut_key",
            "chatstore_key",
            "pipeline_key",
            "conversation_key",
            "project_setting_key",
            "speech_patterns",
            "is_system_bot",
        ):
            assert not _SECRET_FIELD_PATTERN.search(name), (
                f"expected {name!r} NOT to match secret pattern"
            )


class TestRecordFromItemRedaction:
    """``_record_from_item`` drops credential columns from every row."""

    def test_drops_api_key_fields(self) -> None:
        row = _make_row(
            id=1,
            detected_language="en",
            hf_api_key_read_key="sekret",
            hf_api_key_write_key="sekret2",
            civit_ai_api_key="sekret3",
            openai_api_key="sekret4",
        )
        record = _record_from_item(row)
        assert record["id"] == 1
        assert record["detected_language"] == "en"
        assert "hf_api_key_read_key" not in record
        assert "hf_api_key_write_key" not in record
        assert "civit_ai_api_key" not in record
        assert "openai_api_key" not in record

    def test_keeps_non_secret_fields(self) -> None:
        row = _make_row(
            id=1,
            model_path="gpt-4",
            use_cuda=True,
            api_key="hidden-key",
        )
        record = _record_from_item(row)
        assert record["id"] == 1
        assert record["model_path"] == "gpt-4"
        assert record["use_cuda"] is True
        assert "api_key" not in record

    def test_superuser_also_stripped(self) -> None:
        """The redaction runs before any guard or role check — superusers
        never get secret fields back through this channel either."""
        row = _make_row(
            id=1,
            openai_api_key="sk-abc",
            detected_language="en",
        )
        record = _record_from_item(row)
        assert "openai_api_key" not in record
        assert record["detected_language"] == "en"


# -- Part 2: exposure allowlist --------------------------------------------


class TestExposureRegistry:
    """``expose_resource`` and ``is_exposed`` gate access."""

    def test_expose_then_is_exposed(self) -> None:
        assert not is_exposed("TestResource")
        expose_resource("TestResource")
        assert is_exposed("TestResource")

    def test_guard_implicitly_exposes(self) -> None:
        from airunner_services.api.resource_guards import (
            ResourceGuard,
            register_guard,
        )

        guard = ResourceGuard(resource_name="GuardedRes")
        register_guard(guard)
        assert is_exposed("GuardedRes")

    def test_clear_removes_exposure(self) -> None:
        expose_resource("TempRes")
        clear_registry()
        assert not is_exposed("TempRes")

    def test_framework_defaults_exposed(self) -> None:
        """Reload rpc_settings to trigger the module-level exposure
        registration, then verify all 15 framework resources are
        exposed."""
        import importlib

        import airunner_services.api.routes.rpc_settings as mod

        importlib.reload(mod)
        framework = {
            "ApplicationSettings",
            "Chatbot",
            "EspeakSettings",
            "GeneratorSettings",
            "LanguageSettings",
            "LLMGeneratorSettings",
            "MemorySettings",
            "OpenVoiceSettings",
            "PathSettings",
            "PromptTemplate",
            "ShortcutKeys",
            "SoundSettings",
            "STTSettings",
            "User",
            "VoiceSettings",
        }
        for name in framework:
            assert is_exposed(name), (
                f"expected {name!r} to be framework-exposed"
            )
        # A resource that is not exposed and has no guard
        assert not is_exposed("KnowledgeFact")


class TestResourceStoreTableGating:
    """``resource_store_table`` raises LookupError for unexposed
    resources."""

    def test_unexposed_raises_lookup_error(self) -> None:
        from airunner_services.api.routes.rpc_settings import (
            resource_store_table,
        )

        with pytest.raises(LookupError, match="not exposed"):
            resource_store_table("KnowledgeFact")

    def test_exposed_succeeds(self) -> None:
        from airunner_services.api.routes.rpc_settings import (
            resource_store_table,
        )

        expose_resource("Chatbot")
        table = resource_store_table("Chatbot")
        assert table.__name__ == "Chatbot"


# -- Part 4: UserGuard -----------------------------------------------------


class TestUserGuardCheckOwnership:
    """``UserGuard.check_ownership`` rejects cross-account access."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import UserGuard

        self.guard = UserGuard()

    def test_own_row_passes(self) -> None:
        row = _make_row(id=42)
        self.guard.check_ownership(row, account_id=42, is_superuser=False)

    def test_other_row_rejected(self) -> None:
        row = _make_row(id=99)
        with pytest.raises(
            ResourceGuardRejected, match="do not own"
        ):
            self.guard.check_ownership(
                row, account_id=42, is_superuser=False
            )

    def test_superuser_bypasses_ownership(self) -> None:
        row = _make_row(id=99)
        self.guard.check_ownership(
            row, account_id=42, is_superuser=True
        )

    def test_no_account_id_rejected(self) -> None:
        row = _make_row(id=1)
        with pytest.raises(
            ResourceGuardRejected, match="do not own"
        ):
            self.guard.check_ownership(
                row, account_id=None, is_superuser=False
            )


class TestUserGuardSanitizeUpdate:
    """``UserGuard.sanitize_update`` strips server-authoritative
    currency/streak fields unconditionally."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import UserGuard

        self.guard = UserGuard()

    def test_currency_fields_stripped(self) -> None:
        row = _make_row(id=1, gems=0)
        values = {
            "gems": 999999,
            "daily_pulls_taken": 50,
            "paid_pulls_available": 100,
            "username": "hacker",
        }
        result = self.guard.sanitize_update(row, values)
        assert "gems" not in result
        assert "daily_pulls_taken" not in result
        assert "paid_pulls_available" not in result
        assert result["username"] == "hacker"

    def test_streak_fields_stripped(self) -> None:
        row = _make_row(id=1)
        values = {
            "streak_count": 999,
            "streak_last_date": "2026-01-01",
            "daily_gems_claimed_at": "2026-01-01T00:00:00",
            "daily_pulls_reset_at": "2026-01-01T00:00:00",
            "display_name": "test",
        }
        result = self.guard.sanitize_update(row, values)
        for field in (
            "streak_count",
            "streak_last_date",
            "daily_gems_claimed_at",
            "daily_pulls_reset_at",
        ):
            assert field not in result, f"{field} was not stripped"
        assert result["display_name"] == "test"

    def test_superuser_also_stripped(self) -> None:
        """Currency stripping is unconditional — superusers cannot
        bypass it through this generic channel."""
        row = _make_row(id=1, gems=10)
        values = {"gems": 999999, "display_name": "admin"}
        result = self.guard.sanitize_update(
            row, values, is_superuser=True
        )
        assert "gems" not in result
        assert result["display_name"] == "admin"

    def test_user_editable_fields_preserved(self) -> None:
        row = _make_row(id=1)
        values = {
            "username": "newuser",
            "zipcode": "80202",
            "location_display_name": "Denver",
            "latitude": 39.7392,
            "longitude": -104.9903,
            "unit_system": "metric",
            "preferred_language": "es",
            "display_name": "NewName",
            "gender": "Female",
            "avatar_image": "base64...",
            "banner_image": "base64...",
            "data": {"theme": "dark"},
        }
        result = self.guard.sanitize_update(row, values)
        for field in values:
            assert field in result, f"{field} was incorrectly stripped"


class TestUserGuardSanitizeCreate:
    """``UserGuard.sanitize_create`` also strips currency fields."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import UserGuard

        self.guard = UserGuard()

    def test_currency_fields_stripped_on_create(self) -> None:
        values = {
            "gems": 999,
            "username": "newuser",
            "display_name": "New",
        }
        result = self.guard.sanitize_create(values)
        assert "gems" not in result
        assert result["username"] == "newuser"
        assert result["display_name"] == "New"


class TestUserGuardSetupCompleteNotStripped:
    """Regression: ``setup_complete`` is client-writable (onboarding
    wizard sets it via updateSingleton in useUserSetup.ts)."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import UserGuard

        self.guard = UserGuard()

    def test_setup_complete_preserved_in_update(self) -> None:
        row = _make_row(id=1, setup_complete=False)
        values = {
            "setup_complete": True,
            "gems": 999,
            "streak_count": 50,
        }
        result = self.guard.sanitize_update(row, values)
        assert result["setup_complete"] is True, (
            "setup_complete must pass through for onboarding"
        )
        assert "gems" not in result
        assert "streak_count" not in result

    def test_all_server_fields_except_setup_complete_stripped(self) -> None:
        row = _make_row(id=1)
        values = {
            "setup_complete": True,
            "gems": 999,
            "daily_pulls_taken": 10,
            "daily_pulls_reset_at": "2026-01-01",
            "paid_pulls_available": 5,
            "daily_gems_claimed_at": "2026-01-01",
            "streak_count": 7,
            "streak_last_date": "2026-01-01",
        }
        result = self.guard.sanitize_update(row, values)
        assert result["setup_complete"] is True
        for field in (
            "gems",
            "daily_pulls_taken",
            "daily_pulls_reset_at",
            "paid_pulls_available",
            "daily_gems_claimed_at",
            "streak_count",
            "streak_last_date",
        ):
            assert field not in result, (
                f"{field} should be stripped"
            )


class TestUserGuardOwnershipInByMutationEndpoints:
    """``UserGuard.check_ownership`` rejects cross-account access
    for reset-defaults and make-current — the same class of bug
    that was closed for update-by-id and delete."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        from projects.uwuchat.server.security import UserGuard

        self.guard = UserGuard()

    def test_own_row_reset_defaults_passes(self) -> None:
        row = _make_row(id=42)
        self.guard.check_ownership(row, account_id=42, is_superuser=False)

    def test_other_row_reset_defaults_rejected(self) -> None:
        row = _make_row(id=99)
        with pytest.raises(
            ResourceGuardRejected, match="do not own"
        ):
            self.guard.check_ownership(
                row, account_id=42, is_superuser=False
            )

    def test_own_row_make_current_passes(self) -> None:
        row = _make_row(id=42)
        self.guard.check_ownership(row, account_id=42, is_superuser=False)

    def test_other_row_make_current_rejected(self) -> None:
        row = _make_row(id=99)
        with pytest.raises(
            ResourceGuardRejected, match="do not own"
        ):
            self.guard.check_ownership(
                row, account_id=42, is_superuser=False
            )

    def test_superuser_bypasses_ownership_both_endpoints(self) -> None:
        row = _make_row(id=99)
        self.guard.check_ownership(
            row, account_id=42, is_superuser=True
        )


# -- Round 4: filter_read superuser parity -------------------------------


class TestFilterReadSuperuserParity:
    """After round 4, ``filter_read`` returns the same narrowed result
    for superusers and non-superusers — no role gets the full row
    through the browser-facing WS channel."""

    def test_chatbot_guard_superuser_parity(self) -> None:
        from projects.uwuchat.server.security import ChatbotGuard

        guard = ChatbotGuard()
        record = {
            "id": 1,
            "name": "TestBot",
            "system_instructions": "secret prompt",
            "temperature": 1000,
            "is_system_bot": False,
        }
        non_admin = guard.filter_read(record, is_superuser=False)
        admin = guard.filter_read(record, is_superuser=True)
        assert admin == non_admin
        assert "system_instructions" not in admin
        assert "temperature" not in admin
        assert "name" in admin

    def test_application_settings_guard_superuser_parity(self) -> None:
        from projects.uwuchat.server.security import (
            ApplicationSettingsGuard,
        )

        guard = ApplicationSettingsGuard()
        record = {
            "id": 1,
            "detected_language": "en",
            "openai_api_key": "sk-secret",
            "sd_enabled": True,
        }
        non_admin = guard.filter_read(record, is_superuser=False)
        admin = guard.filter_read(record, is_superuser=True)
        assert admin == non_admin
        assert admin == {"id": 1, "detected_language": "en"}

    def test_llm_generator_settings_guard_superuser_parity(self) -> None:
        from projects.uwuchat.server.security import (
            LLMGeneratorSettingsGuard,
        )

        guard = LLMGeneratorSettingsGuard()
        record = {
            "id": 1,
            "model_path": "gpt-4",
            "temperature": 1000,
            "top_p": 900,
        }
        non_admin = guard.filter_read(record, is_superuser=False)
        admin = guard.filter_read(record, is_superuser=True)
        assert admin == non_admin
        assert admin == {"id": 1, "model_path": "gpt-4"}

    def test_pipeline_config_guard_superuser_parity(self) -> None:
        from projects.uwuchat.server.security import (
            PipelineConfigGuard,
        )

        guard = PipelineConfigGuard()
        record = {
            "id": 1,
            "pipeline_key": "llm",
            "overrides": {"model": "gpt-4"},
            "updated_by": "admin",
        }
        non_admin = guard.filter_read(record, is_superuser=False)
        admin = guard.filter_read(record, is_superuser=True)
        assert admin == non_admin
        assert admin == {"id": 1, "pipeline_key": "llm"}

    def test_chatbot_block_reason_and_offline_reason_stripped(self) -> None:
        """Round 5: block_reason/offline_reason are moderation text
        never rendered by any client component."""
        from projects.uwuchat.server.security import ChatbotGuard

        guard = ChatbotGuard()
        record = {
            "id": 1,
            "name": "TestBot",
            "has_blocked_user": True,
            "blocked_by_user": False,
            "block_reason": "Repeated boundary violations detected",
            "offline_reason": "Scheduled maintenance window",
        }
        result = guard.filter_read(record, is_superuser=False)
        # Blocklist fields stripped
        assert "block_reason" not in result
        assert "offline_reason" not in result
        # Boolean flags still visible
        assert result["has_blocked_user"] is True
        assert result["blocked_by_user"] is False
        assert result["name"] == "TestBot"
        # Superuser parity (round 4)
        admin = guard.filter_read(record, is_superuser=True)
        assert admin == result
        assert "block_reason" not in admin
        assert "offline_reason" not in admin
