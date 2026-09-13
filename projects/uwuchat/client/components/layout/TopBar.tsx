import { useEffect, useRef, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import LucideIcon from "@/components/shared/LucideIcon";
import styles from "./TopBar.module.css";
import { useAuth } from "../../hooks/useAuth";
import { useDeployment } from "@/context/DeploymentContext";
import { useIsMobile } from "../../hooks/useIsMobile";
import { useUserSetup } from "../../hooks/useUserSetup";
import { getAvatarSrc } from "../../utils/avatar";
import AuthedLanguageSwitcher from "./AuthedLanguageSwitcher";

export default function TopBar() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { user: profileUser } = useUserSetup();
  const { deployment, setDeployment } = useDeployment();
  const isSuperuser = user?.is_superuser === true;
  const isCloud = deployment === "cloud";
  const isMobile = useIsMobile();
  const [menuOpen, setMenuOpen] = useState(false);
  const [panelType, setPanelType] = useState<string | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    const handler = (e: Event) => { const d = (e as CustomEvent<{ panelType: string | null }>).detail; setPanelType(d?.panelType ?? null); };
    window.addEventListener("uwuchat:panel-changed", handler);
    return () => window.removeEventListener("uwuchat:panel-changed", handler);
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => { const t = e.target as Node; if (menuRef.current && !menuRef.current.contains(t) && btnRef.current && !btnRef.current.contains(t)) setMenuOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  const contactsActive = panelType === "contacts";
  const profileActive = menuOpen || panelType === "user-profile";

  return (
    // eslint-disable-next-line no-restricted-syntax -- state-driven conditional style
    <div className={styles.bar} style={{ padding: isMobile ? "6px 10px" : "6px 14px" }}>
      <div onClick={() => window.dispatchEvent(new Event("uwuchat:toggle-contacts"))} className={styles.logoArea}>
        <LucideIcon name="bot" size={18} color="var(--theme-primary, #0084b9)" />
        <span className={styles.uwuBrand}>UwU<span className="text-theme-primary">chat</span></span>
      </div>
      <div className="d-flex align-items-center gap-1">
        <AuthedLanguageSwitcher />
        <button type="button" onClick={() => window.dispatchEvent(new Event("uwuchat:toggle-contacts"))} title={t("sidebar.contacts")} className={contactsActive ? styles.barBtnActive : styles.barBtnInactive}>
          <LucideIcon name="users" size={18} />
        </button>
        <div className={styles.relative}>
          <button ref={btnRef} type="button" onClick={() => setMenuOpen((o) => !o)} title={t("bottomBar.account")} className={profileActive ? styles.barBtnActive : styles.barBtnInactive}>
            {profileUser?.avatar_image ? (
              <img src={getAvatarSrc(profileUser.avatar_image) ?? ""} alt="" className={styles.avatarImgSmall} />
            ) : (
              <LucideIcon name="user" size={18} />
            )}
          </button>
          {menuOpen && (
            <div ref={menuRef} className={styles.menuDropdown}>
              <HeaderMenuRow onClick={() => { closeMenu(); sessionStorage.setItem("uwuchat_show_user_profile", "1"); window.dispatchEvent(new Event("uwuchat:show-user-profile")); }}><LucideIcon name="user" size={16} />{t("bottomBar.viewProfile")}</HeaderMenuRow>
              <HeaderMenuDivider />
              <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new CustomEvent("airunner:open-settings")); }}><LucideIcon name="settings" size={16} />{t("bottomBar.settings")}</HeaderMenuRow>
              <HeaderMenuDivider />
              {isSuperuser && (<>
                <HeaderMenuRow onClick={() => { closeMenu(); setDeployment(isCloud ? "edge" : "cloud"); }}><LucideIcon name="cloud" size={16} color={isCloud ? "#4caf50" : undefined} />{isCloud ? "Cloud" : "Edge"}</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:toggle-inspection")); }}><LucideIcon name="scan-search" size={16} />Inspect</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-fastsearch-status")); }}><LucideIcon name="globe" size={16} />Search</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-admin-users")); }}><LucideIcon name="users" size={16} />Users</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-admin-promotions")); }}><LucideIcon name="ticket-percent" size={16} />Promotions</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-admin-reports")); }}><LucideIcon name="flag" size={16} />Reports</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-admin-calendar")); }}><LucideIcon name="calendar" size={16} />Agent Calendar</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-admin-costs")); }}><LucideIcon name="dollar-sign" size={16} />Costs</HeaderMenuRow>
                <HeaderMenuDivider />
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-admin-waitlist")); }}><LucideIcon name="list" size={16} />Waitlist</HeaderMenuRow>
                <HeaderMenuRow onClick={() => { closeMenu(); window.dispatchEvent(new Event("airunner:show-admin-disputes")); }}><LucideIcon name="alert-triangle" size={16} />Disputes</HeaderMenuRow>
              </>)}
              <HeaderMenuRow danger onClick={() => { closeMenu(); logout(); }}><LucideIcon name="log-out" size={16} />{t("bottomBar.logout")}</HeaderMenuRow>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function HeaderMenuRow({ children, onClick, danger }: { children: React.ReactNode; onClick: () => void; danger?: boolean; }) {
  return <button onClick={onClick} className={danger ? styles.headerMenuRowDanger : styles.headerMenuRow}>{children}</button>;
}

function HeaderMenuDivider() {
  return <div className={styles.menuDivider} />;
}
