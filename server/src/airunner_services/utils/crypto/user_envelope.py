"""User-controlled key envelope — DEK wrapping with password-derived KEK.

Each user gets a random 32-byte Data Encryption Key (DEK).  The DEK is
never stored in the clear — it is wrapped (encrypted) by a Key Encryption
Key (KEK) derived from the user's password via Argon2id.  The wrapped DEK
sits in the DB; the KEK is never persisted.

This module provides the low-level primitives.  The DEK cache
(:mod:`airunner_services.utils.crypto.dek_cache`) and the per-request
contextvar wiring live in separate modules.
"""

from __future__ import annotations

import base64
import os

from argon2.low_level import hash_secret_raw, Type
from cryptography.fernet import Fernet, InvalidToken


class EnvelopeError(RuntimeError):
    """Raised when a key-envelope operation fails (wrap, unwrap, derive)."""


# Argon2id parameters — kept in sync with extensions/auth/server/passwords.py
# but stored per-account so they can be upgraded independently later.
DEFAULT_KDF_PARAMS: dict = {
    "time_cost": 3,
    "memory_cost": 65536,
    "parallelism": 4,
}

# Output key length in bytes.  Fernet requires 32-byte URL-safe base64 keys.
_KEK_LENGTH = 32

# Salt length for KEK derivation (independent of the login-hash salt).
_SALT_LENGTH = 16


def generate_kdf_salt() -> bytes:
    """Return a fresh random salt for KEK derivation."""
    return os.urandom(_SALT_LENGTH)


def encode_salt(salt: bytes) -> str:
    """Base64-encode a salt for storage in a text column."""
    return base64.b64encode(salt).decode("ascii")


def decode_salt(encoded: str) -> bytes:
    """Decode a base64-encoded salt back to bytes."""
    return base64.b64decode(encoded.encode("ascii"))


def derive_kek(password: str, salt: bytes, params: dict | None = None) -> bytes:
    """Derive a Fernet-compatible KEK from *password* using Argon2id.

    Args:
        password: The user's plaintext password (never logged or persisted).
        salt: Random salt bytes for KDF (independent of login-hash salt).
        params: Optional dict with ``time_cost``, ``memory_cost``,
            ``parallelism``.  Defaults to :data:`DEFAULT_KDF_PARAMS`.

    Returns:
        32-byte raw key suitable for use as a Fernet key (after base64
        encoding).
    """
    if params is None:
        params = DEFAULT_KDF_PARAMS

    try:
        raw = hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=int(params["time_cost"]),
            memory_cost=int(params["memory_cost"]),
            parallelism=int(params["parallelism"]),
            hash_len=_KEK_LENGTH,
            type=Type.ID,
        )
        return raw
    except Exception as exc:
        raise EnvelopeError(
            f"KEK derivation failed: {exc}"
        ) from exc


def generate_dek() -> bytes:
    """Return a fresh 32-byte random DEK.

    Returns the raw bytes; callers are responsible for base64-encoding
    before using as a Fernet key.
    """
    return Fernet.generate_key()


def _kek_to_fernet(kek: bytes) -> Fernet:
    """Wrap raw KEK bytes into a Fernet instance."""
    return Fernet(base64.urlsafe_b64encode(kek))


def wrap_dek(dek: bytes, kek: bytes) -> str:
    """Encrypt *dek* with *kek* and return the base64-encoded ciphertext.

    Returns a string suitable for storing in the ``wrapped_dek`` column.
    """
    try:
        f = _kek_to_fernet(kek)
        token = f.encrypt(dek)
        return token.decode("ascii")
    except Exception as exc:
        raise EnvelopeError(
            f"DEK wrapping failed: {exc}"
        ) from exc


def unwrap_dek(wrapped: str, kek: bytes) -> bytes:
    """Decrypt *wrapped* (base64 ciphertext) with *kek* and return the raw DEK.

    Raises :class:`EnvelopeError` when the KEK is wrong or the ciphertext
    is malformed.
    """
    try:
        f = _kek_to_fernet(kek)
        return f.decrypt(wrapped.encode("ascii"))
    except InvalidToken as exc:
        raise EnvelopeError(
            "Failed to unwrap DEK — password is incorrect or wrapped "
            "key is corrupted"
        ) from exc
    except Exception as exc:
        raise EnvelopeError(
            f"DEK unwrapping failed: {exc}"
        ) from exc


__all__ = [
    "DEFAULT_KDF_PARAMS",
    "EnvelopeError",
    "decode_salt",
    "derive_kek",
    "encode_salt",
    "generate_dek",
    "generate_kdf_salt",
    "unwrap_dek",
    "wrap_dek",
]
