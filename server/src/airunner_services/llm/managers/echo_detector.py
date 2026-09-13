"""Algorithmic echo detection for LLM responses."""

from __future__ import annotations

import string
from typing import Set


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, and collapse whitespace."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return " ".join(text.split())


def _ngrams(words: list[str], n: int) -> Set[str]:
    """Return a set of space-joined n-grams from a word list."""
    result: Set[str] = set()
    for i in range(len(words) - n + 1):
        result.add(" ".join(words[i : i + n]))
    return result


def echo_ratio(user_text: str, bot_text: str) -> float:
    """Return n-gram overlap ratio between user and bot text."""
    user_words = _normalize(user_text).split()
    bot_words = _normalize(bot_text).split()

    user_ngrams: Set[str] = set()
    user_ngrams.update(_ngrams(user_words, 1))
    user_ngrams.update(_ngrams(user_words, 2))

    bot_ngrams: Set[str] = set()
    bot_ngrams.update(_ngrams(bot_words, 1))
    bot_ngrams.update(_ngrams(bot_words, 2))

    if not bot_ngrams:
        return 0.0
    overlap = len(bot_ngrams & user_ngrams)
    return overlap / len(bot_ngrams)


def is_echo(
    user_text: str,
    bot_text: str,
    threshold: float = 0.45,
) -> bool:
    """Return True when the bot response echoes the user message.

    An echo is declared when the n-gram overlap exceeds *threshold*
    AND the bot response is under 120 words (longer responses with
    high overlap are usually legitimate summaries, not echoes).
    """
    ratio = echo_ratio(user_text, bot_text)
    word_count = len(bot_text.split())
    return ratio > threshold and word_count < 120
