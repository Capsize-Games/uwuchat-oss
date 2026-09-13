# AIRunner — Codebase Guide for AI Agents

## Repository layout

```
airunner/
  client/src/              ← AIRunner framework (React)
  server/                  ← AIRunner server (Python / FastAPI)
  projects/uwuchat/        ← UwUchat — the first project built on AIRunner
    server/                ← Server-side project overrides (Python)
    client/                ← Client-side project overrides (React)
  extensions/              ← Optional feature extensions loaded at runtime
  scripts/                 ← Dev and CI scripts
```

---

## Wiki

The `wiki/` directory contains living documentation on non-obvious subsystems
(LLM integrations, multi-tenant architecture, extension patterns, and more).
Before starting any task, do a quick scan of `wiki/` for a file relevant to
the area you are about to touch. Reading the relevant doc first often prevents
mistakes that would otherwise require multiple correction cycles.

---

## Framework / Project Separation — read this before touching any file

AIRunner is a **framework** for building AI-backed websites, analogous to Django.
UwUchat (`uwuchat.com`) is a **project** built on that framework.

The two must be kept separate. Violating this is the most common mistake to avoid.

### The rule

| Type of change | Where it goes |
|---|---|
| Applies to any site built on AIRunner | `client/src/` or `server/src/airunner_services/` |
| Specific to UwUchat | `projects/uwuchat/client/` or `projects/uwuchat/server/` |

If you are unsure, ask: *would a hypothetical second site built on AIRunner want
this behavior?* If yes → framework. If no → project.

### How the overlay works (client)

`client/vite-plugin-project.ts` implements a transparent file overlay at build
time. When `VITE_PROJECT=uwuchat`, any file in `projects/uwuchat/client/` silently
replaces its framework counterpart in `client/src/` with the same relative path.

Examples:
- `client/src/components/chat/ChatView.tsx` (framework) is replaced by
  `projects/uwuchat/client/components/chat/ChatView.tsx` (project override)
- `client/src/hooks/useLayoutPrefs.ts` (framework) is replaced by
  `projects/uwuchat/client/hooks/useLayoutPrefs.ts` (project override)

Framework files that have no project counterpart are used as-is.
**Never edit a framework file to add UwUChat-specific behavior.** Create or
edit the project override instead.

### Import conventions in project files

```ts
// Framework module with NO project override → use @/ alias (resolves to src/)
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { EdgeOnly } from "@/context/DeploymentContext";

// Framework module WITH a project override, or another project file → relative
// (resolves to the project version because the file exists in the project dir)
import { useChatInference } from "../../hooks/useChatInference";
import { useUwuThread } from "../../hooks/useUwuThread";
```

Never use `@/` in a project file for a module that has a project override —
the relative import picks up the project version. `@/` always resolves to
the framework copy.

### Adding a new override

1. Copy the framework file to the matching path under `projects/uwuchat/client/`.
2. Modify the copy. Do not touch the original.
3. Update imports in the copy: framework-only deps → `@/`, project deps → relative.

### Adding a new UwUChat-only file (no framework counterpart)

Create it under `projects/uwuchat/client/`. Other project files import it with
relative paths. If a framework file needs to import it (unusual), add a
framework stub that the project overrides.

### Common mistakes

- **Do not edit `client/src/components/...` to add UwUChat behavior.** Edit the
  project override at `projects/uwuchat/client/components/...` instead.
- **Do not remove framework features** from framework files. UwUChat hides them
  via its overrides; the framework must stay complete.
- **Do not use relative imports for framework-only deps in project files.** The
  relative path resolves to a non-existent location inside the project directory
  and breaks TypeScript. Use `@/` instead.
- **Do not add `VITE_PROJECT` checks inside framework code.** Use the override
  system instead.

---

## Building

| Command | Result |
|---|---|
| `npm run dev` (no env) | AIRunner framework build |
| `VITE_PROJECT=uwuchat npm run dev` | UwUchat build |

The Docker setup passes `VITE_PROJECT=uwuchat` automatically for the UwUchat
deploy.

---

## What UwUchat changes vs the framework

UwUchat is an AIM-style persistent chat experience, not a productivity tool.
Key differences from the generic AIRunner UI:

- **Chatbot-centric** (not conversation-centric): the sidebar shows UwUs
  (chatbots), not a conversation list. The concept of "conversations" as a
  user-visible object is hidden.
- **No new-conversation button, no message edit/delete**: append-only.
- **Session model**: the backend auto-creates sessions on a 4-hour gap; the UI
  renders all sessions as one continuous thread with subtle time-gap dividers.
- **Stripped settings**: many AIRunner settings panels are hidden or replaced
  with UwUChat-specific ones (e.g. "UwU Preferences" instead of agent settings).
- **UwU Creator**: a character-generation modal unique to UwUchat.

The full design spec is in `uwuchat-conversation-architecture.md`.

---

## LLM Provider — UwUchat

UwUchat is a **cloud-only** deployment. It does **not** use local/edge models.

