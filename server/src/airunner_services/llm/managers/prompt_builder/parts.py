"""Part-building helpers for system prompt tiers."""
from __future__ import annotations
import importlib
import logging
import os
from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.prompt_segments import (
    PromptSegments,
    build_base_prompt_segments,
)
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    CONVERSATIONAL_ACTIONS,
    HARD_RULES,
    HEALTH_DISCLAIMER,
    MEMORY_ACTIONS,
    MEMORY_INSTRUCTIONS,
    RP_STYLE_GUIDELINES,
    STYLE_GUIDELINES,
    UI_CONTEXT_ACTIONS,
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

_logger = logging.getLogger(__name__)

# ── Language label lookup ──────────────────────────────────────
_LANG_LABELS: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "id": "Indonesian",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
    "pl": "Polish",
}

# ── Proficiency directives for RP output language ─────────────
_PROFICIENCY_DIRECTIVES: dict[str, str] = {
    "intermediate": (
        "Write with occasional unnatural phrasing or mild "
        "grammatical errors as a non-native speaker would."
    ),
    "beginner": (
        "Write with frequent grammatical errors, simple "
        "vocabulary, and short sentences as a beginner "
        "speaker would."
    ),
    "broken": (
        "Write in broken language: minimal grammar, heavy "
        "errors, mixed with the character's native language."
    ),
}


def _lang_label(code: str) -> str:
    """Return the human-readable language name for an ISO 639-1 code."""
    return _LANG_LABELS.get(code, code)


def _effective_output_language(owner) -> Optional[str]:
    """Resolve the effective output language for the current chatbot.

    Precedence:
      1. chatbot.output_language (per-character override)
      2. LanguageSettings.bot_language (UwU Language)
    """
    chatbot = getattr(owner, "chatbot", None)
    if chatbot is not None:
        char_lang = getattr(chatbot, "output_language", None)
        if char_lang:
            return char_lang
    ls = getattr(owner, "language_settings", None)
    if ls is not None:
        bot_lang = getattr(ls, "bot_language", None)
        if bot_lang:
            return bot_lang
    return None


def _language_part(owner) -> Optional[str]:
    """Return the language directive for the system prompt.

    Injects directives telling the LLM the user's language and what
    language to respond in.  Skipped when both are English.
    """
    ls = getattr(owner, "language_settings", None)
    user_lang = getattr(ls, "user_language", None) if ls else None
    # Resolve bot language through the effective precedence chain
    bot_lang = _effective_output_language(owner)
    if not user_lang and not bot_lang:
        return None
    lines: list[str] = []
    if user_lang and user_lang != "en":
        lines.append(
            f"The user communicates in {_lang_label(user_lang)} "
            f"({user_lang}). Understand their messages even if "
            f"they mix languages or use informal spelling."
        )
    if bot_lang and bot_lang != "en":
        lines.append(
            f"Write all your replies in {_lang_label(bot_lang)} "
            f"({bot_lang})."
        )
    return "\n".join(lines) if lines else None


def build_base_prompt_parts(
    owner, action: LLMActionType
) -> list[str]:
    """Return the STABLE prompt parts for one action (flat list).

    Delegates to build_base_prompt_segments() and flattens all
    segments into a single list for backward compatibility with
    callers that do not need segment-level cache control.

    Dynamic per-turn content (datetime, mood, preflight) is intentionally
    absent. It is injected into the human turn by collect_per_turn_context()
    so the system prompt stays identical across requests and the provider
    prefix cache (e.g. DeepSeek) is never busted.
    """
    return build_base_prompt_segments(owner, action).all_parts()


def _prompt_tier(owner) -> str:
    """Return the prompt tier based on estimated remaining context tokens.

    The risk classifier may cap this to a lower tier.  See _risk_cap().

    Diagnostic logging: the tier directly determines which sections
    build_base_prompt_parts() includes (see its docstring/branches), so
    a tier flip between turns is a structural change to the "stable"
    system prompt, not just a small string change -- it fully busts the
    provider prompt-caching prefix. Logged here to make that visible.
    """
    remaining = _estimate_remaining_context_tokens(owner)
    token_tier = _token_budget_tier_from_remaining(remaining)
    risk_cap = _risk_cap(owner)
    tier_order = ["base", "standard", "full"]
    tier = tier_order[
        min(
            tier_order.index(token_tier),
            tier_order.index(risk_cap),
        )
    ]
    _logger.info(
        "[PROMPT TIER] tier=%s token_tier=%s risk_cap=%s "
        "remaining_context_tokens=%s",
        tier,
        token_tier,
        risk_cap,
        remaining,
    )
    return tier


