/**
 * Admin API client for the conversation inspector extension (superuser only).
 *
 * Mirrors the auth extension's admin-api.ts pattern — fetch through the
 * Vite proxy with bearer token attached.
 */

import { getRequestHeaders } from "@extensions/auth/client/headers";

const PREFIX = "/api/v1/conversation_inspector";

export interface ConversationSummary {
  id: number;
  title: string | null;
  user_name: string;
  chatbot_name: string;
  message_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
}

export interface FlowStep {
  type:
    | "system_prompt"
    | "per_turn_context"
    | "semantic_bridge"
    | "user_message"
    | "rag_step"
    | "thinking"
    | "tool_call"
    | "tool_result"
    | "mood_update"
    | "response"
    | "system_message"
    | "proactive_trigger"
    | string;
  label: string;
  content?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface TurnData {
  turn_index: number;
  user_message: Record<string, unknown> | null;
  system_prompt: Record<string, unknown> | null;
  rag_context: Record<string, unknown> | null;
  flow_steps: FlowStep[];
  model?: string | null;
  total_tokens: number;
  total_characters: number;
}

export interface ConversationFlowResponse {
  conversation_id: number;
  title: string | null;
  user_name: string;
  chatbot: Record<string, unknown> | null;
  turns: TurnData[];
  total_tokens: number;
  total_characters: number;
}

/** Shared fetch wrapper: attaches auth headers and unwraps API errors. */
async function inspectorFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${PREFIX}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...getRequestHeaders(),
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const err = await res.json();
      if (err?.detail) detail = err.detail;
    } catch {
      // non-JSON error body — keep the status-based message
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function fetchConversations(
  limit = 100,
  offset = 0,
  q = "",
  userId?: number | null,
): Promise<ConversationListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  if (q) params.set("q", q);
  if (userId != null) params.set("user_id", String(userId));
  return inspectorFetch(`/conversations?${params.toString()}`);
}

export async function fetchFlow(
  conversationId: number,
  userId?: number,
): Promise<ConversationFlowResponse> {
  const params = new URLSearchParams();
  if (userId != null) params.set("user_id", String(userId));
  const qs = params.toString();
  return inspectorFetch(`/flow/${conversationId}${qs ? "?" + qs : ""}`);
}

export async function fetchThreadFlow(
  chatbotId: number,
  userId?: number,
): Promise<ConversationFlowResponse> {
  const params = new URLSearchParams();
  if (userId != null) params.set("user_id", String(userId));
  const qs = params.toString();
  return inspectorFetch(`/flow/chatbot/${chatbotId}${qs ? "?" + qs : ""}`);
}
