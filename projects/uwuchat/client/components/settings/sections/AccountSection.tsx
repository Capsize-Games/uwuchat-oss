/** Account settings for the self-hosted UwUchat build. */

import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { SettingsButton } from "../SettingsButton";
import styles from "./AccountSection.module.css";

export default function AccountSection() {
  const { t } = useTranslation();
  const { user } = useAuth();

  return (
    <div>
      <h6 className={`text-uppercase small mb-3 ${styles.sectionHeading}`}>
        {t("settings.account.heading")}
      </h6>
      {user && (
        <div className="mb-4">
          <div className="mb-2 small">
            <span className={styles.emailLabel}>
              {t("settings.account.email")} {" "}
            </span>
            <span className={styles.emailValue}>{user.email}</span>
          </div>
          <SettingsButton
            className={`mt-2 ${styles.settingsBtn}`}
            onClick={() => {
              sessionStorage.setItem("uwuchat_show_user_profile", "1");
              window.dispatchEvent(new Event("airunner:close-settings"));
              window.dispatchEvent(new Event("uwuchat:show-user-profile"));
            }}
          >
            {t("settings.account.view_profile")}
          </SettingsButton>
        </div>
      )}
      <p className={`${styles.subText} small mb-3`}>
        Billing is disabled in the self-hosted build. Configure your own
        billing provider if this deployment needs subscriptions.
      </p>
    </div>
  );
}
