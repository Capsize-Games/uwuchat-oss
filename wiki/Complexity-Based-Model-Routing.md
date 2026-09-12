# Complexity-Based Model Routing

Every user message in UwUchat is scored for complexity before generation. The DIALOGUE model is dynamically swapped based on that score, and several pipeline stages are gated so that simple messages skip expensive processing. This is a pure heuristic system — no extra LLM call, no network overhead, sub-millisecond latency.

---

## How It Works

```
User message
    │
    ▼
_compute_turn_scores(owner, prompt)       # complexity_scorer.classify()
    │                                       # → owner._complexity_score
    │                                       # → owner._complexity_tier
    ▼
_apply_dialogue_tier_model(owner)          # swaps chat_model.model to tier model
    │
    ▼
LLM generation runs with tier-selected model
    │
    ▼
_restore_dialogue_model(owner)             # restores original model
```

The orchestration lives in
[`server/src/airunner_services/llm/managers/mixins/generation_execution_support.py:528-574`](server/src/airunner_services/llm/managers/mixins/generation_execution_support.py:528).

---

## Complexity Scorer

**File:** [`server/src/airunner_services/llm/complexity_scorer.py`](server/src/airunner_services/llm/complexity_scorer.py)

Returns a float `0.0–1.0` using six weighted heuristics. No LLM call, no network — pure `stdlib` math and regex.

| Signal | Weight | What It Measures |
|---|---|---|
| Length | 15% | `log(word_count + 1) / log(150)` |
| Avg word length | 15% | `(mean_chars − 3) / 6` |
| Question complexity | 20% | Count of words like *why, how, explain, analyze, compare* |
| Clause density | 15% | Presence of *because, although, therefore, however*, etc. |
| Technical terms | 25% | Hits on ~200 STEM/CS terms (*entropy, backpropagation, microservices, sandboxing*, etc.) |
| Structural complexity | 10% | Sentence count, punctuation variety (question marks, semicolons, colons) |

### Public API

```python
from airunner_services.llm.complexity_scorer import score, classify

score("hey what's up")        # → ~0.08  (word-count + avg-word signals only)
score("how does")              # → ~0.18  (question signal fires)
score("explain entropy in")    # → ~0.64  (question + tech-term signals)
classify("explain entropy")    # → (0.64, "complex")
```

Both functions **never raise** — they return `0.0` / `"standard"` on any error.

---

## Tier Configuration

Tiers are defined in the project pipeline config under the `DIALOGUE` key.

**UwUchat:** [`projects/uwuchat/server/ai_pipeline.py:38-56`](projects/uwuchat/server/ai_pipeline.py:38)

```python
"DIALOGUE": {
    "provider": "openrouter",
    "model": "google/gemini-2.5-flash-lite",
    "tiers": [
        {"name": "minimal",  "max_complexity": 0.20, "model": "google/gemini-2.5-flash-lite",
         "description": "Short social responses, acknowledgements"},
        {"name": "standard", "max_complexity": 0.55, "model": "google/gemini-2.5-flash-lite",
         "description": "Normal conversational exchanges"},
        {"name": "complex",  "max_complexity": 1.0,  "model": "google/gemini-2.5-flash",
         "description": "Multi-part questions, tech topics, analysis"},
    ],
}
```

| Tier | Score Range | Model | Example Input |
|---|---|---|---|
| **minimal** | 0.00 – 0.20 | `gemini-2.5-flash-lite` | "yeah", "lol ok", "hey" |
| **standard** | 0.20 – 0.55 | `gemini-2.5-flash-lite` | "what do you think about that?", "tell me a story" |
| **complex** | 0.55 – 1.00 | `gemini-2.5-flash` | "explain the difference between entropy and enthalpy", "how does RAFT consensus work?" |

If the `tiers` list is absent or empty, all messages use the base DIALOGUE `model`.

Tier resolution logic is in [`complexity_scorer._resolve_tier()`](server/src/airunner_services/llm/complexity_scorer.py:436). It walks the tiers list in order and returns the first tier where `max_complexity >= score`.

---

## Complexity-Gated Pipeline Stages

Beyond the DIALOGUE model swap, the complexity score gates other pipeline stages so cheap messages skip expensive LLM calls.

| Stage | `min_complexity` | Effect When Below Threshold |
|---|---|---|
| `TOOL_CLASSIFICATION` | 0.25 | Tools are not classified — no tool calls made |
| `CURIOSITY_ENGINE` | 0.20 | Knowledge gap detection is skipped |
| `INTRA_SESSION_MOOD` | 0.10 | Mood update is skipped (prevents mood thrashing on "lol") |
| `NODE_VALIDATOR` | 0.35 | Response validation is skipped |

