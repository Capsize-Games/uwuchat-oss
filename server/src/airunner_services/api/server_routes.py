"""Route registration helper extracted from server_helpers.py."""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import FastAPI


def _ensure_project_root_on_path() -> None:
    """Add the project root to ``sys.path`` so ``projects.*`` modules resolve.

    The ``projects/`` directory lives at the repository root (one level up
    from ``server/``).  It is **not** a pip-installed package, so it must
    be discoverable via the Python path for
    ``import projects.uwuchat.server.steam.routes`` (and similar) to work.

    This function is idempotent — safe to call from any startup path.
    """
    import sys

    # This file is at: <project_root>/server/src/airunner_services/api/server_routes.py
    # Go up 4 levels from api/ to reach the project root.
    _here = Path(__file__).resolve().parent  # api/
    _project_root = str(_here.parent.parent.parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)


def _safe_import_router(module_name: str, attr: str = "router"):
    """Import one router module, returning None on ImportError."""
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, attr)
    except ImportError:
        # Retry after ensuring project root is on sys.path
        _ensure_project_root_on_path()
        try:
            mod = importlib.import_module(module_name)
            return getattr(mod, attr)
        except ImportError:
            return None


from airunner_services.api.server_routes_specs import _ROUTE_SPECS


def register_routes(app: FastAPI) -> None:
    """Register all API route handlers."""
    for spec in _ROUTE_SPECS:
        module_name = spec[1]
        include_kwargs = spec[2]
        attr = spec[4] if len(spec) > 4 else "router"
        router = _safe_import_router(module_name, attr)
        if router is not None:
            app.include_router(router, **include_kwargs)
    # Guard registration (follows the same "hardcoded literal import
    # path, swallowed on ImportError" convention as the route specs).
    _ensure_project_root_on_path()
    try:
        mod = importlib.import_module("projects.uwuchat.server.security")
    except ImportError:
        pass
    else:
        mod.register_guards()
