# RAG (Retrieval-Augmented Generation)

AI Runner provides a RAG system for answering questions based on your own documents.

---

## Overview

RAG allows the LLM to retrieve relevant passages from ingested documents to generate more informed, accurate responses grounded in your data.

### Supported Document Formats

- **PDF** — Text extraction from PDF files
- **Markdown** — `.md` files
- **EPUB** — E-book format
- **Plain text** — `.txt` files

---

## How RAG Works

1. **Upload documents** via the Documents panel in the web UI
2. **Documents are indexed** — Text is extracted, chunked, and embedded for semantic search
3. **When chatting** — The LLM searches the index for relevant passages
4. **Context-enhanced responses** — Retrieved passages are included in the LLM's context

### Keyword-Based Retrieval

The system extracts keywords from queries and searches the index for matching content. Passages are ranked by relevance and the top results are provided to the LLM.

---

## Performance Optimizations

- **Caching** — Keyword extraction results are cached
- **Throttled indexing** — Index refreshes at intervals (5 minutes)
- **Batched processing** — Documents processed in efficient batches
- **Progress reporting** — Long operations show progress

---

## RAG vs Knowledge System

| Feature | RAG Search | Knowledge System |
|---------|-----------|------------------|
| **Purpose** | Document Q&A | Long-term memory |
| **Data Source** | Uploaded documents (PDF, EPUB, etc.) | Conversation-extracted facts |
| **Storage** | Vector index | Markdown files |
| **Updates** | Manual document upload | Automatic from chat |

---

## Using RAG

1. Navigate to the **Documents** tab
2. Upload your documents (drag-and-drop or file browser)
3. Switch the chat mode to **RAG**
4. Ask questions — the LLM will search your documents for relevant context

## Document Scanner (ZIM Files)

AI Runner can scan **ZIM files** (offline Wikipedia archives) for additional document sources:

```
server/src/airunner_services/documents/scan_zimfiles.py
```

ZIM files provide access to offline encyclopedia and reference content.
