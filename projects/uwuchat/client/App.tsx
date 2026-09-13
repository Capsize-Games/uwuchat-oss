import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Routes, Route, useLocation, useNavigate } from "react-router-dom";
import Layout from "./components/layout/Layout";
import SettingsModal from "./components/settings/SettingsModal";
import { useLayoutPrefs } from "./hooks/useLayoutPrefs";
import {
  extensionRouteElements,
  extensionProviders,
} from "virtual:extensions";
import UwuRegisterPage from "./components/auth/RegisterPage";
import UwuLoginPage from "./components/auth/LoginPage";
import ForgotPasswordPage from "./components/auth/ForgotPasswordPage";
import ResetPasswordPage from "./components/auth/ResetPasswordPage";
import LogoutPage from "./components/auth/LogoutPage";
import TosAgreementPage from "./components/auth/TosAgreementPage";
import TermsOfService from "./components/legal/TermsOfService";
import PrivacyPolicy from "./components/legal/PrivacyPolicy";
import DataRequest from "./components/legal/DataRequest";
import LandingPage from "./components/landing/LandingPage";
import { useAuth, LoadingScreen } from "./hooks/useAuth";
import { MainContent } from "./components/MainContent";
import { SetupWizard } from "./components/setup/SetupWizard";
import { useUserSetup } from "./hooks/useUserSetup";
import { useUwuCreation } from "./hooks/useUwuCreation";
import UwuReadyNotification from "./components/chat/UwuReadyNotification";
import { waitForBootstrap } from "@/features/api/WsApiClient";
import { AdminCostProvider } from "./context/AdminCostContext";
import { UserSetupProvider } from "./context/UserSetupContext";
import UserProfilePage from "./components/user/UserProfilePage";
import ItchioCallbackPage from "./components/auth/ItchioCallbackPage";
import i18n, { SUPPORTED_LANGS } from "./i18n";
import styles from "./App.module.css";

/**
 * Composes all extension providers (AuthProvider, etc.) into a single
 * provider component so that hooks like useAuth() work inside AppBody.
 */
const Providers = extensionProviders.reduce(
  (Acc, Provider) =>
    ({ children }: { children: ReactNode }) =>
      (
        <Acc>
          <Provider>{children}</Provider>
        </Acc>
      ),
  ({ children }: { children: ReactNode }) => <>{children}</>,
);

export default function App() {
  return (
    <Providers>
      <UserSetupProvider>
        <AppBody />
      </UserSetupProvider>
    </Providers>
  );
}

