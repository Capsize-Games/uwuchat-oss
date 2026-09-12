# Encryption Architecture

## What we can encrypt

The Fernet infrastructure already exists in the codebase. Currently `AgentMemory.summary`
is encrypted at rest. The following columns are straightforward to encrypt with the same
pattern because they are written once and read back as opaque blobs — no server-side
search is performed on their content:

| Column | Table | Status |
|---|---|---|
| `summary` | `agent_memories` | **Encrypted** (Fernet, done) |
| `value` | `conversations` | Ready to encrypt — large JSON blob, read whole |
| `summary` | `episodic_summaries` | Ready to encrypt |
| `body` | `knowledge_facts` | Ready to encrypt (tag/category columns can stay clear) |

For these columns, encryption is transparent: write path encrypts, read path decrypts,
no search is ever done on the ciphertext. User-controlled keys (derived from a passphrase
or a client-side secret) are possible in principle, but the current Fernet key lives on
the server, so the server can always decrypt. True E2E (server-blind) requires the client
to hold the key and send plaintext only for the current turn — a bigger architectural
change documented separately.

---

## What we CANNOT encrypt with full-search capability

### The RAG / knowledge search columns

The knowledge pipeline stores text chunks in `document_chunks` with a `pgvector` embedding
alongside the raw text content:

```
document_chunks
  chunk_text    TEXT       ← plaintext needed for embedding + LLM context injection
  embedding     vector     ← float array, always plaintext (pgvector requirement)
```

And the knowledge-fact search path uses `ILIKE` pattern matching (planned migration to
pgvector once `ConversationTurn.content` is encrypted):

```
knowledge_facts
  body          TEXT       ← searched with ILIKE / vector similarity
  tags          TEXT[]     ← searched with ANY() operator
```

**Why ``document_chunks`` cannot be encrypted without sacrificing search:**

Similarity search (`<->`, `<=>`, cosine distance operators) operates on the raw float
vector. pgvector has no concept of encrypted vectors — the numbers must be plaintext at
query time. ``document_chunks`` is deliberately left plaintext for this reason.

For ``knowledge_facts``, ``conversation_turns``, and ``email_body_chunks``, however,
the ``embedding_enc`` column stores CKKS homomorphically encrypted embeddings
(see :mod:`.fhe_helpers`, :mod:`.fhe_search`).  The server computes dot-product
similarity directly on ciphertext via TenSEAL (Microsoft SEAL), ranking candidates
without ever decrypting the stored vectors.  This is the homomorphic-encryption
path — it runs at practical speed for up to ``FHE_CANDIDATE_CAP`` (100) candidates
per query.

| Table | Column | Mechanism |
|---|---|---|
| ``knowledge_facts`` | ``embedding_enc`` | CKKS ciphertext (TenSEAL) |
| ``conversation_turns`` | ``embedding_enc`` | CKKS ciphertext (TenSEAL) |
| ``email_body_chunks`` | ``embedding_enc`` | CKKS ciphertext (TenSEAL) |
| ``document_chunks`` | ``embedding`` | Plaintext (pgvector requirement) |

Full-text / ILIKE search on `body` has the same constraint: the DB engine must see
plaintext to match patterns.

The only ways to search encrypted content are:
1. **Deterministic encryption** (same plaintext → same ciphertext) — allows equality
   checks but not similarity or ILIKE. Breaks semantic search entirely.
2. **Client-side search** — decrypt all records to the client, search in JS/WASM. Works
   only for small corpora; not viable for large knowledge bases.
3. **Trusted-enclave search** (e.g., AWS Nitro Enclaves) — requires infrastructure we
   do not have.

---

## The tradeoff we must communicate to users

| Feature | Fully encrypted? | Notes |
|---|---|---|
| Conversation messages | Yes (can be) | Fernet on `conversations.value` |
| Agent memory summaries | Yes (already) | Fernet on `agent_memories.summary` |
| Episodic summaries | Yes (can be) | Same pattern |
| Knowledge facts body | **No** | Needed for RAG recall |
| Document chunk text | **No** | Needed for embedding generation |
| Knowledge facts embedding | **Yes** | CKKS ciphertext (TenSEAL FHE) |
| Conversation turns embedding | **Yes** | CKKS ciphertext (TenSEAL FHE) |
| Email body chunks embedding | **Yes** | CKKS ciphertext (TenSEAL FHE) |
| pgvector embeddings | **No** | pgvector is always plaintext (document_chunks only) |

