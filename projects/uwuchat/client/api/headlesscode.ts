import { request } from "./client-base";

/** One registered headlesscode project (project registry settings panel). */
export interface HeadlesscodeProject {
  id: number;
  name: string;
  repo_path: string;
  workspace_root: string;
  created_at?: string | null;
}

export interface HeadlesscodeProjectInput {
  name: string;
  repo_path: string;
  workspace_root: string;
}

/** One durable event row from a session's transcript. */
export interface HeadlesscodeSessionEvent {
  id: number;
  chat_block_kind?: string | null;
  raw_event: Record<string, unknown>;
  created_at?: string | null;
}

/** Session header data for a session card. */
export interface HeadlesscodeSession {
  headlesscode_session_id: string;
  project_id: number;
  project_name?: string | null;
  status: string;
  task_description?: string | null;
  mode?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface HeadlesscodeSessionDetail {
  session: HeadlesscodeSession;
  events: HeadlesscodeSessionEvent[];
}

export interface HeadlesscodeMessageResult {
  ok: boolean;
  session_id: string;
}

const BASE = "/api/v1/uwuchat/headlesscode";

export async function listHeadlesscodeProjects(): Promise<{
  projects: HeadlesscodeProject[];
}> {
  return request<{ projects: HeadlesscodeProject[] }>(
    "GET",
    `${BASE}/projects`,
  );
}

export async function createHeadlesscodeProject(
  body: HeadlesscodeProjectInput,
): Promise<HeadlesscodeProject> {
  return request<HeadlesscodeProject>("POST", `${BASE}/projects`, body);
}

export async function updateHeadlesscodeProject(
  id: number,
  body: HeadlesscodeProjectInput,
): Promise<HeadlesscodeProject> {
  return request<HeadlesscodeProject>(
    "PATCH",
    `${BASE}/projects/${id}`,
    body,
  );
}

export async function deleteHeadlesscodeProject(id: number): Promise<void> {
  return request<void>("DELETE", `${BASE}/projects/${id}`);
}

export async function getHeadlesscodeSessionDetail(
  sessionId: string,
): Promise<HeadlesscodeSessionDetail> {
  return request<HeadlesscodeSessionDetail>(
    "GET",
    `${BASE}/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export async function injectHeadlesscodeMessage(
  sessionId: string,
  text: string,
): Promise<HeadlesscodeMessageResult> {
  return request<HeadlesscodeMessageResult>(
    "POST",
    `${BASE}/sessions/${encodeURIComponent(sessionId)}/message`,
    { text },
  );
}
