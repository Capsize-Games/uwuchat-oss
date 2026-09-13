import Dropdown from "react-bootstrap/Dropdown";
import LucideIcon from "@/components/shared/LucideIcon";
import { useAuth } from "../../../hooks/useAuth";
import { CODE_MODE_SLUGS, type CodeModeSlug } from "../../../api/codeMode";
import styles from "./CodeModePicker.module.css";

const MODE_META: Record<
  CodeModeSlug,
  { icon: string; label: string; description: string }
> = {
  code: {
    icon: "code",
    label: "Code",
    description: "Read, edit, and run commands — implements the task.",
  },
  architect: {
    icon: "compass",
    label: "Architect",
    description: "Read, search, and run commands — explores and plans, never edits.",
  },
  ask: {
    icon: "help-circle",
    label: "Ask",
    description: "Answers questions and explains code — never makes changes.",
  },
  debug: {
    icon: "bug",
    label: "Debug",
    description: "Systematic diagnosis: reasons about causes, confirms before fixing.",
  },
  orchestrator: {
    icon: "workflow",
    label: "Orchestrator",
    description: "Breaks a complex task into subtasks and delegates them to other modes.",
  },
  planning: {
    icon: "clipboard-list",
    label: "Planning",
    description: "Discovery conversation to scope an idea before it becomes a plan doc.",
  },
  "zoo-audit": {
    icon: "shield-check",
    label: "Audit",
    description: "Read-only sweep for security, bugs, and cost issues — no fixes.",
  },
  "script-agent": {
    icon: "terminal",
    label: "Script",
    description: "Runs predefined scripts/ for deploy and ops tasks — nothing else.",
  },
  "qa-agent": {
    icon: "check-circle",
    label: "QA",
    description: "Starts the app, observes it in a real browser, fixes what's broken.",
  },
  "deepseek-reviewer": {
    icon: "search",
    label: "Reviewer",
    description: "Independent, adversarial verification of a worker's claimed changes.",
  },
  "multi-agent-orchestrator-headless": {
    icon: "network",
    label: "Orchestrator (Headless)",
    description: "Splits a plan into issues and runs a full headless multi-worker round.",
  },
};

/**
 * Admin-only mode picker for the current conversation — the bottom-left
 * popup Zoo Code shows under its own chat input, adapted for UwUChat's
 * headlesscode integration (see code_mode_service.py's CODE_MODE_SLUGS).
 * Renders nothing for non-superusers.
 *
 * Selecting "Off" turns code mode off; selecting a mode turns code mode
 * on (if it wasn't already) for that mode. Before a conversation has
 * resolved (conversationId === null), a selection just arms a "start as
 * code" intent — see useCodeMode's `pending`.
 */
export default function CodeModePicker({
  enabled,
  mode,
  pending,
  loading,
  onSelect,
}: {
  enabled: boolean;
  mode: CodeModeSlug;
  pending: boolean;
  loading: boolean;
  onSelect: (mode: CodeModeSlug | null) => void;
}) {
  const { user } = useAuth();
  if (!user?.is_superuser) return null;

  const active = enabled || pending;
  const label = active ? MODE_META[mode].label : "Off";
  const icon = active ? MODE_META[mode].icon : "circle-x";

  return (
    <Dropdown className={styles.picker}>
      <Dropdown.Toggle
        as="button"
        disabled={loading}
        className={`${styles.trigger} ${active ? styles.active : ""}`}
        title={
          pending
            ? "Next conversation will start in this mode"
            : "Pick the headlesscode mode for this conversation"
        }
      >
        <LucideIcon name={icon} size={13} />
        <span>{label}</span>
      </Dropdown.Toggle>
      <Dropdown.Menu className={styles.menu}>
        <Dropdown.Item
          className={styles.item}
          active={!active}
          onClick={() => onSelect(null)}
        >
          <span className={styles.itemLabel}>Off</span>
          <span className={styles.itemDesc}>
            Normal companion persona — no coding tools.
          </span>
        </Dropdown.Item>
        {CODE_MODE_SLUGS.map((slug) => (
          <Dropdown.Item
            key={slug}
            className={styles.item}
            active={active && mode === slug}
            onClick={() => onSelect(slug)}
          >
            <span className={styles.itemLabel}>
              <LucideIcon name={MODE_META[slug].icon} size={13} />{" "}
              {MODE_META[slug].label}
            </span>
            <span className={styles.itemDesc}>
              {MODE_META[slug].description}
            </span>
          </Dropdown.Item>
        ))}
      </Dropdown.Menu>
    </Dropdown>
  );
}
