import { request } from "./client-base";

const BASE = "/api/v1/uwuchat";

/** Mirrors code_mode_service.py's CODE_MODE_SLUGS. */
export const CODE_MODE_SLUGS = [
  "code",
  "architect",
  "ask",
  "debug",
  "orchestrator",
  "planning",
  "zoo-audit",
  "script-agent",
  "qa-agent",
  "deepseek-reviewer",
  "multi-agent-orchestrator-headless",
] as const;
export type CodeModeSlug = (typeof CODE_MODE_SLUGS)[number];

export interface CodeModeState {
  enabled: boolean;
  mode: CodeModeSlug;
}

export async function getCodeMode(
  conversationId: number,
): Promise<CodeModeState> {
  return request<CodeModeState>(
    "GET",
    `${BASE}/code-mode/${conversationId}`,
  );
}

export async function setCodeMode(
  conversationId: number,
  enabled: boolean,
  mode?: CodeModeSlug,
): Promise<CodeModeState> {
  return request<CodeModeState>(
    "PUT",
    `${BASE}/code-mode/${conversationId}`,
    mode ? { enabled, mode } : { enabled },
  );
}
