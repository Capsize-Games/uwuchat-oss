/**
 * Immersion level preference for UwUchat.
 *
 * - "minimal": Tokens stream in live, no artificial delays.
 * - "full":    Artificial reading/typing delays + "{name} is typing…" indicator.
 *
 * Persisted in the server DB (ProjectSetting table, key="immersion") so the
 * setting syncs across devices.  localStorage is used as a fast initial value
 * while the server load is in flight, and as a fallback when offline.
 */

import { useState, useCallback } from "react";
import { useEffectOnce } from "@/hooks/useEffectOnce";
import { createResource, updateResource } from "@/api/settings";
import { waitForBootstrap } from "@/features/api/WsApiClient";

const LS_KEY = "uwuchat_immersion";
const LS_EXPLICIT_KEY = "uwuchat_immersion_explicit";
const RESOURCE = "ProjectSetting";
const SETTING_KEY = "immersion";

export type ImmersionLevel = "minimal" | "full";

function readLocal(): ImmersionLevel {
  try {
    const v = localStorage.getItem(LS_KEY);
    if (v === "minimal" || v === "full") return v;
  } catch {
    /* localStorage unavailable */
  }
  return "full";
}

function writeLocal(level: ImmersionLevel): void {
  try {
    localStorage.setItem(LS_KEY, level);
  } catch {
    /* ignore */
  }
}

/** True when the user has explicitly changed the immersion setting on
 *  this device (via setLevel / the Settings UI), as opposed to the
 *  value being the compiled-in default from an empty localStorage. */
function hasExplicitChoice(): boolean {
  try {
    return localStorage.getItem(LS_EXPLICIT_KEY) === "1";
  } catch {
    return false;
  }
}

/** Mark that the user has made an explicit immersion choice on this
 *  device, so future mounts can distinguish "user chose full" from
 *  "no preference set yet, defaulting to full." */
function markExplicit(): void {
  try {
    localStorage.setItem(LS_EXPLICIT_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function useImmersion() {
  const [level, setLevelState] = useState<ImmersionLevel>(readLocal);
  const [dbId, setDbId] = useState<number | null>(null);

  useEffectOnce(() => {
    let cancelled = false;
    waitForBootstrap()
      .then((payload) => {
        if (cancelled) return;
        try {
          const ps = payload.project_setting as
            | Record<string, { id?: number; value?: string }>
            | undefined;
          const record = ps?.immersion;
          if (record?.id) {
            setDbId(record.id);
            const v = record.value;
            if (v === "minimal" || v === "full") {
              if (hasExplicitChoice()) {
                // The user has previously made an explicit choice on
                // this device.  If local differs from DB, the user's
                // local change is more recent than the last successful
                // DB write — keep local and push it to DB so the
                // inconsistency is fixed for future mounts on other
                // devices.  If they match, no action needed.
                const local = readLocal();
                if (local !== v) {
                  setLevelState(local);
                  updateResource(RESOURCE, record.id, { value: local })
                    .catch(() => {});
                } else {
                  setLevelState(v);
                  writeLocal(v);
                }
              } else {
                // Fresh device (user has never changed the setting
                // locally).  Trust the DB value unconditionally —
                // this is the cross-device sync path: a user who
                // set "minimal" on another device will see "minimal"
                // here too, even though readLocal() defaults to "full".
                setLevelState(v);
                writeLocal(v);
              }
            }
          }
        } catch {
          /* keep localStorage value */
        }
      })
      .catch(() => {
        /* offline — keep localStorage value */
      });
    return () => {
      cancelled = true;
    };
  });

  const setLevel = useCallback(
    (next: ImmersionLevel) => {
      setLevelState(next);
      writeLocal(next);
      markExplicit();
      if (dbId !== null) {
        updateResource(RESOURCE, dbId, { value: next }).catch(() => {});
      } else {
        createResource(RESOURCE, { key: SETTING_KEY, value: next })
          .then((res) => {
            // Server wraps the created row in { record: { id, ... } }
            const raw = res as Record<string, unknown>;
            const id =
              (raw["record"] as Record<string, unknown> | undefined)?.["id"] ??
              raw["id"];
            if (typeof id === "number") setDbId(id);
          })
          .catch(() => {});
      }
    },
    [dbId],
  );

  return { immersion: level, setImmersion: setLevel };
}

export function getImmersion(): ImmersionLevel {
  return readLocal();
}
