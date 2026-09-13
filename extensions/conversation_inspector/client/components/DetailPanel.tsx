/**
 * Slide-out detail panel showing full content of a selected flow node.
 *
 * Each node type gets its own rich detail view:
 *   system_prompt  — sectioned prompt parts with char/token counts
 *   user_message   — timestamp, model, attached docs
 *   rag_step       — document list, full preview text
 *   thinking       — full thinking text
 *   tool_call      — tool name, call ID, full JSON arguments
 *   tool_result    — tool call ID, full result text
 *   mood_update    — mood, emoji, reason
 *   response       — model, timestamp, char/token counts, full content
 *   system_message — raw content
 */

import type { FlowStep } from "../api";

interface SystemPromptParts {
  identity?: string;
  personality?: string;
  datetime?: string;
  mood?: string;
  style_guidelines?: string;
  memory_instructions?: string;
  health_disclaimer?: string;
  other?: string;
  [key: string]: string | undefined;
}

interface DetailPanelProps {
  step: FlowStep | null;
  systemPromptParts: SystemPromptParts | null;
  onClose: () => void;
}

/** Color map for node types. */
const TYPE_COLORS: Record<string, string> = {
  system_prompt:    "#6366F1",
  per_turn_context: "#10B981",
  user_message:     "#3B82F6",
  rag_step:         "#10B981",
  thinking:         "#F59E0B",
  tool_call:        "#EF4444",
  tool_result:      "#14B8A6",
  mood_update:      "#A855F7",
  response:         "#6366F1",
  system_message:   "#6B7280",
};

function formatTimestamp(ts: string): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

export default function DetailPanel({
  step,
  systemPromptParts,
  onClose,
}: DetailPanelProps) {
  if (!step) return null;

  const color = TYPE_COLORS[step.type] || "#6B7280";
  const meta = step.metadata || {};

  return (
    <div className="cip-detail-overlay" onClick={onClose}>
      <div
        className="cip-detail-panel"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="cip-detail-header">
          <span className="cip-detail-badge" style={{ background: color }}>
            {step.label}
          </span>
          <button className="cip-detail-close" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="cip-detail-body">

          {/* ── System Prompt ─────────────────────────────────────── */}
          {step.type === "system_prompt" && (
            <SystemPromptDetail
              meta={meta}
              systemPromptParts={systemPromptParts}
            />
          )}

          {/* ── Per-Turn Context ──────────────────────────────────── */}
          {step.type === "per_turn_context" && (
            <PerTurnContextDetail meta={meta} />
          )}

          {/* ── User Message ──────────────────────────────────────── */}
          {step.type === "user_message" && (
            <UserMessageDetail content={step.content} meta={meta} />
          )}

          {/* ── RAG Step ──────────────────────────────────────────── */}
          {step.type === "rag_step" && (
            <RagStepDetail content={step.content} meta={meta} />
          )}

          {/* ── Thinking ──────────────────────────────────────────── */}
          {step.type === "thinking" && (
            <GenericContentDetail
              content={step.content}
              meta={meta}
              label="Thinking"
            />
          )}

          {/* ── Tool Call ─────────────────────────────────────────── */}
          {step.type === "tool_call" && <ToolCallDetail meta={meta} />}

          {/* ── Tool Result ───────────────────────────────────────── */}
          {step.type === "tool_result" && <ToolResultDetail meta={meta} />}

          {/* ── Mood Update ───────────────────────────────────────── */}
          {step.type === "mood_update" && (
            <MoodUpdateDetail content={step.content} meta={meta} />
          )}

          {/* ── Response ──────────────────────────────────────────── */}
          {step.type === "response" && (
            <ResponseDetail content={step.content} meta={meta} />
          )}

          {/* ── System Message ────────────────────────────────────── */}
          {step.type === "system_message" && (
            <GenericContentDetail
              content={step.content}
              meta={meta}
              label="System Message"
            />
          )}

        </div>
      </div>
    </div>
  );
}

/* ─── Sub-components ────────────────────────────────────────────── */

