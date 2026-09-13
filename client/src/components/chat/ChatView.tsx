import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import Alert from "react-bootstrap/Alert";
import { useLLMWebSocket } from "../../features/llm/useLLMWebSocket";
import { useConversationMessages } from "../../hooks/useConversationMessages";
import { useKnowledgeBaseDocs } from "../../hooks/useKnowledgeBaseDocs";
import { useChatModelStatus } from "../../hooks/useChatModelStatus";
import { useChatPopupPanel } from "../../hooks/useChatPopupPanel";
import { useChatTextareaResize } from "../../hooks/useChatTextareaResize";
import { useChatModelPath } from "../../hooks/useChatModelPath";
import styles from "./ChatView.module.css";
import { useChatInference } from "../../hooks/useChatInference";
import { useChatMessageActions } from "../../hooks/useChatMessageActions";
import { useChatNames } from "../../hooks/useChatNames";
import MessageList from "./MessageList";
import ModelLoadingIndicator from "./input/ModelLoadingIndicator";
import ActiveToolsDisplay from "./input/ActiveToolsDisplay";
import ChatInputArea from "./input/ChatInputArea";
import ChatPopupPanel from "./panels/ChatPopupPanel";

export default function ChatView({
  conversationId,
  onSelectConversation,
  ttsOn = false,
  sttOn = false,
  onToggleTts,
  onToggleStt,
}: {
  conversationId: number | null;
  onSelectConversation?: (id: number | null) => void;
  ttsOn?: boolean;
  sttOn?: boolean;
  onToggleTts?: () => void;
  onToggleStt?: () => void;
}) {
  // ── Hooks ──────────────────────────────────────────────────────────────────
  const { isModelLoading } = useChatModelStatus();
  const { openPanel, popupAnchor, setOpenPanel, togglePanel, inputAreaRef } =
    useChatPopupPanel();
  const { textareaH, textareaDrag, handleTextareaResize } =
    useChatTextareaResize();
  const { modelPathRef } = useChatModelPath();
  const { botName, userName } = useChatNames();
  const { messages, loading, currentMood, setMessages, load, cancelLoad, appendMessage, deleteMessagesAfter } =
    useConversationMessages();
  const { docs: kbDocs, reload: reloadDocs } = useKnowledgeBaseDocs();
  const llm = useLLMWebSocket();
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);

  const conversationIdRef = useRef<number | null>(conversationId);
  const loadedConvRef = useRef<number | null>(null);

  useEffect(() => {
    if (conversationId !== null) {
      conversationIdRef.current = conversationId;
      llm.restoreMood(conversationId);
    }
  }, [conversationId]);

  // Load conversation when ID changes (skip if already loaded via new-conv flow)
  useEffect(() => {
    if (!conversationId) return;
    if (loadedConvRef.current === conversationId) return;
    loadedConvRef.current = conversationId;
    load(conversationId);
    // Cleanup: reset on unmount so React StrictMode double-mount
    // doesn't skip the load (refs survive unmount in StrictMode).
    return () => {
      loadedConvRef.current = null;
    };
  }, [conversationId, load]);

  // Restore current mood from server on conversation load
  useEffect(() => {
    if (currentMood?.mood) {
      llm.setMood(
        currentMood.mood,
        currentMood.emoji || "😐",
        currentMood.kaomoji || "(｡◕ᴗ◕｡)",
      );
    }
  }, [currentMood, llm.setMood]);

  const activeDocs = useMemo(
    () =>
      kbDocs
        .filter((d) => d.active)
        .map((d) => ({ id: d.id, name: d.path.split("/").pop() || d.path })),
    [kbDocs],
  );

  // ── Inference ──────────────────────────────────────────────────────────────
  const {
    input,
    setInput,
    error,
    setError,
    doInference,
    handleSend,
    handleCancel,
    handleKeyDown,
    handleNewConversation,
  } = useChatInference({
    messages,
    setMessages,
    appendMessage,
    cancelLoad,
    onSelectConversation,
    conversationIdRef,
    loadedConvRef,
    modelPathRef,
    llm,
    activeDocs,
  });

  // ── Message Actions ────────────────────────────────────────────────────────
  const {
    handleDeleteMessage,
    handleSubmitEdit,
    handleCopyMessage,
    handlePlayMessage,
  } = useChatMessageActions({
    conversationIdRef,
    messages,
    setMessages,
    deleteMessagesAfter,
    setError,
    doInference,
  });

  // ── Auto-scroll ─────────────────────────────────────────────────────────────
  // scrollToBottomRef is populated by MessageList from the virtualisation
  // hook and forces the full message list to mount before measuring
  // scrollHeight, avoiding the estimate-based gap bug.
  const scrollToBottomRef = useRef<() => void>(() => {});

  const wasLoadingRef = useRef(loading);
  useEffect(() => {
    if (wasLoadingRef.current && !loading && messages.length > 0) {
      scrollToBottomRef.current();
    }
    wasLoadingRef.current = loading;
  }, [loading, messages.length]);

  // ── Streaming auto-scroll tracking ────────────────────────────────────────
  // Tracks whether the user has scrolled away from the bottom so we don't
  // yank them back during streaming.
  // Declared early so the send-scroll effect below can read it.
  const userScrolledAwayRef = useRef(false);

  // When the user sends their own message while scrolled up, scroll to
  // bottom so they see their message appear.  This is the user's own
  // action, so force-scrolling is expected UX (matching Slack, Discord,
  // WhatsApp, etc.).  When already at bottom the lightweight path
  // (tail-inclusion in computeVisibleRange + heights-keyed compensation
  // effect) handles it without the expensive full-list mount.
  const prevMsgLenRef = useRef(messages.length);
  useEffect(() => {
    const isOwnMessage =
      !loading &&
      messages.length > prevMsgLenRef.current &&
      messages.length > 0 &&
      messages[messages.length - 1]?.role === "user";

    if (isOwnMessage && userScrolledAwayRef.current) {
      scrollToBottomRef.current();
    }
    prevMsgLenRef.current = messages.length;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, messages.length]);

  // Keep an at-bottom user pinned to true bottom across any tail
  // append (own send or bot-reply finalize), without the heavy
  // full-list mount and without waiting on the heights map /
  // ResizeObserver round-trip.  Runs in useLayoutEffect, after the
  // DOM has committed the new message, so el.scrollHeight already
  // reflects its real, browser-computed layout.
  //
  // Unlike useVirtualMessages.ts's heights-keyed compensation effect,
  // this is intentionally bidirectional: it exists specifically to
  // re-pin the view across the streaming-bubble → finalized-message
  // swap, which can make total content height shrink as well as
  // grow. The user was already watching the live-growing tail, so
  // snapping back to true bottom here is the desired behavior, not
  // something to guard against.
  const prevMsgLenForPinRef = useRef(messages.length);
  useLayoutEffect(() => {
    const grew = messages.length > prevMsgLenForPinRef.current;
    prevMsgLenForPinRef.current = messages.length;
    if (!grew || loading) return;
    if (userScrolledAwayRef.current) return;
    const el = messagesContainerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight - el.clientHeight;
  }, [messages.length, loading]);

  const isAtBottom = useCallback(() => {
    const el = messagesContainerRef.current;
    if (!el) return true;
    const { scrollTop, scrollHeight, clientHeight } = el;
    return scrollHeight - scrollTop - clientHeight < 40;
  }, []);

  // Track user scroll position relative to bottom.
  const handleScroll = useCallback(() => {
    userScrolledAwayRef.current = !isAtBottom();
  }, [isAtBottom]);

  // ── Drag-and-drop RAG docs ─────────────────────────────────────────────────
  const handleDragOver = (e: React.DragEvent) => {
    if (e.dataTransfer.types.includes("application/x-airunner-doc-id")) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const raw = e.dataTransfer.getData("application/x-airunner-doc-id");
    if (!raw) return;
    const docId = Number(raw);
    if (Number.isNaN(docId)) return;
    try {
      const { toggleDocumentActive } = await import("../../api/client");
      await toggleDocumentActive(docId);
      await reloadDocs();
      window.dispatchEvent(new Event("knowledge-base-changed"));
    } catch {
      // unchanged
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div
      className="d-flex flex-column h-100"
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {llm.mood && llm.mood !== "neutral" && (
        <div
          className={`d-flex align-items-center gap-1 px-3 py-1 border-bottom ${styles.moodBar}`}
          title={`${botName}'s current mood`}
        >
          <span>{llm.moodEmoji}</span>
          <span className="text-muted">{llm.mood}</span>
        </div>
      )}

      <div
        className={`chat-messages p-2 flex-grow-1 min-h-0 overflow-auto ${styles.messagesContainer}`}
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        <MessageList
          messages={messages}
          streamBuffer={llm.streamBuffer}
          thinkingBuffer={llm.thinkingBuffer}
          onDeleteMessage={handleDeleteMessage}
          onSubmitEdit={handleSubmitEdit}
          onCopyMessage={handleCopyMessage}
          onPlayMessage={handlePlayMessage}
          botName={botName}
          userName={userName}
          containerRef={messagesContainerRef}
          scrollToBottomRef={scrollToBottomRef}
        />
        {!loading && (
          <>
            <ActiveToolsDisplay activeTools={llm.activeTools} />
            <ModelLoadingIndicator
              visible={isModelLoading && messages.length > 0}
            />
          </>
        )}
      </div>

      <ChatInputArea
        input={input}
        setInput={setInput}
        handleKeyDown={handleKeyDown}
        handleTextareaResize={handleTextareaResize}
        textareaDrag={textareaDrag}
        textareaH={textareaH}
        inputAreaRef={inputAreaRef}
        llm={llm}
        openPanel={openPanel}
        togglePanel={togglePanel}
        docCount={activeDocs.length}
        ttsOn={ttsOn}
        sttOn={sttOn}
        onToggleTts={onToggleTts}
        onToggleStt={onToggleStt}
        handleSend={handleSend}
        handleCancel={handleCancel}
        handleNewConversation={handleNewConversation}
      />

      <ChatPopupPanel
        openPanel={openPanel}
        popupAnchor={popupAnchor}
        onSelectConversation={onSelectConversation}
        onClose={() => setOpenPanel(null)}
      />
    </div>
  );
}
