"""Unit tests for the PII masking / vault / restore pipeline.

Tests the pii package in isolation — no network, no LLM, no Presidio
(analyzer responses are patched so we test our own logic, not spaCy).
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from airunner_services.llm.pii.masker import mask_messages, mask_text
from airunner_services.llm.pii.restorer import restore_text
from airunner_services.llm.pii.vault import PIIVault


# ---------------------------------------------------------------------------
# Synthetic analyzer results builder
# ---------------------------------------------------------------------------


def _analyze_results(entities):
    """Build fake Presidio results from (entity_type, start, end, score)."""
    return [
        {
            "entity_type": et,
            "start": s,
            "end": e,
            "score": sc,
        }
        for et, s, e, sc in entities
    ]


# ---------------------------------------------------------------------------
# mask_text
# ---------------------------------------------------------------------------


class TestMaskText:
    """Tests for ``mask_text``."""

    def test_detects_and_replaces_all_entity_types(self):
        """Email, phone, SSN, credit card, person name."""
        vault = PIIVault()
        text = (
            "Contact jane@example.com or call 555-123-4567. "
            "SSN: 123-45-6789. Card: 4111-1111-1111-1111. "
            "Ask for Alice."
        )
        entities = _analyze_results(
            [
                ("EMAIL_ADDRESS", 8, 24, 0.85),
                ("PHONE_NUMBER", 34, 46, 0.90),
                ("US_SSN", 53, 64, 0.95),
                ("CREDIT_CARD", 73, 92, 0.98),
                ("PERSON", 102, 107, 0.85),
            ],
        )
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = entities
            result = mask_text(text, vault)

        assert "jane@example.com" not in result
        assert "555-123-4567" not in result
        assert "123-45-6789" not in result
        assert "4111-1111-1111-1111" not in result
        assert "Alice" not in result
        assert "[EMAIL_ADDRESS_1]" in result
        assert "[PHONE_NUMBER_1]" in result
        assert "[US_SSN_1]" in result
        assert "[CREDIT_CARD_1]" in result
        assert "[PERSON_1]" in result

    def test_same_name_reuses_placeholder(self):
        """Two occurrences of the same name -> same placeholder."""
        vault = PIIVault()
        text = "Alice told Bob that Alice would call Bob."
        entities = _analyze_results(
            [
                ("PERSON", 0, 5, 0.85),
                ("PERSON", 11, 14, 0.82),
                ("PERSON", 20, 25, 0.85),
                ("PERSON", 37, 40, 0.82),
            ],
        )
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = entities
            result = mask_text(text, vault)

        assert result.count("[PERSON_1]") == 2  # Alice twice
        assert result.count("[PERSON_2]") == 2  # Bob twice

    def test_different_names_different_placeholders(self):
        """Two different names get different, incrementing placeholders."""
        vault = PIIVault()
        text = "Alice met Charlie."
        entities = _analyze_results(
            [
                ("PERSON", 0, 5, 0.85),
                ("PERSON", 10, 17, 0.85),
            ],
        )
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = entities
            result = mask_text(text, vault)

        assert "[PERSON_1]" in result
        assert "[PERSON_2]" in result

    def test_no_pii_returns_input_unchanged(self):
        """Text with no PII entities returns unchanged."""
        vault = PIIVault()
        text = "Hello, how are you today?"
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = []
            result = mask_text(text, vault)

        assert result == text

    def test_empty_string_unchanged(self):
        """Empty string returns unchanged."""
        vault = PIIVault()
        assert mask_text("", vault) == ""

    def test_whitespace_only_unchanged(self):
        """Whitespace-only input returns unchanged, no crash."""
        vault = PIIVault()
        assert mask_text("   \n\t  ", vault) == "   \n\t  "


# ---------------------------------------------------------------------------
# mask_messages
# ---------------------------------------------------------------------------


class TestMaskMessages:
    """Tests for ``mask_messages``."""

    def test_preserves_message_order_and_role(self):
        """``mask_messages`` preserves order, role, and extra keys."""
        vault = PIIVault()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "My name is Alice.", "id": 1},
            {"role": "assistant", "content": "Hi Alice!"},
        ]

        def _mock_analyze(text, **kwargs):
            if "Alice" in text:
                return _analyze_results(
                    [
                        ("PERSON", text.index("Alice"),
                         text.index("Alice") + 5, 0.85),
                    ],
                )
            return []

        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.side_effect = _mock_analyze
            result = mask_messages(messages, vault)

        assert len(result) == 3
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful."
        assert result[1]["role"] == "user"
        assert result[1]["id"] == 1
        assert "Alice" not in result[1]["content"]
        assert "[PERSON_1]" in result[1]["content"]
        assert result[2]["role"] == "assistant"
        assert "Alice" not in result[2]["content"]

    def test_does_not_mutate_input(self):
        """Input list is not mutated — caller keeps the original."""
        vault = PIIVault()
        messages = [{"role": "user", "content": "Call Alice"}]

        entities = _analyze_results([("PERSON", 5, 10, 0.85)])
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = entities
            _ = mask_messages(messages, vault)

        assert messages[0]["content"] == "Call Alice"


# ---------------------------------------------------------------------------
# restore_text
# ---------------------------------------------------------------------------


class TestRestoreText:
    """Tests for ``restore_text``."""

    def test_round_trip_all_entity_types(self):
        """Round-trip mask -> restore for all 7 entity types."""
        vault = PIIVault()
        scenarios = [
            (
                "Email me at alice@example.com",
                [("EMAIL_ADDRESS", 12, 28, 0.90)],
            ),
            (
                "Call 555-123-4567 for help",
                [("PHONE_NUMBER", 5, 17, 0.90)],
            ),
            (
                "SSN 123-45-6789 is mine",
                [("US_SSN", 4, 15, 0.95)],
            ),
            (
                "Card 4111-1111-1111-1111 expired",
                [("CREDIT_CARD", 5, 24, 0.98)],
            ),
            (
                "IBAN GB29NWBK60161331926819 is valid",
                [("IBAN_CODE", 5, 27, 0.90)],
            ),
            (
                "Alice lives in Denver",
                [
                    ("PERSON", 0, 5, 0.85),
                    ("LOCATION", 15, 21, 0.80),
                ],
            ),
            (
                "Meet at 123 Main St, Springfield",
                [("LOCATION", 8, 31, 0.75)],
            ),
        ]
        for text, entities in scenarios:
            with patch(
                "airunner_services.llm.pii.masker.get_analyzer"
            ) as mock_get:
                mock_get.return_value.analyze.return_value = (
                    _analyze_results(entities)
                )
                masked = mask_text(text, vault)
            restored = restore_text(masked, vault)
            assert restored == text, f"Round-trip failed: {text!r}"

    def test_round_trip_multiple_same_type(self):
        """Round-trip with multiple entities of the same type."""
        vault = PIIVault()
        text = (
            "Alice emailed Bob about Charlie. "
            "Reach Alice at alice@example.com or Bob at bob@test.org."
        )
        entities = _analyze_results(
            [
                ("PERSON", 0, 5, 0.85),
                ("PERSON", 13, 16, 0.85),
                ("PERSON", 23, 30, 0.85),
                ("PERSON", 39, 44, 0.85),
                ("EMAIL_ADDRESS", 49, 65, 0.90),
                ("PERSON", 70, 73, 0.85),
                ("EMAIL_ADDRESS", 77, 89, 0.90),
            ],
        )
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = entities
            masked = mask_text(text, vault)
        restored = restore_text(masked, vault)
        assert restored == text

    def test_unknown_placeholder_left_untouched(self):
        """Unrecognized placeholder stays as-is, no exception."""
        vault = PIIVault()
        text = "Hello [PERSON_999], how are you?"
        restored = restore_text(text, vault)
        assert restored == text

    def test_longest_placeholder_first_ordering(self):
        """PERSON_10 is not corrupted by partial match on PERSON_1."""
        vault = PIIVault()
        for i in range(1, 12):
            vault.placeholder_for("PERSON", f"Name{i:02d}")

        text = "[PERSON_1] and [PERSON_10] are different"
        restored = restore_text(text, vault)
        assert restored == "Name01 and Name10 are different"
        assert "Name01" in restored
        assert "Name10" in restored


# ---------------------------------------------------------------------------
# Vault
# ---------------------------------------------------------------------------


class TestPIIVault:
    """Tests for ``PIIVault`` standalone."""

    def test_consistent_placeholder_for_same_value(self):
        """Same (entity_type, original) returns the same placeholder."""
        vault = PIIVault()
        ph1 = vault.placeholder_for("PERSON", "Alice")
        ph2 = vault.placeholder_for("PERSON", "Alice")
        assert ph1 == ph2

    def test_different_values_increment(self):
        """Different values get incrementing placeholders."""
        vault = PIIVault()
        ph1 = vault.placeholder_for("PERSON", "Alice")
        ph2 = vault.placeholder_for("PERSON", "Bob")
        assert ph1 != ph2
        assert ph1 == "[PERSON_1]"
        assert ph2 == "[PERSON_2]"

    def test_different_types_separate_counters(self):
        """PERSON and EMAIL counters are independent."""
        vault = PIIVault()
        ph1 = vault.placeholder_for("PERSON", "Alice")
        ph2 = vault.placeholder_for("EMAIL_ADDRESS", "a@b.com")
        assert ph1 == "[PERSON_1]"
        assert ph2 == "[EMAIL_ADDRESS_1]"

    def test_original_for_returns_none_for_unknown(self):
        """``original_for`` returns None for unknowns."""
        vault = PIIVault()
        assert vault.original_for("[PERSON_999]") is None

    def test_all_placeholders_sorted_longest_first(self):
        """Sort order prevents partial-match bugs during restore."""
        vault = PIIVault()
        vault.placeholder_for("PERSON", "A")
        vault.placeholder_for("PERSON", "B")
        vault.placeholder_for("PHONE", "123")
        vault.placeholder_for("EMAIL_ADDRESS", "a@b.com")
        for i in range(9):
            vault.placeholder_for("PERSON", f"Name{i:02d}")

        sorted_ph = vault.all_placeholders_sorted_longest_first()
        assert sorted_ph[0] == "[EMAIL_ADDRESS_1]"
        idx_11 = sorted_ph.index("[PERSON_11]")
        idx_1 = sorted_ph.index("[PERSON_1]")
        assert idx_11 < idx_1, (
            f"[PERSON_11] at {idx_11} should precede "
            f"[PERSON_1] at {idx_1}"
        )


# ---------------------------------------------------------------------------
# Logging hygiene
# ---------------------------------------------------------------------------


class TestLoggingHygiene:
    """Assert no PII values or placeholders leak into log records."""

    def test_no_pii_in_logs(self, caplog):
        """Mask/restore operations must not log raw PII or placeholders."""
        caplog.set_level(
            logging.DEBUG, logger="airunner_services.llm.pii"
        )
        vault = PIIVault()

        text = "Alice's email is alice@example.com"
        entities = _analyze_results(
            [
                ("PERSON", 0, 5, 0.85),
                ("EMAIL_ADDRESS", 16, 32, 0.90),
            ],
        )
        with patch(
            "airunner_services.llm.pii.masker.get_analyzer"
        ) as mock_get:
            mock_get.return_value.analyze.return_value = entities
            masked = mask_text(text, vault)
            _ = restore_text(masked, vault)

        log_text = caplog.text
        assert "Alice" not in log_text
        assert "alice@example.com" not in log_text
        assert "[PERSON_1]" not in log_text
        assert "[EMAIL_ADDRESS_1]" not in log_text
