"""Admin RPC routes for token usage aggregation.

Decomposed into focused modules:

- ``_superuser`` — superuser guard shared by admin routes
- ``_pricing_cache`` — pricing cache lookups and alternate-ID variants
- ``_pricing_fetch`` — OpenRouter catalog fetch and cache population
- ``_cost`` — per-row cost computation
- ``_aggregation`` — tier/account aggregation helpers
- ``_summary_routes`` — summary and per-customer endpoints
- ``_call_chain_routes`` — call-chain and cost-by-turn endpoints
- ``_conversation_routes`` — per-conversation cost endpoint
- ``_accounts_routes`` — account listing endpoint
- ``_rows_routes`` — paginated usage rows endpoint
- ``_health_routes`` — pricing-health diagnostic endpoint

Importing this package registers all RPC routes (decorator side
effects) and re-exports the module-level names consumers rely on,
including ``_require_superuser``, ``_fetch_failed``/``_fetch_in_flight``
and the pricing helpers used as patch targets by tests.
"""

from __future__ import annotations

import logging

# Side-effect route registration — must import every submodule that
# defines @_rpc_register handlers.
from airunner_services.api.routes.token_usage_routes import (
    _accounts_routes as _accounts_routes,
)
from airunner_services.api.routes.token_usage_routes import (
    _call_chain_routes as _call_chain_routes,
)
from airunner_services.api.routes.token_usage_routes import (
    _conversation_routes as _conversation_routes,
)
from airunner_services.api.routes.token_usage_routes import (
    _health_routes as _health_routes,
)
from airunner_services.api.routes.token_usage_routes import (
    _rows_routes as _rows_routes,
)
from airunner_services.api.routes.token_usage_routes import (
    _summary_routes as _summary_routes,
)
from airunner_services.api.routes.token_usage_routes._accounts_routes import (
    _token_usage_accounts,
)
from airunner_services.api.routes.token_usage_routes._aggregation import (
    _accounts_with_email,
    _per_account_request_stats,
    _tier_breakdown,
)
from airunner_services.api.routes.token_usage_routes._call_chain_routes import (
    _call_chain_by_turn,
    _call_chain_detail,
    _cost_by_turn,
)
from airunner_services.api.routes.token_usage_routes._conversation_routes import (
    _token_usage_conversation,
)
from airunner_services.api.routes.token_usage_routes._cost import (
    _compute_cost,
)
from airunner_services.api.routes.token_usage_routes._health_routes import (
    _pricing_health,
)
from airunner_services.api.routes.token_usage_routes._pricing_cache import (
    _alternate_model_ids,
    _cache_has_nonzero_price,
    _fetch_failed,
    _fetch_in_flight,
    _lookup_pricing_in_cache,
    _price_lookup,
)
from airunner_services.api.routes.token_usage_routes._pricing_fetch import (
    _do_fetch_single_model,
    _ensure_model_in_cache,
    _insert_placeholder_model,
)
from airunner_services.api.routes.token_usage_routes._rows_routes import (
    _token_usage_rows,
)
from airunner_services.api.routes.token_usage_routes._summary_routes import (
    _token_usage_per_customer,
    _token_usage_summary,
)
from airunner_services.api.routes.token_usage_routes._superuser import (
    _require_superuser,
)

logger = logging.getLogger(__name__)

__all__ = [
    "_accounts_with_email",
    "_alternate_model_ids",
    "_cache_has_nonzero_price",
    "_call_chain_by_turn",
    "_call_chain_detail",
    "_compute_cost",
    "_cost_by_turn",
    "_do_fetch_single_model",
    "_ensure_model_in_cache",
    "_fetch_failed",
    "_fetch_in_flight",
    "_insert_placeholder_model",
    "_lookup_pricing_in_cache",
    "_per_account_request_stats",
    "_price_lookup",
    "_pricing_health",
    "_require_superuser",
    "_tier_breakdown",
    "_token_usage_accounts",
    "_token_usage_conversation",
    "_token_usage_per_customer",
    "_token_usage_rows",
    "_token_usage_summary",
]
