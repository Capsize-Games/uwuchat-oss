import type { RefObject, MutableRefObject } from "react";
import type { ChatPanel } from "../types";
import type { useLLMWebSocket } from "../../../features/llm/useLLMWebSocket";
import ChatDocsRow from "./ChatDocsRow";
import ChatToolbar from "./ChatToolbar";
import styles from "./ChatInputArea.module.css";

interface ChatInputAreaProps {
  input: string;
  setInput: (v: string) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleTextareaResize: (e: React.MouseEvent) => void;
  textareaDrag: MutableRefObject<boolean>;
  textareaH: number;
  inputAreaRef: RefObject<HTMLDivElement>;
  llm: ReturnType<typeof useLLMWebSocket>;
  openPanel: ChatPanel;
  togglePanel: (panel: NonNullable<ChatPanel>) => void;
  docCount: number;
  ttsOn: boolean;
  sttOn: boolean;
  onToggleTts?: () => void;
  onToggleStt?: () => void;
  handleSend: () => Promise<void>;
  handleCancel: () => void;
  handleNewConversation: () => Promise<void>;
}

export default function ChatInputArea({
  input,
  setInput,
  handleKeyDown,
  handleTextareaResize,
  textareaDrag,
  textareaH,
  inputAreaRef,
  llm,
  openPanel,
  togglePanel,
  docCount,
  ttsOn,
  sttOn,
  onToggleTts,
  onToggleStt,
  handleSend,
  handleCancel,
  handleNewConversation,
}: ChatInputAreaProps) {
  return (
    <>
      <div
        onMouseDown={handleTextareaResize}
        className={styles.resizeHandle}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.background =
            "rgba(99,153,255,0.3)";
        }}
        onMouseLeave={(e) => {
          if (!textareaDrag.current) {
            (e.currentTarget as HTMLDivElement).style.background = "transparent";
          }
        }}
      />

      <div
        ref={inputAreaRef}
        className="chat-input-area flex-shrink-0 d-flex flex-column"
        // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
        style={{ height: textareaH }}
      >
        <div className="flex-grow-1 d-flex flex-column min-h-0">
          <ChatDocsRow
            openPanel={openPanel}
            togglePanel={togglePanel}
            docCount={docCount}
          />

          <div
            className={`d-flex flex-column min-h-0 prompt-textarea-bg ${styles.inputArea}`}
          >
            <textarea
              className={`flex-grow-1 min-h-0 ${styles.textarea}`}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
            />

          </div>

          <ChatToolbar
            ttsOn={ttsOn}
            sttOn={sttOn}
            onToggleTts={onToggleTts}
            onToggleStt={onToggleStt}
            streaming={llm.streaming}
            input={input}
            handleSend={handleSend}
            handleCancel={handleCancel}
            handleNewConversation={handleNewConversation}
          />
        </div>
      </div>
    </>
  );
}
