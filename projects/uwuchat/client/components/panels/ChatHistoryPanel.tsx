import { useState, useEffect, useCallback } from "react";
import { useEffectOnce } from "@/hooks/useEffectOnce";
import { useTranslation } from "react-i18next";
import Spinner from "react-bootstrap/Spinner";
import LucideIcon from "@/components/shared/LucideIcon";
import { queryResources, updateResource } from "@/api/client";
import { waitForBootstrap } from "@/features/api/WsApiClient";
import { getConversationPreviews } from "../../api/chat";
import { stripMarkdownPreview } from "../../utils/stripMarkdownPreview";
import type { ResourceRecord } from "../../types/api";
import UwuRow, { type UwuRecord as UwuRowRecord } from "./UwuRow";
import { useOnboardingTourContext } from "../onboarding/OnboardingTourContext";
import styles from "./ChatHistoryPanel.module.css";

interface UwuRecord extends ResourceRecord, UwuRowRecord { deleted?: boolean; offline_until?: string | null; }

function isDeceased(u: UwuRecord): boolean { return u.is_deceased === true; }
function isBlocked(u: UwuRecord): boolean { return u.has_blocked_user === true || u.blocked_by_user === true; }

function SectionLabel({ label, style, onHelpClick, anchorStep }: { label: string; style?: React.CSSProperties; onHelpClick?: () => void; anchorStep?: "system-bot" | "rp-bot"; }) {
  return (
    <div data-onboarding-anchor={anchorStep} className={styles.sectionLabel}>
      <div className={`${styles.sectionLabelInner} ${style ? "" : ""}`} style={style}>{label}</div>
      {onHelpClick && <button type="button" onClick={(e) => { e.stopPropagation(); onHelpClick(); }} title="What is this?" className={styles.helpBtn} aria-label="Help"><LucideIcon name="circle-help" size={14} /></button>}
    </div>
  );
}

export function ChatHistoryPanel({ currentChatbotId, onSelectUwu, onUnfriendChatbot, onCreateUwu, onClose }: {
  currentChatbotId: number | null; onSelectUwu: (id: number) => void; onUnfriendChatbot?: (id: number) => void; onCreateUwu?: () => void; onClose?: () => void;
}) {
  const { t } = useTranslation(); const { replay } = useOnboardingTourContext();
  const [uwus, setUwus] = useState<UwuRecord[]>([]); const [loading, setLoading] = useState(true);
  const [confirmingId, setConfirmingId] = useState<number | null>(null); const [previews, setPreviews] = useState<Record<number, string>>({});

  const applyRoster = useCallback((records: UwuRecord[]) => { setUwus(records); const ids = records.map((u) => u.id); getConversationPreviews(ids).then((p) => { const n: Record<number, string> = {}; for (const [idStr, pr] of Object.entries(p)) if (pr.preview) n[Number(idStr)] = stripMarkdownPreview(pr.preview); setPreviews(n); }).catch(() => {}); }, []);
  const load = useCallback(async () => { try { const res = await queryResources("Chatbot", { deleted: false }); applyRoster((res?.records ?? []) as UwuRecord[]); } catch {} finally { setLoading(false); } }, [applyRoster]);

  useEffectOnce(() => { let c = false; waitForBootstrap().then((payload) => { if (c) return; applyRoster((payload.chatbots as UwuRecord[] | undefined) ?? []); }).catch(() => { if (!c) load(); }).finally(() => { if (!c) setLoading(false); }); return () => { c = true; }; });
  useEffect(() => { const h = () => { load(); }; window.addEventListener("uwuchat:uwu-created", h); window.addEventListener("uwuchat:block-changed", h); window.addEventListener("uwuchat:chatbot-deceased", h); return () => { window.removeEventListener("uwuchat:uwu-created", h); window.removeEventListener("uwuchat:block-changed", h); window.removeEventListener("uwuchat:chatbot-deceased", h); }; }, [load]);

  const systemBots = uwus.filter((u) => u.is_system_bot); const personas = uwus.filter((u) => !u.is_system_bot && !isBlocked(u));
  const deceased = personas.filter(isDeceased); const active = personas.filter((u) => !isDeceased(u));

  const renderRow = (u: UwuRecord) => <UwuRow key={u.id} u={u} isActive={u.id === currentChatbotId} confirming={confirmingId === u.id} previewText={previews[u.id]} onSelect={() => onSelectUwu(u.id)} onRequestRemove={(e) => { e.stopPropagation(); setConfirmingId(u.id); }} onCancelRemove={(e) => { e.stopPropagation(); setConfirmingId(null); }} onConfirmRemove={async (e) => { e.stopPropagation(); setConfirmingId(null); try { await updateResource("Chatbot", u.id, { deleted: true }); if (u.id === currentChatbotId) onUnfriendChatbot?.(u.id); await load(); } catch {} }} />;

  return (
    <div className={`d-flex flex-column overflow-hidden ${styles.wrap}`}>
      <div className="scroll-panel">
        {loading ? <div className="p-3 text-center"><Spinner animation="border" size="sm" /></div>
        : uwus.length === 0 ? <div className={styles.emptyState}><div className={styles.emptyIcon}>👋</div><p className="small text-muted mb-0">{t("sidebar.no_contacts")}</p></div>
        : <>
          {systemBots.length > 0 && <><SectionLabel label={t("sidebar.assistant")} onHelpClick={() => replay("system-bot")} anchorStep="system-bot" />{systemBots.map(renderRow)}</>}
          {personas.length > 0 && <>{systemBots.length > 0 && <SectionLabel label={t("sidebar.role_play")} anchorStep="rp-bot" />}{active.map(renderRow)}{deceased.length > 0 && <><SectionLabel label={t("sidebar.deceased")} />{deceased.map(renderRow)}</>}</>}
        </>}
      </div>
    </div>
  );
}
