"""CKKS homomorphic encryption helpers for embedding vectors.

Uses TenSEAL (wraps Microsoft SEAL) to provide CPU-only CKKS
operations. The module handles:

* Context generation sized for EMBEDDING_DIM (1024) with CKKS
  parameters that support one ciphertext×plaintext dot-product.
* L2 normalization of embedding vectors before encryption.
* Encryption of plaintext vectors into serialized ciphertext bytes.
* Deserialization and dot-product of ciphertext with plaintext query.
* Scalar decryption of dot-product results.

Parameter rationale
--------------------

:data:`POLY_MODULUS_DEGREE` = 8192
    Gives 4096 CKKS slots.  1024-dimensional embeddings fit
    comfortably with room for the internal rescaling that occurs
    during dot-product accumulation (the ciphertext rotates and
    adds across slots, which benefits from extra slot headroom).

:data:`COEFF_MOD_BIT_SIZES` = [60, 40, 40, 60]
    Provides ~200 bits of total modulus, supporting one
    ciphertext×plaintext multiplication followed by the ~log₂(N)
    rotations needed to sum slots into a scalar.  The 60-bit
    "special primes" at the ends provide noise margin; the two
    40-bit middle primes are consumed by the multiply.

:data:`GLOBAL_SCALE` = 2**40
    Matches the 40-bit middle primes.  After one multiply the
    scale squares to 2⁸⁰, then rescaling (mod-switch down by one
    40-bit prime) brings it back to 2⁴⁰ for output.

These parameters were chosen following TenSEAL's recommended
defaults for CKKS.  For 1024-slot vectors with a single
ciphertext×plaintext dot-product, 8192/200-bit is conservative
and works reliably on CPU-only deployments.

"""
from __future__ import annotations

from typing import Optional
import numpy as np


# TenSEAL is imported lazily in the helper functions below so that
# module-level imports succeed even before the package is installed.
# The first call to any public function will trigger the import.


# ── CKKS parameters (see module docstring for rationale) ─────────

POLY_MODULUS_DEGREE: int = 8192
"""Polynomial modulus degree — must be a power of 2."""

COEFF_MOD_BIT_SIZES: list[int] = [60, 40, 40, 60]
"""Bit sizes for the coefficient modulus chain."""

GLOBAL_SCALE: int = 2**40
"""Default scale for encoding floating-point values into CKKS."""

EMBEDDING_DIM: int = 1024
"""Expected embedding vector dimension.  Must match
``document_chunk.EMBEDDING_DIM``."""


# ── Lazy import ──────────────────────────────────────────────────

_ts = None


def _tenseal():
    """Return the ``tenseal`` module, importing it on first access."""
    global _ts
    if _ts is None:
        import tenseal as ts
        _ts = ts
    return _ts


# ── Context ──────────────────────────────────────────────────────


def generate_fhe_context() -> tuple:
    """Create a fresh TenSEAL CKKS context pair.

    Returns:
        ``(public_context, secret_context)`` where *public_context*
        is serializable (contains Galois + relin keys but NOT the
        secret key) and *secret_context* holds the full secret key.

    The public context is **not sensitive** — it can be stored in
    the database.  The secret context must be wrapped with the
    account DEK before storage (see :mod:`.fhe_key_wrap`).
    """
    ts = _tenseal()
    context = ts.context(
        ts.SCHEME_TYPE.CKKS,
        poly_modulus_degree=POLY_MODULUS_DEGREE,
        coeff_mod_bit_sizes=COEFF_MOD_BIT_SIZES,
    )
    context.global_scale = GLOBAL_SCALE
    context.generate_galois_keys()
    context.generate_relin_keys()

    # Make the context public (strip secret key) for the
    # serializable version we store in the DB.
    public_context = context.copy()
    public_context.make_context_public()

    return public_context, context


def public_context_from_bytes(data: bytes):
    """Deserialize a public (secret-key-free) TenSEAL context."""
    ts = _tenseal()
    return ts.context_from(data)


def secret_context_from_bytes(data: bytes):
    """Deserialize a full TenSEAL context including the secret key.

    This should only be used after unwrapping the stored secret
    context with the account DEK.
    """
    ts = _tenseal()
    return ts.context_from(data)


# ── Vector helpers ───────────────────────────────────────────────


def l2_normalize(vec: list[float]) -> np.ndarray:
    """L2-normalize *vec* in-place (returns a new numpy array).

    Cosine similarity of two unit vectors equals their dot product,
    so a plain dot product on normalized vectors is a correct
    drop-in replacement for pgvector ``cosine_distance``.

    Returns a zero vector when the input norm is zero (empty embedding
    or all-zeros — should not happen in practice but handled safely).
    """
    arr = np.array(vec, dtype=np.float64)
    norm = np.linalg.norm(arr)
    if norm < 1e-12:
        return arr
    return arr / norm


# ── Encryption ───────────────────────────────────────────────────


