"""Lazy singleton wrapping Presidio ``AnalyzerEngine``.

spaCy model load is expensive — do not reload per request.
Uses ``en_core_web_sm`` by default (smaller Docker footprint).
Swap to ``en_core_web_lg`` for higher NER recall if size budget allows.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from airunner_services.llm.pii.entities import MIN_CONFIDENCE, SUPPORTED_ENTITIES

logger = logging.getLogger(__name__)


class _AnalyzerSingleton:
    """Process-wide lazy holder for Presidio engines."""

    def __init__(self) -> None:
        self._analyzer: Any = None
        self._anonymizer: Any = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Import and instantiate Presidio engines (once).

        Uses ``en_core_web_sm`` (smallest spaCy model — good recall/size
        trade-off for Docker deployments).  Swap the ``model_name`` in
        the NlpEngineProvider configuration below to ``en_core_web_lg``
        for higher NER recall if image size budget allows.
        """
        if self._loaded:
            return
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            from presidio_anonymizer import AnonymizerEngine

            provider = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [
                        {
                            "lang_code": "en",
                            "model_name": "en_core_web_sm",
                        },
                    ],
                },
            )
            nlp_engine = provider.create_engine()
            self._analyzer = AnalyzerEngine(
                nlp_engine=nlp_engine,
                default_score_threshold=MIN_CONFIDENCE,
            )
            self._anonymizer = AnonymizerEngine()
            self._loaded = True
            logger.info(
                "Presidio engines initialised (entities=%s, "
                "min_confidence=%.2f)",
                SUPPORTED_ENTITIES,
                MIN_CONFIDENCE,
            )
        except (ImportError, OSError, TypeError) as exc:
            logger.warning(
                "Presidio not available — PII masking disabled: %s", exc,
            )
            self._loaded = True
            self._analyzer = None
            self._anonymizer = None

    def analyze(
        self, text: str, language: str = "en"
    ) -> list[dict[str, Any]]:
        """Run Presidio analysis and return recognised entity spans.

        Each result dict has keys: ``entity_type``, ``start``, ``end``,
        ``score``, ``analysis_explanation``.
        """
        self._ensure_loaded()
        if self._analyzer is None:
            return []
        try:
            results = self._analyzer.analyze(
                text=text,
                language=language,
                entities=list(SUPPORTED_ENTITIES),
                score_threshold=MIN_CONFIDENCE,
            )
        except Exception:
            logger.exception("Presidio analysis failed for %d-char text", len(text))
            return []
        return [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": r.score,
            }
            for r in results
        ]


_analyzer: Optional[_AnalyzerSingleton] = None


def get_analyzer() -> _AnalyzerSingleton:
    """Return the process-wide Presidio analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = _AnalyzerSingleton()
    return _analyzer
