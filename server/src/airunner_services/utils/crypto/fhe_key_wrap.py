"""DEK-wrapped serialization of TenSEAL secret-key contexts.

The FHE secret key is serialized with ``tenseal.Context.serialize()``
and then encrypted with the account's DEK using AES-256-GCM.  This
ensures the secret key is only accessible when a live, authenticated
session provides the DEK — matching the threat model described in
`fhe-encrypted-knowledge-search.md`_.

The Fernet keyring in :mod:`airunner_services.utils.crypto.data_encryption`
is intentionally NOT used here — that key is global, not per-user,
and would defeat the point of per-user FHE encryption.

Key derivation for AES-GCM
--------------------------

The DEK bytes stored in :mod:`airunner_services.utils.crypto.dek_cache`
are Fernet-format keys (44 bytes of base64 encoding a 32-byte key).
We extract the raw 32 bytes via base64 decode and use them directly
as an AES-256 key for GCM.
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)


_WRAP_NONCE_LENGTH = 12
"""AES-GCM nonce length in bytes (96 bits, standard)."""


def _raw_aes_key(dek: bytes) -> bytes:
    """Extract the raw 32-byte AES key from a Fernet-format DEK.

    *dek* is the output of ``Fernet.generate_key()`` — 44 bytes of
    urlsafe-base64 encoding a 32-byte key.
    """
    return base64.urlsafe_b64decode(dek)


def _aesgcm_from_dek(dek: bytes) -> AESGCM:
    """Return an AES-GCM cipher initialised with *dek*."""
    return AESGCM(_raw_aes_key(dek))


def wrap_secret_context(context, dek: bytes) -> bytes:
    """Encrypt a serialized TenSEAL secret context with the DEK.

    Args:
        context: A full TenSEAL context (with secret key).  Will be
            serialized via ``context.serialize()``.
        dek: The account's DEK (raw bytes from dek_cache).

    Returns:
        ``nonce (12) + ciphertext`` bytes suitable for storage in
        ``fhe_key_material.secret_key_wrapped``.

    Raises:
        DataEncryptionError: If no DEK is provided or wrapping fails.
    """
    if not dek:
        raise DataEncryptionError(
            "FHE secret-key wrap requires an active DEK"
        )
    serialized = context.serialize(
        save_secret_key=True,
        save_galois_keys=True,
        save_relin_keys=True,
        save_public_key=False,
    )
    nonce = os.urandom(_WRAP_NONCE_LENGTH)
    cipher = _aesgcm_from_dek(dek)
    return nonce + cipher.encrypt(nonce, serialized, None)


def unwrap_secret_context(wrapped: bytes, dek: bytes):
    """Decrypt a DEK-wrapped TenSEAL secret context.

    Args:
        wrapped: ``nonce + ciphertext`` bytes from
            ``fhe_key_material.secret_key_wrapped``.
        dek: The account's DEK (raw bytes from dek_cache).

    Returns:
        A deserialized TenSEAL context with the secret key loaded.

    Raises:
        DataEncryptionError: If the DEK is wrong, the wrapped data is
            corrupted, or deserialization fails.
    """
    if not dek:
        raise DataEncryptionError(
            "FHE secret-key unwrap requires an active DEK"
        )
    if len(wrapped) < _WRAP_NONCE_LENGTH + 1:
        raise DataEncryptionError(
            "Wrapped FHE secret key is too short — may be corrupted"
        )
    nonce = wrapped[:_WRAP_NONCE_LENGTH]
    ciphertext = wrapped[_WRAP_NONCE_LENGTH:]
    try:
        cipher = _aesgcm_from_dek(dek)
        plaintext = cipher.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise DataEncryptionError(
            "Failed to unwrap FHE secret key — DEK may be wrong "
            "or wrapped data is corrupted"
        ) from exc

    # Lazy import to avoid circular dependency at module level.
    from airunner_services.utils.crypto.fhe_helpers import (
        secret_context_from_bytes,
    )

    try:
        return secret_context_from_bytes(plaintext)
    except Exception as exc:
        raise DataEncryptionError(
            "Failed to deserialize unwrapped FHE secret context"
        ) from exc


__all__ = [
    "unwrap_secret_context",
    "wrap_secret_context",
]
