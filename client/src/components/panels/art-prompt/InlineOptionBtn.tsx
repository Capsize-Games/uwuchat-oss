import type { ReactNode } from "react";
import styles from "./InlineOptionBtn.module.css";

export default function InlineOptionBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={active ? styles.btnActive : styles.btn}
    >
      {children}
    </button>
  );
}
