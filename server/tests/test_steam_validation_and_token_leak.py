"""Tests for round-3 Steam security fixes.

Covers:
- Part 1: _SKIP_VALIDATION must not silently disable just because
          STEAM_STATE_JWT_SECRET is unset; forged identities rejected.
- Part 3: Steam auth-mode redirect uses short-lived handoff code
          (``code=``) instead of real access/refresh tokens in the URL.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


# -- helpers ---------------------------------------------------------------


def _build_test_app() -> FastAPI:
    """Create a FastAPI app with the Steam router mounted."""
    app = FastAPI()
    from projects.uwuchat.server.steam.routes import router as steam_router

    app.include_router(steam_router, prefix="/api/v1/steam")
    return app


# -- Part 1: _SKIP_VALIDATION gating ---------------------------------------


class TestSkipValidationNotTiedToSecret:
    """_SKIP_VALIDATION must not be True without explicit opt-in.

    Tests the module-level default.  In the test environment
    AIRUNNER_ALLOW_STEAM_SKIP_VALIDATION is NOT set and deployment
    mode defaults to ``"development"``, so _SKIP_VALIDATION must be
    False (the old code would have computed True because
    STEAM_STATE_JWT_SECRET was unset — the reset-of-env-var-prefix
    alone no longer disables validation).
    """

    def test_skip_validation_false_by_default(self) -> None:
        """Without explicit opt-in, _SKIP_VALIDATION is False."""
        from projects.uwuchat.server.steam.routes import (
            _SKIP_VALIDATION,
        )

        assert _SKIP_VALIDATION is False, (
            "_SKIP_VALIDATION must be False when "
            "AIRUNNER_ALLOW_STEAM_SKIP_VALIDATION is not set to '1'"
        )


class TestCallbackRejectsForgedIdentity:
    """When validation runs and fails, forged identities are rejected.

    This is the canonical regression test for Part 1: a forged
    ``openid.claimed_id`` must be rejected, not silently accepted.
    """

    def test_validation_failure_rejects_callback(self) -> None:
        """validate_openid returning False → error redirect."""
        import projects.uwuchat.server.steam.routes as steam_routes

        app = _build_test_app()
        client = TestClient(app)

        # Force _SKIP_VALIDATION to False (default) and mock
        # validate_openid to simulate a Steam rejection.
        with patch.object(
            steam_routes, "_SKIP_VALIDATION", False,
        ), patch.object(
            steam_routes,
            "_decode_state_jwt",
            return_value=(0, "auth", ""),
        ), patch.object(
            steam_routes,
            "validate_openid",
            return_value=False,
        ):
            resp = client.get(
                "/api/v1/steam/auth/callback",
                params={
                    "state": "fake-state-jwt",
                    "openid.mode": "id_res",
                    "openid.claimed_id": (
                        "https://steamcommunity.com/"
                        "openid/id/76561198000000000"
                    ),
                },
                follow_redirects=False,
            )

        # Must reject — either a 302 to an error URL or an error
        # status code.
        assert resp.status_code in (302, 400, 401, 403), (
            f"Expected rejection status, got {resp.status_code}"
        )
        if resp.status_code == 302:
            location = resp.headers.get("location", "")
            assert (
                "error=steam_auth_failed" in location
                or "steam_error=validation_failed" in location
            ), (
                "Expected error redirect, got location: "
                f"{location}"
            )


# -- Part 3: token leak ----------------------------------------------------


class TestSteamRedirectUsesHandoffCode:
    """Steam auth-mode redirect must use ``code=``, not real tokens.

    This is the canonical regression test for Part 3: the redirect
    must contain a short-lived handoff code and must NOT contain
    ``access_token=`` or ``refresh_token=`` in the query string.
    """

    def test_redirect_contains_code_not_tokens(self) -> None:
        """The redirect URL has ``code=`` and no ``access_token=``."""
        import projects.uwuchat.server.steam.routes as steam_routes

        app = _build_test_app()
        client = TestClient(app)

        # Mock the entire auth-mode path: state decode → OpenID skip
        # → extract_steam_id → DB lookup (existing account) →
        # handoff code redirect.
        with patch.object(
            steam_routes, "_SKIP_VALIDATION", True,
        ), patch.object(
            steam_routes,
            "_decode_state_jwt",
            return_value=(0, "auth", ""),
        ), patch.object(
            steam_routes,
            "extract_steam_id",
            return_value="76561198000000000",
        ), patch(
            "airunner_services.database.session.public_session_scope",
        ) as mock_session_ctx, patch(
            "extensions.auth.server.jwt.create_oauth_handoff_token",
            return_value="test-handoff-code-12345",
        ):
            # Mock the DB session to return an existing account.
            mock_session = MagicMock()
            mock_session_ctx.return_value.__enter__.return_value = (
                mock_session
            )

            mock_account = MagicMock()
            mock_account.id = 42
            mock_account.steam_id = "76561198000000000"
            mock_account.tenant_schema = "tenant_abc"
            mock_account.token_version = 1
            mock_account.deleted = False
            mock_session.query.return_value.filter.return_value.first.return_value = (
                mock_account
            )

            resp = client.get(
                "/api/v1/steam/auth/callback",
                params={
                    "state": "fake-state-jwt",
                    "openid.mode": "id_res",
                    "openid.claimed_id": (
                        "https://steamcommunity.com/openid/"
                        "id/76561198000000000"
                    ),
                },
                follow_redirects=False,
            )

        assert resp.status_code == 302, (
            f"Expected 302 redirect, got {resp.status_code}"
        )
        location = resp.headers.get("location", "")

        # Must contain the handoff code.
        assert "code=test-handoff-code-12345" in location, (
            f"Expected 'code=test-handoff-code-12345' in redirect, "
            f"got: {location}"
        )

        # Must NOT contain real long-lived tokens.
        assert "access_token=" not in location, (
            f"Redirect must not contain access_token: {location}"
        )
        assert "refresh_token=" not in location, (
            f"Redirect must not contain refresh_token: {location}"
        )
