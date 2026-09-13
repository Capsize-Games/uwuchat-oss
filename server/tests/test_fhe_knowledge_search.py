"""Tests for FHE-encrypted knowledge embedding search.

Covers:
- encrypt/decrypt round-trip correctness (CKKS → bytes → CKKS → vector).
- Dot product of normalized vectors matches plaintext numpy cosine
  similarity within CKKS floating-point tolerance.
- Fail-closed behaviour when no DEK/context is available (write path
  raises, does not silently store plaintext).
- Candidate-cap logic in the search path.
- Embedding ciphertext does not reveal anything about the plaintext
  fact without the secret key.
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)
from airunner_services.utils.crypto.fhe_helpers import (
    EMBEDDING_DIM,
    compute_encrypted_dot_product,
    decrypt_embedding,
    decrypt_scalar,
    deserialize_ciphertext,
    encrypt_embedding,
    generate_fhe_context,
    l2_normalize,
)
from airunner_services.utils.crypto.fhe_key_wrap import (
    unwrap_secret_context,
    wrap_secret_context,
)
from airunner_services.utils.crypto.fhe_cache import (
    fhe_cache_evict,
    fhe_cache_get,
    fhe_cache_set,
)

# Tolerance for CKKS floating-point comparison.  CKKS is an
# approximate scheme — decrypted values have ~10–12 significant
# decimal digits.  1e-4 is generous enough to absorb encoding noise
# while still catching algorithmic errors (e.g. forgetting to
# normalize before dot product).
CKKS_TOLERANCE: float = 1e-4
"""Acceptable error for CKKS round-trip and dot-product comparisons."""


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def fhe_contexts():
    """Generate a fresh CKKS context pair for each test."""
    public_ctx, secret_ctx = generate_fhe_context()
    return public_ctx, secret_ctx


@pytest.fixture
def random_embedding() -> np.ndarray:
    """Return a random 1024-dim vector, L2-normalized."""
    rng = np.random.RandomState(42)
    vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
    return l2_normalize(vec.tolist())


@pytest.fixture
def query_vector() -> np.ndarray:
    """Return a different random normalized query vector."""
    rng = np.random.RandomState(99)
    vec = rng.randn(EMBEDDING_DIM).astype(np.float64)
    return l2_normalize(vec.tolist())


# ── Round-trip correctness ───────────────────────────────────────


class TestEncryptDecryptRoundTrip:
    """Encrypt → serialize → deserialize → decrypt should recover the
    original vector within CKKS tolerance."""

    def test_round_trip_preserves_vector(
        self, fhe_contexts, random_embedding,
    ) -> None:
        public_ctx, secret_ctx = fhe_contexts
        enc_bytes = encrypt_embedding(random_embedding, public_ctx)
        decrypted = decrypt_embedding(enc_bytes, secret_ctx)
        assert decrypted is not None
        assert len(decrypted) == EMBEDDING_DIM
        for a, b in zip(random_embedding, decrypted):
            assert math.isclose(a, b, abs_tol=CKKS_TOLERANCE)

    def test_round_trip_fails_without_secret_key(
        self, fhe_contexts, random_embedding,
    ) -> None:
        public_ctx, _secret_ctx = fhe_contexts
        enc_bytes = encrypt_embedding(random_embedding, public_ctx)
        # Decrypt with public context should fail.
        result = decrypt_embedding(enc_bytes, public_ctx)
        assert result is None

    def test_empty_embedding_encrypts_zero_vector(
        self, fhe_contexts,
    ) -> None:
        public_ctx, secret_ctx = fhe_contexts
        zero_vec = np.zeros(EMBEDDING_DIM, dtype=np.float64)
        enc_bytes = encrypt_embedding(zero_vec, public_ctx)
        decrypted = decrypt_embedding(enc_bytes, secret_ctx)
        assert decrypted is not None
        for val in decrypted:
            assert abs(val) < CKKS_TOLERANCE * 10


# ── Dot-product matches cosine similarity ────────────────────────


class TestDotProductMatchesCosine:
    """FHE dot product of two normalized vectors must equal plaintext
    numpy dot product (which equals cosine similarity for unit vectors)
    within CKKS tolerance."""

    def test_dot_product_equals_cosine(
        self, fhe_contexts, random_embedding, query_vector,
    ) -> None:
        public_ctx, secret_ctx = fhe_contexts

        # Plaintext cosine similarity (dot product of unit vectors).
        expected = float(np.dot(random_embedding, query_vector))

        # FHE path.
        enc_bytes = encrypt_embedding(random_embedding, public_ctx)
        ct_vec = deserialize_ciphertext(enc_bytes, secret_ctx)
        enc_scalar = compute_encrypted_dot_product(ct_vec, query_vector)
        score = decrypt_scalar(enc_scalar, secret_ctx)

        assert math.isclose(expected, score, abs_tol=CKKS_TOLERANCE)

    def test_identical_vectors_score_near_one(
        self, fhe_contexts, random_embedding,
    ) -> None:
        public_ctx, secret_ctx = fhe_contexts
        enc_bytes = encrypt_embedding(random_embedding, public_ctx)
        ct_vec = deserialize_ciphertext(enc_bytes, secret_ctx)
        enc_scalar = compute_encrypted_dot_product(
            ct_vec, random_embedding,
        )
        score = decrypt_scalar(enc_scalar, secret_ctx)
        assert math.isclose(score, 1.0, abs_tol=CKKS_TOLERANCE)


# ── Normalization ────────────────────────────────────────────────


class TestL2Normalization:
    """l2_normalize produces unit vectors."""

    def test_unit_norm(self) -> None:
        vec = np.array([3.0, 4.0, 0.0], dtype=np.float64)
        result = l2_normalize(vec.tolist())
        norm = float(np.linalg.norm(result))
        assert math.isclose(norm, 1.0, abs_tol=1e-12)

    def test_zero_vector_returns_zero(self) -> None:
        vec = np.zeros(10, dtype=np.float64)
        result = l2_normalize(vec.tolist())
        assert np.allclose(result, 0.0)

    def test_negative_values(self) -> None:
        vec = np.array([-1.0, -2.0, -3.0], dtype=np.float64)
        result = l2_normalize(vec.tolist())
        norm = float(np.linalg.norm(result))
        assert math.isclose(norm, 1.0, abs_tol=1e-12)


# ── DEK wrapping ─────────────────────────────────────────────────


class TestDekWrapping:
    """Secret contexts survive wrap/unwrap with a valid DEK."""

    def test_wrap_unwrap_round_trip(self, fhe_contexts) -> None:
        from cryptography.fernet import Fernet

        public_ctx, secret_ctx = fhe_contexts
        dek = Fernet.generate_key()
        wrapped = wrap_secret_context(secret_ctx, dek)
        assert len(wrapped) > 0

        # Unwrap and verify the context can decrypt (but NOT encrypt —
        # the unwrapped context lacks a public key; encryption happens
        # with the public context, matching the real write path).
        unwrapped = unwrap_secret_context(wrapped, dek)
        vec = l2_normalize([0.1] * EMBEDDING_DIM)
        enc = encrypt_embedding(vec, public_ctx)
        dec = decrypt_embedding(enc, unwrapped)
        assert dec is not None
        for a, b in zip(vec, dec):
            assert math.isclose(a, b, abs_tol=CKKS_TOLERANCE)

    def test_wrap_fails_with_empty_dek(self, fhe_contexts) -> None:
        _public_ctx, secret_ctx = fhe_contexts
        with pytest.raises(DataEncryptionError):
            wrap_secret_context(secret_ctx, b"")

    def test_unwrap_fails_with_wrong_dek(self, fhe_contexts) -> None:
        from cryptography.fernet import Fernet

        _public_ctx, secret_ctx = fhe_contexts
        dek = Fernet.generate_key()
        wrapped = wrap_secret_context(secret_ctx, dek)
        wrong_dek = Fernet.generate_key()
        with pytest.raises(DataEncryptionError):
            unwrap_secret_context(wrapped, wrong_dek)

    def test_unwrap_rejects_short_data(self, fhe_contexts) -> None:
        from cryptography.fernet import Fernet

        _public_ctx, _secret_ctx = fhe_contexts
        dek = Fernet.generate_key()
        with pytest.raises(DataEncryptionError):
            unwrap_secret_context(b"short", dek)

    def test_wrap_unwrap_dot_product_path(
        self, fhe_contexts, random_embedding, query_vector,
    ) -> None:
        """Full production path: wrap → unwrap → deserialize → dot
        → decrypt.  This is the regression guard for
        save_galois_keys=True/save_relin_keys=True — without those
        flags the unwrapped context cannot perform the rotation-based
        summation CKKSVector.dot() requires."""
        from cryptography.fernet import Fernet

        public_ctx, secret_ctx = fhe_contexts
        dek = Fernet.generate_key()

        # Encrypt with the public context (write path).
        enc_bytes = encrypt_embedding(random_embedding, public_ctx)

        # Wrap the secret context (storage path).
        wrapped = wrap_secret_context(secret_ctx, dek)

        # Unwrap it (read path — this is what the search path does).
        unwrapped = unwrap_secret_context(wrapped, dek)

        # Use the unwrapped context for the full dot-product pipeline.
        ct_vec = deserialize_ciphertext(enc_bytes, unwrapped)
        enc_scalar = compute_encrypted_dot_product(ct_vec, query_vector)
        score = decrypt_scalar(enc_scalar, unwrapped)

        expected = float(np.dot(random_embedding, query_vector))
        assert math.isclose(expected, score, abs_tol=CKKS_TOLERANCE)


# ── Ciphertext does not leak plaintext ───────────────────────────


class TestCiphertextDoesNotLeakPlaintext:
    """embedding_enc bytes must not reveal the plaintext fact string
    or its embedding values without the secret key."""

    def test_ciphertext_not_substring_of_plaintext(
        self, fhe_contexts, random_embedding,
    ) -> None:
        public_ctx, _secret_ctx = fhe_contexts
        enc_bytes = encrypt_embedding(random_embedding, public_ctx)

        # The ciphertext should not contain any plaintext float as
        # a byte pattern.
        for val in random_embedding[:10]:
            float_bytes = np.float64(val).tobytes()
            assert float_bytes not in enc_bytes, (
                "Ciphertext leaks plaintext float value"
            )

    def test_ciphertext_is_not_valid_raw_vector_without_key(
        self, fhe_contexts, random_embedding,
    ) -> None:
        public_ctx, _secret_ctx = fhe_contexts
        enc_bytes = encrypt_embedding(random_embedding, public_ctx)

        # Without the secret key, the ciphertext should not decode
        # as 1024 valid float64 values (8192 bytes).
        assert len(enc_bytes) != EMBEDDING_DIM * 8, (
            "Ciphertext size matches raw float64 vector — "
            "data may be stored in plaintext"
        )

    def test_ciphertext_differs_for_different_inputs(
        self, fhe_contexts,
    ) -> None:
        public_ctx, _secret_ctx = fhe_contexts
        a = l2_normalize([0.1] * EMBEDDING_DIM)
        b = l2_normalize([0.5] * EMBEDDING_DIM)
        enc_a = encrypt_embedding(a, public_ctx)
        enc_b = encrypt_embedding(b, public_ctx)
        assert enc_a != enc_b, (
            "Different embeddings produced identical ciphertexts"
        )


# ── Cache eviction ───────────────────────────────────────────────


class TestFheCache:
    """Cache get/set/evict behaves as expected."""

    def test_set_and_get(self, fhe_contexts) -> None:
        _, secret_ctx = fhe_contexts
        fhe_cache_set(42, secret_ctx)
        result = fhe_cache_get(42)
        assert result is not None
        fhe_cache_evict(42)
        assert fhe_cache_get(42) is None

    def test_evict_nonexistent_no_error(self) -> None:
        fhe_cache_evict(99999)
        assert fhe_cache_get(99999) is None


# ── Fail-closed on write path ────────────────────────────────────


class TestFailClosedOnWrite:
    """Write path raises when no DEK is available for FHE encryption."""

    def test_get_or_create_public_context_raises_no_dek(self) -> None:
        # _get_or_create_public_context imports FheKeyMaterial lazily
        # from airunner_services.database.models.fhe_key_material,
        # so the mock must target that source module.
        with patch(
            "airunner_services.knowledge_crud.get_user_dek",
            return_value=None,
        ), patch(
            "airunner_services.database.models.fhe_key_material"
            ".FheKeyMaterial.objects.transaction",
        ) as mock_tx:
            mock_tx_ctx = MagicMock()
            mock_tx.return_value.__enter__.return_value = mock_tx_ctx
            mock_tx_ctx.query.return_value.filter.return_value.first.return_value = None

            from airunner_services.knowledge_crud import (
                _get_or_create_public_context,
            )

            with pytest.raises(DataEncryptionError):
                _get_or_create_public_context(1)


# ── Candidate cap constant ───────────────────────────────────────


class TestCandidateCap:
    """FHE_CANDIDATE_CAP is a reasonable value."""

    def test_cap_is_positive(self) -> None:
        from airunner_services.knowledge_rag import FHE_CANDIDATE_CAP
        assert FHE_CANDIDATE_CAP > 0

    def test_cap_is_named_constant(self) -> None:
        from airunner_services.knowledge_rag import FHE_CANDIDATE_CAP
        assert isinstance(FHE_CANDIDATE_CAP, int)
        assert FHE_CANDIDATE_CAP == 100
