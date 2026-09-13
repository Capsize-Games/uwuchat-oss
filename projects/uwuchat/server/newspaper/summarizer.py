"""LLM-quality article summarization for the newspaper system.

Uses the SUMMARIZATION pipeline model from :mod:`ai_pipeline`
to generate concise, abstractive summaries on demand.
"""

from __future__ import annotations

import logging
import os

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL

logger = logging.getLogger(__name__)

_SUMMARIZE_SYSTEM_PROMPT = (
    "You are a precise news summarizer. Write 1-2 concise sentences "
    "capturing the key facts. Do not add commentary, opinions, or "
    "phrases like 'This article discusses'. Just state the facts."
)

_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class ArticleSummarizer:
    """LLM-quality article summarization.

    Calls the SUMMARIZATION pipeline model (configured in
    :mod:`ai_pipeline`) via OpenRouter to produce abstractive
    1-2 sentence summaries.
    """

    def __init__(self, model: str | None = None) -> None:
        """Initialise the summarizer.

        Args:
            model: OpenRouter model string.  Defaults to the
                SUMMARIZATION pipeline model from ``ai_pipeline``,
                or ``"meta-llama/llama-3.1-8b-instruct"`` as a
                last resort.
        """
        self._model = model or self._resolve_model()
        self._api_key = os.environ.get(
            "OPENROUTER_API_KEY",
            os.environ.get("LLM_API_KEY", ""),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def summarize_text(
        self,
        text: str,
        max_sentences: int = 2,
    ) -> str:
        """Generate a short summary of *text*.

        Args:
            text: The article or passage to summarise.
            max_sentences: Maximum number of sentences in the summary.

        Returns:
            Summary string, or the first 200 chars of *text* on failure.
        """
        if not text.strip():
            return ""
        if not self._api_key:
            return _fallback_summary(text)

        prompt = (
            f"Summarize this article in {max_sentences} sentence(s). "
            f"Return ONLY the summary, nothing else.\n\n{text[:4000]}"
        )
        try:
            summary = await self._call_openrouter(prompt)
            return summary.strip() or _fallback_summary(text)
        except Exception:
            logger.exception("LLM summarization failed, using fallback")
            return _fallback_summary(text)

    async def summarize_url(self, url: str) -> str:
        """Fetch *url* content then summarise it.

        Args:
            url: The article URL to fetch and summarise.

        Returns:
            Summary string, or an error message on failure.
        """
        try:
            from extensions.fastsearch.server.provider import (
                FastSearchProvider,
            )

            provider = FastSearchProvider()
            data = await provider.scrape_url(url)
            if "error" in data:
                return f"Could not read URL: {data['error']}"
            content = data.get("content", "")
            if not content:
                return "No content found at that URL."
            return await self.summarize_text(content)
        except Exception:
            logger.exception("summarize_url failed for %s", url)
            return "Could not summarise that URL."

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_model() -> str:
        """Return the SUMMARIZATION pipeline model, or a default."""
        try:
            from airunner_services.llm.pipeline_loader import pipeline_config

            summ = pipeline_config("SUMMARIZATION")
            model = summ.get("model")
            if model:
                return model
        except Exception:
            pass
        return META_LLAMA_INSTRUCT_MODEL

    async def _call_openrouter(self, user_prompt: str) -> str:
        """Make a single-turn chat completion call to OpenRouter."""
        import aiohttp

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 150,
            "temperature": 0.3,
        }
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                _OPENROUTER_API_URL,
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                self._record_summarization_usage(data)
                return data["choices"][0]["message"]["content"]

    def _record_summarization_usage(self, data: dict) -> None:
        """Fire-and-forget token usage recording for SUMMARIZATION."""
        try:
            usage = data.get("usage", {}) if isinstance(data, dict) else {}
            if not usage:
                return
            from airunner_services.llm.token_usage import record_usage
            from airunner_services.llm.active_call_chain import (
                get_active_call_chain,
            )

            record_usage(
                pipeline_key="SUMMARIZATION",
                model_id=self._model,
                input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                output_tokens=int(
                    usage.get("completion_tokens", 0) or 0
                ),
                call_chain_id=get_active_call_chain(),
            )
        except Exception:
            pass


def _fallback_summary(text: str, max_chars: int = 200) -> str:
    """Return the first *max_chars* of *text* as a fallback summary."""
    clean = text.strip()
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rsplit(" ", 1)[0] + "..."
