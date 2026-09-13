"""Static location → trait mappings for character randomization.

Uses approximate demographic data for realism without external APIs.
"""

from __future__ import annotations

from typing import Any

# ── Country → primary languages (BCP 47) ────────────────────────────
# For multilingual countries, earlier entries are more widely spoken.

COUNTRY_LANGUAGES: dict[str, list[str]] = {
    "US": ["en-US"], "GB": ["en-GB"], "CA": ["en-CA", "fr-CA"],
    "AU": ["en-AU"], "NZ": ["en-NZ"], "IE": ["en-IE"],
    "JP": ["ja-JP"], "CN": ["zh-CN"], "KR": ["ko-KR"],
    "TW": ["zh-TW"], "HK": ["zh-HK"],
    "IN": ["hi-IN", "bn-IN", "te-IN", "ta-IN", "mr-IN"],
    "BR": ["pt-BR"], "AR": ["es-AR"], "CO": ["es-CO"],
    "PE": ["es-PE"], "CL": ["es-CL"], "MX": ["es-MX"],
    "FR": ["fr-FR"], "DE": ["de-DE"], "ES": ["es-ES"],
    "IT": ["it-IT"], "NL": ["nl-NL"], "PT": ["pt-PT"],
    "SE": ["sv-SE"], "NO": ["nb-NO"], "DK": ["da-DK"],
    "FI": ["fi-FI"], "PL": ["pl-PL"], "CZ": ["cs-CZ"],
    "GR": ["el-GR"], "TR": ["tr-TR"], "RU": ["ru-RU"],
    "UA": ["uk-UA"], "IL": ["he-IL"], "AE": ["ar-AE"],
    "SA": ["ar-SA"], "IR": ["fa-IR"],
    "NG": ["ha-NG", "yo-NG"], "KE": ["sw-KE"],
    "ZA": ["af-ZA", "zu-ZA"], "EG": ["ar-EG"],
    "MA": ["ar-MA", "fr-MA"], "ET": ["am-ET"],
    "TH": ["th-TH"], "VN": ["vi-VN"], "ID": ["id-ID"],
    "PH": ["tl-PH"], "SG": ["zh-SG", "ms-SG"],
    "MY": ["ms-MY"], "BD": ["bn-BD"],
    "PK": ["ur-PK"], "LK": ["si-LK"],
}

# ── Country → gender probability weights ─────────────────────────────
# Most countries near 50/50 with small non-binary fraction.

_COUNTRY_GENDER: dict[str, dict[str, float]] = {
    "IN": {"Female": 0.39, "Male": 0.59, "Non-binary": 0.02},
    "CN": {"Female": 0.46, "Male": 0.52, "Non-binary": 0.02},
    "SA": {"Female": 0.42, "Male": 0.56, "Non-binary": 0.02},
    "IR": {"Female": 0.40, "Male": 0.58, "Non-binary": 0.02},
}
_DEFAULT_GENDER = {"Female": 0.48, "Male": 0.48, "Non-binary": 0.04}


def country_gender_weights(country_code: str) -> dict[str, float]:
    """Return gender weights for a country, falling back to defaults."""
    return _COUNTRY_GENDER.get(country_code, _DEFAULT_GENDER)


# ── Country → estimated English proficiency (CEFR 1-5) ───────────────

COUNTRY_ENGLISH_PROFICIENCY: dict[str, int] = {
    "GB": 5, "US": 5, "CA": 5, "AU": 5, "NZ": 5, "IE": 5,
    "NL": 4, "SE": 4, "NO": 4, "DK": 4, "FI": 4, "DE": 3,
    "PT": 3, "FR": 2, "ES": 2, "IT": 2, "GR": 2,
    "PL": 3, "CZ": 3, "UA": 2, "RU": 2, "TR": 2,
    "IN": 4, "NG": 4, "KE": 4, "PH": 4, "SG": 4, "MY": 3,
    "ZA": 4, "EG": 2, "MA": 2, "ET": 1,
    "JP": 2, "CN": 2, "KR": 2, "TW": 3, "HK": 3,
    "BR": 2, "AR": 2, "CO": 2, "PE": 2, "CL": 2, "MX": 2,
    "TH": 2, "VN": 2, "ID": 2, "BD": 2, "PK": 3, "LK": 3,
    "AE": 3, "SA": 2, "IR": 1, "IL": 4,
}