def encrypt_embedding(
    normalized_vector: np.ndarray,
    public_context,
) -> bytes:
    """Encrypt an L2-normalized embedding vector into ciphertext bytes.

    Args:
        normalized_vector: Already L2-normalized numpy array of
            shape ``(EMBEDDING_DIM,)``.
        public_context: A TenSEAL context with the secret key
            stripped (as returned by :func:`generate_fhe_context`).

    Returns:
        Serialized ``CKKSVector`` ciphertext bytes suitable for
        storage in ``KnowledgeFact.embedding_enc``.
    """
    ts = _tenseal()
    # TenSEAL CKKSVector encrypts the input as a single ciphertext.
    ckks_vec = ts.CKKSVector(
        public_context,
        normalized_vector.tolist(),
    )
    return ckks_vec.serialize()


def deserialize_ciphertext(
    data: bytes,
    secret_context,
):
    """Deserialize ciphertext bytes back into a CKKSVector.

    Args:
        data: Raw bytes from ``KnowledgeFact.embedding_enc``.
        secret_context: Full TenSEAL context (with secret key),
            obtained from the FHE cache after DEK unwrap.

    Returns:
        A ``tenseal.CKKSVector`` ready for dot-product operations.
    """
    ts = _tenseal()
    return ts.CKKSVector.load(secret_context, data)


# ── Search operations ────────────────────────────────────────────


def compute_encrypted_dot_product(
    ciphertext_vec,
    normalized_query: np.ndarray,
) -> bytes:
    """Compute dot(ciphertext, plaintext) → encrypted scalar.

    Uses TenSEAL's ``CKKSVector.dot()`` which performs
    ciphertext×plaintext element-wise multiplication followed by
    summing across slots.  The query vector is plaintext (never
    persisted, freshly computed per request).

    Args:
        ciphertext_vec: Deserialized ``CKKSVector``.
        normalized_query: L2-normalized numpy query vector.

    Returns:
        Encrypted scalar as bytes — decrypt with
        :func:`decrypt_scalar`.
    """
    # TenSEAL CKKSVector.dot takes a plaintext list and returns
    # a new CKKSVector containing the encrypted scalar in each slot.
    result = ciphertext_vec.dot(normalized_query.tolist())
    return result.serialize()


def decrypt_scalar(encrypted_scalar: bytes, secret_context) -> float:
    """Decrypt a dot-product result back to a Python float.

    Args:
        encrypted_scalar: Serialized CKKSVector containing the
            encrypted dot-product scalar.
        secret_context: Full TenSEAL context with secret key.

    Returns:
        The decrypted cosine-similarity score as a float.
    """
    ts = _tenseal()
    vec = ts.CKKSVector.load(secret_context, encrypted_scalar)
    # The decrypted result is a list with the scalar replicated
    # across all slots.  Return the first element.
    decrypted = vec.decrypt()
    if decrypted is None:
        return 0.0
    return float(decrypted[0])


def decrypt_embedding(
    data: bytes,
    secret_context,
) -> Optional[list[float]]:
    """Decrypt an embedding ciphertext back to a plaintext vector.

    Used only for benchmarks and tests — never in the production
    search path.

    Args:
        data: Serialized CKKSVector ciphertext.
        secret_context: Full TenSEAL context with secret key.

    Returns:
        Decrypted vector as list[float], or None on failure.
    """
    ts = _tenseal()
    try:
        vec = ts.CKKSVector.load(secret_context, data)
        result = vec.decrypt()
        if result is None:
            return None
        return [float(x) for x in result]
    except Exception:
        return None


def check_fhe_available() -> None:
    """Verify TenSEAL is importable at startup; log CRITICAL if not.

    FHE encrypted-embedding search is core architecture — embedding_enc
    columns are written unconditionally whenever FHE key material exists,
    with no feature-flag gate.  A missing TenSEAL library means every
    ``embedding_enc`` column is empty and every FHE search path silently
    falls back to plaintext scoring.  This check makes that
    misconfiguration impossible to miss in logs/monitoring.

    The server is NOT prevented from booting — the FHE ranking path has
    a safe degrade (skip FHE and fall back to plaintext scoring).

    Call this once at application startup, after logging is configured.
    """
    import logging as _logging

    try:
        import tenseal
    except ImportError:
        _logging.getLogger(__name__).critical(
            "The TenSEAL library is not installed in this environment. "
            "FHE encrypted-embedding search is non-functional — all "
            "embedding_enc columns are empty and every FHE search path "
            "will silently fall back to plaintext scoring. Rebuild the "
            "server image (docker/Dockerfile) to include the tenseal "
            "dependency declared in server/package_metadata.py."
        )
        return

    _logging.getLogger(__name__).info(
        "TenSEAL %s loaded — FHE encrypted-embedding search is available",
        tenseal.__version__,
    )


__all__ = [
    "COEFF_MOD_BIT_SIZES",
    "EMBEDDING_DIM",
    "GLOBAL_SCALE",
    "POLY_MODULUS_DEGREE",
    "check_fhe_available",
    "compute_encrypted_dot_product",
    "decrypt_embedding",
    "decrypt_scalar",
    "deserialize_ciphertext",
    "encrypt_embedding",
    "generate_fhe_context",
    "l2_normalize",
    "public_context_from_bytes",
    "secret_context_from_bytes",
]
