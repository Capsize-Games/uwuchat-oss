"""Tests for character-creation token usage recording (issue #95).

Both character-creation endpoints (``/api/v1/llm/generate-character``
and ``/api/v1/llm/generate-uwu-identity``) make real LLM calls that
previously bypassed ``pipeline_token_usage``.  These tests pin the new
behaviour: ``invoke_llm_runtime`` surfaces the runtime's token counts
and each handler records them under the ``CHARACTER_CREATION`` key.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from airunner_services.api.routes.llm_runtime import (
    LLMRuntimeResult,
    invoke_llm_runtime,
)
from airunner_services.ipc.messages import (
    EnvelopeStatus,
    ResponseEnvelope,
)
from airunner_services.runtimes.contracts import (
    ChatMessage as RuntimeChatMessage,
    MessageRole,
)


class _FakeClient:
    """RuntimeClient double returning a canned envelope."""

    def __init__(self, envelope: ResponseEnvelope) -> None:
        self._envelope = envelope
        self.invoked = 0

    def invoke(self, request: object) -> ResponseEnvelope:
        self.invoked += 1
        return self._envelope


def test_llm_runtime_result_defaults_to_zero_tokens() -> None:
    result = LLMRuntimeResult(content="hello")
    assert result.content == "hello"
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_invoke_llm_runtime_extracts_usage_from_envelope() -> None:
    envelope = ResponseEnvelope(
        request_id="r1",
        status=EnvelopeStatus.SUCCEEDED,
        payload={"content": '{"name": "Aiko"}'},
        metadata={
            "prompt_tokens": 120,
            "completion_tokens": 45,
            "total_tokens": 165,
        },
    )
    client = _FakeClient(envelope)
    result = await invoke_llm_runtime(
        client,
        [RuntimeChatMessage(role=MessageRole.USER, content="hi")],
        None,
        None,
        0.9,
        500,
        stateless=True,
    )
    assert client.invoked == 1
    assert result.content == '{"name": "Aiko"}'
    assert result.prompt_tokens == 120
    assert result.completion_tokens == 45
    assert result.total_tokens == 165


@pytest.mark.asyncio
async def test_invoke_llm_runtime_defaults_when_metadata_missing() -> None:
    envelope = ResponseEnvelope(
        request_id="r2",
        status=EnvelopeStatus.SUCCEEDED,
        payload={"content": "ok"},
    )
    result = await invoke_llm_runtime(
        _FakeClient(envelope),
        [RuntimeChatMessage(role=MessageRole.USER, content="hi")],
        None,
        None,
        0.9,
        500,
        stateless=True,
    )
    assert result.content == "ok"
    assert result.prompt_tokens == 0
    assert result.completion_tokens == 0
    assert result.total_tokens == 0


def _assert_recorded(
    record: MagicMock, cfg_value: dict, tokens: tuple[int, int]
) -> None:
    """Assert record_usage got the CHARACTER_CREATION attribution."""
    record.assert_called_once_with(
        pipeline_key="CHARACTER_CREATION",
        model_id=cfg_value["model"],
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        call_chain_id="chain-1",
    )


def test_http_record_character_usage_writes_row() -> None:
    from airunner_services.api.routes import llm_http_routes

    result = LLMRuntimeResult(
        content="{}", prompt_tokens=10, completion_tokens=6, total_tokens=16
    )
    cfg_value = {"model": "deepseek/deepseek-v4-flash"}
    with (
        patch(
            "airunner_services.llm.pipeline_loader.pipeline_config",
            return_value=cfg_value,
        ) as cfg,
        patch(
            "airunner_services.llm.active_call_chain.get_active_call_chain",
            return_value="chain-1",
        ),
        patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as record,
    ):
        llm_http_routes._record_character_usage(result)

    cfg.assert_called_once_with("CHARACTER_CREATION")
    _assert_recorded(record, cfg_value, (10, 6))


def test_rpc_record_character_usage_writes_row() -> None:
    from airunner_services.api.routes import rpc_character_handlers

    result = LLMRuntimeResult(
        content="{}", prompt_tokens=3, completion_tokens=9, total_tokens=12
    )
    cfg_value = {"model": "deepseek/deepseek-v4-flash"}
    with (
        patch(
            "airunner_services.llm.pipeline_loader.pipeline_config",
            return_value=cfg_value,
        ) as cfg,
        patch(
            "airunner_services.llm.active_call_chain.get_active_call_chain",
            return_value="chain-1",
        ),
        patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as record,
    ):
        rpc_character_handlers._record_character_usage(result)

    cfg.assert_called_once_with("CHARACTER_CREATION")
    _assert_recorded(record, cfg_value, (3, 9))


@pytest.mark.asyncio
async def test_invoke_character_llm_records_usage() -> None:
    from airunner_services.api.routes import rpc_character_handlers

    registry = MagicMock()

    async def _fake_invoke(
        client, messages, model, profile, temperature, max_tokens, stateless=False
    ) -> LLMRuntimeResult:
        assert stateless is True
        return LLMRuntimeResult(
            content='{"name": "Aiko"}',
            prompt_tokens=4,
            completion_tokens=2,
            total_tokens=6,
        )

    with (
        patch(
            "airunner_services.api.routes.llm_runtime.invoke_llm_runtime",
            new=AsyncMock(side_effect=_fake_invoke),
        ) as invoke,
        patch(
            "airunner_services.api.routes.llm_runtime.resolve_llm_client",
            return_value=object(),
        ),
        patch.object(
            rpc_character_handlers, "_record_character_usage"
        ) as record,
    ):
        content = await rpc_character_handlers._invoke_character_llm(
            registry, lambda gender: ("sys", f"user-{gender}"), "Female"
        )

    assert content == '{"name": "Aiko"}'
    invoke.assert_awaited_once()
    record.assert_called_once()
    recorded = record.call_args.args[0]
    assert recorded.prompt_tokens == 4
    assert recorded.completion_tokens == 2


@pytest.mark.asyncio
async def test_generate_character_handler_records_usage() -> None:
    from airunner_services.api.routes import llm_http_routes

    cfg_value = {"model": "deepseek/deepseek-v4-flash"}
    with (
        patch(
            "airunner_services.api.routes.llm_runtime.require_runtime_registry"
        ),
        patch(
            "airunner_services.api.routes.llm_runtime.resolve_llm_client",
            return_value=object(),
        ),
        patch(
            "airunner_services.api.routes.llm_runtime.invoke_llm_runtime",
            new=AsyncMock(
                return_value=LLMRuntimeResult(
                    content='{"name": "Aiko"}',
                    prompt_tokens=8,
                    completion_tokens=3,
                    total_tokens=11,
                )
            ),
        ),
        patch(
            "airunner_services.llm.pipeline_loader.pipeline_config",
            return_value=cfg_value,
        ),
        patch(
            "airunner_services.llm.active_call_chain.get_active_call_chain",
            return_value="chain-1",
        ),
        patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as record,
    ):
        body = llm_http_routes.CharacterGenerateRequest()
        result = await llm_http_routes.generate_character(body, MagicMock())

    assert result == {"name": "Aiko"}
    _assert_recorded(record, cfg_value, (8, 3))
