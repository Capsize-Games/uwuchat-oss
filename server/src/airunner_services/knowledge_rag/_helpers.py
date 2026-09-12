"""Blocked-chatbot scoping, fact fetching, and entity formatting."""

from __future__ import annotations

import logging

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.knowledge_context import get_knowledge_chatbot_id

logger = logging.getLogger(__name__)


class KnowledgeBaseHelpersMixin:
    """Fact-fetching, chatbot scoping, and entity formatting methods."""

    @staticmethod
    def _blocked_chatbot_ids() -> set[int]:
        """Return the set of chatbot IDs that are blocked in either
        direction and should be excluded from omnipotent queries."""
        try:
            from airunner_services.database.models.chatbot import Chatbot
            blocked: set[int] = set()
            for bot in Chatbot.objects.filter_by(
                blocked_by_user=True,
            ) or []:
                blocked.add(bot.id)
            for bot in Chatbot.objects.filter_by(
                has_blocked_user=True,
            ) or []:
                blocked.add(bot.id)
            return blocked
        except Exception:
            return set()

    def get_recent_facts(
        self: "KnowledgeBase",
        limit: int = 50,
    ) -> list[KnowledgeFact]:
        """Return recent unique facts for injection into system prompts."""
        chatbot_id = get_knowledge_chatbot_id()
        q = KnowledgeFact.objects.query().filter(
            KnowledgeFact.deleted.is_(False),
            KnowledgeFact.fact_text != "",
        )
        if chatbot_id is not None:
            q = q.filter(KnowledgeFact.chatbot_id == chatbot_id)
        rows = (
            q.order_by(
                KnowledgeFact.created_at.desc(),
                KnowledgeFact.id.desc(),
            )
            .limit(limit)
            .all()
        )

        seen: set[str] = set()
        unique: list[KnowledgeFact] = []
        for f in rows:
            key = f.fact_text.strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    def get_omnipotent_facts(
        self: "KnowledgeBase",
        limit: int = 50,
    ) -> list[KnowledgeFact]:
        """Return recent facts from ALL non-blocked chatbots.

        Used by the system bot when omnipotent_knowledge is enabled.
        Excludes facts owned by chatbots that are blocked in either
        direction.
        """
        blocked = self._blocked_chatbot_ids()
        q = KnowledgeFact.objects.query().filter(
            KnowledgeFact.deleted.is_(False),
            KnowledgeFact.fact_text != "",
        )
        if blocked:
            q = q.filter(~KnowledgeFact.chatbot_id.in_(blocked))
        rows = (
            q.order_by(
                KnowledgeFact.created_at.desc(),
                KnowledgeFact.id.desc(),
            )
            .limit(limit * 3)
            .all()
        )
        seen: set[str] = set()
        unique: list[KnowledgeFact] = []
        for f in rows:
            key = f.fact_text.strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(f)
                if len(unique) >= limit:
                    break
        return unique

    def search_entity_facts(
        self: "KnowledgeBase",
        entity_id: int,
        k: int = 10,
    ) -> list[str]:
        """Return recent facts about one entity, newest first.

        Fact counts per entity are expected to be small — a direct
        fetch ordered by recency is sufficient and avoids API cost.
        Facts are scoped by entity_id, not chatbot_id, so they are
        visible to any chatbot that can query this entity.
        """
        rows = (
            KnowledgeFact.objects.query()
            .filter(
                KnowledgeFact.entity_id == entity_id,
                KnowledgeFact.deleted.is_(False),
                KnowledgeFact.fact_text != "",
            )
            .order_by(KnowledgeFact.created_at.desc())
            .limit(k)
            .all()
        )
        seen: set[str] = set()
        unique: list[str] = []
        for f in rows:
            key = f.fact_text.strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(f.fact_text)
        return unique

    def get_entity_relationships(
        self: "KnowledgeBase",
        entity_id: int,
    ) -> list[str]:
        """Return formatted relationship descriptions for one entity.

        Structured graph query — not vector search.  Returns lines
        like "connected via email (5 emails)" for each edge.
        """
        from airunner_services.database.models.entity_relationship \
            import EntityRelationship
        from airunner_services.database.models.entity import Entity

        with EntityRelationship.objects.transaction() as tx:
            blocked = self._blocked_chatbot_ids()
            edges_raw = (
                tx.query(EntityRelationship)
                .filter(
                    (EntityRelationship.entity_a_id == entity_id)
                    | (EntityRelationship.entity_b_id == entity_id),
                    EntityRelationship.deleted.is_(False),
                )
                .all()
            )
            if blocked:
                blocked_set = set(blocked)
                other_ids_raw: set[int] = set()
                for e in edges_raw:
                    if e.entity_a_id == entity_id:
                        other_ids_raw.add(e.entity_b_id)
                    else:
                        other_ids_raw.add(e.entity_a_id)
                safe_ids = self._safe_entity_ids(
                    tx, other_ids_raw, blocked_set,
                )
                edges = [
                    e for e in edges_raw
                    if (
                        e.entity_a_id in safe_ids
                        and e.entity_b_id in safe_ids
                    )
                ]
            else:
                edges = edges_raw
            if not edges:
                return []

            other_ids: set[int] = set()
            for edge in edges:
                if edge.entity_a_id == entity_id:
                    other_ids.add(edge.entity_b_id)
                else:
                    other_ids.add(edge.entity_a_id)

            entities = (
                tx.query(Entity)
                .filter(
                    Entity.id.in_(other_ids),
                    Entity.deleted.is_(False),
                )
                .all()
            ) if other_ids else []
            id_to_name = {e.id: e.display_name_ct for e in entities}

            lines: list[str] = []
            for edge in edges:
                other = (
                    edge.entity_b_id if edge.entity_a_id == entity_id
                    else edge.entity_a_id
                )
                name = id_to_name.get(other, "someone")
                lines.append(
                    f"- {name}: connected via email "
                    f"({edge.evidence_count} emails)"
                )
            return lines

    @staticmethod
    def _safe_entity_ids(tx, ids: set[int], blocked: set[int]) -> set[int]:
        """Filter *ids* to only those belonging to non-blocked chatbots."""
        if not ids or not blocked:
            return ids
        from airunner_services.database.models.entity import Entity

        rows = (
            tx.query(Entity.id)
            .filter(
                Entity.id.in_(ids),
                Entity.deleted.is_(False),
                ~Entity.chatbot_id.in_(blocked),
            )
            .all()
        )
        return {r[0] for r in rows}
