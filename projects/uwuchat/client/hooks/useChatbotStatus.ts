import { useState, useEffect, useCallback } from "react";
import {
  type ChatbotStatus,
  getChatbotStatus,
  blockChatbot,
  unblockChatbot,
} from "../api/chatbot-status";

const DEFAULT: ChatbotStatus = {
  is_online: true,
  offline_until: null,
  has_blocked_user: false,
  blocked_by_user: false,
};

export function useChatbotStatus(chatbotId: number | null): {
  status: ChatbotStatus;
  loading: boolean;
  blockBot: () => Promise<void>;
  unblockBot: () => Promise<void>;
  refresh: () => void;
  setBlocked: () => void;
} {
  const [status, setStatus] = useState<ChatbotStatus>(DEFAULT);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(() => {
    if (chatbotId === null) {
      setStatus(DEFAULT);
      return;
    }
    setLoading(true);
    getChatbotStatus(chatbotId)
      .then(setStatus)
      .catch(() => setStatus(DEFAULT))
      .finally(() => setLoading(false));
  }, [chatbotId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // React to server-pushed block/go-offline events in real time
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as {
        chatbotId?: number;
      } | undefined;
      if (detail?.chatbotId === chatbotId) {
        refresh();
      }
    };
    window.addEventListener("uwuchat:block-changed", handler);
    return () =>
      window.removeEventListener("uwuchat:block-changed", handler);
  }, [chatbotId, refresh]);

  const blockBot = useCallback(async () => {
    if (chatbotId === null) return;
    await blockChatbot(chatbotId);
    setStatus((s) => ({ ...s, blocked_by_user: true }));
    window.dispatchEvent(
      new CustomEvent("uwuchat:block-changed", { detail: { chatbotId } }),
    );
  }, [chatbotId]);

  const unblockBot = useCallback(async () => {
    if (chatbotId === null) return;
    await unblockChatbot(chatbotId);
    setStatus((s) => ({
      ...s,
      blocked_by_user: false,
      has_blocked_user: false,
    }));
    window.dispatchEvent(
      new CustomEvent("uwuchat:block-changed", { detail: { chatbotId } }),
    );
  }, [chatbotId]);

  const setBlocked = useCallback(() => {
    setStatus((s) => ({
      ...s,
      has_blocked_user: true,
      blocked_by_user: false,
    }));
  }, []);

  return { status, loading, blockBot, unblockBot, refresh, setBlocked };
}
