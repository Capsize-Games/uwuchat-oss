/**
 * Module-level singleton WebSocket client for the unified
 * ``/api/v1/events`` endpoint.
 *
 * Provides:
 * - Event subscription (``subscribe``/``unsubscribe``) for ``useEventBus``
 * - RPC request/response (``rpcRequest``, ``rpcRequestBlob``) for
 *   ``client-base.ts`` ``request()`` replacement
 *
 * All consumers share one WebSocket connection.
 */

import { wsHost } from "../../api/client-base";
import { getRequestHeaders } from "virtual:extensions";

// ---------------------------------------------------------------------------
// WS URL resolver
// ---------------------------------------------------------------------------

function currentToken(): string | null {
  const authHeader = getRequestHeaders()["Authorization"];
  return authHeader?.startsWith("Bearer ") ? authHeader.slice(7) : null;
}

function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const base = `${proto}://${wsHost()}/api/v1/events`;
  const token = currentToken();
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EventBusCallback = (event: string, data: unknown) => void;

interface PendingRpc {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
}

// ---------------------------------------------------------------------------
// Singleton state
// ---------------------------------------------------------------------------

let _ws: WebSocket | null = null;
let _connected = false;
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _mountCount = 0;
let _connecting = false;
let _connGen = 0;
// The auth token the live socket was opened with. The server binds the
// tenant at connection time (token travels in the URL query string), so a
// token change — e.g. an SPA login that doesn't reload the page — requires a
// fresh connection for subsequent RPCs to run under the new identity.
let _connectedToken: string | null = null;

// When a token rotation forces a new socket, the previous socket stays
// alive briefly so in-flight RPCs (especially streaming LLM responses)
// can complete.  _drainingRpcIds is the flat union of all draining-RPC
// IDs (used by the new socket's onmessage to skip RPCs it doesn't own).
// _drainingSocketRpcIds tracks per-socket ownership so we know when a
// draining socket can be closed.
const _drainingRpcIds = new Set<string>();
const _drainingSocketRpcIds = new Map<WebSocket, Set<string>>();

/** Detach handlers and close a draining socket.  Idempotent — safe to
 *  call even if the socket has already torn itself down. */
function _closeDrainingSocket(socket: WebSocket): void {
  _drainingSocketRpcIds.delete(socket);
  socket.onclose = null;
  socket.onerror = null;
  socket.onmessage = null;
  try {
    socket.close();
  } catch {
    /* socket may already be closed */
  }
}

/** Called after a single draining RPC completes (resolve or reject).
 *  Removes the id from both tracking structures.  If this was the last
 *  RPC on its socket, closes the socket. */
function _onDrainRpcComplete(socket: WebSocket, rpcId: string): void {
  _drainingRpcIds.delete(rpcId);
  const rpcIds = _drainingSocketRpcIds.get(socket);
  if (!rpcIds) return;
  rpcIds.delete(rpcId);
  if (rpcIds.size === 0) {
    _closeDrainingSocket(socket);
  }
}

// Fires exactly once per page load when an RPC response carries
// error_code === "encryption_session_expired".  The AuthProvider listens
// for this and forces logout.  Debounced so multiple concurrent failed
// RPCs only trigger one redirect.
let _encryptionSessionExpiredDispatched = false;

// Session-bootstrap payload pushed by the server immediately after
// tenant resolution on connect.  Components read this instead of
// firing individual singleton/roster RPC calls on mount.
let _bootstrapPayload: Record<string, unknown> | null = null;

// Resolvers waiting for the bootstrap payload (registered before the
// WS connection delivers the bootstrap message).
const _bootstrapResolvers: Array<
  (payload: Record<string, unknown>) => void
> = [];

// Event callbacks: event type → Set of callbacks
const _eventCallbacks = new Map<string, Set<EventBusCallback>>();

// Subscribed event types on the WS
const _subscribedEvents = new Set<string>();

// Pending RPC requests: request ID → PendingRpc
const _pendingRpc = new Map<string, PendingRpc>();

// Connection-state listeners (e.g. the "Live"/"Reconnecting" indicator) —
// notified on transitions so the UI updates instantly instead of polling.
const _connectionListeners = new Set<(connected: boolean) => void>();

