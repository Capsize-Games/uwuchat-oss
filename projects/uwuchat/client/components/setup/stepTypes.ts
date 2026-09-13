import type { UserProfile } from "../../api/user";

type Step = "name" | "language" | "verify-email";

/** All steps in order — subscribe is last and optional. */
const STEPS: Step[] = ["name", "language", "verify-email"];

/** Determine which step to start on based on saved profile data. */
function initialStep(user: UserProfile | null): Step {
  if (!user) return "name";
  if (!user.display_name) return "name";
  if (!user.preferred_language) return "language";
  return "verify-email";
}

export type { Step };
export { STEPS, initialStep };
