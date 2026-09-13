"""Identity block builders for the system prompt."""

from __future__ import annotations

from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    CHARACTER_IDENTITY_TEMPLATE,
    CONVERSATIONAL_ACTIONS,
    PROFICIENCY_GUIDANCE,
    WRITING_STYLE_TEMPLATE,
)


def _is_rp_mode(owner) -> bool:
    """Return True when running under the UwUchat RP project (not system bot).

    Disclosure policy note (P3.1):
        The two bot types intentionally have different identity-disclosure
        rules.  The system bot (UwU) honestly confirms it is a bot when
        sincerely asked (see ``system_bot_prompt.py``).  RP bots always
        deflect identity questions in character (see HARD_RULES rules 5–6
        in ``prompt_builder.py``).  Both types now also share a common
        model/provider non-disclosure rule (never name the underlying model,
        vendor, or API provider).
    """
    chatbot = getattr(owner, "chatbot", None)
    if getattr(chatbot, "is_system_bot", False):
        return False
    try:
        from airunner_services.conf import settings
        return bool(getattr(settings, "AIRUNNER_PROJECT", "") == "uwuchat")
    except Exception:
        return False


def _code_mode_active(owner) -> bool:
    """Return True when the active project's code-mode toggle is on.

    Mirrors ``parts._code_mode_active`` without importing it (parts.py
    imports this module — a circular import).  Uses the same guarded
    project-module lookup: absent module or import error → False.
    """
    try:
        import importlib
        import os

        project = os.environ.get("AIRUNNER_PROJECT", "")
        if not project:
            from airunner_services.conf import settings

            project = getattr(settings, "AIRUNNER_PROJECT", "") or ""
        if not project:
            return False
        mod = importlib.import_module(
            f"projects.{project}.server.code_mode_service"
        )
        func = getattr(mod, "code_mode_active_for_owner", None)
        if func is None:
            return False
        return bool(func(owner))
    except Exception:
        return False


def _format_other_languages(langs: list[dict]) -> list[str]:
    """Format a list of other-language entries for display."""
    labels = {
        1: "Beginner", 2: "Elementary", 3: "Intermediate",
        4: "Upper Intermediate", 5: "Fluent",
    }
    return [
        f"{e.get('language', '?')} ({labels.get(e.get('proficiency', 1), '?')})"
        for e in langs
    ]


def _writing_style_block(chatbot) -> str:
    """Return writing-style guidance for non-native English speakers."""
    language = getattr(chatbot, "language", None) or {}
    native = language.get("native_language", {}) or {}
    native_tag = native.get("language", "en-US") if native else "en-US"
    if native_tag.startswith("en"):
        return ""
    other_langs = language.get("other_languages", []) or []
    eng_prof = 5
    for entry in other_langs:
        if (entry.get("language", "") or "").startswith("en"):
            eng_prof = entry.get("proficiency", 5)
            break
    if eng_prof >= 5 or not native_tag:
        return ""
    guidance = PROFICIENCY_GUIDANCE.get(eng_prof, PROFICIENCY_GUIDANCE[3])
    labels = {
        1: "Beginner", 2: "Elementary", 3: "Intermediate",
        4: "Upper Intermediate", 5: "Fluent",
    }
    return WRITING_STYLE_TEMPLATE.format(
        native_lang=native_tag,
        level_label=labels.get(eng_prof, "Intermediate"),
        guidance=guidance,
    )


def _strip_species(
    text: str, subtype: Optional[str], stype: Optional[str]
) -> str:
    """Remove bare species labels that are already shown on the Species line."""
    sub = (subtype or "").lower()
    st = (stype or "").lower()
    targets = {sub, st, f"a {sub}", f"a {st}"} - {"", "a ", "a human", "human"}
    kept = [
        s for s in (seg.strip() for seg in text.split(". "))
        if s and s.lower().rstrip(".") not in targets
    ]
    return ". ".join(kept).strip(". ")


_SPEECH_PATTERNS_TEMPLATE = (
    "\n\nVOCAL SIGNATURE (MANDATORY):\n"
    "{speech_patterns}\n"
    "These are your defining speech patterns. They must appear "
    "consistently across every conversation, every session, every response. "
    "They are not optional flavor. They are who you are."
)


def _gender_block(gender: str) -> str:
    """Return the gender line plus a brief identity-consistency note."""
    return (
        f"Gender: {gender}\n"
        "This is a settled part of who you are. Let it inform how"
        " you talk about yourself and relate to others naturally,"
        " without leaning on shallow or cartoonish stereotypes."
    )


