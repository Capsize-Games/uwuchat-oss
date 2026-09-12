import { Star } from "lucide-react";
import { useCallback, type ReactNode } from "react";
import { BotMessageSquare } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "./LanguageSwitcher";
import styles from "./PublicShell.module.css";

const YEAR = new Date().getFullYear();

interface PublicShellProps { children: ReactNode; contentClass?: string; stickyFooter?: boolean; }

export function PublicShell({ children, contentClass, stickyFooter = true }: PublicShellProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const go = useCallback((path: string) => (e: { preventDefault(): void }) => { e.preventDefault(); navigate(path); }, [navigate]);

  const contentClassName = `${stickyFooter ? styles.content : styles.contentNoSticky}${contentClass ? ` ${contentClass}` : ""}`;

  return (
    <div className={`${styles.page}${stickyFooter ? " public-shell--sticky" : ""}`}>
      <nav className={styles.nav}>
        <a href="/" className={styles.brand} onClick={go("/")}>
          <BotMessageSquare size={20} color="var(--bs-primary)" />
          <span>UwUchat</span>
        </a>
        <div className={styles.navActions}>
          <LanguageSwitcher />
          <a href="https://github.com/Capsize-Games/uwuchat-oss" className={styles.navLink} target="_blank" rel="noreferrer">
            GitHub
          </a>
          <a href="/login" className={styles.navLink} onClick={go("/login")}>
            {t("publicNav.sign_in")}
          </a>
          <a href="/register" className={styles.navCta} onClick={go("/register")}>
            <Star size={16} strokeWidth={2} aria-hidden="true" /> {t("publicNav.get_started")}
          </a>
        </div>
      </nav>
      <div className={contentClassName}>
        {children}
      </div>
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <span>{t("publicNav.copyright", { year: YEAR })}</span>
          <div className={styles.footerLinks}>
            <a href="https://github.com/Capsize-Games/uwuchat-oss" target="_blank" rel="noreferrer">GitHub</a>
            <a href="/terms" onClick={go("/terms")}>{t("publicNav.terms")}</a>
            <a href="/privacy" onClick={go("/privacy")}>{t("publicNav.privacy")}</a>
            <a href="/data-request" onClick={go("/data-request")}>
              {t("publicNav.data_request")}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
