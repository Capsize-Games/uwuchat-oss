// ── Welcome Screen ──────────────────────────────────────────────────────
import LucideIcon from "../shared/LucideIcon";
import styles from "./WelcomeScreen.module.css";

interface Props {
  onOpenChat: () => void;
  onOpenCanvas: () => void;
  onOpenCivitai: () => void;
}

export default function WelcomeScreen({
  onOpenChat,
  onOpenCanvas,
  onOpenCivitai,
}: Props) {
  const items = [
    {
      key: "chat",
      icon: "bot-message-square",
      label: "Chat",
      hint: "Talk to a local LLM",
      onClick: onOpenChat,
    },
    {
      key: "canvas",
      icon: "image",
      label: "Canvas",
      hint: "Generate and edit images",
      onClick: onOpenCanvas,
    },
    {
      key: "civitai",
      icon: "globe",
      label: "CivitAI",
      hint: "Browse and download models",
      onClick: onOpenCivitai,
    },
  ];

  return (
    <div className={"flex-grow-1 d-flex flex-column align-items-center justify-content-center text-theme-secondary user-select-none " + styles.outer}>
      <div className={"d-flex flex-column align-items-center " + styles.logoWrap}>
        <img
          src="/favicon.svg"
          alt="AI Runner"
          className={styles.logo}
        />
        <h2 className={styles.title}>
          AI Runner
        </h2>
        <p className={styles.subtitle}>
          Open a panel from the sidebar to get started.
        </p>
      </div>

      <div className={"d-flex flex-column w-100 " + styles.buttons}>
        {items.map(({ key, icon, label, hint, onClick }) => (
          <button
            key={key}
            type="button"
            onClick={onClick}
            className={styles.cardBtn}
          >
            <span className={styles.icon}>
              <LucideIcon name={icon} size={20} />
            </span>
            <div className={"d-flex flex-column " + styles.btnHintWrap}>
              <span className={styles.btnLabel}>
                {label}
              </span>
              <span className={styles.btnHint}>
                {hint}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
