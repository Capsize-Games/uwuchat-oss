"""SQLAlchemy TypeDecorator for per-user-key encryption.

Columns declared with ``UserEncryptedText`` store their data encrypted
with the user's Data Encryption Key (DEK) — the per-user key managed by
:mod:`airunner_services.utils.crypto.user_envelope`.

Supports both string and JSON-serializable values (dict, list).  JSON
values are prefixed with a non-printable marker before encryption so
round-tripping is exact regardless of content shape.

During the migration period, reads fall back to the global Fernet keyring
(``EncryptedText``'s legacy behaviour) when the DEK is unavailable, so
existing rows on the global key remain readable until lazy re-encryption
completes.  Writes always require an active DEK and **fail closed** when
none is available.
"""

from __future__ import annotations

import json

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger
from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
    decrypt_bytes,
    get_edge_keyring,
    get_keyring,
)
from airunner_services.utils.crypto.dek_cache import get_user_dek

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_FERNET_PREFIX = b"gAAAAA"

# Non-printable marker prefixed to JSON-serialized values before
# encryption.  This distinguishes JSON payloads from plain strings
# without relying on content-sniffing (which would corrupt strings
# that happen to look like JSON, e.g. the literal message "[1,2,3]").
#
# The marker is part of the plaintext (encrypted with the rest), so
# it only matters after decryption.  NUL+chr(1) ensures it never
# collides with real user text.
_JSON_MARKER = b"\x00\x01JSON"


def _looks_encrypted(raw: bytes) -> bool:
    return raw.startswith(_FERNET_PREFIX)


def _serialize(value) -> bytes:
    """Convert *value* to bytes for encryption.

    Strings are encoded directly.  Dicts/lists are JSON-serialized
    and prefixed with ``_JSON_MARKER`` so deserialization is exact.
    """
    if isinstance(value, str):
        return value.encode("utf-8")
    return _JSON_MARKER + json.dumps(value, default=str).encode("utf-8")


def _deserialize(raw: str) -> object:
    """Convert decrypted text back to the original Python value.

    If the plaintext starts with ``_JSON_MARKER``, strip it and
    parse as JSON.  Otherwise return the raw string as-is.
    """
    if raw.startswith("\x00\x01JSON"):
        try:
            return json.loads(raw[6:])
        except (json.JSONDecodeError, TypeError):
            return raw
    return raw


