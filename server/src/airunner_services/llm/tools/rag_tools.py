"""
RAG and document search tools.

Tools for searching loaded documents (RAG), finding documents in knowledge base,
and saving new content to the knowledge base.
"""

import os
from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import tool, ToolCategory
from airunner_services.database.models.document import Document
from airunner_services.database.models.path_settings import PathSettings
from airunner_services.contract_enums import SignalCode
from airunner_services.knowledge_context import get_knowledge_chatbot_id
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger
from airunner_services.utils.application.log_hygiene import summarize_text
from airunner_services.llm.tools.rag_tools_helpers._shared import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
)

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_NO_DOCS_FOUND_MSG = (
    "No documents found in knowledge base. "
    "⚠️ Try search_web() to search the internet instead, "
    "then use record_knowledge() to save any useful facts."
)


# LAUNCH DISABLED: rag_search is not registered at soft launch.
# Retrieve tools cause DeepSeek 400 errors on tool-continuation turns because
# their ToolMessage results cannot be stripped (unlike write-only tools).
# Re-enable once the two-phase tool architecture is implemented.
# See wiki/planned_work/two-phase-tool-architecture.md
# @tool(
#     name="rag_search",
#     category=ToolCategory.RAG,
#     description=(...),
#     requires_api=True,
#     keywords=["document", "search", "knowledge", "memory", "loaded"],
# )
def rag_search(
    query: Annotated[
        str, "Search query for finding relevant document content"
    ],
    api: Any = None,  # Injected by ToolManager
) -> str:
    """Search through LOADED documents in memory for relevant information.

    IMPORTANT: This only works if documents have been loaded into memory first.
    Documents must be actively loaded before searching them.

    If this tool fails because documents aren't loaded, inform the user
    that the requested documents need to be loaded first.

    Args:
        query: Search query for finding relevant document content
        api: API instance (injected by ToolManager)

    """
    logger.info(
        "rag_search called (%s)",
        summarize_text(query, label="query"),
    )

    # For RAG tools, api IS the rag_manager (LLMModelManager with RAG search methods)
    rag_manager = api

    logger.debug(
        "rag_manager available=%s has_search=%s",
        rag_manager is not None,
        hasattr(rag_manager, "search") if rag_manager else False,
    )

    if not rag_manager:
        error_msg = (
            "TOOL UNAVAILABLE: No RAG manager available. "
            "This is an internal error - RAG tools should receive the LLM model manager."
        )
        logger.warning(error_msg)
        return error_msg

    # Check if documents are loaded by calling the RAG manager's search method
    try:
        results = rag_manager.search(query, k=3)
        logger.info(
            f"rag_manager.search returned "
            f"{len(results) if results else 0} results"
        )

        if not results:
            msg = (
                f"No relevant information found for '{query}' in loaded "
                f"documents. The document may not contain information about this topic, "
                f"or the search query may need to be rephrased."
            )
            logger.info(msg)
            return msg

        context_parts = []
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get("source", "unknown")
            content = (
                doc.page_content[:500]
                if len(doc.page_content) > 500
                else doc.page_content
            )
            context_parts.append(f"[Source {i}: {source}]\n{content}")
            logger.debug(
                f"Result {i} from source: {source}, "
                f"length: {len(doc.page_content)}"
            )

        result_text = "\n\n".join(context_parts)
        logger.info(
            f"Returning {len(context_parts)} document excerpts, "
            f"total length: {len(result_text)}"
        )
        return result_text
    except Exception as e:
        error_msg = f"Error searching documents: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return error_msg


@tool(
    name="search_knowledge_base_documents",
    category=ToolCategory.SEARCH,
    description=(
        "Search across ALL knowledge base documents to find the most relevant "
        "ones. This is a broad search across document titles and paths - like "
        "a search engine for your entire knowledge base. Use this BEFORE "
        "rag_search to determine which documents should be loaded. If documents "
        "aren't indexed, this tool will automatically discover and index them."
    ),
    return_direct=False,
    requires_api=True,
)
def search_knowledge_base_documents(
    query: Annotated[
        str,
        "What topics/documents you're looking for (e.g., 'Python programming books')",
    ],
    k: Annotated[int, "Number of document paths to return"] = 10,
    api: Any = None,
) -> str:
    """Search across ALL knowledge base documents to find relevant ones.

    This is a BROAD SEARCH across document titles and paths - like a search
    engine for your entire knowledge base. Use this BEFORE using rag_search
    to determine which documents should be loaded into RAG for detailed
    querying.

    The knowledge base may contain ebooks, PDFs, markdown files, ZIM files,
    and more. This tool helps you discover which documents are relevant to
    the user's question so you can load them for deeper analysis.

    Args:
        query: What topics/documents you're looking for
        k: Number of document paths to return (default 10)


    Examples:
        search_knowledge_base_documents("machine learning tutorials")
        search_knowledge_base_documents("health and fitness guides", k=5)
        search_knowledge_base_documents("cooking recipes")
    """
    try:
        docs = Document.objects.query().filter_by(active=True).all()
        if not docs and api:
            docs = _discover_documents_from_disk(api)
        if not docs:
            return _NO_DOCS_FOUND_MSG
        top_docs = _score_docs_by_keywords(query, docs, k)
        if not top_docs:
            top_docs = _retry_scoring_after_indexing(query, docs, api, k)
        if not top_docs:
            return (
                f"No documents found matching '{query}' in the "
                f"knowledge base. ⚠️ Try search_web('{query}') to "
                f"search the internet instead, then use "
                f"record_knowledge() to save any useful facts you find."
            )
        idx_count, just_indexed = _index_top_unindexed(top_docs, api)
        return _format_kb_results(query, top_docs, idx_count, just_indexed)
    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        return f"Error searching knowledge base: {str(e)}"


