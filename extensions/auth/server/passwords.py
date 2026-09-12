"""Password hashing using argon2id.

Argon2id is the OWASP-recommended password hashing algorithm.  We use the
``argon2-cffi`` package which must be installed in the server environment:

    pip install argon2-cffi
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

_hasher = PasswordHasher(
    time_cost=3,       # Number of iterations
    memory_cost=65536,  # 64 MiB
    parallelism=4,      # Number of threads
    hash_len=32,        # Length of the hash in bytes
    salt_len=16,        # Length of the salt in bytes
)


# Precomputed hash of a random throwaway value.  Used to spend roughly the
# same CPU verifying a password when the account does not exist (or has no
# password), so response timing does not reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-compare")


def hash_password(password: str) -> str:
    """Return an argon2id hash of *password*."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether *password* matches the stored *password_hash*."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def dummy_verify() -> None:
    """Burn a verify cycle to mask account-existence timing differences."""
    try:
        _hasher.verify(_DUMMY_HASH, "dummy-password-for-constant-time-compare")
    except (VerifyMismatchError, VerificationError):
        pass
