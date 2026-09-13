"""Abstract base class for concern classifiers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


class BaseConcern(ABC):
    """One independent concern classifier in the scatter-gather pipeline.

    Each subclass decides whether its tool should fire for a given
    user message and returns the tool arguments when it should.
    """

    tool_name: str

    def classify(
        self,
        user_message: str,
        context: str,
        model: Any,
    ) -> tuple[bool, dict[str, Any]]:
        """Return ``(should_fire, tool_args)``. Never raises."""
        try:
            prompt = self._build_prompt(user_message, context)
            text = self._call_classifier(prompt, model)
            return self._parse(text)
        except Exception as exc:
            logger.warning(
                "%s classify error: %s", self.__class__.__name__, exc
            )
            return False, {}

    def _call_classifier(self, prompt: str, model: Any) -> str:
        """Call the fast model; return text or '' on error."""
        if model is None:
            return ""
        try:
            response = model.invoke([HumanMessage(content=prompt)])
            return str(getattr(response, "content", "") or "").strip()
        except Exception as exc:
            logger.warning(
                "%s model call error: %s",
                self.__class__.__name__,
                exc,
            )
            return ""

    @abstractmethod
    def _build_prompt(self, user_message: str, context: str) -> str:
        """Build the classifier prompt for this concern."""
        ...

    @abstractmethod
    def _parse(self, text: str) -> tuple[bool, dict[str, Any]]:
        """Parse the classifier response into (should_fire, tool_args)."""
        ...
