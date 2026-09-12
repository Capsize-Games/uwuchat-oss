"""Tag normalisation and linking for knowledge facts.

``_normalise_tags`` merges the deprecated ``section`` kwarg into the
tag list; ``KnowledgeBaseTagMixin`` resolves or creates
``KnowledgeTag`` rows and links facts to them via
``KnowledgeFactTag`` rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from airunner_services.database.models.knowledge_fact import (
        KnowledgeFact,
    )


class KnowledgeBaseTagMixin:
    """KnowledgeTag creation and fact-tag linking helpers."""

    @staticmethod
    def _get_or_create_tag(tx, name: str, chatbot_id: Optional[int] = None):
        """Return an existing KnowledgeTag or create one."""
        from airunner_services.database.models.knowledge_tag import (
            KnowledgeTag,
        )

        q = tx.query(KnowledgeTag).filter(KnowledgeTag.name == name)
        if chatbot_id is not None:
            q = q.filter(KnowledgeTag.chatbot_id == chatbot_id)
        else:
            q = q.filter(KnowledgeTag.chatbot_id.is_(None))
        tag = q.first()
        if tag is None:
            tag = KnowledgeTag(name=name, chatbot_id=chatbot_id)
            tx.add(tag)
            tx.flush()
        return tag

    @staticmethod
    def _link_fact_tags(
        tx,
        fact: KnowledgeFact,
        tag_names: list[str],
        chatbot_id: Optional[int] = None,
    ) -> None:
        """Create KnowledgeFactTag rows linking fact to each tag name."""
        from airunner_services.database.models.knowledge_fact_tag import (
            KnowledgeFactTag,
        )

        for name in tag_names:
            name = name.strip()
            if not name:
                continue
            tag = KnowledgeBaseTagMixin._get_or_create_tag(
                tx,
                name,
                chatbot_id=chatbot_id,
            )
            link = KnowledgeFactTag(fact_id=fact.id, tag_id=tag.id)
            tx.add(link)


def _normalise_tags(
    tags: "str | list[str] | None",
    section: "str | None",
) -> list[str]:
    """Normalise tags, merging section kwarg into the list."""
    resolved: list[str] = []
    if tags is not None:
        if isinstance(tags, str):
            resolved = [t.strip() for t in tags.split(",") if t.strip()]
        else:
            resolved = [t.strip() for t in tags if t and t.strip()]
    if section:
        tag_from_section = section.strip()
        if tag_from_section and tag_from_section not in resolved:
            resolved.insert(0, tag_from_section)
    return resolved
