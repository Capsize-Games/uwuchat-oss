import { useTranslation } from "react-i18next";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import { useUserSetup } from "../../hooks/useUserSetup";
import UserProfilePanel from "./UserProfilePanel";
import ProfileNotFound from "./page/ProfileNotFound";
import styles from "./UserProfilePage.module.css";

export default function UserProfilePage() {
  const { t } = useTranslation();
  const { username } = useParams<{ username: string }>();
  const navigate = useNavigate();
  const { user: authUser } = useAuth();
  const { user: setupUser } = useUserSetup();

  const isOwnProfile =
    authUser !== null &&
    username !== undefined &&
    username === authUser.username;

  if (!isOwnProfile) {
    return <ProfileNotFound loggedInUsername={authUser?.username} />;
  }

  const displayName =
    setupUser?.display_name ?? authUser?.username ?? "User";

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <button
          onClick={() => navigate("/")}
          className={styles.backBtn}
        >
          {t("user.profile_page.back")}
        </button>
        <span className={styles.title}>
          {displayName}&rsquo;s Profile
        </span>
      </div>

      <UserProfilePanel />
    </div>
  );
}
