import { useCallback, useState } from "react";
import { request } from "@/api/client-base";
import styles from "./HostExecConsentCard.module.css";

/** Marker prefix the server emits when a host command needs consent. */
export const HOST_EXEC_CONSENT_PREFIX = "HOST_EXEC_CONSENT::";

/** Parse a tool result into a consent request, or null. */
export function parseHostExecConsent(
  content: string,
): { command: string; group: string } | null {
  if (!content || !content.includes(HOST_EXEC_CONSENT_PREFIX)) return null;
  const idx = content.indexOf(HOST_EXEC_CONSENT_PREFIX);
  const raw = content.slice(idx + HOST_EXEC_CONSENT_PREFIX.length).trim();
  try {
    const parsed = JSON.parse(raw) as {
      command?: string;
      group?: string;
    };
    if (parsed?.command) return { command: parsed.command, group: parsed.group ?? "other" };
  } catch { /* not valid JSON — treat as no consent request */ }
  return null;
}

interface Props {
  command: string;
  group: string;
}

export default function HostExecConsentCard({ command, group }: Props) {
  const [state, setState] = useState<"pending" | "sending" | "done" | "error">(
    "pending",
  );
  const [result, setResult] = useState<string>("");

  const choose = useCallback(
    async (choice: "approve" | "deny" | "always") => {
      setState("sending");
      try {
        const res = await request<{
          id: string;
          command: string;
          consent: string;
          allowed: boolean;
        }>("POST", "/api/v1/uwuchat/host-exec/consent", {
          id: "consent-" + Date.now(),
          command,
          consent: choice,
        });
        setResult(
          res.allowed
            ? "Approved — the command will run on your computer."
            : "Denied — the command will not run.",
        );
        setState("done");
      } catch {
        setState("error");
      }
    },
    [command],
  );

  return (
    <div className={styles.card}>
      <div className={styles.header}>Host command consent</div>
      <div className={styles.command}>
        <code>{command}</code>
      </div>
      <div className={styles.group}>Group: {group}</div>
      {state === "pending" && (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.approve}
            onClick={() => choose("approve")}
          >
            Approve
          </button>
          <button
            type="button"
            className={styles.always}
            onClick={() => choose("always")}
          >
            Always allow
          </button>
          <button
            type="button"
            className={styles.deny}
            onClick={() => choose("deny")}
          >
            Deny
          </button>
        </div>
      )}
      {state === "sending" && (
        <div className={styles.status}>Sending…</div>
      )}
      {state === "done" && (
        <div className={styles.done}>{result}</div>
      )}
      {state === "error" && (
        <div className={styles.error}>Could not send your choice. Try again.</div>
      )}
    </div>
  );
}
