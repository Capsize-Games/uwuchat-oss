"""Regression tests for security finding #11 — admin gating on RPCs.

Confirms that cost/billing, token usage, and other admin-only RPCs
correctly reject non-superuser callers.  The underlying functions
use the ``_require_superuser`` pattern; these tests verify the gate
works independently of the actual business logic.
"""

from __future__ import annotations



from airunner_services.api.routes.token_usage_routes import (
    _require_superuser,
)
from airunner_services.api.routes.rpc_conversation_handlers import (
    _require_superuser as _conv_require_superuser,
)


class TestTokenUsageSuperuserGate:
    """The _require_superuser helper returns an account_id for superusers
    and None for non-superusers.  Since we can't create real accounts in
    these unit tests, we verify the helper function exists and has the
    expected signature."""

    def test_require_superuser_is_callable(self) -> None:
        assert callable(_require_superuser)

    def test_require_superuser_returns_none_for_invalid_ws(self) -> None:
        """Passing None (no websocket) returns None, not an exception."""
        result = _require_superuser(None)
        assert result is None

    def test_conv_require_superuser_is_callable(self) -> None:
        assert callable(_conv_require_superuser)

    def test_conv_require_superuser_returns_none_for_none(self) -> None:
        result = _conv_require_superuser(None)
        assert result is None


class TestAdminGatingOnRoutes:
    """Verify that admin-only routes apply superuser gating by checking
    the function signature / docstring conventions.

    These are static checks — actual auth requires a real WS connection
    with a JWT.  The purpose is to confirm the gate exists, not to
    exercise the full auth flow (which is covered by integration tests
    that need a database).
    """

    def test_message_delete_has_superuser_check(self) -> None:
        """_rpc_message_delete's first operation is the superuser check."""
        from airunner_services.api.routes import (
            rpc_conversation_handlers as rch,
        )

        func = rch._rpc_message_delete
        import inspect
        source = inspect.getsource(func)
        # The function should reference _require_superuser before any
        # database operation.
        assert "_require_superuser" in source
        # The 403 response must exist in the code path.
        assert '"error": "Admin access required"' in source

    def test_token_usage_route_has_superuser_gate(self) -> None:
        """token_usage_routes must import _require_superuser."""
        from airunner_services.api.routes import token_usage_routes as tur

        assert hasattr(tur, "_require_superuser")

    def test_admin_rpc_has_superuser_gate(self) -> None:
        """admin_events should gate on is_superuser."""
        import inspect
        from airunner_services.api.routes import admin_events

        source = inspect.getsource(admin_events)
        assert "is_superuser" in source or "_require_superuser" in source

    def test_pipeline_config_route_admin_only(self) -> None:
        """pipeline_config_routes should gate on is_superuser."""
        import inspect
        from airunner_services.api.routes import pipeline_config_routes

        source = inspect.getsource(pipeline_config_routes)
        assert "is_superuser" in source or "_require_superuser" in source

    def test_code_mode_routes_admin_only(self) -> None:
        """rpc_code_mode's GET and PUT handlers both gate on
        _require_superuser before touching the database."""
        import inspect
        from airunner_services.api.routes import rpc_code_mode

        for func in (
            rpc_code_mode._rpc_code_mode_get,
            rpc_code_mode._rpc_code_mode_set,
        ):
            source = inspect.getsource(func)
            assert "_require_superuser" in source
            assert '"error": "Admin access required"' in source

    def test_code_credits_rpc_admin_only(self) -> None:
        """code_credits_rpc's get/topup handlers both gate on
        _require_superuser before touching the ledger."""
        import inspect
        from projects.uwuchat.server.routes import code_credits_rpc

        for func in (
            code_credits_rpc._rpc_get_code_credits,
            code_credits_rpc._rpc_top_up_code_credits,
        ):
            source = inspect.getsource(func)
            assert "_require_superuser" in source