function AppBody() {
  const {
    ttsOn,
    setTtsOn,
    sttOn,
    setSttOn,
    chatbotId,
    setChatbotId,
  } = useLayoutPrefs();

  const [showSettings, setShowSettings] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, isCheckingAuth, user } = useAuth();

  // A brand-new OAuth/Steam account has tos_agreed=false until the ToS
  // interstitial's POST /agree-tos succeeds. Overlays (setup wizard,
  // settings are rendered as siblings of <Routes> below, so
  // they mount regardless of the current path — without this gate, a
  // user sitting on /tos-agreement would see the setup wizard on top
  // of it.
  const tosAgreementPending = !!user && user.tos_agreed === false;
  const blockOverlays =
    tosAgreementPending || location.pathname === "/tos-agreement";

  // Apply the user's saved GUI language as soon as bootstrap arrives.
  useEffect(() => {
    let cancelled = false;
    waitForBootstrap().then((payload) => {
      if (cancelled) return;
      try {
        const appSettings = (
          payload.application_settings as Record<string, unknown>
        ) ?? {};
        const lang = String(appSettings.detected_language ?? "en");
        if (
          SUPPORTED_LANGS.includes(
            lang as (typeof SUPPORTED_LANGS)[number],
          )
        ) {
          i18n.changeLanguage(lang);
        }
      } catch { /* ignore — app renders in default language */ }
    });
    return () => { cancelled = true; };
  }, []);

  // Auto-select the user's first chatbot, validating any cached ID from
  // localStorage against the current tenant's chatbot list.  Runs on auth
  // changes (login/logout) so stale IDs from a different user's session
  // don't persist.  Users with no chatbot and no subscription are sent to
  // the plan picker; subscribers with no chatbot land on the empty chat
  // view and create one via the "New Role-Play Chatbot" sidebar button.
  const chatbotIdRef = useRef(chatbotId);
  chatbotIdRef.current = chatbotId;

  useEffect(() => {
    if (!isAuthenticated || blockOverlays) return;
    let cancelled = false;
    waitForBootstrap().then((payload) => {
      if (cancelled) return;
      try {
        const records =
          (payload.chatbots as Array<{ id: number }>) ?? [];
        if (records.length > 0) {
          const current = chatbotIdRef.current;
          if (
            current !== null &&
            records.some((r) => r.id === current)
          ) {
            return; // cached ID is valid for this tenant
          }
          setChatbotId(records[0].id);
        }
      } catch { /* ignore */ }
    });
    return () => { cancelled = true; };
  }, [isAuthenticated, setChatbotId]);

  const handleCreated = useCallback((id: number) => {
    setChatbotId(id);
    window.dispatchEvent(new Event("uwuchat:uwu-created"));
  }, [setChatbotId]);

  // "New Role-Play Chatbot" now creates a random character immediately.
  // The choice modal ("Random UwU" vs "Build your own") was removed, so
  // connectRandom kicks off durable, server-side generation and returns
  // right away — `connecting` is resumed from server state (survives
  // reload/tab-close, see useUwuCreation) rather than local React state.
  // `readyChatbot` drives the one-time "your UwU is ready" notice;
  // dismissing it is what actually switches the app into the new bot.
  const {
    connectRandom,
    connecting,
    error: connectError,
    readyChatbot,
    acknowledgeReady,
  } = useUwuCreation(handleCreated);

  // Listen for extension-triggered settings open
  useEffect(() => {
    const handler = () => setShowSettings(true);
    window.addEventListener("airunner:open-settings", handler);
    return () => window.removeEventListener("airunner:open-settings", handler);
  }, []);

  useEffect(() => {
    const handler = () => setShowSettings(false);
    window.addEventListener("airunner:close-settings", handler);
    return () => window.removeEventListener("airunner:close-settings", handler);
  }, []);

  // Listen for settings-section navigation — saves the desired section
  // to localStorage first (SettingsModal reads it on mount), then opens.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ section: string }>).detail;
      if (detail?.section) {
        try {
          localStorage.setItem("airunner_settings_section", detail.section);
        } catch { /* ignore */ }
      }
      setShowSettings(true);
    };
    window.addEventListener("airunner:open-settings-section", handler);
    return () =>
      window.removeEventListener("airunner:open-settings-section", handler);
  }, []);

  const handleSelectChatbot = useCallback(
    (id: number | null) => { setChatbotId(id); },
    [setChatbotId],
  );

  const {
    needsSetup,
    loading: setupLoading,
    user: setupUser,
    saveUser,
    completeSetup,
  } = useUserSetup();

  // The wizard stays visible until the user completes the short
  // first-run setup (name → language → verification reminder).
  // forceWizard is cleared in handleSetupComplete so the wizard does
  // not re-open after setup is finished.
  const [forceWizard, setForceWizard] = useState(
    () => sessionStorage.getItem("uwuchat_continue_wizard") === "1",
  );

  // When the user declines pricing, hide the wizard for this session.
  // It reopens on the next reload (needsSetup stays true because
  // setup_complete is still false).  needsSetup remains the outer gate
  const showWizard =
    !!user &&
    !blockOverlays &&
    !user?.is_superuser &&
    (
      forceWizard ||
      needsSetup
    );

  const handleSetupComplete = useCallback(async () => {
    sessionStorage.removeItem("uwuchat_continue_wizard");
    await completeSetup();
    setForceWizard(false);
  }, [completeSetup]);


  // While the setup hook is still fetching the user record, show a
  // full-screen loading overlay so the user cannot interact with the
  // app before their account state has been determined.  This is
  // especially important after OAuth sign-up where the wizard must
  // appear before any other interaction.
  //
  // AuthContext.isCheckingAuth gates the initial token validation;
  // setupLoading gates the subsequent user-profile fetch (WS connect +
  // getUser).  Both use the same LoadingScreen component so there is
  // exactly one full-screen overlay, and it turns off once, when both
  // signals resolve.
  if (isCheckingAuth || (setupLoading && isAuthenticated)) {
    return <LoadingScreen />;
  }

  return (
    <AdminCostProvider chatbotId={chatbotId} adminPanelOpen={false}>
    <Routes>
      <Route
        path="/"
        element={
          <HomeRoute
            chatbotId={chatbotId}
            ttsOn={ttsOn}
            sttOn={sttOn}
            setTtsOn={setTtsOn}
            setSttOn={setSttOn}
            onCreateUwu={connectRandom}
            connecting={connecting}
            connectError={connectError}
            handleSelectChatbot={handleSelectChatbot}
          />
        }
      />
      <Route path="/login" element={<UwuLoginPage />} />
      <Route path="/logout" element={<LogoutPage />} />
      <Route path="/register" element={<UwuRegisterPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/tos-agreement" element={<TosAgreementPage />} />
      <Route path="/terms" element={<TermsOfService />} />
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/data-request" element={<DataRequest />} />
      <Route path="/user/:username" element={<UserProfilePage />} />
      <Route
        path="/settings"
        element={<SettingsModal onClose={() => navigate("/")} />}
      />
      <Route path="/itch/callback" element={<ItchioCallbackPage />} />
      {extensionRouteElements}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>

    {showSettings && (
      <SettingsModal onClose={() => setShowSettings(false)} />
    )}

    {showWizard && (
      <SetupWizard
        user={setupUser}
        onSave={saveUser}
        onComplete={handleSetupComplete}
      />
    )}

    {readyChatbot && (
      <UwuReadyNotification
        chatbot={readyChatbot}
        onDismiss={acknowledgeReady}
      />
    )}

    </AdminCostProvider>
  );
}

