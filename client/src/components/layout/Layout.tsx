// ── Layout ──────────────────────────────────────────────────────────────
import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import CanvasPanel from "../panels/CanvasPanel";
import CivitaiBrowserPanel from "../panels/civitai-browser/CivitaiBrowserPanel";
import DownloadTray from "../downloads/DownloadTray";
import TopBar from "./TopBar";
import { LeftIconBar } from "./IconBar";
import { CanvasProvider } from "../../features/canvas";
import WelcomeScreen from "./WelcomeScreen";
import FooterStats from "./FooterStats";
import LiveIndicator from "./LiveIndicator";
import { EdgeOnly } from "../../context/DeploymentContext";
import { useMenuAction } from "./action-menu-bar";
import styles from "./Layout.module.css";
import { useLocalStorage } from "../../hooks/useLocalStorage";

const HANDLE_W = 4;
const CHAT_MIN = 260;
const CANVAS_MIN = 400;

type PanelId = "civitai_browser";

interface LayoutProps {
  children: ReactNode;
  rightPanel: PanelId | null;
  onRightPanel: (id: PanelId) => void;
  showChat: boolean;
  onToggleChat: () => void;
  showCanvas: boolean;
  onToggleCanvas: () => void;
  onOpenSettings: () => void;
  onSelectConversation: (id: number | null) => void;
  bottomBarSlot?: React.ReactNode;
}

/* ── Drag state (module-level, captured at mousedown) ── */
let dragState: {
  startX: number;
  startChatW: number;
  maxChatW: number;
  setChatW: (w: number) => void;
} | null = null;

function onGlobalMouseMove(e: MouseEvent) {
  if (!dragState) return;
  const delta = e.clientX - dragState.startX;
  dragState.setChatW(
    Math.max(
      CHAT_MIN,
      Math.min(
        dragState.maxChatW,
        dragState.startChatW + delta,
      ),
    ),
  );
}

function onGlobalMouseUp() {
  if (!dragState) return;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  dragState = null;
}

if (typeof window !== "undefined") {
  window.addEventListener(
    "mousemove",
    onGlobalMouseMove,
  );
  window.addEventListener("mouseup", onGlobalMouseUp);
}

export default function Layout({
  children,
  rightPanel,
  onRightPanel,
  showChat,
  onToggleChat,
  showCanvas,
  onToggleCanvas,
  onOpenSettings,
  bottomBarSlot,
}: LayoutProps) {
  const panelsRef = useRef<HTMLDivElement>(null);
  const [panelsWidth, setPanelsWidth] = useState(0);
  const [chatW, setChatW] = useLocalStorage("airunner_chat_w", 400);

  useEffect(() => {
    const el = panelsRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries)
        setPanelsWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Clamp chat width when container or visibility changes.
  useEffect(() => {
    if (panelsWidth === 0 || !showChat) return;
    const max =
      panelsWidth -
      (showCanvas ? CANVAS_MIN + HANDLE_W : 0);
    if (chatW > max) setChatW(Math.max(CHAT_MIN, max));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panelsWidth, showChat, showCanvas]);


  // ── Respond to action-menu events ──────────────────────────────────
  useMenuAction(
    useCallback(
      (action) => {
        switch (action.type) {
          case "view:toggle-chat":
            onToggleChat();
            break;
          case "view:toggle-canvas":
            onToggleCanvas();
            break;
          case "view:toggle-civitai":
            onRightPanel("civitai_browser");
            break;
        }
      },
      [onToggleChat, onToggleCanvas, onRightPanel],
    ),
  );

  // Sync layout panel state back to the action menu bar
  useEffect(() => {
    window.dispatchEvent(
      new CustomEvent("airunner:layout-state", {
        detail: {
          showChat,
          showCanvas:
            showCanvas &&
            rightPanel !== "civitai_browser",
          showCivitai:
            rightPanel === "civitai_browser",
        },
      }),
    );
  }, [showChat, showCanvas, rightPanel]);

  const makeHandle = () => {
    const onDown = (e: React.MouseEvent) => {
      e.preventDefault();
      dragState = {
        startX: e.clientX,
        startChatW: chatW,
        maxChatW:
          panelsWidth - CANVAS_MIN - HANDLE_W,
        setChatW,
      };
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    };
    return (
      <div
        className="resize-handle"
        onMouseDown={onDown}
      />
    );
  };

  return (
    <div className="app-shell">
      <TopBar />

      <div className="main-row">
        <LeftIconBar
          showChat={showChat}
          showCanvas={showCanvas}
          rightPanel={rightPanel}
          onToggleChat={onToggleChat}
          onToggleCanvas={onToggleCanvas}
          onRightPanel={onRightPanel}
          onOpenSettings={onOpenSettings}
          bottomSlot={bottomBarSlot}
        />

        {/* ── Panels container ── */}
        <div
          ref={panelsRef}
          className="flex-grow-1 d-flex overflow-hidden min-w-0"
        >
          {/* Chat */}
          {showChat && (
            <div
              className={
                "chat-panel " + (
                  showCanvas
                    ? styles.chatPanelCanvasOpen
                    : styles.chatPanelAlone
                )
              }
              style={
                showCanvas
                  ? { width: chatW }
                  : undefined
              }
            >
              {children}
            </div>
          )}

          {showChat && showCanvas && makeHandle()}

          {/* Main content */}
          {showCanvas && (
            <div
              className="flex-grow-1 overflow-hidden min-w-0"
            >
              {rightPanel === "civitai_browser" ? (
                <CivitaiBrowserPanel />
              ) : (
                <CanvasProvider>
                  <CanvasPanel />
                </CanvasProvider>
              )}
            </div>
          )}

          {/* Welcome screen */}
          {!showChat && !showCanvas && (
            <WelcomeScreen
              onOpenChat={onToggleChat}
              onOpenCanvas={onToggleCanvas}
              onOpenCivitai={() =>
                onRightPanel("civitai_browser")
              }
            />
          )}
        </div>
      </div>

      <DownloadTray />

      <div
        className={"footer-bar d-flex justify-content-between align-items-center " + styles.footerBar}
      >
        <span>
          &copy; {new Date().getFullYear()} Capsize
          LLC &mdash; All rights reserved.
        </span>
        <div
          className={"d-flex align-items-center " + styles.footerRight}
        >
          <EdgeOnly>
            <FooterStats />
          </EdgeOnly>
          <LiveIndicator />
        </div>
      </div>
    </div>
  );
}
