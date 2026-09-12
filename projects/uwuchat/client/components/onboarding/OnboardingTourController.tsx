import {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useOnboardingTour } from "../../hooks/useOnboardingTour";
import OnboardingTourContext, {
  type TourStep,
} from "./OnboardingTourContext";
import OnboardingCallout from "./OnboardingCallout";

type TourState = "idle" | "active";

const POLL_INTERVAL_MS = 500;

interface Props {
  children: ReactNode;
  /** When true, the tour is eligible to auto-start (wizard completed). */
  enabled: boolean;
}

export default function OnboardingTourController({
  children,
  enabled,
}: Props) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const {
    systemBotSeen,
    rpBotSeen,
    markSystemBotSeen,
    markRpBotSeen,
    loading: tourLoading,
  } = useOnboardingTour();

  const [activeStep, setActiveStep] = useState<TourStep | null>(null);
  const [tourState, setTourState] = useState<TourState>("idle");
  const autoStartedRef = useRef(false);

  // Auto-start tour only after the setup wizard is complete.
  useEffect(() => {
    if (tourLoading || autoStartedRef.current) return;
    if (!enabled) return;
    autoStartedRef.current = true;
    if (!systemBotSeen) {
      setTourState("active");
      setActiveStep("system-bot");
    } else if (!rpBotSeen) {
      setTourState("active");
      setActiveStep("rp-bot");
    }
  }, [tourLoading, enabled, systemBotSeen, rpBotSeen]);

  // Listen for manual replay requests.
  useEffect(() => {
    function handler(e: Event) {
      const step = (e as CustomEvent<TourStep>).detail;
      if (step === "system-bot" || step === "rp-bot") {
        setTourState("active");
        setActiveStep(step);
      }
    }
    window.addEventListener("onboarding-tour:replay", handler);
    return () =>
      window.removeEventListener(
        "onboarding-tour:replay",
        handler,
      );
  }, []);

  // Anchor discovery (polling).
  const [polledAnchor, setPolledAnchor] =
    useState<HTMLElement | null>(null);
  useEffect(() => {
    if (!activeStep) {
      setPolledAnchor(null);
      return;
    }
    const interval = setInterval(() => {
      const el = document.querySelector<HTMLElement>(
        `[data-onboarding-anchor="${activeStep}"]`,
      );
      if (el) setPolledAnchor(el);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [activeStep]);

  // "Got it" (close / outside-click): mark current step seen, stop.
  const handleClose = useCallback(() => {
    if (activeStep === "system-bot") {
      markSystemBotSeen();
    } else if (activeStep === "rp-bot") {
      markRpBotSeen();
    }
    setActiveStep(null);
    setTourState("idle");
  }, [activeStep, markSystemBotSeen, markRpBotSeen]);

  // "Next": mark step seen, advance. Only shown on step 1.
  const handleNext = useCallback(() => {
    if (activeStep === "system-bot") {
      markSystemBotSeen();
      setActiveStep("rp-bot");
    } else if (activeStep === "rp-bot") {
      markRpBotSeen();
      setActiveStep(null);
      setTourState("idle");
    }
  }, [activeStep, markSystemBotSeen, markRpBotSeen]);

  const replay = useCallback((step: TourStep) => {
    setTourState("active");
    setActiveStep(step);
  }, []);

  const contextValue = useMemo(() => ({ replay }), [replay]);

  const stepLabel =
    activeStep === "system-bot"
      ? t("onboarding_tour.system_bot_label")
      : activeStep === "rp-bot"
        ? t("onboarding_tour.rp_bot_label")
        : "";

  const stepText =
    activeStep === "system-bot"
      ? t("onboarding_tour.system_bot_text")
      : activeStep === "rp-bot"
        ? t("onboarding_tour.rp_bot_text")
        : "";

  // Check whether an RP bot anchor exists in the DOM.
  const [rpBotExists, setRpBotExists] = useState(false);
  useEffect(() => {
    const interval = setInterval(() => {
      const el = document.querySelector(
        '[data-onboarding-anchor="rp-bot"]',
      );
      setRpBotExists(!!el);
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // "Next" only shown on the first step when an RP bot actually
  // exists — otherwise the tour is a single step with no advance.
  const showNext = activeStep === "system-bot" && rpBotExists;

  return (
    <OnboardingTourContext.Provider value={contextValue}>
      {children}
      {activeStep && (
        <OnboardingCallout
          anchorEl={polledAnchor}
          placement={isMobile ? "below" : "left"}
          text={stepText}
          label={stepLabel}
          onClose={handleClose}
          onNext={showNext ? handleNext : undefined}
        />
      )}
    </OnboardingTourContext.Provider>
  );
}
