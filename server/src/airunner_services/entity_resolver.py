"""Entity resolution — find-or-create an Entity row by name.

Uses a deterministic HMAC-SHA256 blind index (``name_lookup_hash``)
for fast exact-match lookups without storing plaintext names —
currently the only matching strategy implemented (conservative
default: prefer creating a duplicate entity over incorrectly merging
two different people).

Resolved ids are cached in-process per (chatbot_id, lookup_hash) —
safe because the underlying row is immutable once created (an
existing entity's identity never changes), and correct because a
cache miss always falls through to the real DB lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import threading
from typing import Optional

from airunner_services.database.models.entity import Entity
from airunner_services.database.session import session_scope
from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)

logger = logging.getLogger(__name__)

# Server-side key for the HMAC blind index.  Falls back to
# AIRUNNER_JWT_SECRET for dev; production must set a dedicated
# AIRUNNER_ENTITY_LOOKUP_KEY to avoid reusing JWT signing materials
# for an unrelated cryptographic purpose.
_LOOKUP_KEY = (
    os.environ.get("AIRUNNER_ENTITY_LOOKUP_KEY", "")
    or os.environ.get("AIRUNNER_JWT_SECRET", "")
).encode()[:32]

_RECOGNIZED_TYPES = frozenset({
    "person", "place", "thing", "concept", "organization", "event",
})


def normalize_entity_type(entity_type: str) -> str:
    """Return *entity_type* if it is one of the recognized types,
    otherwise return ``"person"`` as the safe default.

    This is the public counterpart of the inline check in
    :func:`resolve_entity`, provided so callers can validate before
    calling or storing.
    """
    return (
        entity_type
        if entity_type in _RECOGNIZED_TYPES
        else "person"
    )
_cache_lock = threading.Lock()
_resolved_cache: dict[tuple[str, int, str], int] = {}
_MAX_CACHE_SIZE = 8192


def _resolve_tenant_key() -> str:
    """Return the current tenant key, or ``"__no_tenant__"`` when the
    tenant context is not active (e.g. during tests or CLI tools)."""
    try:
        from airunner_services.data.tenant import get_tenant_key
        return get_tenant_key() or "__no_tenant__"
    except Exception:
        return "__no_tenant__"


def resolve_entity(
    name: str,
    chatbot_id: int,
    entity_type: str = "person",
    source_type: str = "inferred",
    source_ref_table: str | None = None,
    source_ref_id: int | None = None,
) -> Optional[int]:
    """Find or create an entity row for *name* within *chatbot_id* scope.

    Returns the entity's id, or None when both lookup and creation
    fail (e.g. no DEK available, no server key, or name is empty).
    Returns an id rather than the ORM object because the object would
    be detached (and its attributes unreadable) once this function's
    session closes — every caller only ever needs the id anyway.
    """
    name = (name or "").strip()
    if not name:
        return None

    if entity_type not in _RECOGNIZED_TYPES:
        entity_type = "person"

    lookup_hash = _compute_lookup_hash(name)
    tenant_key = _resolve_tenant_key()
    cache_key = (tenant_key, chatbot_id, lookup_hash)
    with _cache_lock:
        cached = _resolved_cache.get(cache_key)
    if cached is not None:
        return cached

    entity_id = _resolve_entity_uncached(
        name, chatbot_id, lookup_hash, entity_type,
        source_type, source_ref_table, source_ref_id,
    )
    if entity_id is not None:
        with _cache_lock:
            if len(_resolved_cache) >= _MAX_CACHE_SIZE:
                _resolved_cache.clear()
            _resolved_cache[cache_key] = entity_id
    return entity_id


def _resolve_entity_uncached(
    name: str,
    chatbot_id: int,
    lookup_hash: str,
    entity_type: str,
    source_type: str,
    source_ref_table: str | None,
    source_ref_id: int | None,
) -> Optional[int]:
    """Look up or create the Entity row, bypassing the cache."""
    with session_scope() as session:
        try:
            existing = (
                session.query(Entity)
                .filter(
                    Entity.chatbot_id == chatbot_id,
                    Entity.name_lookup_hash == lookup_hash,
                    Entity.deleted.is_(False),
                )
                .first()
            )
        except DataEncryptionError:
            # A legacy row encrypted under a since-rotated/expired DEK
            # can't be decrypted here — same fail-open philosophy as
            # the create path below (prefer a duplicate entity over
            # crashing the whole sync). Without this, one stale row
            # silently kills the entire task with no further progress
            # or completion ever written.
            logger.warning(
                "Entity lookup hit undecryptable row for hash=%s — "
                "treating as not-found",
                lookup_hash,
            )
            existing = None
        if existing is not None:
            return existing.id

        try:
            row = Entity(
                entity_type=entity_type,
                chatbot_id=chatbot_id,
                display_name_ct=name,
                name_lookup_hash=lookup_hash,
                source_type=source_type,
                source_ref_table=source_ref_table,
                source_ref_id=source_ref_id,
            )
            session.add(row)
            session.flush()
            return row.id
        except Exception as exc:
            logger.warning(
                "Failed to create Entity for name hash=%s: %s",
                lookup_hash, exc,
            )
            return None


def _normalize_name(name: str) -> str:
    """Collapse whitespace and lowercase for hash stability."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _compute_lookup_hash(name: str) -> str:
    """HMAC-SHA256 blind index of the normalized name.

    Uses the first 32 bytes of the lookup key as the HMAC secret.
    Returns the first 16 hex characters of the digest — sufficient
    for exact-match dedup, not reversible to the original name.
    """
    normalized = _normalize_name(name)
    return hmac.new(
        _LOOKUP_KEY, normalized.encode(), hashlib.sha256,
    ).hexdigest()[:16]
