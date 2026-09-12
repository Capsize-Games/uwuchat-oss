"""Classification model invocation for the tool classification mixin."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from langchain_core.messages import HumanMessage


class ToolClassificationInvocationMixin:
    """Invoke the classification model and select the right model."""

    def _invoke_classification_response(
        self,
        chat_model: Any,
        classification_prompt: str,
    ) -> Tuple[Optional[str], str]:
        """Return one non-streamed classification response."""
        from airunner_services.data.tenant import get_tenant_key
        from airunner_services.llm.token_usage import (
            record_background_usage,
        )
        from airunner_services.llm.pipeline_loader import pipeline_config
        # ---- PII masking before LLM egress ----
        vault = getattr(self, "_pii_vault", None)
        if vault is not None:
            from airunner_services.llm.pii.masker import mask_text
            classification_prompt = mask_text(classification_prompt, vault)
        # ---- end PII ----
        response = chat_model.invoke(
            [HumanMessage(content=classification_prompt)]
        )
        record_background_usage(
            "TOOL_CLASSIFICATION",
            pipeline_config("TOOL_CLASSIFICATION"),
            response,
            chatbot_id=getattr(
                getattr(self, "chatbot", None), "id", None
            ),
            tenant_key=get_tenant_key(),
            call_chain_id=getattr(self, "_call_chain_id", None),
        )
        return self._split_classification_response(
            getattr(response, "content", "") or "",
            getattr(response, "additional_kwargs", {}) or {},
        )

    def _get_classification_model(self):
        """Return the chat model to use for tool classification.

        Prefers a TOOL_CLASSIFICATION-routed model when one has been
        pre-built by the component loader; falls back to the primary
        workflow chat model.
        """
        specialized = getattr(self, "_specialized_chat_models", {})
        return specialized.get("TOOL_CLASSIFICATION") or (
            getattr(self._workflow_manager, "_original_chat_model", None)
            if self._workflow_manager
            else None
        )
