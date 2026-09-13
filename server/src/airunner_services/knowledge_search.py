"""Search and query mixin for KnowledgeBase."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.knowledge_context import get_knowledge_chatbot_id

if TYPE_CHECKING:
    from airunner_services.knowledge import KnowledgeBase


# Common English stop words for keyword extraction
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would could should may might must shall can what who where "
    "when why how which i me my we our you your he she it its they "
    "their them his her this that these those and or but if of in on "
    "at to for with by from up about into through during before after "
    "above below between among while so then just only also not no ".split()
)


def _fmt_ts(dt: Optional[datetime]) -> str:
    """Format a datetime as 'YYYY-MM-DD HH:MM:SS' or empty string."""
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class KnowledgeBaseSearchMixin:
    """Search, query, and context retrieval methods."""

    def search_facts(
        self: "KnowledgeBase",
        query: str,
        limit: int = 20,
        date_str: Optional[str] = None,
        tag: Optional[str] = None,
        section: Optional[str] = None,
    ) -> list[KnowledgeFact]:
        """Search facts with TF-IDF ranking over decrypted rows.

        fact_text is encrypted with UserEncryptedText — ILIKE/substring
        queries on ciphertext never match.  All searches go through
        in-memory TF-IDF over the decrypted candidate set.
        """
        if section is not None and tag is None:
            tag = section

        keywords = self._extract_keywords(query)
        if not keywords:
            return []

        # Always use in-memory TF-IDF — ILIKE on ciphertext is impossible.
        return self._in_memory_search(query, limit)

    def _in_memory_search(
        self: "KnowledgeBase",
        query: str,
        limit: int,
        min_score: float = 0.1,
    ) -> list[KnowledgeFact]:
        """TF-IDF over all decrypted facts; filters below min_score so generic greetings inject nothing."""
        all_facts = self.get_recent_facts(  # type: ignore[attr-defined]
            limit=min(limit * 40, 500)
        )
        if not all_facts:
            return []
        return self._tfidf_rank(all_facts, query, limit, min_score=min_score)

    def search(
        self: "KnowledgeBase",
        query: str,
        max_results: int = 10,
    ) -> list[dict[str, str]]:
        """Keyword + TF-IDF search; returns dicts with 'line' and 'timestamp', most-recent first."""
        facts = self.search_facts(query, limit=max_results)
        facts.sort(
            key=lambda f: f.created_at or datetime.min, reverse=True
        )
        return [
            {
                "line": f.fact_text,
                "timestamp": _fmt_ts(f.created_at),
            }
            for f in facts
            if f.fact_text
        ]

    def search_tfidf(
        self: "KnowledgeBase",
        query: str,
        max_results: int = 5,
    ) -> list[dict[str, str]]:
        """TF-IDF search — alias of search for backward compat."""
        return self.search(query, max_results=max_results)

    def get_context(
        self: "KnowledgeBase",
        max_chars: int = 2000,
    ) -> str:
        """Return recent facts as markdown for system-prompt injection."""
        from airunner_services.knowledge_helpers import (
            _format_facts_as_markdown,
        )

        facts = self.get_recent_facts(limit=30)
        if not facts:
            return ""
        return _format_facts_as_markdown(facts)[:max_chars]

    def get_omnipotent_context(
        self: "KnowledgeBase",
        max_chars: int = 2000,
    ) -> str:
        """Return recent facts from ALL non-blocked chatbots as markdown.

        Used by the system bot when omnipotent_knowledge is enabled.
        """
        from airunner_services.knowledge_helpers import (
            _format_facts_as_markdown,
        )

        facts = self.get_omnipotent_facts(limit=30)
        if not facts:
            return ""
        return _format_facts_as_markdown(facts)[:max_chars]

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Strip punctuation and return meaningful keywords from *text*."""
        import re as _re

        tokens = _re.sub(r"[^\w\s]", " ", text.lower()).split()
        return [t for t in tokens if len(t) >= 3 and t not in _STOP_WORDS]

    def _build_base_query(self, keywords: list[str]):
        """Return all non-deleted facts for the current chatbot.

        ILIKE is not used — fact_text is encrypted with
        UserEncryptedText; filtering happens in-memory via TF-IDF.
        """
        chatbot_id = get_knowledge_chatbot_id()
        base = KnowledgeFact.objects.query().filter(
            KnowledgeFact.deleted.is_(False),
        )
        if chatbot_id is not None:
            base = base.filter(KnowledgeFact.chatbot_id == chatbot_id)
        return base

    def _apply_date_filter(self, builder, date_str: Optional[str]):
        """Apply an optional date filter to *builder*."""
        if date_str is None:
            return builder
        from sqlalchemy import func

        target = self._parse_date(date_str)
        return builder.filter(func.date(KnowledgeFact.created_at) == target)

    def _apply_tag_filter(self, builder, tag: Optional[str]):
        """Apply an optional tag filter to *builder*."""
        if tag is None:
            return builder
        from airunner_services.database.models.knowledge_fact_tag import (
            KnowledgeFactTag,
        )
        from airunner_services.database.models.knowledge_tag import (
            KnowledgeTag,
        )

        return (
            builder.join(
                KnowledgeFactTag,
                KnowledgeFactTag.fact_id == KnowledgeFact.id,
            )
            .join(KnowledgeTag, KnowledgeTag.id == KnowledgeFactTag.tag_id)
            .filter(KnowledgeTag.name.ilike(f"%{tag}%"))
        )

    def _tfidf_rank(
        self,
        candidates: list,
        query: str,
        limit: int,
        min_score: float = 0.0,
    ) -> list[KnowledgeFact]:
        """TF-IDF rank *candidates*; filters below *min_score* when non-zero."""
        texts = [f.fact_text for f in candidates]
        try:
            tfidf = TfidfVectorizer(stop_words="english")
            matrix = tfidf.fit_transform(texts)
            scores = cosine_similarity(tfidf.transform([query]), matrix).flatten()
            scored = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
            return [f for f, s in scored if s >= min_score][:limit]
        except Exception:
            return candidates[:limit] if min_score == 0.0 else []

    def _get_facts_for_date(
        self: "KnowledgeBase",
        target_date: date,
    ) -> list[KnowledgeFact]:
        """Return non-deleted facts for a specific date, scoped by chatbot."""
        from sqlalchemy import func

        chatbot_id = get_knowledge_chatbot_id()
        q = KnowledgeFact.objects.query().filter(
            func.date(KnowledgeFact.created_at) == target_date,
            KnowledgeFact.deleted.is_(False),
        )
        if chatbot_id is not None:
            q = q.filter(KnowledgeFact.chatbot_id == chatbot_id)
        return q.order_by(KnowledgeFact.id).all()

    def _get_facts_for_tag(
        self: "KnowledgeBase",
        tag: str,
    ) -> list[KnowledgeFact]:
        """Return non-deleted facts for a given tag name."""
        from airunner_services.database.models.knowledge_fact_tag import (
            KnowledgeFactTag,
        )
        from airunner_services.database.models.knowledge_tag import (
            KnowledgeTag,
        )

        return (
            KnowledgeFact.objects.query()
            .join(
                KnowledgeFactTag,
                KnowledgeFactTag.fact_id == KnowledgeFact.id,
            )
            .join(KnowledgeTag, KnowledgeTag.id == KnowledgeFactTag.tag_id)
            .filter(
                KnowledgeFact.deleted.is_(False),
                KnowledgeTag.name.ilike(f"%{tag}%"),
            )
            .order_by(KnowledgeFact.id)
            .all()
        )
