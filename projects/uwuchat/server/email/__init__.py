"""Email ingest — Fastmail/JMAP integration for UwUchat.

Subpackages:
  provider.py       — EmailProvider ABC
  fastmail.py       — FastmailJMAPProvider (Phase 1)
  routes.py         — Account linking / unlinking API (Phase 0)
  _route_helpers.py — Shared validation + cascade-delete helpers
  sync_engine.py    — Signal handler; enqueues the Celery sync task
  sync_delta.py     — JMAP Email/changes delta sync (Phase 1)
  sync_pipeline.py  — Phases 2–4 processing after metadata persist
  sync_progress_events.py — emit_progress/emit_complete entry points
  sync_progress_store.py  — Redis-backed cross-process progress store
  preprocessor.py   — Quote stripping, automated classification (Phase 2)
  contacts.py       — Contact extraction + response-time heuristics (Phase 2)
  summarizer.py     — Level-1 LLM thread summarization (Phase 3)
  extractor.py      — Level-2 LLM fact extraction (Phase 4)
"""
