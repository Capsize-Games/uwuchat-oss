"""Tests for the code-mode output-token ceiling override.

The per-tier ``MAX_OUTPUT_TOKENS`` ceiling (300-800) clamps every
streaming reply, including code-mode conversations where the inline
agent tools narrate real work.  These tests verify that code-mode
conversations resolve to ``CODE_MODE_MAX_OUTPUT_TOKENS`` (8192) while
everything else keeps the tier ceiling.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import patch

from airunner_services.api.routes.llm_runtime import (
    CODE_MODE_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    _conversation_is_code_mode,
)

_PROJECT = "uwuchat"


def _stub_project_module(result: bool) -> ModuleType:
    """Return a stub ``code_mode_service`` module with *result*."""
    stub = ModuleType(f"projects.{_PROJECT}.server.code_mode_service")
    stub.get_code_mode = lambda conv_id: result
    return stub


def test_no_conversation_id_returns_false() -> None:
    """A missing conversation id can never be code mode."""
    assert _conversation_is_code_mode(None) is False


def test_code_mode_on_resolves_to_true() -> None:
    """A conversation with code mode on resolves to True."""
    stub = _stub_project_module(result=True)
    with (
        patch.dict("os.environ", {"AIRUNNER_PROJECT": _PROJECT}),
        patch.dict(
            sys.modules,
            {f"projects.{_PROJECT}.server.code_mode_service": stub},
        ),
    ):
        assert _conversation_is_code_mode(7) is True


def test_code_mode_off_resolves_to_false() -> None:
    """A conversation with code mode off resolves to False."""
    stub = _stub_project_module(result=False)
    with (
        patch.dict("os.environ", {"AIRUNNER_PROJECT": _PROJECT}),
        patch.dict(
            sys.modules,
            {f"projects.{_PROJECT}.server.code_mode_service": stub},
        ),
    ):
        assert _conversation_is_code_mode(7) is False


def test_import_error_is_noop() -> None:
    """A missing project module (non-UwUchat) is a pure no-op."""
    with patch.dict("os.environ", {"AIRUNNER_PROJECT": "other"}):
        assert _conversation_is_code_mode(7) is False


def test_ceiling_constants_are_sane() -> None:
    """The code-mode ceiling must be well above the tier default."""
    assert CODE_MODE_MAX_OUTPUT_TOKENS > DEFAULT_MAX_OUTPUT_TOKENS
    assert CODE_MODE_MAX_OUTPUT_TOKENS == 8192
