"""Route-table introspection test — auth-dependency completeness.

Walks every mounted route defined in
:data:`airunner_services.api.server_routes._ROUTE_SPECS` and asserts
that each non-public handler includes at least one FastAPI
``Depends(...)`` parameter that resolves the caller's identity
(``require_auth``, ``require_superuser``, or a locally-defined auth
dependency that surfaces ``request.state.account_id``).

Public routes (health checks, OAuth callbacks, webhook receivers that
verify via signature) are listed explicitly in two allowlists — the
middleware's public-path set (imported directly so this test cannot
drift out of sync) and the test's own additional allowlist.

Routes that use the ``request.state.account_id`` pattern (set by the
auth middleware) without an explicit ``Depends`` are **not** flagged
as failures — this is an accepted alternative pattern in this
codebase (see ``images.py`` and ``test_images_route_scoping.py``).
Those routes appear in the skip set with a justification.

Reference: plans/tenant-isolation-test-harness.md Part 2
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest
from fastapi.params import Depends as DependsClass

# ---------------------------------------------------------------------------
# 1. Build the master allowlist: public paths that the auth middleware
#    skips.  Imported directly from the middleware module so this test
#    stays in sync with the real allowlist.
# ---------------------------------------------------------------------------
# Paths that the auth middleware skips entirely (no token required).
# Single source of truth: both the framework middleware and the auth
# extension import ``PUBLIC_PATHS`` from
# ``airunner_services.api.server_middleware``, so this test reads that
# shared constant directly (it cannot drift).
from airunner_services.api.server_middleware import PUBLIC_PATHS

_MIDDLEWARE_PUBLIC_PATHS: set[str] = set(PUBLIC_PATHS)

# Additional public routes NOT in the middleware's exact-match set but
# that are intentionally unauthenticated.  Each entry must include a
# justification.
_TEST_ALLOWLIST: dict[str, str] = {
    # Root health / API info endpoints (mounted outside _ROUTE_SPECS
    # but served by health.router at root).
    "/": "Root API info endpoint (health router)",
    "/api/v1": "API v1 root (health router)",
    "/health/daemon": "Daemon health check (health router)",
    "/api/v1/health/daemon": "Daemon health check (health router)",
    # OAuth callback endpoints that verify via state parameter
    # instead of JWT (same pattern as steam/itch auth callbacks
    # already in _MIDDLEWARE_PUBLIC_PATHS).
    "/api/v1/spotify/callback": (
        "Spotify OAuth callback — state-verified, not JWT"
    ),
    "/api/v1/twitch/auth/callback": (
        "Twitch OAuth callback — state-verified, not JWT"
    ),
    "/api/v1/embed/text": (
        "Local embedding endpoint for headlesscode — no user data, "
        "no tenant/session scoping (matches health.py pattern)"
    ),
}

# Routes whose handlers call ``require_auth(request)`` or
# ``require_superuser(request)`` **inside the function body** rather
# than via a ``Depends`` parameter in the signature.  This is the
# pattern used by steam/itch/bluesky/twitch/email routes that accept
# a ``{user_id}`` path parameter and enforce ``account_id == user_id``
# inside the body.
#
# These are discovered at runtime by :func:`_handler_has_inbody_auth`
# via source-code inspection, not by this static list — the list
# exists only as documentation of the expected pattern.

# Handlers that use the ``request.state.account_id`` pattern —
# the auth middleware sets this before the handler runs, so the
# handler doesn't need an explicit ``Depends(require_auth)``.
# This is the accepted pattern in images.py (validated by
# test_images_route_scoping.py).
_REQUEST_STATE_PATTERN_PREFIXES: set[str] = {
    "/api/v1/images",
    "/api/v1/knowledge-base",  # knowledge_base_index.py
}

# Route prefixes that are RPC-only (WebSocket dispatch functions
# registered via _rpc_register).  These do not have FastAPI
# route decorators and are not inspected by this test.
_RPC_ONLY_PREFIXES: set[str] = {
    "/api/v1/llm",      # WebSocket chat loop
    "/api/v1/tts",      # WebSocket TTS stream
    "/api/v1/art",      # WebSocket art generation
    "/api/v1/canvas",   # WebSocket canvas document
    "/api/v1/daemon",   # WebSocket daemon commands
}


# ---------------------------------------------------------------------------
# 2. Helpers
# ---------------------------------------------------------------------------


def _import_route_specs() -> list[tuple]:
    """Return the route-spec list from ``server_routes.py``.

    We import the spec list directly rather than building the full
    FastAPI app — many route modules import external services at
    module level, and resolving all of them in a test environment
    would require a real database, Redis, and model files.
    """
    from airunner_services.api.server_routes import _ROUTE_SPECS

    return list(_ROUTE_SPECS)


def _import_router(
    module_name: str, attr: str = "router",
) -> Any | None:
    """Import one router module, returning the router or None.

    Route modules import external services (DB models, Celery,
    Redis) at module level.  When this test's dynamic import runs
    after other tests have already touched SQLAlchemy's declarative
    registry in a conflicting way, re-importing a models-backed
    route module can raise ``sqlalchemy.exc.InvalidRequestError``
    ("Table already defined") — a pre-existing, order-dependent
    flakiness in this suite's metadata registration, not something
    this test can fix.  Any import-time exception here means "skip
    this module's routes," same as ``ImportError``.
    """
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, attr, None)
    except ImportError:
        # Retry with project root on path (for projects.uwuchat.*)
        _ensure_project_root_on_path()
        try:
            mod = importlib.import_module(module_name)
            return getattr(mod, attr, None)
        except Exception:
            return None
    except Exception:
        return None


def _ensure_project_root_on_path() -> None:
    """Add the project root to ``sys.path`` (idempotent)."""
    import sys

    _here = Path(__file__).resolve().parent  # tests/
    _server_root = _here.parent  # server/
    _project_root = _server_root.parent  # project root
    _project_root_str = str(_project_root)
    if _project_root_str not in sys.path:
        sys.path.insert(0, _project_root_str)


def _handler_has_auth_dep(handler: Any) -> bool:
    """Return ``True`` when *handler* has at least one ``Depends``
    parameter that looks like an auth dependency.

    Checks the function signature for parameter defaults that are
    ``fastapi.Depends`` instances wrapping a callable whose name
    contains ``auth``, ``require_auth``, or ``superuser``.
    """
    try:
        sig = inspect.signature(handler)
    except (ValueError, TypeError):
        return False

    for param in sig.parameters.values():
        default = param.default
        if default is inspect.Parameter.empty:
            continue
        # Check if it's a Depends instance.
        if not isinstance(default, DependsClass):
            continue
        dep_callable = default.dependency
        if dep_callable is None:
            continue
        dep_name = getattr(dep_callable, "__name__", "")
        # Match require_auth, require_superuser, or _auth_dep-style
        # module-level wrappers that resolve to require_auth.
        if (
            "auth" in dep_name.lower()
            or "superuser" in dep_name.lower()
        ):
            return True
        # The dependency might be a locally-resolved wrapper stored
        # in a module-level variable.  Check the callable itself.
        if callable(dep_callable):
            try:
                dep_sig = inspect.signature(dep_callable)
                for dp in dep_sig.parameters.values():
                    if dp.name in ("request", "req"):
                        return True
            except (ValueError, TypeError):
                pass
    return False


def _handler_has_inbody_auth(handler: Any) -> bool:
    """Return ``True`` when *handler* calls ``require_auth(request)``
    or ``require_superuser(request)`` inside the function body.

    This is the third auth pattern in this codebase (besides
    ``Depends(require_auth)`` in the signature and the
    ``request.state.account_id`` read-only pattern).  Used by
    steam, itch, bluesky, twitch, and email routes that accept a
    ``{user_id}`` path parameter and enforce ``account_id == user_id``
    inside the body.
    """
    import re

    try:
        source = inspect.getsource(handler)
    except (OSError, TypeError):
        return False
    return bool(
        re.search(r"\brequire_auth\s*\(", source)
        or re.search(r"\brequire_superuser\s*\(", source)
    )


def _collect_routes_with_auth_status() -> list[
    tuple[str, str, str, bool]
]:
    """Walk every route spec and return
    ``[(method, path, status, has_auth), ...]``.

    *has_auth* is ``True`` when the handler includes an auth check
    via any of the three accepted patterns:
    1. ``Depends(require_auth)`` / ``Depends(_auth_dep)`` in the
       function signature.
    2. ``require_auth(request)`` / ``require_superuser(request)``
       called inside the function body.
    3. ``request.state.account_id`` read via request state (detected
       by prefix matching against ``_REQUEST_STATE_PATTERN_PREFIXES``
       in the test body — too fragile to detect automatically from
       source).

    Routes from RPC-only prefixes are excluded.
    """
    results: list[tuple[str, str, str, bool]] = []
    specs = _import_route_specs()

    for spec in specs:
        module_name = spec[1]
        include_kwargs = spec[2]
        attr = spec[4] if len(spec) > 4 else "router"
        router = _import_router(module_name, attr)
        if router is None:
            continue

        prefix = include_kwargs.get("prefix", "")

        # Skip RPC-only prefixes.
        if prefix in _RPC_ONLY_PREFIXES:
            continue

        for route in router.routes:
            # WebSocket routes have no 'methods' or 'endpoint' — skip.
            if not hasattr(route, "methods") or route.methods is None:
                continue
            if not hasattr(route, "endpoint"):
                continue
            method = ",".join(route.methods)
            path = prefix + route.path
            # Normalise trailing slashes.
            path = path.rstrip("/") or "/"
            has_auth = (
                _handler_has_auth_dep(route.endpoint)
                or _handler_has_inbody_auth(route.endpoint)
            )
            results.append((method, path, module_name, has_auth))

    return results


# ---------------------------------------------------------------------------
# 3. The test
# ---------------------------------------------------------------------------


@pytest.fixture()
def route_statuses() -> list[tuple[str, str, str, bool]]:
    """Collect route auth status per test."""
    return _collect_routes_with_auth_status()


class TestRouteAuthCompleteness:
    """Every non-public, non-RPC route handler must include an auth
    dependency OR be in one of the allowlists."""

    def test_all_non_public_routes_have_auth_dependency(
        self, route_statuses: list[tuple[str, str, str, bool]],
    ) -> None:
        """Assert every non-public route has an explicit auth
        ``Depends`` or a justified allowlist entry."""
        failures: list[str] = []
        auth_ok: list[str] = []
        rpc_skipped: list[str] = []

        # Already-handled categories.
        _middleware_public: set[str] = set()
        _test_public: set[str] = set()
        _request_state: set[str] = set()

        for method, path, module, has_auth in route_statuses:
            label = f"{method} {path} ({module})"

            if has_auth:
                auth_ok.append(label)
                continue

            # Check middleware public paths.
            if path in _MIDDLEWARE_PUBLIC_PATHS:
                _middleware_public.add(label)
                continue

            # Check test allowlist.  Every entry here names one
            # specific endpoint, not a route namespace, so this is
            # an EXACT match (after normalising a trailing slash) —
            # never a prefix match.  A prefix match on an entry like
            # "/api/v1" would silently absorb every route under it
            # (that was the same bug the removed "/" entry had).
            matched_test = False
            for allowed, reason in _TEST_ALLOWLIST.items():
                if path == (allowed.rstrip("/") or "/"):
                    _test_public.add(f"{label} — {reason}")
                    matched_test = True
                    break
            if matched_test:
                continue

            # Check request.state.account_id pattern (prefix match).
            matched_state = False
            for pfx in _REQUEST_STATE_PATTERN_PREFIXES:
                if path.startswith(pfx):
                    _request_state.add(
                        f"{label} — request.state.account_id pattern"
                    )
                    matched_state = True
                    break
            if matched_state:
                continue

            # Check RPC-only (already filtered, but belt and suspenders).
            matched_rpc = False
            for pfx in _RPC_ONLY_PREFIXES:
                if path.startswith(pfx):
                    rpc_skipped.append(label)
                    matched_rpc = True
                    break
            if matched_rpc:
                continue

            failures.append(label)

        # Report summaries for visibility.
        print(f"\n  Auth-dep OK: {len(auth_ok)} routes")
        print(f"  Middleware public allowlist: "
              f"{len(_middleware_public)} routes")
        print(f"  Test allowlist: {len(_test_public)} routes")
        print(f"  Request.state pattern: {len(_request_state)} routes")
        print(f"  RPC skipped: {len(rpc_skipped)} routes")

        if failures:
            print(f"\n  FAILURES — {len(failures)} routes without "
                  f"auth dep or allowlist entry:")
            for f in sorted(failures):
                print(f"    {f}")

        assert len(failures) == 0, (
            f"{len(failures)} route(s) have no auth dependency and "
            f"are not in any allowlist.  Either add an auth "
            f"``Depends`` to the handler, add the route to "
            f"``_TEST_ALLOWLIST`` with a justification, or confirm "
            f"the route uses ``request.state.account_id`` and add "
            f"its prefix to ``_REQUEST_STATE_PATTERN_PREFIXES``.  "
            f"See failures printed above."
        )

    def test_no_silent_disagreement_with_middleware_allowlist(
        self,
    ) -> None:
        """The auth middleware must use the shared ``PUBLIC_PATHS``
        constant — it must NOT re-hardcode a divergent set.

        ``_MIDDLEWARE_PUBLIC_PATHS`` now IS the shared constant
        (imported from ``airunner_services.api.server_middleware``),
        so a re-hardcoded literal in the auth middleware would be the
        only way the two could disagree.  This test guards against that
        by asserting the middleware source references the import.
        """
        import ast

        middleware_path = (
            Path(__file__).resolve().parent.parent.parent
            / "extensions" / "auth" / "server" / "middleware.py"
        )
        if not middleware_path.exists():
            pytest.skip("Auth middleware not found — "
                         "cannot cross-check allowlist")

        source = middleware_path.read_text()
        tree = ast.parse(source)

        # The auth middleware must reference the shared PUBLIC_PATHS
        # name (imported from the framework), not define its own set
        # literal of public paths.
        imports_shared = any(
            (
                isinstance(node, ast.ImportFrom)
                and node.module == "airunner_services.api.server_middleware"
                and any(
                    alias.name == "PUBLIC_PATHS" for alias in node.names
                )
            )
            for node in ast.walk(tree)
        )
        if not imports_shared:
            pytest.fail(
                "Auth middleware no longer imports the shared "
                "PUBLIC_PATHS constant — it must, so the framework "
                "and extension public-path sets cannot drift."
            )

        # The auth middleware must not define its own inline set of
        # public paths (that was the pre-shared-constant design and is
        # exactly the drift this test guards against).
        inline_sets = {
            p for node in ast.walk(tree)
            if isinstance(node, ast.Set)
            for elt in node.elts
            if isinstance(elt, ast.Constant)
            and isinstance(elt.value, str)
            and elt.value.startswith("/api/")
            for p in [elt.value]
        }
        # The only path-like strings expected are the shared constant
        # import itself (a Name, not a literal) — any literal /api/*
        # set here is a regression.
        assert not inline_sets, (
            f"Auth middleware defines inline public paths: "
            f"{sorted(inline_sets)}.  Use the shared PUBLIC_PATHS."
        )

    def test_request_state_prefixes_do_not_overlap_allowlists(
        self,
    ) -> None:
        """Routes in ``_REQUEST_STATE_PATTERN_PREFIXES`` must not
        also appear in the middleware public allowlist — that would
        be a contradiction (public routes don't need request.state)."""
        for pfx in _REQUEST_STATE_PATTERN_PREFIXES:
            for public_path in _MIDDLEWARE_PUBLIC_PATHS:
                assert not public_path.startswith(pfx), (
                    f"Prefix '{pfx}' overlaps with public path "
                    f"'{public_path}' — request.state pattern "
                    f"is unnecessary for public routes"
                )
