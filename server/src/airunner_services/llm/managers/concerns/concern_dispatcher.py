"""Parallel concern dispatcher using ThreadPoolExecutor."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from airunner_services.llm.managers.concerns.base_concern import (
    BaseConcern,
)

logger = logging.getLogger(__name__)


class ConcernDispatcher:
    """Runs all registered concerns in parallel, returning fired results.

    Attributes:
        concerns: Ordered list of concern classifiers.
        model: The fast TOOL_CLASSIFICATION model shared by all concerns.
    """

    def __init__(
        self,
        concerns: list[BaseConcern],
        model: Any,
    ) -> None:
        """Store concerns and the shared fast model."""
        self._concerns = concerns
        self._model = model

    def dispatch(
        self,
        user_message: str,
        context: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Run all concerns in parallel; return ``(tool_name, args)`` pairs.

        Each concern that fires contributes one tuple to the result.
        Order matches the registration order of the concerns list.
        """
        if not self._concerns:
            return []

        results: list[tuple[int, str, dict[str, Any]]] = []
        with ThreadPoolExecutor(max_workers=len(self._concerns)) as ex:
            future_map = {
                ex.submit(
                    concern.classify,
                    user_message,
                    context,
                    self._model,
                ): idx
                for idx, concern in enumerate(self._concerns)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    should_fire, args = future.result()
                except Exception:
                    logger.warning(
                        "Concern %d failed; skipping", idx
                    )
                    continue
                if should_fire:
                    results.append(
                        (
                            idx,
                            self._concerns[idx].tool_name,
                            args,
                        )
                    )

        # Restore registration order.
        results.sort(key=lambda r: r[0])
        return [(name, args) for _, name, args in results]
