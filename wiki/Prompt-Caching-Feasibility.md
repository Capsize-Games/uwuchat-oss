# Prompt Caching — Feasibility for the OpenRouter+DeepInfra DIALOGUE Path

Research result for WO-5 (#49). **Verdict: caching is already active,
automatically, on the DIALOGUE path — zero code is required.** This page
records the evidence so nobody re-derives it.

Scope: `deepseek/deepseek-v4-flash` via OpenRouter, pinned to DeepInfra
(see
[`_provider_order_for_model`](../server/src/airunner_services/cloud/llm/model_builders.py:96)
and [`ai_pipeline.py`](../projects/uwuchat/server/ai_pipeline.py:31)).

---

## Q1 — Does DeepInfra support prompt caching for deepseek-v4-flash?

**Yes, automatically.** DeepInfra's official Prompt Caching doc
(https://deepinfra.com/docs — "Prompt Caching" under Chat Completions;
source: `github.com/deepinfra/docs` `chat/prompt-caching.mdx`) states
caching is **automatic — no extra parameters required**: a request whose
prefix matches a recent request on the same model reuses the KV cache,
cutting time-to-first-token and billing cached input at a reduced rate.

DeepInfra's DeepSeek V4 Flash model page
(https://deepinfra.com/deepseek-ai/DeepSeek-V4-Flash) lists the cached
input rate explicitly:

| Tier | Input | Output | Cached input |
|---|---|---|---|
| Standard (1x) | $0.135 / 1M | $0.27 / 1M | $0.027 / 1M (0.2x) |
| Flex (0.8x) | $0.072 / 1M | $0.144 / 1M | $0.0144 / 1M (0.2x) |

OpenRouter's own Prompt Caching guide
(https://openrouter.ai/docs/guides/best-practices/prompt-caching) has a
dedicated DeepSeek section: *"Prompt caching with DeepSeek is automated
and does not require any additional configuration."* DeepSeek is **not**
on the list of providers that require per-message opt-in (only Alibaba
Qwen and Anthropic do, via `cache_control`). Cache reads are reported in
`usage.prompt_tokens_details.cached_tokens` by both OpenRouter and
DeepInfra.

## Q2 — What is the mechanism?

**Automatic server-side prefix caching — no client directive.** This is
the OpenAI/DeepSeek/Gemini-style "implicit" caching, not Anthropic-style
explicit `cache_control` breakpoints:

- The provider caches whatever identical prefix repeats across requests.
- No headers, no `cache_control`, no `X-Title`, no cache-creation call.
- OpenRouter adds **provider sticky routing** to keep a conversation on
  the same upstream so its cache stays warm — but notes sticky routing
  is *not* used when a manual `provider.order` is set. Our code already
  hard-pins `provider: {order: ["deepinfra"], allow_fallbacks: False}`
  (see
  [`create_openrouter_model`](../server/src/airunner_services/cloud/llm/model_builders.py:127)),
  which is exactly the cache-continuity guarantee the docstring claims.
- The existing Anthropic-style machinery
  ([`agent_loop_cache.py`](../server/src/airunner_services/llm/agent_loop_cache.py),
  [`node_prompt_cache_mixin.py`](../server/src/airunner_services/llm/managers/mixins/node_prompt_cache_mixin.py))
  injects `cache_control: {"type": "ephemeral"}` markers; on the DeepSeek
  route these are unnecessary (automatic caching) and OpenRouter drops
  `cache_control` toward non-Anthropic/Alibaba providers anyway.
- Optional DeepInfra extra: a session-scoped `prompt_cache_key` in
  `extra_body` can improve hit rates (DeepInfra doc). It is a
  DeepInfra-native param, so it only applies when calling DeepInfra
  directly — OpenRouter will not forward it. Not needed today.

## Q3 — Estimated cost savings

Rates used: input $0.14/1M, output $0.28/1M (OpenRouter blended for
`deepseek/deepseek-v4-flash`), cached input $0.027/1M (0.2x, DeepInfra
standard; OpenRouter bills its own discounted cached rate, same
`cached_tokens` accounting).

Typical DIALOGUE turn (plan's assumptions: system ≈2K + tool schemas
≈1K + conversation prefix ≈1-4K; measured pre-experiment totals were
~7,800 input tokens for a plain turn — see
[`wiki/UwUChat-Pricing-and-Cost-Economics.md`](UwUChat-Pricing-and-Cost-Economics.md)):

| Scenario | Input cost | vs uncached |
|---|---|---|
| Uncached (7,800 in) | $0.00109 | — |
| 70% cache hit (5,460 cached) | $0.00048 | **-57% of input cost** |
| Full turn incl. ~1,200 out tokens | $0.00143 → $0.00082 | **~-43% of turn cost** |

Absolute scale: top-tier (Devoted) cap is 1,500 turns/user/month →
worst case ~$0.9/user/month. At current small-user scale this is a
single-digit-to-low-tens of dollars per month platform-wide — real but
small, and **already being captured** because caching is automatic.

## Q4 — Implementation complexity

**Zero code.** There is nothing to add:

- Call path (traced):
  [`ai_pipeline.py`](../projects/uwuchat/server/ai_pipeline.py:31) →
  [`create_provider_model_from_runtime`](../server/src/airunner_services/cloud/llm/provider_creation.py:18)
  → [`create_openrouter_model`](../server/src/airunner_services/cloud/llm/model_builders.py:127)
  → `ReasoningAwareChatOpenAI` (a `ChatOpenAI` subclass) against
  `https://openrouter.ai/api/v1`.
- The OpenAI-compatible client needs no cache headers for this route.
  (`default_headers`/`extra_headers` exist on `ChatOpenAI` if an
  Anthropic-style explicit path were ever needed; none is.)
- Accounting is already wired:
  [`generation_usage.py`](../server/src/airunner_services/llm/managers/mixins/generation_usage.py:23)
  reads `prompt_tokens_details.cached_tokens` via
  `cache_read_tokens_from_usage`, and OpenRouter returns a `cache_discount`
  field in responses.
- Only the DeepInfra pin + stable prefix ordering matter — both already
  in place.

## Q5 — Risks

- **Provider lock-in:** caching follows the pinned provider. The
  DeepInfra pin (`allow_fallbacks: False`) is already the cache-continuity
  mechanism; switching providers/models starts cold and (for a non-
  DeepSeek provider) may need explicit `cache_control` if Anthropic/
  Alibaba-hosted. No new lock-in introduced.
- **Cache invalidation:** any byte change in the repeated prefix (system
  prompt edit, tool-schema change, dynamic content placed before the
  stable prefix) invalidates that segment. The prompt builder already
  emits the stable system prompt first; per-turn dynamic elements sit
  after it, so they shrink the hit ratio without killing it.
- **Cache-write billing gotcha:** DeepSeek/DeepInfra bill cache writes at
  the **normal input rate — no 1.25x penalty** (unlike Anthropic and
  OpenAI GPT-5.6+). No storage cost. OpenRouter's DeepSeek section
  confirms writes at original input pricing. Low surprise risk.
- **OpenRouter sticky routing is inert here** (manual `provider.order`
  takes priority) — the hard pin replaces it, which is correct for this
  single-provider deployment.

## Recommendation

**Implement now — but the implementation is zero code.** Prompt caching
is already active, automatically, on the OpenRouter→DeepInfra
`deepseek/deepseek-v4-flash` DIALOGUE path; the DeepInfra pin and the
stable system-prompt-first ordering are the only things that matter for
hit rate, and both already exist. Do **not** add `cache_control` markers
(ignored on this route) and do **not** add DeepInfra's `prompt_cache_key`
(OpenRouter strips provider-specific params). The only concrete actions
are observational: keep watching `prompt_tokens_details.cached_tokens`
(via the already-wired `cache_read_tokens_from_usage`) once real
DeepSeek-era traffic accumulates, and preserve the DeepInfra pin + prefix
ordering in any future model/provider change. If a future DIALOGUE route
ever calls DeepInfra directly (the framework already has a
`ModelService.DEEPINFRA` branch in
[`provider_creation.py`](../server/src/airunner_services/cloud/llm/provider_creation.py:30)),
a session-scoped `prompt_cache_key` becomes a cheap additional lever.