function _setConnected(value: boolean): void {
  if (_connected === value) return;
  _connected = value;
  for (const cb of _connectionListeners) {
    try {
      cb(value);
    } catch {
      /* a listener error must not break others */
    }
  }
}

// Messages queued while WS is connecting
const _sendQueue: Record<string, unknown>[] = [];

// Establish the shared WebSocket immediately on module load.
_mountCount++;
_connect();

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

function _send(msg: Record<string, unknown>): void {
  if (_ws?.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(msg));
  } else {
    // CONNECTING, null, CLOSING, or CLOSED — queue the message.
    // It will be flushed when the next connection opens (onopen).
    // CLOSING/CLOSED were previously a silent drop; queueing them
    // prevents RPC promises from hanging forever during the narrow
    // window between onerror.close() and onclose._ws=null.
    _sendQueue.push(msg);
  }
}

function _subscribeEvents(events: string[]): void {
  const needed = events.filter((e) => !_subscribedEvents.has(e));
  if (needed.length === 0) return;
  for (const e of needed) _subscribedEvents.add(e);
  _send({ type: "subscribe", events: needed });
}

function _unsubscribeEvents(events: string[]): void {
  const active = events.filter((e) => _subscribedEvents.has(e));
  if (active.length === 0) return;
  for (const e of active) _subscribedEvents.delete(e);
  _send({ type: "unsubscribe", events: active });
}

/**
 * Reconnect if the auth token has changed since the socket was opened.
 *
 * The tenant is bound to the connection (token in the URL), so after a
 * login/logout that doesn't reload the page the existing socket would keep
 * issuing RPCs under the previous (often anonymous) identity. Called before
 * every RPC / event subscription so the next request uses the live token.
 *
 * When the token rotates (routine background refresh), the old socket is
 * kept alive for in-flight RPCs to drain while a new socket is opened in
 * parallel.  Pending RPCs are NOT rejected — they complete on the old
 * socket naturally.  ``_setConnected`` is NOT called, so the UI never sees
 * a disconnect blip purely from a token rotation.
 */
