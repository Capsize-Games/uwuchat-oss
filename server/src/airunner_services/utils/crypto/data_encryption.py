from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from cryptography.fernet import Fernet, InvalidToken


class DataEncryptionError(RuntimeError):
    pass


def _parse_keys(raw: str) -> list[bytes]:
    keys: list[bytes] = []
    for part in (raw or "").split(","):
        key = part.strip()
        if not key:
            continue
        try:
            keys.append(key.encode("utf-8"))
        except Exception:
            continue
    return keys


def generate_fernet_key() -> str:
    """Return a new base64 Fernet key as a string."""
    return Fernet.generate_key().decode("utf-8")


@dataclass(frozen=True)
class Keyring:
    encrypt_key: bytes
    decrypt_keys: tuple[bytes, ...]

    def fernet_for_encrypt(self) -> Fernet:
        return Fernet(self.encrypt_key)

    def fernet_for_decrypt(self) -> Iterable[Fernet]:
        for k in self.decrypt_keys:
            yield Fernet(k)


def get_keyring(required: bool = True) -> Optional[Keyring]:
    """Build a keyring from env.

    Env:
      - AIRUNNER_DATA_ENCRYPTION_KEYS: comma-separated Fernet keys
        (first used for encrypt).

    If *required* is True and no keys are present, raises.
    """
    raw = (os.environ.get("AIRUNNER_DATA_ENCRYPTION_KEYS") or "").strip()
    keys = _parse_keys(raw)
    if not keys:
        if required:
            raise DataEncryptionError(
                "AIRUNNER_DATA_ENCRYPTION_KEYS is not set; "
                "refusing to store encrypted user data"
            )
        return None

    # First key is used for encrypt; all keys can decrypt.
    return Keyring(encrypt_key=keys[0], decrypt_keys=tuple(keys))


def encrypt_bytes(data: bytes) -> bytes:
    if data is None:
        raise DataEncryptionError("encrypt_bytes received None")
    keyring = get_keyring(required=True)
    assert keyring is not None
    return keyring.fernet_for_encrypt().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    if token is None:
        raise DataEncryptionError("decrypt_bytes received None")
    keyring = get_keyring(required=True)
    assert keyring is not None

    last_err: Exception | None = None
    for f in keyring.fernet_for_decrypt():
        try:
            return f.decrypt(token)
        except InvalidToken as exc:
            last_err = exc
            continue

    raise DataEncryptionError(
        "Failed to decrypt payload with provided keys"
    ) from last_err


def is_encryption_active() -> bool:
    """Return True when AIRUNNER_DATA_ENCRYPTION_KEYS is configured.

    Use this to short-circuit ILIKE/substring queries that cannot
    match against Fernet-encrypted ciphertext columns.
    """
    return get_keyring(required=False) is not None


# ── Persistent edge/local key ────────────────────────────────────


_EDGE_KEY_FILENAME = "fernet_edge.key"
_edge_keyring: Keyring | None = None


def get_edge_keyring() -> Keyring | None:
    """Return a persistent keyring for edge/desktop deployments.

    Reads or generates a Fernet key stored under
    ``AIRUNNER_BASE_PATH / _EDGE_KEY_FILENAME``.  The key is
    generated once on first use and reused across restarts.

    Returns ``None`` when ``AIRUNNER_BASE_PATH`` is not set (cloud /
    multi-tenant deployments must never use this — they must have a
    per-user DEK in context).
    """
    global _edge_keyring

    if _edge_keyring is not None:
        return _edge_keyring

    base = os.environ.get("AIRUNNER_BASE_PATH", "").strip()
    if not base:
        return None

    key_path = Path(base) / _EDGE_KEY_FILENAME
    try:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            raw = key_path.read_text().strip()
            key_bytes = raw.encode("ascii")
        else:
            key_bytes = Fernet.generate_key()
            key_path.write_text(key_bytes.decode("ascii"))
            # Restrictive permissions — key file is a secret.
            key_path.chmod(0o600)
    except OSError:
        return None

    _edge_keyring = Keyring(
        encrypt_key=key_bytes, decrypt_keys=(key_bytes,)
    )
    return _edge_keyring


def _reset_edge_keyring_for_tests() -> None:
    """Clear the cached edge keyring (test-only)."""
    global _edge_keyring
    _edge_keyring = None
