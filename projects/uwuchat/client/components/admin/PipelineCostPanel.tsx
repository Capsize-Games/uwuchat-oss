/** Right-column admin drawer for pipeline cost management. */

import { useState, useEffect } from "react";
import { useAdminCost } from "../../context/AdminCostContext";
import { ConversationCostSummary } from "./ConversationCostSummary";
import { PipelineStageControls } from "./PipelineStageControls";
import { CallChainInspector } from "./CallChainInspector";
import {
  PricingHealthTable,
  fetchPricingHealth,
  fixPricingHealth,
  type PricingHealthResponse,
} from "./PricingHealthTable";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  chatbotId: number | null;
}

export function PipelineCostPanel({ isOpen, onClose, chatbotId }: Props) {
  const data = useAdminCost();
  const [pending, setPending] = useState<Record<string, Record<string, unknown>>>({});
  const [syncing, setSyncing] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [pricingHealth, setPricingHealth] = useState<PricingHealthResponse | null>(null);
  const [checkingPricing, setCheckingPricing] = useState(false);

  useEffect(() => {
    if (isOpen && data.models.length === 0 && !data.loading) {
      data.syncOpenRouter();
    }
  }, [isOpen, data.models.length, data.loading, data.syncOpenRouter]);

  const setPendingStage = (key: string, overrides: Record<string, unknown>) => {
    setPending(p => ({ ...p, [key]: { ...(p[key] || {}), ...overrides } }));
  };

  const handleSaveStage = async (key: string, overrides: Record<string, unknown>) => {
    await data.saveOverride(key, overrides as never);
    setPending(p => { const n = { ...p }; delete n[key]; return n; });
  };

  const handleSavePrompt = async (key: string, prompt: string) => {
    await data.savePrompt(key, prompt);
  };

  const handleResetStage = async (key: string) => {
    await data.clearOverride(key);
  };

  const handleSync = async () => {
    setSyncing(true);
    try { await data.syncOpenRouter(); } finally { setSyncing(false); }
  };

  const handleCheckPricing = async () => {
    setCheckingPricing(true);
    try {
      setPricingHealth(await fetchPricingHealth());
    } catch {
      setPricingHealth(null);
    } finally {
      setCheckingPricing(false);
    }
  };

  const handleFixPricing = async () => {
    setCheckingPricing(true);
    try {
      setPricingHealth(await fixPricingHealth());
    } catch {
      setPricingHealth(null);
    } finally {
      setCheckingPricing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={P.overlay}>
      <div style={P.header}>
        <span style={P.title}>Pipeline Cost</span>
        <div>
          <button style={P.healthBtn} onClick={handleCheckPricing} disabled={checkingPricing}>
            {checkingPricing ? "…" : "Check Pricing"}
          </button>
          <button style={P.syncBtn} onClick={handleSync} disabled={syncing}>
            {syncing ? "Refreshing…" : "Refresh"}
          </button>
          <button style={P.closeBtn} onClick={onClose}>✕</button>
        </div>
      </div>
      {data.error && <div style={P.error}>{data.error}</div>}
      <ConversationCostSummary
        data={data.conversationCost}
        todayCost={data.todayCost}
      />
      <CallChainInspector adminPanelOpen={isOpen} />

      {pricingHealth && (
        <PricingHealthTable
          data={pricingHealth}
          checking={checkingPricing}
          onFix={handleFixPricing}
        />
      )}

      <div style={P.configToggle}>
        <button
          style={P.configToggleBtn}
          onClick={() => setShowConfig(!showConfig)}
        >
          {showConfig ? "▾" : "▸"} Pipeline Configuration
        </button>
      </div>

      {showConfig && (
        <PipelineStageControls
          stages={data.stages}
          models={data.models}
          costBreakdown={data.conversationCost?.breakdown || []}
          pending={pending}
          setPending={setPendingStage}
          onSaveStage={handleSaveStage}
          onSavePrompt={handleSavePrompt}
          onResetStage={handleResetStage}
        />
      )}
    </div>
  );
}

const P = {
  overlay: { position: "fixed" as const, top: 0, right: 0, width: 360, height: "100vh", background: "#1a1a2e", borderLeft: "1px solid rgba(255,255,255,0.1)", display: "flex", flexDirection: "column" as const, zIndex: 200, overflowY: "auto" as const },
  header: { padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)" },
  title: { fontSize: 15, fontWeight: 700, color: "#e0e0e0" },
  closeBtn: { background: "none", border: "none", color: "rgba(255,255,255,0.45)", fontSize: 18, cursor: "pointer", padding: 0 },
  syncBtn: { background: "rgba(255,255,255,0.08)", color: "rgba(255,255,255,0.75)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 6, padding: "4px 10px", cursor: "pointer", fontSize: 12, marginRight: 8 },
  error: { background: "rgba(248,113,113,0.15)", color: "#f87171", padding: "8px 16px", fontSize: 12 },
  healthBtn: { background: "rgba(255,255,255,0.06)", color: "rgba(255,255,255,0.65)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 6, padding: "4px 8px", cursor: "pointer", fontSize: 11, marginRight: 6 },
  configToggle: { borderTop: "1px solid rgba(255,255,255,0.08)", padding: "8px 16px" },
  configToggleBtn: { background: "none", border: "none", color: "rgba(255,255,255,0.45)", cursor: "pointer", fontSize: 11, padding: 0, width: "100%", textAlign: "left" as const },
};
