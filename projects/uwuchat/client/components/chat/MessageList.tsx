import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import Alert from "react-bootstrap/Alert";
import type { Message } from "../../types/api";
import { useVirtualMessages } from "@/hooks/useVirtualMessages";
import ChatLoadingSkeleton from "./messages/ChatLoadingSkeleton";
import EmptyPlaceholder from "./messages/EmptyPlaceholder";
import MessageBubble from "./messages/MessageBubble";
import { InlineFlowNodes } from "./messages/InlineFlowNodes";
import { InlineEventNodes } from "./messages/InlineEventNodes";
import type { ConversationEvent } from "../../api/admin";
import type { ConversationFlowResponse } from "@extensions/conversation_inspector/client/api";
import type { CallChainDetail } from "../../types/pipeline";
import { generateTurnMermaid } from "./InspectionMermaid";
import styles from "./MessageList.module.css";

function formatSessionGap(isoStr: string): string {
  try {
    const d = new Date(isoStr); if (isNaN(d.getTime())) return "";
    const today = new Date(); const todayStr = today.toDateString();
    if (d.toDateString() === todayStr) return "Earlier today";
    const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    const diffMs = today.getTime() - d.getTime(); if (diffMs <= 0) return "Just now";
    const diffDays = Math.floor(diffMs / 86_400_000);
    if (diffDays < 7) return `${diffDays} days ago`;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch { return ""; }
}

function formatDateLabel(isoStr: string): string {
  try {
    const d = new Date(isoStr); if (isNaN(d.getTime())) return "";
    const today = new Date(); const yesterday = new Date(today); yesterday.setDate(today.getDate() - 1);
    if (d.toDateString() === today.toDateString()) return "Today";
    if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
    return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  } catch { return ""; }
}

function dividerBefore(messages: Message[], idx: number): { label: string } | null {
  if (idx === 0) return null;
  const cur = messages[idx]; const curSid = cur.session_id ?? null;
  const curDate = cur.created_at ? new Date(cur.created_at).toDateString() : null;
  for (let p = idx - 1; p >= 0; p--) {
    const prev = messages[p]; const prevSid = prev.session_id ?? null;
    const prevDate = prev.created_at ? new Date(prev.created_at).toDateString() : null;
    if (curSid !== null && prevSid !== curSid && cur.session_started_at) return { label: formatSessionGap(cur.session_started_at) };
    if (curDate !== null && prevDate !== curDate && cur.created_at) { const label = formatDateLabel(cur.created_at); if (label) return { label }; }
    if (prevSid !== null || prevDate !== null) return null;
  }
  return null;
}

export default function MessageList({
  messages, onCopyMessage, onPlayMessage, onDeleteMessage, chatbotId, botName, botEmoji,
  userName, userAvatarImage, containerRef, inspectionEnabled = false, flowData = null,
  flowLoading = false, costMap = {}, costLoading = false, events = [], onSendOpener,
  onAvatarClick, scrollToBottomRef, loading = false, error = null, onRetryConversation,
}: {
  messages: Message[]; onCopyMessage?: (c: string) => void; onPlayMessage?: (c: string) => void;
  onDeleteMessage?: (i: number, chatbotId: number) => void; chatbotId?: number | null;
  botName?: string; botEmoji?: string; onSendOpener?: (t: string) => void; onAvatarClick?: () => void;
  userName?: string; userAvatarImage?: string | null;
  containerRef: React.RefObject<HTMLDivElement | null>;
  scrollToBottomRef?: React.MutableRefObject<() => void>;
  inspectionEnabled?: boolean; flowData?: ConversationFlowResponse | null; flowLoading?: boolean;
  costMap?: Record<string, CallChainDetail>; costLoading?: boolean; events?: ConversationEvent[];
  loading?: boolean; error?: Error | null; onRetryConversation?: () => void;
}) {
  const { t } = useTranslation();
  const [copiedTurn, setCopiedTurn] = useState<number | null>(null);

  const handleCopyTurn = useCallback((turn: any, costDetail: CallChainDetail | null, turnNum: number) => {
    const mermaid = generateTurnMermaid(turn, costDetail, turnNum);
    navigator.clipboard?.writeText(mermaid).then(() => { setCopiedTurn(turnNum); setTimeout(() => setCopiedTurn(null), 1500); }).catch(() => {});
  }, []);

  const { visibleRange, paddingTop, paddingBottom, measureRef, scrollToBottom } = useVirtualMessages({ messageCount: messages.length, containerRef });
  useEffect(() => { if (scrollToBottomRef) scrollToBottomRef.current = scrollToBottom; }, [scrollToBottom, scrollToBottomRef]);

  if (messages.length === 0) {
    if (loading) {
      return <ChatLoadingSkeleton />;
    }
    if (error) {
      return (
        <div className="d-flex flex-column align-items-center justify-content-center py-5">
          <Alert variant="warning" className="mb-3">
            <p className="mb-2">
              {t("chat.error.load_failed", "Couldn't load your conversation.")}
            </p>
            {onRetryConversation && (
              <button
                onClick={onRetryConversation}
                className="btn btn-sm btn-outline-warning"
                type="button"
              >
                {t("chat.error.retry", "Retry")}
              </button>
            )}
          </Alert>
        </div>
      );
    }
    return <EmptyPlaceholder emoji={botEmoji} greeting={botName ? t("chat.empty_placeholder.greeting_with_name", { name: botName }) : undefined} botName={botName} onProfileClick={onAvatarClick} onSelectOpener={onSendOpener} />;
  }

  const items: React.ReactNode[] = [];
  const contentToTurn = new Map<string, unknown>();
  if (inspectionEnabled && flowData) {
    for (const turn of flowData.turns) {
      const um = turn.user_message;
      if (um && typeof um === "object") { const c = String((um as Record<string, unknown>).content || "").slice(0, 80).trim(); if (c) contentToTurn.set(c, turn); }
    }
  }

  let turnNumber = 0;
  if (visibleRange) {
    const [start, end] = visibleRange;
    for (let i = 0; i < start; i++) { if (messages[i]?.role === "user") turnNumber++; }

    const leadingDivider = dividerBefore(messages, start);
    if (leadingDivider) {
      items.push(<div key="divider-lead" className={styles.divider}><span className={styles.dividerLineLeft} /><span className={styles.dividerLabel}>{leadingDivider.label}</span><span className={styles.dividerLineRight} /></div>);
    }

    for (let i = start; i <= end; i++) {
      const msg = messages[i];
      if (i > start) { const div = dividerBefore(messages, i); if (div) items.push(<div key={`divider-${i}`} className={styles.divider}><span className={styles.dividerLineLeft} /><span className={styles.dividerLabel}>{div.label}</span><span className={styles.dividerLineRight} /></div>); }
      const handleDelete = onDeleteMessage != null && chatbotId != null ? (idx: number) => onDeleteMessage(idx, chatbotId) : undefined;
      const isUserMsg = msg.role === "user"; if (isUserMsg) turnNumber++;
      let turn: any = null;
      if (isUserMsg && inspectionEnabled && flowData) { const key = (msg.content || "").slice(0, 80).trim(); turn = contentToTurn.get(key) || null; }
      let botCallChainId: string | null = null;
      if (isUserMsg && inspectionEnabled) { for (let j = i + 1; j <= end; j++) { if (messages[j]?.role === "assistant" && messages[j]?.call_chain_id) { botCallChainId = messages[j].call_chain_id!; break; } } }
      const hasFlow = turn && turn.flow_steps && turn.flow_steps.length > 0;
      const costDetail = botCallChainId ? costMap[botCallChainId] : null;
      const turnCost = costDetail?.total_cost_usd;
      const inTurn = isUserMsg || (i > start && messages[i - 1]?.role !== "user" && messages[i]?.role === "assistant");

      items.push(
        <div key={`msg-${i}`} ref={measureRef(i)} style={inspectionEnabled && hasFlow ? {
          borderLeft: isUserMsg ? "2px solid rgba(76,175,80,0.4)" : (inTurn ? "2px solid rgba(76,175,80,0.15)" : "none"),
          paddingLeft: isUserMsg ? 10 : (inTurn ? 10 : 0),
        } : undefined}>
          {isUserMsg && hasFlow && inspectionEnabled && (
            <div className={styles.turnLabel}>
              <span>{t("chat.message.turn")} {turnNumber}</span>
              {turnCost != null && turnCost > 0 && <span className={styles.turnCost}>${turnCost.toFixed(6)}</span>}
            </div>
          )}
          {isUserMsg && inspectionEnabled && hasFlow && <InlineFlowNodes steps={turn.flow_steps} position="pre" costDetail={costDetail} />}
          <MessageBubble message={msg} onCopy={onCopyMessage} onPlay={onPlayMessage} botName={botName} botEmoji={botEmoji}
            userName={userName} userAvatarImage={userAvatarImage} messageIndex={i} chatbotId={chatbotId} onDelete={handleDelete} onAvatarClick={onAvatarClick} />
          {isUserMsg && inspectionEnabled && hasFlow && <InlineFlowNodes steps={turn.flow_steps} position="mid" costDetail={costDetail} />}
          {isUserMsg && inspectionEnabled && hasFlow && (
            <div className={styles.copyBar}>
              <button onClick={(e) => { e.stopPropagation(); handleCopyTurn(turn, costDetail, turnNumber); }}
                className={copiedTurn === turnNumber ? styles.copyBtnActive : styles.copyBtnIdle}
                title="Copy the flow diagram for this turn as a Mermaid markdown diagram">
                {copiedTurn === turnNumber ? t("chat.message.copied_mermaid") : t("chat.message.copy_mermaid")}
              </button>
            </div>
          )}
          {isUserMsg && inspectionEnabled && events.length > 0 && (
            <InlineEventNodes events={events} afterTimestamp={msg.created_at || undefined}
              beforeTimestamp={messages[i + 1]?.role === "assistant" ? messages[i + 1]?.created_at || undefined : undefined} />
          )}
        </div>,
      );
    }
  }

  return (
    <div className="d-flex flex-column">
      {/* eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop */}
      {paddingTop > 0 && <div className={styles.spacer} style={{ height: paddingTop }} />}
      {items}
      {/* eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop */}
      {paddingBottom > 0 && <div className={styles.spacer} style={{ height: paddingBottom }} />}
    </div>
  );
}
