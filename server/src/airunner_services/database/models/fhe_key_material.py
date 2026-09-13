"""Per-account FHE key material for homomorphically encrypted embeddings.

One row per account.  The public context (without secret key) is stored
in the clear — it is not sensitive.  The secret key is serialized and
then wrapped with the account's DEK (AES-256-GCM) before storage.

Lifecycle
---------

1. **Lazy creation, fail-closed.**  The first time a fact is written
   for an account with no ``fhe_key_material`` row, a new CKKS context
   is generated, split, and stored.  If no DEK is available the
   operation raises — no fallback to plaintext embeddings.
2. **Per-request unwrap + cache.**  The secret context is unwrapped
   and held in a process-local cache (see ``fhe_cache``) for the
   lifetime of the access token.
"""
from __future__ import annotations

from sqlalchemy import Column, Integer, LargeBinary

from airunner_services.database.base import BaseModel


class FheKeyMaterial(BaseModel):
    """One row per account — FHE public context and wrapped secret key."""

    __tablename__ = "fhe_key_material"

    account_id = Column(
        Integer,
        primary_key=True,
        autoincrement=False,
    )
    # Serialized TenSEAL context WITHOUT the secret key.
    # Contains encryption params + Galois keys + relin keys.
    # Not sensitive — needed to encrypt new embeddings at write time.
    public_context = Column(LargeBinary, nullable=False)

    # TenSEAL secret key, serialized, then AES-256-GCM encrypted with
    # the account's DEK.  Sensitive — must never be logged or returned
    # in any API response.
    secret_key_wrapped = Column(LargeBinary, nullable=False)


__all__ = ["FheKeyMaterial"]
