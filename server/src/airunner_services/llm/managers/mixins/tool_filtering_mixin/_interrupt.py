"""Interrupt and section-change handling.

Extracted from ``ToolFilteringMixin``.  Interrupts ongoing generation
on both the chat model and the workflow manager, and handles section
changes by clearing history.
"""

from __future__ import annotations


class ToolFilterInterruptMixin:
    """Interrupt and lifecycle helpers for the tool filter."""

    def do_interrupt(self) -> None:
        """Interrupt ongoing generation."""
        self.logger.info("do_interrupt called on instance %s", id(self))
        self._interrupted = True

        if self._chat_model and hasattr(self._chat_model, "set_interrupted"):
            self.logger.info(
                "Setting interrupt on chat_model %s",
                id(self._chat_model),
            )
            self._chat_model.set_interrupted(True)
        else:
            self.logger.warning(
                "Chat model not available or missing set_interrupted: %s",
                self._chat_model,
            )

        if self._workflow_manager and hasattr(
            self._workflow_manager,
            "set_interrupted",
        ):
            self.logger.info(
                "Setting interrupt on workflow_manager %s",
                id(self._workflow_manager),
            )
            self._workflow_manager.set_interrupted(True)
        else:
            self.logger.warning(
                "Workflow manager not available: %s",
                self._workflow_manager,
            )

    def on_section_changed(self) -> None:
        """Handle section change events."""
        self.logger.info("Section changed, clearing history")
        self.clear_history()
