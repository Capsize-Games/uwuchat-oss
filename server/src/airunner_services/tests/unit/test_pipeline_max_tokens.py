"""Tests that every pipeline has an explicit ``max_tokens`` value.

Before the fix (plan uwuchat-dialogue-knowledge-max-tokens-truncation.md),
several pipelines silently fell through to the 500-token builder default
because they had no ``max_tokens`` key in the pipeline config at all.
"""

from __future__ import annotations

from airunner_services.llm.pipeline_defaults import PIPELINE_DEFAULTS


# -- pipelines that MUST have max_tokens (framework defaults) -----------

_FRAMEWORK_PIPELINES_WITH_TOKENS = {
    "DIALOGUE",
    "TOOL_CLASSIFICATION",
    "SUMMARIZATION",
    "STATELESS",
    "INTRA_SESSION_MOOD",
    "ROLLING_COMPRESSOR",
    "EPISODIC_SUMMARIZER",
    "MEMORY_UPDATER",
    "WORLD_TICK",
    "NODE_VALIDATOR",
    "CURIOSITY_ENGINE",
    "INTERJECTION",
    "KNOWLEDGE",
}


def _load_uwuchat_pipeline_config() -> dict:
    """Return the UwUchat project pipeline config dict."""
    from projects.uwuchat.server.ai_pipeline import PIPELINE_CONFIG
    return PIPELINE_CONFIG  # type: ignore[no-any-return]


class TestFrameworkPipelineDefaultsHaveMaxTokens:
    """Every text-generation pipeline in the framework defaults must
    have an explicit ``max_tokens`` so it does not silently fall
    through to the 500-token builder default."""

    @staticmethod
    def _pipeline_keys() -> list[str]:
        return sorted(_FRAMEWORK_PIPELINES_WITH_TOKENS)

    def test_every_required_pipeline_exists(self) -> None:
        """The expected pipeline keys must be present in
        PIPELINE_DEFAULTS."""
        for key in self._pipeline_keys():
            assert key in PIPELINE_DEFAULTS, (
                f"Pipeline key {key!r} is missing from PIPELINE_DEFAULTS"
            )

    def test_every_required_pipeline_has_max_tokens(self) -> None:
        """Every pipeline in the required set must have a
        ``max_tokens`` key."""
        for key in self._pipeline_keys():
            cfg = PIPELINE_DEFAULTS[key]
            assert "max_tokens" in cfg, (
                f"Pipeline {key!r} has no max_tokens in "
                "PIPELINE_DEFAULTS"
            )

    def test_max_tokens_is_positive_int(self) -> None:
        """Every ``max_tokens`` value must be a positive integer."""
        for key in self._pipeline_keys():
            cfg = PIPELINE_DEFAULTS[key]
            val = cfg.get("max_tokens")
            if val is None:
                continue  # absence is caught by the previous test
            assert isinstance(val, int), (
                f"Pipeline {key!r} max_tokens is not an int: {val!r}"
            )
            assert val > 0, (
                f"Pipeline {key!r} max_tokens is not positive: {val}"
            )

    def test_affected_pipelines_no_longer_default_to_500(self) -> None:
        """Pipelines that need headroom above the old 500 default
        (DIALOGUE, KNOWLEDGE, STATELESS) must have max_tokens > 500.
        SUMMARIZATION deliberately stays at 500 and is excluded."""
        must_exceed = {
            "DIALOGUE", "KNOWLEDGE", "STATELESS",
        }
        for key in must_exceed:
            val = PIPELINE_DEFAULTS[key].get("max_tokens")
            assert val is not None, (
                f"Pipeline {key!r} has no max_tokens"
            )
            assert val > 500, (
                f"Pipeline {key!r} max_tokens={val} is not above "
                "the old 500 default"
            )

    def test_specific_max_tokens_values_match_spec(self) -> None:
        """Spot-check the expected values from the plan."""
        expected = {
            "DIALOGUE": 2048,
            "TOOL_CLASSIFICATION": 256,
            "SUMMARIZATION": 500,
            "STATELESS": 1024,
            "KNOWLEDGE": 1500,
            "CURIOSITY_ENGINE": 256,
            "INTERJECTION": 256,
        }
        for key, want in expected.items():
            got = PIPELINE_DEFAULTS[key].get("max_tokens")
            assert got == want, (
                f"Pipeline {key!r} max_tokens={got!r}, expected {want}"
            )


class TestUwuchatProjectPipelineHasMaxTokens:
    """UwUChat-specific pipelines (TOOL_EXECUTION, JOURNAL_SUMMARIZER)
    must also carry an explicit ``max_tokens``."""

    @staticmethod
    def _uwuchat_expected() -> dict:
        return _load_uwuchat_pipeline_config()

    def test_tool_execution_has_max_tokens(self) -> None:
        """TOOL_EXECUTION must have an explicit max_tokens."""
        cfg = self._uwuchat_expected()
        assert "TOOL_EXECUTION" in cfg, (
            "TOOL_EXECUTION pipeline missing from UwUChat config"
        )
        val = cfg["TOOL_EXECUTION"].get("max_tokens")
        assert val is not None, "TOOL_EXECUTION has no max_tokens"
        assert isinstance(val, int), f"max_tokens is not int: {val!r}"
        assert val == 1024, f"TOOL_EXECUTION max_tokens={val}, want 1024"

    def test_journal_summarizer_has_max_tokens(self) -> None:
        """JOURNAL_SUMMARIZER must have an explicit max_tokens."""
        cfg = self._uwuchat_expected()
        assert "JOURNAL_SUMMARIZER" in cfg, (
            "JOURNAL_SUMMARIZER pipeline missing from UwUChat config"
        )
        val = cfg["JOURNAL_SUMMARIZER"].get("max_tokens")
        assert val is not None, "JOURNAL_SUMMARIZER has no max_tokens"
        assert isinstance(val, int), f"max_tokens is not int: {val!r}"
        assert val == 500, f"JOURNAL_SUMMARIZER max_tokens={val}, want 500"