# ── Country → IANA timezone (primary) ────────────────────────────────

COUNTRY_TIMEZONES: dict[str, str] = {
    "US": "America/New_York", "GB": "Europe/London",
    "CA": "America/Toronto", "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland", "IE": "Europe/Dublin",
    "JP": "Asia/Tokyo", "CN": "Asia/Shanghai", "KR": "Asia/Seoul",
    "TW": "Asia/Taipei", "HK": "Asia/Hong_Kong",
    "IN": "Asia/Kolkata", "BR": "America/Sao_Paulo",
    "AR": "America/Argentina/Buenos_Aires",
    "CO": "America/Bogota", "PE": "America/Lima",
    "CL": "America/Santiago", "MX": "America/Mexico_City",
    "FR": "Europe/Paris", "DE": "Europe/Berlin", "ES": "Europe/Madrid",
    "IT": "Europe/Rome", "NL": "Europe/Amsterdam",
    "PT": "Europe/Lisbon", "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo", "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki", "PL": "Europe/Warsaw",
    "CZ": "Europe/Prague", "GR": "Europe/Athens",
    "TR": "Europe/Istanbul", "RU": "Europe/Moscow",
    "UA": "Europe/Kyiv", "IL": "Asia/Jerusalem",
    "AE": "Asia/Dubai", "SA": "Asia/Riyadh", "IR": "Asia/Tehran",
    "NG": "Africa/Lagos", "KE": "Africa/Nairobi",
    "ZA": "Africa/Johannesburg", "EG": "Africa/Cairo",
    "MA": "Africa/Casablanca", "ET": "Africa/Addis_Ababa",
    "TH": "Asia/Bangkok", "VN": "Asia/Ho_Chi_Minh",
    "ID": "Asia/Jakarta", "PH": "Asia/Manila",
    "SG": "Asia/Singapore", "MY": "Asia/Kuala_Lumpur",
    "BD": "Asia/Dhaka", "PK": "Asia/Karachi", "LK": "Asia/Colombo",
}

# ── Country → [cities] for city selection ────────────────────────────

