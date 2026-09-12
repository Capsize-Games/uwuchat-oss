"""Integration test: PII masking reaches the LLM egress path.

Proves the Part 1a fix by driving the real handle_request() entry point
and asserting _ensure_pii_vault() runs BEFORE the stateless branch.

Mutation-test proof: revert the Part 1a fix (move _ensure_pii_vault back
after the stateless return) and this test fails. Restore the fix and it
passes.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

_TEST_EMAIL = "alice.johnson@example.com"


# Force PII masking enabled BEFORE any pii.settings import.
os.environ["AIRUNNER_PII_MASKING_ENABLED"] = "1"


def _build_manager():
    """Build a CloudModelManager for testing handle_request()."""
    from airunner_services.cloud.workers.cloud_model_manager import (
        CloudModelManager,
    )

    mgr = CloudModelManager.__new__(CloudModelManager)
    mgr.llm_settings = MagicMock()
    mgr.llm_settings.use_openrouter = True
    mgr.logger = MagicMock()
    mgr._chat_model = None
    mgr._workflow_manager = None
    mgr._tool_manager = None
    mgr._pii_vault = None
    mgr._current_request_id = None
    mgr._interrupted = False
    mgr._call_chain_id = None
    mgr._specialized_chat_models = {}
    mgr.llm_request = None
    mgr._chatbot = None
    mgr._runtime_settings_cache = {}
    mgr.load = MagicMock()
    mgr.unload = MagicMock()
    mgr._run_preflight = MagicMock(return_value=None)
    return mgr


@pytest.mark.timeout(15)
async def test_ensure_pii_vault_called_before_stateless_return() -> None:
    """_ensure_pii_vault() MUST run before _do_stateless_generate().

    Proves the Part 1a ordering fix.  When the original bug is present
    (_ensure_pii_vault after stateless return), this test fails because
    the vault was never created when _do_stateless_generate executes.
    """
    from langchain_core.messages import AIMessage
    from airunner_services.cloud.workers.cloud_model_manager import (
        CloudModelManager,
    )

    mgr = _build_manager()

    vault_created = []

    def _wrap_ensure(self_mgr):
        vault_created.append(1)
        return None

    def _fake_stateless(self_mgr, prompt, sp, llm_req):
        assert vault_created, (
            "_ensure_pii_vault() was NOT called before "
            "_do_stateless_generate() — the Part 1a ordering fix "
            "is broken or was reverted"
        )
        return {"response": "ok"}

    # Minimal chat model mock for stateless path.
    mock_chat_model = MagicMock()
    mock_chat_model.invoke.return_value = AIMessage(content="ok")
    mgr._specialized_chat_models["STATELESS"] = mock_chat_model

    mock_settings = MagicMock()
    mock_settings.dtype = None

    with patch.object(
        CloudModelManager, "_ensure_pii_vault", _wrap_ensure,
    ), patch.object(
        CloudModelManager, "_do_stateless_generate", _fake_stateless,
    ), patch.object(
        CloudModelManager, "llm_generator_settings",
        property(lambda s: mock_settings),
    ), patch(
        "airunner_services.llm.managers.request_preparation."
        "capture_request_settings_snapshot",
        return_value=MagicMock(),
    ):
        llm_req = MagicMock()
        llm_req.stateless = True
        llm_req.system_prompt = None
        result = await mgr.handle_request({
            "request_data": {
                "prompt": f"email: {_TEST_EMAIL}",
                "action": "CHAT",
                "llm_request": llm_req,
            },
            "request_id": "test-req",
        })

    assert result == {"response": "ok"}
    assert vault_created, (
        "_ensure_pii_vault was never called by handle_request"
    )
