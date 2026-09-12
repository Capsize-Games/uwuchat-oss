"""Tests for the session-bootstrap push message sent after WS connect.

Verifies that:
1. ``build_bootstrap_payload`` exists in ``events_bootstrap.py`` and is
   called from ``unified_events`` in ``events.py``.
2. The bootstrap helpers reuse existing field-level guard filtering
   (``_apply_read_filter``) rather than reimplementing serialization.
3. Guard filtering is applied: a ``Chatbot`` record in the bootstrap
   payload never contains ``system_instructions`` or ``block_reason``.
4. ``LanguageSettings`` is included (needed by ``AuthedLanguageSwitcher``
   in the persistent TopBar — not a settings-panel-only concern).
"""

from __future__ import annotations

import inspect


class TestBootstrapPayloadStructural:
    """Verify ``build_bootstrap_payload`` in ``events_bootstrap.py`` is
    wired into the WS connect path and reuses the existing guard-filter
    helpers."""

    def test_build_bootstrap_function_exists(self) -> None:
        """``build_bootstrap_payload`` is defined in
        events_bootstrap.py."""
        from airunner_services.api.routes import events_bootstrap

        source = inspect.getsource(events_bootstrap)
        assert "build_bootstrap_payload" in source
        assert "async def build_bootstrap_payload" in source

    def test_bootstrap_called_from_unified_events(self) -> None:
        """``unified_events`` imports and calls
        ``build_bootstrap_payload`` after tenant scope resolution."""
        from airunner_services.api.routes import events

        source = inspect.getsource(events.unified_events)
        assert "build_bootstrap_payload" in source
        assert '"type": "bootstrap"' in source

    def test_bootstrap_reuses_apply_read_filter(self) -> None:
        """The per-resource helpers in ``events_bootstrap.py`` call
        ``_apply_read_filter`` (the same guard-filter function used by
        the singleton/query RPC handlers)."""
        from airunner_services.api.routes import events_bootstrap

        source = inspect.getsource(events_bootstrap)
        assert "_apply_read_filter" in source
        assert "_record_from_item" in source

    def test_bootstrap_reuses_apply_filters(self) -> None:
        """``events_bootstrap.py`` calls ``_apply_filters`` for
        queries so ``deleted=False`` is enforced identically."""
        from airunner_services.api.routes import events_bootstrap

        source = inspect.getsource(events_bootstrap)
        assert "_apply_filters" in source

    def test_bootstrap_has_per_field_tolerance(self) -> None:
        """Each resource lookup in ``build_bootstrap_payload`` is
        wrapped in its own ``try/except`` so one failure does not
        prevent the others from being sent."""
        from airunner_services.api.routes import events_bootstrap

        source = inspect.getsource(events_bootstrap)
        fn_start = source.find(
            "async def build_bootstrap_payload"
        )
        assert fn_start != -1
        fn_source = source[fn_start:]
        # Four try/except blocks — one per resource (now includes
        # LanguageSettings).
        assert fn_source.count("except Exception as exc:") >= 4

    def test_bootstrap_payload_has_expected_keys(self) -> None:
        """The bootstrap body contains ``application_settings``,
        ``language_settings``, ``chatbots``, and ``project_setting``
        keys."""
        from airunner_services.api.routes import events_bootstrap

        source = inspect.getsource(events_bootstrap)
        fn_start = source.find(
            "async def build_bootstrap_payload"
        )
        assert fn_start != -1
        fn_source = source[fn_start:]
        assert '"application_settings"' in fn_source
        assert '"language_settings"' in fn_source
        assert '"chatbots"' in fn_source
        assert '"project_setting"' in fn_source

    def test_per_resource_helpers_exist(self) -> None:
        """Each resource has its own small helper function in
        ``events_bootstrap.py``."""
        from airunner_services.api.routes import events_bootstrap

        source = inspect.getsource(events_bootstrap)
        assert "async def _bootstrap_application_settings" in source
        assert "async def _bootstrap_language_settings" in source
        assert "async def _bootstrap_chatbots" in source
        assert "async def _bootstrap_project_setting" in source


class TestForceLogoutOnStaleDek:
    """Verify that ``unified_events`` in ``events.py`` sends a
    ``force_logout`` frame and skips the bootstrap push when the
    in-memory DEK cache has no entry for the connecting account
    (server restart / TTL expiry)."""

    def test_force_logout_frame_type_present(self) -> None:
        """``unified_events`` contains the ``"force_logout"`` frame
        type string and the ``"stale_session"`` guard flag."""
        from airunner_services.api.routes import events

        source = inspect.getsource(events.unified_events)
        assert '"type": "force_logout"' in source
        assert "stale_session" in source

    def test_bootstrap_gated_by_stale_session(self) -> None:
        """The bootstrap push is guarded by ``if not stale_session:``
        so it is skipped when the DEK is missing."""
        from airunner_services.api.routes import events

        source = inspect.getsource(events.unified_events)
        assert "if not stale_session:" in source

    def test_cache_get_imported_in_dek_check(self) -> None:
        """``cache_get`` is imported from ``dek_cache`` inside the
        stale-session check path."""
        from airunner_services.api.routes import events

        source = inspect.getsource(events.unified_events)
        assert "from airunner_services.utils.crypto.dek_cache import" in source
        assert "cache_get" in source

    def test_force_logout_reason_matches_error_sanitizer(self) -> None:
        """The ``reason`` string in the ``force_logout`` frame reuses
        the exact ``encryption_session_expired`` code from
        ``error_sanitizer.py``."""
        from airunner_services.api.routes import events

        source = inspect.getsource(events.unified_events)
        assert '"reason": "encryption_session_expired"' in source


class TestBootstrapGuardFilteringContacts:
    """Verify that the bootstrap payload would respect the same guard
    filters the singleton/query RPC handlers enforce.  These are unit
    tests against the guards themselves — the structural tests above
    confirm the bootstrap code path calls them."""

    def test_chatbot_guard_strips_system_instructions(self) -> None:
        """``ChatbotGuard.filter_read`` removes
        ``system_instructions``."""
        from projects.uwuchat.server.security import ChatbotGuard

        guard = ChatbotGuard()
        record = {
            "id": 1,
            "name": "TestBot",
            "system_instructions": "secret prompt",
            "block_reason": "violation",
            "temperature": 0.7,
        }
        result = guard.filter_read(record, is_superuser=False)
        assert "system_instructions" not in result
        assert "block_reason" not in result
        assert "temperature" not in result
        assert "name" in result

    def test_application_settings_guard_strips_api_keys(self) -> None:
        """``ApplicationSettingsGuard.filter_read`` returns only
        ``id`` and ``detected_language``."""
        from projects.uwuchat.server.security import (
            ApplicationSettingsGuard,
        )

        guard = ApplicationSettingsGuard()
        record = {
            "id": 1,
            "detected_language": "ja",
            "openai_api_key": "sk-topsecret",
            "hf_api_key_read_key": "hf-abc",
        }
        result = guard.filter_read(record, is_superuser=False)
        assert result == {"id": 1, "detected_language": "ja"}