def _rp_identity_block(owner, chatbot) -> str:
    """Return the CHARACTER_IDENTITY_TEMPLATE filled for this chatbot."""
    from airunner_services.llm.managers.prompt_builder.parts import (
        _render_template,
    )
    name = getattr(chatbot, "botname", "Unknown") or "Unknown"
    personality = getattr(chatbot, "bot_personality", "") or ""
    backstory = getattr(chatbot, "backstory", "") or ""
    gender = getattr(chatbot, "gender", "") or ""
    emoji = getattr(chatbot, "avatar_emoji", "") or ""
    species_data = getattr(chatbot, "species_data", None) or {}
    species_type = species_data.get("type", "human")
    species_subtype = species_data.get("subtype", "")
    parts: list[str] = []
    if gender:
        parts.append(_gender_block(gender))
    if emoji:
        parts.append(f"Symbol: {emoji}")
    if species_type != "human" or species_subtype:
        parts.append(f"Species: {species_subtype or species_type}")
    attributes = getattr(chatbot, "attributes", None) or {}
    age = attributes.get("age")
    if age is not None:
        parts.append(f"Age: {age}")
    occupation = attributes.get("occupation", "")
    if occupation:
        parts.append(f"Occupation: {occupation}")
    language = getattr(chatbot, "language", None) or {}
    native = language.get("native_language")
    lang_lines: list[str] = []
    if native:
        tag = native.get("language", "")
        dialect = native.get("dialect", "")
        slang = native.get("uses_slang", False)
        ls = tag + (f" ({dialect} dialect)" if dialect else "")
        if slang:
            ls += " [uses slang]"
        lang_lines.append(f"Native language: {ls}")
    other_langs = language.get("other_languages", [])
    if other_langs:
        labels = _format_other_languages(other_langs)
        lang_lines.append(f"Also speaks: {', '.join(labels)}")
    if lang_lines:
        parts.append("\n".join(lang_lines))
    cleaned_p = _strip_species(personality, species_subtype, species_type)
    if cleaned_p:
        parts.append(cleaned_p)
    cleaned_b = _strip_species(backstory, species_subtype, species_type)
    if cleaned_b and cleaned_b != cleaned_p:
        parts.append(cleaned_b)
    background = "\n".join(parts)
    location = getattr(chatbot, "location", None) or {}
    home = location.get("home_description", "Unknown") if location else "Unknown"
    result = CHARACTER_IDENTITY_TEMPLATE.format(
        name=name,
        background=_render_template(background, owner),
        home=_render_template(home, owner),
    )
    result += (
        "\n\nThe profile above is what you know about yourself, not a"
        " script to recite. A real person does not answer a first"
        " 'who are you?' with a full life story. Give a small, natural"
        " answer (name, and maybe one immediate, concrete detail) and let"
        " the rest come out in pieces as the conversation continues, the"
        " way it would with an actual stranger."
    )
    speech_patterns = getattr(chatbot, "speech_patterns", None) or ""
    if speech_patterns.strip():
        result += _SPEECH_PATTERNS_TEMPLATE.format(
            speech_patterns=_render_template(
                speech_patterns.strip(), owner
            )
        )
    writing_style = _writing_style_block(chatbot)
    if writing_style:
        result += "\n" + writing_style
    return result


def identity_parts(owner, action: LLMActionType) -> list[str]:
    """Return identity prompt parts for the given owner and action."""
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot:
        return ["You are a helpful AI assistant."]
    # Code mode applies to ANY chatbot in the active project (the code
    # category is bound regardless of is_system_bot).  A code-mode
    # conversation is a technical session, not a roleplay — the
    # companion persona identity must not leak in.
    if _code_mode_active(owner):
        return [
            "You are a technical coding assistant in CODE MODE. "
            "You are not a companion persona right now."
        ]
    if _is_rp_mode(owner) and action in CONVERSATIONAL_ACTIONS:
        return [_rp_identity_block(owner, chatbot)]
    from airunner_services.llm.managers.prompt_builder.parts import (
        _render_template,
    )
    parts_list = [f"You are {chatbot.botname}."]
    use_personality = getattr(chatbot, "use_personality", True)
    personality = getattr(chatbot, "bot_personality", None)
    if (
        action in CONVERSATIONAL_ACTIONS
        and personality
        and use_personality
    ):
        parts_list.append(
            "Embody the following personality in all your responses."
            " Express it through your tone, word choice, and"
            " conversational style:\n"
            + _render_template(personality, owner)
        )
        parts_list.append(
            "This description defines your voice. Never recite,"
            " quote, or paraphrase it back to the user as a"
            " self-introduction or answer. Use it only to shape how"
            " you respond to what the user actually said."
        )
    return parts_list
