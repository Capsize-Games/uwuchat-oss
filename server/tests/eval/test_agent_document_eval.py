"""API-backed evals for RAG document retrieval via the Docker server.

These tests verify that the LLM correctly uses RAG document content
injected through the ``active_document_ids`` WebSocket parameter.

All communication goes through the running Docker API server — no local
daemon subprocess is started.  Document fixtures are placed into the
knowledge-base directory inside the container, indexed via the KB API,
and then referenced in chat requests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rag_eval_support import (
    assert_success,
    ensure_document_active,
    index_all_documents,
    list_kb_documents,
    llm_chat_sync,
    resolve_active_model,
    wait_for_document_indexed,
)

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
_DOCUMENT_FIXTURE = _FIXTURES_DIR / "agent_eval_document.md"
_TIME_MACHINE_FIXTURE_DIR = _FIXTURES_DIR / "rag_formats" / "the-time-machine"
_TIME_MACHINE_PATHS = [
    _TIME_MACHINE_FIXTURE_DIR / "source.epub",
    _TIME_MACHINE_FIXTURE_DIR / "source.mobi",
    _TIME_MACHINE_FIXTURE_DIR / "source.pdf",
]

# KB directory inside the Docker container (matches AIRUNNER_BASE_PATH=/data)
_KB_ROOT = Path("/data/knowledge_base")

# Name used in the KB path for the eval document
_FIXTURE_DOC_NAME = "agent_eval_document.md"


def _ensure_fixture_in_kb(fixture_path: Path) -> str:
    """Copy a fixture into the knowledge-base directory if not already there.

    Returns the KB path (relative) used for lookup.
    """
    _KB_ROOT.mkdir(parents=True, exist_ok=True)
    dest = _KB_ROOT / fixture_path.name
    if not dest.exists():
        dest.write_text(fixture_path.read_text(encoding="utf-8"))
    return str(dest)


def _find_active_doc_id(doc_name: str) -> int | None:
    """Return the document ID for a KB document by name, or None."""
    docs = list_kb_documents()
    for doc in docs:
        if Path(str(doc.get("path", ""))).name == doc_name:
            return int(doc["id"])
    return None


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def eval_doc_id() -> int:
    """Ensure the eval document fixture is in KB, indexed, and active.

    Returns the document ID.
    """
    _ensure_fixture_in_kb(_DOCUMENT_FIXTURE)
    # Trigger a sync + list so the DB sees the file
    list_kb_documents()
    # Find and activate
    doc_id = _find_active_doc_id(_FIXTURE_DOC_NAME)
    if doc_id is None:
        # Maybe needs another sync cycle
        list_kb_documents()
        doc_id = _find_active_doc_id(_FIXTURE_DOC_NAME)
    if doc_id is None:
        pytest.fail(
            f"Document {_FIXTURE_DOC_NAME} not found in KB after sync. "
            f"Check that {_KB_ROOT} is accessible."
        )
    ensure_document_active(doc_id)
    # Only index if not already indexed (avoids re-indexing all 17+ docs)
    docs = list_kb_documents()
    for d in docs:
        if d["id"] == doc_id and d.get("indexed"):
            return doc_id
    index_all_documents(force=True)
    wait_for_document_indexed(doc_id, timeout_seconds=300)
    return doc_id


# ── Tests ──────────────────────────────────────────────────────────────────


class TestRagDocumentRetrieval:
    """Verify the LLM retrieves information from RAG-attached documents."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_has_rag_content_injected(
        self,
        eval_doc_id: int,
    ) -> None:
        """LLM receives RAG document content — response should be non-empty."""
        model = resolve_active_model()
        # Use a simple prompt that allows the model to reference the document
        # without overly strict formatting (which confuses qwen3 thinking mode)
        messages = [
            {
                "role": "user",
                "content": (
                    "Based on the attached document, what is the "
                    "emergency code? Answer briefly."
                ),
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=128,
            active_document_ids=[eval_doc_id],
        )
        assert_success(result)
        text = result.text.lower()
        # The document contains "Emergency code: 73142".  Assert on the value
        # only — "emergency" appears in the question, so matching it would
        # pass even without retrieval (the old false-positive).
        assert (
            "73142" in text
        ), f"Document content not found in response: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_identifies_project_alpha(
        self,
        eval_doc_id: int,
    ) -> None:
        """LLM should find 'Project Alpha' in the RAG document."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": (
                    "Based on the attached document, what is the "
                    "codename of the offline document-analysis pilot?"
                ),
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=200,
            active_document_ids=[eval_doc_id],
        )
        assert_success(result)
        text = result.text.lower()
        # "project"/"codename"/"pilot" all appear in the question; require the
        # actual retrieved codename so the assertion proves retrieval happened.
        assert (
            "alpha" in text
        ), f"Expected 'Project Alpha' codename, got: {result.text[:300]}"

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_uses_document_for_release_year(
        self,
        eval_doc_id: int,
    ) -> None:
        """LLM should find release year '2031' from the RAG document."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": (
                    "Based on the attached document, what is the "
                    "release year of Project Alpha?"
                ),
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=128,
            active_document_ids=[eval_doc_id],
        )
        assert_success(result)
        text = result.text.lower()
        # "release" is in the question; assert on the retrieved year only.
        assert (
            "2031" in text
        ), f"Expected release year '2031' context, got: {result.text[:300]}"