CITIES_BY_COUNTRY: dict[str, list[dict[str, Any]]] = {
    "US": [
        {"city": "New York City", "region": "New York",
         "lat": 40.71, "lng": -74.01},
        {"city": "Chicago", "region": "Illinois",
         "lat": 41.88, "lng": -87.63},
        {"city": "Los Angeles", "region": "California",
         "lat": 34.05, "lng": -118.24},
        {"city": "Austin", "region": "Texas",
         "lat": 30.27, "lng": -97.74},
        {"city": "Denver", "region": "Colorado",
         "lat": 39.74, "lng": -104.99},
        {"city": "Atlanta", "region": "Georgia",
         "lat": 33.75, "lng": -84.39},
        {"city": "San Francisco", "region": "California",
         "lat": 37.77, "lng": -122.42},
        {"city": "Anchorage", "region": "Alaska",
         "lat": 61.22, "lng": -149.90},
        {"city": "Honolulu", "region": "Hawaii",
         "lat": 21.31, "lng": -157.86},
    ],
    "GB": [
        {"city": "London", "region": "England",
         "lat": 51.51, "lng": -0.13},
        {"city": "Manchester", "region": "England",
         "lat": 53.48, "lng": -2.24},
        {"city": "Edinburgh", "region": "Scotland",
         "lat": 55.95, "lng": -3.19},
    ],
    "JP": [
        {"city": "Tokyo", "region": "Tokyo",
         "lat": 35.68, "lng": 139.65},
        {"city": "Osaka", "region": "Osaka",
         "lat": 34.69, "lng": 135.50},
        {"city": "Kyoto", "region": "Kyoto",
         "lat": 35.01, "lng": 135.77},
    ],
    "CA": [
        {"city": "Toronto", "region": "Ontario",
         "lat": 43.65, "lng": -79.38},
        {"city": "Vancouver", "region": "British Columbia",
         "lat": 49.28, "lng": -123.12},
        {"city": "Montreal", "region": "Quebec",
         "lat": 45.50, "lng": -73.57},
    ],
    "AU": [
        {"city": "Sydney", "region": "New South Wales",
         "lat": -33.87, "lng": 151.21},
        {"city": "Melbourne", "region": "Victoria",
         "lat": -37.81, "lng": 144.96},
        {"city": "Perth", "region": "Western Australia",
         "lat": -31.95, "lng": 115.86},
    ],
    "BR": [
        {"city": "São Paulo", "region": "São Paulo",
         "lat": -23.55, "lng": -46.63},
        {"city": "Rio de Janeiro", "region": "Rio de Janeiro",
         "lat": -22.91, "lng": -43.17},
    ],
    "IN": [
        {"city": "Mumbai", "region": "Maharashtra",
         "lat": 19.08, "lng": 72.88},
        {"city": "Delhi", "region": "Delhi",
         "lat": 28.70, "lng": 77.10},
        {"city": "Bangalore", "region": "Karnataka",
         "lat": 12.97, "lng": 77.59},
    ],
    "DE": [
        {"city": "Berlin", "region": "Berlin",
         "lat": 52.52, "lng": 13.40},
        {"city": "Munich", "region": "Bavaria",
         "lat": 48.14, "lng": 11.58},
    ],
    "FR": [
        {"city": "Paris", "region": "Île-de-France",
         "lat": 48.86, "lng": 2.35},
        {"city": "Lyon", "region": "Auvergne-Rhône-Alpes",
         "lat": 45.76, "lng": 4.84},
    ],
    "KR": [
        {"city": "Seoul", "region": "Seoul",
         "lat": 37.57, "lng": 126.98},
        {"city": "Busan", "region": "Busan",
         "lat": 35.18, "lng": 129.08},
    ],
    "CN": [
        {"city": "Shanghai", "region": "Shanghai",
         "lat": 31.23, "lng": 121.47},
        {"city": "Beijing", "region": "Beijing",
         "lat": 39.90, "lng": 116.41},
    ],
}

# ── Species subtypes ──────────────────────────────────────────────────

SPECIES_SUBTYPES: dict[str, list[str]] = {
    "human": [],
    "animal": [
        "frog", "cat", "dog", "wolf", "fox", "rabbit", "bear",
        "raccoon", "owl", "penguin", "deer", "otter", "axolotl",
        "dragonfly", "turtle", "crow", "hedgehog", "bat",
        "koala", "red panda", "seal", "hamster", "capybara",
    ],
    "monster": [
        "dragon", "ghost", "vampire", "werewolf", "demon",
        "slime", "goblin", "kraken", "banshee", "eldritch horror",
        "gargoyle", "lich", "wendigo", "oni", "chimera",
        "zombie", "shade", "nightmare", "harpy", "ogre",
    ],
    "mythical": [
        "unicorn", "fairy", "mermaid", "phoenix", "centaur",
        "griffin", "pegasus", "dryad", "kitsune", "sphinx",
        "naga", "sylph", "satyr", "kelpie", "valkyrie",
        "djinn", "pixie", "yokai", "selkie", "leprachaun",
    ],
    "robot": [
        "android", "cyborg", "AI hologram", "clockwork automaton",
        "drone", "mecha", "nanite swarm", "industrial bot",
        "companion droid", "sentient starship", "battle mech",
        "service unit", "quantum construct", "steam automaton",
    ],
}

# ── Defaults for unknown countries ───────────────────────────────────

DEFAULT_COUNTRY = {
    "code": "US",
    "city": {"city": "New York City", "region": "New York",
             "lat": 40.71, "lng": -74.01},
    "timezone": "America/New_York",
    "language": "en-US",
    "english_proficiency": 5,
    "gender_weights": {"Female": 0.48, "Male": 0.48,
                       "Non-binary": 0.04},
}
