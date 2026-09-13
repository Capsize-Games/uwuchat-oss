/** Data hook for the pipeline cost admin panel. */

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./useAuth";
import { request } from "@/api/client-base";
import type {
  PipelineConfigEntry,
  PipelineStage,
  PerCustomerUsage,
  OpenRouterModelInfo,
  PipelineKeyConfig,
  ConversationCostSummary,
  CallChainDetail,
  TurnCostAnnotations,
} from "../types/pipeline";

interface PipelineCostData {
  pipelineConfig: PipelineConfigEntry[];
  stages: PipelineStage[];
  perCustomerUsage: PerCustomerUsage | null;
  conversationCost: ConversationCostSummary | null;
  todayCost: ConversationCostSummary | null;
  turnAnnotations: TurnCostAnnotations | null;
  models: OpenRouterModelInfo[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
  refreshAnnotations: () => void;
  syncOpenRouter: () => Promise<{ synced: number }>;
  getCallChain: (callChainId: string) => Promise<CallChainDetail>;
  saveOverride: (key: string, overrides: Partial<PipelineKeyConfig>) => Promise<void>;
  clearOverride: (key: string) => Promise<void>;
  savePrompt: (key: string, prompt: string) => Promise<void>;
}

interface Props {
  chatbotId: number | null;
  enabled?: boolean;
}

export function usePipelineCostData({
  chatbotId,
  enabled = true,
}: Props): PipelineCostData {
  const { accessToken } = useAuth();
  const [config, setConfig] = useState<PipelineConfigEntry[]>([]);
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [usage, setUsage] = useState<PerCustomerUsage | null>(null);
  const [convCost, setConvCost] = useState<ConversationCostSummary | null>(null);
  const [todayCost, setTodayCost] = useState<ConversationCostSummary | null>(null);
  const [turnAnnotations, setTurnAnnotations] = useState<TurnCostAnnotations | null>(null);
  const [models, setModels] = useState<OpenRouterModelInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, s, u, m] = await Promise.all([
        request<PipelineConfigEntry[]>("GET", "/api/admin/pipeline-config"),
        request<PipelineStage[]>("GET", "/api/admin/pipeline-stages"),
        request<PerCustomerUsage>("GET", "/api/admin/token-usage/per-customer?days=30"),
        request<OpenRouterModelInfo[]>("GET", "/api/admin/openrouter-models"),
      ]);
      setConfig(c);
      setStages(s);
      setUsage(u);
      setModels(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchConv = useCallback(async () => {
    if (!chatbotId) return;
    try {
      const c = await request<ConversationCostSummary>("GET", `/api/admin/token-usage/conversation?chatbot_id=${chatbotId}`);
      setConvCost(c);
    } catch { setConvCost(null); }
  }, [chatbotId]);

  const fetchTodayCost = useCallback(async () => {
    if (!chatbotId) return;
    try {
      const t = await request<ConversationCostSummary>("GET", `/api/admin/token-usage/conversation?chatbot_id=${chatbotId}&days=1`);
      setTodayCost(t);
    } catch { setTodayCost(null); }
  }, [chatbotId]);

  const fetchTurnAnnot = useCallback(async () => {
    if (!chatbotId) return;
    try {
      if (!accessToken) return;
      const resp = await fetch(
        `/api/v1/admin/cost-by-turn?chatbot_id=${chatbotId}`,
        { headers: { Authorization: `Bearer ${accessToken}` } },
      );
      if (resp.ok) {
        const data = await resp.json();
        setTurnAnnotations(data);
      }
    } catch { setTurnAnnotations(null); }
  }, [chatbotId, accessToken]);

  // fetchConv / fetchTodayCost / fetchTurnAnnot are small, chatbot-scoped,
  // and have live inline consumers (MessageBubble, InlineCostBreakdown).
  // They remain eager.
  //
  // fetchAll (pipelineConfig / stages / perCustomerUsage / models) has
  // zero live consumer while PipelineCostPanel and MessageInspector are
  // not rendered anywhere in the app.  It runs only when explicitly
  // invoked via refresh() (or saveOverride / savePrompt which call it
  // internally), not automatically on mount.
  useEffect(() => {
    if (enabled) { fetchConv(); fetchTodayCost(); fetchTurnAnnot(); }
  }, [fetchConv, fetchTodayCost, fetchTurnAnnot, enabled]);

  const saveOverride = useCallback(async (key: string, overrides: Partial<PipelineKeyConfig>) => {
    await request("PUT", `/api/admin/pipeline-config/${key}`, { ...overrides } as never);
    await fetchAll();
  }, [fetchAll]);

  const savePrompt = useCallback(async (key: string, prompt: string) => {
    await request("POST", `/api/admin/pipeline-stages/${key}/prompt`, { prompt_template: prompt } as never);
    await fetchAll();
  }, [fetchAll]);

  const clearOverride = useCallback(async (key: string) => {
    await request("DELETE", `/api/admin/pipeline-config/${key}`);
    await fetchAll();
  }, [fetchAll]);

  const syncOpenRouter = useCallback(async () => {
    const result = await request<{ synced: number }>("POST", "/api/admin/openrouter-models/sync");
    await fetchAll();
    return result;
  }, [fetchAll]);

  const getCallChain = useCallback(async (callChainId: string) => {
    return request<CallChainDetail>("GET", `/api/admin/call-chain/${callChainId}`);
  }, []);

  return {
    pipelineConfig: config,
    stages,
    perCustomerUsage: usage,
    conversationCost: convCost,
    todayCost,
    turnAnnotations,
    models,
    loading,
    error,
    refresh: fetchAll,
    refreshAnnotations: fetchTurnAnnot,
    syncOpenRouter,
    getCallChain,
    saveOverride,
    clearOverride,
    savePrompt,
  };
}