# ------------------------------------------------------------------ helpers


def _get_candidate_kb_dirs(api) -> list[str]:
    """Get candidate directories for KB document discovery from PathSettings."""
    settings = api.path_settings or PathSettings.objects.first()
    logger.info(f"PathSettings: {settings}")
    if not settings:
        return []
    dirs = [
        settings.documents_path,
        settings.ebook_path,
        settings.webpages_path,
        os.path.join(settings.base_path, "knowledge_base"),
    ]
    logger.info(f"Candidate dirs for KB discovery: {dirs}")
    return dirs


def _find_document_files(directories: list[str]) -> list[str]:
    """Walk directories and find document files with supported extensions."""
    found_files: list[str] = []
    for d in directories:
        if not d:
            logger.debug("Skipping empty candidate dir")
            continue
        d = os.path.expanduser(d)
        if not os.path.exists(d):
            logger.info(f"KB discovery dir not found: {d}")
            continue
        logger.info(f"Scanning KB dir for documents: {d}")
        file_count = 0
        for root, _, files in os.walk(d):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in SUPPORTED_DOCUMENT_EXTENSIONS:
                    file_count += 1
                    found_files.append(os.path.join(root, fname))
        logger.info(f"Found {file_count} files in {d}")
    return found_files


def _ensure_document_record(file_path: str, api) -> None:
    """Create a Document DB entry if one doesn't already exist."""
    exists = Document.objects.filter_by(path=file_path)
    if exists and len(exists) > 0:
        logger.debug(f"Document already exists: {file_path}")
        return
    logger.info(f"Creating Document record for: {file_path}")
    Document.objects.create(
        path=file_path,
        active=True,
        indexed=False,
        chatbot_id=get_knowledge_chatbot_id(),
    )
    if hasattr(api, "emit_signal"):
        api.emit_signal(
            SignalCode.DOCUMENT_COLLECTION_CHANGED,
            {"path": file_path, "action": "discovered"},
        )


def _discover_standard_dirs(api) -> tuple[list, list[str]]:
    """Discover docs from PathSettings dirs. Returns (docs, found_files)."""
    found_files: list[str] = []
    try:
        found_files = _find_document_files(_get_candidate_kb_dirs(api))
        for fpath in found_files:
            _ensure_document_record(fpath, api)
    except Exception as e:
        logger.error(f"Disk discovery failed: {e}", exc_info=True)
    docs = Document.objects.query().filter_by(active=True).all()
    logger.info(
        f"After discovery, DB now has {len(docs)} active document records"
    )
    return docs, found_files


def _find_repo_root() -> str | None:
    """Walk up from __file__ to locate the repo root containing 'booksite/'."""
    candidate = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
    )
    while True:
        if os.path.exists(os.path.join(candidate, "booksite")):
            return candidate
        parent = os.path.abspath(os.path.join(candidate, os.pardir))
        if parent == candidate:
            return None
        candidate = parent


def _get_repo_fallback_dirs(repo_root: str) -> list[str]:
    """Return known document directories under booksite/ in the repo."""
    return [
        os.path.join(repo_root, "booksite", "text", "other", "documents"),
        os.path.join(repo_root, "booksite", "text", "other", "ebooks"),
        os.path.join(repo_root, "booksite", "text", "other", "webpages"),
    ]


def _discover_repo_fallback(api) -> list:
    """Fallback discovery: walk up to repo root, scan booksite/ for docs."""
    found_files: list[str] = []
    try:
        repo_root = _find_repo_root()
        if repo_root:
            logger.debug(f"Repo fallback candidate root: {repo_root}")
            found_files = _find_document_files(
                _get_repo_fallback_dirs(repo_root)
            )
            for fpath in found_files:
                _ensure_document_record(fpath, api)
    except Exception as e:
        logger.warning(f"Fallback repo discovery failed: {e}")
    if found_files:
        return Document.objects.query().filter_by(active=True).all()
    return []


def _discover_documents_from_disk(api) -> list:
    """Discover documents on disk, create DB records, return active docs."""
    logger.info(
        f"No docs in DB, attempting discovery. api={type(api).__name__}"
    )
    docs, found_files = _discover_standard_dirs(api)
    if len(docs) == 0 and not found_files:
        docs = _discover_repo_fallback(api)
    return docs


