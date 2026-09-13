"""LLM tool: write_journal_entry — summarize a day's conversation."""

from __future__ import annotations

import datetime
import logging
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool

from airunner_services.conf.model_settings import GOOGLE_GEMINI_FLASH_LITE_MODEL


@tool(
    name="write_journal_entry",
    category=ToolCategory.SYSTEM,
    description=(
        "Write a first-person journal entry summarizing what happened "
        "today. Use this at natural conversation end points (when "
        "wrapping up for the day, after a deep chat, or when the user "
        "asks). The entry is written in the user's voice — as if they "
        "wrote it themselves — capturing key events, feelings, and "
        "takeaways from the day's conversation."
    ),
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=[
        "journal", "diary", "entry", "summarize day", "log",
        "write down", "note today",
    ],
    input_examples=[
        {"date_str": "2026-06-30"},
        {
            "date_str": "2026-06-30",
            "summary_override": (
                "User had a rough day at work but felt better after "
                "talking about it."
            ),
        },
    ],
)
def write_journal_entry(
    date_str: Annotated[
        str,
        "ISO-format date string for the entry (e.g. '2026-06-30'). "
        "Defaults to today if the day's conversation is still active.",
    ],
    summary_override: Annotated[
        str | None,
        "Optional pre-written summary. When provided, this is saved "
        "verbatim as the journal body instead of calling the LLM "
        "summarizer. Use this when the user explicitly dictates what "
        "they want written.",
    ] = None,
    agent: Any = None,
) -> str:
    """Write a first-person journal entry derived from today's conversation.

    Gathers ConversationTurn rows for the given date, formats them
    into a prompt, and calls the SUMMARIZATION model to produce a
    first-person narrative.  Saves the result as a JournalEntry row.
    If an entry already exists for that date, it is overwritten
    (the UwU is "rewriting" it).

    Returns:
        Confirmation message the UwU can relay to the user in character.
    """
    try:
        entry_date = datetime.date.fromisoformat(date_str)
    except (ValueError, TypeError):
        entry_date = datetime.date.today()

    user = getattr(agent, "user", None) if agent else None
    chatbot = getattr(agent, "chatbot", None) if agent else None
    user_id = getattr(user, "id", None) if user else None
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not user_id or not chatbot_id:
        return (
            "I couldn't figure out whose journal to write to — "
            "something's off with the session state."
        )

    if summary_override and summary_override.strip():
        return _save_journal_entry(
            user_id, chatbot_id, entry_date,
            summary_override.strip(),
        )

    turns = _fetch_turns_for_date(user_id, chatbot_id, entry_date)
    if not turns:
        return (
            f"I looked through our conversation for {entry_date}, "
            "but there wasn't much to write about."
        )

    summary = _summarize_turns(turns, entry_date)
    if not summary:
        return (
            "I tried to write a journal entry, but the words "
            "wouldn't come together. Maybe we can try again later?"
        )

    return _save_journal_entry(user_id, chatbot_id, entry_date, summary)


def _fetch_turns_for_date(
    user_id: int,
    chatbot_id: int,
    entry_date: datetime.date,
) -> list[dict]:
    """Return conversation turns for a given date, oldest first."""
    from airunner_services.database.models.conversation_turn import (
        ConversationTurn,
    )

    day_start = datetime.datetime(
        entry_date.year, entry_date.month, entry_date.day,
        tzinfo=datetime.timezone.utc,
    )
    day_end = day_start + datetime.timedelta(days=1)

    rows = (
        ConversationTurn.objects.query(
            ConversationTurn.role, ConversationTurn.content,
            ConversationTurn.created_at,
        )
        .filter(
            ConversationTurn.chatbot_id == chatbot_id,
            ConversationTurn.created_at >= day_start,
            ConversationTurn.created_at < day_end,
        )
        .order_by(ConversationTurn.created_at.asc())
        .all()
    )
    result: list[dict] = []
    for role, content, ts in rows:
        result.append({"role": role, "content": content, "timestamp": ts})
    return result


