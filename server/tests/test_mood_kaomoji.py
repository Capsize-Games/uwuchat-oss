"""Tests for _kaomoji_for_mood — verifies the sentinel-based
kaomoji auto-selection used by intra_session_mood."""

from __future__ import annotations

from airunner_services.llm.tools.mood_tools import (
    _DEFAULT_KAOMOJI,
    _decode_literal_escapes,
    _kaomoji_for_mood,
)


class TestKaomojiForMood:
    """Verify kaomoji selection semantics for auto-mood codepaths."""

    def test_default_sentinel_triggers_map_lookup(self) -> None:
        """When the caller passes _DEFAULT_KAOMOJI (i.e. the LLM response
        had no "kaomoji" key), the function MUST consult _KAOMOJI_MAP
        and return a mood-appropriate face, not the sentinel itself."""
        result = _kaomoji_for_mood("happy", _DEFAULT_KAOMOJI)
        # Must NOT return the sentinel — the whole point is that
        # _DEFAULT_KAOMOJI is a signal, not a display value.
        assert result != _DEFAULT_KAOMOJI, (
            "_kaomoji_for_mood returned the sentinel instead of "
            "looking up from _KAOMOJI_MAP"
        )
        # Must be a non-empty string.
        assert isinstance(result, str) and len(result) > 0

    def test_different_moods_produce_different_faces(self) -> None:
        """A sad mood and a happy mood must resolve to different kaomoji
        when both fall through to the map."""
        happy = _kaomoji_for_mood("happy", _DEFAULT_KAOMOJI)
        sad = _kaomoji_for_mood("sad", _DEFAULT_KAOMOJI)
        assert happy != sad, (
            f"happy={happy!r} and sad={sad!r} should differ"
        )

    def test_explicit_kaomoji_is_respected(self) -> None:
        """When the LLM genuinely provides a non-default kaomoji, it
        must be returned verbatim without map lookup."""
        explicit = "(╯°□°)╯︵ ┻━┻"
        result = _kaomoji_for_mood("angry", explicit)
        assert result == explicit, (
            "Explicit kaomoji should bypass _KAOMOJI_MAP"
        )

    def test_default_sentinel_with_no_keyword_match(self) -> None:
        """When mood text doesn't match any keyword and the sentinel
        is passed, fall back to a calm variant — not the sentinel."""
        result = _kaomoji_for_mood(
            "some unheard-of emotion", _DEFAULT_KAOMOJI
        )
        assert result != _DEFAULT_KAOMOJI, (
            "Fallback should produce a calm kaomoji, not the sentinel"
        )
        assert isinstance(result, str) and len(result) > 0

    def test_same_mood_produces_same_face_deterministically(self) -> None:
        """The same mood text must produce the same kaomoji every call."""
        a = _kaomoji_for_mood("curious", _DEFAULT_KAOMOJI)
        b = _kaomoji_for_mood("curious", _DEFAULT_KAOMOJI)
        assert a == b, "Same mood must produce deterministic kaomoji"

    def test_reproduces_old_bug_scenario(self) -> None:
        """Reproduce the exact scenario from the plan: the LLM prompt
        never asks for "kaomoji", so result.get("kaomoji", ...) always
        falls through to the default.  When the default was the plain
        literal "(｡◕ᴗ◕｡)" it bypassed the map.  With _DEFAULT_KAOMOJI
        ("ʕ•ᴥ•ʔ") the map IS consulted.

        This test proves the fix works by simulating exactly what
        _compute_mood_payload does: the LLM returns {"mood": "annoyed",
        "emoji": "😤"} with NO "kaomoji" key, so the caller passes
        _DEFAULT_KAOMOJI as fallback.
        """
        # Simulate parsed LLM response — no kaomoji key at all.
        llm_result: dict = {"mood": "annoyed", "emoji": "😤"}
        result = _kaomoji_for_mood(
            llm_result.get("mood", "neutral"),
            llm_result.get("kaomoji", _DEFAULT_KAOMOJI),
        )
        # Before the fix this would have returned "(｡◕ᴗ◕｡)" unchanged.
        # After the fix it must come from _KAOMOJI_MAP["annoyed"] or a
        # related keyword match — definitely not the sentinel.
        assert result != _DEFAULT_KAOMOJI, (
            "With sentinel as fallback, kaomoji must come from "
            f"_KAOMOJI_MAP, got {result!r}"
        )
        assert result != "(｡◕ᴗ◕｡)", (
            "Stale literal should never appear as map-bypass result"
        )

    def test_escaped_kaomoji_repaired(self) -> None:
        """Literal \\uXXXX escape text in explicit kaomoji is decoded
        to the real Unicode character before returning."""
        escaped = "(" + "\\u25ce" + "_" + "\\u25ce" + ";)"
        result = _kaomoji_for_mood("confused", escaped)
        expected = "(◎_◎;)"
        assert result == expected, (
            f"Escaped kaomoji should be repaired, got {result!r}"
        )

    def test_normal_kaomoji_unchanged(self) -> None:
        """A normal real-Unicode explicit kaomoji is returned unchanged."""
        normal = "(◕‿◕)"
        result = _kaomoji_for_mood("happy", normal)
        assert result == normal, (
            f"Normal kaomoji should pass through, got {result!r}"
        )

    def test_empty_explicit_still_falls_through_to_map(self) -> None:
        """Empty explicit kaomoji still falls through to keyword map."""
        result = _kaomoji_for_mood("happy", "")
        assert result != _DEFAULT_KAOMOJI, (
            "Empty explicit should fall through to map, "
            f"got {result!r}"
        )
        assert result != "", "Should not return empty string"


def test_decode_literal_escapes_replaces_pattern() -> None:
    """_decode_literal_escapes replaces literal escape sequences."""
    input_str = "(" + "\\u25ce" + "_" + "\\u25ce" + ";)"
    result = _decode_literal_escapes(input_str)
    assert result == "(◎_◎;)"


def test_decode_literal_escapes_unchanged_without_pattern() -> None:
    """_decode_literal_escapes returns text unchanged when no escapes."""
    result = _decode_literal_escapes("(◕‿◕)")
    assert result == "(◕‿◕)"
