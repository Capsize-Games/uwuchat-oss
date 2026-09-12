"""Topic-shift detection for conversation context annotation.

When a user switches to an unrelated subject mid-conversation the LLM
inherits prior context and incorrectly applies it to the new question —
"context bleeding". A human naturally resets their working memory when
the subject changes; this module approximates that by detecting low
word-overlap between the new message and recent turns, then returning an
annotation that tells the model to evaluate relevance before answering
rather than assuming the new subject continues the previous topic.

The specific wording returned depends on whether the chatbot is the
system bot (compliance-oriented: just answer the new topic) or a
roleplay persona (caution-oriented: may react in character).

Only word-overlap (Jaccard similarity) is used here. Embedding-based
similarity (option A) and RAG-style context retrieval (option C) are
planned follow-ups if this heuristic proves insufficient.
"""

from __future__ import annotations

from typing import List

from langchain_core.messages import BaseMessage, HumanMessage

_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "i", "you", "he", "she",
    "it", "we", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "its", "our", "their", "that", "this", "these", "those",
    "what", "who", "which", "when", "where", "why", "how", "and", "or",
    "but", "if", "in", "on", "at", "to", "for", "of", "with", "by",
    "from", "about", "into", "through", "not", "no", "so", "as", "up",
    "out", "then", "than", "more", "some", "tell", "know", "think",
    "just", "also", "any", "all", "there", "here", "get", "got",
}

# Jaccard similarity below this value is treated as a topic change.
# Tuned empirically: "who is joe curlee?" after Colorado-politics context
# scores ~0.04 even with one shared word ("colorado"), well below 0.12.
_SHIFT_THRESHOLD = 0.12

# How many messages before the new one to use as the "prior context" window.
_RECENT_TURNS = 4

_ROLEPLAY_TOPIC_SHIFT_NOTE = (
    "[Context note: The user's message may be starting a new topic "
    "unrelated to the prior conversation. Evaluate whether prior context "
    "applies before answering. Do not assume new subjects are related to "
    "previous topics unless the user explicitly connects them.]"
)

_SYSTEM_BOT_TOPIC_SHIFT_NOTE = (
    "[Context note: The user's message may be starting a new topic "
    "unrelated to the prior conversation. If so, set aside the prior "
    "topic and answer the new one directly and completely, as you "
    "normally would for any user request. Do not ask the user to "
    "explain or justify the change of subject, and do not comment on "
    "the fact that the topic changed unless the user brings it up.]"
)


def _msg_text(msg: BaseMessage) -> str:
    """Extract plain text from a message regardless of content type."""
    if isinstance(msg.content, str):
        return msg.content
    return " ".join(
        b.get("text", "") if isinstance(b, dict) else str(b)
        for b in msg.content
    )


def _tokenize(text: str) -> set[str]:
    """Return lowercase alpha content words, filtering stopwords."""
    return {
        w for w in text.lower().split()
        if w.isalpha() and w not in _STOPWORDS and len(w) > 2
    }


def _prior_tokens(
    messages: List[BaseMessage], end_idx: int
) -> set[str]:
    """Collect content words from the N turns before *end_idx*."""
    start = max(0, end_idx - _RECENT_TURNS)
    tokens: set[str] = set()
    for msg in messages[start:end_idx]:
        tokens |= _tokenize(_msg_text(msg))
    return tokens


def detect_topic_shift(messages: List[BaseMessage]) -> bool:
    """Return True when the last human message appears to change topic.

    Computes Jaccard similarity between content words in the new human
    message and the preceding _RECENT_TURNS messages. Low overlap
    signals a subject pivot rather than a follow-up question.
    """
    if len(messages) < 2:
        return False
    last_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_idx = i
            break
    if last_idx is None or last_idx == 0:
        return False
    new_tokens = _tokenize(_msg_text(messages[last_idx]))
    if not new_tokens:
        return False
    prior = _prior_tokens(messages, last_idx)
    if not prior:
        return False
    jaccard = len(new_tokens & prior) / len(new_tokens | prior)
    return jaccard < _SHIFT_THRESHOLD


def topic_shift_annotation(is_system_bot: bool = False) -> str:
    """Return the annotation to prepend when a topic shift is detected.

    System bots get a compliance-oriented note (answer the new topic
    directly, no pushback). Roleplay bots keep the existing note, which
    permits in-character caution about the abrupt subject change.
    """
    if is_system_bot:
        return _SYSTEM_BOT_TOPIC_SHIFT_NOTE
    return _ROLEPLAY_TOPIC_SHIFT_NOTE
