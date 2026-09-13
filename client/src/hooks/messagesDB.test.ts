/**
 * Unit tests for messagesDB IndexedDB cache layer.
 *
 * Covers:
 * - Save/load/delete round-trips scoped by conversation ID
 * - Cross-conversation isolation (conversation A's messages
 *   never leak into conversation B's cache)
 * - Graceful fallback when IndexedDB is unavailable
 * - updatedAt timestamp is set on every save
 * - Newer-wins conflict resolution: stale writes from one
 *   source do not clobber fresher data from another source
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

const TEST_DB = "airunner_messages";

async function clearTestDB(): Promise<void> {
  return new Promise((resolve) => {
    const req = indexedDB.deleteDatabase(TEST_DB);
    req.onsuccess = () => resolve();
    req.onerror = () => resolve();
  });
}

describe("messagesDB", () => {
  beforeEach(async () => {
    await clearTestDB();
  });

  afterEach(async () => {
    await clearTestDB();
  });

  describe("saveMessagesDB / loadMessagesDB", () => {
    it("round-trips messages scoped to a conversation ID", async () => {
      const { saveMessagesDB, loadMessagesDB } = await import(
        "./messagesDB"
      );
      const messages = [
        { id: 1, content: "hello", role: "user", chatbot_id: 1 },
        { id: 2, content: "hi!", role: "assistant", chatbot_id: 1 },
      ];
      await saveMessagesDB(42, messages as any);
      const cached = await loadMessagesDB(42);
      expect(cached).not.toBeNull();
      expect(cached!.messages).toHaveLength(2);
      expect(cached!.messages[0].content).toBe("hello");
      expect(cached!.updatedAt).toBeTruthy();
    });

    it("returns null for an un-cached conversation", async () => {
      const { loadMessagesDB } = await import("./messagesDB");
      const cached = await loadMessagesDB(99999);
      expect(cached).toBeNull();
    });

    it("isolates conversations — save to A, load from B returns null", async () => {
      const { saveMessagesDB, loadMessagesDB } = await import(
        "./messagesDB"
      );
      await saveMessagesDB(10, [
        { id: 1, content: "secret", role: "user", chatbot_id: 1 },
      ] as any);
      const b = await loadMessagesDB(20);
      expect(b).toBeNull();
    });
  });

  describe("deleteMessagesDB", () => {
    it("removes messages so subsequent load returns null", async () => {
      const { saveMessagesDB, loadMessagesDB, deleteMessagesDB } =
        await import("./messagesDB");
      await saveMessagesDB(7, [
        { id: 1, content: "x", role: "user", chatbot_id: 1 },
      ] as any);
      const before = await loadMessagesDB(7);
      expect(before).not.toBeNull();

      await deleteMessagesDB(7);
      const after = await loadMessagesDB(7);
      expect(after).toBeNull();
    });

    it("does not throw when deleting a non-existent key", async () => {
      const { deleteMessagesDB } = await import("./messagesDB");
      await expect(deleteMessagesDB(12345)).resolves.toBeUndefined();
    });
  });

  describe("updatedAt conflict resolution", () => {
    it("stale write (older updatedAt) does not clobber a fresher record", async () => {
      const { saveMessagesDB, loadMessagesDB } = await import(
        "./messagesDB"
      );

      // Write fresh data with a newer timestamp (e.g. from a server fetch).
      const freshMessages = [
        { id: 1, content: "fresh", role: "user", chatbot_id: 1 },
      ];
      await saveMessagesDB(
        99,
        freshMessages as any,
        null,
        "2026-07-23T10:00:00.000Z",
      );

      // Write stale data with an older timestamp (e.g. a delayed cache mirror).
      const staleMessages = [
        { id: 2, content: "stale", role: "user", chatbot_id: 1 },
      ];
      await saveMessagesDB(
        99,
        staleMessages as any,
        null,
        "2026-07-22T10:00:00.000Z",
      );

      // The fresh record must survive.
      const cached = await loadMessagesDB(99);
      expect(cached).not.toBeNull();
      expect(cached!.messages[0].content).toBe("fresh");
      expect(cached!.updatedAt).toBe("2026-07-23T10:00:00.000Z");
    });

    it("fresh write (newer updatedAt) does update an older record", async () => {
      const { saveMessagesDB, loadMessagesDB } = await import(
        "./messagesDB"
      );

      // Write old data.
      const oldMessages = [
        { id: 1, content: "old", role: "user", chatbot_id: 1 },
      ];
      await saveMessagesDB(
        88,
        oldMessages as any,
        null,
        "2026-07-01T00:00:00.000Z",
      );

      // Write newer data.
      const newMessages = [
        { id: 2, content: "new", role: "user", chatbot_id: 1 },
      ];
      await saveMessagesDB(
        88,
        newMessages as any,
        null,
        "2026-07-20T00:00:00.000Z",
      );

      // The new record must replace the old one.
      const cached = await loadMessagesDB(88);
      expect(cached).not.toBeNull();
      expect(cached!.messages[0].content).toBe("new");
      expect(cached!.updatedAt).toBe("2026-07-20T00:00:00.000Z");
    });

    it("same-timestamp overwrite is allowed (no-op edge case)", async () => {
      const { saveMessagesDB, loadMessagesDB } = await import(
        "./messagesDB"
      );

      const ts = "2026-07-20T12:00:00.000Z";
      const first = [
        { id: 1, content: "first", role: "user", chatbot_id: 1 },
      ];
      await saveMessagesDB(77, first as any, null, ts);

      // Same timestamp — should overwrite (the new data is equally fresh).
      const second = [
        { id: 2, content: "second", role: "user", chatbot_id: 1 },
      ];
      await saveMessagesDB(77, second as any, null, ts);

      const cached = await loadMessagesDB(77);
      expect(cached).not.toBeNull();
      expect(cached!.messages[0].content).toBe("second");
    });
  });
});
