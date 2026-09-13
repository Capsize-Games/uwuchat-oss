"""Local fallback LLM runtime client."""

from __future__ import annotations

from queue import Empty, Queue
from typing import Any, Iterable, Optional

from airunner_services.ipc.messages import (
    EnvelopeStatus,
    RequestEnvelope,
    ResponseEnvelope,
    StreamDelta,
)
from airunner_services.runtimes.contracts import (
    LLMInvocationRequest,
    RuntimeAction,
    RuntimeKind,
)
from airunner_services.runtimes.local_fallback._base import (
    DEFAULT_PROVIDER,
    DEFAULT_TIMEOUT_SECONDS,
    HealthProvider,
    LLMRequestFactory,
    _build_llm_request,
    _build_llm_service,
    _resolve_model_type,
    _SignalRuntimeClient,
)
from airunner_services.runtimes.local_fallback._llm_client_helpers import (
    failure_delta,
    is_complete,
    resolve_action,
    response_message,
    response_metadata,
    timeout_response,
)


def _terminal_content(
    response: Any, is_done: bool, yielded_content: bool
) -> str:
    """Return the content for one stream delta.

    send_end_of_message uses message="" with the full text in
    final_visible_message.  When nothing was streamed (error path),
    fall back so the error string reaches the client.
    """
    content = response_message(response)
    if is_done and not content and not yielded_content:
        content = getattr(response, "final_visible_message", "") or ""
    return content