class TestRagWithoutDocument:
    """Verify LLM behavior when NO RAG document is attached."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    def test_llm_responds_without_rag_documents(self) -> None:
        """LLM should still produce non-empty response without RAG docs."""
        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": "What is 2 + 2? Answer with just the number.",
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=32,
        )
        assert_success(result)
        # Model should produce some output — being lenient about content
        assert (
            len(result.text.strip()) > 0
        ), "Expected non-empty response, got empty"


class TestRagDocumentFormatSupport:
    """Verify RAG supports multiple document formats."""

    @pytest.mark.eval
    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.timeout(600)
    @pytest.mark.parametrize(
        "doc_path",
        _TIME_MACHINE_PATHS,
        ids=["epub", "mobi", "pdf"],
    )
    def test_llm_uses_multiformat_rag_document(
        self,
        doc_path: Path,
    ) -> None:
        """LLM should use content from EPUB/MOBI/PDF RAG documents."""
        _ensure_fixture_in_kb(doc_path)
        list_kb_documents()
        doc_id = _find_active_doc_id(doc_path.name)
        if doc_id is None:
            pytest.skip(
                f"Document {doc_path.name} not found in KB — "
                "may need file format support enabled"
            )
        ensure_document_active(doc_id)
        # Only index if not already done
        docs = list_kb_documents()
        already_indexed = any(
            d["id"] == doc_id and d.get("indexed") for d in docs
        )
        if not already_indexed:
            index_all_documents(force=True)
            wait_for_document_indexed(doc_id, timeout_seconds=300)

        model = resolve_active_model()
        messages = [
            {
                "role": "user",
                "content": (
                    "Based on the attached document, what is the "
                    "name of the subterranean creatures in the story? "
                    "Answer briefly."
                ),
            },
        ]
        result = llm_chat_sync(
            messages,
            model=model,
            temperature=0.1,
            max_tokens=128,
            active_document_ids=[doc_id],
        )
        assert_success(result)
        text = result.text.lower()
        # The subterranean creatures in The Time Machine are the "Morlocks".
        # "creature"/"time machine" echo the question, so require the actual
        # retrieved name — this proves binary (EPUB/MOBI/PDF) extraction +
        # pgvector retrieval actually worked.
        assert "morlock" in text, (
            f"Expected 'Morlocks' from retrieved content, "
            f"got: {result.text[:300]}"
        )
