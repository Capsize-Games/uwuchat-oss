/** Server URL — empty string when proxied through Vite dev server,
 *  otherwise configurable via env or defaults to localhost:8188. */
export const BASE_URL = import.meta.env.PROD
  ? (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8188")
  : "";

/** Generic JSON response wrapper. */
export type JsonObject = Record<string, unknown>;

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------
export interface Message {
  id?: number;
  role: "user" | "assistant" | "system";
  content: string;
  thinking_content?: string;
  created_at?: string;
  session_id?: number | null;
  session_started_at?: string | null;
  call_chain_id?: string | null;
  bot_mood?: string;
  bot_mood_emoji?: string;
  bot_mood_kaomoji?: string;
  /** Headlesscode session id — when set, the message renders as a
   *  live session card instead of a normal bubble. */
  headlesscode_session_id?: string;
  /** Tool-call records captured during this turn's stream — rendered
   *  as collapsible tool-call widgets inline in the assistant bubble. */
  tool_events?: ToolCallRecord[];
  /** Seed fields for the session card header (mirror the card entry
   *  written into the conversation by the launch task). */
  headlesscode_project_name?: string;
  headlesscode_status?: string;
  headlesscode_task?: string;
}

/** One tool invocation + its result, captured from tool_status WS
 *  events during a streamed turn.  Rendered as a collapsible widget. */
export interface ToolCallRecord {
  tool_id: string;
  tool_name: string;
  status: "starting" | "completed" | "error";
  details?: string | null;
  query?: string;
}

export interface UwuSessionResponse {
  conversation_id: number | null;
  session_id: number | null;
}

export interface UwuThreadResponse {
  messages: Record<string, unknown>[];
  total: number;
  offset: number;
  current_mood?: {
    mood?: string;
    emoji?: string;
    kaomoji?: string;
  } | null;
}

export interface Conversation {
  id: number;
  title: string;
  current: boolean;
  messages?: Message[];
  first_user_message?: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
}

export interface ConversationSessionResponse {
  conversation_id?: number;
  messages: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Hardware
// ---------------------------------------------------------------------------
export interface HardwareProfile {
  total_vram_gb: number;
  available_vram_gb: number;
  total_ram_gb: number;
  available_ram_gb: number;
  cuda_available: boolean;
  device_name: string | null;
  cpu_count: number;
  platform: string;
  num_gpus: number;
}

// ---------------------------------------------------------------------------
// LLM / Chat
// ---------------------------------------------------------------------------
export interface ChatCompletionRequest {
  messages: Message[];
  model?: string;
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
}

export interface StreamChunk {
  token?: string;
  done?: boolean;
  message_type?: string;
  conversation_id?: number;
  error?: string;
  call_chain_id?: string;
}

// ---------------------------------------------------------------------------
// Art
// ---------------------------------------------------------------------------
export interface ArtGenerateRequest {
  prompt: string;
  negative_prompt?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg_scale?: number;
  seed?: number;
  num_images?: number;
  model?: string;
  version?: string;
  scheduler?: string;
  init_image?: string;   // base64 PNG of the canvas region
  mask_image?: string;   // base64 PNG of the inpaint mask, white = inpaint region
}

export interface ArtGenerateResponse {
  job_id: string;
}

export interface ArtJobStatus {
  status: string;
  progress: number;
  error?: string;
  image?: string;  // base64 PNG, present when status === "completed"
  width?: number;  // pixel width of the generated image
  height?: number; // pixel height of the generated image
}

// ---------------------------------------------------------------------------
// VRAM
// ---------------------------------------------------------------------------
export interface VRAMEstimate {
  path: string;
  file_size_gb: number;
  native_dtype: string | null;
}

// ---------------------------------------------------------------------------
// Bootstrap / Catalog
// ---------------------------------------------------------------------------
export interface BootstrapData {
  models: JsonObject[];
  pipelines: JsonObject[];
  unified_model_files: JsonObject;
  controlnet_bootstrap_data: JsonObject[];
  espeak_settings_data: JsonObject[];
  llm_file_bootstrap_data: JsonObject;
  openvoice_files: JsonObject;
  openvoice_core_models: JsonObject[];
  openvoice_language_models: JsonObject;
  path_settings_data: JsonObject[];
  rmbg_files: JsonObject;
  sd_file_bootstrap_data: JsonObject;
  whisper_files: JsonObject;
  imagefilter_bootstrap_data: JsonObject;
  prompt_templates_bootstrap_data: JsonObject[];
}

// ---------------------------------------------------------------------------
// Settings (resource store)
// ---------------------------------------------------------------------------
export interface ResourceRecord {
  id?: number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Downloads
// ---------------------------------------------------------------------------
export interface DownloadJobAccepted {
  job_id: string;
  status?: string;
}

export interface DownloadJobStatus {
  status: string;
  progress: number;
  error?: string;
  result?: JsonObject;
  metadata?: JsonObject;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------
export interface DocumentRecord {
  id: number;
  name: string;
  path: string;
  file_type: string;
  indexed: boolean;
  active: boolean;
}
