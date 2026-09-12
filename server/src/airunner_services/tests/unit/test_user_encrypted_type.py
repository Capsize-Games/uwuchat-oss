"""Unit tests for UserEncryptedText round-trip correctness.

Tests the asymmetric read/write fallback bug where process_result_value
returned raw marker-prefixed plaintext instead of calling _deserialize()
on it, causing non-string values to come back as strings.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from airunner_services.utils.crypto.user_encrypted_type import (
    UserEncryptedText,
    _deserialize,
    _serialize,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_type() -> UserEncryptedText:
    """Return a fresh UserEncryptedText instance."""
    return UserEncryptedText()


def _serialized_list(value: list) -> str:
    """Return the plaintext marker+JSON string for *value*."""
    return _serialize(value).decode("utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProcessResultValueRoundTrip:
    """Verify process_result_value correctly round-trips values."""

    def test_no_key_list_raises(self):
        """A list written with no keys raises DataEncryptionError
        (fail-closed, Round 16 Part 2)."""
        from airunner_services.utils.crypto.data_encryption import (
            DataEncryptionError,
        )

        original = [{"role": "assistant", "content": "Hello!"}]
        col = _make_type()

        with patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_user_dek",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_keyring",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_edge_keyring",
            return_value=None,
        ):
            with pytest.raises(DataEncryptionError, match="no per-user DEK"):
                col.process_bind_param(original, None)

    def test_no_key_dict_raises(self):
        """A dict written with no keys raises DataEncryptionError
        (fail-closed, Round 16 Part 2)."""
        from airunner_services.utils.crypto.data_encryption import (
            DataEncryptionError,
        )

        original = {"status": "ok", "count": 5}
        col = _make_type()

        with patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_user_dek",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_keyring",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_edge_keyring",
            return_value=None,
        ):
            with pytest.raises(DataEncryptionError, match="no per-user DEK"):
                col.process_bind_param(original, None)

    def test_plain_string_raises_no_keys(self):
        """A plain string written without keys raises DataEncryptionError
        (fail-closed, Round 16 Part 2)."""
        from airunner_services.utils.crypto.data_encryption import (
            DataEncryptionError,
        )

        original = "hello world"
        col = _make_type()

        with patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_user_dek",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_keyring",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_edge_keyring",
            return_value=None,
        ):
            with pytest.raises(DataEncryptionError, match="no per-user DEK"):
                col.process_bind_param(original, None)

    def test_decrypt_fallback_deserializes_marker_plaintext(self):
        """When both DEK and keyring decrypt fail, marker plaintext is
        still correctly deserialized."""
        original = [{"role": "assistant", "content": "Hi"}]
        # Simulate marker-prefixed plaintext that was never encrypted
        # (same form as what the "no key" write path produces).
        marker_text = _serialized_list(original)

        col = _make_type()

        with patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_user_dek",
            return_value=b"not-a-valid-dek-value",
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type.get_keyring",
            return_value=None,
        ):
            # process_result_value will try the DEK, fail, then fall
            # through to the global keyring branch.  With keyring=None,
            # it takes the "No key available at all" return at line 179.
            read_back = col.process_result_value(marker_text, None)
            assert read_back == original, (
                "Even after failed decrypt attempts, marker-prefixed "
                "plaintext must be deserialized back to the original list"
            )


class TestDeserializeSafety:
    """Confirm _deserialize is safe to call on any plaintext value."""

    def test_marker_prefixed_json_returns_parsed(self):
        """Marker-prefixed JSON is parsed to the original object."""
        original = [{"key": "value"}]
        marker_text = _serialized_list(original)
        result = _deserialize(marker_text)
        assert result == original

    def test_plain_string_passes_through(self):
        """A plain string without the marker is returned as-is."""
        assert _deserialize("just a string") == "just a string"

    def test_json_looking_string_passes_through(self):
        """A string that looks like JSON but lacks the marker is not
        parsed — the caller must have explicitly serialized it."""
        json_str = '{"key": "value"}'
        result = _deserialize(json_str)
        assert result == json_str, (
            "Without the _JSON_MARKER prefix, strings that look like "
            "JSON must NOT be parsed"
        )
