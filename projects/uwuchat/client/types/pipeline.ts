/** Shared types for the pipeline cost admin panel. */

export interface PipelineKeyConfig {
  provider: string;
  model: string | null;
  enabled: boolean;
  interval_turns?: number;
  trigger?: string;
  max_tokens?: number;
  temperature?: number;
  openrouter_provider?: string | null;
  openrouter_provider_category?: string;
  tiers?: TierConfig[];
  min_complexity?: number;
  safety?: SafetyConfig;
}

export interface TierConfig {
  name: string;
  max_complexity: number;
  model: string;
  description: string;
}

export interface SafetyConfig {
  hard_rules_min_risk: string;
  health_disclaimer_min_risk: string;
  flag_high_risk: boolean;
}

export interface PipelineConfigEntry {
  key: string;
  merged_config: PipelineKeyConfig;
  has_db_override: boolean;
}

export interface TokenUsageBreakdown {
  pipeline_key: string;
  model_id: string;
  avg_input: number;
  avg_output: number;
  avg_cost_usd: number;
}

export interface PerCustomerUsage {
  days: number;
  distinct_tenants: number;
  estimated_cost_per_customer_usd: number;
  avg_input_per_customer: number;
  avg_output_per_customer: number;
  breakdown: TokenUsageBreakdown[];
}

export interface OpenRouterModelInfo {
  model_id: string;
  display_name: string;
  input_price_per_mtok: number;
  output_price_per_mtok: number;
  cache_read_per_mtok: number;
  context_length: number;
  latency_p50_ms: number | null;
  throughput_tps: number | null;
  fetched_at: string | null;
}

export interface ConversationCostBreakdownItem {
  pipeline_key: string;
  model_id: string;
  call_count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  pct_of_total: number;
}

export interface ConversationCostSummary {
  chatbot_id: number;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_skipped_calls: number;
  estimated_saved_usd: number;
  breakdown: ConversationCostBreakdownItem[];
}

export interface PipelineOverrides {
  [pipeline_key: string]: { model?: string; enabled?: boolean };
}

export interface CallChainStep {
  sequence: number;
  pipeline_key: string;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
  skipped: boolean;
  prompt_char_count: number | null;
  response_char_count: number | null;
  complexity_score: number | null;
  tier_name: string | null;
  recorded_at: string | null;
  /** Real prompt text (superuser inspector only, tenant-scoped). */
  prompt_text?: string | null;
  /** Real response text (superuser inspector only, tenant-scoped). */
  response_text?: string | null;
}

export interface CallChainDetail {
  call_chain_id: string;
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  steps: CallChainStep[];
  trigger_type: string;
}

export interface TurnCostAnnotation {
  call_chain_id: string;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface TurnCostAnnotations {
  annotations: Record<string, TurnCostAnnotation>;
  total_cost_usd: number;
}

export interface PipelineStage {
  key: string;
  label: string;
  description: string;
  trigger: string;
  model: string | null;
  enabled: boolean;
  config: Record<string, unknown>;
  prompt_template: string | null;
  prompt_source: string | null;
}
