import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useAuth } from "../hooks/useAuth";
import { getUser, updateUser, type UserProfile } from "../api/user";
import {
  isWsConnected,
  onWsConnectionChange,
} from "@/features/api/WsApiClient";

/* ── Public interface (identical to the old useUserSetup shape) ── */

export interface UserSetupState {
  user: UserProfile | null;
  loading: boolean;
  needsSetup: boolean;
  pricingDeclined: boolean;
  saveUser: (values: Partial<UserProfile>) => Promise<boolean>;
  completeSetup: () => Promise<void>;
  declinePricing: () => Promise<void>;
  refresh: () => void;
}

/* ── Internal helpers ── */

const MAX_RETRIES = 10;
const RETRY_DELAY_MS = 2000;

/* ── Default (before provider mounts) ── */

const DEFAULT_STATE: UserSetupState = {
  user: null,
  loading: true,
  needsSetup: false,
  pricingDeclined: false,
  saveUser: async () => false,
  completeSetup: async () => {},
  declinePricing: async () => {},
  refresh: () => {},
};

/* ── Context ── */

const UserSetupContext = createContext<UserSetupState>(DEFAULT_STATE);

export function useUserSetup(): UserSetupState {
  return useContext(UserSetupContext);
}

/* ── Provider ── */

interface ProviderProps {
  children: React.ReactNode;
}

export function UserSetupProvider({ children }: ProviderProps) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const retryCount = useRef(0);
  const mountedRef = useRef(true);

  const { isAuthenticated, isCheckingAuth } = useAuth();

  /* ── Fetch user profile ── */

  useEffect(() => {
    // Wait for AuthContext to finish its own initial auth check.
    if (isCheckingAuth) return;

    if (!isAuthenticated) {
      setUser(null);
      setLoading(false);
      return;
    }

    if (!isWsConnected()) {
      setLoading(true);
      const unsub = onWsConnectionChange(
        (connected: boolean) => {
          if (connected && mountedRef.current) {
            unsub();
            setTick((t: number) => t + 1);
          }
        },
      );
      return () => unsub();
    }

    let cancelled = false;
    retryCount.current = 0;
    setLoading(true);

    const attempt = async () => {
      if (cancelled || !mountedRef.current) return;
      try {
        const u = await getUser();
        if (cancelled || !mountedRef.current) return;
        if (u?.id) {
          setUser(u);
          setLoading(false);
        } else if (retryCount.current < MAX_RETRIES) {
          retryCount.current += 1;
          setTimeout(attempt, RETRY_DELAY_MS);
        } else {
          setLoading(false);
        }
      } catch {
        if (
          retryCount.current < MAX_RETRIES &&
          !cancelled
        ) {
          retryCount.current += 1;
          setTimeout(attempt, RETRY_DELAY_MS);
        } else {
          if (mountedRef.current) setLoading(false);
        }
      }
    };

    attempt();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, isCheckingAuth, tick]);

  /* ── Mutations ── */

  const saveUser = useCallback(
    async (values: Partial<UserProfile>) => {
      try {
        const updated = await updateUser(values);
        if (updated) {
          setUser(updated);
          return true;
        }
        return false;
      } catch {
        return false;
      }
    },
    [],
  );

  const declinePricing = useCallback(async () => {
    const existingData =
      (user?.data ?? {}) as Record<string, unknown>;
    const updated = await updateUser({
      data: { ...existingData, pricing_declined: true },
    });
    if (updated) setUser(updated);
  }, [user]);

  const completeSetup = useCallback(async () => {
    try {
      const updated = await updateUser({
        setup_complete: true,
      });
      if (updated) setUser(updated);
    } catch {
      /* Fallback: next refresh will re-fetch */
    }
    // NOTE: the client-triggered signup gem bonus was removed (security
    // round 10, Part 1) — the server no longer accepts a client-supplied
    // earn amount. Restoring a signup bonus needs a server-driven award
    // triggered from the setup-complete handler, not a client call.
  }, []);

  /* ── Profile-update event listener ── */

  useEffect(() => {
    function handleProfileUpdated(e: Event) {
      const detail = (
        e as CustomEvent<Partial<UserProfile>>
      ).detail;
      if (!detail) return;
      setUser((prev) => (prev ? { ...prev, ...detail } : prev));
    }
    window.addEventListener(
      "uwuchat:user-profile-updated",
      handleProfileUpdated,
    );
    return () =>
      window.removeEventListener(
        "uwuchat:user-profile-updated",
        handleProfileUpdated,
      );
  }, []);

  const refresh = useCallback(() => {
    setTick((t: number) => t + 1);
  }, []);

  /* ── Derived state ── */

  const needsSetup =
    !loading && !!user?.id && !user.setup_complete;

  const pricingDeclined =
    !!user?.data &&
    (user.data as Record<string, unknown>)
      .pricing_declined === true;

  const value: UserSetupState = {
    user,
    loading,
    needsSetup,
    pricingDeclined,
    saveUser,
    completeSetup,
    declinePricing,
    refresh,
  };

  return (
    <UserSetupContext.Provider value={value}>
      {children}
    </UserSetupContext.Provider>
  );
}