class UserEncryptedText(TypeDecorator):
    """Transparent per-user-key encrypted Text column.

    On bind (write):
      - Tries the per-request DEK first (preferred path).
      - Falls back to the global Fernet keyring when no per-user DEK
        is in context (defense-in-depth — data is still encrypted at
        rest, just not scoped to the user's own key).
      - Raises :class:`DataEncryptionError` when neither key is
        available — fails closed, never stores plaintext.

    On read:
      - Tries the per-request DEK first.
      - Falls back to the global keyring (legacy rows not yet
        re-encrypted).
      - Raises :class:`DataEncryptionError` when the stored value is
        confirmed ciphertext but cannot be decrypted.
      - Returns raw plaintext when the stored value does not look
        encrypted (plaintext written by legacy ``EncryptedText``
        before this column type was introduced).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt before writing to DB.

        Tries the per-request DEK first.  Falls back to the global
        keyring when no DEK is in context (dev mode, anonymous users,
        or accounts without a user envelope).  In single-tenant /
        edge / desktop mode, falls back to a persistent local key
        stored under ``AIRUNNER_BASE_PATH`` so data survives
        restarts.  Raises ``DataEncryptionError`` when no key of any
        kind is available — fails closed.
        """
        if value is None:
            return None

        plaintext = _serialize(value)
        if not plaintext:
            return ""

        dek = get_user_dek()
        if dek is not None:
            try:
                return self._encrypt_with_key(
                    plaintext, dek
                ).decode("utf-8")
            except DataEncryptionError:
                logger.exception(
                    "UserEncryptedText: encrypt with DEK failed"
                )
                raise

        # No per-user DEK — fall back to the global keyring, matching
        # the read-side behavior in process_result_value.
        keyring = get_keyring(required=False)
        if keyring is not None:
            try:
                return keyring.fernet_for_encrypt().encrypt(
                    plaintext
                ).decode("utf-8")
            except DataEncryptionError:
                logger.exception(
                    "UserEncryptedText: encrypt with global key failed"
                )
                raise

        # No configured keyring — try the persistent edge/local key
        # (for single-tenant desktop deployments with no account).
        edge_keyring = get_edge_keyring()
        if edge_keyring is not None:
            try:
                return edge_keyring.fernet_for_encrypt().encrypt(
                    plaintext
                ).decode("utf-8")
            except DataEncryptionError:
                logger.exception(
                    "UserEncryptedText: encrypt with edge key failed"
                )
                raise

        # No key available at all — fail closed.
        raise DataEncryptionError(
            "UserEncryptedText: no per-user DEK, no global keyring, "
            "and no persistent edge key — cannot encrypt. The "
            "caller must ensure a DEK is active (via dek_scope or "
            "task_dek_scope) before writing to an encrypted column."
        )

    def process_result_value(self, value, dialect):
        """Decrypt after reading from DB.

        Raises :class:`DataEncryptionError` when the stored value is
        confirmed ciphertext (starts with the Fernet prefix) but neither
        the per-account DEK nor the global keyring can decrypt it.
        Previously this returned raw ciphertext as-is, which downstream
        code interpreted as valid data — causing silent data corruption
        (e.g. conversations appearing empty).
        """
        if value is None:
            return None

        raw = value.encode("utf-8")
        if not _looks_encrypted(raw):
            return _deserialize(value)

        # Try per-request DEK first
        dek = get_user_dek()
        if dek is not None:
            try:
                decrypted = (
                    self._decrypt_with_key(raw, dek)
                    .decode("utf-8")
                )
                return _deserialize(decrypted)
            except DataEncryptionError:
                # Not encrypted with this DEK — fall through to
                # global key.
                pass

        # Fall back to global keyring (legacy rows)
        keyring = get_keyring(required=False)
        if keyring is not None:
            try:
                decrypted = decrypt_bytes(raw).decode("utf-8")
                return _deserialize(decrypted)
            except DataEncryptionError:
                logger.error(
                    "UserEncryptedText: decrypt failed with both DEK "
                    "and global key; raising DataEncryptionError "
                    "(value length=%d, prefix=%s)",
                    len(raw),
                    raw[:20],
                )
                raise DataEncryptionError(
                    "UserEncryptedText: unable to decrypt stored "
                    "value — neither the per-account DEK nor the "
                    "global keyring could decrypt this ciphertext. "
                    "The user may need to re-authenticate to "
                    "re-populate the DEK cache."
                )

        # Try the persistent edge/local key (single-tenant desktop).
        edge_keyring = get_edge_keyring()
        if edge_keyring is not None:
            try:
                decrypted = (
                    self._decrypt_with_key(raw, edge_keyring.encrypt_key)
                    .decode("utf-8")
                )
                return _deserialize(decrypted)
            except DataEncryptionError:
                pass

        # No key available at all, but value is confirmed ciphertext.
        logger.error(
            "UserEncryptedText: confirmed ciphertext but no DEK, "
            "no global keyring, and no edge key configured; "
            "raising DataEncryptionError "
            "(value length=%d, prefix=%s)",
            len(raw),
            raw[:20],
        )
        raise DataEncryptionError(
            "UserEncryptedText: unable to decrypt stored value — "
            "no DEK in context and no global keyring is configured. "
            "The user may need to re-authenticate."
        )

    @staticmethod
    def _encrypt_with_key(plaintext: bytes, key_bytes: bytes) -> bytes:
        """Encrypt *plaintext* with a Fernet key.

        *key_bytes* is already a valid Fernet key (base64-encoded,
        as returned by ``Fernet.generate_key()``).  Do NOT re-encode.

        Raises :class:`DataEncryptionError` on any failure.
        """
        from cryptography.fernet import Fernet

        try:
            f = Fernet(key_bytes)
            return f.encrypt(plaintext)
        except Exception as exc:
            raise DataEncryptionError(
                "Encryption with user DEK failed"
            ) from exc

    @staticmethod
    def _decrypt_with_key(ciphertext: bytes, key_bytes: bytes) -> bytes:
        """Decrypt *ciphertext* with a Fernet key.

        *key_bytes* is already a valid Fernet key (base64-encoded,
        as returned by ``Fernet.generate_key()``).  Do NOT re-encode.

        Raises :class:`DataEncryptionError` on any failure.
        """
        from cryptography.fernet import Fernet

        try:
            f = Fernet(key_bytes)
            return f.decrypt(ciphertext)
        except Exception as exc:
            raise DataEncryptionError(
                "Decryption with user DEK failed"
            ) from exc


__all__ = ["UserEncryptedText"]