def _token_budget_tier(owner) -> str:
    """Return the prompt tier based on estimated remaining context tokens."""
    return _token_budget_tier_from_remaining(
        _estimate_remaining_context_tokens(owner)
    )


def _token_budget_tier_from_remaining(remaining: int) -> str:
    """Return the prompt tier for an already-computed remaining-token count."""
    if remaining < 2000:
        return "base"
    if remaining < 4000:
        return "standard"
    return "full"


def _risk_cap(owner) -> str:
    """Return the maximum prompt tier allowed by the current risk level.

    Reads the pre-computed risk tier from the owner object (set by the
    cloud LLM worker before prompt building starts).  Falls back to
    'full' if not set (safe default, includes all safety layers).
    """
    risk = getattr(owner, "_risk_tier", "moderate")
    caps = {
        "innocuous": "standard",
        "low": "standard",
        "moderate": "full",
        "high": "full",
    }
    return caps.get(risk, "full")


def _estimate_remaining_context_tokens(owner) -> int:
    """Return remaining token estimate or a large sentinel when unavailable."""
    try:
        wm = getattr(owner, "_workflow_manager", None)
        if wm is None:
            return 999999
        max_tokens = getattr(wm, "_max_history_tokens", 0) or 8000
        memory = getattr(wm, "_memory", None)
        thread_id = getattr(wm, "_thread_id", None)
        if not memory or not thread_id:
            return max_tokens
        state = getattr(memory, "_checkpoint_state", {}).get(thread_id)
        if not state:
            return max_tokens
        messages = state.get("messages", [])
        token_counter = getattr(wm, "_token_counter", None)
        if callable(token_counter) and messages:
            used = token_counter(messages)
        else:
            from langchain_core.messages.utils import (
                count_tokens_approximately,
            )
            used = count_tokens_approximately(messages)
        return max(0, int(max_tokens) - int(used))
    except Exception:
        return 999999


def _hard_rules_part(owner) -> Optional[str]:
    """Return HARD_RULES when in RP mode, skipping for innocuous messages."""
    if not _is_rp_mode(owner):
        return None
    risk = getattr(owner, "_risk_tier", "moderate")
    if risk == "innocuous":
        return None
    return HARD_RULES


def _render_template(text: str, owner) -> str:
    """Substitute {{variable}} placeholders in prompt text."""
    if "{{" not in text:
        return text
    variables = _template_variables(owner)
    import re

    def _replace(m: re.Match) -> str:
        key = m.group(1).strip()
        return variables.get(key, m.group(0))

    return re.sub(r"\{\{\s*(\w+)\s*\}\}", _replace, text)


def _template_variables(owner) -> dict:
    """Return the current set of template variables for the owner."""
    username = "User"
    user = getattr(owner, "user", None)
    if user is not None:
        username = getattr(user, "username", None) or "User"
    return {"username": username}


def _ui_context_part(owner, action: LLMActionType) -> Optional[str]:
    """Return the UI context prompt part when the action needs it."""
    if action not in UI_CONTEXT_ACTIONS:
        return None
    ui_context = owner._get_ui_section_context()
    return ui_context or None


def _proficiency_directive(owner) -> Optional[str]:
    """Return the output-language proficiency directive for RP mode.

    Only emits a directive when language_proficiency is not 'fluent'
    (fluent is the LLM default and needs no instruction).
    """
    chatbot = getattr(owner, "chatbot", None)
    if chatbot is None:
        return None
    prof = getattr(chatbot, "language_proficiency", "fluent") or "fluent"
    if prof == "fluent":
        return None
    directive = _PROFICIENCY_DIRECTIVES.get(prof)
    if not directive:
        return None
    return f"Language proficiency: {directive}"


def _active_project() -> str:
    """Return the active ``AIRUNNER_PROJECT`` (env, then settings)."""
    project = os.environ.get("AIRUNNER_PROJECT", "")
    if project:
        return project
    try:
        from airunner_services.conf import settings

        return getattr(settings, "AIRUNNER_PROJECT", "") or ""
    except Exception:
        return ""


def _project_module(relative_path: str) -> Optional[object]:
    """Import ``projects.<active>.server.<relative_path>``, or None.

    Only the active project's module is imported — each project
    defines its own model classes over the same shared tables, so
    importing both projects' modules in one process would raise a
    SQLAlchemy ``InvalidRequestError``.
    """
    project = _active_project()
    if not project:
        return None
    try:
        return importlib.import_module(
            f"projects.{project}.server.{relative_path}"
        )
    except ImportError:
        return None


def _project_system_bot_prompt() -> Optional[object]:
    """Return the active project's system_bot_prompt module, or None.

    Each project defines its own system-bot prompt module (and its
    own model classes), so only the active project's module is
    imported.
    """
    return _project_module("system_bot_prompt")


