# WebSocket RPC

AIRunner's client communicates with the daemon exclusively over a single
persistent WebSocket connection at `/api/v1/events`. HTTP-style calls are made
through `rpcRequest()` on the client, dispatched by `_dispatch_rpc()` on the
server. This page documents the transport contract and known gotchas.

---

## How it works

1. The client calls `rpcRequest(method, path, body)` in
   `client/src/features/api/WsApiClient.ts`.
2. A JSON frame is sent: `{type:"rpc", id, method, path, body}`.
3. The server's `_dispatch_rpc` in
   `server/src/airunner_services/api/routes/events_rpc.py` matches the
   method+path against registered handlers, merges query-string params into
   the body, and invokes the handler.
4. The handler returns `{status, body}` which is sent back as
   `{type:"rpc_response", id, status, body}`.

---

## Known gotchas

### 1. Query-string parameters — send in the body, not the URL

**Bug fixed:** 2026-06-09

Some client calls originally passed params only in the URL query string with
an empty body, e.g.:

```
GET /api/v1/llm/conversations/session?conversation_id=11   body={}
```

The dispatcher now merges query-string params into the body, but relying on
this is fragile. **Prefer sending params in the body** for new endpoints:

```ts
// preferred
request("GET", "/api/v1/llm/conversations/session", { conversation_id: 11 })
```

**Symptom when this breaks:** the endpoint falls back to a server-side
default (e.g. most-recent conversation) and ignores the client's requested id.
After clicking "New conversation" and reloading the browser, an old
conversation from history loads instead of a blank slate.

**Verify it's working:** open a raw WebSocket to `/api/v1/events` and send:

```json
{ "type": "rpc", "id": "test", "method": "GET",
  "path": "/api/v1/llm/conversations/session?conversation_id=11",
  "body": {} }
```

The `rpc_response` must have `body.conversation_id == 11`. If it returns a
different id the query-string merge has regressed.

---

### 2. HTTPException is not caught inside WebSocket handlers

Runtime helpers (`unload_llm_before_art`, `resolve_art_client`,
`require_runtime_registry`) raise `HTTPException`. Inside a WebSocket handler
FastAPI's exception middleware **does not run** — the exception bubbles up and
closes the connection instead of returning an error response.

**Fix:** wrap every call to these helpers in `try/except HTTPException` and
forward the error as a JSON message:

```python
try:
    client = resolve_art_client(registry)
except HTTPException as exc:
    await websocket.send_json({"type": "error", "message": exc.detail})
    return
```

---

### 3. LLM streaming — `messages` not `message`

The client sends `{type:"chat", messages:[...]}` (plural). The server handler
must read `data.get("messages")`; reading `data.get("message")` silently drops
the entire chat history.

---

### 4. A plain FastAPI HTTP route is invisible to the client

**Bug fixed:** 2026-08-20 (`projects/uwuchat/server/routes/code_mode_routes.py`)

`client-base.ts`'s `request()` sends every call over `rpcRequest()` — there is
no `fetch()` fallback. A resource whose server side is only a normal
`@router.get`/`@router.put` FastAPI router (registered in
`server_routes_specs.py` and mounted with `app.include_router`) will import
fine, pass code review, and even show up in `/openapi.json` — but the client
can never reach it. It fails at runtime with an RPC-side 404 from
`_dispatch_rpc` (`{"error": "Not found: PUT <path>"}`), not an HTTP 404, so it
won't show up in a network tab filtered to XHR/fetch — check the WebSocket
frames instead.

**Fix:** add a matching handler decorated with `@_rpc_register(method, path)`
(see `rpc_conversation_handlers.py` for the pattern, including the
per-module `_require_superuser(ws)` helper for admin-gated routes) and import
the new module in `api/routes/__init__.py`. The FastAPI HTTP router can stay
if something else needs real HTTP (e.g. a script), but it is not what the
client's UI is calling.

**Verify it's registered:** `_find_rpc_handler(method, path)` from
`events_rpc.py` should return a non-None handler — see
`test_all_routes_registered` in `test_rpc_dispatch.py` for the pattern of
asserting a path is present in `_rpc_routes`.

**Second confirmed instance (2026-08-21):**
`code_credits_routes.py` (`/api/v1/uwuchat/code-credits/*` — the only
way to top up an account's headlesscode spending balance) had the
exact same gap: HTTP-only, no `@_rpc_register` handler, so an admin
had **no way to fund code-mode sessions at all** through the app —
`launch_headlesscode_session` always failed with "no code credits."
Fixed the same way as gotcha #4's original case: added
`code_credits_rpc.py`, triggered via the same
`importlib.import_module(...)` pattern from the bottom of
`code_credits_routes.py` (mirroring `headlesscode_routes.py`'s
`headlesscode_rpc` trigger — see that file for the reference
implementation of this side-effect-import convention).

---

## RuntimeRegistry ownership

The daemon builds **one** `RuntimeRegistry` during `_initialize_lifecycle_service()`
and stores it on `app.runtime_registry`. `create_app()` in `server.py` must
reuse this registry — if it rebuilds it, new sidecar clients have `_process=None`
and attempt to spawn duplicate sidecar processes, causing "port already in use"
failures.

**Fix:** check `app_instance.runtime_registry` before calling
`build_runtime_registry()`.

---

## Sidecar isolation env vars

Sidecar processes must set `AIRUNNER_*_SIDECAR_PROCESS=1` for every modality
they don't own, otherwise `build_runtime_registry` inside the sidecar registers
and tries to start sub-sidecars. The art sidecar sets: `ART`, `TTS`, `LLM`,
`STT` all to `1`.

See `bootstrap.py` and `sidecar_art_launcher.py`.
