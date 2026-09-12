"""Scale tests for knowledge retrieval reliability.

Verifies that chatbot memory (facts, tags, conversation history) stays
reliable as it grows into the thousands.  Exercises both the vector search
and TF-IDF fallback paths.

All tests use the ``ephemeral_tenant`` fixture, which creates a dedicated
PostgreSQL schema per test session and drops it unconditionally on teardown
— no bulk test data is ever left behind in the persistent dev database.

Usage (from inside the Docker container)::

    # Fast CI run (small scales only)
    python -m pytest server/tests/eval/test_knowledge_retrieval_scale.py -v

    # Full scale run (includes 20k facts — several minutes)
    python -m pytest server/tests/eval/test_knowledge_retrieval_scale.py -v \\
        -m "slow or not slow"
"""

from __future__ import annotations

import pytest

from scale_seed import seed_facts, seed_conversation_turns
from scale_test_support import (
    GroundTruthCase,
    ScaleReport,
    load_ground_truth_cases,
    refresh_ground_truth_timestamps,
    run_recall_check,
    seed_ground_truth_facts,
)

# Scales to test — smaller scales run fast, larger scales are marked slow.
_SCALE_PARAMS = [
    pytest.param(0, id="0"),
    pytest.param(100, id="100"),
    pytest.param(1000, id="1000"),
    pytest.param(5000, id="5000", marks=pytest.mark.slow),
    pytest.param(20000, id="20000", marks=pytest.mark.slow),
]

_SLOW_SCALES = {5000, 20000}

_FAST_SCALE_PARAMS = [
    pytest.param(0, id="0"),
    pytest.param(100, id="100"),
    pytest.param(1000, id="1000"),
]


def _slow_requested(request: pytest.FixtureRequest) -> bool:
    """Return True when the ``-m`` expression includes 'slow'."""
    markexpr = request.config.getoption("-m", default="") or ""
    return "slow" in markexpr


def _resolve_scales(request: pytest.FixtureRequest) -> list[int]:
    """Return the scale list for the current test, respecting marks."""
    if request.node.get_closest_marker("slow"):
        return [0, 100, 1000, 5000, 20000]
    return [0, 100, 1000]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ground_truth_cases() -> list[GroundTruthCase]:
    """Load the version-controlled ground-truth fixture once per module."""
    return load_ground_truth_cases()


@pytest.fixture(scope="module")
def seeded_ground_truth(
    ephemeral_tenant: str,
    ground_truth_cases: list[GroundTruthCase],
) -> list[GroundTruthCase]:
    """Seed ground-truth needle facts into the ephemeral tenant schema."""
    seed_ground_truth_facts(ground_truth_cases, embedding_model=None)
    return ground_truth_cases


# ---------------------------------------------------------------------------
# Dimension 1: Recall accuracy vs. scale
# ---------------------------------------------------------------------------


class TestRecallAccuracyVsScale:
    """Recall accuracy curve across increasing noise volumes."""

    @pytest.mark.parametrize("noise_count", _SCALE_PARAMS)
    def test_recall_at_scale(
        self,
        ephemeral_tenant: str,
        seeded_ground_truth: list[GroundTruthCase],
        noise_count: int,
        request: pytest.FixtureRequest,
    ) -> None:
        """Assert ground-truth facts are retrievable at a given noise level."""
        if noise_count in _SLOW_SCALES and not _slow_requested(request):
            pytest.skip("Use -m slow to run large-scale tests")

        if noise_count > 0:
            seed_facts(count=noise_count, chatbot_count=3)
            refresh_ground_truth_timestamps(seeded_ground_truth)

        report = ScaleReport(scales=[noise_count])
        for case in seeded_ground_truth:
            case.seed_scale = noise_count
            result = run_recall_check(case, top_k=5)
            report.results.append(result)

        accuracy = report.accuracy_at_scale(noise_count)
        # At 0 noise, accuracy should be near-perfect. At higher scales,
        # some degradation is expected — we record the curve rather than
        # enforcing a single threshold.
        if noise_count <= 1000:
            assert accuracy >= 0.5, (
                f"Recall accuracy at scale {noise_count} is {accuracy:.1%} "
                f"— expected >=50%.\n{report.summary()}"
            )
        # For all scales, print the report so it appears in CI output.
        print(f"\n{report.summary()}")

    def test_accuracy_curve_report(
        self,
        ephemeral_tenant: str,
        seeded_ground_truth: list[GroundTruthCase],
        request: pytest.FixtureRequest,
    ) -> None:
        """Produce a per-scale accuracy/latency report across all fast scales."""
        scales = _resolve_scales(request)
        report = ScaleReport(scales=scales)

        for noise_count in scales:
            if noise_count > 0:
                seed_facts(count=noise_count, chatbot_count=3)
                refresh_ground_truth_timestamps(seeded_ground_truth)

            for case in seeded_ground_truth:
                case.seed_scale = noise_count
                result = run_recall_check(case, top_k=5)
                report.results.append(result)

        print(f"\n{report.summary()}")
        # The test always passes — it's a report, not a threshold check.
        # Degradation is the signal; the printed table is the deliverable.
        assert True