All routing is in `projects/uwuchat/server/ai_pipeline.py` (`PIPELINE_CONFIG`).
Edit that file to change models without touching framework code.
**`projects/uwuchat/server/llm_routing.py` is dead legacy code** — its
`MODEL_ROUTING` dict is only consulted by `pipeline_loader.py` if
`ai_pipeline.py` fails to import, which it never does. Do not read it as a
source of truth; it currently holds stale `meta-llama/llama-3.1-8b-instruct`
entries that are not what actually runs.

| Task | Provider | Model |
|---|---|---|
| `DIALOGUE` (all complexity tiers) | OpenRouter | `deepseek/deepseek-v4-flash-0731` (pinned to the native `deepseek` provider, see experiment note below) |
| `KNOWLEDGE` (fact extraction) | OpenRouter | `deepseek/deepseek-v4-flash-0731` |
| `STATELESS` (in-character narration: DMs, room posts, catch-ups) | OpenRouter | `deepseek/deepseek-v4-flash-0731` |
| `TOOL_CLASSIFICATION` | OpenRouter | `deepseek/deepseek-v4-flash-0731` |
| `TOOL_EXECUTION` (cheap-model tool-running stage) | OpenRouter | `deepseek/deepseek-v4-flash-0731` |
| `SUMMARIZATION` | OpenRouter | `deepseek/deepseek-v4-flash-0731` (disabled by default) |
| Background tasks (`INTRA_SESSION_MOOD`, `ROLLING_COMPRESSOR`, `EPISODIC_SUMMARIZER`, `MEMORY_UPDATER`, `NODE_VALIDATOR`, `CURIOSITY_ENGINE`, `JOURNAL_SUMMARIZER`) | OpenRouter | `deepseek/deepseek-v4-flash-0731` |
| `EMBEDDING` | OpenRouter (pinned to DeepInfra) | `qwen/qwen3-embedding-8b` |

> **Experiment (2026-07-27):** All text-generation pipelines were
> temporarily switched from `anthropic/claude-haiku-4.5` /
> `google/gemini-2.5-flash` to `deepseek/deepseek-v4-flash-0731` in
> `projects/uwuchat/server/ai_pipeline.py`. The previous models (Haiku
> for quality-critical pipelines, Flash for cheap background tasks) are
> the fallback. To revert a pipeline, import `CLAUDE_HAIKU_MODEL` or
> `GOOGLE_GEMINI_FLASH_MODEL` from `airunner_services.conf.model_settings`
> and set its `"model"` value in `PIPELINE_CONFIG` — full revert
> instructions are in the `ai_pipeline.py` comments.
>
> **Provider pin revised 2026-08-20:** the DeepSeek pin
> (`_provider_order_for_model` in
> `server/src/airunner_services/cloud/llm/model_builders.py`) moved
> from `deepinfra` to the native `deepseek` provider after DeepInfra
> started returning "no endpoints found" for this OpenRouter account
> (account-side restriction, not a DeepInfra outage) — this was the
> direct cause of code-mode chat failing with "Error: An error
> occurred while contacting the model." DeepInfra was originally
> chosen as a US-incorporated host to avoid Chinese-hosted inference;
> the native `deepseek` provider is China-hosted, so this pin change
> is an explicit, informed exception to that policy, not a reversal of
> it — check DeepInfra availability before adding a similar pin
> elsewhere.

DeepSeek V4 Flash currently drives all text-generation pipelines
(experiment since 2026-07-27). EMBEDDING uses `qwen3-embedding-8b` and
is the only non-DeepSeek model. Token-spend distribution is tracked in
`public.pipeline_token_usage`.

**Do not configure or test with local GGUF models, Ollama, or any
edge/local inference path when working on UwUchat.** AIRunner supports
both deployment modes, but UwUchat uses OpenRouter exclusively for all
models — including DeepSeek and Qwen, which are accessed as cloud APIs
through OpenRouter. Changes to the cloud path
(`server/src/airunner_services/cloud/`) affect UwUchat; changes to the
edge path (`server/src/airunner_services/edge/`) do not.

---

## Server side

The server (`server/src/airunner_services/`) is the framework layer.
All server changes made so far are framework-level additions (session management,
agent-scoped knowledge, pgvector RAG). There is no server-side project-overlay
mechanism yet — if UwUChat needs server behavior AIRunner shouldn't have, use
the existing extension system or create a similar overlay for server routes.

### Where things live (LLM routing internals)

A handful of framework-internal concepts get re-derived by grep every time an
agent session needs them (this list came out of reviewing headlesscode worker
session logs, where it was over half of all `execute_command` calls in one
round). Start here instead of grepping from scratch:

| Concept | Location |
|---|---|
| Tool category classification (which category a tool call falls under) | `server/src/airunner_services/llm/managers/mixins/tool_classification_mixin/constants.py` (`_LOOKUP_TOOL_CATEGORY`) |
| Categories always included regardless of classification | `server/src/airunner_services/llm/managers/mixins/tool_classification_mixin/patterns.py` (`ALWAYS_INCLUDE_CATEGORIES`) |
| Native-routed tool categories (bypass the LLM tool-filter stage) | `server/src/airunner_services/llm/managers/mixins/tool_filtering_mixin/_plan.py` (`_NATIVE_ROUTING_CATEGORIES`) |
| Account/tenant resolution from the current request context | `server/src/airunner_services/data/tenant.py` (`get_account_id`) |
| Request-handling pipeline stages (where tool defaults get set, where classification is invoked) | `server/src/airunner_services/llm/managers/mixins/request_handling_mixin/` |

