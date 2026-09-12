"""Overflow route spec table — see ``server_routes_specs`` docstring.

``server_routes_specs.py`` is itself at the repo's 250-line file-size
cap, so further route-spec entries land here instead and get appended
onto ``_ROUTE_SPECS`` at import time.
"""

from __future__ import annotations

# WS-RPC only; import registers create-random-chatbot's handler.
_ROUTE_SPECS_2: list = [
    (
        "uwuchat_random_chatbot",
        "projects.uwuchat.server.routes.random_chatbot_routes",
        {
            "prefix": "/api/v1/uwuchat/random-chatbot",
            "tags": ["random-chatbot"],
        },
        [],
    ),
    (
        "embed_text",
        "airunner_services.api.routes.embed_text",
        {"prefix": "/api/v1", "tags": ["embeddings"]},
        [],
    ),
    # WS-RPC only; import registers the host-exec policy handlers.
    (
        "uwuchat_host_exec",
        "projects.uwuchat.server.routes.host_exec_routes",
        {
            "prefix": "/api/v1/uwuchat/host-exec",
            "tags": ["host-exec"],
        },
        [],
    ),
]
