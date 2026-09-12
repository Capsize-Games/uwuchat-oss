"""Classifier response parsing for the tool classification mixin."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from airunner_services.llm.thinking_parser import (
    extract_thinking_and_response,
)


class ToolClassificationParsingMixin:
    """Parse raw classifier responses into thinking text and categories."""

    @staticmethod
    def _split_classification_response(
        response_text: str,
        additional_kwargs: Optional[dict] = None,
    ) -> Tuple[Optional[str], str]:
        """Return classifier thinking text and visible category text."""
        reasoning_text = ""
        if additional_kwargs:
            reasoning_text = additional_kwargs.get("reasoning_content") or ""
        tagged_thinking, visible_text = extract_thinking_and_response(
            response_text
        )
        if tagged_thinking and not reasoning_text:
            reasoning_text = tagged_thinking
        cleaned_thinking = reasoning_text.strip() or None
        return cleaned_thinking, visible_text

    @staticmethod
    def _classification_candidates(response_text: str) -> list[str]:
        """Return normalized classifier candidates without assistant labels."""
        normalized = re.sub(
            r"categories:\s*[a-z,\s]+",
            "",
            (response_text or "").strip().lower(),
            flags=re.IGNORECASE,
        )
        candidates = []
        for line in normalized.splitlines():
            candidate = line.strip()
            if candidate in {"", "assistant", "assistant:"}:
                continue
            if candidate.startswith("assistant:"):
                candidate = candidate[len("assistant:") :].strip()
            elif candidate.startswith("assistant "):
                candidate = candidate[len("assistant ") :].strip()
            if candidate:
                candidates.append(candidate)
        return candidates or ([normalized] if normalized else [])

    @staticmethod
    def _parse_selected_categories(
        candidate_text: str,
        available_categories: list[str],
    ) -> list[str]:
        """Parse one normalized classifier response into tool categories."""
        selected_categories = []
        for cat in candidate_text.split(","):
            token = cat.strip()
            if (
                token in available_categories
                and token not in selected_categories
            ):
                selected_categories.append(token)
        if selected_categories:
            return selected_categories[:5]
        for token in candidate_text.replace(",", " ").split():
            token_clean = token.strip().strip(".;:")
            if (
                token_clean in available_categories
                and token_clean not in selected_categories
            ):
                selected_categories.append(token_clean)
        return selected_categories[:5]
