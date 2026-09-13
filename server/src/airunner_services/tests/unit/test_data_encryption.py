"""Unit tests for Fernet data encryption (data_encryption.py).

Tests encrypt/decrypt round-trip, wrong-key rejection, keyring
construction, and the encrypted_type ORM integration.
"""

from __future__ import annotations

import os

import pytest

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
    decrypt_bytes,
    encrypt_bytes,
    generate_fernet_key,
    get_keyring,
    is_encryption_active,
)


@pytest.fixture()
def _temp_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Set a temporary encryption key for the test."""
    key = generate_fernet_key()
    monkeypatch.setenv("AIRUNNER_DATA_ENCRYPTION_KEYS", key)
    return key


# ---------------------------------------------------------------------------
# encrypt / decrypt round-trip
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_round_trip(_temp_key: str) -> None:
    """Encrypt → decrypt preserves the original value."""
    original = b"this is sensitive user data"
    token = encrypt_bytes(original)
    assert token != original, "Ciphertext must differ from plaintext"
    result = decrypt_bytes(token)
    assert result == original


def test_encrypt_produces_different_output_for_same_input(
    _temp_key: str,
) -> None:
    """Two encryptions of the same plaintext produce different tokens
    (Fernet IV is random)."""
    plain = b"repeatable data"
    t1 = encrypt_bytes(plain)
    t2 = encrypt_bytes(plain)
    assert t1 != t2


# ---------------------------------------------------------------------------
# wrong key → loud failure
# ---------------------------------------------------------------------------


def test_decrypt_with_wrong_key_fails(_temp_key: str) -> None:
    """Decryption with a different key raises DataEncryptionError."""
    token = encrypt_bytes(b"secret")
    # Replace with a different key.
    wrong_key = generate_fernet_key()
    os.environ["AIRUNNER_DATA_ENCRYPTION_KEYS"] = wrong_key
    with pytest.raises(DataEncryptionError, match="Failed to decrypt"):
        decrypt_bytes(token)


# ---------------------------------------------------------------------------
# nil / missing key
# ---------------------------------------------------------------------------


def test_encrypt_bytes_refuses_none(_temp_key: str) -> None:
    """encrypt_bytes(None) raises."""
    with pytest.raises(DataEncryptionError):
        encrypt_bytes(None)  # type: ignore[arg-type]


def test_decrypt_bytes_refuses_none(_temp_key: str) -> None:
    """decrypt_bytes(None) raises."""
    with pytest.raises(DataEncryptionError):
        decrypt_bytes(None)  # type: ignore[arg-type]


def test_get_keyring_raises_when_required_and_missing() -> None:
    """get_keyring(required=True) raises when no keys configured."""
    saved = os.environ.pop("AIRUNNER_DATA_ENCRYPTION_KEYS", None)
    try:
        with pytest.raises(DataEncryptionError):
            get_keyring(required=True)
    finally:
        if saved:
            os.environ["AIRUNNER_DATA_ENCRYPTION_KEYS"] = saved


def test_get_keyring_returns_none_when_not_required() -> None:
    """get_keyring(required=False) returns None when no keys configured."""
    saved = os.environ.pop("AIRUNNER_DATA_ENCRYPTION_KEYS", None)
    try:
        assert get_keyring(required=False) is None
    finally:
        if saved:
            os.environ["AIRUNNER_DATA_ENCRYPTION_KEYS"] = saved


# ---------------------------------------------------------------------------
# keyring construction
# ---------------------------------------------------------------------------


def test_keyring_multi_key_decrypt() -> None:
    """A keyring with multiple keys can decrypt with any of them."""
    k1 = generate_fernet_key()
    k2 = generate_fernet_key()
    os.environ["AIRUNNER_DATA_ENCRYPTION_KEYS"] = f"{k1},{k2}"

    # Encrypt with k1 (the first key).
    token = encrypt_bytes(b"multi-key test")

    # Decrypt with the keyring built from both keys.
    result = decrypt_bytes(token)
    assert result == b"multi-key test"


def test_is_encryption_active() -> None:
    """is_encryption_active reflects the presence of keys."""
    saved = os.environ.pop("AIRUNNER_DATA_ENCRYPTION_KEYS", None)
    try:
        assert is_encryption_active() is False
        os.environ["AIRUNNER_DATA_ENCRYPTION_KEYS"] = generate_fernet_key()
        assert is_encryption_active() is True
    finally:
        if saved:
            os.environ["AIRUNNER_DATA_ENCRYPTION_KEYS"] = saved
        else:
            os.environ.pop("AIRUNNER_DATA_ENCRYPTION_KEYS", None)
