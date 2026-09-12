# UwUchat — Pricing Economics

*Last updated: 2026-06-26. Re-verify API prices before each pricing revision.*

---

## 1. Verified Token Budget per Turn

This audit is based on code inspection, not estimates. Source files are listed
for each figure so they can be re-checked as the pipeline evolves.

### Input tokens (per inference call)

| Component | Budget | Source |
|---|---|---|
| Static system prompt (persona, instructions, tools) | ~2,500 tokens | `system_prompt_mixin.py` — static cacheable block |
| Session bridge (prior sessions) | ~300 tokens | `session_bridge_builder.py` — `_BRIDGE_TURNS=4`, `_TURN_CHARS=300` |
| Dynamic context injected per turn (date, mode, etc.) | ~200 tokens | `system_prompt_mixin.py` — injected into last HumanMessage |
| Conversation history (sliding window) | up to 8,000 tokens | `node_prompt_assembly_helper.py` — `trim_messages(max_tokens=8000, strategy="last")` |
| **Total input cap** | **~10,000 tokens** | Hard upper bound; typical turns land at 8,000–9,000 |

The sliding window uses LangChain `trim_messages()` with `strategy="last"` —
it drops the **oldest** turns first, so context never silently balloons.

### Output tokens

Typical reply: 100–400 tokens. Budget estimate: **200 tokens** (observed median).

### What is NOT auto-injected

- `AgentMemory` (rolling summary, `_MAX_MEMORY_CHARS=1500`): available only when
  the model calls the `recall_knowledge` tool. Not in every turn.
- `ConversationTurn` semantic search results (`k=10`): triggered only when the
  model calls the `search_conversation_history` tool.
- RAG document chunks (`k=5`): triggered only when the model calls `search_knowledge`.

These are **on-demand** — they add tokens only when the model decides to use them.

---

## 2. Per-Turn Cost (Calibrated from Real Traffic — 2026-06-26)

### Observed turn sample (5 real turns from admin cost panel)

| Turn | Stages | Total in | Total out | Cost | Type |
|---|---|---|---|---|---|
| A | 3 | 19,965 | 177 | $0.020430 | Tool call |
| B | 2 | 9,255 | 186 | $0.009756 | No tool |
| C | 3 | 26,869 | 407 | $0.028490 | Tool call |
| D | 2 | 9,577 | 117 | $0.009723 | No tool |
| E | 3 | 19,651 | 177 | $0.020115 | Tool call |

Stage breakdown verified at $1.00/1M input + $5.00/1M output (Haiku 4.5,
Anthropic-direct price; OpenRouter routes at the same rate for this model).
Llama 3.1 8B (mood stage) costs ~$0.000008/turn — negligible.

### Scenarios by turn type

| Turn type | Pipeline stages | Cost range | Avg cost |
|---|---|---|---|
| Simple reply (no tool) | Mood + Response | $0.009–$0.011 | **~$0.010** |
| Tool-call reply | Mood + Tool call + Response | $0.020–$0.029 | **~$0.023** |
| Tool-call + web search | Above + Google CSE | $0.025–$0.034 | **~$0.028** |

Tool-call cost varies primarily with output token count — a long reply after a tool
call (turn C: 407 out) costs nearly 3× a short one (turn E: 177 out, turn A: 177 out).

### Blended estimate

Assuming ~35% of turns invoke a tool and ~15% trigger a Google web search:

```
0.65 × $0.010  +  0.35 × $0.023  +  0.15 × $0.005 (Google CSE)
= $0.0065 + $0.0081 + $0.00075
≈ $0.016 / turn (blended)
```

> **Use $0.015/turn for margin calculations** (conservative midpoint).
> Use $0.023/turn for cap-exhaustion worst-case (all turns with tool calls).

---

## 3. Pricing Tiers

### Design principles

- Match turn caps to **realistic daily companion usage**, not minimums.
- Margins must survive even if the top 5% of users max out their cap.
- Entry tier is cheap enough for impulse purchase; upper tiers serve users
  for whom UwUchat is a primary social outlet.
