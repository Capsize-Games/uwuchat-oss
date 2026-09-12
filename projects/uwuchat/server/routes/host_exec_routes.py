"""UwUChat host-executor policy routes (WS-RPC only).

The client reaches the host-exec policy over the unified
``/api/v1/events`` WebSocket (the ``request()`` helper), never over
HTTP — so this module intentionally defines no HTTP endpoints.  It
exists to give the route-spec table a module to import at startup,
mirroring ``random_chatbot_routes.py`` / ``headlesscode_routes.py``:

- the ``router`` attribute is included by
  :func:`airunner_services.api.server_routes.register_routes` (an empty
  router contributes no HTTP paths);
- importing by name (not binding it) runs the ``@_rpc_register``
  decorators in :mod:`host_exec_rpc`, registering the WS-RPC handlers.
"""

from __future__ import annotations

import importlib

from fastapi import APIRouter

router = APIRouter()

importlib.import_module(f"{__package__}.host_exec_rpc")
