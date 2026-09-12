"""Regression eval: core rules survive when prompt tier drops to base.

When a conversation contains a large tool/search result followed by a
short follow-up, the prompt tier can drop to ``"base"`` which
historically dropped the entire ``_style_part()`` block — including all
anti-stall-phrase rules, tool-use priority instructions, and the
anti-recitation guardrail.  This test asserts that those critical rules
now survive at every tier.
"""

from __future__ import annotations

from unittest.mock import MagicMock


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_large_tool_result() -> str:
    """Return a realistic ~10 KB tool result simulating a search/newspaper."""
    paragraph = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna."
    ) * 20  # ~2 KB
    return (paragraph + "\n") * 5  # ~10 KB


def _make_owner(is_system_bot: bool = True):
    """Build a mock owner with the given remaining token estimate."""
    owner = MagicMock()
    owner.chatbot.is_system_bot = is_system_bot
    owner.chatbot.botname = "UwU"
    owner.chatbot.use_personality = False
    owner.chatbot.bot_personality = ""
    owner._workflow_manager._max_history_tokens = 4096
    # Simulate a realistic used-token count from a large tool result.
    # With 4096 budget and ~3500 tokens used, remaining ≈ 596 → base tier.
    owner._workflow_manager._token_counter = (
        lambda msgs: 3500
    )
    owner._workflow_manager._memory._checkpoint_state = {
        "thread-1": {
            "messages": [
                MagicMock(content="x" * 11000),
                MagicMock(content="what about chicago?"),
            ]
        }
    }
    owner._workflow_manager._thread_id = "thread-1"
    return owner


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_core_rules_survive_at_base_tier():
    """Core behavioral rules appear even when tier is ``"base"``."""
    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.parts import (
        build_base_prompt_parts,
    )

    owner = _make_owner()
    parts = build_base_prompt_parts(owner, LLMActionType.CHAT)
    joined = "\n".join(str(p) for p in parts)

    # Core identity
    assert "You are UwU" in joined
    # Anti-stall rules
    assert "CALL THE TOOL IMMEDIATELY" in joined
    # Anti-recitation guardrail (Phase 4c)
    assert "operating instructions, not talking points" in joined
    # Disambiguation rule (Phase 2b)
    assert "do NOT treat the earlier newspaper digest as exhaustive" in joined


def test_core_rules_no_false_positive_on_rp_bot():
    """Core rules are NOT injected for non-system-bot chatbots."""
    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.parts import (
        build_base_prompt_parts,
    )

    owner = _make_owner(is_system_bot=False)
    parts = build_base_prompt_parts(owner, LLMActionType.CHAT)
    joined = "\n".join(str(p) for p in parts)

    assert "CALL THE TOOL IMMEDIATELY" not in joined
    assert "operating instructions, not talking points" not in joined


def test_examples_dropped_at_base_tier():
    """Few-shot examples are NOT present at ``"base"`` tier."""
    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.parts import (
        build_base_prompt_parts,
    )

    owner = _make_owner()
    parts = build_base_prompt_parts(owner, LLMActionType.CHAT)
    joined = "\n".join(str(p) for p in parts)

    # The expensive few-shot examples should be absent at base tier
    assert "Example 1 — echoing" not in joined


def test_examples_present_at_full_tier():
    """Few-shot examples ARE present when tier is ``"full"``."""
    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.parts import (
        build_base_prompt_parts,
    )

    owner = _make_owner()
    # Override token counter to simulate plenty of budget → full tier
    owner._workflow_manager._token_counter = lambda msgs: 500
    parts = build_base_prompt_parts(owner, LLMActionType.CHAT)
    joined = "\n".join(str(p) for p in parts)

    assert "Example 1 — echoing" in joined
    assert "CALL THE TOOL IMMEDIATELY" in joined


def test_topic_change_directive_precedes_core_rules():
    """The CRITICAL topic-change directive is assembled before
    core_rules/style — it used to be bundled inside core_rules, which
    is placed after the agent-memory and episodic-summary blocks.
    Reading it only after those blocks defeats the point of stating
    it prominently, so it now has its own earlier slot."""
    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.parts import (
        build_base_prompt_parts,
    )

    owner = _make_owner()
    owner._workflow_manager._token_counter = lambda msgs: 500
    parts = build_base_prompt_parts(owner, LLMActionType.CHAT)
    joined = "\n".join(str(p) for p in parts)

    assert "CRITICAL — TOPIC CHANGES ARE NORMAL" in joined
    assert "You are UwU. You run UwUchat" in joined
    assert joined.index("CRITICAL — TOPIC CHANGES ARE NORMAL") < joined.index(
        "You are UwU. You run UwUchat"
    )


def test_topic_change_directive_absent_for_rp_bot():
    """The topic-change directive is system-bot only."""
    from airunner_services.contract_enums import LLMActionType
    from airunner_services.llm.managers.prompt_builder.parts import (
        build_base_prompt_parts,
    )

    owner = _make_owner(is_system_bot=False)
    parts = build_base_prompt_parts(owner, LLMActionType.CHAT)
    joined = "\n".join(str(p) for p in parts)

    assert "CRITICAL — TOPIC CHANGES ARE NORMAL" not in joined
