"""API route modules — WebSocket-only architecture.

Each import triggers route registration via decorators in the
imported modules.  Imports are prefixed with ``_`` to signal they
are side-effect-only and kept in ``__all__`` for discoverability.
"""

from airunner_services.api.routes import admin_events as _admin_events
from airunner_services.api.routes import events as _events
from airunner_services.api.routes import openrouter_catalog_routes as _openrouter_catalog_routes
from airunner_services.api.routes import pipeline_config_routes as _pipeline_config_routes
from airunner_services.api.routes import token_usage_routes as _token_usage_routes

from airunner_services.api.routes import rpc_art as _rpc_art
from airunner_services.api.routes import rpc_canvas as _rpc_canvas
from airunner_services.api.routes import rpc_character_handlers as _rpc_char
from airunner_services.api.routes import rpc_chatbot_status as _rpc_chatbot_status
from airunner_services.api.routes import rpc_code_mode as _rpc_code_mode
from airunner_services.api.routes import rpc_conversation_handlers as _rpc_conv
from airunner_services.api.routes import rpc_downloads as _rpc_downloads
from airunner_services.api.routes import rpc_embeddings as _rpc_embeddings
from airunner_services.api.routes import rpc_handlers as _rpc
from airunner_services.api.routes import rpc_images as _rpc_images
from airunner_services.api.routes import rpc_kb as _rpc_kb
from airunner_services.api.routes import rpc_location as _rpc_location
from airunner_services.api.routes import rpc_loras as _rpc_loras
from airunner_services.api.routes import rpc_models as _rpc_models
from airunner_services.api.routes import rpc_privacy as _rpc_privacy
from airunner_services.api.routes import rpc_push as _rpc_push
from airunner_services.api.routes import rpc_saved_prompts as _rpc_saved_prompts
from airunner_services.api.routes import rpc_settings as _rpc_settings
from airunner_services.api.routes import rpc_spotify as _rpc_spotify
from airunner_services.api.routes import rpc_user_profile as _rpc_user_profile
from airunner_services.api.routes import rpc_weather as _rpc_weather

from airunner_services.api.routes.events import router as _events_router

__all__ = [
    "_admin_events",
    "_events",
    "_events_router",
    "_openrouter_catalog_routes",
    "_pipeline_config_routes",
    "_rpc",
    "_rpc_art",
    "_rpc_canvas",
    "_rpc_char",
    "_rpc_chatbot_status",
    "_rpc_code_mode",
    "_rpc_conv",
    "_rpc_downloads",
    "_rpc_embeddings",
    "_rpc_images",
    "_rpc_kb",
    "_rpc_location",
    "_rpc_loras",
    "_rpc_models",
    "_rpc_privacy",
    "_rpc_push",
    "_rpc_saved_prompts",
    "_rpc_settings",
    "_rpc_spotify",
    "_rpc_user_profile",
    "_rpc_weather",
    "_token_usage_routes",
]
