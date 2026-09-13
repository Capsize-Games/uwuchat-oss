# DeepSeek / OpenRouter Integration

This page documents how to configure and use DeepSeek models (and other reasoning models) via OpenRouter, with specific notes on the thinking-mode / tool-use interaction.

---

## Quick-start: configuring a DeepSeek model via OpenRouter

Set the provider to `openrouter` and a model ID such as `deepseek/deepseek-v4-flash` in the agent settings. The only required credential is an `OPENROUTER_API_KEY` environment variable.

```env
OPENROUTER_API_KEY=sk-or-...
```

The adapter is `cloud/llm/openrouter_adapter.py`. It wraps LangChain's `ChatOpenAI` pointed at `https://openrouter.ai/api/v1` and uses a custom `ReasoningAwareChatOpenAI` subclass that rescues `reasoning_content` from streaming deltas so the thinking block surfaces correctly in the UI.

---

## Thinking mode (reasoning)

### How DeepSeek's thinking API works

DeepSeek's **native API** (`api.deepseek.com`) enables thinking via a `thinking` object:

```json
{
  "thinking": {
    "type": "enabled",
    "reasoning_effort": "high"
  }
}
```

DeepSeek's effort values map to OpenRouter's `effort` string as follows:

| DeepSeek native | OpenRouter `effort` |
|---|---|
| `"high"` | `"low"` or `"medium"` |
| `"max"` | `"xhigh"` |

### How OpenRouter wraps it

When using OpenRouter, thinking mode is enabled via `extra_body` — **not** a top-level kwarg:

```python
client.chat.completions.create(
    model="deepseek/deepseek-v4-flash",
    messages=[...],
    extra_body={
        "reasoning": {
            "effort": "medium",   # "xhigh" | "high" | "medium" | "low" | "minimal" | "none"
            "exclude": False      # True = model thinks but the thoughts aren't returned
        }
    }
)
```

`effort` is read from `LLMRequest.reasoning_effort` (defaults to `"medium"`). The `exclude` flag is always `False` so thinking content is surfaced in the conversation-flow inspector.

OpenRouter normalizes this across providers — the same `extra_body.reasoning` format works for DeepSeek, Anthropic Claude, and other reasoning models via OpenRouter.

### ⚠️ Critical pitfall: top-level `reasoning_effort` also enables thinking mode

OpenRouter also interprets a **top-level `reasoning_effort` kwarg** (passed alongside `messages`, `temperature`, etc.) as a signal to enable thinking mode. This is not prominently documented but is confirmed behavior.

Both of these enable thinking mode via OpenRouter:

```python
# Method 1 — documented, correct
extra_body={"reasoning": {"effort": "medium", "exclude": False}}

# Method 2 — undocumented side effect; DO NOT use
reasoning_effort="medium"   # plain top-level kwarg → OpenRouter enables thinking
```

`LLMRequest.to_generation_kwargs()` emits `reasoning_effort` as a plain top-level key. **This key must be popped from `generation_kwargs` before any OpenAI-compatible request is made.** Failing to do so causes the same HTTP 400 (`"Thinking mode does not support this tool_choice"`) whenever any restrictive `tool_choice` is also active — even if `extra_body.reasoning` was never added.

### How thinking content comes back

OpenRouter strips the raw `<think>` tags and delivers the reasoning text in `message.reasoning` (non-streaming) or in `delta.reasoning` on streaming chunks. The `ReasoningAwareChatOpenAI` subclass in `cloud/llm/model_builders.py` rescues `delta["reasoning"]` and places it in `AIMessageChunk.additional_kwargs["reasoning_content"]`, which is the key our streaming helpers look for.

### Enabling / disabling thinking per-request

`enable_thinking` defaults to `True` from the `LLMGeneratorSettings` DB row. A request can override it:

```python
llm_request.enable_thinking = False  # disable for one request
llm_request.reasoning_effort = "high"  # override effort level
```

---

## Thinking mode + tool use — the rules

This is the most important compatibility constraint to understand.

### What works

| Configuration | Outcome |
|---|---|
| Thinking mode + **no tools** | ✅ Full reasoning in response |
| Thinking mode + tools bound + `tool_choice=None/auto`, **first model call** | ✅ Model may call tools; thinking content returned |

### What does not work

| Configuration | Outcome |
|---|---|
| Thinking mode + **restrictive** `tool_choice` | ❌ HTTP 400: `"Thinking mode does not support this tool_choice"` |
| Thinking mode + **tool-continuation turn** (ToolMessages in history) | ❌ HTTP 400: same error — DeepSeek applies an implicit restriction on the follow-up turn after a tool call |

A "restrictive" `tool_choice` means any value other than `None` or `"auto"` — specifically:
- `"any"` / `"required"` (forced to call *some* tool)
- `{"type": "function", "function": {"name": "..."}}` (forced to call a specific tool)

A **tool-continuation turn** is any model call where the message history already contains a `ToolMessage` — i.e. the LLM previously called a tool and the workflow routed back to the model to generate a follow-up response. DeepSeek rejects thinking mode here even with `tool_choice=None`, which contradicts the published documentation but is confirmed empirical behavior.

### Where restrictive tool_choice is applied in AIRunner

Two code paths apply restrictive choices:

1. **Search / RAG flows** — `tool_filtering_mixin._resolve_tool_choice` returns `"any"` when `action == PERFORM_RAG_SEARCH` or search categories are active.
2. **Forced-tool policy** — `ForcedToolExecutionPolicy.complete()` re-binds the model mid-graph with a named-function choice to sequence multi-step workflows.

### How AIRunner handles it

`_normalize_generation_kwargs` in `generation_execution_support.py` is called before every stream. It:

