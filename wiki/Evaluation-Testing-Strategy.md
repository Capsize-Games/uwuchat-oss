# Evaluation Testing

AI Runner includes an evaluation (eval) framework for testing LLM quality and behavior. The framework is located in `server/src/airunner_services/eval/`.

---

## Overview

The eval framework tests **LLM intelligence** — does the model use tools correctly, generate coherent responses, and follow instructions?

### What We Test

- **Tool usage** — Does the LLM recognize when to call tools?
- **Response quality** — Are responses accurate and relevant?
- **Mathematical reasoning** — GSM8K, MATH benchmark datasets
- **Code generation** — HumanEval benchmark
- **Agent behavior** — Document, flow, mood, response, and tool evaluation

### What We Mock

External side effects (database, HTTP requests) are mocked. **LLM responses are real** — mocking the LLM would defeat the purpose of eval tests.

---

## Test Categories

### Math Benchmarks

| Dataset | Level | Coverage |
|---------|-------|----------|
| GSM8K | Grade school | Basic arithmetic, word problems |
| MATH Level 1-5 | High school to competition | Advanced math reasoning |

### Code Benchmarks

| Dataset | Coverage |
|---------|----------|
| HumanEval | 164 Python function generation problems |

### Agent Eval Tests

| Test | Purpose |
|------|---------|
| `test_agent_document_eval` | Document-grounded response quality |
| `test_agent_flow_eval` | Conversation flow and coherence |
| `test_agent_mood_eval` | Mood analysis accuracy |
| `test_agent_response_eval` | Response quality assessment |
| `test_agent_tool_eval` | Tool selection correctness |
| `test_agent_tool_selection_eval` | Tool selection accuracy |

---

## Running Tests

```bash
# Run all eval tests
pytest server/src/ -m eval

# Run specific eval test
pytest server/tests/eval/test_agent_tool_eval.py -v -m eval

# Run math benchmarks
pytest server/tests/eval/ -v -m benchmark
```

### Test Fixtures

- **`airunner_client`** — Session-scoped client connected to the daemon server
- **`airunner_client_function_scope`** — Fresh client per test function

---

## Persona & Memory Coherence Evals

In addition to the LLM intelligence benchmarks above, UwUchat ships a
separate assertion-based eval suite that validates **character consistency**
rather than reasoning ability. These tests call the production model
(Claude Haiku 4.5 via OpenRouter) with assembled system prompts that
mirror the live UwUchat prompt stack.

### What they test

| Suite | File | Coverage |
|-------|------|----------|
| Persona fidelity | `server/src/airunner_services/evals/persona_fidelity_eval.py` | Name self-identification (TC-PF-01), speech pattern adherence (TC-PF-02), OOC bleed prevention (TC-PF-03), character-consistent refusal (TC-PF-04), multi-turn consistency (TC-PF-05), emotional register (TC-PF-06), subtle jailbreak resistance (TC-PF-07) |
| Persona fidelity (ext) | `server/src/airunner_services/evals/persona_fidelity_eval_ext.py` | Voice survives topic churn (TC-PF-08), mimicry resistance (TC-PF-09), long-conversation stability (TC-PF-10) |
| Character voice (integration) | `server/tests/eval/test_character_voice_integration.py` | Real-pipeline mimicry resistance — exercises `BANNED_PATTERNS_BLOCK` via UwUchat prompt stack (requires `AIRUNNER_PROJECT=uwuchat`, `@pytest.mark.integration`) |
| Memory coherence | `server/src/airunner_services/evals/memory_coherence_eval.py` | Rolling memory recall — user preference (TC-MC-01), shared event recall (TC-MC-02), episodic bullet recall (TC-MC-03), hallucination prevention (TC-MC-04), session bridge concern (TC-MC-05), negative recall (TC-MC-06), within-session recall (TC-MC-07) |
| Memory coherence (ext) | `server/src/airunner_services/evals/memory_coherence_eval_ext.py` | Null tool → no false confirmation (TC-MC-08), new info not falsely recalled (TC-MC-09) |

### Running

Requires `OPENROUTER_API_KEY` set in the environment:

```bash
# Docker (recommended)
docker compose exec -e OPENROUTER_API_KEY server \
    python -m airunner_services.evals.run_evals

# Or via the test runner
python scripts/run_tests.py --eval
```

The runner prints PASS/FAIL per test case with the failing assertion and
exits code 1 on any failure (CI-safe).

### Architecture

- **`base_eval.py`** — `EvalBase` class assembles the system prompt from
  persona config + memory summary + episodic bullets, then calls OpenRouter
  via the `openai` SDK.
- **System prompt layers** (in order): hard rules → identity block →
  long-term memory → episodic bullets. Per-turn bridge text is prepended
  to the user message, not the system prompt (preserves prefix cache).
- **No mocking** — every test case sends one real API call and asserts on
  the raw response text with substring and word-boundary checks.

### Known limitations

- **Tool simulation via conversation injection.** TC-MC-08 injects a null
  tool result (`[recall_knowledge returned: no results ...]`) as an
  assistant turn. The model sees this as something *it* said rather than
  a system-level signal, so a clever model could reason around it. This is
  the best approximation available without a real tool-calling harness. If
  a future model starts disputing injected tool results, the fallback is
  to prepend the tool result as a system-level instruction before the user
  follow-up rather than injecting it as an assistant message.

- **Two evaluation frameworks.** The project has two separate eval
  frameworks that serve different purposes:

  1. **`airunner_services.evals`** — Fast, assertion-based,
     ``EvalBase``-driven tests (TC-PF-\*, TC-MC-\*).  Assembles a
     simplified hand-rolled system prompt and calls OpenRouter directly.
     Good for quick regression checks but does **not** exercise the
     production UwUchat prompt stack (e.g. ``BANNED_PATTERNS_BLOCK``,
     ``uwuchat_rp_style``).

  2. **`airunner_services.eval`** — Pytest-based integration tests that
     go through the real WebSocket daemon (`rag_eval_support.py`).  The
     **only** framework that exercises the full production prompt stack.

  TC-PF-09 (mimicry resistance) has both a fast ``EvalBase`` version and
  a real-pipeline counterpart in
  ``server/tests/eval/test_character_voice_integration.py``.  The former
  tells you whether Claude Haiku resists mimicry when asked nicely; only
  the latter tells you whether the production ``BANNED_PATTERNS_BLOCK``
  guard actually works.

## Quality Metrics

Metrics tracked during evaluation:
- **Pass rate** — % of problems meeting minimum score
- **Average score** — Mean evaluation score (0-1)
- **Grade** — Letter grade (A-F) based on score
- **Execution time** — Total evaluation duration

---

## File Locations

| Component | Path |
|-----------|------|
| Eval framework | `server/src/airunner_services/eval/` |
| Test files | `server/tests/eval/` |
| Benchmarks | `server/src/airunner_services/eval/benchmark_datasets/` |
| Eval utilities | `server/src/airunner_services/eval/utils/` |
