/**
 * Maps a chatbot's species_data (type/subtype) to a small visual badge for
 * contact-list rows. All species badges render as monochrome lucide icons
 * (never emoji) so the badge row has one consistent visual language —
 * mixing colorful animal emoji next to grey icons for monster/mythical/
 * robot types looked inconsistent. A handful of animal subtypes get a
 * specific icon (cat, dog, rabbit, turtle, bird-ish, bug-ish); everything
 * else falls back to one generic icon per category, with the exact
 * subtype surfaced via the hover tooltip.
 */

export type SpeciesType = "human" | "animal" | "monster" | "mythical" | "robot";

export interface SpeciesBadge {
  /** Lucide icon name to render. */
  icon: string;
  /** Tooltip text — always shows the real classification/subtype. */
  label: string;
}

const ANIMAL_ICON: Record<string, string> = {
  cat: "cat",
  dog: "dog",
  rabbit: "rabbit",
  turtle: "turtle",
  owl: "bird",
  penguin: "bird",
  crow: "bird",
  dragonfly: "bug",
};

const MONSTER_ICON: Record<string, string> = {
  ghost: "ghost",
};

/** Species types with no useful visual differentiation by subtype. */
const CATEGORY_FALLBACK: Record<SpeciesType, { icon: string; label: string }> = {
  human: { icon: "user", label: "Human" },
  animal: { icon: "paw-print", label: "Animal" },
  monster: { icon: "skull", label: "Monster" },
  mythical: { icon: "sparkles", label: "Mythical creature" },
  robot: { icon: "bot", label: "Robot" },
};

const SUBTYPE_ICON: Record<SpeciesType, Record<string, string>> = {
  human: {},
  animal: ANIMAL_ICON,
  monster: MONSTER_ICON,
  mythical: {},
  robot: {},
};

function titleCase(s: string): string {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Returns null for humans (the common/default case) so contact rows don't
 * show a badge for the majority of chatbots — only non-human species get
 * a visual marker.
 */
export function getSpeciesBadge(
  type?: string | null,
  subtype?: string | null,
): SpeciesBadge | null {
  const t = (type ?? "").toLowerCase() as SpeciesType;
  if (!t || t === "human") return null;

  const sub = (subtype ?? "").toLowerCase();
  const fallback = CATEGORY_FALLBACK[t] ?? CATEGORY_FALLBACK.animal;
  const specific = SUBTYPE_ICON[t]?.[sub];

  return {
    icon: specific ?? fallback.icon,
    label: subtype ? `${titleCase(sub)} (${fallback.label})` : fallback.label,
  };
}

export function getGenderBadge(
  gender?: string | null,
): { icon: string; label: string } | null {
  if (!gender) return null;
  const g = gender.toLowerCase();
  if (g === "male" || g === "he/him" || g === "he_him" || g === "he him") {
    return { icon: "mars", label: "Male" };
  }
  if (g === "female" || g === "she/her" || g === "she_her" || g === "she her") {
    return { icon: "venus", label: "Female" };
  }
  if (g === "non-binary" || g === "nonbinary" || g === "enby"
      || g === "they/them" || g === "they_them" || g === "they them") {
    return { icon: "non-binary", label: "Non-binary" };
  }
  if (g === "transgender" || g === "trans" || g === "transfeminine"
      || g === "transmasculine") {
    return { icon: "transgender", label: "Transgender" };
  }
  if (g === "intersex" || g === "hermaphrodite") {
    return { icon: "venus-and-mars", label: "Intersex" };
  }
  if (g === "genderfluid" || g === "genderqueer") {
    return { icon: "mars-stroke", label: "Genderfluid" };
  }
  return null;
}
