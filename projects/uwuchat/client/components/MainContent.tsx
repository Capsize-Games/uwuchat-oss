import { useState, useCallback, useEffect, useRef } from "react";
import ChatView from "./chat/ChatView";
import { ContactsSidebar } from "./panels/ContactsSidebar";
import { useIsMobile } from "../hooks/useIsMobile";
import { isWsConnected, onWsConnectionChange } from "@/features/api/WsApiClient";
import styles from "./MainContent.module.css";

const RECONNECT_GRACE_MS = 1500;

function ReconnectingSpinner() {
  // eslint-disable-next-line no-restricted-syntax -- computed dimension from state/prop
  return <div className={styles.spinner}>{[0, 400, 800].map((delay) => <div key={delay} className={styles.spinnerRing} style={{ animation: `rco-pulse-ring 1.6s ${delay}ms ease-out infinite` }} />)}</div>;
}

interface MainContentProps { chatbotId: number | null; onSelectChatbot: (id: number | null) => void; ttsOn: boolean; onToggleTts: () => void; sttOn: boolean; onToggleStt: () => void; onCreateUwu?: () => void; connecting?: boolean; connectError?: string | null; }

export function MainContent({ chatbotId, onSelectChatbot, ttsOn, onToggleTts, sttOn, onToggleStt, onCreateUwu, connecting, connectError }: MainContentProps) {
  const isMobile = useIsMobile(); const [isContactsOpen, setIsContactsOpen] = useState(false);
  const [connected, setConnected] = useState(isWsConnected); const [showReconnecting, setShowReconnecting] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => { setConnected(isWsConnected()); return onWsConnectionChange(setConnected); }, []);
  useEffect(() => { if (!connected) { reconnectTimer.current = setTimeout(() => setShowReconnecting(true), RECONNECT_GRACE_MS); return () => { if (reconnectTimer.current) { clearTimeout(reconnectTimer.current); reconnectTimer.current = null; } }; } if (reconnectTimer.current) { clearTimeout(reconnectTimer.current); reconnectTimer.current = null; } setShowReconnecting(false); }, [connected]);
  useEffect(() => { if (!isMobile) return; const h = () => setIsContactsOpen((w) => { if (!w) sessionStorage.removeItem("uwuchat_right_panel"); return !w; }); window.addEventListener("uwuchat:toggle-contacts", h); return () => window.removeEventListener("uwuchat:toggle-contacts", h); }, [isMobile]);
  useEffect(() => { const h = () => setIsContactsOpen(false); window.addEventListener("airunner:show-user-profile", h); window.addEventListener("uwuchat:show-user-profile", h); return () => { window.removeEventListener("airunner:show-user-profile", h); window.removeEventListener("uwuchat:show-user-profile", h); }; }, []);
  const handleUnfriend = useCallback((id: number) => { if (chatbotId === id) onSelectChatbot(null); }, [chatbotId, onSelectChatbot]);
  const handleSelectUwu = useCallback((id: number) => { onSelectChatbot(id); }, [onSelectChatbot]);
  const closeContacts = () => setIsContactsOpen(false);

  if (isContactsOpen) return <div className={styles.contactsWrap}><ContactsSidebar variant="fullPage" currentChatbotId={chatbotId} onSelectUwu={handleSelectUwu} onUnfriendChatbot={handleUnfriend} onCreateUwu={onCreateUwu} connecting={connecting} connectError={connectError} onCloseMobile={closeContacts} /></div>;

  return (
    <div className={styles.chatWrap}>
      <ChatView chatbotId={chatbotId} onSelectChatbot={onSelectChatbot} ttsOn={ttsOn} onToggleTts={onToggleTts} sttOn={sttOn} onToggleStt={onToggleStt} onCreateUwu={onCreateUwu} connecting={connecting} connectError={connectError} />
      {showReconnecting && <div className={styles.reconnectOverlay}><div className={styles.reconnectInner}><ReconnectingSpinner /><span>Reconnecting&hellip;</span></div></div>}
    </div>
  );
}
