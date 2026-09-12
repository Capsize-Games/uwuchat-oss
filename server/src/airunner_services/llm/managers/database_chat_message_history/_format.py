"""Human-friendly tool-call status phrasing shown to end users.

These constants and helpers were moved verbatim from the former
monolithic ``database_chat_message_history.py`` module.
"""

# Map tool-name prefixes / patterns to human-friendly activity labels.
_TOOL_LABEL_MAP: dict[str, str] = {
    "search_news": "checking recent news",
    "search_fastsearch": "searching the internet",
    "search_web": "searching the web",
    "scrape_website": "reading an article",
    "check_similar_facts": "checking my notes",
    "save_fact": "remembering something",
    "retract_fact": "updating my notes",
    "calculator": "doing some math",
    "add_calendar_event": "adding to your calendar",
    "check_grounding": "verifying sources",
    "search_email": "searching your inbox",
    "search_weather": "checking the weather",
    "get_my_weather": "checking your weather",
    "summarize_article": "summarizing an article",
}

_FALLBACK_LABEL = "looking into that"

# Varied status templates to avoid robotic repetition.
# Every template must be grammatically compatible with the gerund
# labels in _TOOL_LABEL_MAP (e.g. "checking recent news").
_STATUS_TEMPLATES: list[str] = [
    "One sec — {activities}",
    "Hmm, {activities}…",
    "Just a moment — {activities}",
    "Hang tight, {activities}…",
    "Working on it — {activities}",
    "Right away — {activities}",
]

# Rotating counter so consecutive calls with the same tool count
# cycle through templates instead of repeating the same one.
_template_counter: int = 0


def _friendly_tool_status(tool_names: list[str]) -> str:
    """Return a short, human-facing status string for active tool calls.

    Never exposes raw tool names to the end user.  Varies phrasing
    via a rotating counter so consecutive identical calls (e.g.
    repeated single-tool invocations) don't repeat the same string.
    """
    global _template_counter

    labels: list[str] = []
    seen: set[str] = set()
    for name in tool_names:
        label = _TOOL_LABEL_MAP.get(name)
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    if not labels:
        return _FALLBACK_LABEL

    # Rotate through templates — counter advances on every call so
    # even repeated single-tool turns get varied phrasing.
    template_idx = _template_counter % len(_STATUS_TEMPLATES)
    _template_counter += 1
    template = _STATUS_TEMPLATES[template_idx]
    return template.format(activities=activities_phrase(labels))


def activities_phrase(labels: list[str]) -> str:
    """Join activity labels into a natural English phrase."""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"
