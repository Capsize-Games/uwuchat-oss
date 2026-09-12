import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_GROUPS,
  GROUP_LABELS,
  getHostExecPolicy,
  saveHostExecPolicy,
  type HostExecPolicy,
} from "../../../api/hostExec";
import styles from "./HostExecSection.module.css";

function defaultPolicy(): HostExecPolicy {
  return {
    enabled: true,
    enable_all: false,
    groups: { ...DEFAULT_GROUPS },
    whitelist: [],
    blacklist: [],
    allow_always: [],
  };
}

function ListEditor({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
}) {
  return (
    <label className={styles.listEditor}>
      <span className={styles.listLabel}>{label}</span>
      <textarea
        className={styles.textarea}
        value={value.join("\n")}
        onChange={(e) =>
          onChange(e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))
        }
        placeholder={placeholder}
        rows={4}
      />
      <span className={styles.hint}>One entry per line.</span>
    </label>
  );
}

export default function HostExecSection() {
  const [policy, setPolicy] = useState<HostExecPolicy>(defaultPolicy);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHostExecPolicy()
      .then((p) => {
        if (cancelled) return;
        setPolicy({
          enabled: p.enabled ?? true,
          enable_all: p.enable_all ?? false,
          groups: { ...DEFAULT_GROUPS, ...(p.groups ?? {}) },
          whitelist: p.whitelist ?? [],
          blacklist: p.blacklist ?? [],
          allow_always: p.allow_always ?? [],
        });
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError("Could not load the host-command policy.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await saveHostExecPolicy(policy);
      setSaved(true);
    } catch {
      setError("Could not save the policy.");
    } finally {
      setSaving(false);
    }
  }, [policy]);

  if (loading) {
    return <div className={styles.loading}>Loading…</div>;
  }

  return (
    <div className={styles.wrap}>
      <h3 className={styles.title}>Host Command Execution</h3>
      <p className={styles.description}>
        Control which commands the code-mode assistant may run on your
        computer (git push, gh writes, shell commands). Commands that need
        host access are gated by this policy and prompt for your approval.
      </p>

      <label className={styles.row}>
        <input
          type="checkbox"
          checked={policy.enabled}
          onChange={(e) => setPolicy({ ...policy, enabled: e.target.checked })}
        />
        <span>Enable host command execution</span>
      </label>

      <label className={styles.row}>
        <input
          type="checkbox"
          checked={policy.enable_all}
          onChange={(e) =>
            setPolicy({ ...policy, enable_all: e.target.checked })
          }
        />
        <span>Enable all (skip consent prompts — the blacklist still applies)</span>
      </label>

      <div className={styles.groupBlock}>
        <span className={styles.groupTitle}>Command groups</span>
        {Object.keys(GROUP_LABELS).map((group) => (
          <label key={group} className={styles.row}>
            <input
              type="checkbox"
              checked={policy.groups[group] ?? false}
              onChange={(e) =>
                setPolicy({
                  ...policy,
                  groups: { ...policy.groups, [group]: e.target.checked },
                })
              }
            />
            <span>{GROUP_LABELS[group]}</span>
          </label>
        ))}
      </div>

      <ListEditor
        label="Whitelist (always allow, no prompt)"
        value={policy.whitelist}
        onChange={(whitelist) => setPolicy({ ...policy, whitelist })}
        placeholder={"gh issue list\ngit status"}
      />

      <ListEditor
        label="Blacklist (always block, even with Enable all)"
        value={policy.blacklist}
        onChange={(blacklist) => setPolicy({ ...policy, blacklist })}
        placeholder={"sudo\nrm -rf /"}
      />

      <ListEditor
        label="Always allow (per-command approvals you accepted)"
        value={policy.allow_always}
        onChange={(allow_always) => setPolicy({ ...policy, allow_always })}
        placeholder={"git push origin main"}
      />

      <div className={styles.actions}>
        <button
          type="button"
          className={styles.saveBtn}
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? "Saving…" : "Save policy"}
        </button>
        {saved && <span className={styles.saved}>Saved.</span>}
      </div>
      {error && <div className={styles.error}>{error}</div>}
    </div>
  );
}
