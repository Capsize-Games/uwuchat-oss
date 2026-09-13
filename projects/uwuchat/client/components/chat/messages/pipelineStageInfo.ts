/** Shared label + description for every pipeline_key recorded server-side.
 *
 *  Verified against real `record_usage()` / `record_background_usage()`
 *  call sites.  When a new pipeline stage is added, update this map
 *  instead of copying a label/description into individual components.
 */
export interface PipelineStageInfo {
  label: string;
  description: string;
}

const _INFO: Record<string, PipelineStageInfo> = {
  DIALOGUE: {
    label: "Dialogue",
    description: "The main conversation model — produces the visible "
      + "chat reply and decides whether to call tools.",
  },
  RESPONSE: {
    label: "Response",
    description: "Narration pass that writes the final in-character "
      + "reply after tool results are available.",
  },
  TOOL_CLASSIFICATION: {
    label: "Tool Classification",
    description: "Classifies which tool categories apply to this turn.",
  },
  TOOL_EXECUTION: {
    label: "Tool Execution",
    description: "Cheap-model stage that runs search, math, system, "
      + "and research tools before the main dialogue model.",
  },
  INTRA_SESSION_MOOD: {
    label: "Mood Update",
    description: "Updates the bot's mood and emoji from recent "
      + "conversation (cheap model, every turn).",
  },
  KNOWLEDGE: {
    label: "Knowledge Extraction",
    description: "Extracts durable personal facts for long-term memory "
      + "(async, post-hoc).",
  },
  NODE_VALIDATOR: {
    label: "Validator",
    description: "Validates the response against character rules and "
      + "safety constraints.",
  },
  CURIOSITY_ENGINE: {
    label: "Curiosity",
    description: "Generates follow-up questions to keep the "
      + "conversation going (session-end).",
  },
  EPISODIC_SUMMARIZER: {
    label: "Episode Summary",
    description: "Summarizes a completed conversation session into a "
      + "narrative memory.",
  },
  MEMORY_UPDATER: {
    label: "Memory Update",
    description: "Blends episodic summaries into long-term agent memory.",
  },
  ROLLING_COMPRESSOR: {
    label: "Rolling Compression",
    description: "Compresses old session messages into a rolling "
      + "summary (session-end).",
  },
  NEWS_SYNTHESIS: {
    label: "News Synthesis",
    description: "Synthesizes news articles into a daily digest.",
  },
  SUMMARIZATION: {
    label: "Summarization",
    description: "Generates an LLM summary of an article or URL.",
  },
  STATELESS: {
    label: "Stateless",
    description: "One-shot LLM call with no conversation context.",
  },
};

/** Return label + description for *pipelineKey*, or a title-cased
 *  fallback label with no description for unknown keys. */
export function pipelineStageInfo(pipelineKey: string): PipelineStageInfo {
  // DIALOGUE / RESPONSE variants: _iteration_label() emits
  // "DIALOGUE (tool call)" or "RESPONSE (tool call)" when the model
  // calls tools, and "DIALOGUE (response)" or "RESPONSE (response)"
  // for the final narration iteration.  Both represent real,
  // separately-billed LLM calls — disambiguate them visually.
  if (
    pipelineKey.startsWith("DIALOGUE (tool call)") ||
    pipelineKey.startsWith("RESPONSE (tool call)") ||
    pipelineKey.startsWith("KNOWLEDGE (tool call)") ||
    pipelineKey.startsWith("TOOL_EXECUTION (tool call)")
  ) {
    return {
      label: "Tool Call",
      description: "The LLM decided to invoke tools. It generates the "
        + "tool name and arguments.",
    };
  }
  if (
    pipelineKey.startsWith("DIALOGUE (response)") ||
    pipelineKey.startsWith("RESPONSE (response)")
  ) {
    return {
      label: "Response",
      description: "The LLM produces the visible chat reply. May "
        + "include tool results injected into the prompt.",
    };
  }
  if (pipelineKey.startsWith("KNOWLEDGE (response)")) {
    return {
      label: "Knowledge Extraction",
      description: "Extracts durable personal facts for long-term "
        + "memory (async, post-hoc).",
    };
  }
  if (pipelineKey.startsWith("TOOL_EXECUTION (response)")) {
    return {
      label: "Tool Execution",
      description: "Cheap-model stage that runs search, math, system, "
        + "and research tools before the main dialogue model.",
    };
  }
  const entry = _INFO[pipelineKey];
  if (entry) return entry;
  return {
    label: pipelineKey
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase()),
    description: "",
  };
}
