import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import styles from "./ProfileNotFound.module.css";

interface ProfileNotFoundProps {
  loggedInUsername?: string;
}

export default function ProfileNotFound({
  loggedInUsername,
}: ProfileNotFoundProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className={styles.center}>
      <div className={styles.emoji}>{"\uD83D\uDE3F"}</div>
      <div className={styles.title}>
        {t("user.profile_not_found.title")}
      </div>
      <div className={styles.body}>
        {loggedInUsername ? (
          <>
            {t("user.profile_not_found.your_profile_at")}{" "}
            <span
              onClick={() => navigate(`/user/${loggedInUsername}`)}
              className={styles.link}
            >
              /user/{loggedInUsername}
            </span>
          </>
        ) : (
          t("user.profile_not_found.not_logged_in")
        )}
      </div>
      <button
        onClick={() => navigate("/")}
        className={styles.homeBtn}
      >
        {t("user.profile_not_found.back_to_app")}
      </button>
    </div>
  );
}
