"""Regression test: model_path property rejects path-traversal payloads.

Round 9, Part 3 — ensures the fix in property_mixin.py's ``model_path``
property prevents a connected client from escaping ``AIRUNNER_BASE_PATH``
via a ``../`` traversal in ``LLMRequest.model``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_mixin_with_model(model_value: str) -> object:
    """Build a PropertyMixin with ``LLMRequest.model`` set to *model_value*.

    Uses ``unittest.mock.MagicMock`` for heavy dependencies (settings,
    LLMProviderConfig) so the test does not need a full app context.
    """
    from airunner_services.llm.managers.mixins.property_mixin import (
        PropertyMixin,
    )

    mixin = PropertyMixin()
    mixin.logger = MagicMock()

    # Simulate a request with a client-supplied model value.
    mock_request = MagicMock()
    mock_request.model = model_value
    mixin.llm_request = mock_request

    # path_settings.base_path must be set for the confinement check.
    base = "/home/user/.local/share/airunner"
    mock_path_settings = MagicMock()
    mock_path_settings.base_path = base
    mixin.path_settings = mock_path_settings

    return mixin


@pytest.fixture(autouse=True)
def _mock_provider_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch LLMProviderConfig so resolve_model_id always returns None.

    This forces the code into the path-shaped branch (the ``elif``)
    rather than the resolved-model-ID branch.
    """
    from airunner_services.llm.managers.mixins import (
        property_mixin as mod,
    )

    def _resolve_never(_provider: str, _value: str) -> None:
        return None

    monkeypatch.setattr(
        mod.LLMProviderConfig,
        "resolve_model_id",
        _resolve_never,
    )


class TestModelPathConfinement:
    """Path-traversal payloads must raise ValueError, not escape base_path."""

    def test_relative_traversal_rejected(self) -> None:
        """``../../../etc/passwd`` must raise ValueError."""
        mixin = _make_mixin_with_model("../../../etc/passwd")
        with pytest.raises(ValueError, match="outside"):
            _ = mixin.model_path

    def test_absolute_outside_base_rejected(self) -> None:
        """An absolute path outside base_path must raise ValueError."""
        mixin = _make_mixin_with_model("/etc/passwd")
        with pytest.raises(ValueError, match="outside"):
            _ = mixin.model_path

    def test_path_inside_base_passes(self) -> None:
        """A path inside base_path (simulating a valid host path) must
        not raise the confinement error.

        Uses ``base_path/text/models/llm/causallm/some-model/`` so the
        resolved path stays within base_path.
        """
        base = "/home/user/.local/share/airunner"
        valid = f"{base}/text/models/llm/causallm/some-model/"
        mixin = _make_mixin_with_model(valid)
        # Mock out the rest of model_path so it doesn't crash on
        # missing downstream dependencies.
        mock_llm_settings = MagicMock()
        mock_llm_settings.model_id = None
        mock_llm_settings.model_path = ""
        mixin.llm_generator_settings = mock_llm_settings
        try:
            _ = mixin.model_path
        except ValueError as exc:
            if "outside" in str(exc):
                raise AssertionError(
                    f"Valid path inside base_path was rejected: {exc}"
                ) from exc
            # Any other ValueError (e.g. embedding-model guard) is fine.
