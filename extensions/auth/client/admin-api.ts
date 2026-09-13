/**
 * Admin API client for the auth extension (superuser only).
 *
 * Mirrors api.ts's fetch-through-the-Vite-proxy style and attaches the
 * bearer token the same way the authenticated calls do. Every endpoint
 * here is gated server-side by `require_superuser`; the frontend gate in
 * the AdminPage is UX only.
 */

import { getRequestHeaders } from "./headers";

const ADMIN_PREFIX = "/api/v1/auth/admin";

export interface AdminAccount {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  is_suspended: boolean;
  auth_provider: string;
}

export interface AdminAccountDetail extends AdminAccount {
  tenant_schema: string;
  created_at: string | null;
  last_login: string | null;
}

export interface AdminResetUsageResult {
  message: string;
  deleted_count: number;
}

export interface AdminAccountList {
  accounts: AdminAccount[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminAccountUpdate {
  is_active?: boolean;
  is_verified?: boolean;
  is_superuser?: boolean;
}

export interface AdminCreateAccount {
  email: string;
  username?: string;  // Optional — server auto-generates if omitted
  password: string;
  is_superuser?: boolean;
  is_verified?: boolean;
}

export interface AdminDeleteResult {
  id: number;
  message: string;
  tenant_schema: string;
}

/** Shared fetch wrapper: attaches auth headers and unwraps API errors. */
async function adminFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${ADMIN_PREFIX}${path}`, {
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
  // DELETE/PATCH always return a body in this API, but guard anyway.
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function listAccounts(params: {
  limit?: number;
  offset?: number;
  q?: string;
} = {}): Promise<AdminAccountList> {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  if (params.q) search.set("q", params.q);
  const qs = search.toString();
  return adminFetch<AdminAccountList>(`/accounts${qs ? `?${qs}` : ""}`);
}

export function getAccount(id: number): Promise<AdminAccountDetail> {
  return adminFetch<AdminAccountDetail>(`/accounts/${id}`);
}

export function updateAccount(
  id: number,
  body: AdminAccountUpdate,
): Promise<AdminAccountDetail> {
  return adminFetch<AdminAccountDetail>(`/accounts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function disableAccount(id: number): Promise<AdminAccountDetail> {
  return adminFetch<AdminAccountDetail>(`/accounts/${id}/disable`, {
    method: "POST",
  });
}

export function enableAccount(id: number): Promise<AdminAccountDetail> {
  return adminFetch<AdminAccountDetail>(`/accounts/${id}/enable`, {
    method: "POST",
  });
}

export function createAccount(
  body: AdminCreateAccount,
): Promise<AdminAccountDetail> {
  return adminFetch<AdminAccountDetail>(`/accounts`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteAccount(id: number): Promise<AdminDeleteResult> {
  return adminFetch<AdminDeleteResult>(`/accounts/${id}`, {
    method: "DELETE",
  });
}

export function suspendAccount(id: number): Promise<AdminAccountDetail> {
  return adminFetch<AdminAccountDetail>(`/accounts/${id}/suspend`, {
    method: "POST",
  });
}

export function setUsage(
  id: number,
  targetCount: number,
): Promise<AdminResetUsageResult> {
  return adminFetch<AdminResetUsageResult>(
    `/accounts/${id}/set-usage`,
    { method: "POST", body: JSON.stringify({ target_count: targetCount }) },
  );
}

export function getUsageCount(
  id: number,
): Promise<{ turns_used: number }> {
  return adminFetch<{ turns_used: number }>(
    `/accounts/${id}/usage-count`,
  );
}

export function reactivateAccount(id: number): Promise<AdminAccountDetail> {
  return adminFetch<AdminAccountDetail>(`/accounts/${id}/reactivate`, {
    method: "POST",
  });
}

export function resetUsage(
  id: number,
): Promise<AdminResetUsageResult> {
  return adminFetch<AdminResetUsageResult>(
    `/accounts/${id}/reset-usage`,
    { method: "POST" },
  );
}

// ── Waitlist admin ──────────────────────────────────────────────

export interface WaitlistEntry {
  id: number;
  email: string;
  status: "waiting" | "invited" | "converted";
  invited_at: string | null;
  converted_at: string | null;
}

export interface WaitlistList {
  entries: WaitlistEntry[];
  total: number;
  waiting: number;
  invited: number;
  converted: number;
}

export interface WaitlistRelease {
  released: number;
  emails: string[];
}

const WAITLIST_PREFIX = "/api/v1/auth/waitlist";

async function waitlistFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${WAITLIST_PREFIX}${path}`, {
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
      if (typeof err?.detail === "string") detail = err.detail;
      else if (err?.detail?.message) detail = err.detail.message;
    } catch {
      // non-JSON error body
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function listWaitlist(): Promise<WaitlistList> {
  return waitlistFetch<WaitlistList>("/admin/list");
}

export function releaseInvites(count: number): Promise<WaitlistRelease> {
  return waitlistFetch<WaitlistRelease>("/admin/release", {
    method: "POST",
    body: JSON.stringify({ count }),
  });
}