function _ensureAuthFresh(): void {
  if (currentToken() === _connectedToken) return;

  // Discard the bootstrap payload cached from the previous
  // identity so waitForBootstrap() waits for the new socket's
  // server-pushed bootstrap instead of serving stale data (e.g.
  // an anonymous/empty roster after a fresh login).
  _bootstrapPayload = null;

  if (_ws) {
    if (_ws.readyState === WebSocket.CONNECTING) {
      // Socket hasn't connected yet — no identity to drain.
      // Close it cleanly and let _connect() open a fresh one.
      _ws.onopen = null;
      _ws.onmessage = null;
      _ws.onclose = null;
      _ws.onerror = null;
      try {
        _ws.close();
      } catch {
        /* ignore */
      }
      _ws = null;
      _setConnected(false);
    } else {
      // Socket is OPEN — keep it alive for in-flight RPC draining.
      const oldSocket = _ws;

      // Record which RPCs are on this socket so we only reject them
      // if the draining socket actually dies, and so we know when it
      // is safe to close it.
      const rpcIds = new Set(_pendingRpc.keys());
      for (const id of rpcIds) {
        _drainingRpcIds.add(id);
      }

      if (rpcIds.size === 0) {
        // Nothing to drain — close immediately, no socket leak.
        oldSocket.onclose = null;
        oldSocket.onerror = null;
        oldSocket.onmessage = null;
        try {
          oldSocket.close();
        } catch {
          /* ignore */
        }
        _ws = null;
        _setConnected(false);
        // Fall through to _connect() below — it handles reconnect.
      } else {
        _drainingSocketRpcIds.set(oldSocket, rpcIds);

        // Override onmessage so the draining socket continues to
        // resolve in-flight RPCs.  (The original handler would be
        // invalidated by the _connGen bump in _connect().)
        oldSocket.onmessage = (event: MessageEvent) => {
          // ── Binary frame ──
          if (typeof event.data !== "string") {
            for (const [id, pending] of _pendingRpc) {
              if (_drainingRpcIds.has(id)) {
                _pendingRpc.delete(id);
                pending.resolve(event.data as Blob);
                _onDrainRpcComplete(oldSocket, id);
                return;
              }
            }
            return;
          }

          // ── JSON frame ──
          try {
            const msg = JSON.parse(event.data) as {
              type?: string;
              id?: string;
              data?: unknown;
              body?: unknown;
              status?: number;
              error?: string;
              binary?: boolean;
            };
            if (msg.type === "rpc_response" && msg.id) {
              if (!_drainingRpcIds.has(msg.id)) return;
              const pending = _pendingRpc.get(msg.id);
              if (pending) {
                _pendingRpc.delete(msg.id);
                if (msg.binary === true) {
                  _pendingRpc.set(msg.id, pending);
                } else if (
                  msg.status &&
                  msg.status >= 200 &&
                  msg.status < 300
                ) {
                  pending.resolve(msg.body);
                  _onDrainRpcComplete(oldSocket, msg.id);
                } else {
                  _maybeDispatchEncryptionSessionExpired(
                    msg.body as Record<string, unknown> | undefined,
                  );
                  pending.reject(_rpcErrorFromMessage(msg));
                  _onDrainRpcComplete(oldSocket, msg.id);
                }
              }
            }
            // Events are intentionally not dispatched from the
            // draining socket — they arrive on the new socket
            // after reconnect.
          } catch {
            /* ignore malformed messages */
          }
        };

        // Override onclose so the draining socket doesn't trigger
        // _setConnected(false) or _reconnect() when it eventually
        // closes naturally.
        oldSocket.onclose = () => {
          // Reject any RPCs still pending on this socket.
          const ids = _drainingSocketRpcIds.get(oldSocket);
          if (ids) {
            for (const id of ids) {
              _drainingRpcIds.delete(id);
              const pending = _pendingRpc.get(id);
              if (pending) {
                _pendingRpc.delete(id);
                pending.reject(
                  new Error("WebSocket disconnected"),
                );
              }
            }
            _drainingSocketRpcIds.delete(oldSocket);
          }
          // Only schedule a reconnect if no connection attempt is
          // in progress and no other socket is active.
          if (!_ws && !_connecting && _mountCount > 0) {
            _reconnect();
          }
        };

        oldSocket.onerror = null;
        _ws = null;
      }
    }
  }

  // IMPORTANT: do NOT reject _pendingRpc — in-flight RPCs stay alive
  // on the draining socket.
  // IMPORTANT: do NOT call _setConnected(false) — we're still
  // connected via the draining socket.

  _connecting = false;
  _connect();
}

function _reconnect(): void {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer);
    _reconnectTimer = null;
  }
  _reconnectTimer = setTimeout(_connect, 3000);
}

