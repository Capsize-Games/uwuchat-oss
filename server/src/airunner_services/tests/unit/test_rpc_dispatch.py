"""Integration tests for RPC dispatch infrastructure."""

import pytest
from airunner_services.api.routes.events import (
    _rpc_routes,
    _dispatch_rpc,
)
from airunner_services.api.routes.events_rpc import _path_to_regex


def test_path_to_regex_literal():
    pattern, params = _path_to_regex("/api/v1/health")
    assert pattern.match("/api/v1/health") is not None
    assert params == []


def test_path_to_regex_with_params():
    pattern, params = _path_to_regex(
        "/api/v1/settings/resources/{name}/singleton"
    )
    match = pattern.match("/api/v1/settings/resources/myres/singleton")
    assert match is not None
    assert params == ["name"]


def test_path_to_regex_multiple_params():
    pattern, params = _path_to_regex(
        "/api/v1/art/images/{date}/info/{filename}"
    )
    match = pattern.match("/api/v1/art/images/20240601/info/test.png")
    assert match is not None
    assert params == ["date", "filename"]


def test_path_to_regex_no_match():
    pattern, _ = _path_to_regex("/api/v1/health")
    assert pattern.match("/api/v1/nonexistent") is None


@pytest.mark.asyncio
async def test_dispatch_health_route():
    result = await _dispatch_rpc("GET", "/api/v1/health", {}, None)
    assert result["status"] == 200


@pytest.mark.asyncio
async def test_dispatch_404():
    result = await _dispatch_rpc("GET", "/api/v1/nonexistent", {}, None)
    assert result["status"] == 404


def test_singleton_route_beats_generic_resource_id():
    """The singleton PUT must route to the singleton handler, not the
    generic ``{resource_id}`` CRUD handler.

    Both ``PUT /api/v1/settings/resources/{name}/singleton`` and
    ``PUT /api/v1/settings/resources/{name}/{resource_id}`` match the
    path ``/api/v1/settings/resources/User/singleton``.  The more
    specific (fewer placeholders) pattern must win — otherwise the
    singleton write returns ``400 Invalid ID`` because ``resource_id``
    captures ``"singleton"``.  This is the onboarding name-save bug.
    """
    from airunner_services.api.routes.events_rpc import (
        _find_rpc_handler,
    )

    func, params = _find_rpc_handler(
        "PUT", "/api/v1/settings/resources/User/singleton"
    )
    assert func is not None
    # The winning handler is the singleton update (defined in _handlers),
    # not the by-id CRUD update (defined in _crud).
    assert func.__name__ == "_rpc_settings_singleton_update", (
        f"expected singleton handler, got {func.__name__}"
    )
    assert params == {"name": "User"}


def test_specificity_preferred_over_registration_order():
    """A literal-suffix route beats a later-registered param route
    regardless of registration order."""
    from airunner_services.api.routes.events_rpc import (
        _find_rpc_handler,
    )

    # GET /settings/resources/{name}/quota vs a hypothetical generic —
    # the quota route (1 placeholder) must win over any 2-placeholder
    # route that could also match this path.
    func, params = _find_rpc_handler(
        "GET", "/api/v1/settings/resources/User/quota"
    )
    assert func is not None
    assert func.__name__ == "_rpc_settings_quota", (
        f"expected quota handler, got {func.__name__}"
    )
    assert params == {"name": "User"}


def test_all_routes_registered():
    registered: set[tuple[str, str]] = set()
    for method, pattern, _params, _func in _rpc_routes:
        registered.add((method, pattern.pattern))

    required = [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/models/active"),
        ("GET", "/api/v1/knowledge-base/documents"),
        ("GET", "/api/v1/art/options"),
        ("GET", "/api/v1/art/bootstrap"),
        ("GET", "/api/v1/llm/conversations"),
        ("GET", "/api/v1/art/images/dates"),
        ("POST", "/api/v1/downloads/huggingface"),
        ("POST", "/api/v1/downloads/civitai/models"),
        ("GET", "/api/v1/art/loras"),
        ("GET", "/api/v1/art/embeddings"),
        ("GET", "/api/v1/uwuchat/code-mode/{conversation_id}"),
        ("PUT", "/api/v1/uwuchat/code-mode/{conversation_id}"),
    ]

    for method, path in required:
        target_pat, _ = _path_to_regex(path)
        found = any(
            r_method == method and r_pat == target_pat.pattern
            for r_method, r_pat in registered
        )
        assert found, f"Route {method} {path} not registered"
