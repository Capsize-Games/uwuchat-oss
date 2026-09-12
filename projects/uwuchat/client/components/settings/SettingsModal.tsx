import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import Button from "react-bootstrap/Button";
import LucideIcon from "@/components/shared/LucideIcon";
import UserSection from "@/components/settings/sections/UserSection";
import AppearanceSection from "@/components/settings/sections/AppearanceSection";
import LanguageSection from "./sections/LanguageSection";
import AccountSection from "./sections/AccountSection";
import IntegrationsSection from "./sections/IntegrationsSection";
import ImmersionSection from "./sections/ImmersionSection";
import LocationSection from "./sections/LocationSection";
import HeadlesscodeProjectsPanel from "./sections/HeadlesscodeProjectsPanel";
import HostExecSection from "./sections/HostExecSection";
import { useImmersion } from "../../hooks/useImmersion";
import { useLocalStorage } from "@/hooks/useLocalStorage";

type SectionId =
  | "user"
  | "appearance"
  | "language"
  | "account"
  | "immersion"
  | "integrations"
  | "location"
  | "headlesscode"
  | "hostexec";

const NAV_ENTRY_DEFS: { id: SectionId; labelKey: string; icon: string }[] = [
  { id: "headlesscode",  labelKey: "settings.nav.headlesscode",  icon: "folder-open" },
  { id: "hostexec",      labelKey: "settings.nav.hostexec",      icon: "terminal" },
  { id: "integrations",  labelKey: "settings.nav.integrations",  icon: "link" },
  { id: "immersion",     labelKey: "settings.nav.immersion",     icon: "cloud-fog" },
  { id: "user",          labelKey: "settings.nav.user",          icon: "user" },
  { id: "appearance",    labelKey: "settings.nav.appearance",    icon: "palette" },
  { id: "language",      labelKey: "settings.nav.language",      icon: "globe" },
  { id: "location",      labelKey: "settings.nav.location",      icon: "cloud-sun" },
  { id: "account",       labelKey: "settings.nav.account",       icon: "user-cog" },
];

const LS_KEY = "airunner_settings_section";

export default function SettingsModal({
  onClose,
}: {
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { immersion, setImmersion } = useImmersion();
  const [activeSection, setActiveSection] = useLocalStorage<SectionId>(
    LS_KEY,
    "user",
  );

  // Check URL search params on mount (e.g. ?tab=integrations from
  // OAuth redirects) — these must take priority over localStorage.
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const tabParam = params.get("tab");
      if (tabParam && NAV_ENTRY_DEFS.some((e) => e.id === tabParam)) {
        setActiveSection(tabParam as SectionId);
      }
    } catch { /* ignore */ }
  }, [setActiveSection]);

  function handleNavClick(id: SectionId) {
    setActiveSection(id);
  }

  function renderSection() {
    switch (activeSection) {
      case "user":
        return <UserSection />;
      case "appearance":
        return <AppearanceSection />;
      case "language":
        return <LanguageSection />;
      case "immersion":
        return <ImmersionSection value={immersion} onChange={setImmersion} />;
      case "integrations":
        return <IntegrationsSection />;
      case "location":
        return <LocationSection />;
      case "account":
        return <AccountSection />;
      case "headlesscode":
        return <HeadlesscodeProjectsPanel />;
      case "hostexec":
        return <HostExecSection />;
      default:
        return <UserSection />;
    }
  }

  return (
    <div className="settings-modal-backdrop" onClick={onClose}>
      <div
        className="settings-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t("settings.title")}
      >
        <div className="settings-modal-header">
          <h5 className="mb-0">{t("settings.title")}</h5>
          <Button
            variant="link"
            className="text-light p-0 d-flex align-items-center"
            onClick={onClose}
            size="sm"
          >
            <LucideIcon name="circle-x" size={20} />
          </Button>
        </div>
        <div className="settings-modal-body">
          <nav className="settings-nav">
            {NAV_ENTRY_DEFS.map((entry) => (
              <button
                key={entry.id}
                className={
                  "settings-nav-item" +
                  (activeSection === entry.id ? " active" : "")
                }
                onClick={() => handleNavClick(entry.id)}
              >
                <LucideIcon name={entry.icon} size={18} />
                <span>{t(entry.labelKey)}</span>
              </button>
            ))}
          </nav>
          <div className="settings-content">{renderSection()}</div>
        </div>
      </div>
    </div>
  );
}