function _connect(): void {
  // Prevent concurrent connection attempts
  if (_connecting) return;
  if (_ws && (_ws.readyState === WebSocket.OPEN ||
              _ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  if (_ws) {
    const old = _ws;
    old.onclose = null;
    old.onerror = null;
    old.onmessage = null;
    old.close();
    _ws = null;
  }

  _connecting = true;
  const gen = ++_connGen;
  _connectedToken = currentToken();

  try {
    const socket = new WebSocket(wsUrl());
    _ws = socket;

    socket.onopen = () => {
      if (gen !== _connGen) return; // stale — a newer socket took over
      _connecting = false;
      _setConnected(true);
      // Re-subscribe all currently tracked event types
      const events = [..._subscribedEvents];
      if (events.length > 0) {
        _send({ type: "subscribe", events });
      }
      // Flush queued messages
      const queue = _sendQueue.splice(0);
      for (const msg of queue) {
        _send(msg);
      }
    };

    socket.onmessage = (event: MessageEvent) => {
      if (gen !== _connGen) return; // stale
      // ── Binary frame: resolve the first pending binary RPC ──
      if (typeof event.data !== "string") {
        for (const [id, pending] of _pendingRpc) {
          // Skip RPCs that belong to a draining socket — a binary
          // frame on the new socket must not resolve the wrong RPC.
          if (_drainingRpcIds.has(id)) continue;
          _pendingRpc.delete(id);
          pending.resolve(event.data as Blob);
          return;
        }
        return;
      }

      // ── JSON frame ──
      try {
        const msg = JSON.parse(event.data) as {
          type?: string;
          event?: string;
          id?: string;
          data?: unknown;
          body?: unknown;
          status?: number;
          error?: string;
          binary?: boolean;
          headers?: Record<string, string>;
        };

        if (msg.type === "event" && msg.event) {
          const cbs = _eventCallbacks.get(msg.event);
          if (cbs) {
            for (const cb of cbs) {
              try {
                cb(msg.event, msg.data);
              } catch {
                // individual callback error must not break others
              }
            }
          }
        } else if (msg.type === "rpc_response" && msg.id) {
          const pending = _pendingRpc.get(msg.id);
          if (pending) {
            _pendingRpc.delete(msg.id);
            if (msg.binary === true) {
              // Binary response: re-register to expect the binary frame
              _pendingRpc.set(msg.id, pending);
            } else if (msg.status && msg.status >= 200 && msg.status < 300) {
              pending.resolve(msg.body);
            } else {
              _maybeDispatchEncryptionSessionExpired(
                msg.body as Record<string, unknown> | undefined,
              );
              pending.reject(_rpcErrorFromMessage(msg));
            }
          }
        } else if (msg.type === "bootstrap") {
          _bootstrapPayload = (msg.body ?? {}) as Record<
            string,
            unknown
          >;
          const resolvers = _bootstrapResolvers.splice(0);
          for (const resolve of resolvers) {
            resolve(_bootstrapPayload);
          }
        } else if (msg.type === "force_logout") {
          // Server-side proactive logout — the in-memory DEK cache was
          // wiped (server restart / TTL expiry) so encrypted operations
          // would fail.  Reuse the same DOM-event dispatch path that the
          // RPC error handler uses, so AuthProvider.logout() is called in
          // exactly one place no matter how the condition is detected.
          _maybeDispatchEncryptionSessionExpired({
            error_code: "encryption_session_expired",
          });
        }
        // Ignore subscribed, unsubscribed, pong, keepalive
      } catch {
        // ignore malformed messages
      }
    };

    socket.onclose = () => {
      if (gen !== _connGen) return; // stale
      _connecting = false;
      _ws = null;
      _setConnected(false);
      // Reject all pending RPCs
      for (const [id, pending] of _pendingRpc) {
        _pendingRpc.delete(id);
        pending.reject(new Error("WebSocket disconnected"));
      }
      if (_mountCount > 0) _reconnect();
    };

    socket.onerror = () => {
      if (gen !== _connGen) return; // stale
      _connecting = false;
      socket.close();
    };
  } catch {
    _connecting = false;
    if (_mountCount > 0) _reconnect();
  }
}

// ---------------------------------------------------------------------------
// Public RPC helpers
// ---------------------------------------------------------------------------

let _rpcIdCounter = 0;

function _nextRpcId(): string {
  _rpcIdCounter++;
  return `rpc-${Date.now()}-${_rpcIdCounter}`;
}

export type RpcError = Error & { code?: string };

/**
 * Check an RPC response body for the encryption-session-expired code and
 * fire exactly one ``airunner:encryption-session-expired`` DOM event per
 * page load.  The AuthProvider listens for this and forces logout.
 */
function _maybeDispatchEncryptionSessionExpired(
  bodyRec: Record<string, unknown> | undefined,
): void {
  if (
    !_encryptionSessionExpiredDispatched &&
    bodyRec?.error_code === "encryption_session_expired"
  ) {
    _encryptionSessionExpiredDispatched = true;
    window.dispatchEvent(new Event("airunner:encryption-session-expired"));
  }
}

/** Build an Error from a failed rpc_response, preserving error_code. */
function _rpcErrorFromMessage(msg: {
  error?: string;
  detail?: string;
  status?: number;
  body?: unknown;
}): RpcError {
  const bodyRec = msg.body as Record<string, unknown> | undefined;
  const errMsg =
    msg.detail ??
    (bodyRec?.detail as string) ??
    msg.error ??
    (bodyRec?.error as string) ??
    `RPC error ${msg.status}`;
  const err: RpcError = new Error(errMsg);
  if (typeof bodyRec?.error_code === "string") {
    err.code = bodyRec.error_code;
  }
  return err;
}

/** Return whether the WebSocket is currently connected. */
export function isWsConnected(): boolean {
  return _connected;
}

/**
 * Subscribe to WebSocket connection-state transitions. The callback fires
 * with the new state on every connect/disconnect. Returns an unsubscribe
 * function. Lets the UI react instantly instead of polling `isWsConnected`.
 */
export function onWsConnectionChange(
  cb: (connected: boolean) => void,
): () => void {
  _connectionListeners.add(cb);
  return () => {
    _connectionListeners.delete(cb);
  };
}

/**
 * Send an RPC request and wait for the JSON response.
 * Replaces the old `fetch()`-based request() in client-base.ts.
 */
export function rpcRequest<T>(
  method: string,
  path: string,
  body?: Record<string, unknown>,
): Promise<T> {
  return new Promise((resolve, reject) => {
    _ensureAuthFresh();
    const id = _nextRpcId();
    _pendingRpc.set(id, {
      resolve: resolve as (value: unknown) => void,
      reject,
    });
    // Ensure the WS connection exists, even if no event bus consumers
    // have registered (RPC-only caller)
    if (!_ws || (_ws.readyState !== WebSocket.OPEN && _ws.readyState !== WebSocket.CONNECTING)) {
      _mountCount++;
      _connect();
    }
    _send({ type: "rpc", id, method, path, body: body ?? {} });
  });
}

/**
 * Send an RPC request and return the binary response as a Blob.
 * Used for images, audio, and other binary data.
 */
export function rpcRequestBlob(
  method: string,
  path: string,
  body?: Record<string, unknown>,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    _ensureAuthFresh();
    const id = _nextRpcId();
    _pendingRpc.set(id, {
      resolve: resolve as (value: unknown) => void,
      reject,
    });
    // Ensure the WS connection exists (same as rpcRequest)
    if (!_ws || (_ws.readyState !== WebSocket.OPEN && _ws.readyState !== WebSocket.CONNECTING)) {
      _mountCount++;
      _connect();
    }
    _send({ type: "rpc", id, method, path, body: body ?? {} });
  });
}

