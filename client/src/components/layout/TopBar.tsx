// ── Top Bar ─────────────────────────────────────────────────────────────
// App header with logo and integrated action menu bar.
// ──────────────────────────────────────────────────────────────────────────
import ActionMenuBar from "./action-menu-bar";
import styles from "./TopBar.module.css";

export default function TopBar() {
  return (
    <div className="topbar">
      <div className="topbar-logo">
        AI <span>Runner</span>
      </div>
      <div className={styles.menuArea}>
        <ActionMenuBar />
      </div>
    </div>
  );
}
