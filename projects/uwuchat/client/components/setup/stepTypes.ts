import type { UserProfile } from "../../api/user";

type Step =
  | "name" | "gender" | "language" | "location"
  | "avatar" | "banner" | "status" | "kaomoji"
  | "verify-email"
  | "subscribe";

/** All steps in order — subscribe is last and optional. */
const STEPS: Step[] = [
  "name", "gender", "language", "location",
  "avatar", "banner", "status", "kaomoji",
  "verify-email",
  "subscribe",
];

interface Props {
  user: UserProfile | null;
  onSave: (values: Partial<UserProfile>) => Promise<boolean>;
  onComplete: () => Promise<void>;
  onSubscribe: (tier: string) => Promise<void>;
}

/** Determine which step to start on based on saved profile data. */
function initialStep(
  user: UserProfile | null,
  subscribed: boolean,
): Step {
  if (!user) return "name";
  if (!user.display_name) return "name";
  if (!user.gender) return "gender";
  if (!user.preferred_language) return "language";
  if (!user.latitude || !user.longitude) return "location";
  // Profile completion steps — shown before subscribe.
  if (!user.avatar_image) return "avatar";
  if (!user.banner_image) return "banner";
  const data = (user.data ?? {}) as Record<string, unknown>;
  if (!data.status_message && typeof data.status_message !== "string")
    return "status";
  if (!data.kaomoji && typeof data.kaomoji !== "string")
    return "kaomoji";
  // When pricing was previously declined and the user is not yet
  // subscribed, resume directly at the pricing step so the modal
  // does not force them through all profile steps again.
  if (!subscribed && data.pricing_declined) return "subscribe";
  // verify-email is always reachable — it's a nudge, not a gate.
  // When already subscribed, the wizard ends after verify-email
  // (see SetupWizard — onDone calls handleComplete directly).
  // When not subscribed, verify-email advances to subscribe.
  return "verify-email";
}

export type { Step };
export { STEPS, initialStep };
