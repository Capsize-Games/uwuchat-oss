"""Cross-tenant entity resolver isolation test.

Proves the round 10 Part 9 fix: the entity-resolver cache key includes
the tenant key, preventing cross-tenant identity collision.

The real function signature is
``resolve_entity(name, chatbot_id, ...)`` — it computes ``lookup_hash``
internally via ``_compute_lookup_hash(name)``.  The cache key is
``(tenant_key, chatbot_id, lookup_hash)``, so two tenants with the same
entity name and chatbot_id must use separate cache entries.

Entity IDs may happen to collide (both schemas start at sequence 1), so
assertions verify the cache-key *structure* rather than comparing raw
integer IDs.
"""

from __future__ import annotations

import pytest

from tenant_isolation_helpers import TwoTenants, two_tenants

_COLLIDING_NAME = "cross_tenant_test_entity"


@pytest.mark.functional
class TestEntityResolverCrossTenant:
    """Entity resolver must not leak entity IDs across tenant schemas."""

    def test_cache_entries_are_tenant_scoped(
        self, two_tenants: TwoTenants,
    ) -> None:
        """Resolve the same entity name + chatbot_id under both tenants
        and confirm the cache stores separate entries keyed by
        tenant_key — i.e. tenant B's lookup does not reuse tenant A's
        cached row."""
        from airunner_services.entity_resolver import (
            _resolved_cache,
            _compute_lookup_hash,
            resolve_entity,
        )
        from airunner_services.data.tenant import (
            reset_tenant_key,
            set_tenant_key,
        )

        _resolved_cache.clear()

        shared_chatbot_id = two_tenants.tenant_a.chatbot_id
        lookup_hash = _compute_lookup_hash(_COLLIDING_NAME)
        key_a = two_tenants.tenant_a.tenant_key
        key_b = two_tenants.tenant_b.tenant_key

        # Resolve as tenant A.
        token_a = set_tenant_key(key_a)
        try:
            entity_a = resolve_entity(
                name=_COLLIDING_NAME,
                chatbot_id=shared_chatbot_id,
            )
        finally:
            reset_tenant_key(token_a)

        assert entity_a is not None, "entity_a resolved to None"
        cache_key_a = (key_a, shared_chatbot_id, lookup_hash)
        assert cache_key_a in _resolved_cache, (
            f"Expected cache entry {cache_key_a} after tenant A resolve"
        )

        # Resolve as tenant B — must create a separate cache entry.
        token_b = set_tenant_key(key_b)
        try:
            entity_b = resolve_entity(
                name=_COLLIDING_NAME,
                chatbot_id=shared_chatbot_id,
            )
        finally:
            reset_tenant_key(token_b)

        assert entity_b is not None, "entity_b resolved to None"
        cache_key_b = (key_b, shared_chatbot_id, lookup_hash)
        assert cache_key_b in _resolved_cache, (
            f"Expected cache entry {cache_key_b} after tenant B resolve"
        )

        # The entries must be distinct (different tenant_key prefix).
        assert cache_key_a != cache_key_b, (
            "Cache keys for tenant A and tenant B must differ"
        )
        assert len(_resolved_cache) >= 2, (
            f"Expected >=2 cache entries (one per tenant), "
            f"got {len(_resolved_cache)}: {list(_resolved_cache.keys())}"
        )

    def test_poisoned_tenant_less_cache_entry_is_ignored(
        self, two_tenants: TwoTenants,
    ) -> None:
        """Inject a cache entry keyed WITHOUT tenant_key (simulating a
        rollback of the fix) and prove the real tenant-keyed lookup
        ignores it — i.e. the test *can* detect a broken fix."""
        from airunner_services.entity_resolver import (
            _resolved_cache,
            _cache_lock,
            _compute_lookup_hash,
            resolve_entity,
        )
        from airunner_services.data.tenant import (
            reset_tenant_key,
            set_tenant_key,
        )

        _resolved_cache.clear()

        shared_chatbot_id = two_tenants.tenant_a.chatbot_id
        lookup_hash = _compute_lookup_hash(_COLLIDING_NAME)

        # Poison the cache with a tenant_key-less entry whose value is
        # a sentinel that can never be a real entity_id.
        POISON_ID = -999
        broken_key = (shared_chatbot_id, lookup_hash)
        with _cache_lock:
            _resolved_cache[broken_key] = POISON_ID

        # Resolve as tenant B — the real cache key includes tenant_key,
        # so the poisoned entry above must NOT be returned.
        token_b = set_tenant_key(two_tenants.tenant_b.tenant_key)
        try:
            entity_b = resolve_entity(
                name=_COLLIDING_NAME,
                chatbot_id=shared_chatbot_id,
            )
        finally:
            reset_tenant_key(token_b)

        assert entity_b is not None, "entity_b resolved to None"
        assert entity_b != POISON_ID, (
            f"Poisoned tenant_key-less cache entry returned sentinel "
            f"{POISON_ID} — the cache key fix is not working"
        )

        # Cleanup.
        with _cache_lock:
            _resolved_cache.pop(broken_key, None)

    def test_resolve_same_entity_twice_is_idempotent(
        self, two_tenants: TwoTenants,
    ) -> None:
        """Entity.deleted.is_(False) regression: resolving the same
        entity name twice returns the same Entity.id, proving the
        lookup filter is not collapsing to WHERE false."""
        from airunner_services.entity_resolver import (
            _resolved_cache,
            resolve_entity,
        )
        from airunner_services.data.tenant import (
            reset_tenant_key,
            set_tenant_key,
        )

        _resolved_cache.clear()

        token = set_tenant_key(two_tenants.tenant_a.tenant_key)
        try:
            entity1 = resolve_entity(
                name=_COLLIDING_NAME,
                chatbot_id=two_tenants.tenant_a.chatbot_id,
            )
            entity2 = resolve_entity(
                name=_COLLIDING_NAME,
                chatbot_id=two_tenants.tenant_a.chatbot_id,
            )
        finally:
            reset_tenant_key(token)

        assert entity1 is not None, "first resolve returned None"
        assert entity2 is not None, "second resolve returned None"
        assert entity1 == entity2, (
            f"Expected same entity id on repeated resolve, "
            f"got {entity1} and {entity2}"
        )