1. **Pops `reasoning_effort`** unconditionally — removes the top-level key from `generation_kwargs` regardless of thinking mode state, preventing the undocumented top-level kwarg from silently enabling thinking mode via OpenRouter.
2. **Pops `enable_thinking`** — extracts the flag before it reaches the OpenAI client (which rejects unknown top-level kwargs).
3. **Conditionally builds `extra_body.reasoning`** — only adds the `reasoning` block when `enable_thinking` is truthy *and* no restrictive `tool_choice` is active at call time.

```python
# generation_execution_support.py — _normalize_generation_kwargs
has_tc = _has_tool_choice(owner)
enable_thinking = generation_kwargs.pop("enable_thinking", None)

# Must pop reasoning_effort — OpenRouter treats it as a thinking-mode
# enabler even as a plain top-level kwarg, causing the same 400 as
# extra_body.reasoning when combined with a restrictive tool_choice.
generation_kwargs.pop("reasoning_effort", None)

if enable_thinking is not None and not has_tc:
    effort = getattr(llm_request, "reasoning_effort", None) or "medium"
    extra_body = generation_kwargs.get("extra_body") or {}
    extra_body["reasoning"] = {"effort": effort, "exclude": False}
    generation_kwargs["extra_body"] = extra_body
```

`node_streaming_reasoning_guard.strip_reasoning_for_forced_tool()` provides a second layer of defense: it is called immediately before every `.stream()` call in `NodeStreamingResponseHelper._run_stream_loop`. It strips `extra_body.reasoning` in two cases:

1. A restrictive `tool_choice` is bound (mid-graph rebind by ForcedToolExecutionPolicy).
2. The formatted prompt contains any `ToolMessage` — the tool-continuation turn case.

```python
# node_streaming_reasoning_guard.py
def strip_reasoning_for_forced_tool(chat_model, kwargs, prompt=None):
    extra_body = kwargs.get("extra_body")
    if not isinstance(extra_body, dict) or "reasoning" not in extra_body:
        return kwargs
    if has_restrictive_tool_choice(chat_model):
        return _remove_reasoning(kwargs, extra_body)
    if prompt is not None and has_tool_continuation(prompt):
        return _remove_reasoning(kwargs, extra_body)
    return kwargs
```

### Reasoning-content preservation across tool turns (important for multi-turn)

DeepSeek's API requires that when a thinking model fires a tool, the model's `reasoning_content` from that turn is preserved in the message history when you send the tool result back. If you strip reasoning from the assistant message before injecting the `ToolMessage`, the model loses the chain of thought for *why* it called the tool.

> **TODO:** Audit `database_chat_message_history.py` and `conversation_history_formatter.py` to confirm `reasoning_content` is round-tripped in assistant messages that contain tool calls, not only in final-response messages.

---

## Streaming tool calls — delta accumulation

DeepSeek (via OpenRouter) sends tool call data as streaming deltas: the tool name arrives in an early chunk with empty args, and the args arrive in later chunks with no name. This is standard OpenAI-compatible streaming behavior but requires proper accumulation.

**Wrong approach:** collecting `chunk.tool_calls` from each individual streaming chunk and extending a list — this produces two partial entries: `{name: "foo", args: {}}` and `{name: "", args: {...}}`, causing ToolNode to attempt to execute two invalid tool calls.

**Correct approach (what AIRunner does):** accumulate `AIMessageChunk` objects using LangChain's `+` operator throughout the stream, then read `tool_calls` from the final accumulated message:

```python
# StreamingState.accumulated_message
if state.accumulated_message is None:
    state.accumulated_message = chunk_message
else:
    state.accumulated_message = state.accumulated_message + chunk_message
```

`_build_streamed_message` then reads `state.accumulated_message.tool_calls` as the authoritative tool call list.

---

## Model-specific notes

### deepseek/deepseek-v4-flash

- Thinking model; sends reasoning in `delta.reasoning` during streaming.
- Supports function calling while in thinking mode, as long as `tool_choice` is not restrictive.
- Thinking tokens are billed as output tokens and count toward `max_tokens`.
- If you use `"effort": "xhigh"` ensure `max_tokens` is set high enough that the budget isn't exhausted before the `content` block is generated.

### deepseek/deepseek-r1

- Original reasoning model; raw model versions wrap thoughts in `<think>` tags, but the API endpoint (and OpenRouter) extract them into `message.reasoning`.
- Older API versions did not support native function calling alongside thinking mode. Use V4 or later for combined thinking + tools.

### Other providers via OpenRouter (Gemini Flash, etc.)

OpenRouter normalizes the `reasoning` / `extra_body` interface across providers. Effort levels and the `exclude` flag work consistently. The `reasoning_content` response key is also normalized — your provider-specific thinking blocks all arrive via the same `delta.reasoning` path regardless of underlying provider.

---

## Fallback messages — when tool calls produce no response

If a tool executes but the model produces no visible text afterward, AIRunner emits a fallback string rather than an empty bubble. The set `STATUS_ONLY_TOOLS` in `generation_response_support.py` lists tools whose "ran with no follow-up text" state should be silently swallowed (empty fallback):

```python
STATUS_ONLY_TOOLS = {
    "update_mood",
    "record_knowledge",
    "record_character_fact",
    "recall_character_facts",   # read-only self-knowledge lookup
    "recall_knowledge",         # read-only knowledge lookup
    "toggle_tts",
    "clear_conversation",
}
```

`recall_character_facts` and `recall_knowledge` are read-only lookups the character uses to inform its response. If the LLM calls one and then generates text normally, no fallback fires. The fallback is only relevant during error scenarios (e.g. validation failures before the streaming fix was in place).
