"""Class-level trigger patterns for the tool classification mixin."""

from __future__ import annotations

from typing import Tuple


class ToolClassificationPatternsMixin:
    """Trigger-word tables and simple-prompt pattern lists.

    These class attributes are inherited by the composed
    ``ToolClassificationMixin`` so tests and callers can read them as
    ``ToolClassificationMixin.SEARCH_TRIGGER_WORDS`` etc.
    """

    ALWAYS_INCLUDE_CATEGORIES = {"mood", "orchestration"}
    # Datetime patterns removed — current datetime is now injected
    # directly into the per-turn context block so the model always
    # has it without needing a tool call.
    SIMPLE_SYSTEM_TOOL_PATTERNS: Tuple[Tuple[str, str], ...] = ()
    SIMPLE_GREETING_PATTERNS: Tuple[str, ...] = (
        r"^\s*hello[!.?,\s]*$",
        r"^\s*hi[!.?,\s]*$",
        r"^\s*hey[!.?,\s]*$",
        r"^\s*yo[!.?,\s]*$",
        r"^\s*sup[!.?,\s]*$",
        r"^\s*good\s+morning[!.?,\s]*$",
        r"^\s*good\s+afternoon[!.?,\s]*$",
        r"^\s*good\s+evening[!.?,\s]*$",
        r"^\s*thanks[!.?,\s]*$",
        r"^\s*thank\s+you[!.?,\s]*$",
    )
    SIMPLE_NO_TOOL_PATTERNS: Tuple[str, ...] = (
        r"^\s*how\s+are\s+you[!.?,\s]*$",
        r"^\s*who\s+are\s+you[!.?,\s]*$",
        r"^\s*what(?:'s|\s+is)\s+your\s+name[!.?,\s]*$",
        r"^\s*what\s+can\s+you\s+do[!.?,\s]*$",
        r"^\s*(?:tell\s+me\s+another|another\s+one)\b.*$",
        r"^\s*(?:like\s+what|for\s+example)[!.?,\s]*$",
        r"^\s*(?:can\s+you\s+)?tell\s+me\s+" r"(?:a|another)?\s*joke\b.*$",
        r"^\s*(?:please\s+)?(?:tell\s+me|write\s+me|make\s+up)\s+"
        r"(?:a|another)?\s*(?:story|poem|haiku|riddle)\b.*$",
        r"^\s*(?:give\s+me|share)\s+(?:a\s+)?" r"(?:fun\s+fact|quote)\b.*$",
        r"^\s*(?:make\s+me\s+laugh|be\s+funny)[!.?,\s]*$",
    )
    CONSTRAINED_REPLY_HINTS: Tuple[str, ...] = (
        "single digit",
        "one digit",
        "single character",
        "one character",
        "single letter",
        "one letter",
        "single word",
        "one word",
    )
    SEARCH_TRIGGER_WORDS: Tuple[str, ...] = (
        "search",
        "look up",
        "lookup",
        "find",
        "google",
        "bing",
        "duckduckgo",
        "ddg",
        "web",
        "internet",
        "news",
        "latest",
        "recent",
    )
    IMAGE_TRIGGER_WORDS: Tuple[str, ...] = (
        "generate an image",
        "generate a picture",
        "create an image",
        "create a picture",
        "draw an image",
        "draw a picture",
        "make an image",
        "make a picture",
        "generate image",
        "generate picture",
        "create image",
        "create picture",
        "draw image",
        "draw picture",
        "make image",
        "make picture",
        "image of",
        "picture of",
        "photo of",
        "painting of",
        "illustration of",
    )
    CALENDAR_TRIGGER_WORDS: Tuple[str, ...] = (
        "remind me",
        "add to my calendar",
        "add to calendar",
        "schedule a",
        "schedule an",
        "set a reminder",
        "set reminder",
        "don't let me forget",
        "put on my calendar",
        "put on the calendar",
        "block off",
        "calendar event",
        "create event",
        "make an appointment",
        "make appointment",
    )
    RECALL_TRIGGER_WORDS: Tuple[str, ...] = (
        "yesterday",
        "today",
        "last week",
        "this morning",
        "last time we talked",
        "what did we talk about",
        "do you remember when",
        "our last conversation",
        "my email",
        "my inbox",
        "from my email",
        "in my email",
        "our conversation",
        "our conversations",
        "past conversation",
        "past conversations",
        "our past conversations",
        "from our conversation",
        "from our conversations",
        "in our conversation",
        "in our conversations",
        "we discussed",
        "we've discussed",
        "we talked about",
    )
    WEATHER_TRIGGER_WORDS: Tuple[str, ...] = (
        "weather",
        "forecast",
        "temperature outside",
        "how hot",
        "how cold",
        "how humid",
        "is it raining",
        "is it snowing",
        "going to rain",
        "going to snow",
        "sunny",
        "cloudy",
        "windy",
        "degrees out",
        "degrees today",
        "air quality",
    )
    MATH_TRIGGER_WORDS: Tuple[str, ...] = (
        "calculate",
        "compute",
        "solve for",
        "solve the equation",
        "what is the sum",
        "what's the sum",
        "percent of",
        "percentage of",
        "square root",
        "cube root",
        "derivative",
        "integral",
        "factorial",
        "divided by",
        "average of",
        "mean of",
        "how much total",
        "total cost",
    )
    RETRY_PHRASE_TRIGGERS: Tuple[str, ...] = (
        "try again",
        "try one more time",
        "one more time",
        "try that again",
        "retry",
        "please try again",
        "go ahead and try again",
    )
