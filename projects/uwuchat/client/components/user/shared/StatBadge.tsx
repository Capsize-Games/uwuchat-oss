import React from "react";
import styles from "./StatBadge.module.css";

export default function StatBadge({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className={styles.badge}>
      <div className={styles.value}>
        {value.toLocaleString()}
      </div>
      <div className={styles.label}>
        {label}
      </div>
    </div>
  );
}
