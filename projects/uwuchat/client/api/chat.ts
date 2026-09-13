import { request } from "./client-base";
import { BASE_URL, type JsonObject, type Message } from "../types/api";

// ── Health / Daemon ──
export async function healthCheck() {
  return request<{ status: string }>("GET", "/api/v1/health");
}

export async function getHardwareProfile() {
  return request<import("../types/api").HardwareProfile>(
    "GET", "/api/v1/daemon/hardware",
  );
}

// ── Conversations ──
export async function listConversations(limit = 50) {
  return request<import("../types/api").ConversationListResponse>(
    "GET", `/api/v1/llm/conversations?limit=${limit}`,
  );
}

export async function createConversation() {
  return request<{ conversation_id: number }>(
    "POST",
    "/api/v1/llm/conversations",
  );
}

export async function deleteConversation(id: number) {
  return request<void>("DELETE", `/api/v1/llm/conversations/${id}`);
}

export async function truncateConversation(
  conversationId: number,
  keepCount: number,
) {
  return request<{ truncated: boolean; kept: number }>(
    "POST",
    "/api/v1/llm/conversations/truncate",
    { conversation_id: conversationId, keep_count: keepCount },
  );
}

export async function deleteMessage(chatbotId: number, visibleIndex: number) {
  return request<{ kept: number }>(
    "DELETE",
    `/api/v1/llm/chatbot/${chatbotId}/messages/${visibleIndex}`,
  );
}

export async function loadConversation(conversationId: number) {
  return request<import("../types/api").ConversationSessionResponse>(
    "GET",
    `/api/v1/llm/conversations/session?conversation_id=${conversationId}`,
  );
}

export async function selectConversation(conversationId: number) {
  return request<import("../types/api").ConversationSessionResponse>(
    "POST",
    "/api/v1/llm/conversations/select",
    { conversation_id: conversationId },
  );
}

export async function getConversationPreviews(
  chatbotIds: number[],
): Promise<
  Record<string, { preview: string | null; updated_at: string | null }>
> {
  const res = await request<{
    previews: Record<
      string,
      { preview: string | null; updated_at: string | null }
    >;
  }>("POST", "/api/v1/llm/conversations/previews", {
    chatbot_ids: chatbotIds,
  });
  return res.previews ?? {};
}

// ── UwU thread / session ──

export async function getUwuSession(chatbotId: number) {
  return request<import("../types/api").UwuSessionResponse>(
    "GET",
    `/api/v1/llm/uwu-session?chatbot_id=${chatbotId}`,
  );
}

export async function loadUwuThread(
  chatbotId: number,
  limit = 200,
  offset = 0,
) {
  return request<import("../types/api").UwuThreadResponse>(
    "GET",
    `/api/v1/llm/thread?chatbot_id=${chatbotId}&limit=${limit}&offset=${offset}`,
    undefined,
    10_000,
  );
}

// ── LLM Models ──
export async function listLLMModels() {
  const data = await request<import("../types/api").BootstrapData>(
    "GET", "/api/v1/art/bootstrap",
  );
  const models = data.models ?? [];
  return models
    .filter((m: JsonObject) => m.category === "llm")
    .map((m: JsonObject) => ({
      label: String(m.name ?? m.version ?? m.path),
      value: String(m.path ?? ""),
      category: String(m.category ?? ""),
      pipeline_action: String(m.pipeline_action ?? ""),
    }));
}

// ---------------------------------------------------------------------------
// TTS — module-level singleton WebSocket for non-React callers
// ---------------------------------------------------------------------------

let _ttsWs: WebSocket | null = null;
let _ttsReady = false;
let _ttsPendingResolve: ((blob: Blob) => void) | null = null;
let _ttsPendingReject: ((err: Error) => void) | null = null;
let _ttsReconnectTimer: ReturnType<typeof setTimeout> | null = null;
let _ttsRetryCount = 0;
const _TTS_MAX_RETRIES = 10;

import { wsHost } from "./client-base";