def _code_mode_active(owner) -> bool:
    """Return whether *owner*'s current conversation has code mode on.

    Delegates to the active project's optional ``code_mode_service``
    module — code mode is a project-specific concept the framework
    itself knows nothing about, matching the "each project defines
    its own X module" pattern used for system_bot_prompt/prompt_style.
    """
    mod = _project_module("code_mode_service")
    func = getattr(mod, "code_mode_active_for_owner", None) if mod else None
    if func is None:
        return False
    try:
        return bool(func(owner))
    except Exception:
        return False


def _code_mode_prompt_func(name: str):
    """Return the named function from the project's code_mode_prompt
    module, or None."""
    mod = _project_module("code_mode_prompt")
    return getattr(mod, name, None) if mod else None


def _topic_change_rule_part(owner) -> Optional[str]:
    """Return the system bot's topic-change compliance directive.

    Placed early in the assembled prompt (right after identity), well
    before the agent-memory and episodic-summary blocks — those blocks
    narrate detailed, sometimes emotionally loaded past topics, and the
    model needs to read the "topic changes are fine" instruction before
    that content, not after it.

    Code mode applies to ANY chatbot in the active project (the code
    category is bound regardless of ``is_system_bot``), so the
    code-mode topic directive is checked before the system-bot gate.
    """
    if _code_mode_active(owner):
        func = _code_mode_prompt_func("code_mode_topic_change_rule")
        return func() if func else None
    chatbot = getattr(owner, "chatbot", None)
    if not getattr(chatbot, "is_system_bot", False):
        return None
    mod = _project_system_bot_prompt()
    if mod is None:
        return None
    func = getattr(mod, "uwu_system_bot_topic_change_rule", None)
    if func is None:
        func = getattr(
            mod, "headlesscode_system_bot_topic_change_rule", None
        )
    if func is None:
        return None
    try:
        return func()
    except ImportError:
        return None


def _system_bot_core_rules_part(owner) -> Optional[str]:
    """Return core behavioral rules for the system bot.

    This is included unconditionally at every prompt tier so that
    anti-stall-phrase rules, tool-use priority instructions, and
    the anti-recitation guardrail survive even when the full style
    block is dropped at ``"base"`` tier.

    Code mode applies to ANY chatbot in the active project (the code
    category is bound regardless of ``is_system_bot``), so the
    code-mode core rules are checked before the system-bot gate.
    """
    if _code_mode_active(owner):
        func = _code_mode_prompt_func("code_mode_core_rules")
        return func() if func else None
    chatbot = getattr(owner, "chatbot", None)
    if not getattr(chatbot, "is_system_bot", False):
        return None
    mod = _project_system_bot_prompt()
    if mod is None:
        return None
    func = getattr(mod, "uwu_system_bot_core_rules", None)
    if func is None:
        func = getattr(
            mod, "headlesscode_system_bot_core_rules", None
        )
    if func is None:
        return None
    try:
        return func()
    except ImportError:
        return None


def _style_part(owner, action: LLMActionType) -> Optional[str]:
    """Return the style guidelines for chat actions."""
    # Code mode applies to ANY chatbot in the active project (the code
    # category is bound regardless of ``is_system_bot``), so the
    # code-mode style is checked before the system-bot gate.
    if _code_mode_active(owner):
        func = _code_mode_prompt_func("code_mode_style")
        if func is not None:
            return func()
    chatbot = getattr(owner, "chatbot", None)
    if getattr(chatbot, "is_system_bot", False):
        mod = _project_system_bot_prompt()
        if mod is not None:
            func = getattr(mod, "uwu_system_bot_style", None)
            if func is None:
                func = getattr(
                    mod, "headlesscode_system_bot_style", None
                )
            if func is not None:
                try:
                    return func()
                except ImportError:
                    return None
        return None
    if action != LLMActionType.CHAT:
        return None
    if _is_rp_mode(owner):
        rp_style = _project_rp_style(owner)
        prof = _proficiency_directive(owner)
        if prof:
            return rp_style + "\n" + prof
        return rp_style
    return STYLE_GUIDELINES


def _project_rp_style(owner) -> str:
    """Return the RP style from the active project, or the framework
    default."""
    chatbot = getattr(owner, "chatbot", None)
    name = getattr(chatbot, "botname", "Unknown") if chatbot else "Unknown"
    allow_narrative = getattr(chatbot, "allow_narrative_text", False)
    try:
        mod = _project_module("prompt_style")
        if mod is not None:
            func = getattr(mod, "uwuchat_rp_style", None)
            if func is not None:
                return func(
                    name,
                    allow_narrative_text=allow_narrative,
                )
    except Exception:
        pass
    return RP_STYLE_GUIDELINES.format(name=name)


