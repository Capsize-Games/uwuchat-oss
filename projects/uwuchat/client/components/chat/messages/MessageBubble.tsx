import { useMemo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import ChatMarkdown from "@/components/markdown/ChatMarkdown";
import type { Message, ToolCallRecord } from "../../../types/api";
import { parseToolCallContent } from "@/components/chat/toolCallUtils";
import MessageAvatar from "./MessageAvatar";
import MessageActions from "./MessageActions";
import HeadlesscodeSessionCard from "./HeadlesscodeSessionCard";
import HostExecConsentCard, {
  parseHostExecConsent,
} from "./HostExecConsentCard";
import ToolCallWidget from "./ToolCallWidget";
import { useAdminCost } from "../../../context/AdminCostContext";
import { reportChatbotMessage } from "../../../api/chatbot-status";
import styles from "./MessageBubble.module.css";

function formatTime(isoStr?: string): string {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "";
    const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", hour12: true });
    const now = new Date();
    const isToday = d.getFullYear() === now.getFullYear()
      && d.getMonth() === now.getMonth()
      && d.getDate() === now.getDate();
    if (isToday) return time;
    const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return `${date} ${time}`;
  } catch { return ""; }
}

interface MessageBubbleProps {
  message: Message; botName?: string; botEmoji?: string; userName?: string;
  userAvatarImage?: string | null; messageIndex?: number; chatbotId?: number | null;
  onDelete?: (index: number) => void; onCopy?: (content: string) => void;
  onPlay?: (content: string) => void; onAvatarClick?: () => void;
}

