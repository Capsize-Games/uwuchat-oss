"""Tests for the prompt-rewrite classification stage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage


class TestPromptRewriteClassification:
    """The classification model correctly identifies unrealistic
    quantity requests."""

    def test_flags_unrealistic_quantity(self) -> None:
        """A 'find 50 X' prompt is flagged and rewritten."""
        from projects.uwuchat.server.prompt_rewrite_stage import (
            run_prompt_rewrite_stage,
        )

        chat_model = MagicMock()
        chat_model.invoke.return_value = AIMessage(
            content=(
                "NEEDS_REWRITE: Find a handful of well-sourced "
                "articles on a topic covering different time periods "
                "if possible, and tell me what you learn"
            ),
        )

        original = (
            "Find 50 different articles on a topic from over "
            "the years and tell me what you learn from those "
            "articles"
        )
        rewritten, reason = run_prompt_rewrite_stage(
            chat_model=chat_model,
            prompt=original,
        )

        assert reason == "unrealistic quantity"
        assert rewritten is not None
        assert rewritten != original
        assert "50" not in rewritten

    def test_ok_prompt_passes_through(self) -> None:
        """A normal, reasonably-scoped prompt passes through."""
        from projects.uwuchat.server.prompt_rewrite_stage import (
            run_prompt_rewrite_stage,
        )

        chat_model = MagicMock()
        chat_model.invoke.return_value = AIMessage(
            content="OK: What is the latest news on this topic?",
        )

        original = "What is the latest news on this topic?"
        rewritten, reason = run_prompt_rewrite_stage(
            chat_model=chat_model,
            prompt=original,
        )

        assert reason == "scope acceptable"
        assert rewritten is None or rewritten == original

    def test_classification_failure_fails_open(self) -> None:
        """A classification model exception fails open."""
        from projects.uwuchat.server.prompt_rewrite_stage import (
            run_prompt_rewrite_stage,
        )

        chat_model = MagicMock()
        chat_model.invoke.side_effect = RuntimeError("timeout")

        original = "Find 50 articles on X"
        result, reason = run_prompt_rewrite_stage(
            chat_model=chat_model,
            prompt=original,
        )

        assert result == original
        assert reason is None

    def test_unparseable_response_fails_open(self) -> None:
        """An unparseable model response fails open."""
        from projects.uwuchat.server.prompt_rewrite_stage import (
            run_prompt_rewrite_stage,
        )

        chat_model = MagicMock()
        chat_model.invoke.return_value = AIMessage(
            content="Here is my analysis of your request...",
        )

        original = "Find 50 articles on X"
        result, reason = run_prompt_rewrite_stage(
            chat_model=chat_model,
            prompt=original,
        )

        assert result == original
        assert reason == "unparseable response"


class TestMaybeRewriteDataPrompt:
    """_maybe_rewrite_data_prompt returns rewritten text without
    mutating the data dict."""

    def test_no_model_returns_none(self) -> None:
        """When PROMPT_REWRITE is not configured, returns None."""
        from airunner_services.llm.managers.mixins.request_handling_mixin import (
            _maybe_rewrite_data_prompt,
        )

        owner = MagicMock()
        owner._specialized_chat_models = {}
        owner.logger = MagicMock()

        data = {"request_data": {"prompt": "Find 50 articles on X"}}
        result = _maybe_rewrite_data_prompt(owner, data)

        assert result is None
        assert data["request_data"]["prompt"] == "Find 50 articles on X"

    def test_returns_rewritten_without_mutating_data(self) -> None:
        """Returns rewritten text, dict unchanged."""
        import sys

        from airunner_services.llm.managers.mixins.request_handling_mixin import (
            _maybe_rewrite_data_prompt,
        )

        owner = MagicMock()
        owner._specialized_chat_models = {
            "PROMPT_REWRITE": MagicMock(),
        }
        owner.logger = MagicMock()

        fake_mod = MagicMock()
        fake_mod.run_prompt_rewrite_stage = MagicMock(
            return_value=(
                "Find a few articles on X",
                "unrealistic quantity",
            ),
        )
        sys.modules[
            "projects.uwuchat.server.prompt_rewrite_stage"
        ] = fake_mod

        try:
            data = {
                "request_data": {"prompt": "Find 50 articles on X"}
            }
            result = _maybe_rewrite_data_prompt(owner, data)

            assert result == "Find a few articles on X"
            assert (
                data["request_data"]["prompt"]
                == "Find 50 articles on X"
            )
        finally:
            del sys.modules[
                "projects.uwuchat.server.prompt_rewrite_stage"
            ]

    def test_import_error_returns_none(self) -> None:
        """Returns None on ImportError, dict unchanged."""
        import sys

        from airunner_services.llm.managers.mixins.request_handling_mixin import (
            _maybe_rewrite_data_prompt,
        )

        owner = MagicMock()
        owner._specialized_chat_models = {
            "PROMPT_REWRITE": MagicMock(),
        }
        owner.logger = MagicMock()

        sys.modules.pop(
            "projects.uwuchat.server.prompt_rewrite_stage", None
        )

        original_import = __import__

        def _failing_import(name, *args, **kwargs):
            if name == "projects.uwuchat.server.prompt_rewrite_stage":
                raise ImportError("no module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", _failing_import):
            data = {
                "request_data": {"prompt": "Find 50 articles on X"}
            }
            result = _maybe_rewrite_data_prompt(owner, data)

        assert result is None
        assert (
            data["request_data"]["prompt"] == "Find 50 articles on X"
        )

    def test_stage_exception_returns_none(self) -> None:
        """Returns None when stage raises, dict unchanged."""
        import sys

        from airunner_services.llm.managers.mixins.request_handling_mixin import (
            _maybe_rewrite_data_prompt,
        )

        owner = MagicMock()
        owner._specialized_chat_models = {
            "PROMPT_REWRITE": MagicMock(),
        }
        owner.logger = MagicMock()

        fake_mod = MagicMock()
        fake_mod.run_prompt_rewrite_stage = MagicMock(
            side_effect=RuntimeError("timeout"),
        )
        sys.modules[
            "projects.uwuchat.server.prompt_rewrite_stage"
        ] = fake_mod

        try:
            data = {
                "request_data": {"prompt": "Find 50 articles on X"}
            }
            result = _maybe_rewrite_data_prompt(owner, data)

            assert result is None
            assert (
                data["request_data"]["prompt"]
                == "Find 50 articles on X"
            )
        finally:
            del sys.modules[
                "projects.uwuchat.server.prompt_rewrite_stage"
            ]


class TestPromptRewriteModelLoaded:
    """_dialogue_routing_subset includes PROMPT_REWRITE from
    PIPELINE_CONFIG so the model router actually loads it."""

    def test_routing_subset_includes_prompt_rewrite(self) -> None:
        """When PIPELINE_CONFIG has PROMPT_REWRITE,
        _dialogue_routing_subset includes it."""
        from airunner_services.llm.model_router import (
            _dialogue_routing_subset,
        )

        pipeline = {
            "DIALOGUE": {"provider": "openrouter", "model": "test"},
            "PROMPT_REWRITE": {
                "provider": "openrouter",
                "model": "test-rewrite",
                "max_tokens": 256,
            },
        }
        subset = _dialogue_routing_subset(pipeline)
        assert "PROMPT_REWRITE" in subset, (
            f"PROMPT_REWRITE missing: {list(subset.keys())}"
        )

    def test_routing_subset_absent_when_not_in_config(self) -> None:
        """When PIPELINE_CONFIG has no PROMPT_REWRITE,
        _dialogue_routing_subset excludes it."""
        from airunner_services.llm.model_router import (
            _dialogue_routing_subset,
        )

        pipeline = {
            "DIALOGUE": {"provider": "openrouter", "model": "test"},
        }
        subset = _dialogue_routing_subset(pipeline)
        assert "PROMPT_REWRITE" not in subset
