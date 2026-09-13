"""Unit tests for JWT token creation and validation."""

from __future__ import annotations

import time
from unittest.mock import patch

from extensions.auth.server.jwt import (
    create_access_token,
    create_refresh_token,
    create_verification_token,
    decode_token,
)


def test_access_token_round_trip():
    """Create → decode preserves all claims."""
    token = create_access_token(42, "tenant_abc123", token_version=1)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["tenant"] == "tenant_abc123"
    assert payload["ver"] == 1
    assert payload["type"] == "access"


def test_refresh_token_round_trip():
    """Refresh tokens have the correct type and claims."""
    token = create_refresh_token(99, token_version=3)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "99"
    assert payload["ver"] == 3
    assert payload["type"] == "refresh"


def test_verification_token_round_trip():
    """Verification token has type 'verify'."""
    token = create_verification_token(7)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["type"] == "verify"


def test_decode_invalid_token_returns_none():
    """A garbage string is not a valid JWT."""
    assert decode_token("not-a-jwt") is None


def test_decode_empty_token_returns_none():
    """An empty string is not a valid JWT."""
    assert decode_token("") is None


def test_tampered_signature_rejected():
    """A token with a modified signature is rejected."""
    token = create_access_token(1, "tenant_xyz")
    # Replace the last 8 chars of the signature with clearly invalid chars;
    # a single-char flip can occasionally still produce valid padding.
    parts = token.rsplit(".", 1)
    tampered = parts[0] + "." + parts[1][:-8] + "DEADBEEF"
    assert decode_token(tampered) is None


def test_tampered_payload_rejected():
    """A token with a modified payload is rejected."""
    token = create_access_token(1, "tenant_xyz")
    header, payload_b64, sig = token.split(".")
    import base64
    import json

    payload = json.loads(
        base64.urlsafe_b64decode(payload_b64 + "===")
    )
    payload["sub"] = "999"  # tampered account ID
    new_payload_b64 = (
        base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        )
        .rstrip(b"=")
        .decode()
    )
    tampered = f"{header}.{new_payload_b64}.{sig}"
    assert decode_token(tampered) is None


def test_access_token_expiry():
    """An expired access token is rejected."""
    with patch(
        "extensions.auth.server.jwt._ACCESS_TOKEN_TTL", -1
    ):
        token = create_access_token(1, "tenant_xyz")
    payload = decode_token(token)
    assert payload is None, "Expired token must return None"


def test_token_issued_for_tenant_a_has_correct_tenant():
    """Access token carries the tenant schema it was issued for."""
    token = create_access_token(5, "tenant_alpha")
    payload = decode_token(token)
    assert payload is not None
    assert payload["tenant"] == "tenant_alpha"