Each gated stage still calls `record_usage()` with `skipped=True` and zero tokens so the admin dashboard can show skip rates.

The score is computed **once per turn** and stored on the worker as `owner._complexity_score` and `owner._complexity_tier`. It is never recomputed per stage.

---

## Token Usage Tracking

Every `record_usage()` call accepts `complexity_score` and `tier_name`:

```python
record_usage(
    pipeline_key="DIALOGUE",
    model_id="google/gemini-2.5-flash",
    input_tokens=142,
    output_tokens=89,
    complexity_score=0.64,
    tier_name="complex",
    ...
)
```

The database stores `complexity_score` as `Numeric(5,4)` in the `pipeline_token_usage` table
([`server/src/airunner_services/database/models/pipeline_token_usage.py:48`](server/src/airunner_services/database/models/pipeline_token_usage.py:48)).

This enables per-tier cost breakdowns in the admin dashboard.

---

## Config Loading Order

The pipeline loader resolves config in this priority (last wins):

1. Framework defaults: [`server/src/airunner_services/llm/pipeline_defaults.py`](server/src/airunner_services/llm/pipeline_defaults.py)
2. Project overrides: `projects/<AIRUNNER_PROJECT>/server/ai_pipeline.py` → `PIPELINE_CONFIG`
3. DB overrides: `pipeline_config` table in the public schema

The loader is at [`server/src/airunner_services/llm/pipeline_loader.py`](server/src/airunner_services/llm/pipeline_loader.py).

---

## How to Control It

### Change tier thresholds or models

Edit `tiers` in [`projects/uwuchat/server/ai_pipeline.py`](projects/uwuchat/server/ai_pipeline.py) and restart.

```python
# Example: route complex to a more powerful model
{"name": "complex", "max_complexity": 1.0, "model": "anthropic/claude-sonnet-4"},
```

### Tune scoring weights

Edit the weights in [`server/src/airunner_services/llm/complexity_scorer.py:325-330`](server/src/airunner_services/llm/complexity_scorer.py:325).

```python
_WEIGHT_LENGTH  = 0.15
_WEIGHT_AVG_WORD = 0.15
_WEIGHT_QUESTION = 0.20
_WEIGHT_CLAUSE  = 0.15
_WEIGHT_TECH    = 0.25   # increase to make tech terms more decisive
_WEIGHT_STRUCT  = 0.10
```

### Add or remove technical vocabulary

Edit `_TECHNICAL_VOCABULARY` in [`server/src/airunner_services/llm/complexity_scorer.py`](server/src/airunner_services/llm/complexity_scorer.py). It is a `frozenset` of ~200 terms — add domain-specific jargon that should push a message into the complex tier.

### Disable tier routing entirely

Remove the `tiers` list from the DIALOGUE config. All messages will use the base `model` value.

### DB overrides (admin API)

The `pipeline_config` table supports runtime overrides. Use the admin API at `PUT /api/v1/pipeline/config` to adjust tier models without restarting.

---

## Testing Complexity Scores

```bash
docker compose exec server python -c "
from airunner_services.llm.complexity_scorer import classify
tests = [
    'hey',
    'lol yeah',
    'what do you think?',
    'explain how photosynthesis works',
    'compare TCP and UDP congestion control algorithms',
]
for t in tests:
    score, tier = classify(t)
    print(f'{score:.3f}  {tier:10s}  {t}')
"
```

---

## Related Files

| File | Role |
|---|---|
| [`server/src/airunner_services/llm/complexity_scorer.py`](server/src/airunner_services/llm/complexity_scorer.py) | Scoring algorithm and tier resolution |
| [`server/src/airunner_services/llm/managers/mixins/generation_execution_support.py`](server/src/airunner_services/llm/managers/mixins/generation_execution_support.py) | Orchestration — `_compute_turn_scores`, `_apply_dialogue_tier_model`, `_restore_dialogue_model` |
| [`server/src/airunner_services/llm/pipeline_loader.py`](server/src/airunner_services/llm/pipeline_loader.py) | Config loading and merge |
| [`server/src/airunner_services/llm/pipeline_defaults.py`](server/src/airunner_services/llm/pipeline_defaults.py) | Framework default tier config |
| [`projects/uwuchat/server/ai_pipeline.py`](projects/uwuchat/server/ai_pipeline.py) | UwUchat tier overrides |
| [`server/src/airunner_services/llm/token_usage.py`](server/src/airunner_services/llm/token_usage.py) | Usage recording with complexity metadata |
| [`server/src/airunner_services/llm/curiosity_engine.py`](server/src/airunner_services/llm/curiosity_engine.py) | `min_complexity` gate for curiosity engine |
| [`plans/ai-pipeline-phases-2-5.md`](plans/ai-pipeline-phases-2-5.md) | Original design document (Phase 1.5) |
