"""Location-first cascading character randomization.

Pick a country → city → language → gender → species → age.
Then hand off to the LLM for name, personality, backstory, and occupation.
"""

from __future__ import annotations

import random
from typing import Any, Optional

from airunner_services.api.routes.location_data import (
    CITIES_BY_COUNTRY,
    COUNTRY_ENGLISH_PROFICIENCY,
    COUNTRY_LANGUAGES,
    COUNTRY_TIMEZONES,
    DEFAULT_COUNTRY,
    SPECIES_SUBTYPES,
    country_gender_weights,
)


def randomize_character(
    allowed_species: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Return a complete character profile ready for LLM identity generation.

    Args:
        allowed_species: Species types to include. Defaults to all five.

    Returns:
        A dict with ``location``, ``language``, ``species_data``,
        ``attributes`` (including age), ``gender``, and context fields
        for the LLM prompt builder.
    """
    if allowed_species is None:
        allowed_species = ["human", "animal", "monster", "mythical", "robot"]

    # 1. Country ──────────────────────────────────────────────────────
    country_codes = _available_countries()
    country_code = random.choice(country_codes)

    # 2. City ──────────────────────────────────────────────────────────
    cities = CITIES_BY_COUNTRY.get(country_code, [DEFAULT_COUNTRY["city"]])
    city_data = random.choice(cities)

    # 3. Native language ──────────────────────────────────────────────
    languages = COUNTRY_LANGUAGES.get(country_code, ["en-US"])
    native_lang = random.choice(languages)
    locale = _locale_from_language(native_lang, country_code)

    # 4. Timezone ─────────────────────────────────────────────────────
    timezone = COUNTRY_TIMEZONES.get(
        country_code, DEFAULT_COUNTRY["timezone"]
    )

    # 5. Gender ───────────────────────────────────────────────────────
    gender_weights = country_gender_weights(country_code)
    gender = _weighted_choice(gender_weights)

    # 7. Species ──────────────────────────────────────────────────────
    species_type = random.choice(allowed_species)
    subtypes = SPECIES_SUBTYPES.get(species_type, [])
    species_subtype = random.choice(subtypes) if subtypes else None

    # 8. Age ──────────────────────────────────────────────────────────
    age = _roll_age(species_type)

    # 9. Language profile ─────────────────────────────────────────────
    eng_prof: int = COUNTRY_ENGLISH_PROFICIENCY.get(
        country_code
    ) or DEFAULT_COUNTRY["english_proficiency"]
    language_profile = _build_language_profile(native_lang, eng_prof)

    # 10. Assemble location ───────────────────────────────────────────
    location = {
        "timezone": timezone,
        "locale": locale,
        "city": city_data["city"],
        "region": city_data["region"],
        "country_code": country_code,
        "latitude": city_data["lat"],
        "longitude": city_data["lng"],
        # home_description filled by LLM
        "home_description": "",
    }

    # 11. Assemble attributes ─────────────────────────────────────────
    attributes: dict[str, Any] = {"age": age}

    # 12. Assemble species_data ───────────────────────────────────────
    species_data: dict[str, Any] = {
        "type": species_type,
        "subtype": species_subtype,
        "description": "",
    }

    return {
        "location": location,
        "language": language_profile,
        "species_data": species_data,
        "attributes": attributes,
        "gender": gender,
        # Context for the LLM prompt builder:
        "_llm_context": {
            "country_code": country_code,
            "city": city_data["city"],
            "region": city_data["region"],
            "native_language": native_lang,
            "species_type": species_type,
            "species_subtype": species_subtype,
            "age": age,
            "gender": gender,
        },
    }


# ── helpers ──────────────────────────────────────────────────────────────

def _available_countries() -> list[str]:
    """Return country codes that have at least one city entry."""
    return list(CITIES_BY_COUNTRY.keys())


def _weighted_choice(weights: dict[str, float]) -> str:
    """Pick a key by probability weight."""
    items = list(weights.items())
    total = sum(w for _, w in items)
    r = random.random() * total
    cumulative = 0.0
    for key, weight in items:
        cumulative += weight
        if r <= cumulative:
            return key
    return items[-1][0]


def _locale_from_language(lang_tag: str, country_code: str) -> str:
    """Derive a BCP 47 locale from a language tag and country."""
    # Simple mapping — could use pycountry for richer resolution.
    region = lang_tag.split("-")[1] if "-" in lang_tag else country_code
    base = lang_tag.split("-")[0]
    return f"{base}-{region}"


def _roll_age(species_type: str) -> int:
    """Roll an age appropriate to the species type (18+ for humans)."""
    if species_type == "human":
        # Weighted toward 20-40
        return max(18, int(random.gauss(30, 12)))
    if species_type == "robot":
        # "Age" is years since activation, 1-50
        return max(1, int(random.gauss(8, 10)))
    if species_type == "mythical":
        # Mythical creatures can be ancient
        return max(18, int(random.gauss(200, 300)))
    if species_type == "monster":
        # Monsters vary widely
        return max(18, int(random.gauss(80, 120)))
    # animal: shorter lifespans
    return max(2, int(random.gauss(5, 5)))


def _build_language_profile(
    native_lang: str,
    english_proficiency: int,
) -> dict[str, Any]:
    """Build the language JSON profile for a character."""
    native_tag = native_lang.split("-")[0]
    is_native_english = native_tag == "en"

    native: dict[str, Any] = {
        "language": native_lang,
        "proficiency": 5,
        "uses_slang": False,
        "dialect": None,
    }

    other_languages: list[dict[str, Any]] = []
    if not is_native_english and english_proficiency < 5:
        other_languages.append({
            "language": "en-US",
            "proficiency": english_proficiency,
            "uses_slang": False,
            "dialect": None,
        })

    return {
        "native_language": native,
        "other_languages": other_languages,
    }
