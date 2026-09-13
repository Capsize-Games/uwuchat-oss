// ── Messages Cache (IndexedDB) ───────────────────────────────────────────
// Individual conversation messages are too valuable to lose on reload.
// Mirror them in IndexedDB so the chat view always has something to
// show immediately, even before the server round-trip completes.
//
// Each cached entry is keyed by conversation ID and carries the full
// message list plus the current mood (kaomoji/emoji) so the chat
// restores its visual state instantly.

import type { Message } from "../types/api";

const DB_NAME = "airunner_messages";
const STORE = "messages";
const DB_VERSION = 1;

interface CachedMessages {
  /** Conversation ID used as the key. */
  conversationId: number;
  /** Serialized message list. */
  messages: Message[];
  /** Current mood at the time of cache (kaomoji / emoji). */
  mood: {
    mood?: string;
    emoji?: string;
    kaomoji?: string;
  } | null;
  /** ISO-8601 timestamp of last write. */
  updatedAt: string;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: "conversationId" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Persist messages for one conversation to IndexedDB.

 * Respects the "newer wins" storage convention: callers SHOULD pass
 *  ``updatedAt`` with the timestamp of the server data being saved
 *  (typically the most recent message's ``created_at``).  When
 *  omitted, the current time is used — this is fine for appends
 *  where the data is fresh, but data sourced from a server response
 *  should carry the server timestamp so a concurrent server fetch
 *  doesn't get clobbered by a stale cached write.
 */
export async function saveMessagesDB(
  conversationId: number,
  messages: Message[],
  mood: CachedMessages["mood"] = null,
  updatedAt?: string,
): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);

    // Check for an existing record — keep the newer one.
    const existing = await new Promise<CachedMessages | undefined>(
      (resolve, reject) => {
        const req = store.get(conversationId);
        req.onsuccess = () => resolve(req.result as CachedMessages | undefined);
        req.onerror = () => reject(req.error);
      },
    );

    const incomingAt = updatedAt || new Date().toISOString();
    if (existing && existing.updatedAt > incomingAt) {
      // Existing record is newer — don't overwrite with stale data.
      tx.abort();
      db.close();
      return;
    }

    const record: CachedMessages = {
      conversationId,
      messages,
      mood,
      updatedAt: incomingAt,
    };
    store.put(record);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* IndexedDB unavailable — messages won't survive this reload. */
  }
}

/** Load cached messages for one conversation, or null if none. */
export async function loadMessagesDB(
  conversationId: number,
): Promise<CachedMessages | null> {
  try {
    const db = await openDB();
    const record = await new Promise<CachedMessages | undefined>(
      (resolve, reject) => {
        const tx = db.transaction(STORE, "readonly");
        const req = tx.objectStore(STORE).get(conversationId);
        req.onsuccess = () => resolve(req.result as CachedMessages | undefined);
        req.onerror = () => reject(req.error);
      },
    );
    db.close();
    return record ?? null;
  } catch {
    return null;
  }
}

/** Clear ALL cached messages from IndexedDB. Called on logout and
 * account deletion to prevent stale data from rendering when a
 * different account logs in on the same machine, and to complete
 * GDPR erasure on the client side. */
export async function clearMessagesDB(): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* IndexedDB unavailable. */
  }
}

/** Delete cached messages for one conversation. */
export async function deleteMessagesDB(
  conversationId: number,
): Promise<void> {
  try {
    const db = await openDB();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(conversationId);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  } catch {
    /* IndexedDB unavailable. */
  }
}