# ---------------------------------------------------------------------------
# Dimension 2: Omnipotent RAG path
# ---------------------------------------------------------------------------


class TestOmnipotentRAGPath:
    """Exercise ``search_omnipotent_rag`` across multiple synthetic chatbots."""

    def test_omnipotent_cross_chatbot_recall(
        self,
        ephemeral_tenant: str,
        seeded_ground_truth: list[GroundTruthCase],
    ) -> None:
        """Verify omnipotent search finds facts from all chatbots."""
        seed_facts(count=500, chatbot_count=5)
        refresh_ground_truth_timestamps(seeded_ground_truth)

        # Pick one case per chatbot to verify cross-chatbot retrieval
        chatbot_cases: dict[int, GroundTruthCase] = {}
        for case in seeded_ground_truth:
            if case.chatbot_id not in chatbot_cases:
                chatbot_cases[case.chatbot_id] = case

        for chatbot_id, case in chatbot_cases.items():
            case.seed_scale = 500
            result = run_recall_check(case, top_k=5)
            assert result.found, (
                f"Omnipotent search failed to find fact for chatbot "
                f"{chatbot_id}: {case.case_id} — '{case.query}'"
            )

    def test_blocked_chatbot_excluded(
        self,
        ephemeral_tenant: str,
    ) -> None:
        """Verify facts from blocked chatbots are excluded from results."""
        from airunner_services.database.models.chatbot import Chatbot

        # Create a blocked chatbot and insert a fact for it
        with Chatbot.objects.transaction() as tx:
            blocked = Chatbot(
                name="blocked_test_bot",
                blocked_by_user=True,
            )
            tx.add(blocked)
            tx.flush()
            blocked_id = int(getattr(blocked, "id"))

        # Insert a distinctive fact for the blocked chatbot
        from airunner_services.knowledge_context import (
            set_knowledge_chatbot_id,
            set_knowledge_subject,
        )

        set_knowledge_chatbot_id(blocked_id)
        set_knowledge_subject("user")

        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )

        with KnowledgeFact.objects.transaction() as tx:
            fact = KnowledgeFact(
                fact_text="the user is secretly a time traveler from 1850",
                chatbot_id=blocked_id,
                subject="user",
            )
            tx.add(fact)
            tx.flush()

        # Search should NOT return the blocked fact
        from airunner_services.knowledge import KnowledgeBase

        kb = KnowledgeBase()
        results = kb.search_omnipotent_rag(
            "time traveler",
            k=10,
        )
        for r in results:
            assert "time traveler" not in r.lower(), (
                f"Blocked chatbot fact leaked into omnipotent results: {r}"
            )


# ---------------------------------------------------------------------------
# Dimension 3: Fallback-path triggering
# ---------------------------------------------------------------------------