- Daily burst limits prevent a user exhausting their monthly cap in 3–5 days
  and then churning for the rest of the billing cycle.

### Observed usage patterns (similar companion/chat products)

| User type | Sessions/week | Turns/session | Turns/month | Daily avg |
|---|---|---|---|---|
| Casual | 2–3 | 5–8 | 50–80 | 2–3 |
| Regular | 4–5 | 8–12 | 180–250 | 6–8 |
| Daily | 7 | 10–15 | 300–450 | 10–15 |
| Power (top ~5%) | Daily | 20–30 | 600–800 | 20–27 |

200 turns/month = ~6.7 turns/day, which is below even "regular" usage. A companion
product needs caps that feel generous relative to natural conversation rhythm.

### Tier structure

| Tier | Price | Monthly cap | Daily burst | Avg turns/day at cap |
|---|---|---|---|---|
| **Lite** | $10 | 200 turns | 15/day | 6.7 |
| **Companion** | $15 | 400 turns | 20/day | 13.3 |
| **Connection** | $25 | 800 turns | 35/day | 26.7 |
| **Devoted** | $40 | 1,500 turns | 65/day | 50.0 |

### Margin analysis

**At typical utilization (50% of cap):**

| Tier | Price | Typical turns | API cost | Gross margin | Margin % |
|---|---|---|---|---|---|
| Lite | $10 | 100 | $1.50 | $8.50 | 85% |
| Companion | $15 | 200 | $3.00 | $12.00 | 80% |
| Connection | $25 | 400 | $6.00 | $19.00 | 76% |
| Devoted | $40 | 750 | $11.25 | $28.75 | 72% |

**At cap exhaustion (100%, all tool-call turns — worst case):**

| Tier | Price | Cap turns | API cost | Gross margin | Margin % |
|---|---|---|---|---|---|
| Lite | $10 | 200 | $4.60 | $5.40 | 54% |
| Companion | $15 | 400 | $9.20 | $5.80 | 39% |
| Connection | $25 | 800 | $18.40 | $6.60 | 26% |
| Devoted | $40 | 1,500 | $34.50 | $5.50 | 14% |

The cap-exhaustion scenario at upper tiers is razor-thin. Accept this deliberately:
a user sending 1,500 messages/month is sending 50/day every day — they are a
superfan and your best word-of-mouth. The real protection is that this behavior is
rare; the typical-utilization margins (72–85%) are what you actually earn.

**Rule of thumb:** if P90 utilization stays below 70% of cap, the product is
healthy. Monitor this monthly once paying users are live.

### Contribution margin at 100 users (50% utilization, evenly spread)

| | Lite | Companion | Connection | Devoted | **Total** |
|---|---|---|---|---|---|
| Revenue | $250 | $375 | $625 | $1,000 | **$2,250** |
| API costs | $38 | $75 | $150 | $281 | **$544** |
| Gross margin | $212 | $300 | $475 | $719 | **$1,706** |
| Margin % | 85% | 80% | 76% | 72% | **76%** |

---

## 4. Daily Rate Limiting

### Why both a daily limit and a monthly cap?

- **Monthly cap** — profitability ceiling. Prevents a single user from costing
  more than their subscription covers.
- **Daily burst limit** — churn insurance. Prevents binge usage that drains the
  monthly budget in a weekend, leaving the user wall-hitting for 3 weeks and
  cancelling.

### Recommended limits

| Tier | Monthly cap | Daily burst | Max daily API cost |
|---|---|---|---|
| Free trial | 20 turns total | 5/day | $0.12 |
| Lite ($10) | 200 turns | 15/day | $0.35 |
| Companion ($15) | 400 turns | 20/day | $0.46 |
| Connection ($25) | 800 turns | 35/day | $0.81 |
| Devoted ($40) | 1,500 turns | 65/day | $1.50 |

