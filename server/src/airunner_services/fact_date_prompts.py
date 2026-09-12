"""Prompt templates for fact date classification and extraction.

Kept separate from ``fact_date_extractor.py`` to stay under the
250-line file-size limit.
"""
from __future__ import annotations

STAGE_A_PROMPT = """You are a date classifier. Analyze the fact below and
classify it into one of three categories.

Categories:
- no_date — the fact has no specific date or time (e.g. name, job,
  preference, personality trait, vague intention).
- hard_date — the fact mentions a specific deadline, calendar date,
  appointment, or event that can be resolved to a concrete date
  (e.g. "release is Friday", "meeting at 3pm today", "vacation
  July 20-27", "therapy every Tuesday").
- soft_aspirational — the fact mentions a time horizon but is vague
  and aspirational, not a concrete commitment (e.g. "wants to travel
  sometime this year", "hopes to learn piano one day", "thinking
  about switching jobs eventually").

Current date: {reference_date}

Fact: {fact_text}

Respond with exactly one word: no_date, hard_date, or soft_aspirational."""

STAGE_B_PROMPT = """You are a date extractor. Given a fact and a reference
date, extract the structured date information.

Current date: {reference_date}

Fact: {fact_text}

Respond with ONLY a JSON object. No other text. The JSON must have
these keys:
- "event_date": ISO date string (YYYY-MM-DD) for the resolved
  absolute start date, or null if not determinable.
- "event_end_date": ISO date string (YYYY-MM-DD) for range events,
  or null.
- "event_time": ISO time string (HH:MM) for same-day events, or null.
- "recurring": true if the fact describes a repeating pattern
  ("every Tuesday", "weekly", "annual"), false otherwise.

Rules:
- Resolve relative dates ("Friday", "next week") against the current
  date provided above.
- For range events ("July 20-27"), set both event_date and
  event_end_date.
- For same-day time events ("meeting at 3pm"), set event_time.
  event_date should still be the resolved date.
- A single date with no time and no end date gets only event_date.
- Do NOT make up dates. If the fact says "in September" without a
  year, resolve using the current year from the current date.
- "next Friday" if today is Monday = 4 days later. If today is
  Saturday = 6 days later (next week's Friday)."""