class LocalFallbackLLMClient(_SignalRuntimeClient):
    """Bridge LLM runtime envelopes to the existing signal service path."""

    def __init__(
        self,
        provider: str = DEFAULT_PROVIDER,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        llm_service: Any = None,
        mediator: Any = None,
        llm_request_factory: Optional[LLMRequestFactory] = None,
        health_provider: Optional[HealthProvider] = None,
    ) -> None:
        llm_service = llm_service or _build_llm_service()
        super().__init__(
            RuntimeKind.LLM,
            provider,
            signal_source=llm_service,
            mediator=mediator,
            timeout_seconds=timeout_seconds,
            health_provider=health_provider,
            allows_model_control=True,
            model_type=_resolve_model_type("LLM"),
        )
        self._llm_service = llm_service
        self._llm_request_factory = llm_request_factory or _build_llm_request

    def invoke(self, request: RequestEnvelope) -> ResponseEnvelope:
        """Invoke the legacy LLM service or model-control path."""
        if request.runtime is not RuntimeKind.LLM:
            raise ValueError("LocalFallbackLLMClient only supports LLM")
        if request.action is RuntimeAction.STATUS:
            return self._status_response(request.request_id)
        if request.action is RuntimeAction.LOAD_MODEL:
            return self._load_model(request.request_id)
        if request.action is RuntimeAction.UNLOAD_MODEL:
            return self._unload_model(request.request_id)
        invocation = self._validate_request(request)
        response_queue = self._dispatch(request, invocation)
        try:
            return self._collect_response(request.request_id, response_queue)
        except TimeoutError as exc:
            return timeout_response(request.request_id, str(exc))
        finally:
            self._mediator.unregister_pending_request(request.request_id)

    def stream(self, request: RequestEnvelope) -> Iterable[StreamDelta]:
        """Stream deltas from the legacy LLM service."""
        invocation = self._validate_request(request)
        response_queue = self._dispatch(request, invocation)
        try:
            yield from self._stream_responses(
                request.request_id, response_queue
            )
        except TimeoutError as exc:
            yield failure_delta(request.request_id, str(exc))
        finally:
            self._mediator.unregister_pending_request(request.request_id)

    def cancel(self, request_id: str) -> ResponseEnvelope:
        """Interrupt the current legacy LLM request on a best-effort basis."""
        if hasattr(self._llm_service, "interrupt"):
            self._llm_service.interrupt()
        return ResponseEnvelope(
            request_id=request_id,
            status=EnvelopeStatus.CANCELLED,
            metadata={"best_effort": True},
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_request(
        self, request: RequestEnvelope
    ) -> LLMInvocationRequest:
        """Validate a runtime request for this client."""
        if request.action is not RuntimeAction.INVOKE:
            raise ValueError("LocalFallbackLLMClient only supports invoke")
        return LLMInvocationRequest.model_validate(request.payload)

    def _load_model(self, request_id: str) -> ResponseEnvelope:
        """Load the local LLM through the current signal graph."""
        from airunner_services.contract_enums import ModelStatus, SignalCode

        return self._wait_for_model_status(
            request_id,
            emit_code=SignalCode.LLM_LOAD_SIGNAL,
            emit_data={},
            success_statuses=(ModelStatus.LOADED, ModelStatus.READY),
            timeout_code="llm_load_timeout",
            failure_code="llm_load_failed",
            action_name="LLM load",
        )

    def _unload_model(self, request_id: str) -> ResponseEnvelope:
        """Unload the local LLM through the current signal graph."""
        from airunner_services.contract_enums import ModelStatus, SignalCode

        return self._wait_for_model_status(
            request_id,
            emit_code=SignalCode.LLM_UNLOAD_SIGNAL,
            emit_data={},
            success_statuses=(ModelStatus.UNLOADED,),
            timeout_code="llm_unload_timeout",
            failure_code="llm_unload_failed",
            action_name="LLM unload",
        )

    def _dispatch(
        self,
        request: RequestEnvelope,
        invocation: LLMInvocationRequest,
    ) -> Queue:
        """Dispatch a request through the legacy LLM API service."""
        response_queue = self._mediator.register_pending_request(
            request.request_id
        )
        try:
            conversation_id = invocation.metadata.get("conversation_id")
            chatbot_id = invocation.metadata.get("chatbot_id")
            self._llm_service.send_request(
                prompt=self._prompt_from_messages(invocation),
                llm_request=self._prepare_llm_request(invocation),
                action=resolve_action(),
                do_tts_reply=False,
                request_id=request.request_id,
                conversation_id=conversation_id,
                chatbot_id=chatbot_id,
            )
        except Exception:
            self._mediator.unregister_pending_request(request.request_id)
            raise
        return response_queue

    def _prepare_llm_request(self, invocation: LLMInvocationRequest) -> Any:
        """Populate a legacy request object from the neutral contract."""
        request = self._llm_request_factory(invocation)
        system_prompt = self._system_prompt(invocation)
        if system_prompt:
            setattr(request, "system_prompt", system_prompt)
        if invocation.tool_choice and invocation.tool_choice != "auto":
            setattr(request, "force_tool", invocation.tool_choice)
        active_document_ids = invocation.metadata.get("active_document_ids")
        if active_document_ids:
            setattr(request, "active_document_ids", list(active_document_ids))
        runtime_profile = invocation.metadata.get("gguf_runtime_profile")
        if isinstance(runtime_profile, str) and runtime_profile.strip():
            setattr(
                request,
                "gguf_runtime_profile",
                runtime_profile.strip(),
            )
        if invocation.metadata.get("stateless"):
            setattr(request, "stateless", True)
        return request

    def _collect_response(
        self, request_id: str, response_queue: Queue
    ) -> ResponseEnvelope:
        """Collect a full response from streamed legacy chunks."""
        chunks = []
        for response in self._iter_responses(response_queue):
            chunks.append(response_message(response))
            if is_complete(response):
                return ResponseEnvelope(
                    request_id=request_id,
                    status=EnvelopeStatus.SUCCEEDED,
                    payload={"content": "".join(chunks)},
                    metadata=response_metadata(response),
                )
        raise TimeoutError(
            "Response is taking longer than expected — "
            "the reply may still appear shortly."
        )

    def _stream_responses(
        self, request_id: str, response_queue: Queue
    ) -> Iterable[StreamDelta]:
        """Yield response deltas from the legacy LLM service."""
        responses = self._iter_responses(response_queue)
        yielded_content = False
        for sequence, response in enumerate(responses):
            if getattr(response, "is_system_message", False):
                yield StreamDelta(
                    request_id=request_id,
                    sequence=sequence,
                    delta={"content": response_message(response)},
                    final=is_complete(response),
                    metadata={"message_type": "system"},
                )
                if is_complete(response):
                    return
                continue
            is_done = is_complete(response)
            content = _terminal_content(response, is_done, yielded_content)
            if content:
                yielded_content = True
            yield StreamDelta(
                request_id=request_id,
                sequence=sequence,
                delta={"content": content},
                final=is_done,
                metadata=response_metadata(response),
            )
            if is_done:
                return
        raise TimeoutError(
            "Response is taking longer than expected — "
            "the reply may still appear shortly."
        )

    def _iter_responses(self, response_queue: Queue) -> Iterable[Any]:
        """Iterate over queued legacy LLM response objects."""
        while True:
            try:
                data = response_queue.get(timeout=self._timeout_seconds)
            except Empty as exc:
                raise TimeoutError(
                    "Response is taking longer than expected — "
                    "the reply may still appear shortly. "
                    "Please wait a moment before retrying."
                ) from exc
            response = data.get("response")
            if response is not None:
                yield response

    @staticmethod
    def _prompt_from_messages(invocation: LLMInvocationRequest) -> str:
        """Extract the user-facing prompt from a message list."""
        import logging
        logger = logging.getLogger(__name__)
        result = next(
            (
                m.content
                for m in reversed(invocation.messages)
                if m.role.value == "user" and m.content
            ),
            "",
        )
        if not result:
            logger.error(
                "_prompt_from_messages: no user-role message with "
                "content found in %d messages",
                len(invocation.messages),
            )
        return result

    @staticmethod
    def _system_prompt(invocation: LLMInvocationRequest) -> Optional[str]:
        """Extract the leading system prompt when present."""
        return next(
            (
                m.content
                for m in invocation.messages
                if m.role.value == "system" and m.content
            ),
            None,
        )