def _score_docs_by_keywords(
    query: str, docs: list, k: int
) -> list[tuple[int, object]]:
    """Score documents by keyword matches in filename and path."""
    query_terms = query.lower().split()
    scored_docs: list[tuple[int, object]] = []
    for doc in docs:
        path_lower = doc.path.lower()
        filename = os.path.basename(path_lower)
        score = 0
        for term in query_terms:
            if term in filename:
                score += 10
            elif term in path_lower:
                score += 5
        if score > 0:
            scored_docs.append((score, doc))
    scored_docs.sort(reverse=True, key=lambda x: x[0])
    return scored_docs[:k]


def _retry_scoring_after_indexing(
    query: str, docs: list, api, k: int
) -> list[tuple[int, object]]:
    """Index unindexed docs and retry keyword scoring when no matches found."""
    if not api:
        return []
    rag_manager = getattr(api, "rag_manager", None)
    if not rag_manager or not hasattr(rag_manager, "ensure_indexed_files"):
        return []
    unindexed = [d.path for d in docs if not d.indexed]
    if not unindexed:
        return []
    logger.info(
        f"No filepath matches for query '{query}'. "
        f"Attempting to index {len(unindexed)} documents and retry."
    )
    try:
        if rag_manager.ensure_indexed_files(unindexed):
            docs = Document.objects.query().filter_by(active=True).all()
            return _score_docs_by_keywords(query, docs, k)
    except Exception as e:
        logger.warning(f"On-demand indexing and retry failed: {e}")
    return []


def _index_top_unindexed(
    top_docs: list[tuple[int, object]], api
) -> tuple[int, set[str]]:
    """Index unindexed docs among top results. Returns (count, paths_set)."""
    to_index = [doc.path for _, doc in top_docs if not doc.indexed]
    if not to_index or not api:
        return 0, set()
    logger.debug(f"Attempting to on-demand index {len(to_index)} files")
    rag_manager = getattr(api, "rag_manager", None)
    if not rag_manager or not hasattr(rag_manager, "ensure_indexed_files"):
        return 0, set()
    try:
        if rag_manager.ensure_indexed_files(to_index):
            return len(to_index), set(to_index)
    except Exception as e:
        logger.warning(f"Failed to index files on demand: {e}")
    return 0, set()


def _format_doc_entry(
    index: int, doc, just_indexed: set[str]
) -> list[str]:
    """Return formatted lines for one document entry."""
    filename = os.path.basename(doc.path)
    status = (
        "indexed"
        if doc.indexed or doc.path in just_indexed
        else "not indexed"
    )
    return [f"{index}. {filename} ({status})", f"   Path: {doc.path}"]


def _format_kb_results(
    query: str,
    top_docs: list[tuple[int, object]],
    indexed_now_count: int,
    just_indexed: set[str],
) -> str:
    """Format knowledge base search results into a human-readable string."""
    parts: list[str] = []
    if indexed_now_count > 0:
        parts.append(
            f"Automatically indexed {indexed_now_count} document(s) "
            f"and refreshed the KB.\n"
        )
    parts.append(
        f"Found {len(top_docs)} relevant document(s) for '{query}':\n"
    )
    for i, (_, doc) in enumerate(top_docs, 1):
        parts.extend(_format_doc_entry(i, doc, just_indexed))
    parts.append(
        "\nTip: Use these document paths with rag_search to get "
        "detailed content."
    )
    return "\n".join(parts)


@tool(
    name="save_to_knowledge_base",
    category=ToolCategory.RAG,
    description=(
        "Save content to the knowledge base for future RAG retrieval. "
        "This allows the agent to build its own knowledge base over time "
        "by saving important information for later reference."
    ),
    return_direct=False,
    requires_api=True,
)
def save_to_knowledge_base(
    content: Annotated[str, "Text content to save"],
    title: Annotated[str, "Title/identifier for this knowledge"],
    category: Annotated[
        str, "Category for organization (e.g., 'research', 'documentation')"
    ] = "general",
    api: Any = None,
) -> str:
    """Save content to the knowledge base for future RAG retrieval.

    This tool allows the agent to build its own knowledge base over time
    by saving important information for later reference.

    Args:
        content: Text content to save
        title: Title/identifier for this knowledge
        category: Category for organization
        api: API instance (injected)

    """
    try:
        # Create a document file
        settings = PathSettings.objects.first()
        base_path = os.path.expanduser(settings.base_path)
        kb_path = os.path.join(base_path, "knowledge_base", category)
        os.makedirs(kb_path, exist_ok=True)

        # Sanitize filename
        filename = "".join(
            c for c in title if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        filename = filename.replace(" ", "_") + ".txt"

        file_path = os.path.join(kb_path, filename)

        # Write content
        with open(file_path, "w") as f:
            f.write(f"Title: {title}\n")
            f.write(f"Category: {category}\n")
            f.write("\n---\n\n")
            f.write(content)

        # Emit signal to reload RAG if API available
        if api and hasattr(api, "emit_signal"):
            api.emit_signal(
                SignalCode.RAG_DOCUMENT_ADDED,
                {"file_path": file_path, "title": title},
            )

        return f"Content saved to knowledge base: {title}"
    except Exception as e:
        return f"Error saving to knowledge base: {str(e)}"
