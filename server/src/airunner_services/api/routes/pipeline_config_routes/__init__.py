"""Admin RPC routes for pipeline config management.

Decomposed into focused modules:

- ``_superuser`` — superuser guard shared by admin routes
- ``_helpers`` — deep-merge helper for pipeline overrides
- ``_list`` — list pipeline configs
- ``_get`` — get one pipeline config
- ``_update`` — upsert pipeline overrides (create + update)
- ``_delete`` — reset pipeline overrides
- ``_stages_meta`` — pipeline stage metadata constants
- ``_stages`` — pipeline stage list and prompt-save endpoints

Importing this package registers all RPC routes (decorator side
effects) and re-exports the shared helpers consumers rely on.
"""

from __future__ import annotations

# Side-effect route registration — must import every submodule that
# defines @_rpc_register handlers.
from airunner_services.api.routes.pipeline_config_routes import (
    _delete as _delete,
)
from airunner_services.api.routes.pipeline_config_routes import (
    _get as _get,
)
from airunner_services.api.routes.pipeline_config_routes import (
    _list as _list,
)
from airunner_services.api.routes.pipeline_config_routes import (
    _stages as _stages,
)
from airunner_services.api.routes.pipeline_config_routes import (
    _update as _update,
)
from airunner_services.api.routes.pipeline_config_routes._helpers import (
    _deep_merge,
)
from airunner_services.api.routes.pipeline_config_routes._superuser import (
    _require_superuser,
)

__all__ = [
    "_deep_merge",
    "_require_superuser",
]
