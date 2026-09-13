/**
 * Account menu button rendered at the bottom of the left icon bar.
 *
 * Shows a user-circle icon that opens a dropdown menu with:
 * - Settings
 * - Logout
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "./Provider";
/** Inline Lucide-style SVG icons (avoids path dependency). */
const ICONS = {
  settings: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
  "log-out": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  ),
  user: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="5" />
      <path d="M20 21a8 8 0 1 0-16 0" />
    </svg>
  ),
  shield: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
};

/** Wraps an icon SVG in a fixed-size container so all icons render uniformly. */
const ICON_WRAPPER: React.CSSProperties = {
  width: 16,
  height: 16,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  flexShrink: 0,
};

/** Shared style for every menu row. */
const ROW_STYLE: React.CSSProperties = {
  display: "flex",
  flexDirection: "row",
  alignItems: "center",
  justifyContent: "flex-start",
  gap: 10,
  width: "100%",
  padding: "8px 16px",
  cursor: "pointer",
  boxSizing: "border-box",
  background: "transparent",
  border: "none",
  outline: "none",
  fontSize: 14,
  color: "var(--theme-text)",
  lineHeight: 1.4,
};

export function BottomBar() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => setMenuOpen(false), []);

  // Close menu on outside click.
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        btnRef.current &&
        !btnRef.current.contains(target)
      ) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  return (
    <>
      <div style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center" }}>
        <button
          ref={btnRef}
          className={menuOpen ? "active" : ""}
          onClick={() => setMenuOpen((o) => !o)}
          title={t("bottomBar.account")}
        >
          {ICONS.user}
          <span className="icon-bar-label">
            {t("bottomBar.account")}
          </span>
        </button>

        {menuOpen && (
          <div
            ref={menuRef}
            style={{
              position: "absolute",
              left: "100%",
              bottom: 0,
              width: 200,
              background: "var(--theme-bg-secondary)",
              border: "1px solid var(--theme-border)",
              borderRadius: 0,
              boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
              zIndex: 200,
              overflow: "hidden",
              padding: "4px 0",
            }}
          >
            <Row
              onClick={() => {
                close();
                sessionStorage.setItem("uwuchat_show_user_profile", "1");
                window.dispatchEvent(new Event("airunner:show-user-profile"));
              }}
            >
              <IconWrap>{ICONS.user}</IconWrap>
              {t("bottomBar.viewProfile")}
            </Row>
            <Hr />
            <Row onClick={() => { close(); window.dispatchEvent(new CustomEvent("airunner:open-settings")); }}>
              <IconWrap>{ICONS.settings}</IconWrap>
              {t("bottomBar.settings")}
            </Row>
            <Hr />
            <Row
              danger
              onClick={() => { close(); logout(); }}
            >
              <IconWrap>{ICONS["log-out"]}</IconWrap>
              {t("bottomBar.logout")}
            </Row>
          </div>
        )}
      </div>

    </>
  );
}

/* ── Sub-components ────────────────────────────────────────────────── */

function IconWrap({ children }: { children: React.ReactNode }) {
  return <span style={ICON_WRAPPER}>{children}</span>;
}

function Row({
  children,
  onClick,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        ...ROW_STYLE,
        color: danger ? "var(--bs-danger)" : "var(--theme-text)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = danger
          ? "rgba(255,50,50,0.12)"
          : "rgba(var(--theme-text-rgb), 0.06)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
      }}
    >
      {children}
    </button>
  );
}

function Hr() {
  return (
    <div
      style={{
        borderTop: "1px solid var(--theme-border)",
        margin: "4px 0",
      }}
    />
  );
}
