"""Tests for node_topic_shift — topic-shift detection and annotation."""

from __future__ import annotations

from airunner_services.llm.managers.mixins.node_topic_shift import (
    detect_topic_shift,
    topic_shift_annotation,
)
from langchain_core.messages import HumanMessage


def test_system_bot_annotation_is_compliance_oriented() -> None:
    """System bot annotation tells the model to answer directly."""
    note = topic_shift_annotation(is_system_bot=True)
    assert "answer the new one directly" in note
    assert "evaluate whether prior context applies" not in note


def test_roleplay_annotation_explicit_false() -> None:
    """Roleplay bot annotation contains the original caution wording."""
    note = topic_shift_annotation(is_system_bot=False)
    assert "Evaluate whether prior context" in note
    assert "answer the new one directly" not in note


def test_roleplay_annotation_default() -> None:
    """Default (no argument) returns the original roleplay note."""
    note = topic_shift_annotation()
    assert "Evaluate whether prior context" in note
    assert "answer the new one directly" not in note


def test_detect_topic_shift_no_messages() -> None:
    """Empty message list does not trigger a topic shift."""
    assert detect_topic_shift([]) is False


def test_detect_topic_shift_single_message() -> None:
    """A single message does not trigger a topic shift."""
    assert detect_topic_shift([HumanMessage(content="hello")]) is False


def test_detect_topic_shift_unrelated_topics() -> None:
    """Completely unrelated topics should be detected as a shift."""
    messages = [
        HumanMessage(content="The politics in Colorado are really "
                     "interesting these days with all the new legislation."),
        HumanMessage(content="Can you explain the quadratic formula "
                     "and show it in LaTeX format please?"),
    ]
    assert detect_topic_shift(messages) is True


def test_detect_topic_shift_same_topic() -> None:
    """A follow-up on the same topic should not be detected as a shift."""
    messages = [
        HumanMessage(content="Tell me about Python decorators."),
        HumanMessage(content="How are Python decorators different "
                     "from context managers?"),
    ]
    assert detect_topic_shift(messages) is False
