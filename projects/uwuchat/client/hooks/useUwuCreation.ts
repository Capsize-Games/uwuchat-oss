import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { queryResources, updateResource } from "@/api/settings";
import { request } from "@/api/client-base";
import { useEventBus } from "@/features/events/useEventBus";
import { EVENT_UWU_CREATION } from "@/features/events/types";
import { greetingStore } from "./greetingStore";

export interface UwuReadyChatbot {
  chatbotId: number;
  name: string;
}

interface UwuCreationPayload {
  chatbot_id: number;
  status: "ready" | "failed";
  name?: string;
  greeting?: string;
}

const ERROR_CODE_KEYS: Record<string, string> = {
  rate_limit_exceeded: "chat.choice_modal.rate_limit_exceeded",
};

function describeError(err: unknown, t: (key: string) => string): string {
  const code = (err as { code?: string } | undefined)?.code;
  if (code && ERROR_CODE_KEYS[code]) return t(ERROR_CODE_KEYS[code]);
  return err instanceof Error ? err.message : String(err);
}

/**
 * Durable, resumable random-chatbot creation.
 *
 * Replaces the old client-driven ``useConnectRandom`` chain: creation
 * now runs server-side (see ``random_chatbot_tasks.py``), so
 * ``connecting`` is derived from server state — resumed on mount from
 * the chatbot list and kept live via the ``uwu_creation`` WS event —
 * instead of local ``useState`` that reset on reload. ``readyChatbot``
 * drives a one-time "your UwU is ready" notification; dismissing it
 * (``acknowledgeReady``) is what actually switches the app into the
 * new chatbot, mirroring the old flow's ``onConnected`` timing.
 */
export function useUwuCreation(onReady: (id: number) => void) {
  const { t } = useTranslation();
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [readyChatbot, setReadyChatbot] = useState<UwuReadyChatbot | null>(
    null,
  );
  const generatingIdRef = useRef<number | null>(null);

  // Resume on mount: a generation may have been kicked off in a
  // previous tab/session and still be running, or may have finished
  // ("ready", unacknowledged) while this tab was closed.
  useEffect(() => {
    let cancelled = false;
    queryResources("Chatbot", { deleted: false })
      .then((res) => {
        if (cancelled) return;
        const records = (res?.records ?? []) as Array<{
          id: number;
          name?: string;
          creation_status?: string;
        }>;
        const generating = records.find(
          (r) => r.creation_status === "generating"
            || r.creation_status === "pending",
        );
        if (generating) {
          generatingIdRef.current = generating.id;
          setConnecting(true);
        }
        const ready = records.find((r) => r.creation_status === "ready");
        if (ready) {
          setReadyChatbot({ chatbotId: ready.id, name: ready.name ?? "" });
        }
      })
      .catch(() => { /* best-effort resume; WS/next mount recovers */ });
    return () => { cancelled = true; };
  }, []);

  const handleCreationEvent = useCallback(
    (_event: string, data: unknown) => {
      const payload = data as UwuCreationPayload;
      if (
        generatingIdRef.current !== null
        && payload.chatbot_id !== generatingIdRef.current
      ) {
        return;
      }
      generatingIdRef.current = null;
      setConnecting(false);
      if (payload.status === "ready") {
        if (payload.greeting) {
          greetingStore.set(
            payload.chatbot_id, payload.greeting, payload.name ?? "",
          );
        }
        setReadyChatbot({
          chatbotId: payload.chatbot_id,
          name: payload.name ?? "",
        });
      } else {
        setError(t("sidebar.generation_failed"));
      }
    },
    [t],
  );
  useEventBus([EVENT_UWU_CREATION], handleCreationEvent);

  const connectRandom = useCallback(async () => {
    if (connecting) return;
    setConnecting(true);
    setError(null);
    try {
      const res = await request<{
        chatbot_id: number;
        creation_status: string;
      }>("POST", "/api/v1/llm/create-random-chatbot");
      generatingIdRef.current = res.chatbot_id;
    } catch (err) {
      setConnecting(false);
      setError(describeError(err, t));
    }
  }, [connecting, t]);

  const acknowledgeReady = useCallback(() => {
    if (!readyChatbot) return;
    const { chatbotId } = readyChatbot;
    setReadyChatbot(null);
    onReady(chatbotId);
    updateResource("Chatbot", chatbotId, {
      creation_status: "acknowledged",
    }).catch(() => { /* best-effort; worst case the notice can reappear */ });
  }, [readyChatbot, onReady]);

  return { connectRandom, connecting, error, readyChatbot, acknowledgeReady };
}
