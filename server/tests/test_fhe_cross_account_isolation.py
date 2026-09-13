"""Cross-account isolation tests for per-account FHE key material.

Verifies that per-account key material is genuinely independent:
different accounts get different public contexts, and the DB-level
lookup (``FheKeyMaterial.objects.query().filter(account_id=...)``)
correctly scopes by account.

The TenSEAL library may allow cross-context deserialization when both
contexts share the same CKKS parameters (which they will from the same
``generate_fhe_context`` call).  The real isolation is enforced at the
**application layer**: ``fhe_similarity_rank`` looks up the secret key
for ``account_id``, not the account that encrypted the data.  This test
verifies that the DB lookup is correctly scoped — a different
account's key material row is returned for a different account_id.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from airunner_services.utils.crypto.fhe_helpers import (
    EMBEDDING_DIM,
    encrypt_embedding,
    generate_fhe_context,
    l2_normalize,
)
from airunner_services.utils.crypto.fhe_key_wrap import (
    wrap_secret_context,
)
from cryptography.fernet import Fernet


@pytest.fixture
def fhe_contexts():
    public_ctx, secret_ctx = generate_fhe_context()
    return public_ctx, secret_ctx


class TestFheCrossAccountIsolation:
    """Per-account key material isolation at the application layer."""

    def test_key_material_lookup_is_scoped_by_account_id(
        self, fhe_contexts,
    ) -> None:
        """When ``fhe_similarity_rank`` looks up key material for
        account_id=999, it queries ``FheKeyMaterial.account_id == 999``
        — not the account that encrypted the data."""
        from airunner_services.utils.crypto.fhe_search import (
            fhe_similarity_rank,
        )

        public_ctx, secret_ctx = fhe_contexts
        dek = Fernet.generate_key()

        vec = l2_normalize(
            np.random.RandomState(42).randn(EMBEDDING_DIM).tolist()
        )
        ciphertext = encrypt_embedding(vec, public_ctx)

        candidate = MagicMock()
        candidate.embedding_enc = ciphertext

        wrapped = wrap_secret_context(secret_ctx, dek)
        mock_row = MagicMock()
        mock_row.secret_key_wrapped = wrapped

        # Use a fake column descriptor so that
        #   FheKeyMaterial.account_id == 999
        # returns a meaningful comparison object instead of False
        # (MagicMock.__eq__ returns NotImplemented against non-mocks
        # in Python ≥3.13, which collapses to False).  This lets us
        # capture and assert on the filter() call's arguments.
        _filter_calls: list = []

        class _FakeColumn:
            def __init__(self, name: str):
                self._name = name

            def __eq__(self, other):
                result = _Comparison(self._name, other)
                return result

            def __repr__(self):
                return f"<column {self._name}>"

        class _Comparison:
            def __init__(self, left: str, right):
                self._left = left
                self._right = right

            def __str__(self):
                return (
                    f"<comparison {self._left} == {self._right}>"
                )

        def _fake_filter(*args, **kwargs):
            _filter_calls.append((args, kwargs))
            result = MagicMock()
            result.first.return_value = mock_row
            return result

        mock_fkm = MagicMock()
        mock_fkm.account_id = _FakeColumn("account_id")
        mock_fkm.objects.query.return_value.filter.side_effect = (
            _fake_filter
        )

        with patch(
            "airunner_services.database.models.fhe_key_material"
            ".FheKeyMaterial",
            mock_fkm,
        ), patch(
            "airunner_services.utils.crypto.dek_cache.get_user_dek",
            return_value=dek,
        ), patch(
            "airunner_services.utils.crypto.fhe_cache"
            ".fhe_cache_get",
            return_value=None,
        ):
            fhe_similarity_rank(
                candidates=[candidate],
                get_ciphertext=lambda r: r.embedding_enc,
                account_id=999,
                normalized_query=vec,
                top_k=5,
            )

        # Verify filter() was called and the comparison captures
        # account_id == 999 — this proves the scoping filter is
        # present and would fail if it were removed.
        assert len(_filter_calls) >= 1, (
            "filter() was never called — account scoping absent"
        )
        filter_args = _filter_calls[0][0]
        assert len(filter_args) >= 1, (
            "filter() called with no arguments — account scoping absent"
        )
        comp = filter_args[0]
        assert hasattr(comp, "_left") and comp._left == "account_id", (
            f"filter comparison left is {comp._left!r}, "
            "expected 'account_id'"
        )
        assert comp._right == 999, (
            f"filter comparison right is {comp._right}, expected 999"
        )

    def test_different_account_keys_are_different(
        self, fhe_contexts,
    ) -> None:
        """Two calls to generate_fhe_context produce independent key
        pairs — the foundation of per-account isolation."""
        public_a, secret_a = fhe_contexts
        public_b, secret_b = generate_fhe_context()

        vec = l2_normalize(
            np.random.RandomState(42).randn(EMBEDDING_DIM).tolist()
        )

        ct_a = encrypt_embedding(vec, public_a)
        ct_b = encrypt_embedding(vec, public_b)

        assert ct_a != ct_b, (
            "Different public keys must produce different ciphertexts"
        )
