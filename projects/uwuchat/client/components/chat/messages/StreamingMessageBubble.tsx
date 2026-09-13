import { useMemo } from "react";
import MessageAvatar from "./MessageAvatar";
import StatusPill from "../StatusPill";
import ToolCallWidget from "./ToolCallWidget";
import type { ToolCallRecord } from "../../../types/api";
import styles from "./StreamingMessageBubble.module.css";

interface ActiveStatus {
  statusKey: string;
  iconName: string;
  label: string;
}

interface Props {
  content: string;
  botName?: string;
  botEmoji?: string;
  activeStatus?: ActiveStatus | null;
  /** Completed/error tool results captured so far this stream — rendered
   *  INLINE at their narration position as the stream reveals past them. */
  toolEvents?: ToolCallRecord[];
}

interface Segment {
  text: string;
  tool?: ToolCallRecord;
  key: string;
}

/** Split narration at each tool event's position, interleaving the
 *  collapsible widget inline.  Events without a position (or with no
 *  markers at all) fall back to after-text placement so nothing is lost. */
function interleaveSegments(content: string, toolEvents: ToolCallRecord[]): Segment[] {
  const segments: Segment[] = [];
  // Only render a widget once the reveal has passed its position — the
  // widget appears exactly where the narration reached that tool call,
  // matching professional inline tool-call UIs.  Events without a
  // position (e.g. live frames before any narration, or reloads without
  // server positions) append after the narration so nothing is dropped.
  // Positioned events whose position is beyond the current reveal are
  // NOT rendered yet (they appear inline when the reveal reaches them).
  // Only truly positionless events append after the narration.
  const reached = toolEvents.filter(
    (t) => typeof t.position === "number" && t.position <= content.length,
  );
  const positionless = toolEvents.filter(
    (t) => typeof t.position !== "number",
  );
  if (reached.length === 0) {
    segments.push({ text: content, key: "text" });
    positionless.forEach((t, i) => {
      segments.push({ text: "", tool: t, key: `w-${i}` });
    });
    return segments;
  }
  const ordered = [...reached].sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
  let cursor = 0;
  ordered.forEach((t, i) => {
    const pos = Math.max(0, Math.min(t.position ?? 0, content.length));
    if (pos > cursor) {
      segments.push({ text: content.slice(cursor, pos), key: `t-${i}` });
    }
    segments.push({ text: "", tool: t, key: `w-${i}` });
    cursor = pos;
  });
  if (cursor < content.length) {
    segments.push({ text: content.slice(cursor), key: "tail" });
  }
  positionless.forEach((t, i) => {
    segments.push({ text: "", tool: t, key: `wp-${i}` });
  });
  return segments;
}

export default function StreamingMessageBubble({
  content,
  botName = "AI",
  botEmoji,
  activeStatus,
  toolEvents,
}: Props) {
  const segments = useMemo(
    () => interleaveSegments(content, toolEvents ?? []),
    [content, toolEvents],
  );
  return (
    <div className="message-bubble">
      <div className={`w-100 ${styles.bubbleWrap}`}>
        <MessageAvatar isUser={false} label={botName} emoji={botEmoji} />
        <div className={styles.content}>
          {segments.map((seg) =>
            seg.tool ? (
              <ToolCallWidget key={seg.key} tool={seg.tool} />
            ) : (
              <span key={seg.key}>{seg.text}</span>
            ),
          )}
          <span className="streaming-cursor" />
        </div>
        {activeStatus && (
          <div className={styles.inlineStatus}>
            <StatusPill
              iconName={activeStatus.iconName}
              label={activeStatus.label}
              statusKey={activeStatus.statusKey}
              compact
            />
          </div>
        )}
      </div>
    </div>
  );
}
