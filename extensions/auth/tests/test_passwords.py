"""Unit tests for argon2id password hashing."""

from __future__ import annotations

from extensions.auth.server.passwords import (
    hash_password,
    verify_password,
    dummy_verify,
)


def test_hash_password_produces_different_output():
    """Each call to hash_password produces a unique hash (salt is random)."""
    pw = "correct-horse-battery-staple"
    h1 = hash_password(pw)
    h2 = hash_password(pw)
    assert h1 != h2, "Hashes of the same password must differ (unique salt)"


def test_verify_password_round_trip():
    """hash → verify returns True for the correct password."""
    pw = "my-secret-password"
    pw_hash = hash_password(pw)
    assert verify_password(pw, pw_hash) is True


def test_verify_password_rejects_wrong_password():
    """verify_password returns False for an incorrect password."""
    pw_hash = hash_password("the-real-password")
    assert verify_password("wrong-password", pw_hash) is False


def test_verify_password_rejects_empty():
    """verify_password returns False for an empty string."""
    pw_hash = hash_password("some-password")
    assert verify_password("", pw_hash) is False


def test_hash_is_not_plaintext():
    """The stored hash is not the plaintext password."""
    pw = "sensitive-password"
    pw_hash = hash_password(pw)
    assert pw not in pw_hash, "Hash must not contain the original password"


def test_hash_is_not_trivially_reversible():
    """Two different passwords produce structurally different hashes."""
    h1 = hash_password("alpha-bravo-charlie")
    h2 = hash_password("delta-echo-foxtrot")
    assert h1 != h2


def test_dummy_verify_does_not_raise():
    """dummy_verify completes without raising (used for timing safety)."""
    dummy_verify()
