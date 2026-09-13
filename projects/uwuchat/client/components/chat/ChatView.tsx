import { useEffect, useRef, useCallback, useLayoutEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Alert from "react-bootstrap/Alert";
import { useLLMWebSocket } from "@/features/llm/useLLMWebSocket";
import { useUwuThread } from "../../hooks/useUwuThread";
import { useChatPopupPanel } from "@/hooks/useChatPopupPanel";
import { useChatTextareaResize } from "@/hooks/useChatTextareaResize";
import { useChatModelPath } from "@/hooks/useChatModelPath";
import { useChatInference } from "../../hooks/useChatInference";
import { useChatNames } from "@/hooks/useChatNames";
import { useAuth } from "../../hooks/useAuth";
import LucideIcon from "@/components/shared/LucideIcon";
import { useAdminCost } from "../../context/AdminCostContext";
import { useCodeMode } from "../../hooks/useCodeMode";
import MessageList from "./MessageList";
import ModelLoadingIndicator from "@/components/chat/input/ModelLoadingIndicator";
import ChatInputArea from "./input/ChatInputArea";
import ChatPopupPanel from "./panels/ChatPopupPanel";
import { TypingBubble } from "../messages/TypingBubble";
import StreamingMessageBubble from "./messages/StreamingMessageBubble";
import StreamingStatus from "./StreamingStatus";
import { useStreamingStatusQueue } from "../../hooks/useStreamingStatusQueue";
import { useStreamingBubbleScroll } from "../../hooks/useStreamingBubbleScroll";
import { useTypewriterReveal } from "../../hooks/useTypewriterReveal";
import { useImmersion } from "../../hooks/useImmersion";
import { greetingStore } from "../../hooks/greetingStore";
import { useEventBus } from "@/features/events/useEventBus";
import { EVENT_PROACTIVE_MESSAGE } from "@/features/events/types";
import { UsageBar } from "./UsageBar";
import { useQuota } from "../../hooks/useQuota";
import { useChatbotProfile } from "../../hooks/useChatbotProfile";
import { useChatbotStatus } from "../../hooks/useChatbotStatus";
import { ProfileView } from "../rooms/ProfileView";
import UserProfilePanel from "../user/UserProfilePanel";
import { ContactsSidebar } from "../panels/ContactsSidebar";
import { useIsMobile } from "../../hooks/useIsMobile";
import FastSearchStatusPanel from "./FastSearchStatusPanel";
import AdminUsersPanel from "./AdminUsersPanel";
import AdminReportsPanel from "../admin/AdminReportsPanel";
import WaitlistPanel from "../admin/WaitlistPanel";
import DisputesPanel from "../admin/DisputesPanel";
import { AgentCalendarViewer, CostTrackingPanel } from "@/components/admin";
import FlowDetailPanel from "./FlowDetailPanel";
import type { FlowStep } from "@extensions/conversation_inspector/client/api";
import {
  fetchThreadFlow,
  type ConversationFlowResponse,
} from "@extensions/conversation_inspector/client/api";
import type { CallChainDetail, CallChainStep } from "../types/pipeline";
import type { ConversationEvent } from "../../api/admin";
import { listAdminEvents } from "../../api/admin";
import TurnFlowView from "./messages/TurnFlowView";
import styles from "./ChatView.module.css";

/* ── Panel drag-resize (module-level) ── */
const PANEL_W_LS_KEY = "uwuchat_panel_width";
const PANEL_MIN = 260;
const PANEL_DEFAULT = 300;

let panelDrag: {
  startX: number;
  startW: number;
  maxW: number;
  panelEl: HTMLElement;
  commitWidth: (w: number) => void;
} | null = null;

function onPanelMouseMove(e: MouseEvent) {
  if (!panelDrag) return;
  const delta = panelDrag.startX - e.clientX;
  const newW = Math.min(panelDrag.maxW, Math.max(PANEL_MIN, panelDrag.startW + delta));
  panelDrag.panelEl.style.width = `${newW}px`;
}

function onPanelMouseUp() {
  if (!panelDrag) return;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  const finalW = parseInt(panelDrag.panelEl.style.width, 10);
  if (!isNaN(finalW)) {
    panelDrag.commitWidth(finalW);
  }
  panelDrag = null;
}

if (typeof window !== "undefined") {
  window.addEventListener("mousemove", onPanelMouseMove);
  window.addEventListener("mouseup", onPanelMouseUp);
}

function readPanelWidth(): number {
  try {
    const v = localStorage.getItem(PANEL_W_LS_KEY);
    return v !== null ? Number(v) : PANEL_DEFAULT;
  } catch { return PANEL_DEFAULT; }
}

export default function ChatView({
  chatbotId,
  onSelectChatbot,
  ttsOn = false,
  sttOn = false,
  onToggleTts,
  onToggleStt,
  onCreateUwu,
  connecting,
  connectError,
}: {
  chatbotId: number | null;
  onSelectChatbot?: (id: number | null) => void;
  ttsOn?: boolean;
  sttOn?: boolean;
  onToggleTts?: () => void;
  onToggleStt?: () => void;
  onCreateUwu?: () => void;
  connecting?: boolean;
  connectError?: string | null;
}) {
  const { t } = useTranslation();
  // Called for server-sync side effects; immersion level is read
  // internally by useChatInference via getImmersion().
  useImmersion();
  const { accessToken } = useAuth();
  const { refreshAnnotations } = useAdminCost();
  const [proactiveLoading, setProactiveLoading] = useState(false);
  const [proactiveError, setProactiveError] = useState<string | null>(null);
  const { openPanel, popupAnchor, setOpenPanel, togglePanel, inputAreaRef } =
    useChatPopupPanel();
  const { textareaH, textareaDrag, handleTextareaResize } =
    useChatTextareaResize();
  const { modelPathRef } = useChatModelPath();
  const { botName, botEmoji, userName, avatarImage } = useChatNames(chatbotId);
  const { messages, setMessages, loading, error: threadError, errorRef: threadErrorRef, load, cancelLoad, appendMessage, threadMood } =
    useUwuThread();
  const llm = useLLMWebSocket();
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const isMobile = useIsMobile();
  const { profile: chatbotProfile } = useChatbotProfile(chatbotId);
  const {
    status: chatbotStatus,
    blockBot,
    unblockBot,
    refresh: refreshStatus,
    setBlocked,
  } = useChatbotStatus(chatbotId);
  type RightPanel =
    | { type: "profile" }
    | { type: "user-profile" }
    | { type: "contacts" }
    | { type: "admin"; panel: "fastsearch" | "users" | "promotions" | "reports" | "calendar" | "costs" | "waitlist" | "disputes" }
    | { type: "flow-detail"; step: FlowStep; costStep?: CallChainStep }
    | null;

  const PANEL_LS_KEY = "uwuchat_right_panel";

  function readPanel(): RightPanel {
    try {
      const raw = localStorage.getItem(PANEL_LS_KEY);
      if (!raw) return { type: "contacts" };
      return JSON.parse(raw) as RightPanel;
    } catch { return { type: "contacts" }; }
  }

  function savePanel(p: RightPanel) {
    try {
      if (p === null) localStorage.removeItem(PANEL_LS_KEY);
      else localStorage.setItem(PANEL_LS_KEY, JSON.stringify(p));
    } catch { /* ignore */ }
  }

  const [rightPanel, setRightPanelState] = useState<RightPanel>(readPanel);
  const [panelWidth, setPanelWidthState] = useState(readPanelWidth);
  const panelElRef = useRef<HTMLDivElement>(null);

  const setRightPanel = (p: RightPanel) => {
    savePanel(p);
    setRightPanelState(p);
  };

  const setPanelWidth = (w: number) => {
    const clamped = Math.max(PANEL_MIN, w);
    setPanelWidthState(clamped);
    try { localStorage.setItem(PANEL_W_LS_KEY, String(clamped)); } catch { /* ignore */ }
  };

  // Notify TopBar of panel changes so header buttons stay highlighted.
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("uwuchat:panel-changed", {
        detail: { panelType: rightPanel?.type ?? null },
      }),
    );
  }, [rightPanel]);

  const handlePanelDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const maxW = Math.max(PANEL_MIN, containerWidth - 200);
    const el = panelElRef.current;
    if (!el) return;
    panelDrag = {
      startX: e.clientX,
      startW: panelWidth,
      maxW,
      panelEl: el,
      commitWidth: setPanelWidth,
    };
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  useEffect(() => {
    const show = () => {
      sessionStorage.removeItem("uwuchat_show_user_profile");
      setRightPanel({ type: "user-profile" });
    };
    if (sessionStorage.getItem("uwuchat_show_user_profile") === "1") show();
    window.addEventListener("airunner:show-user-profile", show);
    window.addEventListener("uwuchat:show-user-profile", show);
    return () => {
      window.removeEventListener("airunner:show-user-profile", show);
      window.removeEventListener("uwuchat:show-user-profile", show);
    };
  }, []);

  useEffect(() => {
    // Desktop only — on mobile, MainContent handles this event by
    // swapping the whole content area to a full-screen contacts panel.
    if (isMobile) return;
    const handler = () => {
      setRightPanel(rightPanel?.type === "contacts" ? null : { type: "contacts" });
    };
    window.addEventListener("uwuchat:toggle-contacts", handler);
    return () => window.removeEventListener("uwuchat:toggle-contacts", handler);
  }, [isMobile, rightPanel]);

  useEffect(() => {
    const show = () => setRightPanel({ type: "admin", panel: "fastsearch" });
    window.addEventListener("airunner:show-fastsearch-status", show);
    return () => window.removeEventListener("airunner:show-fastsearch-status", show);
  }, []);

  useEffect(() => {
    const show = () =>
      setRightPanel({ type: "admin", panel: "promotions" });
    window.addEventListener("airunner:show-admin-promotions", show);
    return () =>
      window.removeEventListener("airunner:show-admin-promotions", show);
  }, []);

  useEffect(() => {
    const show = () => setRightPanel({ type: "admin", panel: "users" });
    window.addEventListener("airunner:show-admin-users", show);
    return () => window.removeEventListener("airunner:show-admin-users", show);
  }, []);

  useEffect(() => {
    const show = () =>
      setRightPanel({ type: "admin", panel: "reports" });
    window.addEventListener("airunner:show-admin-reports", show);
    return () =>
      window.removeEventListener("airunner:show-admin-reports", show);
  }, []);

  useEffect(() => {
    const show = () =>
      setRightPanel({ type: "admin", panel: "calendar" });
    window.addEventListener("airunner:show-admin-calendar", show);
    return () =>
      window.removeEventListener("airunner:show-admin-calendar", show);
  }, []);

  useEffect(() => {
    const show = () =>
      setRightPanel({ type: "admin", panel: "waitlist" });
    window.addEventListener("airunner:show-admin-waitlist", show);
    return () =>
      window.removeEventListener("airunner:show-admin-waitlist", show);
  }, []);

  useEffect(() => {
    const show = () =>
      setRightPanel({ type: "admin", panel: "disputes" });
    window.addEventListener("airunner:show-admin-disputes", show);
    return () =>
      window.removeEventListener("airunner:show-admin-disputes", show);
  }, []);

  useEffect(() => {
    const show = () =>
      setRightPanel({ type: "admin", panel: "costs" });
    window.addEventListener("airunner:show-admin-costs", show);
    return () =>
      window.removeEventListener("airunner:show-admin-costs", show);
  }, []);

  // On desktop, never show an empty panel — default to contacts.
  useEffect(() => {
    if (!isMobile && rightPanel === null) {
      setRightPanel({ type: "contacts" });
    }
  }, [isMobile, rightPanel]);

  useEffect(() => {
    const show = (e: Event) => {
      const detail = (e as CustomEvent<{
        step: FlowStep;
        costStep?: CallChainStep;
      }>).detail;
      if (detail?.step) {
        setRightPanel({
          type: "flow-detail",
          step: detail.step,
          costStep: detail.costStep,
        });
      }
    };
    window.addEventListener("airunner:show-flow-detail", show);
    return () => window.removeEventListener("airunner:show-flow-detail", show);
  }, []);

  const [inspectionEnabled, setInspectionEnabled] = useState(false);
  const [flowData, setFlowData] = useState<ConversationFlowResponse | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);

  useEffect(() => {
    if (!inspectionEnabled || !chatbotId) {
      setFlowData(null);
      return;
    }
    setFlowLoading(true);
    fetchThreadFlow(chatbotId)
      .then(setFlowData)
      .catch(() => setFlowData(null))
      .finally(() => setFlowLoading(false));
  }, [inspectionEnabled, chatbotId, messages]);

  // Listen for toggle-inspection events from the footer indicator
  useEffect(() => {
    const handler = () => setInspectionEnabled((prev) => !prev);
    window.addEventListener("airunner:toggle-inspection", handler);
    return () =>
      window.removeEventListener("airunner:toggle-inspection", handler);
  }, []);

  // Notify footer when inspection state changes
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("airunner:inspection-changed", {
        detail: { enabled: inspectionEnabled },
      }),
    );
  }, [inspectionEnabled]);
  const [costMap, setCostMap] = useState<Record<string, CallChainDetail>>({});
  const [costLoading, setCostLoading] = useState(false);
  const [events, setEvents] = useState<ConversationEvent[]>([]);

  // Fetch events when inspection is ON, scoped to the visible message window
  useEffect(() => {
    if (!inspectionEnabled || !chatbotId) {
      setEvents([]);
      return;
    }
    const params: { limit: number; since?: string } = { limit: 200 };
    if (messages.length > 0) {
      const firstTs = messages[0].created_at;
      if (firstTs) {
        // Pad by 5 minutes so events recorded just before the first
        // visible message (e.g. tool calls that triggered it) are included.
        const sinceDate = new Date(
          new Date(firstTs).getTime() - 5 * 60_000,
        );
        params.since = sinceDate.toISOString();
      }
    }
    listAdminEvents(chatbotId, params)
      .then((res) => setEvents(res.events))
      .catch(() => {});
  }, [inspectionEnabled, chatbotId, messages]);

  // Fetch cost data for all bot messages when inspection is ON
  useEffect(() => {
    if (!inspectionEnabled || messages.length === 0) {
      setCostMap({});
      return;
    }
    const uniqueIds = new Set<string>();
    messages.forEach((m) => {
      if (m.call_chain_id) uniqueIds.add(m.call_chain_id);
    });
    if (uniqueIds.size === 0) {
      setCostMap({});
      return;
    }
    setCostLoading(true);
    const fetches = Array.from(uniqueIds).map(async (cid) => {
      try {
        const headers: Record<string, string> = {};
        if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
        const resp = await fetch(`/api/v1/admin/call-chain/${cid}`, { headers });
        if (!resp.ok) return null;
        const detail = await resp.json() as CallChainDetail;
        return { cid, detail };
      } catch {
        return null;
      }
    });
    Promise.all(fetches).then((results) => {
      const map: Record<string, CallChainDetail> = {};
      results.forEach((r) => {
        if (r && r.detail) map[r.cid] = r.detail;
      });
      setCostMap(map);
      setCostLoading(false);
    });
  }, [inspectionEnabled, messages]);
  const messagesContainerRef = useRef<HTMLDivElement | null>(null);
  const [showTyping, setShowTyping] = useState(false);
  const [proactiveTyping, setProactiveTyping] = useState(false);
  // Compute stabilized tool-status once, shared by both the standalone
  // pre-text StreamingStatus and the inline indicator inside
  // StreamingMessageBubble.  Must be placed after all state hooks it
  // depends on (e.g. showTyping).
  const stabilizedStatus = useStreamingStatusQueue(
    llm.activeTools,
    llm.thinkingBuffer,
    llm.isThinking,
    showTyping,
  );
  // Track active conversation_id (current session) and session_id.
  const conversationIdRef = useRef<number | null>(null);
  // Reactive mirror of conversationIdRef, for consumers (e.g.
  // useCodeMode/CodeModePicker) that need to re-render when it
  // resolves/changes — the ref alone doesn't trigger renders.
  const [conversationId, setConversationId] = useState<number | null>(null);
  const currentSessionIdRef = useRef<number | null>(null);
  // Code-mode intent state, shared with the CodeModePicker rendered
  // inside ChatInputArea.  `pending` is the pre-conversation "start as
  // code" arm; once a conversation resolves with pending set, the
  // effect below applies it.
  const {
    enabled: codeModeEnabled,
    mode: codeModeMode,
    pending: codeModePending,
    loading: codeModeLoading,
    select: selectCodeMode,
    clearPending: clearCodeModePending,
  } = useCodeMode(conversationId);
  const appliedCodeModeRef = useRef<number | null>(null);

  // Apply the "start as code" intent as soon as a fresh conversation
  // resolves after the user armed it.  The ref prevents re-applying to
  // a conversation that already had the intent persisted server-side.
  useEffect(() => {
    if (!codeModePending || conversationId === null) return;
    if (appliedCodeModeRef.current === conversationId) return;
    appliedCodeModeRef.current = conversationId;
    clearCodeModePending();
    import("../../api/codeMode")
      .then(({ setCodeMode }) =>
        setCodeMode(conversationId, true, codeModeMode),
      )
      .catch(() => {});
  }, [codeModePending, conversationId, codeModeMode, clearCodeModePending]);
  const loadedChatbotRef = useRef<number | null>(null);
  // Incremented by the retry button in MessageList to re-trigger the
  // chatbot-switch effect for the current chatbot.
  const [retryKey, setRetryKey] = useState(0);

  const handleRetryConversation = useCallback(() => {
    loadedChatbotRef.current = null;
    setRetryKey((k) => k + 1);
  }, []);
  // Generation counter: incremented on each chatbot switch.  Stale
  // async init closures (e.g. a late-resolving getUwuSession or load
  // from a previous switch) are discarded by comparing their captured
  // generation against this ref.
  const switchGenRef = useRef(0);
  // True while the async session-resolution + thread-load is in flight
  // for the current chatbot switch.  Distinct from
  // conversationIdRef.current === null, which is also the normal
  // expected state for a chatbot that has never had a message sent to
  // it yet (conversation is created lazily on first send).
  const [sessionResolving, setSessionResolving] = useState(false);
  const conversationLoading = sessionResolving || loading;
  const quota = useQuota();


  // Append proactive messages pushed from the server in real time,
  // preceded by a typing indicator for a natural feel.
  useEventBus([EVENT_PROACTIVE_MESSAGE], (_event, data) => {
    const d = data as {
      chatbot_id?: number;
      role?: string;
      content?: string;
    };
    if (d.chatbot_id !== chatbotId) return;
    const content = d.content ?? "";
    setProactiveTyping(true);
    const chars = content.length;
    const cps = 40 + Math.random() * 40;
    const delay = Math.min(8000, Math.max(800, (chars / cps) * 1000));
    setTimeout(() => {
      setProactiveTyping(false);
      appendMessage({ role: "assistant", content });
    }, delay);
  });

  // On chatbotId change: fetch the active session then load the thread.
  useEffect(() => {
    if (!chatbotId) {
      setMessages([]);
      conversationIdRef.current = null;
      setConversationId(null);
      currentSessionIdRef.current = null;
      loadedChatbotRef.current = null;
      setSessionResolving(false);
      return;
    }
    if (loadedChatbotRef.current === chatbotId) return;
    loadedChatbotRef.current = chatbotId;

    // Synchronously invalidate the previous chatbot's session refs
    // BEFORE any async work.  This closes the race window where a send
    // could pick up stale conversation / session ids from the previous
    // chatbot before getUwuSession resolves.
    conversationIdRef.current = null;
    setConversationId(null);
    currentSessionIdRef.current = null;
    setMessages([]);
    setSessionResolving(true);

    // Capture the generation this effect run belongs to.  If a newer
    // switch fires before this async init finishes, the generation
    // counter will have incremented and this closure bails out.
    const gen = ++switchGenRef.current;

    async function init() {
      try {
        const { getUwuSession } = await import("../../api/chat");
        const sess = await getUwuSession(chatbotId);
        // Discard if a later switch has fired.
        if (switchGenRef.current !== gen) return;
        conversationIdRef.current = sess.conversation_id ?? null;
        setConversationId(sess.conversation_id ?? null);
        currentSessionIdRef.current = sess.session_id ?? null;
      } catch (err) {
        if (switchGenRef.current !== gen) return;
        console.warn("[ChatView] getUwuSession failed:", err);
        // Chatbot no longer exists (e.g. after a DB reset) — clear the stale
        // cached ID so the UwU creator is shown instead.
        const msg = err instanceof Error ? err.message : String(err);
        if (/404|not found/i.test(msg)) {
          loadedChatbotRef.current = null;
          setSessionResolving(false);
          onSelectChatbot?.(null);
          return;
        }
        // Any other error: session will be created on first send.
        console.warn("[ChatView] getUwuSession silent fallback — conversationId stays null");
      }
      try {
        const loaded = await load(chatbotId);
        if (switchGenRef.current !== gen) return;
        // Inject the LLM greeting after load so the thread wipe doesn't race.
        // Delay 600–1200ms so the empty-state animation has time to play.
        if (loaded.length === 0 && !threadErrorRef.current) {
          const pending = greetingStore.take(chatbotId);
          if (pending) {
            const delay = Math.floor(Math.random() * 600) + 600;
            setTimeout(
              () => appendMessage({ role: "assistant", content: pending.greeting }),
              delay,
            );
          }
        }
      } finally {
        if (switchGenRef.current === gen) {
          setSessionResolving(false);
        }
      }
    }
    init();
  }, [chatbotId, load, setMessages, appendMessage, retryKey]);

  // Seed the mood display from the stored conversation mood on thread load.
  // The WebSocket eagerly connects and the server may emit a stored-mood
  // message that races with the thread load.  Fire immediately and then
  // at staggered intervals to definitively overwrite any stale WS mood.
  useEffect(() => {
    if (!threadMood) return;
    const apply = () =>
      llm.setMood(threadMood.mood, threadMood.emoji, threadMood.kaomoji);
    apply();
    const ids = [200, 500, 1000, 2000].map((d) => setTimeout(apply, d));
    return () => ids.forEach(clearTimeout);
  }, [threadMood, llm.setMood]);

  // After each bot reply: increment turn counter, show choice bar
  // every 4 turns.
  const handleBotReply = useCallback(() => {
    quota.refresh();
    // Aggressive status check: poll 3 times over 2s to catch any
    // DB commit latency from server-side auto-block.
    import("../../api/chatbot-status").then(
      ({ getChatbotStatus }) => {
        const check = (attempt: number) => {
          getChatbotStatus(chatbotId!).then((s) => {
            if (s.has_blocked_user) {
              setBlocked();
              window.dispatchEvent(
                new CustomEvent("uwuchat:block-changed", {
                  detail: { chatbotId },
                }),
              );
            } else if (attempt < 3) {
              setTimeout(() => check(attempt + 1), 600);
            }
          }).catch(() => {});
        };
        check(1);
      },
    );
    setTimeout(refreshAnnotations, 1500);
  }, [setBlocked, chatbotId, refreshAnnotations]);

  // UwUChat does not use the filesystem-backed Document model — its
  // knowledge system is the chatbot-scoped KnowledgeFact table.
  // Hardcoded empty here so the framework's citation plumbing stays
  // wired but produces no document references.
  const activeDocs = useMemo(() => [], []);

  // ── Auto-scroll ──────────────────────────────────────────────────────────
  // scrollToBottomRef is populated by MessageList from the virtualisation
  // hook and forces the full message list to mount before measuring
  // scrollHeight, avoiding the estimate-based gap bug.
  const scrollToBottomRef = useRef<() => void>(() => {});

  // Scroll to bottom after conversation load completes.
  // Keyed on conversationLoading (sessionResolving || loading),
  // not just loading — sessionResolving flips false strictly after
  // load() resolves, so gating on the combined flag guarantees the
  // real MessageList has mounted (not the skeleton) when we scroll.
  //
  // Deferred with requestAnimationFrame because React 18 batches
  // setMessages + setLoading(false) + setSessionResolving(false)
  // into a single render — the scroll effect fires in the same
  // render that real messages first appear, before the browser has
  // painted the new layout.  rAF waits for the next frame so
  // scrollHeight reflects the actual content.
  // Scroll to bottom after conversation load completes.
  // Keyed on conversationLoading (sessionResolving || loading),
  // not just loading — sessionResolving flips false strictly after
  // load() resolves, so gating on the combined flag guarantees the
  // real MessageList has mounted (not the skeleton) when we scroll.
  //
  // Double-rAF: first frame waits for browser paint, second waits
  // for ResizeObserver callbacks so scrollHeight is final.
  // Direct DOM scrollTop assignment avoids the virtualizer's
  // setState cycle (scrollToBottom → setPinnedToBottom → re-render)
  // which can cause scroll position to drift as heights stabilize.
  const wasLoadingRef = useRef(conversationLoading);
  useEffect(() => {
    if (wasLoadingRef.current && !conversationLoading && messages.length > 0) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const el = messagesContainerRef.current;
          if (el) {
            el.scrollTop = el.scrollHeight;
          }
        });
      });
    }
    wasLoadingRef.current = conversationLoading;
  }, [conversationLoading, messages.length]);

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
  // TODO(diag): remove after scroll-jank fix verification
  const prevMsgLenRef = useRef(messages.length);
  useEffect(() => {
    const isOwnMessage =
      !loading &&
      messages.length > prevMsgLenRef.current &&
      messages.length > 0 &&
      messages[messages.length - 1]?.role === "user";

    if (isOwnMessage && userScrolledAwayRef.current) {
      // TODO(diag): remove after scroll-jank fix verification
      console.log("[scroll-diag] uwuchat user-sent scroll (was scrolled away) at",
        performance.now(), "msgs:", prevMsgLenRef.current, "→", messages.length);
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
  // TODO(diag): remove after scroll-jank fix verification
  const prevMsgLenForPinRef = useRef(messages.length);
  useLayoutEffect(() => {
    const grew = messages.length > prevMsgLenForPinRef.current;
    prevMsgLenForPinRef.current = messages.length;
    if (!grew || loading) return;
    if (userScrolledAwayRef.current) return;
    const el = messagesContainerRef.current;
    if (!el) return;
    // TODO(diag): remove after scroll-jank fix verification
    console.log("[scroll-diag] uwuchat pin-to-bottom on append at", performance.now(),
      "scrollTop:", el.scrollTop, "→ target:", el.scrollHeight - el.clientHeight);
    el.scrollTop = el.scrollHeight - el.clientHeight;
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // Attach ResizeObserver to the streaming bubble so its height growth
  // drives smooth, synchronous scroll-forward compensation without the
  // virtualizer's expensive full-list mount/dismount cycle.
  const streamingBubbleRef = useStreamingBubbleScroll(
    messagesContainerRef,
    userScrolledAwayRef,
  );

  const scrollToBottom = useCallback(() => {
    scrollToBottomRef.current();
  }, []);

  const handleDeleteMessage = useCallback(
    async (msgIndex: number, botId: number) => {
      setMessages((prev) => {
        const remaining = prev.slice(0, msgIndex);
        const lastBot = remaining.slice().reverse().find(
          (m) => m.role === "assistant" && m.bot_mood,
        );
        if (lastBot?.bot_mood) {
          llm.setMood(
            lastBot.bot_mood,
            lastBot.bot_mood_emoji ?? "😐",
            lastBot.bot_mood_kaomoji ?? "(｡◕ᴗ◕｡)",
          );
        }
        return remaining;
      });
      requestAnimationFrame(() => requestAnimationFrame(() => scrollToBottom()));
      try {
        const { deleteMessage } = await import("../../api/chat");
        await deleteMessage(botId, msgIndex);
      } catch (err) {
        console.error("delete message failed", err);
        await load(botId);
      }
    },
    [setMessages, load, scrollToBottom, llm],
  );

  const handlePlayMessage = useCallback(async (content: string) => {
    try {
      const { synthesizeTTS } = await import("../../api/chat");
      const blob = await synthesizeTTS(content);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch {
      /* TTS unavailable */
    }
  }, []);

  const handleForceProactive = useCallback(async () => {
    if (!chatbotId || !accessToken) return;
    setProactiveLoading(true);
    setProactiveError(null);
    try {
      const { forceProactiveMessage } = await import("../../api/proactive");
      await forceProactiveMessage(chatbotId, accessToken);
      await load(chatbotId);
    } catch (err) {
      setProactiveError(
        err instanceof Error ? err.message : "Failed to send",
      );
    } finally {
      setProactiveLoading(false);
    }
  }, [chatbotId, accessToken, load]);

  const {
    input,
    setInput,
    error,
    setError,
    handleSend,
    sendMessage,
    handleCancel,
    handleKeyDown,
    streamingReplyReady,
    finalizeStreamingReply,
  } = useChatInference({
    messages,
    setMessages,
    appendMessage,
    cancelLoad,
    chatbotId,
    onSelectChatbot,
    conversationIdRef,
    currentSessionIdRef,
    modelPathRef,
    llm,
    activeDocs,
    onShowTyping: useCallback(() => setShowTyping(true), []),
    onHideTyping: useCallback(() => setShowTyping(false), []),
    onBotReply: handleBotReply,
    resolveSession: useCallback(
      async (id: number) => {
        const { getUwuSession } = await import("../../api/chat");
        return getUwuSession(id);
      },
      [],
    ),
  });

  // ── Typewriter reveal hook ─────────────────────────────────────────────
  // Smooth character-by-character reveal of the live stream buffer so the
  // text appears at a natural pace instead of popping in word by word.
  const { revealed: revealedStreamText, caughtUp: revealCaughtUp } =
    useTypewriterReveal(llm.streamBuffer, llm.streaming || streamingReplyReady);

  // Finalize the streaming reply once the real stream ends AND the
  // typewriter reveal has caught up, so the streaming bubble isn't
  // swapped out for the final rendered message mid-animation.
  useEffect(() => {
    if (streamingReplyReady && !llm.streaming && revealCaughtUp) {
      finalizeStreamingReply();
    }
  }, [streamingReplyReady, llm.streaming, revealCaughtUp, finalizeStreamingReply]);

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
      window.dispatchEvent(new Event("knowledge-base-changed"));
    } catch {
      /* unchanged */
    }
  };

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={containerRef} className={styles.root}>
    <div
      className={`d-flex flex-column h-100 ${styles.chatCol}`}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {error && (
        <Alert
          variant="danger"
          dismissible
          onClose={() => setError(null)}
          className={styles.errorAlert}
        >
          {error}
        </Alert>
      )}

      <div
        className={`chat-messages ${styles.messagesArea}`}
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        <MessageList
          messages={messages}
          onCopyMessage={(c) => navigator.clipboard?.writeText(c).catch(() => {})}
          onPlayMessage={handlePlayMessage}
          onDeleteMessage={handleDeleteMessage}
          chatbotId={chatbotId}
          botName={botName}
          botEmoji={botEmoji}
          userName={userName}
          userAvatarImage={avatarImage}
          containerRef={messagesContainerRef}
          scrollToBottomRef={scrollToBottomRef}
          inspectionEnabled={inspectionEnabled}
          flowData={flowData}
          flowLoading={flowLoading}
          costMap={costMap}
          events={events}
          costLoading={costLoading}
          loading={conversationLoading}
          error={threadError}
          onRetryConversation={handleRetryConversation}
          onSendOpener={(text) => sendMessage(text)}
          onAvatarClick={() => setRightPanel(rightPanel?.type === "profile" ? null : { type: "profile" })}
            />
            {/* Proactive-message typing indicator (separate from LLM
                streaming — a pre-rendered message being revealed on a
                timer, not an actual stream). */}
            {proactiveTyping && (
              <TypingBubble name={botName} emoji={botEmoji} />
            )}
            {/* Live status during streaming.
                System bot: shows tool execution, thinking, or
                immersion reading detail via StreamingStatus.
                Persona bots: plain TypingBubble — no tool/thinking
                detail exposed, preserving the character illusion.

                Once text has started streaming (streamBuffer non-empty),
                the standalone StreamingStatus is replaced by an inline
                indicator inside StreamingMessageBubble, but only when
                there is actual tool activity (hasActivity = true). */}
            {!proactiveTyping && (
              chatbotProfile?.is_system_bot ? (
                llm.streaming && !llm.streamBuffer ? (
                  <StreamingStatus
                    statusKey={stabilizedStatus.statusKey}
                    iconName={stabilizedStatus.iconName}
                    label={stabilizedStatus.label}
                  />
                ) : null
              ) : (
                llm.streaming && !llm.streamBuffer && (
                  <TypingBubble name={botName} emoji={botEmoji} />
                )
              )
            )}
            {/* Real-time streaming content — renders streamBuffer directly
                as tokens arrive over the WebSocket, matching framework speed.
                When there is active tool status, passes it inline so the
                user sees a compact status pill below the streamed text. */}
            {(llm.streaming || streamingReplyReady) && llm.streamBuffer && (
              <div ref={streamingBubbleRef}>
                <StreamingMessageBubble
                  content={revealedStreamText}
                  botName={botName}
                  botEmoji={botEmoji}
                  activeStatus={
                    stabilizedStatus.hasActivity
                      ? {
                          statusKey: stabilizedStatus.statusKey,
                          iconName: stabilizedStatus.iconName,
                          label: stabilizedStatus.label,
                        }
                      : null
                  }
                  toolEvents={llm.toolEvents}
                />
              </div>
            )}
            <ModelLoadingIndicator
              visible={false}
            />
      </div>

      {(chatbotStatus.has_blocked_user || chatbotStatus.blocked_by_user) && (
        <div className={styles.blockedBanner}>
          <span>
            {chatbotStatus.has_blocked_user
              ? t("chat.view.has_blocked", { name: botName })
              : t("chat.view.you_blocked", { name: botName })}
          </span>
          {chatbotStatus.blocked_by_user && (
            <button
              onClick={() => unblockBot()}
              className={styles.unblockBtn}
            >
              {t("chat.view.unblock")}
            </button>
          )}
        </div>
      )}
      {!chatbotStatus.is_online && !chatbotStatus.has_blocked_user && !chatbotStatus.blocked_by_user && (
        <div className={styles.offlineBanner}>
          {t("chat.view.offline_message", { name: botName })}
        </div>
      )}
      <UsageBar quota={quota} />
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
        ttsOn={ttsOn}
        sttOn={sttOn}
        onToggleTts={onToggleTts}
        onToggleStt={onToggleStt}
        handleSend={handleSend}
        handleCancel={handleCancel}
        quotaExhausted={
          quota.pct >= 100 ||
          (quota.periodDaysRemaining !== null &&
            quota.periodDaysRemaining < 0)
        }
        blocked={chatbotStatus.has_blocked_user}
        loading={sessionResolving}
        codeMode={{
          enabled: codeModeEnabled,
          mode: codeModeMode,
          pending: codeModePending,
          loading: codeModeLoading,
          select: selectCodeMode,
        }}
      />

      <ChatPopupPanel
        openPanel={openPanel}
        popupAnchor={popupAnchor}
        currentChatbotId={chatbotId}
        onSelectChatbot={(id) => {
          onSelectChatbot?.(id);
          setOpenPanel(null);
        }}
        onCreateUwu={onCreateUwu}
        onClose={() => setOpenPanel(null)}
      />

    </div>

    {/* ── Mobile: compact header when panel is closed ── */}
    {isMobile && rightPanel === null && (
      <div
        className={styles.mobilePanelOverlay}
      >
        <PanelHeader
          compact
          panelTitle={null}
          onClose={() => setRightPanel(null)}
        />
      </div>
    )}

    {/* ── Panel overlay (desktop always, mobile only when content shown) ── */}
    {(rightPanel !== null || !isMobile) && (
      <div className={isMobile ? styles.panelWrapMobile : styles.panelWrap}>
        {/* Drag handle — desktop only */}
        {!isMobile && (
          <div
            onMouseDown={handlePanelDrag}
            className={styles.dragHandle}
          />
        )}
        <div
          ref={panelElRef}
          className={isMobile ? styles.panel : styles.panelWithBorder}
          // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
          style={{ width: isMobile ? "100%" : panelWidth }}
        >
        {/* ── Panel header (only for titled panels — contacts/profile handle their own) ── */}
        {rightPanel && rightPanel.type !== "contacts" && rightPanel.type !== "user-profile" && rightPanel.type !== "profile" && (
          <PanelHeader
            compact={isMobile}
            panelTitle={
              rightPanel?.type === "flow-detail"
              ? t("chat.view.flow_detail_panel")
              : rightPanel?.type === "admin" && rightPanel?.panel === "fastsearch"
              ? t("chat.view.fastsearch_panel")
              : rightPanel?.type === "admin" && rightPanel?.panel === "users"
              ? t("chat.view.users_panel")
              : rightPanel?.type === "admin" && rightPanel?.panel === "promotions"
              ? "Promotions"
              : rightPanel?.type === "admin" && rightPanel?.panel === "calendar"
              ? "Agent Calendar"
              : null
            }
            onClose={() => setRightPanel(null)}
          />
        )}

        {/* ── Panel body ── */}
        <div className={styles.panelBody}>
          {rightPanel?.type === "contacts" && (
            <ContactsSidebar
              variant="fullPage"
              currentChatbotId={chatbotId}
              onSelectUwu={(id) => {
                onSelectChatbot?.(id);
                if (isMobile) setRightPanel(null);
              }}
              onUnfriendChatbot={(id) => {
                if (chatbotId === id) onSelectChatbot?.(null);
              }}
              onCreateUwu={onCreateUwu}
              connecting={connecting}
              connectError={connectError}
              onCloseMobile={() => setRightPanel(null)}
            />
          )}
          {rightPanel?.type === "profile" && chatbotId && (
            <ProfileView
              chatbotId={chatbotId}
              blockStatus={chatbotStatus}
              onBlock={blockBot}
              onUnblock={unblockBot}
            />
          )}
          {rightPanel?.type === "user-profile" && (
            <UserProfilePanel onBack={() => setRightPanel(null)} />
          )}
          {rightPanel?.type === "admin" && rightPanel?.panel === "fastsearch" && (
            <FastSearchStatusPanel />
          )}
          {rightPanel?.type === "admin" && rightPanel?.panel === "users" && (
            <AdminUsersPanel />
          )}
          {rightPanel?.type === "admin" && rightPanel?.panel === "waitlist" && (
            <WaitlistPanel />
          )}
          {rightPanel?.type === "admin" && rightPanel?.panel === "disputes" && (
            <DisputesPanel />
          )}
          {rightPanel?.type === "admin" && rightPanel?.panel === "reports" && (
            <AdminReportsPanel />
          )}
          {rightPanel?.type === "admin" && rightPanel?.panel === "calendar" && chatbotId && (
            <AgentCalendarViewer chatbotId={chatbotId} />
          )}
          {rightPanel?.type === "admin" && rightPanel?.panel === "costs" && (
            <CostTrackingPanel />
          )}
          {rightPanel?.type === "flow-detail" && (
            <FlowDetailPanel
              step={rightPanel.step}
              costStep={rightPanel.costStep}
            />
          )}
        </div>
      </div>
      </div>
    )}

    </div>
  );
}

/* ── Right-panel header (simplified — brand/contacts/account moved to TopBar) ── */

interface PanelHeaderProps {
  compact?: boolean;
  panelTitle: string | null;
  onClose: () => void;
}

function PanelHeader({
  compact,
  panelTitle,
  onClose,
}: PanelHeaderProps) {
  const { t } = useTranslation();

  return (
    <div
      className={
        panelTitle
          ? (compact ? styles.panelHeaderCompact : styles.panelHeaderDefault)
          : styles.panelHeaderCloseOnly
      }
    >
      {panelTitle && (
        <span className={styles.panelTitle}>
          {panelTitle}
        </span>
      )}
      <button type="button" onClick={onClose} title={t("common.close")} className={styles.closeBtn}>
        ×
      </button>
    </div>
  );
}
