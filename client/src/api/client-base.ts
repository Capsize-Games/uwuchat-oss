import { rpcRequest } from "../features/api/WsApiClient";
import { getRequestHeaders } from "virtual:extensions";
import type { JsonObject, StreamChunk } from "../types/api";

/**
 * Return the ``?token=`` query suffix for a WebSocket URL, or "" when
 * unauthenticated.
 *
 * WS upgrades can't set Authorization headers, so the JWT must travel in
 * the query string for the server to bind the tenant (see ws_tenant_scope).
 * Every WS endpoint that touches per-tenant data (canvas, art, tts, …) must
 * include this, or its DB access falls back to the tenant_anonymous schema.
 */
export function wsTokenSuffix(): string {
  let token: string | null = null;
  try {
    const auth = getRequestHeaders()["Authorization"];
    token = auth?.startsWith("Bearer ") ? auth.slice(7) : null;
  } catch {
    token = null;
  }
  return token ? `?token=${encodeURIComponent(token)}` : "";
}

/**
 * Resolve the WebSocket host for any WS endpoint.
 *
 * In dev mode the Vite proxy forwards /api/v1/* to the backend, so we
 * use the page's own host (port 5173).  In production the caller must
 * set VITE_API_BASE_URL; the fallback is localhost:8188.
 */
export function wsHost(): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (raw) {
    return raw.replace(/^https?:\/\//, "");
  }
  // Dev mode — go through the Vite proxy.
  return location.host;
}

const REQUEST_TIMEOUT_MS = 30_000; // 30 seconds

/**
 * Send an HTTP-style request over the shared WebSocket RPC channel.
 *
 * The signature is identical to the old ``fetch()``-based version so
 * all callers work without changes.  The underlying transport is now
 * a single persistent WebSocket connection.
 */
export async function request<T>(
  method: string,
  path: string,
  body?: JsonObject,
  timeoutMs?: number,
): Promise<T> {
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(
      () => reject(new Error(`Request timed out: ${method} ${path}`)),
      timeoutMs ?? REQUEST_TIMEOUT_MS,
    ),
  );
  return Promise.race([rpcRequest<T>(method, path, body), timeout]);
}