function TokenInfo({
  charCount,
  tokenEstimate,
}: {
  charCount?: number;
  tokenEstimate?: number;
}) {
  if (!charCount && !tokenEstimate) return null;
  return (
    <div className="cip-detail-section">
      <h4>Size</h4>
      <div style={{ fontSize: 12, color: "#4B5563" }}>
        {charCount != null && (
          <span style={{ marginRight: 16 }}>
            <strong>{charCount.toLocaleString()}</strong> chars
          </span>
        )}
        {tokenEstimate != null && (
          <span>
            ≈ <strong>{tokenEstimate.toLocaleString()}</strong> tokens
          </span>
        )}
      </div>
    </div>
  );
}

function TimestampRow({ ts }: { ts?: string }) {
  if (!ts) return null;
  return (
    <div className="cip-detail-section">
      <h4>Timestamp</h4>
      <code className="cip-tool-name">{formatTimestamp(ts)}</code>
    </div>
  );
}

function ModelRow({ model }: { model?: string }) {
  if (!model) return null;
  return (
    <div className="cip-detail-section">
      <h4>Model</h4>
      <code className="cip-tool-name" style={{ fontSize: 11, wordBreak: "break-all" }}>
        {model}
      </code>
    </div>
  );
}

function SystemPromptDetail({
  meta,
  systemPromptParts,
}: {
  meta: Record<string, unknown>;
  systemPromptParts: Record<string, string> | null;
}) {
  const partLabels: Record<string, string> = {
    identity: "Identity",
    personality: "Personality",
    datetime: "Date & Time",
    mood: "Mood",
    style_guidelines: "Style Guidelines",
    memory_instructions: "Memory Instructions",
    health_disclaimer: "Health Disclaimer",
    other: "Other",
  };

  // Prefer parts embedded in the step's own metadata (most accurate)
  const parts =
    (meta.parts as Record<string, string> | null) ?? systemPromptParts ?? {};
  const fullText = (meta.full_text as string) || "";
  const charCount = (meta.char_count as number) || fullText.length;
  const tokenEstimate = (meta.token_estimate as number) || Math.max(1, Math.floor(charCount / 4));

  const isCacheStable = meta.is_cache_stable !== false;

  return (
    <>
      <div
        className="cip-detail-section"
        style={{
          background: isCacheStable ? "#ECFDF5" : "#FEF2F2",
          borderRadius: 6,
          padding: "6px 10px",
          marginBottom: 10,
          border: `1px solid ${isCacheStable ? "#34D399" : "#FCA5A5"}`,
        }}
      >
        <span style={{ fontSize: 12, color: isCacheStable ? "#065F46" : "#991B1B", fontWeight: 600 }}>
          {isCacheStable
            ? "✅ Cache-stable — datetime, mood, and preflight are NOT in this prompt"
            : "⚠️ Cache may be busted — dynamic content detected in system prompt"}
        </span>
      </div>

      <TokenInfo charCount={charCount} tokenEstimate={tokenEstimate} />

      {Object.keys(parts).length > 0 ? (
        Object.entries(parts).map(([key, value]) => {
          if (!value) return null;
          return (
            <div key={key} className="cip-detail-section">
              <h4>{partLabels[key] || key}</h4>
              <pre className="cip-detail-content">{value}</pre>
            </div>
          );
        })
      ) : fullText ? (
        <div className="cip-detail-section">
          <h4>Full Prompt</h4>
          <pre className="cip-detail-content">{fullText}</pre>
        </div>
      ) : (
        <p style={{ color: "#94A3B8", fontSize: 13 }}>
          No prompt parts available for this turn.
        </p>
      )}
    </>
  );
}

function UserMessageDetail({
  content,
  meta,
}: {
  content?: string | null;
  meta: Record<string, unknown>;
}) {
  const activeDocs = meta.active_documents as string[] | undefined;
  return (
    <>
      <TimestampRow ts={meta.timestamp as string | undefined} />
      <ModelRow model={meta.model as string | undefined} />
      <TokenInfo
        charCount={meta.char_count as number | undefined}
        tokenEstimate={
          meta.char_count
            ? Math.max(1, Math.round((meta.char_count as number) / 4))
            : undefined
        }
      />
      {activeDocs && activeDocs.length > 0 && (
        <div className="cip-detail-section">
          <h4>Attached Documents ({activeDocs.length})</h4>
          <ul className="cip-doc-list">
            {activeDocs.map((name, idx) => (
              <li key={idx}>{name}</li>
            ))}
          </ul>
        </div>
      )}
      {content && (
        <div className="cip-detail-section">
          <h4>Message</h4>
          <pre className="cip-detail-content">{content}</pre>
        </div>
      )}
    </>
  );
}

