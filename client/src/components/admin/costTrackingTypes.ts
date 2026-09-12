/** Shared types for CostTrackingPanel. */

export interface SummaryRow {
  pipeline_key: string;
  model_id: string;
  call_count: number;
  /** Rows with a non-null cost_usd — the correct denominator for
   *  cost averages. call_count includes calls made before cost
   *  tracking existed and must not be used for averaging. */
  priced_call_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  cost_usd: number;
  tier_breakdown?: {
    tier: string;
    call_count: number;
    avg_cost_usd: number;
  }[];
}

export interface UsageRow {
  id: number | null;
  pipeline_key: string;
  model_id: string;
  account_id: number | null;
  tenant_key: string | null;
  chatbot_id: number | null;
  call_chain_id: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number | null;
  tier_name: string | null;
  skipped: boolean;
  prompt_char_count: number | null;
  response_char_count: number | null;
  recorded_at: string | null;
}

export interface PaginatedRows {
  total: number;
  limit: number;
  offset: number;
  rows: UsageRow[];
}

export interface AccountOption {
  account_id: number;
  email: string | null;
}

export interface AccountsList {
  accounts: AccountOption[];
}

export interface AccountRequestStats {
  account_id: number;
  email: string | null;
  /** Distinct call_chain_id count — one per user-initiated request,
   *  billed unit (not raw LLM call count). */
  total_requests: number;
  /** Requests where every LLM call in the chain has a priced cost. */
  priced_requests: number;
  total_cost_usd: number;
  /** null when this account has no fully-priced requests yet. */
  avg_cost_per_request_usd: number | null;
}

export interface PerCustomer {
  days: number;
  distinct_tenants: number;
  accounts: AccountRequestStats[];
}
