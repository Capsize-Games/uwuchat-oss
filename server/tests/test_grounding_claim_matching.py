"""Unit tests for the deterministic claim-matching helper."""

from airunner_services.llm.tools.grounding_tools_helpers._claim_matching import (
    check_claims_against_sources,
    _significant_words,
    _token_overlap_ratio,
    _best_fuzzy_ratio,
    _extract_snippet,
)


class TestSignificantWords:
    """Token extraction from claim / source text."""

    def test_basic_extraction(self):
        words = _significant_words(
            "The quick brown fox jumps over the lazy dog"
        )
        assert "quick" in words
        assert "brown" in words
        assert "jumps" in words
        assert "over" in words
        assert "lazy" in words
        assert "the" not in words  # < 4 chars
        assert "fox" not in words  # 3 chars

    def test_empty_string(self):
        assert _significant_words("") == set()

    def test_short_words_only(self):
        assert _significant_words("a an the is at on") == set()


class TestTokenOverlapRatio:
    """Token overlap between claim and source."""

    def test_full_overlap(self):
        claim = {"quick", "brown", "jumps"}
        ratio = _token_overlap_ratio(
            claim, "the quick brown fox jumps over"
        )
        assert ratio == 1.0

    def test_partial_overlap(self):
        claim = {"quick", "brown", "zebra"}
        ratio = _token_overlap_ratio(
            claim, "the quick brown fox jumps over"
        )
        assert ratio == 2.0 / 3.0

    def test_no_overlap(self):
        claim = {"zebra", "giraffe"}
        ratio = _token_overlap_ratio(claim, "quick brown fox")
        assert ratio == 0.0


class TestBestFuzzyRatio:
    """Fuzzy matching between claim and source."""

    def test_exact_match(self):
        ratio = _best_fuzzy_ratio("hello world", "hello world")
        assert ratio == 1.0

    def test_partial_match(self):
        ratio = _best_fuzzy_ratio(
            "the quick brown fox",
            "the quick brown dog",
        )
        assert ratio > 0.7

    def test_no_match(self):
        ratio = _best_fuzzy_ratio(
            "abcdefghij",
            "zyxwvutsrq",
        )
        assert ratio < 0.4

    def test_needle_longer_than_haystack(self):
        ratio = _best_fuzzy_ratio(
            "the quick brown fox",
            "quick",
        )
        assert ratio < 0.5


class TestExtractSnippet:
    """Snippet extraction around best fuzzy match."""

    def test_short_source(self):
        src = "short text"
        result = _extract_snippet(src, "short")
        assert result == src

    def test_long_source_excerpt(self):
        src = "a" * 500 + "TARGET" + "b" * 500
        result = _extract_snippet(src, "target")
        assert "TARGET" in result
        assert len(result) <= 400  # context * 2


class TestCheckClaimsAgainstSources:
    """End-to-end claim verification."""

    def test_claim_fully_supported(self):
        claims = [
            "The Department of Justice approved the merger on July 10"
        ]
        sources = [
            "The Department of Justice approved the merger "
            "on July 10, 2026, according to official statements."
        ]
        results = check_claims_against_sources(claims, sources)
        assert len(results) == 1
        assert results[0]["supported"] is True
        assert results[0]["best_score"] > 0.6

    def test_claim_invented_not_present(self):
        claims = ["The CEO announced a $50 billion buyback program"]
        sources = [
            "Quarterly earnings were flat. Revenue grew 2% "
            "year-over-year. No buyback was discussed."
        ]
        results = check_claims_against_sources(claims, sources)
        assert len(results) == 1
        assert results[0]["supported"] is False

    def test_empty_claims_list(self):
        results = check_claims_against_sources(
            [], ["some source text"]
        )
        assert len(results) == 0

    def test_empty_sources_list(self):
        claims = ["Some specific claim about a topic"]
        results = check_claims_against_sources(claims, [])
        assert len(results) == 1
        assert results[0]["supported"] is False
        assert "(no grounding sources" in results[0]["best_snippet"]

    def test_multiple_claims_mixed_support(self):
        claims = [
            "The sky is blue",                # supported
            "The moon is made of cheese",     # unsupported
        ]
        sources = [
            "The sky appears blue due to "
            "Rayleigh scattering of sunlight."
        ]
        results = check_claims_against_sources(claims, sources)
        assert len(results) == 2
        assert results[0]["supported"] is True
        assert results[1]["supported"] is False

    def test_short_claim_skipped(self):
        claims = ["short"]
        sources = ["some text that is irrelevant to the claim"]
        results = check_claims_against_sources(claims, sources)
        assert len(results) == 1
        assert results[0]["supported"] is True
        assert "too short" in results[0]["best_snippet"]

    def test_empty_claim_string(self):
        claims = ["", "  "]
        results = check_claims_against_sources(
            claims, ["some source"]
        )
        assert len(results) == 2
        assert all(r["supported"] for r in results)


class TestFormatFactRows:
    """Regression test for _format_fact_rows in recall.py.

    Ensures the loop actually appends entries to the result list
    (the round-2 review caught a regression where entry was built
    but never appended, causing unconditional [] returns).
    """

    def test_nonempty_facts_produces_nonempty_result(self):
        from airunner_services.llm.tools.knowledge_tools.recall import (
            _format_fact_rows,
        )

        class _FakeFact:
            def __init__(self, text, created_at=None, source_type=None,
                         confidence=None):
                self.fact_text = text
                self.created_at = created_at
                self.source_type = source_type
                self.confidence = confidence

        from datetime import datetime

        now = datetime(2026, 7, 13, 12, 0, 0)
        facts = [
            _FakeFact("User works at Acme Corp", now,
                      source_type="user_stated", confidence=0.9),
            _FakeFact("User enjoys hiking", now,
                      source_type="web_search", confidence=0.7),
        ]
        result = _format_fact_rows(facts)
        assert len(result) == 2, (
            "expected 2 rows, got %d — regression: entries not appended"
            % len(result)
        )
        assert result[0]["line"] == "User works at Acme Corp"
        # user_stated is the default — should not appear in output
        assert "source_type" not in result[0]
        assert result[1]["line"] == "User enjoys hiking"
        assert result[1]["source_type"] == "web_search"
        assert result[1]["confidence"] == "0.70"

    def test_empty_facts_produces_empty_result(self):
        from airunner_services.llm.tools.knowledge_tools.recall import (
            _format_fact_rows,
        )

        assert _format_fact_rows([]) == []

    def test_fact_with_none_text_skipped(self):
        from airunner_services.llm.tools.knowledge_tools.recall import (
            _format_fact_rows,
        )

        class _FakeFact:
            fact_text = None
            created_at = None
            source_type = None
            confidence = None

        assert _format_fact_rows([_FakeFact]) == []