Users who want the **highest possible privacy** must understand: enabling the knowledge /
RAG features means their conversation-derived facts and uploaded document text live in
plaintext in the database (inside their tenant schema, but not encrypted beyond OS-level
disk encryption).

### The user choice we should expose

Offer a **Knowledge & RAG** toggle in UwU Preferences:

```
[ ] Enable knowledge base & memory recall
    "Lets your UwU remember facts about you across conversations.
     Requires storing some content in a searchable (unencrypted) form.
     Turn this off for maximum privacy — your UwU will still remember
     things within a session."
```

When disabled:
- `knowledge_tools/recall.py` returns empty results immediately
- `knowledge_crud.py` skips the write path
- `document_chunks` table stays empty
- `knowledge_facts` table stays empty
- Conversation `value` + summaries are still encrypted (or can be)

When enabled:
- Full RAG pipeline runs as today
- Users are informed that fact/document text is searchable plaintext

This is a per-chatbot or per-account preference stored in `users.settings` JSONB.

---

## Phased rollout plan

### Phase 1 — Encrypt what we can (no RAG impact)
- Encrypt `conversations.value` with the existing Fernet key (server-held)
- Encrypt `episodic_summaries.summary`
- Add migration — encryption happens on next write, old rows get a lazy backfill job
- **Delivers**: all message content protected at rest against DB leaks

### Phase 2 — User-facing RAG toggle
- Add `rag_enabled` boolean to user settings (default: `true`)
- Wire `knowledge_crud.py` and `recall.py` to respect it
- Add the toggle to UwU Preferences UI
- **Delivers**: users who want maximum privacy can opt out

### Phase 3 — True E2E (future, complex)
- Key lives in client (derived from password or passphrase, never sent to server)
- Server stores only ciphertext for `conversations.value`
- RAG is unavailable when E2E is enabled (there is no other option)
- Requires: client-side PBKDF2/Argon2, encrypted payload wrapped per-turn,
  server is completely blind to message content
- **Blocker**: session resumption across devices requires key sync (iCloud Keychain /
  hardware security key); out of scope until user demand justifies complexity

---

## Current status

| Item | Done? |
|---|---|
| Fernet infrastructure | Yes |
| `AgentMemory.summary` encrypted | Yes |
| `ConversationTurn.content` encrypted | Yes (per-user DEK, via ``UserEncryptedText``) |
| `ConversationTurn.embedding_enc` (FHE) | Yes (CKKS ciphertext via TenSEAL — see Part 1 backfill note below) |
| `conversations.value` encrypted | Yes (per-user DEK, via ``UserEncryptedText``) |
| `KnowledgeFact.fact_text` encrypted | Yes (per-user DEK, via ``UserEncryptedText``) |
| `KnowledgeFact.embedding_enc` (FHE) | Yes (CKKS ciphertext via TenSEAL) |
| `EmailMessage.from_address/from_name/to/cc/subject` encrypted | Yes (per-user DEK, via ``UserEncryptedText``) |
| `EmailBodyChunk.embedding_enc` (FHE) | Yes (CKKS ciphertext via TenSEAL) |
| `Entity.display_name_ct/aliases_ct` encrypted | Yes (per-user DEK, via ``UserEncryptedText``) |
| `Entity.embedding` (FHE) | Not yet — still plaintext pgvector, scheduled for migration |
| `llm_generator_settings.api_key` encrypted | Not yet — plaintext String, scheduled for migration |
| `application_settings.{hf,civit,openai}_api_key` encrypted | Not yet — plaintext String, scheduled for migration |
| RAG toggle UI | Not yet |
| User-facing privacy disclosure for RAG | Not yet |

### FHE embedding backfill note

As of 2026-07-30, the ``embedding_enc`` columns on ``KnowledgeFact``,
``ConversationTurn``, and ``EmailBodyChunk`` have the correct schema
and write-path encryption logic, but **existing rows from before the
FHE infrastructure was deployed have NULL ``embedding_enc`` values**.
A login-triggered backfill (mirroring the email indexing recovery
pattern) ensures these rows catch up automatically on next login.
See ``server/src/airunner_services/embedding_backfill.py`` for the
cursor-based batch functions.