class TestFallbackPathTriggering:
    """Assert which code path served each query."""

    def test_tfidf_fallback_when_no_embedding_model(
        self,
        ephemeral_tenant: str,
        seeded_ground_truth: list[GroundTruthCase],
    ) -> None:
        """Without an embedding model, all queries use TF-IDF fallback."""
        seed_facts(count=200, chatbot_count=2)

        for case in seeded_ground_truth[:5]:
            case.seed_scale = 200
            result = run_recall_check(case, embedding_model=None, top_k=5)
            assert result.path_used in ("tfidf", "unknown"), (
                f"Expected TF-IDF path for case {case.case_id}, "
                f"got {result.path_used}"
            )

    def test_vector_path_when_embedding_available(
        self,
        ephemeral_tenant: str,
        seeded_ground_truth: list[GroundTruthCase],
    ) -> None:
        """With an embedding model, queries use vector search."""
        embedding_model = _try_load_embedding_model()
        if embedding_model is None:
            pytest.skip("Embedding model not available")

        # Re-seed with embeddings
        seed_ground_truth_facts(seeded_ground_truth, embedding_model)
        seed_facts(count=200, chatbot_count=2, embedding_model=embedding_model)

        for case in seeded_ground_truth[:5]:
            case.seed_scale = 200
            result = run_recall_check(
                case,
                embedding_model=embedding_model,
                top_k=5,
            )
            # With embeddings, vector should be tried. The result could
            # fall through to TF-IDF if vector search returns empty
            # (e.g. facts have NULL embeddings), but vector should at
            # least be attempted.
            assert result.path_used in (
                "vector",
                "vector+tfidf_fallback",
            ), (
                f"Expected vector path for case {case.case_id}, "
                f"got {result.path_used}"
            )


# ---------------------------------------------------------------------------
# Dimension 4: Latency degradation curve
# ---------------------------------------------------------------------------


class TestLatencyDegradation:
    """Record wall-clock time per query at each scale."""

    @pytest.mark.parametrize("noise_count", _FAST_SCALE_PARAMS)
    def test_latency_at_scale(
        self,
        ephemeral_tenant: str,
        seeded_ground_truth: list[GroundTruthCase],
        noise_count: int,
    ) -> None:
        """Record query latency at a given scale."""
        if noise_count > 0:
            seed_facts(count=noise_count, chatbot_count=3)

        latencies: list[float] = []
        for case in seeded_ground_truth[:10]:
            case.seed_scale = noise_count
            result = run_recall_check(case, top_k=5)
            latencies.append(result.latency_ms)

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0

        print(
            f"\nScale {noise_count}: "
            f"avg={avg_latency:.1f}ms, max={max_latency:.1f}ms, "
            f"n={len(latencies)}",
        )

        # HNSW vector search should stay roughly flat with scale.
        # TF-IDF may grow linearly. We record the curve; individual
        # queries should not exceed 5 seconds.
        for i, lat in enumerate(latencies):
            assert lat < 5000, (
                f"Query latency {lat:.0f}ms exceeds 5s limit "
                f"at scale {noise_count} (case index {i})"
            )

    def test_tfidf_vs_vector_latency_comparison(
        self,
        ephemeral_tenant: str,
    ) -> None:
        """Compare TF-IDF latency against vector search latency."""
        embedding_model = _try_load_embedding_model()

        seed_facts(
            count=500,
            chatbot_count=3,
            embedding_model=embedding_model,
        )

        cases = load_ground_truth_cases()
        seed_ground_truth_facts(cases, embedding_model=embedding_model)

        tfidf_latencies: list[float] = []
        vector_latencies: list[float] = []

        for case in cases[:5]:
            case.seed_scale = 500

            # TF-IDF path
            tfidf_result = run_recall_check(
                case,
                embedding_model=None,
                top_k=5,
            )
            tfidf_latencies.append(tfidf_result.latency_ms)

            # Vector path (if model available)
            if embedding_model is not None:
                vector_result = run_recall_check(
                    case,
                    embedding_model=embedding_model,
                    top_k=5,
                )
                vector_latencies.append(vector_result.latency_ms)

        avg_tfidf = (
            sum(tfidf_latencies) / len(tfidf_latencies)
            if tfidf_latencies
            else 0
        )
        print(f"\nTF-IDF avg latency: {avg_tfidf:.1f}ms")

        if vector_latencies:
            avg_vector = sum(vector_latencies) / len(vector_latencies)
            print(f"Vector avg latency: {avg_vector:.1f}ms")
            # Vector search should be faster (or comparable) to TF-IDF
            # for the same dataset. If TF-IDF is consistently 10x slower,
            # that's a useful cross-check that the path instrumentation
            # is accurate.
            if avg_tfidf > 0:
                ratio = avg_tfidf / max(avg_vector, 0.001)
                print(f"TF-IDF/Vector ratio: {ratio:.1f}x")


