import React from "react";
import LucideIcon from "@/components/shared/LucideIcon";
import { getGenderBadge } from "../../utils/speciesIcon";
import styles from "./GenderBadge.module.css";

interface GenderBadgeProps {
  gender: string | null;
}

export default function GenderBadge({ gender }: GenderBadgeProps) {
  const badge = getGenderBadge(gender);
  if (!badge) return null;

  return (
    <span title={badge.label} className={styles.badge}>
      <LucideIcon name={badge.icon} size={16} />
    </span>
  );
}
