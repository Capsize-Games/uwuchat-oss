"""RPC handlers: settings CRUD (resource store).

Decomposed into focused modules:

- ``_registry`` — framework-default exposed-resource allowlist and
  resource-store table lookup
- ``_helpers`` — shared helpers (auth, redaction, validation, rate
  limiting, error mapping)
- ``_guards`` — guard-hook invocation (sanitize, ownership, read filter)
- ``_handlers`` — singleton and create/quota RPC handlers
- ``_crud`` — auth-guarded CRUD RPC handlers (update/delete/reset/
  make-current/query/first)

Importing this package registers all RPC routes (decorator side
effects), runs the framework resource-exposure registration, and
re-exports every name consumers import from the old single module.
"""

from __future__ import annotations

# Relative imports resolve through the package's own name, so both
# ``airunner_services.api.routes.rpc_settings`` and the ``server.src.*``
# test-tree alias load the same submodules under their own names.
# Side-effect registration — every submodule that defines @_rpc_register
# handlers must be imported.
from . import _crud as _crud
from . import _guards as _guards
from . import _handlers as _handlers
from . import _helpers as _helpers
from . import _registry as _registry
from ._crud import (
    _rpc_settings_delete as _rpc_settings_delete,
    _rpc_settings_first as _rpc_settings_first,
    _rpc_settings_make_current as _rpc_settings_make_current,
    _rpc_settings_query as _rpc_settings_query,
    _rpc_settings_reset_defaults as _rpc_settings_reset_defaults,
    _rpc_settings_update_by_id as _rpc_settings_update_by_id,
)
from ._guards import (
    _apply_read_filter as _apply_read_filter,
    _check_before_delete as _check_before_delete,
    _check_before_reset_defaults as _check_before_reset_defaults,
    _check_guard_ownership as _check_guard_ownership,
    _sanitize_for_resource as _sanitize_for_resource,
)
from ._handlers import (
    _rpc_settings_create as _rpc_settings_create,
    _rpc_settings_quota as _rpc_settings_quota,
    _rpc_settings_singleton as _rpc_settings_singleton,
    _rpc_settings_singleton_update as _rpc_settings_singleton_update,
)
from ._helpers import (
    _CHATBOT_RATE_LIMIT as _CHATBOT_RATE_LIMIT,
    _CHATBOT_RATE_LIMIT_WINDOW_HOURS as
    _CHATBOT_RATE_LIMIT_WINDOW_HOURS,
    _CHATBOT_TEXT_FIELDS as _CHATBOT_TEXT_FIELDS,
    _SECRET_FIELD_PATTERN as _SECRET_FIELD_PATTERN,
    _apply_filters as _apply_filters,
    _chatbot_rate_limit_error as _chatbot_rate_limit_error,
    _guard_error_response as _guard_error_response,
    _is_superuser as _is_superuser,
    _record_from_item as _record_from_item,
    _resolve_account_id as _resolve_account_id,
    _settings_auth as _settings_auth,
    _validate_chatbot_values as _validate_chatbot_values,
    _ws_connection_info as _ws_connection_info,
)
from ._registry import (
    _FRAMEWORK_EXPOSED_RESOURCES as _FRAMEWORK_EXPOSED_RESOURCES,
    register_framework_resources as register_framework_resources,
    resource_store_table as resource_store_table,
)

# Import-time registration: expose the framework-default resources so
# the WS resource store allows them.  Re-runs on importlib.reload.
register_framework_resources()

__all__ = [
    "_CHATBOT_RATE_LIMIT",
    "_CHATBOT_RATE_LIMIT_WINDOW_HOURS",
    "_CHATBOT_TEXT_FIELDS",
    "_FRAMEWORK_EXPOSED_RESOURCES",
    "_SECRET_FIELD_PATTERN",
    "_apply_filters",
    "_apply_read_filter",
    "_chatbot_rate_limit_error",
    "_check_before_delete",
    "_check_before_reset_defaults",
    "_check_guard_ownership",
    "_guard_error_response",
    "_is_superuser",
    "_record_from_item",
    "_resolve_account_id",
    "_rpc_settings_create",
    "_rpc_settings_delete",
    "_rpc_settings_first",
    "_rpc_settings_make_current",
    "_rpc_settings_query",
    "_rpc_settings_quota",
    "_rpc_settings_reset_defaults",
    "_rpc_settings_singleton",
    "_rpc_settings_singleton_update",
    "_rpc_settings_update_by_id",
    "_sanitize_for_resource",
    "_settings_auth",
    "_validate_chatbot_values",
    "_ws_connection_info",
    "register_framework_resources",
    "resource_store_table",
]
