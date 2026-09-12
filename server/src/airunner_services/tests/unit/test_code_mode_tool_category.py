"""Tests for the code-mode tool-category hook in auto tool selection.

Covers:
1. ``_project_code_mode_active`` — the guarded project import returns
   True/False correctly and never raises.
2. ``_auto_select_tool_categories`` — when the hook is active, "code"
   is appended to the selected categories so the inline agent tools
   (execute_command, read_file, ...) get bound to DIALOGUE even when
   the heuristic/classifier picked something else.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from airunner_services.llm.managers.mixins.tool_classification_mixin.detectors import (
    ToolClassificationDetectorsMixin,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.patterns import (
    ToolClassificationPatternsMixin,
)
from airunner_services.llm.managers.mixins.tool_filtering_mixin._auto import (
    ToolFilterAutoMixin,
    _project_code_mode_active,
)


class TestProjectCodeModeActive:
    """Unit tests for the guarded _project_code_mode_active helper."""

    @staticmethod
    def _call(monkeypatch, stub_result=None, raise_error=False):
        """Call the helper with a stubbed project module."""
        stub = MagicMock()
        if raise_error:
            stub.code_mode_active_for_owner = MagicMock(
                side_effect=RuntimeError("boom"),
            )
        else:
            stub.code_mode_active_for_owner = MagicMock(
                return_value=stub_result,
            )
        monkeypatch.setenv("AIRUNNER_PROJECT", "uwuchat")
        with patch("importlib.import_module", return_value=stub) as imp:
            result = _project_code_mode_active(MagicMock())
        return result, imp

    def test_active_project_returns_true(self, monkeypatch) -> None:
        """Hook returns True when the project module says code mode on."""
        result, imp = self._call(monkeypatch, stub_result=True)
        assert result is True
        imp.assert_called_once_with("projects.uwuchat.server.code_mode_service")

    def test_active_project_returns_false(self, monkeypatch) -> None:
        """Hook returns False when the project module says code mode off."""
        result, _ = self._call(monkeypatch, stub_result=False)
        assert result is False

    def test_no_project_env_returns_false(self, monkeypatch) -> None:
        """No AIRUNNER_PROJECT and no settings value → False."""
        monkeypatch.setenv("AIRUNNER_PROJECT", "")
        # Stub the settings fallback so a .env-loaded AIRUNNER_PROJECT
        # can't leak into the assertion.
        import airunner_services.conf as conf_mod

        fake_settings = MagicMock()
        fake_settings.AIRUNNER_PROJECT = ""
        monkeypatch.setattr(conf_mod, "settings", fake_settings)
        with patch(
            "importlib.import_module",
        ) as imp:
            result = _project_code_mode_active(MagicMock())
        assert result is False
        imp.assert_not_called()

    def test_missing_module_function_returns_false(self, monkeypatch) -> None:
        """A project module without code_mode_active_for_owner → False."""
        stub = MagicMock()
        del stub.code_mode_active_for_owner
        monkeypatch.setenv("AIRUNNER_PROJECT", "uwuchat")
        with patch("importlib.import_module", return_value=stub):
            result = _project_code_mode_active(MagicMock())
        assert result is False

    def test_import_error_returns_false(self, monkeypatch) -> None:
        """An import failure is swallowed and returns False."""
        monkeypatch.setenv("AIRUNNER_PROJECT", "uwuchat")
        with patch(
            "importlib.import_module",
            side_effect=ImportError("no module"),
        ):
            result = _project_code_mode_active(MagicMock())
        assert result is False

    def test_callback_exception_returns_false(self, monkeypatch) -> None:
        """A callback exception is swallowed and returns False."""
        result, _ = self._call(monkeypatch, raise_error=True)
        assert result is False


class _StubOwner(ToolFilterAutoMixin, ToolClassificationDetectorsMixin,
                 ToolClassificationPatternsMixin):
    """Minimal composed owner for _auto_select_tool_categories tests."""

    def _classify_prompt_for_tools(self, prompt, allow_thinking=True):
        """Stand-in for the classifier mixin's method (not in this MRO)."""
        return ["research"]


class TestCodeModeToolCategoryInAutoSelection:
    """Integration through _auto_select_tool_categories."""

    @staticmethod
    def _make_stub():
        stub = _StubOwner()
        stub.logger = MagicMock()
        stub._emit_tool_selection_status = lambda *a, **k: None
        return stub

    def test_weather_prompt_appends_code_when_hook_active(self) -> None:
        """Weather trigger fires ("system"), then code is appended."""
        stub = self._make_stub()
        with patch(
            "airunner_services.llm.managers.mixins.tool_filtering_mixin."
            "_auto._project_code_mode_active",
            return_value=True,
        ):
            categories, force_tool = stub._auto_select_tool_categories(
                prompt="what's the weather in Denver",
            )

        assert "system" in categories
        assert "code" in categories
        assert force_tool is None
        stub.logger.info.assert_any_call(
            "Auto mode: code mode active — added 'code' category"
        )

    def test_no_code_when_hook_inactive(self) -> None:
        """Weather trigger fires but code is not appended when hook off."""
        stub = self._make_stub()
        with patch(
            "airunner_services.llm.managers.mixins.tool_filtering_mixin."
            "_auto._project_code_mode_active",
            return_value=False,
        ):
            categories, _ = stub._auto_select_tool_categories(
                prompt="what's the weather in Denver",
            )

        assert categories == ["system"]
        assert "code" not in categories

    def test_code_not_duplicated_when_already_selected(self) -> None:
        """If the classifier already picked "code", no duplicate append."""
        stub = self._make_stub()
        with patch(
            "airunner_services.llm.managers.mixins.tool_filtering_mixin."
            "_auto._project_code_mode_active",
            return_value=True,
        ), patch.object(
            stub,
            "_classify_prompt_for_tools",
            return_value=["code"],
        ):
            categories, _ = stub._auto_select_tool_categories(
                prompt="run the test suite for the airunner repo",
            )

        assert categories.count("code") == 1
