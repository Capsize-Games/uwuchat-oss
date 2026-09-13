/**
 * Test for InlineFlowNodes per-tool cost matching fix.
 *
 * Covers:
 * 1. Single-tool DIALOGUE legacy key "DIALOGUE (tool call)"
 * 2. Multi-tool DIALOGUE per-tool keys "DIALOGUE (tool_name)"
 * 3. TOOL_EXECUTION single-tool "TOOL_EXECUTION (tool call)" still works
 * 4. Missing tool_name falls back to generic key
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { InlineFlowNodes } from "./InlineFlowNodes";
import type { FlowStep } from "@extensions/conversation_inspector/client/api";
import type { CallChainDetail, CallChainStep } from "../../../types/pipeline";

/** Create a minimal FlowStep with the given type and metadata. */
function makeStep(
  type: FlowStep["type"],
  metadata?: Record<string, unknown>,
): FlowStep {
  return {
    type,
    label: type === "tool_call" ? "Tool call: search" : `${type} label`,
    content: null,
    metadata: metadata ?? null,
  };
}

/** Create a minimal CallChainStep cost row. */
function makeCostRow(
  pipelineKey: string,
  costUsd: number,
  recordedAt: string = "2026-01-01T00:00:00Z",
): CallChainStep {
  return {
    sequence: 0,
    pipeline_key: pipelineKey,
    model_id: "test-model",
    input_tokens: 100,
    output_tokens: 50,
    cache_read_tokens: 0,
    cost_usd: costUsd,
    skipped: false,
    prompt_char_count: null,
    response_char_count: null,
    complexity_score: null,
    tier_name: null,
    recorded_at: recordedAt,
  };
}

function makeCostDetail(steps: CallChainStep[]): CallChainDetail {
  return {
    call_chain_id: "test-chain",
    total_cost_usd: steps.reduce((s, c) => s + c.cost_usd, 0),
    total_input_tokens: steps.reduce((s, c) => s + c.input_tokens, 0),
    total_output_tokens: steps.reduce((s, c) => s + c.output_tokens, 0),
    steps,
    trigger_type: "user_message",
  };
}

describe("InlineFlowNodes cost matching", () => {
  it("matches single-tool DIALOGUE round using legacy key", () => {
    const step = makeStep("tool_call", {
      tool_name: "search_fastsearch",
      tool_category: "search",
    });
    const costRow = makeCostRow("DIALOGUE (tool call)", 0.001);
    const costDetail = makeCostDetail([costRow]);

    const { container } = render(
      <InlineFlowNodes
        steps={[step]}
        position="mid"
        costDetail={costDetail}
      />,
    );

    // The flow step node should show the cost value.
    const costValues = container.querySelectorAll('[class*="nodeCostValue"]');
    expect(costValues.length).toBe(1);
    expect(costValues[0].textContent).toContain("0.001000");
  });

  it("matches multi-tool DIALOGUE round with per-tool keys", () => {
    const step1 = makeStep("tool_call", {
      tool_name: "search_fastsearch",
      tool_category: "search",
    });
    const step2 = makeStep("tool_call", {
      tool_name: "search_fastsearch_news",
      tool_category: "research",
    });
    const step3 = makeStep("tool_call", {
      tool_name: "scrape_website",
      tool_category: "search",
    });

    const costRow1 = makeCostRow(
      "DIALOGUE (search_fastsearch)", 0.001,
    );
    const costRow2 = makeCostRow(
      "DIALOGUE (search_fastsearch_news)", 0.002,
    );
    const costRow3 = makeCostRow(
      "DIALOGUE (scrape_website)", 0.003,
    );
    const costDetail = makeCostDetail([costRow1, costRow2, costRow3]);

    const { container } = render(
      <InlineFlowNodes
        steps={[step1, step2, step3]}
        position="mid"
        costDetail={costDetail}
      />,
    );

    // Each flow step should have its own cost row — three total.
    const costValues = container.querySelectorAll('[class*="nodeCostValue"]');
    expect(costValues.length).toBe(3);
    // Verify distinct costs — each step got its own row, not all
    // matching the first one.
    const texts = Array.from(costValues).map((el) => el.textContent);
    expect(texts).toContain("$0.001000");
    expect(texts).toContain("$0.002000");
    expect(texts).toContain("$0.003000");

    // No orphan cost steps should remain unconsumed.
    const orphans = container.querySelectorAll('[class*="costStepNode"]');
    expect(orphans.length).toBe(0);
  });

  it("matches TOOL_EXECUTION single-tool round unchanged", () => {
    const step = makeStep("tool_call", {
      tool_name: "search_fastsearch",
      tool_category: "search",
    });
    const costRow = makeCostRow("TOOL_EXECUTION (tool call)", 0.0005);
    const costDetail = makeCostDetail([costRow]);

    const { container } = render(
      <InlineFlowNodes
        steps={[step]}
        position="mid"
        costDetail={costDetail}
      />,
    );

    const costValues = container.querySelectorAll('[class*="nodeCostValue"]');
    expect(costValues.length).toBe(1);
    expect(costValues[0].textContent).toContain("0.000500");
  });

  it("falls back to generic key when tool_name is missing", () => {
    // Metadata has tool_category but no tool_name — older data.
    const step = makeStep("tool_call", {
      tool_category: "search",
    });
    const costRow = makeCostRow("TOOL_EXECUTION (tool call)", 0.0008);
    const costDetail = makeCostDetail([costRow]);

    const { container } = render(
      <InlineFlowNodes
        steps={[step]}
        position="mid"
        costDetail={costDetail}
      />,
    );

    const costValues = container.querySelectorAll('[class*="nodeCostValue"]');
    expect(costValues.length).toBe(1);
    expect(costValues[0].textContent).toContain("0.000800");
  });
});
