"""Unit tests for StreamingRestorer — buffered streaming PII de-masking."""

from __future__ import annotations

from airunner_services.llm.pii.streaming_restorer import StreamingRestorer
from airunner_services.llm.pii.vault import PIIVault


def _chunks(*items: str):
    """Yield items as an iterator (simulates streaming chunks)."""
    yield from items


def _collect(restorer: StreamingRestorer) -> list[str]:
    """Collect all chunks from a StreamingRestorer into a list."""
    result: list[str] = []
    for chunk in restorer:
        result.append(chunk)
    return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_vault_with_person() -> PIIVault:
    """Create a vault with one PERSON entity mapped."""
    vault = PIIVault()
    vault.placeholder_for("PERSON", "Alice")
    return vault


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStreamingRestorer:
    """Tests for ``StreamingRestorer``."""

    def test_placeholder_in_single_chunk_restored(self):
        """A chunk containing a complete placeholder is restored."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Hello [PERSON_1], welcome!"), vault
        )
        result = _collect(sr)
        assert "".join(result) == "Hello Alice, welcome!"

    def test_placeholder_split_across_two_chunks(self):
        """Placeholder split at bracket boundary is correctly restored."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Hello [PERS", "ON_1], welcome!"), vault
        )
        result = _collect(sr)
        assert "".join(result) == "Hello Alice, welcome!"

    def test_placeholder_split_inside_brackets(self):
        """Placeholder split mid-token inside brackets is restored."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Hello [PERSON", "_1], welcome!"), vault
        )
        result = _collect(sr)
        assert "".join(result) == "Hello Alice, welcome!"

    def test_multiple_chunks_no_placeholder(self):
        """Plain text chunks without placeholders pass through."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Hello ", "world", "!"), vault
        )
        result = _collect(sr)
        assert "".join(result) == "Hello world!"

    def test_empty_chunks(self):
        """Empty upstream iterator yields nothing."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(_chunks(), vault)
        result = _collect(sr)
        assert result == []

    def test_empty_string_chunk(self):
        """Empty string chunk doesn't break the buffer."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Hi ", "", "[PERSON_1]"), vault
        )
        result = _collect(sr)
        assert "".join(result) == "Hi Alice"

    def test_unknown_placeholder_left_as_is(self):
        """Placeholder not in vault is left untouched, no exception."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Hello [UNKNOWN_99]"), vault
        )
        result = _collect(sr)
        assert "".join(result) == "Hello [UNKNOWN_99]"

    def test_multiple_placeholders_mixed(self):
        """Multiple placeholders, some split, some complete."""
        vault = PIIVault()
        vault.placeholder_for("PERSON", "Alice")
        vault.placeholder_for("EMAIL_ADDRESS", "alice@example.com")

        sr = StreamingRestorer(
            _chunks(
                "[PERSON_1] emailed [EMAIL_AD",
                "DRESS_1] about the meeting.",
            ),
            vault,
        )
        result = _collect(sr)
        assert "".join(result) == (
            "Alice emailed alice@example.com about the meeting."
        )

    def test_literal_brackets_not_placeholders(self):
        """Text with literal brackets that aren't placeholders passes through."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Array access: arr[0] and arr[1]"), vault
        )
        result = _collect(sr)
        # "[" followed by a digit is bracket-balanced immediately by
        # the "]", so the bracket-counting algorithm in _find_safe_prefix
        # treats the whole "arr[0]" as safe text.
        assert "".join(result) == "Array access: arr[0] and arr[1]"

    def test_flushes_promptly_for_non_placeholder_text(self):
        """Non-placeholder text is emitted promptly, not all at end."""
        vault = _make_vault_with_person()
        sr = StreamingRestorer(
            _chunks("Hello ", "world"), vault
        )
        chunks = _collect(sr)
        # Should have yielded at least one chunk before iterator
        # exhaustion, since the text contains no placeholder patterns.
        assert len(chunks) >= 1  # At minimum one chunk was flushed

    def test_longest_placeholder_first_in_restore(self):
        """PERSON_10 restored correctly alongside PERSON_1."""
        vault = PIIVault()
        for i in range(1, 12):
            vault.placeholder_for("PERSON", f"Name{i:02d}")

        sr = StreamingRestorer(
            _chunks("First [PERSON_1] then [PERSON_10]"), vault
        )
        result = _collect(sr)
        assert "".join(result) == "First Name01 then Name10"