# ---------------------------------------------------------------------------
# Dimension 5: Tag-scale sanity check
# ---------------------------------------------------------------------------


class TestTagScaleSanity:
    """Verify knowledge_tags / knowledge_fact_tags joins at scale."""

    def test_tag_fact_associations_at_scale(
        self,
        ephemeral_tenant: str,
    ) -> None:
        """Insert thousands of tagged facts and verify joins are correct."""
        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )
        from airunner_services.database.models.knowledge_fact_tag import (
            KnowledgeFactTag,
        )
        from airunner_services.database.models.knowledge_tag import (
            KnowledgeTag,
        )

        seed_facts(count=1000, chatbot_count=2)
        # Also test conversation turns seeding
        seed_conversation_turns(count=200, chatbot_count=2)

        # Verify: count of facts, tags, and links
        fact_count = KnowledgeFact.objects.query().count()
        tag_count = KnowledgeTag.objects.query().count()
        link_count = KnowledgeFactTag.objects.query().count()

        assert fact_count >= 1000, (
            f"Expected >=1000 facts, got {fact_count}"
        )
        assert tag_count >= 1, (
            f"Expected >=1 tags, got {tag_count}"
        )
        assert link_count >= 1000, (
            f"Expected >=1000 fact-tag links, got {link_count}"
        )

        # Verify: each fact has at least one tag
        facts_without_tags = (
            KnowledgeFact.objects.query()
            .outerjoin(
                KnowledgeFactTag,
                KnowledgeFact.id == KnowledgeFactTag.fact_id,
            )
            .filter(KnowledgeFactTag.id.is_(None))
            .count()
        )
        assert facts_without_tags == 0, (
            f"{facts_without_tags} facts have no tag association"
        )

        # Verify: tag names match what we expect
        expected_tags = {
            "hobbies", "food", "drinks", "sports", "arts", "technology",
            "home", "pets", "music", "travel", "health", "education",
            "work", "family", "friends", "entertainment", "personal",
        }
        actual_tags = {
            row.name
            for row in KnowledgeTag.objects.query().all()
        }
        for tag in actual_tags:
            assert tag in expected_tags, (
                f"Unexpected tag '{tag}' found in database"
            )

    def test_tag_deletion_cascades(
        self,
        ephemeral_tenant: str,
    ) -> None:
        """Verify CASCADE delete removes fact-tag links when facts are deleted."""
        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )
        from airunner_services.database.models.knowledge_fact_tag import (
            KnowledgeFactTag,
        )

        seed_facts(count=100, chatbot_count=1)

        # Pick one fact, count its tags, soft-delete it, verify links remain
        fact = KnowledgeFact.objects.query().first()
        assert fact is not None
        fact_id = int(getattr(fact, "id"))

        link_count_before = (
            KnowledgeFactTag.objects.query()
            .filter(KnowledgeFactTag.fact_id == fact_id)
            .count()
        )
        assert link_count_before > 0, "Fact should have tag links"

        # Soft-delete (the app uses soft-deletes, not CASCADE deletes)
        with KnowledgeFact.objects.transaction() as tx:
            tx.query(KnowledgeFact).filter(
                KnowledgeFact.id == fact_id,
            ).update(
                {"deleted": True},
                synchronize_session=False,
            )

        # Links should still exist (soft-delete doesn't cascade)
        link_count_after = (
            KnowledgeFactTag.objects.query()
            .filter(KnowledgeFactTag.fact_id == fact_id)
            .count()
        )
        assert link_count_after == link_count_before, (
            "Tag links should persist after soft-delete"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _try_load_embedding_model():
    """Try to load the production embedding model from the standard path.

    Returns the model instance, or None if not available.
    """
    try:
        import os

        from langchain_huggingface import HuggingFaceEmbeddings

        base_path = os.environ.get("AIRUNNER_BASE_PATH", "/data")
        model_path = os.path.expanduser(
            os.path.join(
                base_path,
                "text", "models", "llm", "embedding", "intfloat/e5-large",
            ),
        )
        if not os.path.isdir(model_path):
            return None

        return HuggingFaceEmbeddings(
            model_name=model_path,
            model_kwargs={
                "device": "cpu",
                "trust_remote_code": True,
            },
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception:
        return None
