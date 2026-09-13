"""Shared helpers for knowledge retrieval scale tests.

Provides utilities to load ground-truth fixtures, seed them into the
ephemeral tenant schema, execute search queries, and detect which code
path (vector vs. TF-IDF) was used.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from airunner_services.database.models.knowledge_fact import KnowledgeFact
from airunner_services.database.models.knowledge_fact_tag import (
    KnowledgeFactTag,
)
from airunner_services.database.models.knowledge_tag import KnowledgeTag
from airunner_services.knowledge import KnowledgeBase
from airunner_services.knowledge_context import (
    set_knowledge_chatbot_id,
    set_knowledge_subject,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class GroundTruthCase:
    """One query → expected-fact pair loaded from the fixture file."""

    case_id: str
    fact_text: str
    query: str
    chatbot_id: int
    subject: str
    tags: list[str]
    expected_keywords: list[str]
    fact_db_id: int = 0
    seed_scale: int = 0


@dataclass
class RecallResult:
    """Result of one recall check at one scale."""

    case_id: str
    scale: int
    found: bool
    rank: int  # 1-based rank in results, 0 if not found
    path_used: str  # "vector", "tfidf", or "unknown"
    latency_ms: float
    top_results: list[str] = field(default_factory=list)


@dataclass
class ScaleReport:
    """Aggregate report for all cases at all scales."""

    scales: list[int]
    results: list[RecallResult] = field(default_factory=list)

    def accuracy_at_scale(self, scale: int) -> float:
        """Return accuracy (0.0–1.0) at a given scale."""
        scale_results = [r for r in self.results if r.scale == scale]
        if not scale_results:
            return 0.0
        return sum(1 for r in scale_results if r.found) / len(scale_results)

    def summary(self) -> str:
        """Return a human-readable accuracy/latency report."""
        lines = ["Scale | Accuracy | Avg Latency (ms) | Vector %"]
        lines.append("-" * 50)
        for scale in sorted(set(r.scale for r in self.results)):
            scale_results = [r for r in self.results if r.scale == scale]
            if not scale_results:
                continue
            acc = sum(1 for r in scale_results if r.found) / len(scale_results)
            avg_lat = sum(r.latency_ms for r in scale_results) / len(
                scale_results,
            )
            vector_pct = (
                sum(
                    1
                    for r in scale_results
                    if r.path_used == "vector"
                )
                / len(scale_results)
                * 100
            )
            lines.append(
                f"{scale:>5} | {acc:>7.1%} | {avg_lat:>16.1f} | "
                f"{vector_pct:>6.0f}%",
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def load_ground_truth_cases() -> list[GroundTruthCase]:
    """Load the version-controlled ground-truth fixture file."""
    path = _FIXTURES_DIR / "ground_truth_cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        GroundTruthCase(
            case_id=c["id"],
            fact_text=c["fact_text"],
            query=c["query"],
            chatbot_id=c["chatbot_id"],
            subject=c["subject"],
            tags=c["tags"],
            expected_keywords=c["expected_keywords"],
        )
        for c in data["cases"]
    ]


# ---------------------------------------------------------------------------
# Database seeding
# ---------------------------------------------------------------------------


def seed_ground_truth_facts(
    cases: list[GroundTruthCase],
    embedding_model: Any = None,
) -> None:
    """Insert ground-truth needle facts into the current tenant schema.

    Each fact's database ID is written back into the case object for
    later recall verification.
    """
    for case in cases:
        set_knowledge_chatbot_id(case.chatbot_id)
        set_knowledge_subject(case.subject)

        embedding = None
        if embedding_model is not None:
            from airunner_services.llm.managers.agent.pgvector_store import (
                embed_passages,
            )

            vectors = embed_passages(embedding_model, [case.fact_text])
            embedding = vectors[0] if vectors else None

        with KnowledgeFact.objects.transaction() as tx:
            fact = KnowledgeFact(
                fact_text=case.fact_text,
                chatbot_id=case.chatbot_id,
                subject=case.subject,
                embedding=embedding,
            )
            tx.add(fact)
            tx.flush()
            case.fact_db_id = int(getattr(fact, "id"))

            for tag_name in case.tags:
                tag = _get_or_create_tag(tx, tag_name, case.chatbot_id)
                link = KnowledgeFactTag(fact_id=fact.id, tag_id=tag.id)
                tx.add(link)


def refresh_ground_truth_timestamps(
    cases: list[GroundTruthCase],
) -> None:
    """Update ``created_at`` on GT facts so they appear as the most recent.

    ``get_omnipotent_facts`` / ``get_recent_facts`` both order by
    ``created_at DESC`` and cap at 500 rows.  When GT needle facts are
    seeded before bulk noise, they become the oldest rows and fall
    outside the recency window, making them invisible to TF-IDF search.

    Calling this after noise seeding moves GT facts back to the top of
    the window.
    """
    from datetime import datetime, UTC

    with KnowledgeFact.objects.transaction() as tx:
        for case in cases:
            tx.query(KnowledgeFact).filter(
                KnowledgeFact.id == case.fact_db_id,
            ).update(
                {"created_at": datetime.now(UTC)},
                synchronize_session=False,
            )


def _get_or_create_tag(tx: Any, name: str, chatbot_id: int) -> KnowledgeTag:
    """Return an existing KnowledgeTag or create one."""
    q = tx.query(KnowledgeTag).filter(KnowledgeTag.name == name)
    if chatbot_id is not None:
        q = q.filter(KnowledgeTag.chatbot_id == chatbot_id)
    tag = q.first()
    if tag is None:
        tag = KnowledgeTag(name=name, chatbot_id=chatbot_id)
        tx.add(tag)
        tx.flush()
    return tag


# ---------------------------------------------------------------------------
# Search and recall checking
# ---------------------------------------------------------------------------


def run_recall_check(
    case: GroundTruthCase,
    embedding_model: Any = None,
    top_k: int = 5,
) -> RecallResult:
    """Run a query against the knowledge base and check recall.

    Returns a ``RecallResult`` with whether the expected fact was found
    in the top-k results, which code path was used, and latency.
    """
    set_knowledge_chatbot_id(case.chatbot_id)
    set_knowledge_subject(case.subject)

    path_tracker: dict[str, bool] = {"vector_hit": False, "tfidf_hit": False}
    _install_path_tracker(path_tracker)
    try:
        kb = KnowledgeBase()
        start = time.monotonic()
        results = kb.search_omnipotent_rag(
            case.query,
            k=top_k,
            agent=_mock_agent(embedding_model),
        )
        elapsed_ms = (time.monotonic() - start) * 1000
    finally:
        _remove_path_tracker()

    path_used = _resolve_path(path_tracker)

    found = False
    rank = 0
    for i, result_text in enumerate(results, start=1):
        if case.fact_text.strip().lower() in result_text.strip().lower():
            found = True
            rank = i
            break

    return RecallResult(
        case_id=case.case_id,
        scale=case.seed_scale,
        found=found,
        rank=rank,
        path_used=path_used,
        latency_ms=elapsed_ms,
        top_results=results[:top_k],
    )


def _mock_agent(embedding_model: Any) -> Any:  # type: ignore[return]
    """Return a minimal object with an ``embedding`` attribute."""

    class _MockAgent:
        embedding = embedding_model

    return _MockAgent()


# ---------------------------------------------------------------------------
# Search path instrumentation
#
# Monkey-patches ``KnowledgeBase`` methods to record which code path
# (vector similarity or TF-IDF keyword fallback) served each query.
# ---------------------------------------------------------------------------

_original_similarity: Any = None
_original_tfidf: Any = None


def _install_path_tracker(tracker: dict[str, bool]) -> None:
    """Monkey-patch KnowledgeBase to track which search path is used."""
    global _original_similarity, _original_tfidf

    _original_similarity = KnowledgeBase._similarity_search_omnipotent  # type: ignore[assignment]
    _original_tfidf = KnowledgeBase._search_facts_omnipotent  # type: ignore[assignment]

    def _tracked_similarity(
        self: KnowledgeBase,
        query_text: str,
        k: int = 5,
        embedding_model: Any = None,
    ) -> Any:
        tracker["vector_hit"] = True
        return _original_similarity(self, query_text, k, embedding_model)

    def _tracked_tfidf(
        self: KnowledgeBase,
        query: str,
        limit: int = 20,
    ) -> Any:
        tracker["tfidf_hit"] = True
        return _original_tfidf(self, query, limit)

    KnowledgeBase._similarity_search_omnipotent = _tracked_similarity  # type: ignore[assignment]
    KnowledgeBase._search_facts_omnipotent = _tracked_tfidf  # type: ignore[assignment]


def _remove_path_tracker() -> None:
    """Restore original methods after instrumentation."""
    global _original_similarity, _original_tfidf
    if _original_similarity is not None:
        KnowledgeBase._similarity_search_omnipotent = _original_similarity  # type: ignore[assignment]
    if _original_tfidf is not None:
        KnowledgeBase._search_facts_omnipotent = _original_tfidf  # type: ignore[assignment]
    _original_similarity = None
    _original_tfidf = None


def _resolve_path(tracker: dict[str, bool]) -> str:
    """Determine which search path was used from tracker state."""
    if tracker.get("vector_hit") and not tracker.get("tfidf_hit"):
        return "vector"
    if tracker.get("tfidf_hit") and not tracker.get("vector_hit"):
        return "tfidf"
    if tracker.get("vector_hit") and tracker.get("tfidf_hit"):
        return "vector+tfidf_fallback"
    return "unknown"
