import { createContext, useContext } from "react";

export type TourStep = "system-bot" | "rp-bot";

interface OnboardingTourContextValue {
  replay: (step: TourStep) => void;
}

const OnboardingTourContext = createContext<OnboardingTourContextValue>({
  replay: () => {},
});

export function useOnboardingTourContext(): OnboardingTourContextValue {
  return useContext(OnboardingTourContext);
}

export default OnboardingTourContext;
