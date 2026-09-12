"""Relationship engine — maintains warmth/trust between chatbots and users."""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_WARMTH_DECAY_PER_DAY: float = 0.01
_TRUST_DECAY_PER_DAY: float = 0.005
_INTERACTION_WARMTH_BOOST: float = 0.02
_INTERACTION_TRUST_BOOST: float = 0.01


def _clamp(value: float) -> float:
    """Clamp a value to [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


def _decay_factor(last_at: Optional[datetime.datetime]) -> float:
    """Return accumulated decay since last interaction (never below 0)."""
    if last_at is None:
        return 0.0
    days = (datetime.datetime.utcnow() - last_at).total_seconds() / 86400
    return max(0.0, days)


def get_or_create_relationship(
    chatbot_id: int,
    target_type: str,
    target_id: int,
) -> Any:
    """Return existing relationship or create with neutral defaults."""
    try:
        from airunner_services.database.models.relationship import Relationship
        rel = (
            Relationship.objects.query()
            .filter(
                Relationship.chatbot_id == chatbot_id,
                Relationship.target_type == target_type,
                Relationship.target_id == target_id,
            )
            .first()
        )
        if rel is None:
            rel = Relationship.objects.create(
                chatbot_id=chatbot_id,
                target_type=target_type,
                target_id=target_id,
                warmth=0.5,
                trust=0.5,
                created_at=datetime.datetime.utcnow(),
            )
        return rel
    except Exception:
        logger.exception(
            "get_or_create_relationship failed (%s, %s, %s)",
            chatbot_id, target_type, target_id,
        )
        return None


def record_interaction(
    chatbot_id: int,
    target_type: str,
    target_id: int,
    emotional_weight: float = 0.3,
) -> None:
    """Update warmth/trust after an interaction, applying decay then boost."""
    try:
        from airunner_services.database.models.relationship import Relationship
        rel = get_or_create_relationship(chatbot_id, target_type, target_id)
        if rel is None:
            return

        days = _decay_factor(rel.last_interaction_at)
        warmth = _clamp(
            float(rel.warmth)
            - days * _WARMTH_DECAY_PER_DAY
            + _INTERACTION_WARMTH_BOOST * (1 + emotional_weight)
        )
        trust = _clamp(
            float(rel.trust)
            - days * _TRUST_DECAY_PER_DAY
            + _INTERACTION_TRUST_BOOST
        )
        Relationship.objects.update(
            rel.id,
            warmth=warmth,
            trust=trust,
            last_interaction_at=datetime.datetime.utcnow(),
        )
    except Exception:
        logger.exception(
            "record_interaction failed (%s, %s, %s)",
            chatbot_id, target_type, target_id,
        )


def get_relationship_context(
    chatbot_id: int,
    target_type: str,
    target_id: int,
) -> Optional[str]:
    """Return a one-line relationship summary for prompt injection."""
    try:
        from airunner_services.database.models.relationship import Relationship
        rel = (
            Relationship.objects.query()
            .filter(
                Relationship.chatbot_id == chatbot_id,
                Relationship.target_type == target_type,
                Relationship.target_id == target_id,
            )
            .first()
        )
        if rel is None:
            return None
        warmth = float(rel.warmth)
        trust = float(rel.trust)
        dynamic = rel.dynamic or "acquaintance"
        warmth_label = (
            "deeply fond of"
            if warmth > 0.8 else
            "warm toward"
            if warmth > 0.6 else
            "neutral toward"
            if warmth > 0.4 else
            "reserved with"
        )
        trust_label = (
            "fully trusts"
            if trust > 0.8 else
            "generally trusts"
            if trust > 0.6 else
            "cautiously trusts"
            if trust > 0.4 else
            "guarded with"
        )
        return (
            f"Relationship: {dynamic} — {warmth_label} this person,"
            f" {trust_label} them."
        )
    except Exception:
        return None
