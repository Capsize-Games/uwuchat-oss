import { useCallback, useEffect, useRef, useState } from "react";
import LucideIcon from "@/components/shared/LucideIcon";
import { useEventBus } from "@/features/events/useEventBus";
import { EVENT_HEADLESSCODE_SESSION } from "@/features/events/types";
import StatusPill from "../StatusPill";
import {
  getHeadlesscodeSessionDetail,
  injectHeadlesscodeMessage,
  type HeadlesscodeSession,
  type HeadlesscodeSessionEvent,
} from "../../../api/headlesscode";
import styles from "./HeadlesscodeSessionCard.module.css";

const PENDING_REENABLE_MS = 45_000;

/** Map a headlesscode status onto a StatusPill icon/label pair. */
function statusDisplay(status: string | undefined): {
  iconName: string;
  label: string;
} {
  switch (status) {
    case "running":
      return { iconName: "loader", label: "Running" };
    case "completed":
      return { iconName: "circle-check", label: "Completed" };
    case "failed":
      return { iconName: "circle-stop", label: "Failed" };
    default:
      return { iconName: "circle-dot", label: status || "Starting" };
  }
}

/** Short human label for one event row in the live feed. */
function eventSummary(event: HeadlesscodeSessionEvent): string {
  const raw = event.raw_event ?? {};
  const kind = String(raw.chat_block_kind ?? raw.type ?? "").toUpperCase();
  const text = String(raw.content ?? raw.text ?? "");
  const head = text.length > 90 ? `${text.slice(0, 90)}…` : text;
  return head ? `${kind}: ${head}` : kind || "event";
}

interface Props {
  sessionId: string;
  projectName?: string;
  status?: string;
  taskDescription?: string;
}

export default function HeadlesscodeSessionCard({
  sessionId,
  projectName,
  status: initialStatus,
  taskDescription,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const [session, setSession] = useState<HeadlesscodeSession | null>(null);
  const [liveStatus, setLiveStatus] = useState<string | undefined>(
    initialStatus,
  );
  const [transcript, setTranscript] = useState<HeadlesscodeSessionEvent[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [injectText, setInjectText] = useState("");
  const [injectState, setInjectState] = useState<
    "idle" | "sending" | "pending" | "error"
  >("idle");
  const pendingTextRef = useRef<string | null>(null);
  const reenableTimer = useRef<number | null>(null);

  // Initial REST fetch — header + durable transcript.
  useEffect(() => {
    let alive = true;
    getHeadlesscodeSessionDetail(sessionId)
      .then((detail) => {
        if (!alive) return;
        setSession(detail.session);
        setLiveStatus(detail.session.status);
        setTranscript(detail.events);
      })
      .catch(() => {
        if (alive) setLoadError("Couldn't load session details.");
      });
    return () => {
      alive = false;
    };
  }, [sessionId]);

  useEffect(
    () => () => {
      if (reenableTimer.current != null) {
        window.clearTimeout(reenableTimer.current);
      }
    },
    [],
  );

  const confirmInjection = useCallback((raw: Record<string, unknown>) => {
    const pending = pendingTextRef.current;
    if (!pending) return;
    const body = String(raw.content ?? raw.text ?? "");
    if (raw.event_type === "message_injected" || body.includes(pending)) {
      pendingTextRef.current = null;
      if (reenableTimer.current != null) {
        window.clearTimeout(reenableTimer.current);
        reenableTimer.current = null;
      }
      setInjectState("idle");
    }
  }, []);

  // Live updates via the /api/v1/events WS channel (relay: issue #79).
  const handleSessionEvent = useCallback(
    (event: string, data: unknown) => {
      if (event !== EVENT_HEADLESSCODE_SESSION) return;
      const d = (data ?? {}) as Record<string, unknown>;
      const sid = d.session_id ?? d.headlesscode_session_id;
      if (!sid || String(sid) !== sessionId) return;
      if (typeof d.status === "string") setLiveStatus(d.status);
      if (Array.isArray(d.events)) {
        const fresh = d.events as Record<string, unknown>[];
        setTranscript((prev) => [
          ...prev,
          ...fresh.map((e, i) => ({
            id: prev.length + i,
            chat_block_kind: e.chat_block_kind
              ? String(e.chat_block_kind)
              : null,
            raw_event: e,
            created_at: e.created_at ? String(e.created_at) : null,
          })),
        ]);
        for (const e of fresh) confirmInjection(e);
      } else if (d.event_type === "message_injected") {
        confirmInjection(d);
      }
    },
    [sessionId, confirmInjection],
  );
  useEventBus([EVENT_HEADLESSCODE_SESSION], handleSessionEvent);

  const handleInject = useCallback(async () => {
    const text = injectText.trim();
    if (!text || injectState !== "idle") return;
    setInjectState("sending");
    try {
      await injectHeadlesscodeMessage(sessionId, text);
      pendingTextRef.current = text;
      setInjectText("");
      setInjectState("pending");
      // The relay confirm event is the source of truth; the timeout is
      // only a safety so the box is not bricked forever if the relay
      // is down (the pending chip keeps showing the unconfirmed state).
      reenableTimer.current = window.setTimeout(() => {
        setInjectState((s) => (s === "pending" ? "idle" : s));
      }, PENDING_REENABLE_MS);
    } catch {
      setInjectState("error");
    }
  }, [injectText, injectState, sessionId]);

  const status = statusDisplay(liveStatus);
  const injectDisabled = injectState === "sending" || injectState === "pending";

  return (
    <div className={styles.card}>
      <button
        type="button"
        className={styles.header}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <LucideIcon name="database-zap" size={16} className={styles.headerIcon} />
        <div className={styles.headerText}>
          <span className={styles.projectName}>
            {projectName ?? "Headlesscode session"}
          </span>
          {taskDescription && (
            <span className={styles.task}>{taskDescription}</span>
          )}
        </div>
        <StatusPill
          iconName={status.iconName}
          label={status.label}
          statusKey={`${sessionId}-${liveStatus ?? "unknown"}`}
          compact
        />
        <LucideIcon name={expanded ? "chevron-up" : "chevron-down"} size={16} />
      </button>

      {expanded && (
        <div className={styles.body}>
          <div className={styles.meta}>
            <span>session {sessionId.slice(0, 8)}</span>
            {session?.mode && <span>· mode {session.mode}</span>}
          </div>
          {loadError && <div className={styles.error}>{loadError}</div>}
          <div className={styles.feed}>
            {transcript.length === 0 && (
              <div className={styles.empty}>
                No activity yet — turns and tool calls will appear here.
              </div>
            )}
            {transcript.map((ev, i) => (
              <div key={`${ev.id}-${i}`} className={styles.eventRow}>
                {eventSummary(ev)}
              </div>
            ))}
          </div>
          <form
            className={styles.inject}
            onSubmit={(e) => {
              e.preventDefault();
              void handleInject();
            }}
          >
            <input
              className={styles.injectInput}
              value={injectText}
              onChange={(e) => setInjectText(e.target.value)}
              placeholder="Send a message to the coding agent…"
              disabled={injectDisabled}
              aria-label="Send a message to the coding agent"
            />
            <button
              type="submit"
              className={styles.injectBtn}
              disabled={injectDisabled || !injectText.trim()}
            >
              Send
            </button>
          </form>
          {injectState === "pending" && (
            <div className={styles.pending}>
              Message accepted — waiting for the agent to pick it up…
            </div>
          )}
          {injectState === "error" && (
            <div className={styles.error}>
              Could not send the message. Try again in a moment.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