export default function MessageBubble({
  message, botName = "AI", botEmoji, userName = "You", userAvatarImage,
  messageIndex, chatbotId, onDelete, onAvatarClick,
}: MessageBubbleProps) {
  const { t } = useTranslation();
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const { isSuperuser, turnAnnotations } = useAdminCost();

  // Parse the assistant narration into alternating text/tool segments so
  // ToolCallWidgets render INLINE where each tool ran, not stacked at the
  // top.  Resolution order:
  //   1. tool_events with a `position` (live frame stamp or persisted) —
  //      split content at each offset.
  //   2. raw <tool_call> XML markers in content (server keeps them for
  //      reload) — parseToolCallContent yields the block spans.
  //   3. plain tool_events with no position — append after the narration.
  const contentSegments = useMemo(() => {
    if (isUser || isSystem) return null;
    const events = message.tool_events ?? [];
    const segments: {
      text: string;
      tool?: ToolCallRecord;
      key: string;
    }[] = [];
    const positioned = events.filter((ev) => typeof ev.position === "number");
    if (positioned.length > 0) {
      const ordered = [...positioned].sort(
        (a, b) => (a.position ?? 0) - (b.position ?? 0),
      );
      let cursor = 0;
      ordered.forEach((ev, i) => {
        const pos = Math.max(0, Math.min(ev.position ?? 0, message.content.length));
        if (pos > cursor) {
          segments.push({ text: message.content.slice(cursor, pos), key: `t-${i}` });
        }
        segments.push({ text: "", tool: ev, key: `w-${i}` });
        cursor = pos;
      });
      if (cursor < message.content.length) {
        segments.push({ text: message.content.slice(cursor), key: "tail" });
      }
      return segments;
    }
    const parsed = parseToolCallContent(message.content);
    if (parsed.toolCalls.length === 0) {
      // No inline markers and no positions — keep everything visible.
      segments.push({ text: message.content, key: "text" });
      events.forEach((ev, i) => {
        segments.push({ text: "", tool: ev, key: `w-${i}` });
      });
      return segments;
    }
    let cursor = 0;
    parsed.toolCalls.forEach((tc, i) => {
      const text = message.content.slice(cursor, tc.startIndex);
      if (text) segments.push({ text, key: `t-${i}` });
      const match = events.find(
        (ev) => ev.tool_name === tc.functionName && ev.status !== "starting",
      );
      segments.push({
        text: "",
        tool: match ?? {
          tool_id: `xml-${i}`,
          tool_name: tc.functionName,
          status: "completed",
          query: Object.values(tc.parameters)[0] ?? undefined,
          details: null,
        },
        key: `w-${i}`,
      });
      cursor = tc.endIndex;
    });
    const tail = message.content.slice(cursor);
    if (tail) segments.push({ text: tail, key: "tail" });
    return segments;
  }, [isUser, isSystem, message.content, message.tool_events]);

  const consentRequest = useMemo(
    () => (!isUser && !isSystem ? parseHostExecConsent(message.content) : null),
    [isUser, isSystem, message.content],
  );

  const annotation = useMemo(() => {
    if (!isSuperuser || isUser || isSystem || !message.call_chain_id) return null;
    return turnAnnotations?.annotations[message.call_chain_id] ?? null;
  }, [isSuperuser, isUser, isSystem, message.call_chain_id, turnAnnotations]);

  const handleReport = useCallback(
    (reason: string, detail: string) => {
      if (chatbotId == null) return;
      reportChatbotMessage(chatbotId, { message_id: message.id, reason, detail }).catch(() => {});
    }, [chatbotId, message.id],
  );

  const handleInspect = () => {
    const callChainId = annotation?.call_chain_id ?? message.call_chain_id ?? undefined;
    window.dispatchEvent(new CustomEvent("airunner:inspect-turn", {
      detail: { turnId: message.id, callChainId, timestamp: message.created_at ?? undefined },
    }));
  };

  // Host-command consent card — the tool result carries a consent marker.
  if (consentRequest) {
    return (
      <div className="message-bubble">
        <div className={`w-100 ${styles.bubbleBot}`}>
          <MessageAvatar isUser={false} label={botName} emoji={botEmoji}
            onClick={onAvatarClick} />
          <HostExecConsentCard
            command={consentRequest.command}
            group={consentRequest.group}
          />
          {message.created_at && (
            <div className={styles.footerRow}>
              <div className={styles.timestamp}>{formatTime(message.created_at)}</div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div className="message-bubble">
        <div className={`w-100 ${styles.systemWrap}`}>
          <div className={styles.systemLabel}>{t("chat.message.system_label")}</div>
          <div className={styles.messageContent}><ChatMarkdown content={message.content || ""} /></div>
          {message.created_at && (
            <div className={styles.timestampRow}>
              <div className={styles.timestamp}>{formatTime(message.created_at)}</div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Headlesscode session card — the card entry carries a session id,
  // so this message renders the collapsible live card, not markdown.
  if (message.headlesscode_session_id) {
    return (
      <div className="message-bubble">
        <div className={`w-100 ${styles.bubbleBot}`}>
          <MessageAvatar isUser={false} label={botName} emoji={botEmoji}
            onClick={onAvatarClick} />
          <HeadlesscodeSessionCard
            sessionId={message.headlesscode_session_id}
            projectName={message.headlesscode_project_name}
            status={message.headlesscode_status}
            taskDescription={message.headlesscode_task}
          />
          {message.created_at && (
            <div className={styles.footerRow}>
              <div className={styles.timestamp}>{formatTime(message.created_at)}</div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="message-bubble">
      <div className={`w-100 ${isUser ? styles.bubbleUser : styles.bubbleBot}`}>
        <MessageAvatar isUser={isUser} label={isUser ? userName : botName}
          emoji={isUser ? undefined : botEmoji} avatarImage={isUser ? userAvatarImage : undefined}
          onClick={isUser ? undefined : onAvatarClick}
          kaomoji={!isUser ? message.bot_mood_kaomoji : undefined}
          kaomojiTitle={!isUser ? message.bot_mood : undefined} />
        <div className={styles.messageContent}>
          {isUser || !contentSegments ? (
            <ChatMarkdown content={message.content || ""} />
          ) : (
            contentSegments.map((seg) =>
              seg.tool ? (
                <ToolCallWidget key={seg.key} tool={seg.tool} />
              ) : (
                <ChatMarkdown key={seg.key} content={seg.text} />
              ),
            )
          )}
        </div>
        <MessageActions isUser={isUser} content={message.content} onReport={handleReport}
          onDelete={onDelete != null && messageIndex != null && chatbotId != null ? () => onDelete(messageIndex) : undefined} />
        <div className={styles.footerRow}>
          {isSuperuser && !isUser && message.call_chain_id && (
            <button onClick={handleInspect} className={styles.inspectBtn}>
              {annotation
                ? annotation.cost_usd > 0
                  ? `~$${annotation.cost_usd.toFixed(6)} · ${annotation.input_tokens.toLocaleString()}in / ${annotation.output_tokens.toLocaleString()}out`
                  : `~${annotation.input_tokens.toLocaleString()}in / ${annotation.output_tokens.toLocaleString()}out`
                : t("chat.message.inspect_flow")}
            </button>
          )}
          {message.created_at && <div className={styles.timestamp}>{formatTime(message.created_at)}</div>}
        </div>
      </div>
    </div>
  );
}
