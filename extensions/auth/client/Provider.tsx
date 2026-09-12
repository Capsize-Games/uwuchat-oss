/**
 * Auth provider that manages JWT tokens and user state.
 *
 * Wraps the application and provides an auth context to all children.
 * Handles token storage in localStorage, session restoration on mount,
 * and renders a loading screen while auth state is resolved.
 *
 * When the user is not authenticated, the app still renders — the
 * login/register routes handle themselves.  Core app content that
 * requires authentication should use the `requireAuth` mechanism.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { FC, ReactNode } from "react";
import {
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  deleteAccount as apiDeleteAccount,
  refreshAccessToken,
  type AgreementFlags,
} from "./api";
import { clearMessagesDB } from "@/hooks/messagesDB";
import { clearConversationsDB } from "@/hooks/conversationsDB";

interface User {
  id: number;
  email: string;
  username: string;
  is_verified?: boolean;
  is_superuser?: boolean;
  is_suspended?: boolean;
  tos_agreed?: boolean;
}

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isCheckingAuth: boolean;
  isLoggingIn: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    username: string,
    password: string,
    flags?: AgreementFlags,
    inviteCode?: string,
    waitlistToken?: string,
  ) => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: (password: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}

// Storage keys
const ACCESS_TOKEN_KEY = "airunner_access_token";
const REFRESH_TOKEN_KEY = "airunner_refresh_token";

function loadAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

function saveTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function getTokenExpiryMs(token: string): number | null {
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

// Paths that do NOT require authentication
const PUBLIC_PATHS = [
  "/",
  "/login",
  "/logout",
  "/register",
  "/verify",
  "/oauth/callback",
  "/itch/callback",
  "/tos-agreement",
  "/terms",
  "/privacy",
  "/data-request",
  "/subscribe",
  "/subscribe/success",
  "/subscribe/cancel",
];

function isPublicPath(): boolean {
  return PUBLIC_PATHS.includes(window.location.pathname);
}

// Paths whose own UI does not depend on knowing the auth state up
// front (they render the same thing whether or not a stored token
// turns out to be valid). Blocking these behind the full-screen
// "Signing in…" loader just adds a pointless flash before the page
// the user actually navigated to appears.
const AUTH_CHECK_EXEMPT_PATHS = ["/login", "/register"];

function isAuthCheckExemptPath(): boolean {
  return AUTH_CHECK_EXEMPT_PATHS.includes(window.location.pathname);
}

/**
 * Minimal full-screen loading state shown while the stored token is
 * being validated against the server.
 */
export const LoadingScreen: FC = () => (
  <div
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      height: "100vh",
      fontFamily: "sans-serif",
      color: "#888",
    }}
  >
    Signing in…
  </div>
);

