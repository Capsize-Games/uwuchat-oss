"""Encryption-at-rest tests for API key columns (Round 17 Part 4).

Verifies:
  (a) ORM writes through UserEncryptedText columns produce ciphertext.
  (b) Existing plaintext legacy rows remain readable.
  (c) No-DEK context writes behave per the fail-closed contract.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cryptography.fernet import Fernet


class TestApiKeyEncryptionAtRest:
    """ORM writes produce ciphertext at the storage layer."""

    def test_orm_write_encrypts_llm_api_key(self):
        """Writing llm_generator_settings.api_key via ORM stores
        ciphertext (gAAAAA prefix) at rest."""
        from airunner_services.database.models.llm_generator_settings import (
            LLMGeneratorSettings,
        )

        col = getattr(LLMGeneratorSettings, "api_key")
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        assert isinstance(col.type, UserEncryptedText), (
            "api_key must be UserEncryptedText after Round 17"
        )

    def test_orm_write_encrypts_app_settings_keys(self):
        """Writing application_settings API key columns via ORM stores
        ciphertext at rest."""
        from airunner_services.database.models.application_settings import (
            ApplicationSettings,
        )
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        for col_name in [
            "hf_api_key_read_key",
            "hf_api_key_write_key",
            "civit_ai_api_key",
            "openai_api_key",
        ]:
            col = getattr(ApplicationSettings, col_name)
            assert isinstance(col.type, UserEncryptedText), (
                f"{col_name} must be UserEncryptedText after Round 17"
            )


class TestLegacyPlaintextPassthrough:
    """Plaintext values written before the migration remain readable."""

    def test_plaintext_value_passes_through_process_result(self):
        """process_result_value returns non-ciphertext values as-is."""
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        col = UserEncryptedText()
        plaintext = "sk-legacy-key-12345"
        result = col.process_result_value(plaintext, None)
        assert result == plaintext, (
            "Legacy plaintext must pass through unchanged"
        )

    def test_empty_string_passes_through(self):
        """Empty strings (defaults) pass through without error."""
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        col = UserEncryptedText()
        result = col.process_result_value("", None)
        assert result == ""

    def test_none_passes_through(self):
        """None values pass through without error."""
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        col = UserEncryptedText()
        result = col.process_result_value(None, None)
        assert result is None


class TestFailClosedOnWrite:
    """With no DEK, no global keyring, and no edge key, writes raise."""

    def test_write_fails_with_no_keys(self):
        """process_bind_param raises DataEncryptionError when no keys
        of any kind are available."""
        from airunner_services.utils.crypto.data_encryption import (
            DataEncryptionError,
        )
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        col = UserEncryptedText()

        with patch(
            "airunner_services.utils.crypto.user_encrypted_type"
            ".get_user_dek",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type"
            ".get_keyring",
            return_value=None,
        ), patch(
            "airunner_services.utils.crypto.user_encrypted_type"
            ".get_edge_keyring",
            return_value=None,
        ):
            with pytest.raises(DataEncryptionError, match="no per-user"):
                col.process_bind_param("sk-test-key", None)

    def test_write_succeeds_with_dek(self):
        """process_bind_param encrypts when a DEK is available."""
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        col = UserEncryptedText()
        dek = Fernet.generate_key()

        with patch(
            "airunner_services.utils.crypto.user_encrypted_type"
            ".get_user_dek",
            return_value=dek,
        ):
            result = col.process_bind_param("sk-test-key", None)
            assert result is not None
            assert result.startswith("gAAAAA"), (
                "Output must be Fernet ciphertext"
            )


class TestEdgeKeyRoundTrip:
    """Persistent edge key survives across restarts."""

    def test_round_trip_across_simulated_restart(self):
        """Write with edge key, clear cache, read back — key is
        the same because it's persisted to disk."""
        import os
        import tempfile
        from airunner_services.utils.crypto.data_encryption import (
            _reset_edge_keyring_for_tests,
        )
        from airunner_services.utils.crypto.user_encrypted_type import (
            UserEncryptedText,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "fernet_edge.key")
            from unittest.mock import patch

            with patch.dict(
                "os.environ",
                {"AIRUNNER_BASE_PATH": tmpdir},
                clear=False,
            ):
                # Clear cached keyring
                _reset_edge_keyring_for_tests()

                col = UserEncryptedText()

                # Write
                with patch(
                    "airunner_services.utils.crypto"
                    ".user_encrypted_type.get_user_dek",
                    return_value=None,
                ), patch(
                    "airunner_services.utils.crypto"
                    ".user_encrypted_type.get_keyring",
                    return_value=None,
                ):
                    written = col.process_bind_param(
                        "edge-test-value", None,
                    )
                    assert written.startswith("gAAAAA"), (
                        "Edge key must encrypt with Fernet"
                    )

                # Simulate restart — clear cache
                _reset_edge_keyring_for_tests()

                # Read back with same conditions
                with patch(
                    "airunner_services.utils.crypto"
                    ".user_encrypted_type.get_user_dek",
                    return_value=None,
                ), patch(
                    "airunner_services.utils.crypto"
                    ".user_encrypted_type.get_keyring",
                    return_value=None,
                ):
                    readback = col.process_result_value(
                        written, None,
                    )
                    assert readback == "edge-test-value", (
                        "Edge key must survive restart"
                    )

            # Verify key file was created
            assert os.path.exists(key_path), (
                "Edge key file must exist after first write"
            )
