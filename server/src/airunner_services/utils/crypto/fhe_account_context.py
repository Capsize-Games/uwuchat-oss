"""Per-account FHE public-context resolver — shared by all write paths.

Extracted from ``knowledge_crud.py::_get_or_create_public_context``
so that ``email_body_indexer.py``, ``recall_conversation.py``, and
any future FHE-embedding write path can call the same function
without importing knowledge_crud (which carries heavy dependencies).
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)
from airunner_services.utils.crypto.dek_cache import get_user_dek

logger = logging.getLogger(__name__)


def get_or_create_public_context(account_id: int):
    """Return the TenSEAL public context for *account_id*.

    If no ``fhe_key_material`` row exists, generates a fresh CKKS
    key pair (lazy creation).  Requires an active DEK in context
    to wrap the secret key — fails closed if no DEK is available.

    Args:
        account_id: The account to look up or create FHE keys for.

    Returns:
        A TenSEAL public context (no secret key) suitable for
        encrypting embeddings.

    Raises:
        DataEncryptionError: If no DEK is available (fail-closed).
    """
    from airunner_services.database.models.fhe_key_material import (
        FheKeyMaterial,
    )
    from airunner_services.utils.crypto.fhe_helpers import (
        generate_fhe_context,
        public_context_from_bytes,
    )
    from airunner_services.utils.crypto.fhe_key_wrap import (
        wrap_secret_context,
    )

    with FheKeyMaterial.objects.transaction() as tx:
        row = tx.query(FheKeyMaterial).filter(
            FheKeyMaterial.account_id == account_id,
        ).first()
        if row is not None:
            return public_context_from_bytes(row.public_context)

        # Lazy creation — requires DEK.
        dek = get_user_dek()
        if dek is None:
            raise DataEncryptionError(
                "FHE key material creation requires an active DEK. "
                "No DEK in context — cannot wrap the FHE secret key "
                "for account %d. This guard prevents silent fallback "
                "to plaintext embeddings." % account_id
            )
        public_ctx, secret_ctx = generate_fhe_context()
        wrapped = wrap_secret_context(secret_ctx, dek)
        public_bytes = public_ctx.serialize()
        row = FheKeyMaterial(
            account_id=account_id,
            public_context=public_bytes,
            secret_key_wrapped=wrapped,
            created_at=datetime.now(UTC),
        )
        tx.add(row)
        tx.flush()
        logger.info(
            "Created FHE key material for account %d", account_id,
        )
        return public_context_from_bytes(public_bytes)


__all__ = ["get_or_create_public_context"]
