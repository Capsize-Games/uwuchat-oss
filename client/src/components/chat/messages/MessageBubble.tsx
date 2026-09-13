import { useState, useCallback } from "react";
import ChatMarkdown from "@/components/markdown/ChatMarkdown";
import type { Message } from "../../../types/api";
import { parseToolCallContent } from "../toolCallUtils";
import MessageAvatar from "./MessageAvatar";
import ToolCallSection from "./ToolCallSection";
import MessageActions from "./MessageActions";
import styles from "./MessageBubble.module.css";

interface MessageBubbleProps {
  message: Message;
  index: number;
  editingIndex: number | null;
  editContent: string;
  onStartEdit: (index: number, content: string) => void;
  onCancelEdit: () => void;
  onConfirmEdit: () => void;
  onEditContentChange: (value: string) => void;
  onEditKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onDelete?: (index: number) => void;
  onCopy?: (content: string) => void;
  onPlay?: (content: string) => void;
  botName?: string;
  userName?: string;
}

export default function MessageBubble({
  message,
  index,
  editingIndex,
  editContent,
  onStartEdit,
  onCancelEdit,
  onConfirmEdit,
  onEditContentChange,
  onEditKeyDown,
  onDelete,
  onCopy,
  onPlay,
  botName = "AI",
  userName = "You",
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const hasThinking = !isUser && !!(message.thinking_content?.trim());
  const isEditing = editingIndex === index;

  const { toolCalls, cleanContent } = parseToolCallContent(message.content);
  const hasToolCalls = toolCalls.length > 0;

  const handleCopy = useCallback(
    () => onCopy?.(message.content),
    [onCopy, message.content],
  );
  const handleDelete = useCallback(
    () => onDelete?.(index),
    [onDelete, index],
  );
  const handlePlay = useCallback(
    () => onPlay?.(message.content),
    [onPlay, message.content],
  );
  const handleEditClick = useCallback(
    () => onStartEdit(index, message.content),
    [onStartEdit, index, message.content],
  );

  return (
    <div className="message-bubble">
      <div
        className={`p-2 rounded w-100 ${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleBot}`}
      >
        <MessageAvatar isUser={isUser} label={isUser ? userName : botName} />

        {hasThinking && (
          <div className={`mb-2 rounded ${styles.thinkingCard}`}>
            <div
              className="d-flex align-items-center gap-1 p-1 cursor-pointer user-select-none"
              onClick={() => setThinkingExpanded((e) => !e)}
              role="button"
            >
              <span>{thinkingExpanded ? "▼" : "▶"}</span>
              <span>✅</span>
              <span className={styles.thinkingHeader}>
                Complete
              </span>
            </div>
            {thinkingExpanded && (
              <div className={`p-2 ${styles.thinkingBody}`}>
                {message.thinking_content}
              </div>
            )}
          </div>
        )}

        {hasToolCalls &&
          toolCalls.map((tc, i) => <ToolCallSection key={i} toolCall={tc} />)}
        {!hasToolCalls && message.tool_usage && message.tool_usage.map((tu, i) => (
          <ToolCallSection
            key={`tu-${i}`}
            toolCall={{
              functionName: tu.tool_name,
              parameters: tu.query ? { query: tu.query } : {},
              rawXml: "",
            }}
            result={tu.result}
          />
        ))}

        {isEditing ? (
          <div>
            <textarea
              className={`form-control ${styles.editTextarea}`}
              value={editContent}
              onChange={(e) => onEditContentChange(e.target.value)}
              onKeyDown={onEditKeyDown}
              rows={3}
              autoFocus
            />
            <div className="d-flex gap-1 mt-1 justify-content-end">
              <button
                className={`btn btn-sm btn-outline-secondary p-1 ${styles.editBtn}`}
                onClick={onCancelEdit}
                title="Cancel"
              >
                Cancel
              </button>
              <button
                className={`btn btn-sm btn-outline-primary p-1 ${styles.editBtn}`}
                onClick={onConfirmEdit}
                disabled={!editContent.trim()}
                title="Save"
              >
                Save & Send
              </button>
            </div>
          </div>
        ) : (
          <div className={styles.content}>
            {hasToolCalls && cleanContent ? (
              <ChatMarkdown content={cleanContent.trimStart()} />
            ) : !hasToolCalls ? (
              <ChatMarkdown content={(message.content || "").trimStart()} />
            ) : null}
          </div>
        )}

        <MessageActions
          isUser={isUser}
          isEditing={isEditing}
          onCopy={handleCopy}
          onEdit={handleEditClick}
          onDelete={handleDelete}
          onPlay={handlePlay}
        />
      </div>
    </div>
  );
}
