"""Unit tests for user-controlled key envelope (user_envelope.py).

Tests derive_kek, generate_dek, wrap_dek/unwrap_dek round-trip,
wrong-KEK failure, and salt encoding/decoding.
"""

from __future__ import annotations

import pytest

from airunner_services.utils.crypto.user_envelope import (
    EnvelopeError,
    decode_salt,
    derive_kek,
    encode_salt,
    generate_dek,
    generate_kdf_salt,
    unwrap_dek,
    wrap_dek,
)


# ---------------------------------------------------------------------------
# Salt encode / decode round-trip
# ---------------------------------------------------------------------------


def test_salt_encode_decode_round_trip() -> None:
    """encode_salt → decode_salt preserves the original salt."""
    original = generate_kdf_salt()
    encoded = encode_salt(original)
    assert isinstance(encoded, str)
    assert len(encoded) > 0
    decoded = decode_salt(encoded)
    assert decoded == original


def test_generate_kdf_salt_produces_unique_values() -> None:
    """Each call to generate_kdf_salt produces a different salt."""
    s1 = generate_kdf_salt()
    s2 = generate_kdf_salt()
    assert s1 != s2


# ---------------------------------------------------------------------------
# wrap / unwrap round-trip
# ---------------------------------------------------------------------------


def test_wrap_unwrap_round_trip() -> None:
    """wrap_dek → unwrap_dek returns the original DEK."""
    password = "test-password-42"
    salt = generate_kdf_salt()
    kek = derive_kek(password, salt)
    dek = generate_dek()

    wrapped = wrap_dek(dek, kek)
    assert isinstance(wrapped, str)
    assert len(wrapped) > 0
    assert wrapped != dek  # ciphertext must differ from plaintext

    unwrapped = unwrap_dek(wrapped, kek)
    assert unwrapped == dek


# ---------------------------------------------------------------------------
# wrong password / wrong KEK → failure
# ---------------------------------------------------------------------------


def test_unwrap_with_wrong_password_fails() -> None:
    """unwrapping with a KEK derived from the wrong password raises."""
    password = "correct-password"
    salt = generate_kdf_salt()
    kek = derive_kek(password, salt)
    dek = generate_dek()
    wrapped = wrap_dek(dek, kek)

    wrong_kek = derive_kek("wrong-password", salt)
    with pytest.raises(EnvelopeError, match="Failed to unwrap"):
        unwrap_dek(wrapped, wrong_kek)


def test_unwrap_with_different_salt_fails() -> None:
    """KEK derived with a different salt cannot unwrap."""
    password = "shared-password"
    salt1 = generate_kdf_salt()
    salt2 = generate_kdf_salt()
    kek1 = derive_kek(password, salt1)
    kek2 = derive_kek(password, salt2)

    assert kek1 != kek2, "Different salts must produce different KEKs"

    dek = generate_dek()
    wrapped = wrap_dek(dek, kek1)

    with pytest.raises(EnvelopeError, match="Failed to unwrap"):
        unwrap_dek(wrapped, kek2)


def test_unwrap_corrupted_ciphertext_fails() -> None:
    """Corrupted wrapped DEK raises EnvelopeError."""
    password = "test-password"
    salt = generate_kdf_salt()
    kek = derive_kek(password, salt)

    with pytest.raises(EnvelopeError, match="Failed to unwrap"):
        unwrap_dek("not-valid-ciphertext", kek)


# ---------------------------------------------------------------------------
# generate_dek uniqueness
# ---------------------------------------------------------------------------


def test_generate_dek_produces_unique_keys() -> None:
    """Each call to generate_dek produces a different key."""
    k1 = generate_dek()
    k2 = generate_dek()
    assert k1 != k2


# ---------------------------------------------------------------------------
# KEK derivation is deterministic for same inputs
# ---------------------------------------------------------------------------


def test_derive_kek_deterministic() -> None:
    """Same password + salt always produces the same KEK."""
    password = "deterministic-test"
    salt = generate_kdf_salt()
    kek1 = derive_kek(password, salt)
    kek2 = derive_kek(password, salt)
    assert kek1 == kek2


def test_derive_kek_different_passwords_different_keys() -> None:
    """Different passwords produce different KEKs."""
    salt = generate_kdf_salt()
    kek1 = derive_kek("password-a", salt)
    kek2 = derive_kek("password-b", salt)
    assert kek1 != kek2


# ---------------------------------------------------------------------------
# default params
# ---------------------------------------------------------------------------


def test_derive_kek_uses_default_params() -> None:
    """derive_kek works with default params."""
    kek = derive_kek("test", generate_kdf_salt())
    assert isinstance(kek, bytes)
    assert len(kek) == 32


def test_derive_kek_custom_params() -> None:
    """derive_kek works with custom KDF params."""
    params = {"time_cost": 2, "memory_cost": 32768, "parallelism": 2}
    kek = derive_kek("test", generate_kdf_salt(), params=params)
    assert isinstance(kek, bytes)
    assert len(kek) == 32


# ---------------------------------------------------------------------------
# DEK key-length check
# ---------------------------------------------------------------------------


def test_generate_dek_length() -> None:
    """generate_dek produces Fernet-compatible base64-encoded keys."""
    dek = generate_dek()
    # Fernet.generate_key returns 44 base64 chars (32 bytes raw)
    assert len(dek) == 44


# ---------------------------------------------------------------------------
# error-branch coverage: malformed params, bad KEK, encoding error
# ---------------------------------------------------------------------------


def test_derive_kek_missing_param_key_raises() -> None:
    """derive_kek with a params dict missing 'time_cost' raises."""
    params = {"memory_cost": 65536, "parallelism": 4}
    with pytest.raises(EnvelopeError, match="KEK derivation failed"):
        derive_kek("test", generate_kdf_salt(), params=params)


def test_wrap_dek_with_too_short_kek_raises() -> None:
    """wrap_dek with a 5-byte KEK (not valid Fernet key) raises."""
    dek = generate_dek()
    with pytest.raises(EnvelopeError, match="DEK wrapping failed"):
        wrap_dek(dek, b"short")


def test_unwrap_dek_non_ascii_raises() -> None:
    """unwrap_dek with non-ASCII ciphertext raises encoding error."""
    password = "test-password"
    salt = generate_kdf_salt()
    kek = derive_kek(password, salt)
    with pytest.raises(EnvelopeError, match="DEK unwrapping failed"):
        unwrap_dek("gAAAAA\xff\xfe\xfd", kek)