/* ── HomeRoute: renders Layout or LandingPage based on auth ──── */
/* Must live inside Providers so useAuth() has access to AuthProvider. */

interface HomeRouteProps {
  chatbotId: number | null;
  ttsOn: boolean;
  sttOn: boolean;
  setTtsOn: (v: boolean) => void;
  setSttOn: (v: boolean) => void;
  onCreateUwu: () => void;
  connecting: boolean;
  connectError: string | null;
  handleSelectChatbot: (id: number | null) => void;
}

function HomeRoute({
  chatbotId,
  ttsOn,
  sttOn,
  setTtsOn,
  setSttOn,
  onCreateUwu,
  connecting,
  connectError,
  handleSelectChatbot,
}: HomeRouteProps) {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <LandingPage />;
  }

  return (
    <Layout>
      <MainContent
        chatbotId={chatbotId}
        onSelectChatbot={handleSelectChatbot}
        ttsOn={ttsOn}
        onToggleTts={() => setTtsOn(!ttsOn)}
        sttOn={sttOn}
        onToggleStt={() => setSttOn(!sttOn)}
        onCreateUwu={onCreateUwu}
        connecting={connecting}
        connectError={connectError}
      />
    </Layout>
  );
}

function NotFoundPage() {
  return (
    <div className={styles.notFoundBg}>
      <div className={styles.notFoundInner}>
        <h1 className={styles.notFoundTitle}>404</h1>
        <p className={styles.notFoundText}>Page not found</p>
      </div>
    </div>
  );
}
