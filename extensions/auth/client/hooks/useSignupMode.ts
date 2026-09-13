/**
 * Hook that fetches the server's current signup mode.
 *
 * Calls GET /api/v1/auth/invite-required and returns:
 * - required: whether an invite code is active
 * - signup_mode: "open" | "waitlist"
 */

import { useEffect, useState } from "react";

export interface SignupMode {
  required: boolean;
  signup_mode: "open" | "waitlist";
  loading: boolean;
}

export function useSignupMode(): SignupMode {
  const [mode, setMode] = useState<Omit<SignupMode, "loading">>({
    required: false,
    signup_mode: "open",
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/auth/invite-required")
      .then((r) => r.json())
      .then((d: { required: boolean; signup_mode: string }) => {
        if (!cancelled) {
          setMode({
            required: !!d.required,
            signup_mode:
              d.signup_mode === "waitlist" ? "waitlist" : "open",
          });
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { ...mode, loading };
}
