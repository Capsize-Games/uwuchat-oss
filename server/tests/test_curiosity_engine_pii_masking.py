"""Integration test: PII masking in generate_session_curiosity().

Proves that KnowledgeFact rows and conversation text are masked
before being sent to the OpenRouter model in the curiosity engine
path.  This path is disconnected from CloudModelManager, so it
needs its own standalone PII masking.

Mutation-test proof: remove the masking block from
generate_session_curiosity(), rerun, confirm failure; restore,
confirm pass.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ["AIRUNNER_PII_MASKING_ENABLED"] = "1"

_TEST_EMAIL = "alice.johnson@example.com"


@pytest.mark.timeout(15)
def test_curiosity_engine_masks_pii_before_llm() -> None:
    """generate_session_curiosity() must mask PII in fact/conversation
    text before chat_model.invoke()."""

    from langchain_core.messages import AIMessage

    # Capture what was sent to chat_model.invoke().
    captured_messages: list = []

    def _capture_invoke(messages, **__):
        captured_messages.extend(messages)
        # Return a simple question (curiosity output doesn't contain PII).
        return AIMessage(
            content='{"entity":"Alice","missing":"email","question":"What is your email?"}'
        )

    mock_model = MagicMock()
    mock_model.invoke.side_effect = _capture_invoke

    with patch(
        "airunner_services.cloud.llm.model_builders.create_openrouter_model",
        return_value=mock_model,
    ), patch(
        "airunner_services.llm.curiosity_engine._load_facts",
        return_value=f"User email: {_TEST_EMAIL}\nUser phone: 555-1234",
    ), patch(
        "airunner_services.llm.pipeline_loader.is_enabled",
        return_value=True,
    ), patch(
        "airunner_services.database.models.conversation.Conversation",
    ) as mock_conv:
        # Return a conversation with PII in it.
        mock_conv.objects.query.return_value.filter.return_value.all.return_value = [
            MagicMock(
                value=[
                    {
                        "role": "user",
                        "content": f"My email is {_TEST_EMAIL}",
                        "metadata_type": None,
                    },
                    {"role": "assistant", "content": "Thanks!", "metadata_type": None},
                ]
            )
        ]

        from airunner_services.llm.curiosity_engine import (
            generate_session_curiosity,
        )

        generate_session_curiosity(session_id=1, chatbot_id=1)

    # The email must NOT appear in the outbound messages.
    outbound_text = " ".join(
        getattr(m, "content", "") or "" for m in captured_messages
    )
    assert _TEST_EMAIL not in outbound_text, (
        f"PII email leaked in curiosity engine outbound: {outbound_text[:300]}"
    )
