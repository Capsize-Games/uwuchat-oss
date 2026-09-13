"""Shared helpers for Celery task-internal setup.

Provides the standard pattern for re-entering tenant scope and
DEK scope inside a Celery task.

Tier-1 tasks (no DEK-encrypted data): ``task_tenant_scope``
Tier-2 tasks (needs DEK): ``task_dek_scope`` with relay read-once
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from airunner_services.tasks.redis_client import (
    dek_relay_get,
    dek_relay_get_and_delete,
)

logger = logging.getLogger(__name__)


# -- DEK relay crypto helpers (Part 3) --------------------------------------


def wrap_dek_for_relay(dek: bytes) -> str:
    """Wrap *dek* for relay storage using the per-user KEK-wrap primitive.

    Reuses ``wrap_dek`` from ``user_envelope.py`` (the same primitive
    used for at-rest DEK storage in Postgres).  The wrapping key is
    derived from the global keyring: the encrypt key is decoded from
    its Fernet url-safe-b64 form to raw bytes, then passed as the KEK
    to ``wrap_dek``.
    """
    import base64

    from airunner_services.utils.crypto.data_encryption import (
        get_keyring,
    )
    from airunner_services.utils.crypto.user_envelope import (
        wrap_dek,
    )

    keyring = get_keyring()
    assert keyring is not None, "Global keyring is required for DEK relay"
    # keyring.encrypt_key is the Fernet key string encoded as UTF-8.
    # wrap_dek expects raw 32-byte key material.  Decode from url-safe
    # base64 to get the raw bytes.
    raw_kek = base64.urlsafe_b64decode(keyring.encrypt_key)
    return wrap_dek(dek, raw_kek)


def unwrap_dek_from_relay(wrapped: str) -> bytes:
    """Unwrap a relayed DEK ciphertext using the per-user KEK-wrap
    primitive.

    Reuses ``unwrap_dek`` from ``user_envelope.py``.  The wrapping key
    is decoded from the global keyring's Fernet key the same way
    ``wrap_dek_for_relay`` encodes it.
    """
    import base64

    from airunner_services.utils.crypto.data_encryption import (
        get_keyring,
    )
    from airunner_services.utils.crypto.user_envelope import (
        unwrap_dek,
    )

    keyring = get_keyring()
    assert keyring is not None, "Global keyring is required for DEK relay"
    raw_kek = base64.urlsafe_b64decode(keyring.encrypt_key)
    return unwrap_dek(wrapped, raw_kek)


# -- Task scope helpers -----------------------------------------------------


@contextmanager
def task_tenant_scope(
    tenant_key: str,
) -> Iterator[None]:
    """Enter tenant scope for a Tier-1 task (no DEK-encrypted data).

    Usage inside a Celery task::

        with task_tenant_scope(tenant_key):
            with session_scope() as session:
                ...
    """
    from airunner_services.data.tenant import tenant_scope

    with tenant_scope(tenant_key):
        yield


@contextmanager
def task_dek_scope(
    tenant_key: str,
    account_id: int,
    peek: bool = False,
) -> Iterator[bytes | None]:
    """Enter tenant + DEK scope for a Tier-2 task via the DEK relay.

    Reads the wrapped DEK from the relay (Redis DB 2), unwraps it
    using the global keyring, and activates it for the task body.
    Yields the raw DEK bytes, or ``None`` when no relay entry exists —
    callers must check and follow the skip-and-defer path (Part 3,
    item 4).

    By default this deletes the relay entry on read (true read-once,
    correct when exactly one task consumes it). Pass ``peek=True`` for
    a multi-task pipeline (e.g. a Celery chord: one parent, N
    children, one callback) where more than one task invocation needs
    the same entry — the entry then stays until its TTL expires, and
    the *last* consumer must explicitly call ``dek_relay_delete``
    once the whole pipeline finishes.

    Usage inside a Celery task::

        with task_dek_scope(tenant_key, account_id) as dek:
            if dek is None:
                logger.info("DEK relay empty — skipping")
                return
            # work with DEK-encrypted data
            ...
    """
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.utils.crypto.dek_cache import dek_scope

    with tenant_scope(tenant_key):
        wrapped = (
            dek_relay_get(account_id) if peek
            else dek_relay_get_and_delete(account_id)
        )
        if wrapped is None:
            logger.info(
                "DEK relay empty for account %d — "
                "skipping DEK-encrypted work",
                account_id,
            )
            yield None
            return

        try:
            dek = unwrap_dek_from_relay(wrapped)
        except Exception:
            logger.warning(
                "DEK relay unwrap failed for account %d",
                account_id,
                exc_info=True,
            )
            yield None
            return

        with dek_scope(dek):
            yield dek
