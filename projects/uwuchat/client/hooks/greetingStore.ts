/**
 * Module-level store for pending bot greetings.
 *
 * useUwuCreation writes here when the "ready" event arrives, before
 * calling onConnected.
 * ChatView reads here after the thread loads to inject the greeting,
 * avoiding the React stale-closure / render-ordering race that window
 * events can't reliably solve.
 */

interface PendingGreeting {
  greeting: string;
  name: string;
}

const _store = new Map<number, PendingGreeting>();

export const greetingStore = {
  set(chatbotId: number, greeting: string, name: string): void {
    _store.set(chatbotId, { greeting, name });
  },
  take(chatbotId: number): PendingGreeting | undefined {
    const entry = _store.get(chatbotId);
    _store.delete(chatbotId);
    return entry;
  },
};
