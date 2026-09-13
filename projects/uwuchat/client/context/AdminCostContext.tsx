import React, { createContext, useContext, useEffect } from "react";
import { useAuth } from "../hooks/useAuth";
import { usePipelineCostData } from "../hooks/usePipelineCostData";
import type {
  PipelineConfigEntry,
  PipelineStage,
  PerCustomerUsage,
  OpenRouterModelInfo,
  PipelineKeyConfig,
  ConversationCostSummary,
  TurnCostAnnotations,
  CallChainDetail,
} from "../types/pipeline";

export interface AdminCostData {
  adminPanelOpen: boolean;
  isSuperuser: boolean;
  chatbotId: number | null;
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
  saveOverride: (k: string, o: Partial<PipelineKeyConfig>) => Promise<void>;
  clearOverride: (k: string) => Promise<void>;
  savePrompt: (key: string, prompt: string) => Promise<void>;
  syncOpenRouter: () => Promise<{ synced: number }>;
  getCallChain: (cid: string) => Promise<CallChainDetail>;
}

const noop = async () => { throw new Error("No AdminCostProvider"); };

const DEFAULT: AdminCostData = {
  adminPanelOpen: false,
  isSuperuser: false,
  chatbotId: null,
  pipelineConfig: [],
  stages: [],
  perCustomerUsage: null,
  conversationCost: null,
  todayCost: null,
  turnAnnotations: null,
  models: [],
  loading: false,
  error: null,
  refresh: () => {},
  refreshAnnotations: () => {},
  saveOverride: noop,
  clearOverride: noop,
  savePrompt: noop,
  syncOpenRouter: noop,
  getCallChain: noop,
};

export const AdminCostContext = createContext<AdminCostData>(DEFAULT);

export function useAdminCost(): AdminCostData {
  return useContext(AdminCostContext);
}

interface ProviderProps {
  children: React.ReactNode;
  chatbotId: number | null;
  adminPanelOpen: boolean;
}

export function AdminCostProvider({
  children,
  chatbotId,
  adminPanelOpen,
}: ProviderProps) {
  const { user } = useAuth();
  const isSuperuser = user?.is_superuser === true;
  const data = usePipelineCostData({
    chatbotId: isSuperuser ? chatbotId : null,
    enabled: isSuperuser,
  });

  useEffect(() => {
    if (adminPanelOpen && isSuperuser && data.models.length === 0 && !data.loading) {
      data.syncOpenRouter().catch(() => {});
    }
  }, [adminPanelOpen, isSuperuser, data.models.length, data.loading]);

  const value: AdminCostData = {
    adminPanelOpen: adminPanelOpen && isSuperuser,
    isSuperuser,
    chatbotId,
    pipelineConfig: data.pipelineConfig,
    stages: data.stages,
    perCustomerUsage: data.perCustomerUsage,
    conversationCost: data.conversationCost,
    todayCost: isSuperuser ? data.todayCost : null,
    turnAnnotations: isSuperuser ? data.turnAnnotations : null,
    models: data.models,
    loading: data.loading,
    error: data.error,
    refresh: data.refresh,
    refreshAnnotations: isSuperuser ? data.refreshAnnotations : () => {},
    saveOverride: data.saveOverride,
    clearOverride: data.clearOverride,
    savePrompt: data.savePrompt,
    syncOpenRouter: data.syncOpenRouter,
    getCallChain: data.getCallChain,
  };

  return (
    <AdminCostContext.Provider value={value}>
      {children}
    </AdminCostContext.Provider>
  );
}