// ---------------------------------------------------------------------------
// Public event bus helpers
// ---------------------------------------------------------------------------

/**
 * Register an event callback.
 * Called by useEventBus on mount.
 */
export function registerEventCallbacks(
  events: string[],
  callback: EventBusCallback,
): void {
  _mountCount++;

  _ensureAuthFresh();
  if (_mountCount === 1) _connect();

  for (const event of events) {
    let cbs = _eventCallbacks.get(event);
    if (!cbs) {
      cbs = new Set();
      _eventCallbacks.set(event, cbs);
    }
    cbs.add(callback);
  }

  _subscribeEvents(events);
}

/**
 * Unregister an event callback.
 * Called by useEventBus on unmount.
 */
export function unregisterEventCallbacks(
  events: string[],
  callback: EventBusCallback,
): void {
  for (const event of events) {
    const cbs = _eventCallbacks.get(event);
    if (cbs) {
      cbs.delete(callback);
      if (cbs.size === 0) {
        _eventCallbacks.delete(event);
      }
    }
  }

  const orphaned = events.filter((e) => !_eventCallbacks.has(e));
  if (orphaned.length > 0) _unsubscribeEvents(orphaned);

  _mountCount--;
}

// ---------------------------------------------------------------------------
// Bootstrap data helpers
// ---------------------------------------------------------------------------

/**
 * Return the session-bootstrap payload if already received, or ``null``.
 *
 * The server pushes ``{"type": "bootstrap", "body": {...}}`` immediately
 * after tenant resolution on every new WS connection.  Components that
 * need ``ApplicationSettings``, the ``Chatbot`` roster, or the immersion
 * ``ProjectSetting`` at connect time should read this synchronously
 * rather than firing individual RPC calls.
 */
export function getBootstrapPayload(): Record<
  string,
  unknown
> | null {
  return _bootstrapPayload;
}

/**
 * Return a promise that resolves with the bootstrap payload.
 *
 * If the payload has already arrived, the promise resolves immediately.
 * Callers that mount after WS connect (the normal case) will get an
 * already-resolved promise; callers that mount before the WS connects
 * (e.g. during an SPA route transition) will wait until it arrives.
 */
export function waitForBootstrap(): Promise<
  Record<string, unknown>
> {
  if (_bootstrapPayload) {
    return Promise.resolve(_bootstrapPayload);
  }
  return new Promise((resolve) => {
    _bootstrapResolvers.push(resolve);
  });
}
