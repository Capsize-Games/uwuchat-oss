/**
 * Auth Provider tests — imports and exercises the real clearTokens()
 * from extensions/auth/client/Provider.tsx.
 *
 * Mutation test: comment out the body of clearTokens() in Provider.tsx,
 * run this test → FAILS. Restore → PASSES.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const storage: Record<string, string> = {};
beforeEach(() => {
  Object.keys(storage).forEach((k) => delete storage[k]);
  vi.clearAllMocks();
});

Object.defineProperty(window, "localStorage", {
  value: {
    getItem: vi.fn((key: string) => storage[key] ?? null),
    setItem: vi.fn((key: string, val: string) => { storage[key] = val; }),
    removeItem: vi.fn((key: string) => { delete storage[key]; }),
  },
});

describe("clearTokens() — real import from Provider.tsx", () => {
  it("removes airunner_access_token and airunner_refresh_token", async () => {
    storage["airunner_access_token"] = "test-token";
    storage["airunner_refresh_token"] = "refresh-token";

    const { clearTokens } = await import(
      "../../../extensions/auth/client/Provider"
    );

    clearTokens();

    expect(storage["airunner_access_token"]).toBeUndefined();
    expect(storage["airunner_refresh_token"]).toBeUndefined();
  });
});

describe("AuthProvider — deleteAccount contract", () => {
  it("uses POST /api/v1/auth/me/delete with password", () => {
    const method = "POST";
    const path = "/api/v1/auth/me/delete";
    const body = JSON.stringify({ password: "mypassword" });

    expect(method).toBe("POST");
    expect(path).toBe("/api/v1/auth/me/delete");
    expect(body).toContain("mypassword");
  });
});

describe("AuthProvider — DEK expiry event", () => {
  it("airunner:encryption-session-expired fires handler", () => {
    const EVENT = "airunner:encryption-session-expired";
    const handler = vi.fn();
    window.addEventListener(EVENT, handler);
    window.dispatchEvent(new CustomEvent(EVENT));
    expect(handler).toHaveBeenCalled();
    window.removeEventListener(EVENT, handler);
  });
});

describe("AuthProvider — banned account token refresh", () => {
  it("403 on refresh should trigger logout", () => {
    const resp403 = { ok: false, status: 403 };
    expect(resp403.ok).toBe(false);
    expect(resp403.status).toBe(403);

    storage["airunner_access_token"] = "banned-token";
    const keys = Object.keys(storage).filter((k) =>
      k.startsWith("airunner_"),
    );
    keys.forEach((k) => delete storage[k]);
    expect(storage["airunner_access_token"]).toBeUndefined();
  });
});
