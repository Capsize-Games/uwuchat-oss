import { useState } from "react";
import ChatMarkdown from "@/components/markdown/ChatMarkdown";
import {
  parseToolCallContent,
  hasPartialToolCall,
  extractPartialToolCall,
} from "../toolCallUtils";
import MessageAvatar from "./MessageAvatar";
import ToolCallSection from "./ToolCallSection";
import styles from "./StreamingBubble.module.css";

interface StreamingBubbleProps {
  thinkingBuffer?: string;
  streamBuffer?: string;
  botName?: string;
}

export default function StreamingBubble({
  thinkingBuffer,
  streamBuffer,
  botName = "AI",
}: StreamingBubbleProps) {
  const [thinkingExpanded, setThinkingExpanded] = useState(true);

  let cleanContent = streamBuffer ?? "";
  const hasPartial = streamBuffer ? hasPartialToolCall(streamBuffer) : false;
  let partialToolCall = "";
  const toolCalls = streamBuffer
    ? (() => {
        const result = parseToolCallContent(streamBuffer);
        cleanContent = result.cleanContent;
        return result.toolCalls;
      })()
    : [];

  if (hasPartial && streamBuffer) {
    partialToolCall = extractPartialToolCall(streamBuffer);
  }

  return (
    <div className={`p-2 rounded w-100 ${styles.bubble}`}>
      <MessageAvatar isUser={false} label={botName} />

      {thinkingBuffer?.trim() && (
        <div className={`mb-2 rounded ${styles.thinkingCard}`}>
          <div
            className="d-flex align-items-center gap-1 p-1 cursor-pointer user-select-none"
            onClick={() => setThinkingExpanded((e) => !e)}
            role="button"
          >
            <span>{thinkingExpanded ? "▼" : "▶"}</span>
            <span>🧠</span>
            <span className="text-theme-secondary">
              Thinking
            </span>
          </div>
          {thinkingExpanded && (
            <div className={`p-2 ${styles.thinkingBody}`}>
              {thinkingBuffer}
            </div>
          )}
        </div>
      )}

      {toolCalls.map((tc, i) => (
        <ToolCallSection key={i} toolCall={tc} defaultExpanded={true} />
      ))}

      {partialToolCall && (
        <div className={`mb-2 rounded ${styles.partialToolCard}`}>
          <div className="d-flex align-items-center gap-1 p-1">
            <span>🔧</span>
            <span className="text-theme-secondary">
              Tool Call (streaming...)
            </span>
          </div>
          <div className={`p-2 ${styles.partialToolBody}`}>
            {partialToolCall}
          </div>
        </div>
      )}

      {cleanContent && (
        <div className={`streaming-cursor ${styles.content}`}>
          <ChatMarkdown
            content={cleanContent.trimStart()}
            streaming
          />
        </div>
      )}
    </div>
  );
}