function RagStepDetail({
  content,
  meta,
}: {
  content?: string | null;
  meta: Record<string, unknown>;
}) {
  const docNames = (meta.doc_names as string[]) || [];
  const preview = (meta.rag_text_preview as string) || content || "";
  const isActive = meta.is_rag_active as boolean | undefined;
  const modelVer = meta.model_version as string | undefined;

  return (
    <>
      <TimestampRow ts={meta.timestamp as string | undefined} />
      {isActive !== undefined && (
        <div className="cip-detail-section">
          <h4>Status</h4>
          <span
            style={{
              fontSize: 12,
              color: isActive ? "#059669" : "#DC2626",
              fontWeight: 600,
            }}
          >
            {isActive ? "✅ RAG Active" : "❌ RAG Inactive"}
          </span>
        </div>
      )}
      <ModelRow model={modelVer} />
      {docNames.length > 0 && (
        <div className="cip-detail-section">
          <h4>Documents ({docNames.length})</h4>
          <ul className="cip-doc-list">
            {docNames.map((name, idx) => (
              <li key={idx}>{name}</li>
            ))}
          </ul>
        </div>
      )}
      {preview && (
        <div className="cip-detail-section">
          <h4>Injected Context</h4>
          <pre className="cip-detail-content">{preview}</pre>
        </div>
      )}
      {!preview && !docNames.length && (
        <p style={{ color: "#94A3B8", fontSize: 13 }}>No RAG content available.</p>
      )}
    </>
  );
}

function ToolCallDetail({ meta }: { meta: Record<string, unknown> }) {
  const toolName = String(meta.tool_name || "unknown");
  const args = meta.arguments;
  const toolCallId = meta.tool_call_id;

  return (
    <>
      <TimestampRow ts={meta.timestamp as string | undefined} />
      <ModelRow model={meta.model as string | undefined} />
      <div className="cip-detail-section">
        <h4>Tool Name</h4>
        <code className="cip-tool-name">{toolName}</code>
      </div>
      {toolCallId && (
        <div className="cip-detail-section">
          <h4>Call ID</h4>
          <code className="cip-tool-name">{String(toolCallId)}</code>
        </div>
      )}
      <div className="cip-detail-section">
        <h4>Arguments</h4>
        <pre className="cip-detail-content">
          {typeof args === "string" ? args : JSON.stringify(args, null, 2)}
        </pre>
      </div>
    </>
  );
}

function ToolResultDetail({ meta }: { meta: Record<string, unknown> }) {
  const fullContent = String(meta.full_content || "");
  const charCount = meta.char_count as number | undefined;

  return (
    <>
      <TimestampRow ts={meta.timestamp as string | undefined} />
      <TokenInfo
        charCount={charCount}
        tokenEstimate={charCount ? Math.max(1, Math.round(charCount / 4)) : undefined}
      />
      {meta.tool_call_id && (
        <div className="cip-detail-section">
          <h4>Tool Call ID</h4>
          <code className="cip-tool-name">{String(meta.tool_call_id)}</code>
        </div>
      )}
      <div className="cip-detail-section">
        <h4>Full Result</h4>
        <pre className="cip-detail-content">{fullContent || "(empty)"}</pre>
      </div>
    </>
  );
}

function MoodUpdateDetail({
  content,
  meta,
}: {
  content?: string | null;
  meta: Record<string, unknown>;
}) {
  const args = (meta.arguments as Record<string, string>) || {};
  const mood = args.mood || "";
  const emoji = args.emoji || "";
  const reason = args.reason || "";

  return (
    <>
      <TimestampRow ts={meta.timestamp as string | undefined} />
      <div className="cip-detail-section">
        <h4>New Mood</h4>
        <div style={{ fontSize: 20 }}>
          {emoji} <strong style={{ fontSize: 16 }}>{mood}</strong>
        </div>
      </div>
      {reason && (
        <div className="cip-detail-section">
          <h4>Reason</h4>
          <p style={{ fontSize: 13, color: "#374151", margin: 0 }}>{reason}</p>
        </div>
      )}
      {content && !reason && (
        <div className="cip-detail-section">
          <h4>Details</h4>
          <pre className="cip-detail-content">{content}</pre>
        </div>
      )}
    </>
  );
}

