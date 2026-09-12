"""Unit tests for ``search_result_capping``."""

from extensions.fastsearch.server.search_result_capping import (
    _format_dropped_note,
    _collect_blocks,
    cap_query_blocks,
)


class TestFormatDroppedNote:
    """Tests for ``_format_dropped_note``."""

    def test_single_query_named(self):
        note = _format_dropped_note(["my query"])
        assert "1 query dropped" in note
        assert "'my query'" in note
        assert "Re-query individually" in note

    def test_multiple_queries_named(self):
        note = _format_dropped_note(["q1", "q2", "q3"])
        assert "3 queries dropped" in note
        assert "'q1'" in note
        assert "'q2'" in note
        assert "'q3'" in note

    def test_caps_at_five_names(self):
        names = [f"query-{i}" for i in range(10)]
        note = _format_dropped_note(names)
        assert "10 queries" in note
        assert "and 5 more" in note
        for i in range(5):
            assert f"query-{i}" in note
        assert "query-5" not in note

    def test_truncates_long_names(self):
        long_name = "x" * 200
        note = _format_dropped_note([long_name])
        assert long_name[:60] in note
        assert long_name[61:] not in note


class TestCollectBlocks:
    """Tests for ``_collect_blocks``."""

    def test_all_fit(self):
        parts = ["aaa", "bbb", "ccc"]
        results = [{"query": "a"}, {"query": "b"}, {"query": "c"}]
        kept, kept_idx, dropped = _collect_blocks(
            parts, results, 100
        )
        assert kept == parts
        assert kept_idx == [0, 1, 2]
        assert dropped == []

    def test_some_dropped(self):
        parts = ["aaa", "bbb", "ccc"]
        results = [{"query": "a"}, {"query": "b"}, {"query": "c"}]
        kept, kept_idx, dropped = _collect_blocks(
            parts, results, 10
        )
        assert kept == ["aaa", "bbb"]
        assert kept_idx == [0, 1]
        assert dropped == ["c"]

    def test_non_contiguous_dropped(self):
        """Early large block dropped while later small blocks kept."""
        parts = ["x" * 9000, "short2", "short3"]
        results = [
            {"query": "big"}, {"query": "q2"}, {"query": "q3"}
        ]
        kept, kept_idx, dropped = _collect_blocks(
            parts, results, 8000
        )
        assert kept == ["short2", "short3"]
        assert kept_idx == [1, 2]
        assert "big" in dropped
        assert "q2" not in dropped
        assert "q3" not in dropped

    def test_dropped_uses_result_query_name(self):
        parts = ["aaa", "bbb"]
        results = [{"query": "first"}, {"query": "second"}]
        kept, kept_idx, dropped = _collect_blocks(
            parts, results, 6
        )
        assert kept == ["aaa"]
        assert kept_idx == [0]
        assert dropped == ["second"]

    def test_dropped_falls_back_to_index(self):
        parts = ["aaa", "bbb"]
        results = [{}]  # missing "query" key
        kept, kept_idx, dropped = _collect_blocks(
            parts, results, 6
        )
        assert dropped == ["query 2"]


class TestCapQueryBlocks:
    """Tests for ``cap_query_blocks``."""

    def test_single_query_always_kept(self):
        huge = "x" * 20_000
        results = [{"query": "only"}]
        parts, kept_results = cap_query_blocks([huge], results, 100)
        assert parts == [huge]
        assert kept_results == results

    def test_empty_parts(self):
        parts, results = cap_query_blocks([], [], 100)
        assert parts == []
        assert results == []

    def test_under_cap_all_kept(self):
        parts = ["short1", "short2"]
        results = [{"query": "q1"}, {"query": "q2"}]
        parts_out, results_out = cap_query_blocks(
            parts, results, 500
        )
        assert parts_out == parts
        assert results_out == results

    def test_over_cap_trailing_dropped(self):
        parts = ["short", "x" * 5000, "y" * 5000]
        results = [
            {"query": "q1"},
            {"query": "q2"},
            {"query": "q3"},
        ]
        parts_out, results_out = cap_query_blocks(
            parts, results, 100
        )
        # Only the first short block fits.
        assert len(parts_out) == 2  # kept + truncation note
        assert parts_out[0] == "short"
        assert "truncated" in parts_out[1].lower()
        assert "q2" in parts_out[1]
        assert "q3" in parts_out[1]
        assert len(results_out) == 1  # only q1's result kept

    def test_dropped_note_names_queries(self):
        parts = ["a", "b" * 5000, "c" * 5000]
        results = [
            {"query": "alpha"},
            {"query": "beta"},
            {"query": "gamma"},
        ]
        parts_out, _ = cap_query_blocks(parts, results, 100)
        note = parts_out[-1]
        assert "'beta'" in note
        assert "'gamma'" in note
        assert "'alpha'" not in note

    def test_non_contiguous_results_match_kept_text(self):
        """Results list matches kept text, not a positional slice."""
        parts = ["x" * 9000, "short2", "short3"]
        results = [
            {"query": "big"},
            {"query": "q2"},
            {"query": "q3"},
        ]
        parts_out, results_out = cap_query_blocks(
            parts, results, 8000
        )
        # Text correctly keeps only the two small blocks.
        assert len(parts_out) == 3  # short2, short3, truncation note
        assert "short2" in parts_out[0]
        assert "short3" in parts_out[1]
        # Results must contain exactly q2 and q3, NOT big + q2.
        assert len(results_out) == 2
        assert results_out[0]["query"] == "q2"
        assert results_out[1]["query"] == "q3"

    def test_uses_default_max_chars(self):
        """Default cap from env var (8000) lets normal batches through."""
        parts = ["normal sized query result"] * 3
        results = [
            {"query": "a"}, {"query": "b"}, {"query": "c"}
        ]
        parts_out, results_out = cap_query_blocks(parts, results)
        assert parts_out == parts
        assert results_out == results
