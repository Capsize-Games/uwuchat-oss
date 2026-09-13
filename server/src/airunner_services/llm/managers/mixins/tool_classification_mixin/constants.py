"""Module-level constants for tool classification heuristics."""

from __future__ import annotations

import re

_BELOW_MIN_COMPLEXITY = "below_min_complexity"

# Phrases that indicate the user is referencing a specific real-world
# entity even when phrased as a casual statement (not a question).
# When any of these appear, the complexity gate is bypassed so the
# LLM classifier can decide whether search is needed.
#
# This is a heuristic fallback — not a semantic parser.  It should be
# broad enough to catch casual real-world references ("the government
# is targeting…", "I heard about a policy…") without requiring every
# possible proper noun.  The proper-noun heuristic
# (_contains_proper_noun_reference) provides a second layer for names
# not in this list.
_ENTITY_REFERENCE_TRIGGERS: frozenset[str] = frozenset({
    # Media / culture (existing)
    "made fun", "parodi", "satiri", "episode", "season",
    "movie", "film", "album", "show", "series",
    "news", "article", "headline", "report", "story",
    "president", "senator", "congress", "ceo", "cto",
    "trending", "viral", "according to",
    "box office", "review", "reviews", "critic", "critics",
    "rating", "ratings", "rotten tomatoes",
    "premiere", "opening weekend",
    # Places (existing)
    "city", "state", "country", "place", "town",
    "location", "area", "region",
    # Government / regulatory / political action
    "government", "administration", "official", "officials",
    "agency", "department", "ministry", "regulator",
    "regulation", "regulations", "sanctions", "sanction",
    "tariff", "tariffs", "trade war",
    "policy", "policies", "legislation", "bill",
    "executive order", "law", "laws",
    "ban", "banned", "banning", "restrict", "restrictions",
    "investigation", "investigating", "probe",
    # Organizations / companies
    "company", "companies", "corporation", "startup",
    "firm", "firms", "industry", "industries",
    "tech giant", "big tech",
    # Technology / AI
    "artificial intelligence", "machine learning",
    "chatbot", "chatbots",
    # Casual evidence-hedging (real-world statements, not questions)
    "i heard", "i read", "they say", "apparently",
    "i saw", "someone told me",
})

# Personal-life nouns — relationship, family, and life-detail terms
# that, when paired with a possessive ("my"/"our"), indicate a query
# about stored personal facts rather than real-world entities.
# Detected via word-boundary matching with up to 2 filler words
# between the possessive and the noun (e.g. "my darling wife").
_PERSONAL_LIFE_NOUNS: frozenset[str] = frozenset({
    # Family / relationships
    "wife", "husband", "partner", "spouse", "girlfriend",
    "boyfriend", "fiancé", "fiancée",
    "mom", "dad", "mother", "father", "parent", "parents",
    "son", "daughter", "child", "children", "kid", "kids",
    "sister", "brother", "sibling", "siblings",
    "family", "relatives", "aunt", "uncle", "cousin",
    "grandmother", "grandfather", "grandma", "grandpa",
    "niece", "nephew", "stepmother", "stepfather",
    # Personal life / identity
    "job", "work", "career", "birthday", "anniversary",
    "pet", "dog", "cat", "name", "address", "home",
    "relationship", "relationships",
    "health", "age", "hobby", "hobbies",
    "education", "school", "college",
})

# Phrases that explicitly ask the bot to recall or retrieve stored
# information — bypass the complexity gate when the conversation
# context is about personal facts.
_RECALL_DIRECTIVE_TRIGGERS: frozenset[str] = frozenset({
    "you should have",
    "you should know",
    "you must have",
    "you must know",
    "don't you have",
    "don't you know",
    "don't you remember",
    "do you have",
    "do you know",
    "do you remember",
    "look it up",
    "look that up",
    "look this up",
    "look them up",
    "you're supposed to know",
    "you're supposed to have",
    "you ought to know",
    "you ought to have",
})

# Lookup tool names used to detect when a terse follow-up arrives
# in a conversation where the assistant recently performed a
# lookup (search, news, or weather).  Terse messages in such
# conversations bypass the complexity gate so the classifier can
# decide whether to look up again — avoiding both "digest tunnel
# vision" (an earlier broad digest treated as exhaustive) and a
# false "I don't have that tool" response to a bare follow-up like
# "check again" right after a weather lookup.
_SEARCH_NEWS_TOOL_NAMES: frozenset[str] = frozenset({
    "get_topic_brief",
    "search_news",
    "search_fastsearch",
    "search_fastsearch_news",
    "get_daily_newspaper",
    "get_my_weather",
    "search_weather",
})

# Maps each lookup tool name to its ToolCategory value so that a
# retry/continuation follow-up after a recent lookup can re-enable
# the correct category without re-running the full classifier.
_LOOKUP_TOOL_CATEGORY: dict[str, str] = {
    "get_topic_brief": "search",
    "search_news": "search",
    "search_fastsearch": "search",
    "search_fastsearch_news": "search",
    "get_daily_newspaper": "search",
    "get_my_weather": "system",
    "search_weather": "system",
    "launch_headlesscode_session": "code",
    # Code-mode inline agent tools (thin proxy to the headlesscode
    # executor — see projects/uwuchat/server/tools/code_tools/proxy_tools.py).
    # A recent code-tool call should re-enable the "code" category on a
    # retry/continuation follow-up.
    "apply_diff": "code",
    "codebase_search": "code",
    "edit_file": "code",
    "execute_command": "code",
    "list_files": "code",
    "read_file": "code",
    "run_tests": "code",
    "search_replace": "code",
    "write_to_file": "code",
}

# Max word count for a message to be considered "terse."
_TERSE_MAX_WORDS: int = 8

_REFUSAL_PATTERNS = re.compile(
    r"can['\u2019]t\s+engage|hate\s+speech|"
    r"i\s+(?:cannot|can['\u2019]t)\s+(?:help|assist|respond|create|"
    r"generate|provide|engage|participate|comply)|"
    r"i['\u2019]m\s+not\s+(?:able|willing)\s+to|"
    r"against\s+(?:my|our)\s+(?:policy|guidelines|rules)",
    re.IGNORECASE,
)
