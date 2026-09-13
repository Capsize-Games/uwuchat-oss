import { useEffect, useState, useCallback, useRef } from "react";
import type { Message } from "../../types/api";
import { useVirtualMessages } from "../../hooks/useVirtualMessages";
import type { VirtualMessagesResult } from "../../hooks/useVirtualMessages";
import EmptyPlaceholder from "./messages/EmptyPlaceholder";
import MessageBubble from "./messages/MessageBubble";
import StreamingBubble from "./messages/StreamingBubble";
import styles from "./MessageList.module.css";

export default function MessageList({
  messages,
  streamBuffer,
  thinkingBuffer,
  onDeleteMessage,
  onSubmitEdit,
  onCopyMessage,
  onPlayMessage,
  botName,
  userName,
  containerRef,
  scrollToBottomRef,
}: {
  messages: Message[];
  streamBuffer?: string;
  thinkingBuffer?: string;
  onDeleteMessage?: (index: number) => void;
  onSubmitEdit?: (index: number, newContent: string) => void;
  onCopyMessage?: (content: string) => void;
  onPlayMessage?: (content: string) => void;
  botName?: string;
  userName?: string;
  /** Ref to the scrollable container (for virtual-scroll calculations). */
  containerRef: React.RefObject<HTMLDivElement | null>;
  /**
   * Optional mutable ref that the parent can use to call
   * scrollToBottom() on the virtualisation hook, which forces the
   * full message list to mount before measuring scrollHeight.
   */
  scrollToBottomRef?: React.MutableRefObject<() => void>;
}) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editContent, setEditContent] = useState("");
  const streamingBubbleRef = useStreamingBubbleScroll(containerRef);

  // ── Virtual scroll ─────────────────────────────────────────────────
  const {
    visibleRange,
    paddingTop,
    paddingBottom,
    measureRef,
    scrollToBottom,
  } = useVirtualMessages({
    messageCount: messages.length,
    containerRef,
  }) as VirtualMessagesResult;

  // Expose scrollToBottom to the parent via the optional ref.
  useEffect(() => {
    if (scrollToBottomRef) {
      scrollToBottomRef.current = scrollToBottom;
    }
  }, [scrollToBottom, scrollToBottomRef]);

  const handleStartEdit = useCallback((index: number, content: string) => {
    setEditingIndex(index);
    setEditContent(content);
  }, []);

  const handleCancelEdit = useCallback(() => {
    setEditingIndex(null);
    setEditContent("");
  }, []);

  const handleConfirmEdit = useCallback(() => {
    if (editingIndex === null || !editContent.trim()) return;
    onSubmitEdit?.(editingIndex, editContent.trim());
    setEditingIndex(null);
    setEditContent("");
  }, [editingIndex, editContent, onSubmitEdit]);

  const handleEditKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleConfirmEdit();
      }
      if (e.key === "Escape") handleCancelEdit();
    },
    [handleConfirmEdit, handleCancelEdit],
  );

  const isStreaming = !!(
    thinkingBuffer?.trim() ||
    (streamBuffer && streamBuffer.length > 0)
  );

  if (messages.length === 0 && !isStreaming) {
    return <EmptyPlaceholder />;
  }

  return (
    <div className="d-flex flex-column gap-2">
      {/* Spacer for messages above the visible window */}
      {/* eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop */}
      {paddingTop > 0 && <div className={styles.spacer} style={{ height: paddingTop }} />}

      {visibleRange &&
        messages
          .slice(visibleRange[0], visibleRange[1] + 1)
          .map((msg, sliceIdx) => {
            const actualIndex = visibleRange[0] + sliceIdx;
            return (
              <div
                key={`msg-${actualIndex}`}
                ref={measureRef(actualIndex)}
              >
                <MessageBubble
                  message={msg}
                  index={actualIndex}
                  editingIndex={editingIndex}
                  editContent={editContent}
                  onStartEdit={handleStartEdit}
                  onCancelEdit={handleCancelEdit}
                  onConfirmEdit={handleConfirmEdit}
                  onEditContentChange={setEditContent}
                  onEditKeyDown={handleEditKeyDown}
                  onDelete={onDeleteMessage}
                  onCopy={onCopyMessage}
                  onPlay={onPlayMessage}
                  botName={botName}
                  userName={userName}
                />
              </div>
            );
          })}

      {/* Spacer for messages below the visible window */}
      {paddingBottom > 0 && (
        // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
        <div className={styles.spacer} style={{ height: paddingBottom }} />
      )}

      {isStreaming && (
        <div ref={streamingBubbleRef}>
          <StreamingBubble
            thinkingBuffer={thinkingBuffer}
            streamBuffer={streamBuffer}
            botName={botName}
          />
        </div>
      )}
    </div>
  );
}

// ── Streaming-bubble ResizeObserver for smooth scroll compensation ──
// Uses a callback ref so the observer is attached/detached as the
// streaming bubble mounts/unmounts.  A useLayoutEffect keyed on a
// stable ref never re-fires for a conditionally-rendered element.
function useStreamingBubbleScroll(
  containerRef: React.RefObject<HTMLDivElement | null>,
): (el: HTMLDivElement | null) => void {
  const observerRef = useRef<ResizeObserver | null>(null);

  return useCallback(
    (el: HTMLDivElement | null) => {
      // Teardown: disconnect any previous observer.
      observerRef.current?.disconnect();
      observerRef.current = null;
      if (!el) return;

      // Setup: observe the newly-mounted streaming bubble.
      const ro = new ResizeObserver(() => {
        const container = containerRef.current;
        if (!container) return;

        const { scrollTop, scrollHeight, clientHeight } = container;
        // "At bottom" check matching ChatView's isAtBottom() convention.
        if (scrollHeight - scrollTop - clientHeight >= 40) return;

        // Monotonic "only move forward" guard (mirrors
        // useVirtualMessages.ts lines 247-260).
        const newMax = scrollHeight - clientHeight;
        if (newMax > scrollTop) {
          container.scrollTop = scrollHeight;
        }
      });
      ro.observe(el);
      observerRef.current = ro;
    },
    [containerRef],
  );
}