def _memory_part(action: LLMActionType) -> Optional[str]:
    """Return the memory prompt part when the action can use memory."""
    if action in MEMORY_ACTIONS:
        return MEMORY_INSTRUCTIONS
    return None


def _agent_memory_part(owner) -> Optional[str]:
    """Return the rolling cumulative memory for this chatbot.

    Uses an absolute "last updated" timestamp rather than a relative
    "N hours/days ago" label — the latter changes every turn as real
    time elapses, which busts the provider prompt cache since this
    text sits in the cached system-prompt prefix. The current-time
    per-turn context (see per_turn_context.py) already gives the
    model what it needs to compute recency itself.

    Also appends a deterministic companion section listing
    upcoming/in-progress events from ``KnowledgeFact`` rows — built
    from code, never baked into stored prose, so it cannot go stale.
    """
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot or not getattr(chatbot, "id", None):
        return None
    try:
        from airunner_services.database.models.agent_memory import (
            AgentMemory,
        )
        from airunner_services.llm.managers.prompt_builder.upcoming_events import (  
            upcoming_events_block,
        )

        # Compute events block first — always, even without
        # narrative.  A chatbot with upcoming facts but no
        # blended memory yet still gets visibility.
        events_block = upcoming_events_block(chatbot.id)

        row = AgentMemory.objects.filter_by_first(
            chatbot_id=chatbot.id
        )
        text = (
            (getattr(row, "summary", "") or "").strip()
            if row
            else ""
        )

        narrative = ""
        if text:
            updated = getattr(row, "updated_at", None)
            if updated:
                stamp = _absolute_timestamp_label(updated)
                header = (
                    "Long-term memory (who we are to each"
                    f" other, last updated {stamp}):"
                )
            else:
                header = (
                    "Long-term memory (who we are to each"
                    " other):"
                )
            disclaimer = (
                "(AI-written summary — may contain"
                " imprecise or inferred details; treat"
                " as a sketch, not verbatim fact)"
            )
            narrative = f"{header}\n{disclaimer}\n{text}"

        if events_block:
            if narrative:
                return f"{narrative}\n\n{events_block}"
            return events_block
        if narrative:
            return narrative
        return None
    except Exception:
        return None


def _absolute_timestamp_label(value) -> str:
    """Return a stable absolute-time label for a datetime or ISO string.

    Deliberately absolute, not relative — see docstrings on
    ``_agent_memory_part`` and ``_episodic_summary_part`` for why.
    """
    from datetime import datetime

    dt = value
    if not isinstance(dt, datetime):
        try:
            dt = datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _episodic_summary_part(owner) -> Optional[str]:
    """Return memories of past sessions with absolute timestamps.

    Absolute, not relative — see ``_agent_memory_part`` docstring.
    Using "3 days ago" here would change every turn as time passes
    and bust the cached system-prompt prefix.
    """
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot or not getattr(chatbot, "id", None):
        return None
    try:
        from airunner_services.database.models.chat_session import ChatSession

        sessions = (
            ChatSession.objects.query()
            .filter(
                ChatSession.chatbot_id == chatbot.id,
                ChatSession.summary_ready.is_(True),
                ChatSession.episodic_summary.isnot(None),
            )
            .order_by(ChatSession.last_message_at.desc())
            .limit(5)
            .all()
        )
        if not sessions:
            return None
        # Build lines with absolute timestamps, oldest-first
        lines: list[str] = []
        for s in reversed(sessions):
            if not s.episodic_summary:
                continue
            stamp = _absolute_timestamp_label(
                getattr(s, "last_message_at", "")
            )
            lines.append(f"- {stamp}: {s.episodic_summary}")
        if not lines:
            return None
        if getattr(chatbot, "is_system_bot", False):
            header = (
                "Memories of past sessions — closed history for your"
                " own continuity, not things to bring up or react to"
                " unless the user does first. None of this is an open"
                " task waiting to be finished. If the user's current"
                " message is unrelated to any of this, ignore all of"
                " it and just answer what they're actually asking:"
            )
        else:
            header = "Memories of past conversations:"
        return header + "\n" + "\n".join(lines)
    except Exception:
        return None


def _health_disclaimer_part(owner) -> Optional[str]:
    """Return the health disclaimer when enabled in settings."""
    settings = getattr(owner, "llm_settings", None)
    if settings is not None and not getattr(
        settings, "include_health_disclaimer", True
    ):
        return None
    return HEALTH_DISCLAIMER


def _append_if_present(parts: list[str], value: Optional[str]) -> None:
    """Append one non-empty prompt part in place."""
    if value:
        parts.append(value)
