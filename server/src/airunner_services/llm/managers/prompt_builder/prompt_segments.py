"""Multi-segment prompt structure for Anthropic cache breakpoints.

Provides PromptSegments (three volatility tiers) and the builder
that populates them from owner/action state.  Extracted from
parts.py to keep each file under the 250-line limit.

Imports all part-function dependencies directly (not through
parts.py) to avoid circular imports.
"""

from __future__ import annotations
from dataclasses import dataclass, field

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    CONVERSATIONAL_ACTIONS,
)
from airunner_services.llm.managers.prompt_builder.feelings import (
    belief_part,
    inner_state_constraint_part,
    relationship_part,
    specificity_forcing_part,
    voice_lock_part,
)
from airunner_services.llm.managers.prompt_builder.identity_parts import (
    _is_rp_mode,
    identity_parts as _identity_parts,
)
from airunner_services.llm.managers.prompt_builder.knowledge_horizon import (
    knowledge_horizon_part as _knowledge_horizon_part,
)
from airunner_services.llm.managers.prompt_builder.orchestration_hint import (
    orchestration_hint_part as _orchestration_instructions_part,
)


@dataclass
class PromptSegments:
    """Three volatility-tiered segments for multi-breakpoint caching.

    Segment A is session-stable (identity, language, horizon, etc.).
    Segment B depends only on risk tier.
    Segment C depends on token-budget tier (base / standard / full).
    """
    segment_a: list[str] = field(default_factory=list)
    segment_b: list[str] = field(default_factory=list)
    segment_c: list[str] = field(default_factory=list)

    def all_parts(self) -> list[str]:
        """Return all non-empty parts in A→B→C order (backward compat)."""
        return self.segment_a + self.segment_b + self.segment_c


def build_base_prompt_segments(
    owner, action: LLMActionType
) -> PromptSegments:
    """Return prompt parts grouped by volatility for multi-breakpoint
    Anthropic prompt caching.

    Segment A — session-stable: identity, language, knowledge horizon,
        orchestration hint, topic-change rule.  Cache hit expected on
        every turn of a session.
    Segment B — risk-tier-dependent: hard rules toggle on
        owner._risk_tier == "innocuous".  Cache hit whenever risk
        classification repeats consecutively.
    Segment C — token-budget-tier-dependent: all tier-gated blocks
        (core rules, agent memory, episodic summary, UI context,
        style, RP feeling parts, memory, health disclaimer).
        Cache hit whenever tier repeats consecutively — i.e. most of
        a session, since tier flips only at two threshold crossings.
    """
    # Deferred imports to avoid circularity — these live in parts.py
    # which imports PromptSegments from this module.
    from airunner_services.llm.managers.prompt_builder.parts import (
        _agent_memory_part,
        _append_if_present,
        _episodic_summary_part,
        _hard_rules_part,
        _health_disclaimer_part,
        _language_part,
        _memory_part,
        _prompt_tier,
        _style_part,
        _system_bot_core_rules_part,
        _topic_change_rule_part,
        _ui_context_part,
    )

    tier = _prompt_tier(owner)
    seg = PromptSegments()

    # Segment A — session-stable parts (always present)
    seg.segment_a.extend(_identity_parts(owner, action))
    _append_if_present(
        seg.segment_a, _topic_change_rule_part(owner)
    )
    _append_if_present(seg.segment_a, _language_part(owner))
    _append_if_present(
        seg.segment_a, _knowledge_horizon_part(owner)
    )
    _append_if_present(
        seg.segment_a, _orchestration_instructions_part(owner)
    )

    # Segment B — risk-tier-dependent (hard rules)
    _append_if_present(
        seg.segment_b, _hard_rules_part(owner)
    )

    # Segment C — token-budget-tier-dependent blocks
    if tier == "base":
        _append_if_present(
            seg.segment_c, _system_bot_core_rules_part(owner)
        )
        return seg
    _append_if_present(
        seg.segment_c, _agent_memory_part(owner)
    )
    _append_if_present(
        seg.segment_c, _episodic_summary_part(owner)
    )
    _append_if_present(
        seg.segment_c, _ui_context_part(owner, action)
    )
    _append_if_present(
        seg.segment_c, _style_part(owner, action)
    )
    if _is_rp_mode(owner) and action in CONVERSATIONAL_ACTIONS:
        _append_if_present(
            seg.segment_c, voice_lock_part(owner)
        )
        _append_if_present(
            seg.segment_c, inner_state_constraint_part(owner)
        )
        _append_if_present(
            seg.segment_c, belief_part(owner)
        )
        _append_if_present(
            seg.segment_c, relationship_part(owner)
        )
        seg.segment_c.append(specificity_forcing_part())
    if tier == "standard":
        return seg
    _append_if_present(seg.segment_c, _memory_part(action))
    _append_if_present(
        seg.segment_c, _health_disclaimer_part(owner)
    )
    return seg
