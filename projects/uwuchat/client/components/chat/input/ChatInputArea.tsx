import { useState, type RefObject, type MutableRefObject } from "react";
import { useTranslation } from "react-i18next";
import type { ChatPanel } from "../types";
import type { useLLMWebSocket } from "@/features/llm/useLLMWebSocket";
import CodeModePicker from "./CodeModePicker";
import type { CodeModeSlug } from "../../../api/codeMode";
import styles from "./ChatInputArea.module.css";
const MAX_INPUT_CHARS = 2000;

interface ChatInputAreaProps {
  input: string; setInput: (v: string) => void;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleTextareaResize: (e: React.MouseEvent) => void;
  textareaDrag: MutableRefObject<boolean>; textareaH: number;
  inputAreaRef: RefObject<HTMLDivElement>;
  llm: ReturnType<typeof useLLMWebSocket>;
  openPanel: ChatPanel; togglePanel: (panel: NonNullable<ChatPanel>) => void;
  ttsOn: boolean; sttOn: boolean;
  onToggleTts?: () => void; onToggleStt?: () => void;
  handleSend: () => Promise<void>; handleCancel: () => void;
  blocked?: boolean; previewTier?: string; quotaExhausted?: boolean;
  loading?: boolean;
  codeMode: {
    enabled: boolean;
    mode: CodeModeSlug;
    pending: boolean;
    loading: boolean;
    select: (mode: CodeModeSlug | null) => void;
  };
}

export default function ChatInputArea({
  input, setInput, handleKeyDown, inputAreaRef, llm,
  ttsOn, sttOn, onToggleTts, onToggleStt,
  handleSend, handleCancel, blocked, previewTier, quotaExhausted, loading,
  codeMode,
}: ChatInputAreaProps) {
  const { t } = useTranslation();
  if (loading) return null;
  const exhaustedClass = quotaExhausted ? " chat-input-exhausted" : "";
  return (
    <>
      {quotaExhausted && (
        <style>{`.chat-input-exhausted textarea:focus { outline: 2px solid rgba(239,68,68,0.45) !important; }`}</style>
      )}
      <div ref={inputAreaRef} className={`chat-input-area${exhaustedClass} ${styles.wrap}`}>
        <textarea
          className={styles.textarea}
          value={input}
          onChange={(e) => setInput(e.target.value.slice(0, MAX_INPUT_CHARS))}
          onKeyDown={handleKeyDown}
          placeholder={blocked ? t("chat.blocked_placeholder") : t("chat.type_message")}
          disabled={blocked || loading}
        />
        <div className={styles.footer}>
          <CodeModePicker
            enabled={codeMode.enabled}
            mode={codeMode.mode}
            pending={codeMode.pending}
            loading={codeMode.loading}
            onSelect={codeMode.select}
          />
          <span className={input.length >= MAX_INPUT_CHARS ? styles.charWarn : styles.charOk}>
            {input.length}/{MAX_INPUT_CHARS}
          </span>
          <span className={styles.spacer}>
            {blocked ? (
              <span className={styles.statusTextBlocked}>{t("chat.blocked_label")}</span>
            ) : llm.streaming ? (
              <button type="button" onClick={handleCancel} title="Cancel" className={styles.cancelBtn}>
                <span className={styles.cancelIcon}>✕</span>
              </button>
            ) : (
              <button type="button" onClick={handleSend} onMouseDown={(e) => e.preventDefault()}
                disabled={!input.trim()} title="Send message"
                className={input.trim() ? styles.sendActive : styles.sendDisabled}>
                <span className={styles.sendIcon}>↑</span>
              </button>
            )}
          </span>
        </div>
      </div>
    </>
  );
}