function _ttsWsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${wsHost()}/api/v1/tts/ws`;
}

function _ttsConnect(): void {
  if (_ttsWs) {
    _ttsWs.onclose = null;
    _ttsWs.onerror = null;
    _ttsWs.onmessage = null;
    _ttsWs.close();
    _ttsWs = null;
  }

  try {
    const socket = new WebSocket(_ttsWsUrl());
    _ttsWs = socket;

    socket.onopen = () => {
      _ttsReady = true;
      _ttsRetryCount = 0;
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "audio") {
          const raw = data.data as string;
          const binary = atob(raw);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
          }
          const blob = new Blob([bytes], { type: "audio/wav" });
          if (_ttsPendingResolve) {
            _ttsPendingResolve(blob);
            _ttsPendingResolve = null;
            _ttsPendingReject = null;
          }
        } else if (data.type === "error") {
          const msg = data.message ?? "TTS failed";
          if (_ttsPendingReject) {
            _ttsPendingReject(new Error(msg));
            _ttsPendingResolve = null;
            _ttsPendingReject = null;
          }
        }
      } catch { /* ignore */ }
    };

    socket.onclose = (event) => {
      _ttsWs = null;
      _ttsReady = false;
      if (!event.wasClean) {
        if (_ttsRetryCount < _TTS_MAX_RETRIES) {
          const backoffMs = Math.min(
            1000 * Math.pow(2, _ttsRetryCount) + Math.random() * 500,
            30000,
          );
          _ttsRetryCount++;
          _ttsReconnectTimer = setTimeout(_ttsConnect, backoffMs);
        }
      }
    };

    socket.onerror = () => {
      socket.close();
    };
  } catch {
    if (_ttsRetryCount < _TTS_MAX_RETRIES) {
      const backoffMs = Math.min(
        1000 * Math.pow(2, _ttsRetryCount) + Math.random() * 500,
        30000,
      );
      _ttsRetryCount++;
      _ttsReconnectTimer = setTimeout(_ttsConnect, backoffMs);
    }
  }
}

function _ttsSend(msg: Record<string, unknown>): void {
  if (_ttsWs?.readyState === WebSocket.OPEN) {
    _ttsWs.send(JSON.stringify(msg));
  }
}

function _ttsDisconnect(): void {
  if (_ttsReconnectTimer) {
    clearTimeout(_ttsReconnectTimer);
    _ttsReconnectTimer = null;
  }
  if (_ttsWs) {
    _ttsWs.onclose = null;
    _ttsWs.onerror = null;
    _ttsWs.onmessage = null;
    _ttsWs.close();
    _ttsWs = null;
  }
  _ttsReady = false;
  _ttsRetryCount = 0;
}

// Initialize TTS WebSocket connection eagerly (lazy on first call)
let _ttsInit = false;
function _ttsEnsureConnected(): void {
  if (!_ttsInit) {
    _ttsInit = true;
    _ttsConnect();
  }
}

export async function synthesizeTTS(
  text: string,
  voice?: string,
  speed = 1.0,
): Promise<Blob> {
  _ttsEnsureConnected();

  return new Promise((resolve, reject) => {
    _ttsPendingResolve = resolve;
    _ttsPendingReject = reject;

    _ttsSend({
      type: "synthesize",
      text,
      voice,
      speed,
    });
  });
}

// ── Character Generator ──
export interface CharacterGenerateRequest {
  species: string;
  gender: string;
  vibe: string;
  quirk: string;
  affinity: string;
  age_era: string;
}

export interface CharacterGenerateResponse {
  name: string;
  personality: string;
  backstory: string;
  greeting: string;
}

export async function generateCharacter(
  attrs: CharacterGenerateRequest,
): Promise<CharacterGenerateResponse> {
  return request<CharacterGenerateResponse>(
    "POST",
    "/api/v1/llm/generate-character",
    attrs as unknown as Record<string, unknown>,
  );
}

// ── UwU Identity Generator ──
export interface UwuIdentityRequest {
  gender: string;
  personality_type: string;
  species_data?: Record<string, unknown>;
  location?: Record<string, unknown>;
  age?: number;
}

export interface UwuIdentityResponse {
  name: string;
  personality: string;
  backstory: string;
  greeting: string;
  // Human characters
  occupation?: string;
  // Non-human characters
  daily_life?: string;
  description?: string;
}

export async function persistUwuGreeting(
  chatbotId: number,
  greeting: string,
): Promise<void> {
  await request<void>("POST", "/api/v1/llm/uwu-greeting", {
    chatbot_id: chatbotId,
    greeting,
  });
}

export async function generateUwuIdentity(
  attrs: UwuIdentityRequest,
): Promise<UwuIdentityResponse> {
  return request<UwuIdentityResponse>(
    "POST",
    "/api/v1/llm/generate-uwu-identity",
    attrs as unknown as Record<string, unknown>,
  );
}

// ── LLM Settings Presets ──
export async function listLLMPresets(): Promise<
  Array<{ label: string; args: Record<string, unknown> }>
> {
  const data = await request<{
    presets: Array<{ label: string; args: Record<string, unknown> }>;
  }>("GET", "/api/v1/llm/settings-presets");
  return Array.isArray(data) ? data : (data.presets ?? []);
}