export const Provider: FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(
    loadAccessToken,
  );
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  // Only check auth on initial mount when there's a stored token.
  // This prevents the loading screen from flashing on re-renders.
  const [isCheckingAuth, setIsCheckingAuth] = useState(
    loadAccessToken() !== null,
  );
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isAuthenticated = user !== null && accessToken !== null;

  const scheduleTokenRefresh = useCallback((token: string) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    const expMs = getTokenExpiryMs(token);
    if (!expMs) return;
    // Refresh 60 seconds before expiry
    const delay = expMs - Date.now() - 60_000;
    if (delay <= 0) return;
    refreshTimerRef.current = setTimeout(async () => {
      const storedRefresh = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (!storedRefresh) return;
      try {
        const { access_token } = await refreshAccessToken(storedRefresh);
        localStorage.setItem(ACCESS_TOKEN_KEY, access_token);
        setAccessToken(access_token);
        scheduleTokenRefresh(access_token);
      } catch {
        // Silently clear tokens on background refresh failure.
        // Do NOT redirect — the user is actively using the app and
        // the refresh endpoint may be temporarily unavailable while
        // the current access token is still valid.  The next explicit
        // request will surface the auth failure naturally.
        clearTokens();
        setAccessToken(null);
        setUser(null);
      }
    }, delay);
  }, []);

  // On mount, validate stored token and restore session.
  useEffect(() => {
    const token = loadAccessToken();
    if (!token) {
      setIsCheckingAuth(false);
      if (!isPublicPath()) {
        window.location.href = "/login";
      }
      return;
    }

    import("./api")
      .then((api) => api.getMe(token))
      .then((profile) => {
        setUser(profile);
        setIsCheckingAuth(false);
        scheduleTokenRefresh(token);
      })
      .catch(() => {
        // Token expired or invalid.
        clearTokens();
        setAccessToken(null);
        setUser(null);
        setIsCheckingAuth(false);
        // Only redirect to login for non-public paths.
        // Public paths (like /itch/callback) should render even
        // without auth — they handle their own redirect flow.
        if (!isPublicPath() && window.location.pathname !== "/") {
          window.location.href = "/login";
        }
      });

    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, [scheduleTokenRefresh]);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoggingIn(true);
    try {
      const result = await apiLogin(email, password);
      saveTokens(result.access_token, result.refresh_token);
      setAccessToken(result.access_token);

      const profile = await import("./api").then((api) =>
        api.getMe(result.access_token),
      );
      setUser(profile);
      scheduleTokenRefresh(result.access_token);
    } finally {
      setIsLoggingIn(false);
    }
  }, [scheduleTokenRefresh]);

  const register = useCallback(
    async (
      email: string,
      password: string,
      flags?: AgreementFlags,
      inviteCode?: string,
      waitlistToken?: string,
    ) => {
      setIsLoggingIn(true);
      try {
        const result = await apiRegister(
          email,
          password,
          flags,
          inviteCode,
          waitlistToken,
        );
        saveTokens(result.access_token, result.refresh_token);
        setAccessToken(result.access_token);

        // Fetch the profile to complete initialization.  The account
        // already exists server-side at this point (the registration
        // endpoint committed it), so a failure here must NOT cause the
        // caller to report "Registration failed" — the user simply
        // won't be fully signed in until the next page navigation
        // triggers a token-refresh-based session restore.
        try {
          const profile = await import("./api").then((api) =>
            api.getMe(result.access_token),
          );
          setUser(profile);
          scheduleTokenRefresh(result.access_token);
        } catch {
          // Profile fetch failed; tokens are already saved so the
          // session can be restored on the next navigation.
        }
      } finally {
        setIsLoggingIn(false);
      }
    },
    [scheduleTokenRefresh],
  );

  const deleteAccount = useCallback(async (password: string) => {
    const token = loadAccessToken();
    if (!token) return;
    await apiDeleteAccount(token, password);
    clearTokens();
    // Clear IndexedDB caches so stale data from this account doesn't
    // survive the client side after a GDPR erasure. Awaited (not
    // fire-and-forget) because the immediately-following navigation
    // can abort in-flight IndexedDB transactions before they finish.
    await Promise.all([clearMessagesDB(), clearConversationsDB()]);
    setAccessToken(null);
    setUser(null);
    window.location.href = "/login";
  }, []);

  const logout = useCallback(async () => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    const token = loadAccessToken();
    if (token) {
      // Fire-and-forget server-side revocation; don't block the UI.
      void apiLogout(token);
    }
    clearTokens();
    // Clear IndexedDB caches so the next account to log in on this
    // machine doesn't briefly see the previous account's data.
    // Awaited for the same reason as deleteAccount above.
    await Promise.all([clearMessagesDB(), clearConversationsDB()]);
    setAccessToken(null);
    setUser(null);
    window.location.href = "/login";
  }, []);

  // When the DEK cache expires server-side, every RPC that touches
  // encrypted data fails with error_code="encryption_session_expired".
  // WsApiClient dispatches a DOM event so we can force logout globally
  // without every hook needing to know about this condition.  The
  // listener is registered once for the lifetime of the provider —
  // no dependency-driven subscription needed (same pattern as
  // ChatView.tsx's airunner:show-admin-* listeners).
  useEffect(() => {
    const handler = () => {
      logout();
    };
    window.addEventListener(
      "airunner:encryption-session-expired",
      handler,
    );
    return () => {
      window.removeEventListener(
        "airunner:encryption-session-expired",
        handler,
      );
    };
  }, [logout]);

  const value = useMemo(
    () => ({
      user,
      accessToken,
      isAuthenticated,
      isCheckingAuth,
      isLoggingIn,
      login,
      register,
      logout,
      deleteAccount,
    }),
    [
      user,
      accessToken,
      isAuthenticated,
      isCheckingAuth,
      isLoggingIn,
      login,
      register,
      logout,
      deleteAccount,
    ],
  );

  // Show a loading indicator while restoring the session.
  // This prevents a flash of the main app before we know the auth state.
  if (isCheckingAuth) {
    if (isAuthCheckExemptPath()) {
      return (
        <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
      );
    }
    return (
      <AuthContext.Provider value={value}>
        <LoadingScreen />
      </AuthContext.Provider>
    );
  }

  // Suspended users see only a suspension notice — nothing else.
  if (user?.is_suspended) {
    return (
      <AuthContext.Provider value={value}>
        <SuspensionScreen onLogout={logout} />
      </AuthContext.Provider>
    );
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;


/**
 * Full-screen notice shown to suspended users.  The only available
 * action is signing out.
 */
function SuspensionScreen({ onLogout }: { onLogout: () => void }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        fontFamily: "sans-serif",
        color: "#ccc",
        background: "#16162a",
      }}
    >
      <div style={{ textAlign: "center", maxWidth: 420, padding: 32 }}>
        <h1 style={{ fontSize: 20, marginBottom: 16, color: "#fbbf24" }}>
          Account suspended
        </h1>
        <p style={{ fontSize: 14, lineHeight: 1.6, marginBottom: 24 }}>
          Your account has been suspended. Please contact support if you
          believe this is a mistake.
        </p>
        <button
          onClick={onLogout}
          style={{
            padding: "8px 24px",
            fontSize: 14,
            border: "1px solid #555",
            borderRadius: 4,
            background: "transparent",
            color: "#ccc",
            cursor: "pointer",
          }}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
};
