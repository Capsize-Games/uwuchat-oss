"""Voice sample extraction during episodic summarization.

Extracts 2-3 characteristic assistant lines from a session for next-session
character voice anchoring — directly combating personality drift.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_voice_samples(
    chatbot: Any,
    session_id: int,
    messages: list[dict],
) -> None:
    """Extract 2-3 characteristic assistant lines as voice samples.

    Stores them on chatbot.voice_samples for next-session anchoring.
    Each sample is {text, session_id, captured_at}.
    """
    try:
        from datetime import datetime, timezone

        from airunner_services.database.models.chatbot import Chatbot

        assistant_msgs = [
            m.get("content", "")
            for m in messages
            if isinstance(m, dict) and m.get("role") in ("assistant", "bot")
        ]
        if not assistant_msgs:
            return

        samples: list[dict] = []
        now = datetime.now(timezone.utc).isoformat()

        candidates = [
            m for m in assistant_msgs if 20 <= len(m) <= 200
        ]
        if not candidates:
            candidates = assistant_msgs

        longest = max(candidates, key=len)
        samples.append({
            "text": longest[:200],
            "session_id": session_id,
            "captured_at": now,
        })

        if len(candidates) > 2:
            mid_idx = len(candidates) // 2
            mid = candidates[mid_idx]
            if mid != longest:
                samples.append({
                    "text": mid[:200],
                    "session_id": session_id,
                    "captured_at": now,
                })

        existing = getattr(chatbot, "voice_samples", None) or []
        if not isinstance(existing, list):
            existing = []
        existing.extend(samples)
        if len(existing) > 3:
            existing = existing[-3:]

        Chatbot.objects.update(chatbot.id, voice_samples=existing)
    except Exception:
        pass
