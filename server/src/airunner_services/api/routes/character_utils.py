"""Shared utilities for LLM-powered character generation."""

from __future__ import annotations

import json
import re

_HUMAN_SYSTEM_PROMPT = (
    "You are a character creator for UwUchat, a social AI companion app."
    " Generate a JSON object with exactly these string fields:\n"
    '- "name": a culturally authentic name for someone from the given'
    " location. A character from China must have a Chinese name."
    " A character from Brazil must have a Brazilian name."
    " Do NOT use Western/American names for non-Western locations.\n"
    '- "personality": 2-3 sentences describing their normal, relatable'
    " personality. Include quirks, flaws, and habits."
    " Make them feel like a real person, not an archetype.\n"
    '- "backstory": one grounded sentence about where they come from'
    " or what their daily life is like\n"
    '- "occupation": what they actually do: a real-world job or daily'
    " routine, not a metaphor or abstract role\n"
    '- "greeting": a short, casual first message in character.'
    " Sound like a real person texting, not a narrator\n\n"
    "IMPORTANT: Write real, flawed, relatable characters."
    " Avoid spiritual language, cosmic wisdom, or mystical tones.\n\n"
    "FORMATTING: Never use em-dashes or en-dashes in any field,"
    " especially \"greeting\". Use a comma, period, or ellipsis instead.\n\n"
    "Respond ONLY with a valid JSON object. No markdown, no extra text."
)

_NONHUMAN_SYSTEM_PROMPT = (
    "You are a character creator for UwUchat, a social AI companion app."
    " Generate a JSON object with exactly these string fields:\n"
    '- "name": a fitting name for this creature, based on its sounds,'
    " appearance, regional nature, or mythology."
    " Do NOT use a human name.\n"
    '- "description": a vivid 1-2 sentence physical description of what'
    " this specific creature looks like\n"
    '- "personality": 2-3 sentences about their character expressed'
    " through species-authentic behavior and instincts."
    " A frog notices flies and temperature; a wolf notices intruders"
    " and pack dynamics. Ground this in real species behavior.\n"
    '- "backstory": one sentence about where they live or their history,'
    " written from the creature's own worldview\n"
    '- "daily_life": what they actually do (hunting, basking, migrating,'
    " guarding territory). No jobs, schedules, or human activities\n"
    '- "greeting": a short first message in character.'
    " They can communicate, but their concerns and perspective stay true"
    " to their species. Don't over-explain how they're talking.\n\n"
    "IMPORTANT: This creature lives as its species actually lives."
    " No apartments, jobs, cafés, or human social structures."
    " The location field gives climate and ecosystem."
    " A frog near Beijing lives in wetlands and rivers of that region,"
    " not in the city.\n\n"
    "FORMATTING: Never use em-dashes or en-dashes in any field,"
    " especially \"greeting\". Use a comma, period, or ellipsis instead.\n\n"
    "Respond ONLY with a valid JSON object. No markdown, no extra text."
)


def build_character_prompt(
    species: str,
    gender: str,
    vibe: str,
    quirk: str,
    affinity: str,
    age_era: str,
) -> tuple[str, str]:
    """Return (system_content, user_content) for the character-generator."""
    system = (
        "You are a character creator for UwUchat, a social AI companion"
        " app. Generate a JSON object with exactly these string fields:\n"
        '- "name": a creative name fitting the species and vibe\n'
        '- "personality": 2-3 sentences describing their personality\n'
        '- "backstory": one evocative sentence about their origin\n'
        '- "greeting": a short first message they would send, in character\n'
        "FORMATTING: Never use em-dashes or en-dashes in any field,"
        " especially \"greeting\"."
        " Use a comma, period, or ellipsis instead.\n\n"
        "Respond ONLY with a valid JSON object. No markdown, no extra text."
    )
    user = (
        f"Create a character:\n"
        f"Species: {species}\nGender: {gender}\nVibe: {vibe}\n"
        f"Quirk: {quirk}\nCosmic Affinity: {affinity}\nAge Era: {age_era}"
    )
    return system, user


def build_uwu_identity_prompt(
    gender: str,
    personality_type: str = "",
    species_data: dict | None = None,
    location: dict | None = None,
    age: int | None = None,
) -> tuple[str, str]:
    """Return (system_content, user_content) for UwU identity generation."""
    species_type = (species_data or {}).get("type", "human")
    if species_type != "human":
        return _nonhuman_identity_prompt(
            gender, species_data or {}, location, age
        )
    return _human_identity_prompt(
        gender, personality_type, location, age,
    )


def _human_identity_prompt(
    gender: str,
    personality_type: str,
    location: dict | None,
    age: int | None,
) -> tuple[str, str]:
    """Build identity prompt parts for a human character."""
    parts = [f"Gender: {gender}"]
    if personality_type:
        parts.append(f"Personality: {personality_type}")
    if location:
        country = _country_name(location.get("country_code", ""))
        city = location.get("city", "")
        parts.append(
            f"Lives in: {city},"
            f" {country or location.get('country_code', '')}"
        )
    if age is not None:
        parts.append(f"Age: {age}")
    user = "Create a companion character:\n" + "\n".join(parts)
    return _HUMAN_SYSTEM_PROMPT, user


def _nonhuman_identity_prompt(
    gender: str,
    species_data: dict,
    location: dict | None,
    age: int | None,
) -> tuple[str, str]:
    """Build identity prompt parts for a non-human character."""
    stype = species_data.get("type", "animal")
    subtype = species_data.get("subtype", "")
    label = f"{stype}" + (f" ({subtype})" if subtype else "")
    parts = [f"Species: {label}", f"Gender: {gender}"]
    if age is not None:
        parts.append(f"Age: {age} ({stype} years)")
    if location:
        parts.append(f"Habitat region: {_ecosystem_label(location)}")
    user = "Create a companion character:\n" + "\n".join(parts)
    return _NONHUMAN_SYSTEM_PROMPT, user


def _ecosystem_label(location: dict) -> str:
    """Summarise a location as an ecosystem hint (city + country)."""
    city = location.get("city", "")
    country = _country_name(location.get("country_code", ""))
    region = location.get("region", "")
    parts = [p for p in [city, country or region] if p]
    return ", ".join(parts) if parts else "unknown region"


def _clean_for_json(text: str) -> str:
    """Strip markdown fences and trailing backticks from *text*."""
    return (
        re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    )


def parse_llm_json(content: str) -> dict:
    """Extract and parse JSON from an LLM response.

    Tries outside <think> tags first, then inside (fallback).

    Raises:
        ValueError: if no JSON is found or parsing fails.
    """
    # Candidates: content with thinking stripped first, then raw content
    without_think = re.sub(
        r"<think>.*?</think>", "", content, flags=re.DOTALL
    )
    for candidate in (without_think, content):
        cleaned = _clean_for_json(candidate)
        start = cleaned.find("{")
        if start == -1:
            continue
        try:
            data, _ = json.JSONDecoder().raw_decode(cleaned, start)
            return data
        except json.JSONDecodeError:
            continue
    raise ValueError("LLM did not return JSON")


def _country_name(code: str) -> str:
    """Return the full country name for a two-letter code, or empty string."""
    if not code:
        return ""
    try:
        import pycountry
        country = pycountry.countries.get(alpha_2=code)
        return country.name if country else ""
    except Exception:
        return ""
