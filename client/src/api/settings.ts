import { request } from "./client-base";
import type { JsonObject } from "../types/api";

// ── Resource store ──
export async function getSingleton(resourceName: string) {
  const data = await request<{ record?: import("../types/api").ResourceRecord }>(
    "GET",
    `/api/v1/settings/resources/${resourceName}/singleton?create_if_missing=true`,
  );
  return (data.record ?? {}) as import("../types/api").ResourceRecord;
}

export async function updateSingleton(
  resourceName: string, values: JsonObject,
) {
  return request<import("../types/api").ResourceRecord>(
    "PUT", `/api/v1/settings/resources/${resourceName}/singleton`, { values },
  );
}

export async function queryResources(
  resource: string,
  filters?: Record<string, unknown>,
) {
  return request<{ records: import("../types/api").ResourceRecord[] }>(
    "POST",
    `/api/v1/settings/resources/${resource}/query`,
    filters ? { filters } : undefined,
  );
}

export async function queryFirstResource(
  resource: string,
  filters?: Record<string, unknown>,
  /** Column to sort descending by before taking the first match. */
  orderBy?: string,
) {
  const body: { filters?: Record<string, unknown>; order_by?: string } = {};
  if (filters) body.filters = filters;
  if (orderBy) body.order_by = orderBy;
  return request<{ record: import("../types/api").ResourceRecord }>(
    "POST",
    `/api/v1/settings/resources/${resource}/first`,
    Object.keys(body).length ? body : undefined,
  );
}

export async function createResource(
  resource: string,
  values: JsonObject,
) {
  return request<import("../types/api").ResourceRecord>(
    "POST",
    `/api/v1/settings/resources/${resource}`,
    { values },
  );
}

/**
 * Check creation quota for a resource without creating anything.
 * Lets callers fail fast on a rate limit before doing expensive work
 * (e.g. LLM calls) that a subsequent createResource() would reject anyway.
 * Throws the same RpcError (with .code) createResource() would throw.
 */
export async function checkResourceQuota(resource: string) {
  return request<{ ok?: boolean }>(
    "GET",
    `/api/v1/settings/resources/${resource}/quota`,
  );
}

export async function updateResource(
  resource: string,
  id: number,
  values: JsonObject,
) {
  return request<import("../types/api").ResourceRecord>(
    "PUT",
    `/api/v1/settings/resources/${resource}/${id}`,
    { values },
  );
}

export async function deleteResource(
  resource: string,
  id: number,
) {
  return request<{ deleted: boolean }>(
    "DELETE",
    `/api/v1/settings/resources/${resource}/${id}`,
  );
}

// ── Knowledge Base ──
export async function listKnowledgeBaseDocuments() {
  return request<{ documents: import("../types/api").DocumentRecord[] }>(
    "GET", "/api/v1/knowledge-base/documents",
  );
}

export async function toggleDocumentActive(docId: number) {
  return request<{ id: number; active: boolean }>(
    "PATCH", `/api/v1/knowledge-base/documents/${docId}/toggle-active`,
  );
}

export async function indexAllDocuments(force = false) {
  return request<{ status: string }>(
    "POST", "/api/v1/knowledge-base/documents/index-all",
    { force },
  );
}

export async function cancelIndexing() {
  return request<{ status: string }>(
    "POST", "/api/v1/knowledge-base/documents/index-cancel",
  );
}

// ── Privacy ──
export async function getPrivacySettings() {
  return request<{ services: Record<string, boolean> }>(
    "GET", "/api/v1/settings/privacy",
  );
}

export async function updatePrivacySettings(
  services: Record<string, boolean>,
) {
  return request<{ services: Record<string, boolean> }>(
    "PUT", "/api/v1/settings/privacy", { services },
  );
}

// ── Downloads ──
export async function startHuggingFaceDownload(
  repoId: string, modelType = "llm",
) {
  return request<import("../types/api").DownloadJobAccepted>(
    "POST", "/api/v1/downloads/huggingface",
    { repo_id: repoId, model_type: modelType },
  );
}
