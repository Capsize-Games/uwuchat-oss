"""Tests for unconditional JWT secret guard.

Part 4 (MEDIUM) — The dev-secret fallback must require an explicit
opt-in flag (``AIRUNNER_ALLOW_DEV_JWT_SECRET=1``) rather than
silently falling back when ``AIRUNNER_DEPLOYMENT_MODE`` is unset or
misspelled.
"""

from __future__ import annotations

import importlib


def _reload_jwt_with_env(
    monkeypatch,
    *,
    jwt_secret: str | None = None,
    allow_dev: str | None = None,
) -> bool:
    """Re-import jwt.py with controlled env and return True if it
    succeeded (no RuntimeError).

    Uses ``importlib.reload`` on the specific module rather than
    evicting all ``extensions.auth.server`` modules from
    ``sys.modules``.  The old approach of wholesale pops caused
    cross-test pollution: later tests re-importing
    ``extensions.auth.server.models.Account`` would crash with
    ``Table 'accounts' is already defined for this MetaData instance``
    because the original table definition survived in SQLAlchemy's
    declarative registry.
    """
    monkeypatch.delenv("AIRUNNER_JWT_SECRET", raising=False)
    monkeypatch.delenv("AIRUNNER_ALLOW_DEV_JWT_SECRET", raising=False)
    if jwt_secret is not None:
        monkeypatch.setenv("AIRUNNER_JWT_SECRET", jwt_secret)
    if allow_dev is not None:
        monkeypatch.setenv("AIRUNNER_ALLOW_DEV_JWT_SECRET", allow_dev)

    try:
        import extensions.auth.server.jwt as jwt_mod
        importlib.reload(jwt_mod)
        return True
    except RuntimeError:
        return False


class TestJwtSecretGuard:
    """Module-level guard raises on unsafe configurations."""

    def test_missing_secret_raises(self, monkeypatch) -> None:
        """Without a secret and without opt-in, import must fail."""
        ok = _reload_jwt_with_env(monkeypatch, jwt_secret="")
        assert not ok, (
            "Import must fail when AIRUNNER_JWT_SECRET is unset "
            "and AIRUNNER_ALLOW_DEV_JWT_SECRET is not '1'"
        )

    def test_dev_fallback_raises_without_opt_in(
        self, monkeypatch,
    ) -> None:
        """The known dev fallback value also raises without opt-in."""
        ok = _reload_jwt_with_env(
            monkeypatch,
            jwt_secret="dev-jwt-secret-do-not-use-in-production",
        )
        assert not ok, (
            "Import must fail when AIRUNNER_JWT_SECRET equals the "
            "hardcoded dev fallback"
        )

    def test_opt_in_allows_dev_fallback(self, monkeypatch) -> None:
        """Explicit opt-in permits the dev fallback for local dev."""
        ok = _reload_jwt_with_env(
            monkeypatch,
            jwt_secret="dev-jwt-secret-do-not-use-in-production",
            allow_dev="1",
        )
        assert ok, (
            "Import must succeed when AIRUNNER_ALLOW_DEV_JWT_SECRET=1"
        )

    def test_custom_secret_works(self, monkeypatch) -> None:
        """A strong custom secret works without the opt-in flag."""
        ok = _reload_jwt_with_env(
            monkeypatch,
            jwt_secret="a-strong-random-secret-value-here-ok",
        )
        assert ok, (
            "Import must succeed with a custom non-fallback secret"
        )
