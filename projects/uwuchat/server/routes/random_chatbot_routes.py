"""UwUChat random-chatbot creation routes (WS-RPC only).

The client reaches ``POST /api/v1/llm/create-random-chatbot`` over the
unified ``/api/v1/events`` WebSocket (the ``request()`` helper), never
over HTTP — so this module intentionally defines no HTTP endpoints.  It
exists to give the route-spec table a module to import at startup,
mirroring ``headlesscode_routes.py`` / ``email/routes.py``:

- the ``router`` attribute is included by
  :func:`airunner_services.api.server_routes.register_routes` (an empty
  router contributes no HTTP paths);
- importing by name (not binding it) runs the ``@_rpc_register``
  decorators in :mod:`random_chatbot_rpc`, registering the WS-RPC
  handler for the duration of the process.
"""

from __future__ import annotations

import importlib

from fastapi import APIRouter

router = APIRouter()

# Importing by name (not binding it) runs the @_rpc_register
# decorators in random_chatbot_rpc.py — same convention as
# email/routes.py and headlesscode_routes.py.
importlib.import_module(f"{__package__}.random_chatbot_rpc")