def _summarize_turns(
    turns: list[dict],
    entry_date: datetime.date,
) -> str | None:
    """Call the SUMMARIZATION model to produce a journal entry."""
    if len(turns) <= 2:
        return _lightweight_summary(turns, entry_date)

    transcript = _format_transcript(turns)
    prompt = _journal_prompt(transcript, entry_date)
    try:
        return _call_summarization_llm(prompt)
    except Exception:
        logging.exception("Journal summarization LLM call failed")
        return _lightweight_summary(turns, entry_date)


def _format_transcript(turns: list[dict]) -> str:
    """Format conversation turns into a readable transcript."""
    lines: list[str] = []
    for turn in turns:
        role_label = "User" if turn["role"] == "user" else "UwU"
        timestamp = turn.get("timestamp", "")
        ts_str = ""
        if timestamp and isinstance(timestamp, datetime.datetime):
            ts_str = timestamp.strftime(" [%H:%M]")
        lines.append(f"{role_label}{ts_str}: {turn['content']}")
    return "\n".join(lines)


def _journal_prompt(
    transcript: str,
    entry_date: datetime.date,
) -> str:
    """Build the journal summarization prompt."""
    date_label = entry_date.strftime("%A, %B %-d, %Y")
    return (
        f"You are a thoughtful journal keeper. Below is a transcript "
        f"of a conversation from {date_label}.\n\n"
        f"Write a first-person journal entry as if the user wrote it "
        f"themselves, reflecting on the conversation. Capture key "
        f"events, feelings, realizations, and takeaways. Use a warm, "
        f"introspective tone. Keep it to 2-4 paragraphs. Do not "
        f"mention you as an AI — refer to you as a friend/companion.\n"
        f"\n--- TRANSCRIPT ---\n{transcript}\n--- END ---\n\n"
        f"Journal entry for {date_label}:"
    )


def _call_summarization_llm(prompt: str) -> str | None:
    """Call the LLM for journal summarization via OpenRouter."""
    import os

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logging.warning("OPENROUTER_API_KEY not set; cannot summarize")
        return None

    from langchain_core.messages import HumanMessage
    from airunner_services.cloud.llm.model_builders import (
        create_openrouter_model,
    )
    from airunner_services.cloud.llm.completion_choke import (
        invoke_with_limiter,
    )
    from airunner_services.llm.pipeline_loader import pipeline_config
    from airunner_services.llm.token_usage import (
        record_background_usage,
    )

    cfg = pipeline_config("JOURNAL_SUMMARIZER")
    model = create_openrouter_model(
        api_key=api_key,
        model_name=cfg.get("model", GOOGLE_GEMINI_FLASH_LITE_MODEL),
        temperature=cfg.get("temperature", 0.7),
        max_tokens=cfg.get("max_tokens", 512),
    )
    response = invoke_with_limiter(
        model,
        [HumanMessage(content=prompt)],
        priority="bulk",
    )
    record_background_usage("JOURNAL_SUMMARIZER", cfg, response)
    text = str(getattr(response, "content", response) or "").strip()
    return text or None


def _lightweight_summary(
    turns: list[dict],
    entry_date: datetime.date,
) -> str | None:
    """Produce a minimal summary without an LLM call."""
    if not turns:
        return None
    user_messages = [
        t["content"] for t in turns if t["role"] == "user"
    ]
    if not user_messages:
        return f"Talked with UwU on {entry_date}."
    preview = user_messages[0][:200]
    if len(preview) == 200:
        preview += "..."
    return (
        f"Chatted with UwU today. We talked about: {preview}"
    )


def _save_journal_entry(
    user_id: int,
    chatbot_id: int,
    entry_date: datetime.date,
    body: str,
) -> str:
    """Persist or overwrite a journal entry. Return confirmation."""
    from projects.uwuchat.server.models.journal_entry import JournalEntry

    existing = (
        JournalEntry.objects.query()
        .filter(
            JournalEntry.user_id == user_id,
            JournalEntry.entry_date == entry_date,
        )
        .first()
    )
    if existing:
        JournalEntry.objects.update(existing.id, body=body)
        action = "updated"
    else:
        JournalEntry.objects.create(
            user_id=user_id,
            chatbot_id=chatbot_id,
            entry_date=entry_date,
            body=body,
        )
        action = "saved"

    date_label = entry_date.strftime("%B %-d")
    return (
        f"Journal entry for {date_label} has been {action}! "
        "Let the user know in your own voice that their journal "
        "is up to date."
    )