function ResponseDetail({
  content,
  meta,
}: {
  content?: string | null;
  meta: Record<string, unknown>;
}) {
  const charCount = meta.char_count as number | undefined;
  const tokenEstimate = meta.token_estimate as number | undefined;

  return (
    <>
      <TimestampRow ts={meta.timestamp as string | undefined} />
      <ModelRow model={meta.model as string | undefined} />
      <TokenInfo charCount={charCount} tokenEstimate={tokenEstimate} />
      {content && (
        <div className="cip-detail-section">
          <h4>Full Response</h4>
          <pre className="cip-detail-content">{content}</pre>
        </div>
      )}
    </>
  );
}

function PerTurnContextDetail({ meta }: { meta: Record<string, unknown> }) {
  const parts = (meta.parts as Record<string, string>) || {};
  const fullText = (meta.full_text as string) || "";
  const charCount = (meta.char_count as number) || fullText.length;
  const tokenEstimate = (meta.token_estimate as number) || Math.max(1, Math.floor(charCount / 4));
  const note = (meta.note as string) || "";
  const injectionTarget = (meta.injection_target as string) || "human_turn";

  const partLabels: Record<string, string> = {
    datetime: "📅 Date & Time",
    mood: "🎭 Mood",
    preflight: "🛡 Preflight Intercept",
  };

  return (
    <>
      <div
        className="cip-detail-section"
        style={{
          background: "#ECFDF5",
          border: "1px solid #34D399",
          borderRadius: 6,
          padding: "6px 10px",
          marginBottom: 10,
        }}
      >
        <div style={{ fontSize: 12, color: "#065F46", fontWeight: 600 }}>
          💉 Injected into: <code style={{ fontWeight: 700 }}>{injectionTarget}</code>
        </div>
        {note && (
          <div style={{ fontSize: 11, color: "#059669", marginTop: 4 }}>{note}</div>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {meta.has_datetime && (
          <span style={{ fontSize: 11, background: "#EFF6FF", color: "#1D4ED8", padding: "2px 8px", borderRadius: 10, border: "1px solid #93C5FD" }}>
            📅 datetime
          </span>
        )}
        {meta.has_mood && (
          <span style={{ fontSize: 11, background: "#FDF4FF", color: "#7E22CE", padding: "2px 8px", borderRadius: 10, border: "1px solid #D8B4FE" }}>
            🎭 mood
          </span>
        )}
        {meta.has_preflight_dynamic && (
          <span style={{ fontSize: 11, background: "#FFF7ED", color: "#92400E", padding: "2px 8px", borderRadius: 10, border: "1px solid #FCD34D" }}>
            🛡 preflight (dynamic)
          </span>
        )}
      </div>

      <TokenInfo charCount={charCount} tokenEstimate={tokenEstimate} />

      {Object.keys(parts).length > 0
        ? Object.entries(parts).map(([key, value]) => {
            if (!value) return null;
            return (
              <div key={key} className="cip-detail-section">
                <h4>{partLabels[key] || key}</h4>
                <pre className="cip-detail-content">{value}</pre>
              </div>
            );
          })
        : fullText && (
            <div className="cip-detail-section">
              <h4>Full Context Block</h4>
              <pre className="cip-detail-content">{fullText}</pre>
            </div>
          )}
    </>
  );
}

function GenericContentDetail({
  content,
  meta,
  label,
}: {
  content?: string | null;
  meta: Record<string, unknown>;
  label: string;
}) {
  const charCount = meta.char_count as number | undefined;
  const tokenEstimate = charCount ? Math.max(1, Math.round(charCount / 4)) : undefined;

  return (
    <>
      <TimestampRow ts={meta.timestamp as string | undefined} />
      <TokenInfo charCount={charCount} tokenEstimate={tokenEstimate} />
      {content && (
        <div className="cip-detail-section">
          <h4>{label}</h4>
          <pre className="cip-detail-content">{content}</pre>
        </div>
      )}
    </>
  );
}
