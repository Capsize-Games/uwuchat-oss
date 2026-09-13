"""Shared FHE scoring helper tests.

Covers ``fhe_similarity_rank`` regression guard and candidate-cap
constant.
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
from airunner_services.utils.crypto.fhe_search import (
    FHE_CANDIDATE_CAP,
    fhe_similarity_rank,
)

CKKS_TOLERANCE: float = 1e-4


# ── Helpers ──────────────────────────────────────────────────────


def _mock_key_material_and_dek(secret_ctx, dek):
    """Return (mock_fkm, mock_row) for fhe_similarity_rank."""
    mock_fkm = MagicMock()
    mock_row = MagicMock()
    mock_row.secret_key_wrapped = wrap_secret_context(secret_ctx, dek)
    mock_fkm.objects.query.return_value.filter.return_value.first.return_value = (
        mock_row
    )
    return mock_fkm, mock_row


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def fhe_contexts():
    public_ctx, secret_ctx = generate_fhe_context()
    return public_ctx, secret_ctx


@pytest.fixture
def random_embedding() -> np.ndarray:
    rng = np.random.RandomState(42)
    vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
    return l2_normalize(vec.tolist())


@pytest.fixture
def query_vector() -> np.ndarray:
    rng = np.random.RandomState(99)
    vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
    return l2_normalize(vec.tolist())


@pytest.fixture
def dek():
    from cryptography.fernet import Fernet

    return Fernet.generate_key()


# ── Shared FHE scoring helper ────────────────────────────────────


class TestFheSimilarityRank:
    """The shared helper scores candidates correctly and respects
    top_k."""

    def test_ranks_candidates_by_score(
        self, fhe_contexts, random_embedding, query_vector, dek,
    ) -> None:
        public_ctx, secret_ctx = fhe_contexts
        candidates = []
        for i in range(3):
            rng = np.random.RandomState(100 + i)
            vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
            vec = l2_normalize(vec.tolist())
            enc = encrypt_embedding(vec, public_ctx)
            candidates.append({"id": i, "embedding_enc": enc})

        mock_fkm, _mock_row = _mock_key_material_and_dek(
            secret_ctx, dek,
        )
        with patch(
            "airunner_services.utils.crypto.fhe_cache"
            ".fhe_cache_get",
            return_value=None,
        ), patch(
            "airunner_services.database.models.fhe_key_material"
            ".FheKeyMaterial",
            mock_fkm,
        ), patch(
            "airunner_services.utils.crypto.dek_cache.get_user_dek",
            return_value=dek,
        ):
            scored = fhe_similarity_rank(
                candidates,
                get_ciphertext=lambda c: c["embedding_enc"],
                account_id=1,
                normalized_query=query_vector.tolist(),
                top_k=3,
            )

        assert len(scored) == 3
        for i in range(len(scored) - 1):
            assert scored[i][1] >= scored[i + 1][1]

    def test_respects_top_k(
        self, fhe_contexts, random_embedding, query_vector, dek,
    ) -> None:
        public_ctx, secret_ctx = fhe_contexts
        candidates = []
        for i in range(5):
            rng = np.random.RandomState(200 + i)
            vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
            vec = l2_normalize(vec.tolist())
            enc = encrypt_embedding(vec, public_ctx)
            candidates.append({"id": i, "embedding_enc": enc})

        mock_fkm, _mock_row = _mock_key_material_and_dek(
            secret_ctx, dek,
        )
        with patch(
            "airunner_services.utils.crypto.fhe_cache"
            ".fhe_cache_get",
            return_value=None,
        ), patch(
            "airunner_services.database.models.fhe_key_material"
            ".FheKeyMaterial",
            mock_fkm,
        ), patch(
            "airunner_services.utils.crypto.dek_cache.get_user_dek",
            return_value=dek,
        ):
            scored = fhe_similarity_rank(
                candidates,
                get_ciphertext=lambda c: c["embedding_enc"],
                account_id=1,
                normalized_query=query_vector.tolist(),
                top_k=2,
            )

        assert len(scored) == 2

    def test_top_k_zero_returns_empty(
        self, fhe_contexts, random_embedding, query_vector,
    ) -> None:
        scored = fhe_similarity_rank(
            [{"id": 0, "embedding_enc": b"dummy"}],
            get_ciphertext=lambda c: c["embedding_enc"],
            account_id=1,
            normalized_query=query_vector.tolist(),
            top_k=0,
        )
        assert scored == []

    def test_no_key_material_returns_empty(self) -> None:
        with patch(
            "airunner_services.utils.crypto.fhe_cache"
            ".fhe_cache_get",
            return_value=None,
        ), patch(
            "airunner_services.database.models.fhe_key_material"
            ".FheKeyMaterial",
        ) as mock_fkm:
            mock_fkm.objects.query.return_value.filter.return_value.first.return_value = None
            scored = fhe_similarity_rank(
                [{"id": 0, "embedding_enc": b"dummy"}],
                get_ciphertext=lambda c: c["embedding_enc"],
                account_id=1,
                normalized_query=[0.1] * EMBEDDING_DIM,
                top_k=10,
            )
        assert scored == []

    def test_null_ciphertext_skipped(
        self, fhe_contexts, query_vector, dek,
    ) -> None:
        public_ctx, secret_ctx = fhe_contexts
        rng = np.random.RandomState(42)
        vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
        vec = l2_normalize(vec.tolist())
        enc = encrypt_embedding(vec, public_ctx)

        candidates = [
            {"id": 0, "embedding_enc": None},
            {"id": 1, "embedding_enc": enc},
        ]

        mock_fkm, _mock_row = _mock_key_material_and_dek(
            secret_ctx, dek,
        )
        with patch(
            "airunner_services.utils.crypto.fhe_cache"
            ".fhe_cache_get",
            return_value=None,
        ), patch(
            "airunner_services.database.models.fhe_key_material"
            ".FheKeyMaterial",
            mock_fkm,
        ), patch(
            "airunner_services.utils.crypto.dek_cache.get_user_dek",
            return_value=dek,
        ):
            scored = fhe_similarity_rank(
                candidates,
                get_ciphertext=lambda c: c["embedding_enc"],
                account_id=1,
                normalized_query=query_vector.tolist(),
                top_k=5,
            )

        assert len(scored) == 1
        assert scored[0][0]["id"] == 1


# ── FHE_CANDIDATE_CAP ────────────────────────────────────────────


class TestCandidateCapShared:
    """FHE_CANDIDATE_CAP is importable from the shared module."""

    def test_cap_from_shared_module(self) -> None:
        assert FHE_CANDIDATE_CAP == 100
        assert isinstance(FHE_CANDIDATE_CAP, int)

    def test_cap_from_crypto_init(self) -> None:
        from airunner_services.utils.crypto import FHE_CANDIDATE_CAP
        assert FHE_CANDIDATE_CAP == 100