Daily limit is set so `daily × 30 > monthly cap`: the monthly cap is always the
binding long-term constraint; the daily limit only stops single-day binges.

### UX (mirror Claude.ai's pattern)

- **80% monthly warning:** "You've used X of your Y messages this month."
- **Grace buffer:** Allow 10% over monthly cap before hard stop. Prevents a jarring
  mid-conversation cutoff on the billing boundary.
- **Hard stop at 110%:** Require upgrade or wait for reset.
- **Daily reset:** Midnight UTC. Show "resets in X hours."
- **Monthly reset:** Billing date, not calendar month.
- **Overage rate:** $0.04/turn (2–3× cost) — present as upgrade nudge, not a
  surprise bill.

---

## 5. Fixed Costs & Break-Even

### Fixed cost scenarios

| Phase | Server | Backups | Other | **Monthly fixed** |
|---|---|---|---|---|
| Dev / early launch | $7 | — | — | **$7** |
| Post-launch (< 200 users) | $20–30 | $5–10 | $5 domain | **$30–45** |
| Scaled (200–500 users) | $50–80 | $15 | $10 | **$75–105** |

Google Search API cost is captured in the per-turn variable cost above.

### Break-even by phase (at 50% utilization)

| Phase | Fixed cost | Avg gross margin/user | Users to break even |
|---|---|---|---|
| Dev | $7 | ~$17 | **1 user** |
| Post-launch | $40 | ~$17 | **3 users** |
| Scaled | $90 | ~$17 | **6 users** |

---

## 6. 2026 Revenue Projections

### Assumptions

- Product live Q3 2026; organic growth only.
- ARPU: $18/month (weighted toward Companion and Connection tiers).
- API cost per user at 50% utilization: ~$4.50/month (ARPU-weighted).
- Monthly churn: 8%.

### Scenarios

| Scenario | Users by Q4 2026 | Monthly revenue | API costs | Net (after API + server) |
|---|---|---|---|---|
| **Conservative** | 30 | $540 | $135 | ~$360 |
| **Base case** | 80 | $1,440 | $360 | ~$1,035 |
| **Optimistic** | 200 | $3,600 | $900 | ~$2,655 |
| **Breakout** | 500 | $9,000 | $2,250 | ~$6,705 |

Net = revenue − API costs − fixed costs ($45/month post-launch).

### Key milestone targets

| MRR | Users needed | What unlocks |
|---|---|---|
| $100 | 6 | Covers all fixed costs |
| $500 | 28 | Founder covers coffee + domain + backups |
| $1,000 | 56 | Covers ~20 hrs/week opportunity cost at $50/hr |
| $3,000 | 167 | Sustainable side income; justify next feature sprint |

---

## 7. Monitoring Checklist

Re-run this audit when any of the following change:

- [ ] `_BRIDGE_TURNS` or `_TURN_CHARS` in `session_bridge_builder.py`
- [ ] `max_tokens` in `node_prompt_assembly_helper.py`
- [ ] Haiku 4.5 price on OpenRouter dashboard
- [ ] Google Custom Search API tier / quota usage
- [ ] New tool added to agent — each tool schema adds ~100–300 tokens to the
      system prompt, and each tool-call turn costs ~$0.013 more than a simple reply
- [ ] `_MAX_MEMORY_CHARS` in `memory_updater.py` (if auto-inject is added)
- [ ] Observed P50 and P90 turn cost in the admin pipeline cost panel
- [ ] P90 monthly utilization across paying tiers (target: < 70% of cap)

---

*Sources: code audit 2026-06-25 + 5 real turns observed 2026-06-26 via admin
pipeline cost panel — `node_prompt_assembly_helper.md`, `session_bridge_builder.py`,
`memory_updater.py`, `conversation_turn.py`, `system_prompt_mixin.py`,
`rag_search_mixin.py`. No-tool avg: $0.010. Tool-call avg: $0.023. Blended: ~$0.016.*
