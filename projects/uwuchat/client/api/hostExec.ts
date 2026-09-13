import { request } from "./client-base";

/** The host-executor policy (mirrors server HostExecPolicy + agent). */
export interface HostExecPolicy {
  enabled: boolean;
  enable_all: boolean;
  groups: Record<string, boolean>;
  whitelist: string[];
  blacklist: string[];
  allow_always: string[];
}

export const DEFAULT_GROUPS: Record<string, boolean> = {
  git: true,
  gh: true,
  shell: false,
  file: true,
  network: false,
  other: false,
};

export const GROUP_LABELS: Record<string, string> = {
  git: "Git (commit, push, merge, rebase)",
  gh: "GitHub CLI (issue/pr/release writes)",
  shell: "Arbitrary shell commands (python, node, npm, ...)",
  file: "File operations",
  network: "Network commands (curl, wget, ssh, scp)",
  other: "Anything unclassified",
};

const BASE = "/api/v1/uwuchat/host-exec";

/** Return the caller's saved policy (or the default when none is set). */
export async function getHostExecPolicy(): Promise<HostExecPolicy> {
  const res = await request<{ policy: HostExecPolicy }>(
    "GET",
    `${BASE}/policy`,
  );
  return res.policy;
}

/** Persist the caller's policy. */
export async function saveHostExecPolicy(
  policy: HostExecPolicy,
): Promise<HostExecPolicy> {
  const res = await request<{ policy: HostExecPolicy }>(
    "POST",
    `${BASE}/policy`,
    { policy },
  );
  return res.policy;
}

/** Classify a command as container-safe vs needs-host. */
export async function classifyCommand(
  command: string,
): Promise<{ command: string; group: string; needs_host: boolean }> {
  return request<{ command: string; group: string; needs_host: boolean }>(
    "POST",
    `${BASE}/classify`,
    { command },
  );
}
