"""Tests for reasoning_content round-trip in _get_request_payload."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


class TestReasoningContentRoundTrip:
    """DeepSeek requires reasoning_content to be echoed back in
    tool-calling assistant messages on follow-up turns."""

    def _build_model(self):
        from airunner_services.cloud.llm.model_builders import (
            _build_reasoning_aware_class,
        )

        cls = _build_reasoning_aware_class()
        return cls(
            model="deepseek/deepseek-v4-flash",
            openai_api_key="sk-fake",
            temperature=0.7,
            max_tokens=500,
        )

    def test_reasoning_content_re_injected(self) -> None:
        """An AIMessage with reasoning_content in additional_kwargs
        has it re-injected into the serialized message dict."""
        model = self._build_model()

        messages = [
            HumanMessage(content="hello"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_fastsearch",
                        "args": {"queries": ["test"]},
                        "id": "tc-1",
                    },
                ],
                additional_kwargs={
                    "reasoning_content": "Let me search for that.",
                },
            ),
            ToolMessage(
                content="search results", tool_call_id="tc-1",
            ),
        ]

        with patch.object(
            model,
            "_get_request_payload",
            wraps=model._get_request_payload,
        ) as wrapped:
            # Calling with messages triggers payload building.
            # We test by calling the method directly since invoke()
            # requires a real API connection.
            payload = wrapped(messages)

        msg_dicts = payload["messages"]
        # Find the assistant message dict.
        assistant = None
        for d in msg_dicts:
            if d.get("role") == "assistant":
                assistant = d
                break

        assert assistant is not None, "No assistant message in payload"
        assert "reasoning_content" in assistant, (
            f"reasoning_content missing: {list(assistant.keys())}"
        )
        assert assistant["reasoning_content"] == "Let me search for that."

    def test_no_reasoning_content_not_added(self) -> None:
        """An AIMessage WITHOUT reasoning_content in additional_kwargs
        does not get a reasoning_content key added."""
        model = self._build_model()

        messages = [
            HumanMessage(content="hello"),
            AIMessage(content="hi there!"),
        ]

        payload = model._get_request_payload(messages)

        for d in payload["messages"]:
            if d.get("role") == "assistant":
                assert "reasoning_content" not in d, (
                    f"reasoning_content should not be present: "
                    f"{list(d.keys())}"
                )

    def test_non_ai_messages_unaffected(self) -> None:
        """HumanMessage, SystemMessage, and ToolMessage are passed
        through without modification."""
        model = self._build_model()

        messages = [
            SystemMessage(content="you are a bot"),
            HumanMessage(content="hello"),
            ToolMessage(content="result", tool_call_id="x"),
        ]

        payload = model._get_request_payload(messages)

        roles = {d["role"] for d in payload["messages"]}
        assert "user" in roles
        assert "system" in roles
        assert "tool" in roles
        for d in payload["messages"]:
            if d.get("role") != "assistant":
                assert "reasoning_content" not in d
