"""Route spec table for :mod:`airunner_services.api.server_routes`.

Kept under the 250-line cap; new entries go in ``server_routes_specs_2``.
"""

from __future__ import annotations

from airunner_services.api.server_routes_specs_2 import _ROUTE_SPECS_2


_FRAMEWORK_SPECS = [
    ("health", "airunner_services.api.routes.health", {}, []),
    (
        "health_v1",
        "airunner_services.api.routes.health",
        {"prefix": "/api/v1", "tags": ["health"]},
        ["health"],
    ),
    (
        "events",
        "airunner_services.api.routes",
        {"prefix": "/api/v1", "tags": ["events"]},
        [],
        "_events_router",
    ),
    (
        "art_ws",
        "airunner_services.api.routes.art_websocket",
        {"prefix": "/api/v1/art", "tags": ["art"]},
        [],
    ),
    (
        "art_daemon_ws",
        "airunner_services.api.routes.art_daemon_ws",
        {"prefix": "/api/v1/art", "tags": ["art"]},
        [],
    ),
    (
        "llm_ws",
        "airunner_services.api.routes.llm_stream_routes",
        {"prefix": "/api/v1/llm", "tags": ["llm"]},
        [],
    ),
    (
        "llm_http",
        "airunner_services.api.routes.llm_http_routes",
        {"prefix": "/api/v1/llm", "tags": ["llm"]},
        [],
    ),
    (
        "tts",
        "airunner_services.api.routes.tts",
        {"prefix": "/api/v1/tts", "tags": ["tts"]},
        [],
    ),
    (
        "hardware",
        "airunner_services.api.routes.hardware",
        {"prefix": "/api/v1/daemon", "tags": ["daemon"]},
        [],
    ),
    (
        "geolocation",
        "airunner_services.api.routes.geolocation",
        {"prefix": "/api/v1/daemon", "tags": ["daemon"]},
        [],
    ),
    (
        "canvas",
        "airunner_services.api.routes.canvas_document",
        {"prefix": "/api/v1/canvas", "tags": ["canvas"]},
        [],
    ),
    (
        "images",
        "airunner_services.api.routes.images",
        {"prefix": "/api/v1/images", "tags": ["images"]},
        [],
    ),
    (
        "admin_health",
        "airunner_services.api.routes.admin_health_routes",
        {"prefix": "/api/v1/admin", "tags": ["admin"]},
        [],
    ),
    (
        "admin_celery",
        "airunner_services.api.routes.admin_celery_routes",
        {"prefix": "/api/v1/admin", "tags": ["admin"]},
        [],
    ),
    (
        "call_chain",
        "airunner_services.api.routes.call_chain_routes",
        {"prefix": "/api/v1/admin", "tags": ["admin"]},
        [],
    ),
    (
        "auth_oauth_capabilities",
        "extensions.auth.server.oauth_capabilities_routes",
        {"prefix": "/api/v1/auth", "tags": ["oauth"]},
        [],
    ),
    (
        "auth_data_export",
        "extensions.auth.server.data_export_routes",
        {"prefix": "/api/v1/auth", "tags": ["data-export"]},
        [],
    ),
]

# UwUchat project routes — active for every non-headlesscode project.
_UWUCHAT_PROJECT_SPECS = [
    (
        "spotify_state",
        "projects.uwuchat.server.spotify.routes",
        {"prefix": "/api/v1/spotify", "tags": ["spotify"]},
        [],
    ),
    (
        "spotify_callback",
        "airunner_services.api.routes.rpc_spotify",
        {"prefix": "/api/v1/spotify", "tags": ["spotify"]},
        [],
        "callback_router",
    ),
    (
        "steam",
        "projects.uwuchat.server.steam.routes",
        {"prefix": "/api/v1/steam", "tags": ["steam"]},
        [],
    ),
    (
        "itch",
        "projects.uwuchat.server.itch.routes",
        {"prefix": "/api/v1/itch", "tags": ["itch"]},
        [],
    ),
    (
        "bluesky",
        "projects.uwuchat.server.bluesky.routes",
        {"prefix": "/api/v1/bluesky", "tags": ["bluesky"]},
        [],
    ),
    (
        "twitch",
        "projects.uwuchat.server.twitch.routes",
        {"prefix": "/api/v1/twitch", "tags": ["twitch"]},
        [],
    ),
    (
        "email",
        "projects.uwuchat.server.email.routes",
        {"prefix": "/api/v1/email", "tags": ["email"]},
        [],
    ),
    (
        "email_stats",
        "projects.uwuchat.server.email.stats_routes",
        {"prefix": "/api/v1/email", "tags": ["email"]},
        [],
    ),
    (
        "uwuchat_usage",
        "projects.uwuchat.server.quota_routes",
        {"prefix": "/api/v1/usage", "tags": ["usage"]},
        [],
    ),
    # Admin code-credits (real-dollar prepaid balance, superuser-gated)
    (
        "uwuchat_code_credits",
        "projects.uwuchat.server.code_credits_routes",
        {"prefix": "/api/v1/uwuchat/code-credits", "tags": ["code-credits"]},
        [],
    ),
    # Productivity routes (journal, calendar, tasks, goals)
    (
        "uwuchat_journal",
        "projects.uwuchat.server.routes.journal_routes",
        {"prefix": "/api/v1/uwuchat/journal", "tags": ["journal"]},
        [],
    ),
    (
        "uwuchat_calendar",
        "projects.uwuchat.server.routes.calendar_routes",
        {"prefix": "/api/v1/uwuchat/calendar", "tags": ["calendar"]},
        [],
    ),
    (
        "uwuchat_productivity",
        "projects.uwuchat.server.routes.task_goal_routes",
        {"prefix": "/api/v1/uwuchat/productivity", "tags": ["productivity"]},
        [],
    ),
    (
        "admin_calendar",
        "projects.uwuchat.server.routes.admin_calendar_routes",
        {"prefix": "/api/v1/admin", "tags": ["admin"]},
        [],
    ),
    (
        "admin_jobs",
        "projects.uwuchat.server.routes.admin_jobs_routes",
        {"prefix": "/api/v1/admin", "tags": ["admin"]},
        [],
    ),
    (
        "uwuchat_headlesscode",
        "projects.uwuchat.server.routes.headlesscode_routes",
        {"prefix": "/api/v1/uwuchat/headlesscode", "tags": ["headlesscode"]},
        [],
    ),
    (
        "uwuchat_code_mode",
        "projects.uwuchat.server.routes.code_mode_routes",
        {"prefix": "/api/v1/uwuchat", "tags": ["code-mode"]},
        [],
    ),
] + _ROUTE_SPECS_2

_ROUTE_SPECS = _FRAMEWORK_SPECS + _UWUCHAT_PROJECT_SPECS
