import { useState, useEffect, useCallback } from "react";
import { getUser, updateUser, type UserProfile } from "../api/user";

interface OnboardingTour {
  system_bot_seen?: boolean;
  rp_bot_seen?: boolean;
}

interface UseOnboardingTour {
  systemBotSeen: boolean;
  rpBotSeen: boolean;
  markSystemBotSeen: () => Promise<void>;
  markRpBotSeen: () => Promise<void>;
  loading: boolean;
}

export function useOnboardingTour(): UseOnboardingTour {
  const [systemBotSeen, setSystemBotSeen] = useState(false);
  const [rpBotSeen, setRpBotSeen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const profile = await getUser();
        if (cancelled || !profile) return;
        const tour = (profile.data?.onboarding_tour ?? {}) as OnboardingTour;
        setSystemBotSeen(!!tour.system_bot_seen);
        setRpBotSeen(!!tour.rp_bot_seen);
      } catch {
        /* keep defaults */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const mark = useCallback(
    async (key: "system_bot_seen" | "rp_bot_seen") => {
      try {
        const profile = await getUser();
        if (!profile) return;
        const existingData =
          (profile.data ?? {}) as Record<string, unknown>;
        const tour = (existingData.onboarding_tour ?? {}) as OnboardingTour;
        tour[key] = true;
        await updateUser({
          data: { ...existingData, onboarding_tour: tour },
        });
        if (key === "system_bot_seen") setSystemBotSeen(true);
        if (key === "rp_bot_seen") setRpBotSeen(true);
      } catch {
        /* best effort */
      }
    },
    [],
  );

  return {
    systemBotSeen,
    rpBotSeen,
    markSystemBotSeen: () => mark("system_bot_seen"),
    markRpBotSeen: () => mark("rp_bot_seen"),
    loading,
  };
}