If you find yourself grepping for another framework-internal concept more
than once across sessions, add it here instead of leaving future sessions to
rediscover it.

---

## Environment

We use Docker for both development and production.

- Check server logs: `./scripts/docker.sh logs server`
- Run tests inside Docker:
  ```
  docker compose exec server python scripts/run_tests.py
  ```
- See `docker/README.md` for full setup instructions.

### Auto-restart behaviour

- **Server**: watchdog monitors Python files and restarts the server
  automatically when any `.py` file changes. No manual restart needed.
- **Client**: Vite HMR picks up client file changes automatically.
  No manual restart needed.

---

## Prompt Engineering Rules

**Never use real-world specifics in system prompts or few-shot examples.**

Real people, real artists, real events, real products, named public figures, or
anything from an active test conversation must never appear in prompt files.
Few-shot examples teach style and behavior only. If an example resembles a topic
the bot might actually be asked about, the model treats the example content as
factual knowledge and reproduces it verbatim — or improvises on it incorrectly.

Use abstract, generic placeholders: "an artist", "a collective", "a product",
"a public figure" — never real names.

This applies to all prompt files under `projects/uwuchat/server/` and
`server/src/airunner_services/llm/managers/prompt_builder/`.

---

## Testing Boundary

- The user will always test runtime behavior manually.
- Limit validation to static analysis, targeted unit tests, linting,
  compilation, and read-only inspection unless the user explicitly asks.
- When a change would normally be verified by launching the app, state that the
  user should verify it instead.

---

## Python Code Style

- Maximum line length: 79 characters. Maximum file size: 250 lines.
- Maximum class size: 200 lines. Maximum function size: 20 lines.
- One class per file. Follow PEP 8. Use type hints and docstrings.
- **Never use `# noqa` comments.** Fix the underlying issue instead.
- **Never use stopgaps, shims, or monkeypatches.** Always implement the correct
  first-class solution.

---

## JavaScript / React Code Style

- Functional components and hooks only. One component or hook per file.
- Maximum file size: 250 lines. Maximum component/function size: 50 lines.
- TypeScript types for all props, hook return values, and service interfaces.
- Components must not interact with `localStorage` or `IndexedDB` directly —
  always go through a custom hook.
- Do not suppress lint rules without explicit user approval.

---

## Client-Side Storage

### localStorage — small scalar data only
User preferences, auth tokens, last-known sync timestamps, simple config.

### IndexedDB — everything else
Binary assets, conversation list cache, canvas state.

Use the **raw IndexedDB API** (see `client/src/hooks/conversationsDB.ts` for the
established pattern). Dexie.js is not used in this project.

- All cached data carries an `updatedAt` timestamp; newer wins on conflict.
- Cache reads must be non-blocking — fall back to server fetch if unavailable.

---

## Database (Backend)

- Never use raw SQL. Always generate Alembic migrations:
  ```
  docker compose exec server airunner-generate-migration "your message"
  ```
- Migrations run automatically on API startup — never run them manually.
- All migrations must be idempotent (they run against every tenant schema).
  Probe column existence before destructive DDL:
  ```python
  def _column_exists(table: str, column: str) -> bool:
      conn = op.get_bind()
      return column in [c["name"] for c in sa.inspect(conn).get_columns(table)]
  ```
- Never mutate `alembic_version` manually — create a follow-up revision instead.

---

## Multi-Tenant PostgreSQL

Each authenticated user gets their own PostgreSQL schema (`tenant_<key>`).
Shared data lives in `public`. The `search_path` is set per-connection.

Key constraint: migrations and `_repair_application_schema` run against every
tenant schema independently — see the full rules in `.roo/rules-code/rules.md`.

---

## Security and Privacy

- Never log prompts, conversation bodies, tokens, secrets, or user content.
  Log counts, IDs, hashes, and state transitions only.
- Keep all app-managed files inside `AIRUNNER_BASE_PATH`.
- Client-side: never store sensitive data in IndexedDB. Auth tokens in
  localStorage only.

---

## Development Environment

**Neither Node.js nor Python is installed on the host machine.** All runtime
tooling (`node`, `npm`, `npx`, `tsc`, `python3`, `python`) is available only
inside Docker containers. Never attempt to run these commands directly on the
host — they will not be found. Use Docker to validate code instead of
running interpreters or compilers on the host.

---

## Committing

- A pre-commit hook enforces code rules. Never use `--no-verify`.
- Solo-developer project — commit straight to `master`. No feature
  branches or pull requests required.

### If the pre-commit hook fails

1. Stash immediately before touching anything:
   `git stash -u -m "[checkpoint]" && git stash apply`
2. Confirm the stash exists (`git stash list`), then fix and retry.
3. After three failed attempts, stop and report violations to the user.
